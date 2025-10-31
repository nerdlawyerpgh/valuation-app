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

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib import colors
from io import BytesIO
import base64

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

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
ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "https://valuation.nerdlawyer.ai/", "http://localhost:3000")
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
def send_notification_email(subject: str, body: str, attachment_data: Optional[BytesIO] = None, attachment_name: str = "valuation_report.pdf"):
    """Send notification email with optional PDF attachment"""
    api_key = os.getenv("SENDGRID_API_KEY")
    to_email = os.getenv("NOTIFICATION_EMAIL")
    
    if not api_key or not to_email:
        return
    
    try:
        message = Mail(
            from_email='curt@nerdlawyer.ai',
            to_emails=to_email,
            subject=subject,
            html_content=body
        )
        
        if attachment_data:
            from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition
            attachment_data.seek(0)
            encoded = base64.b64encode(attachment_data.read()).decode()
            
            attached_file = Attachment(
                FileContent(encoded),
                FileName(attachment_name),
                FileType('application/pdf'),
                Disposition('attachment')
            )
            message.attachment = attached_file
        
        sg = SendGridAPIClient(api_key)
        sg.send(message)
        print(f"[Email] Sent successfully{'with PDF attachment' if attachment_data else ''}")
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

def _gs_append_row(worksheet_name: str, row: List[Any], headers: Optional[List[str]] = None) -> None:
    """Append a row to a worksheet; create the worksheet if missing with optional headers."""
    _gs_init_once()
    if _gs_sheet is None:
        return
    try:
        try:
            ws = _gs_sheet.worksheet(worksheet_name)
        except Exception:
            # Create new worksheet with headers
            ws = _gs_sheet.add_worksheet(title=worksheet_name, rows=1000, cols=26)
            if headers:
                ws.append_row(headers, value_input_option="USER_ENTERED")
        
        ws.append_row(row, value_input_option="USER_ENTERED")
        print(f"[Google Sheets] Logged to {worksheet_name}")
    except Exception as e:
        print(f"[Google Sheets] Failed to append to {worksheet_name}: {e}")

# -----------------------------------------------------------------------------
# PDF Generation helpers
# -----------------------------------------------------------------------------
def _create_valuation_chart(payload: ValuationRunIn) -> BytesIO:
    """Create a horizontal bar chart showing valuation ranges"""
    fig, ax = plt.subplots(figsize=(8, 4))
    
    categories = []
    lows = []
    highs = []
    currents = []
    
    # PE Stack
    pe_val = payload.ev_pe_stack or (payload.ebitda * 5.92) if payload.ebitda else None
    if pe_val:
        categories.append('PE Equity Stack')
        lows.append(pe_val)
        highs.append(pe_val)
        currents.append(pe_val)
    
    # TEV Band
    if payload.ev_tev_current and payload.ev_tev_avg:
        categories.append('All-Industry\n(TEV Band)')
        lows.append(min(payload.ev_tev_current, payload.ev_tev_avg))
        highs.append(max(payload.ev_tev_current, payload.ev_tev_avg))
        currents.append(payload.ev_tev_current)
    elif payload.enterprise_value:
        categories.append('All-Industry\n(TEV Band)')
        lows.append(payload.enterprise_value * 0.9)
        highs.append(payload.enterprise_value * 1.1)
        currents.append(payload.enterprise_value)
    
    # Industry Specific
    if payload.ev_ind_current and payload.ev_ind_avg:
        categories.append(f'{payload.industry or "Industry"}\nSpecific')
        lows.append(min(payload.ev_ind_current, payload.ev_ind_avg))
        highs.append(max(payload.ev_ind_current, payload.ev_ind_avg))
        currents.append(payload.ev_ind_current)
    
    if not categories:
        # Return empty chart if no data
        plt.close()
        return None
    
    # Create horizontal bars
    y_pos = range(len(categories))
    
    # Plot ranges as bars
    for i, (low, high) in enumerate(zip(lows, highs)):
        ax.barh(i, high - low, left=low, height=0.4, 
                color='lightblue', alpha=0.4, edgecolor='steelblue')
    
    # Plot current values as points
    ax.scatter(currents, y_pos, color='navy', s=100, zorder=3, marker='o', label='Current')
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(categories)
    ax.set_xlabel('Enterprise Value (USD)', fontsize=10)
    ax.set_title('Valuation Comparison', fontsize=12, fontweight='bold')
    
    # Format x-axis as currency
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1e6:.1f}M'))
    
    ax.grid(True, axis='x', alpha=0.3)
    ax.legend(loc='lower right')
    
    plt.tight_layout()
    
    # Save to buffer
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf

def generate_valuation_pdf(payload: ValuationRunIn) -> BytesIO:
    """Generate a comprehensive PDF report with charts"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        alignment=1  # Center
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        spaceAfter=20,
        alignment=1
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2c5282'),
        spaceAfter=12,
        spaceBefore=16,
        borderWidth=0,
        borderPadding=0,
        leftIndent=0
    )
    
    story = []
    
    # Header with company info
    story.append(Paragraph("JORDON VOYTEK CAPITAL PARTNERS", title_style))
    story.append(Paragraph("Company Valuation Report", subtitle_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Executive Summary Box
    summary_data = [[Paragraph("<b>EXECUTIVE SUMMARY</b>", styles['Normal'])]]
    summary_table = Table(summary_data, colWidths=[6.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e6f2ff')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#2c5282')),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.1*inch))
    
    # Date & Contact Information
    contact_data = [
        ['Report Date:', _utcnow_iso().split('T')[0]],
        ['Contact:', payload.email or 'Not provided'],
        ['Phone:', payload.phone or 'Not provided'],
        ['Location:', payload.location or 'Not provided'],
    ]
    
    contact_table = Table(contact_data, colWidths=[1.5*inch, 5*inch])
    contact_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(contact_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Input Parameters Section
    story.append(Paragraph("Input Parameters", heading_style))
    
    input_data = [
        ['<b>Parameter</b>', '<b>Value</b>'],
        ['TTM EBITDA', f"${payload.ebitda:,.0f}"],
        ['Debt Financing', f"{payload.debt_pct * 100:.1f}%" if payload.debt_pct else "Not specified"],
        ['Industry', payload.industry or "All-Industry"],
    ]
    
    input_table = Table(input_data, colWidths=[2.5*inch, 4*inch])
    input_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(input_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Valuation Results Section
    story.append(Paragraph("Estimated Valuation", heading_style))
    
    results_data = [
        ['<b>Metric</b>', '<b>Value</b>'],
        ['<b>Total Enterprise Value (TEV)</b>', 
        f"<b>${payload.enterprise_value:,.0f}</b>" if payload.enterprise_value else "N/A"],
        ['TEV Range', 
        f"${payload.expected_low:,.0f} - ${payload.expected_high:,.0f}" 
        if payload.expected_low and payload.expected_high else "N/A"],
    ]
    
    results_table = Table(results_data, colWidths=[2.5*inch, 4*inch])
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#fff5f5'), colors.white]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(results_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Add chart
    chart_buffer = _create_valuation_chart(payload)
    if chart_buffer:
        story.append(Paragraph("Valuation Comparison Chart", heading_style))
        img = Image(chart_buffer, width=6.5*inch, height=3.25*inch)
        story.append(img)
        story.append(Spacer(1, 0.2*inch))
    
    # Detailed Breakdown
    story.append(Paragraph("Valuation Methodology Breakdown", heading_style))
    
    methodology_text = """
    <b>Total Enterprise Value (TEV)</b> reflects the value of a company's core operations—its 
    equity plus net debt:<br/>
    <br/>
    <i>TEV = Market Capitalization + Total Debt − Cash &amp; Cash Equivalents</i><br/>
    <br/>
    This valuation uses industry-specific multiples from GF Data and PE cap-stack benchmarks 
    to estimate your company's value across multiple methodologies.
    """
    story.append(Paragraph(methodology_text, styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Methodology details table
    if payload.ev_tev_current or payload.ev_ind_current or payload.ev_pe_stack:
        method_data = [['<b>Methodology</b>', '<b>Estimated Value</b>']]
        
        if payload.ev_pe_stack:
            method_data.append(['PE Equity Stack', f"${payload.ev_pe_stack:,.0f}"])
        if payload.ev_tev_current:
            method_data.append(['All-Industry (Current)', f"${payload.ev_tev_current:,.0f}"])
        if payload.ev_tev_avg:
            method_data.append(['All-Industry (5-yr Avg)', f"${payload.ev_tev_avg:,.0f}"])
        if payload.ev_ind_current:
            method_data.append([f'{payload.industry} (Current)', f"${payload.ev_ind_current:,.0f}"])
        if payload.ev_ind_avg:
            method_data.append([f'{payload.industry} (5-yr Avg)', f"${payload.ev_ind_avg:,.0f}"])
        
        method_table = Table(method_data, colWidths=[3*inch, 3.5*inch])
        method_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(method_table)
        story.append(Spacer(1, 0.3*inch))
    
    # Page break before disclaimer
    story.append(PageBreak())
    
    # Important Notice / Disclaimer
    story.append(Paragraph("Important Legal Notice", heading_style))
    
    disclaimer_data = [[Paragraph("""
    The valuations presented in this report are derived from estimated TEV and public/benchmark 
    multiples based on private equity transactions occurring in 2025 and over the last 5 years 
    in your industry. <b>These estimates are directional only.</b><br/>
    <br/>
    A more accurate conclusion of value requires an in-depth review of your company's financial 
    statements (historical and forecast), normalization adjustments, capital structure (net debt 
    and debt-like items), working-capital targets, industry dynamics, and deal-specific terms.<br/>
    <br/>
    <b>The results are not a fairness opinion or appraisal and should not be relied upon as 
    investment, tax, accounting, or legal advice.</b> Please consult with qualified professionals 
    before making any business decisions based on this report.
    """, styles['Normal'])]]
    
    disclaimer_table = Table(disclaimer_data, colWidths=[6.5*inch])
    disclaimer_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff5f5')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e53e3e')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(disclaimer_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Footer
    footer_text = """
    <para alignment="center">
    <b>Jordon Voytek Capital Partners</b><br/>
    For questions or to schedule a consultation, please contact us.<br/>
    © 2025 Jordon Voytek Capital Partners. All rights reserved.
    </para>
    """
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(footer_text, styles['Normal']))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer

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
    location: Optional[str] = None 

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

@app.post("/log/access")
async def log_access(req: Request, payload: AccessRequestIn):
    ip = _client_ip(req)
    ua = _user_agent(req)
    row = [
        _utcnow_iso(),
        payload.email,
        payload.phone or "",
        payload.location or "",
        ip,
        ua,
        payload.approx_city or "",
        payload.approx_region or "",
        payload.approx_country or "",
        payload.lat if payload.lat is not None else "",
        payload.lon if payload.lon is not None else "",
        payload.referrer or "",
    ]
    
    headers = [
        "Timestamp", "Email", "Phone", "Location", "IP Address", "User Agent",
        "City", "Region", "Country", "Latitude", "Longitude", "Referrer"
    ]
    
    _gs_append_row("AccessRequests", row, headers)
    
    # Send email notification...
    return {"ok": True}

@app.post("/log/valuation")
async def log_valuation(payload: ValuationRunIn):
    row = [
        _utcnow_iso(),
        payload.email or "",
        payload.phone or "",
        payload.location or "",
        payload.ebitda,
        payload.debt_pct if payload.debt_pct is not None else "",
        payload.industry or "",
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
    
    headers = [
        "Timestamp", "Email", "Phone", "Location", "EBITDA", "Debt %", "Industry",
        "EV TEV Current", "EV TEV Avg", "EV Ind Current", "EV Ind Avg",
        "EV PE Stack", "Expected Valuation", "Expected Low", "Expected High",
        "Band Label", "Notes"
    ]
    
    _gs_append_row("ValuationRuns", row, headers)

    # Generate PDF report
    pdf_buffer = generate_valuation_pdf(payload)
    
    # Send email notification...
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
        <p><strong>Location:</strong> {payload.location or 'Not provided'}</p>
        <p><strong>Time:</strong> {_utcnow_iso()}</p>
        
        <h4>Inputs:</h4>
        <ul>
            <li><strong>EBITDA:</strong> {ebitda_formatted}</li>
            <li><strong>Debt %:</strong> {debt_pct_formatted}</li>
            <li><strong>Industry:</strong> {payload.industry or 'Not specified'}</li>
        </ul>
        
        <h4>Results:</h4>
        <ul>
            <li><strong>Total Enterprise Value (TEV):</strong> {ev_formatted}</li>
            <li><strong>TEV Range:</strong> {expected_low_formatted} - {expected_high_formatted}</li>
        </ul>

        """,
        attachment_data=pdf_buffer,
        attachment_name=f"valuation_report_{payload.email or 'user'}_{_utcnow_iso().split('T')[0]}.pdf"
    )
    
    return {"ok": True}

@app.post("/compute-valuation")
async def compute(payload: ValuationInput):
    """
    Your existing valuation endpoint.
    """
    result = compute_valuation(payload)
    return result
