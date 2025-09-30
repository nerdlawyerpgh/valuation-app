# backend/app/google_sheets.py
import os, json, datetime as dt
from typing import List
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NAME = os.getenv("GSHEET_NAME", "JVCP Valuation Logs")  # or put the spreadsheet key in env

def _client():
    # You can provide the service account JSON either as a path or as raw JSON in env
    #key_json = os.getenv("jovocp-valuation-app-1a1e6cb00422.json")
    key_path = os.getenv("jovocp-valuation-app-1a1e6cb00422.json")
    if key_json:
        info = json.loads(key_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    elif key_path:
        creds = Credentials.from_service_account_file(key_path, scopes=SCOPES)
    else:
        raise RuntimeError("Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE")
    return gspread.authorize(creds)

def _open_sheet():
    gc = _client()
    # Prefer spreadsheet key via env to avoid name collisions:
    spreadsheet_key = os.getenv("GSHEET_SPREADSHEET_KEY")
    if spreadsheet_key:
        return gc.open_by_key(spreadsheet_key)
    return gc.open(SHEET_NAME)

def append_row(worksheet_name: str, row: List):
    sh = _open_sheet()
    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=1000, cols=26)
        # Optionally, write headers when creating
    ws.append_row(row, value_input_option="USER_ENTERED")
