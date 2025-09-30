# backend/app/main.py
from __future__ import annotations

import os
import json
import datetime as dt
from typing import Optional, List, Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Your valuation logic
from .valuations import compute_valuation, ValuationInput  # ValuationOutput not required to import

from pathlib import Path
from dotenv import load_dotenv

# Resolve backend/.env regardless of where uvicorn is launched
DOTENV_PATH = (Path(__file__).resolve().parents[1] / ".env")
load_dotenv(dotenv_path=DOTENV_PATH, override=True)
print(f"[env] loaded .env from {DOTENV_PATH.exists() and DOTENV_PATH or 'NOT FOUND'}")

# -----------------------------------------------------------------------------
# CORS (adjust via env)
# -----------------------------------------------------------------------------
ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
ALLOW_ORIGINS_LIST = [o.strip() for o in ALLOW_ORIGINS.split(",") if o.strip()]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -----------------------------------------------------------------------------
# SendGrid helpers 
# -----------------------------------------------------------------------------
def send_notification_email(subject: str, body: str):
    """Send notification email when new data is logged"""
    api_key = os.getenv("SENDGRID_API_KEY")
    to_email = os.getenv("NOTIFICATION_EMAIL")
    
    if not api_key or not to_email:
        return  # Skip if not configured
    
    try:
        message = Mail(
            from_email='curt@nerdlawyer.ai',
            to_emails=to_email,
            subject=subject,
            html_content=body
        )
        sg = SendGridAPIClient(api_key)
        sg.send(message)
    except Exception as e:
        print(f"[Email] Failed to send: {e}")

# -----------------------------------------------------------------------------
# Google Sheets helpers (no-op if not configured)
# -----------------------------------------------------------------------------
_GS_READY = False
_gs_client = None
_gs_sheet = None

def _utcnow_iso() -> str:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()

def _gs_init_once() -> None:
    """Initialize gspread client once per process. If not configured, remain no-op."""
    global _GS_READY, _gs_client, _gs_sheet
    if _GS_READY:  # already tried
        return

    try:
        import gspread  # type: ignore
        from google.oauth2.service_account import Credentials  # type: ignore

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        key_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        key_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        spreadsheet_key = os.getenv("GSHEET_SPREADSHEET_KEY")
        spreadsheet_name = os.getenv("GSHEET_NAME", "JVCP Valuation Logs")

        if not (key_json or key_path):
            # Not configured; stay as no-op
            print("[Google Sheets] No credentials configured - logging disabled")
            _GS_READY = True
            return

        if key_json:
            info = json.loads(key_json)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(key_path, scopes=scopes)

        _gs_client = gspread.authorize(creds)
        if spreadsheet_key:
            _gs_sheet = _gs_client.open_by_key(spreadsheet_key)
        else:
            _gs_sheet = _gs_client.open(spreadsheet_name)

        print(f"[Google Sheets] Successfully connected to spreadsheet")
        _GS_READY = True
    except Exception as e:
        # Log the actual error so you can debug
        print(f"[Google Sheets] Failed to initialize: {e}")
        _GS_READY = True
        _gs_client = None
        _gs_sheet = None

def _gs_append_row(worksheet_name: str, row: List[Any]) -> None:
    """Append a row to a worksheet; create the worksheet if missing. No-op if not configured."""
    _gs_init_once()
    if _gs_sheet is None:
        return  # no-op when credentials/sheet not configured
    try:
        try:
            ws = _gs_sheet.worksheet(worksheet_name)
        except Exception:
            ws = _gs_sheet.add_worksheet(title=worksheet_name, rows=1000, cols=26)
        ws.append_row(row, value_input_option="USER_ENTERED")
        print(f"[Google Sheets] Logged to {worksheet_name}")
    except Exception as e:
        # Log errors so you can debug
        print(f"[Google Sheets] Failed to append to {worksheet_name}: {e}")

# -----------------------------------------------------------------------------
# Utilities to capture metadata
# -----------------------------------------------------------------------------
def _client_ip(req: Request) -> str:
    xfwd = req.headers.get("x-forwarded-for")
    if xfwd:
        return xfwd.split(",")[0].strip()
    return req.client.host if req.client else "unknown"

def _user_agent(req: Request) -> str:
    return req.headers.get("user-agent", "unknown")

# -----------------------------------------------------------------------------
# Pydantic models for logging endpoints
# -----------------------------------------------------------------------------
class AccessRequestIn(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    # Optional location hints (only send if user consents)
    lat: Optional[float] = None
    lon: Optional[float] = None
    approx_city: Optional[str] = None
    approx_region: Optional[str] = None
    approx_country: Optional[str] = None
    referrer: Optional[str] = None

class ValuationRunIn(BaseModel):
    # Inputs we always know:
    ebitda: float
    debt_pct: Optional[float] = None
    industry: Optional[str] = None
    email: Optional[EmailStr] = None  # if you have it in the client
    phone: Optional[str] = None 

    # Outputs to be logged (client should pass back what it received)
    enterprise_value: Optional[float] = None
    expected_valuation: Optional[float] = None
    expected_low: Optional[float] = None
    expected_high: Optional[float] = None
    ev_tev_current: Optional[float] = None
    ev_tev_avg: Optional[float] = None
    ev_ind_current: Optional[float] = None
    ev_ind_avg: Optional[float] = None
    ev_pe_stack: Optional[float] = None
    band_label: Optional[str] = None
    notes: Optional[str] = None

# -----------------------------------------------------------------------------
# API endpoints
# -----------------------------------------------------------------------------

@app.get("/debug/env")
async def debug_env():
    return {
        "GSHEET_SPREADSHEET_KEY": bool(os.getenv("GSHEET_SPREADSHEET_KEY")),
        "GOOGLE_SERVICE_ACCOUNT_FILE": os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        "GOOGLE_SERVICE_ACCOUNT_JSON": bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")),
    }

@app.post("/log/valuation")
async def log_valuation(payload: ValuationRunIn):
    """
    Log a valuation run (inputs + outputs).
    The frontend should POST here right after it receives the results from /compute-valuation.
    """
    row = [
        _utcnow_iso(),
        payload.email or "",
        payload.phone or "",
        payload.ebitda,
        payload.debt_pct if payload.debt_pct is not None else "",
        payload.industry or "",
        # Outputs / tracks:
        payload.ev_tev_current if payload.ev_tev_current is not None else payload.enterprise_value or "",
        payload.ev_tev_avg or "",
        payload.ev_ind_current or "",
        payload.ev_ind_avg or "",
        payload.ev_pe_stack or "",
        payload.expected_valuation or "",
        payload.expected_low or "",
        payload.expected_high or "",
        payload.band_label or "",
        payload.notes or "",
    ]
    _gs_append_row("ValuationRuns", row)
    
    # Send email with valuation data
    # Format values safely before using them in the email
    ev_formatted = f"${payload.enterprise_value:,.0f}" if payload.enterprise_value else "N/A"
    expected_formatted = f"${payload.expected_valuation:,.0f}" if payload.expected_valuation else "N/A"
    expected_low_formatted = f"${payload.expected_low:,.0f}" if payload.expected_low else "N/A"
    expected_high_formatted = f"${payload.expected_high:,.0f}" if payload.expected_high else "N/A"
    ebitda_formatted = f"${payload.ebitda:,.0f}"
    debt_pct_formatted = f"{payload.debt_pct * 100:.0f}%" if payload.debt_pct else "N/A"

    send_notification_email(
        subject=f"New Valuation: {payload.email or 'Unknown User'}",
        body=f"""
        <h3>New Valuation Completed</h3>
        <p><strong>Email:</strong> {payload.email or 'Not provided'}</p>
        <p><strong>Phone:</strong> {payload.phone or 'Not provided'}</p>
        <p><strong>Time:</strong> {_utcnow_iso()}</p>
        
        <h4>Inputs:</h4>
        <ul>
            <li><strong>EBITDA:</strong> {ebitda_formatted}</li>
            <li><strong>Debt %:</strong> {debt_pct_formatted}</li>
            <li><strong>Industry:</strong> {payload.industry or 'Not specified'}</li>
        </ul>
        
        <h4>Results:</h4>
        <ul>
            <li><strong>Enterprise Value:</strong> {ev_formatted}</li>
            <li><strong>Expected Valuation:</strong> {expected_formatted}</li>
            <li><strong>Expected Range:</strong> {expected_low_formatted} - {expected_high_formatted}</li>
        </ul>
        """
    )
    
    return {"ok": True}

@app.post("/compute-valuation")
async def compute(payload: ValuationInput):
    """
    Your existing valuation endpoint.
    """
    result = compute_valuation(payload)
    return result
