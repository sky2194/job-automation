"""
Google Sheets Storage Module
Saves job data, scores, and application status.
Provides get_applied_urls() to prevent duplicate applications.
"""
import json
import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS = [
    "Date", "Title", "Company", "URL", "Source",
    "Score", "Reason", "Status", "Cover Letter", "Tags",
]

_sheet_cache: dict = {}


def _get_sheet(api_config: dict):
    """Return the gspread Spreadsheet object, creating it with headers if needed."""
    creds_file = api_config.get("sheets_creds", "credentials.json")
    sheet_name = api_config.get("sheet_name", "Job Automation Tracker")
    cache_key = f"{creds_file}:{sheet_name}"

    if cache_key in _sheet_cache:
        return _sheet_cache[cache_key]

    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    gc = gspread.authorize(creds)

    try:
        spreadsheet = gc.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        spreadsheet = gc.create(sheet_name)
        ws = spreadsheet.sheet1
        ws.update("A1:J1", [SHEET_HEADERS])
        ws.format("A1:J1", {"textFormat": {"bold": True}})
        log.info("  Created new Google Sheet: %s", sheet_name)

    _sheet_cache[cache_key] = spreadsheet
    return spreadsheet


def save_to_sheets(job: dict, api_config: dict) -> None:
    """Append a job row to Google Sheets, falling back to local JSON on error."""
    try:
        sheet = _get_sheet(api_config)
        ws = sheet.sheet1
        ws.append_row(
            [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                job.get("title", ""),
                job.get("company", ""),
                job.get("url", ""),
                job.get("source", ""),
                job.get("score", 0),
                job.get("reason", ""),
                job.get("status", "new"),
                (job.get("cover_letter") or "")[:500],
                ", ".join(job.get("tags", [])[:5]),
            ],
            value_input_option="USER_ENTERED",
        )
    except Exception as exc:
        log.warning("  Sheets save failed: %s — saving locally", exc)
        save_local_backup(job)


def get_applied_urls(api_config: dict) -> set[str]:
    """
    Return the set of job URLs already saved to Sheets (status != 'error').
    Falls back to the local backup file if Sheets is unavailable.
    """
    creds_file = api_config.get("sheets_creds", "credentials.json")
    if not os.path.exists(creds_file):
        return _applied_urls_from_backup()

    try:
        sheet = _get_sheet(api_config)
        ws = sheet.sheet1
        records = ws.get_all_records()
        return {
            r["URL"]
            for r in records
            if r.get("URL") and r.get("Status", "").lower() not in ("error", "")
        }
    except Exception as exc:
        log.warning("  Could not fetch applied URLs from Sheets: %s — using local backup", exc)
        return _applied_urls_from_backup()


def _applied_urls_from_backup() -> set[str]:
    backup_file = "jobs_backup.json"
    if not os.path.exists(backup_file):
        return set()
    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {entry["url"] for entry in data if entry.get("url") and entry.get("status") not in ("error", None)}
    except Exception:
        return set()


def update_status(job_url: str, new_status: str, api_config: dict) -> None:
    """Find a row by URL and update its Status column."""
    try:
        sheet = _get_sheet(api_config)
        ws = sheet.sheet1
        cell = ws.find(job_url)
        if cell:
            ws.update_cell(cell.row, SHEET_HEADERS.index("Status") + 1, new_status)
    except Exception as exc:
        log.warning("  Status update failed: %s", exc)


def save_local_backup(job: dict) -> None:
    """Append a minimal job record to jobs_backup.json."""
    backup_file = "jobs_backup.json"
    try:
        data: list = []
        if os.path.exists(backup_file):
            with open(backup_file, "r", encoding="utf-8") as f:
                data = json.load(f)

        data.append({
            "date": datetime.now().isoformat(),
            "title": job.get("title"),
            "company": job.get("company"),
            "url": job.get("url"),
            "score": job.get("score"),
            "status": job.get("status"),
        })

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        log.error("  Local backup failed: %s", exc)


def get_all_jobs(api_config: dict) -> list[dict]:
    """Retrieve all tracked jobs from Google Sheets."""
    try:
        sheet = _get_sheet(api_config)
        return sheet.sheet1.get_all_records()
    except Exception as exc:
        log.warning("  Could not retrieve all jobs: %s", exc)
        return []
