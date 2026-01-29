"""
Google Sheets integration for storing apartment listings.
"""

import logging
from typing import List, Dict
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

HEADERS = [
    "Date Added",
    "Title",
    "Price",
    "Neighborhood",
    "Apartment Type",
    "Meets Criteria",
    "Filter Reason",
    "Author",
    "Posted Date",
    "Link",
    "Score",
    "Comments",
    "Notes"
]


class SheetsManager:
    """Manages Google Sheets operations for apartment listings."""

    def __init__(self, credentials_file: str, sheet_id: str, worksheet_name: str):
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
        self.worksheet_name = worksheet_name
        self.client = None
        self.worksheet = None

    def connect(self) -> bool:
        """Connect to Google Sheets."""
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=SCOPES
            )
            self.client = gspread.authorize(creds)
            spreadsheet = self.client.open_by_key(self.sheet_id)

            try:
                self.worksheet = spreadsheet.worksheet(self.worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                self.worksheet = spreadsheet.add_worksheet(
                    title=self.worksheet_name,
                    rows=1000,
                    cols=len(HEADERS)
                )
                self.worksheet.update('A1', [HEADERS])
                self._format_headers()

            logger.info(f"Connected to Google Sheet: {self.sheet_id}")
            return True

        except FileNotFoundError:
            logger.error(f"Credentials file not found: {self.credentials_file}")
            return False
        except Exception as e:
            logger.error(f"Error connecting to Google Sheets: {e}")
            return False

    def _format_headers(self):
        """Apply formatting to header row."""
        try:
            self.worksheet.format('A1:M1', {
                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.6},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            })
        except Exception as e:
            logger.warning(f"Could not format headers: {e}")

    def ensure_headers(self):
        """Ensure the worksheet has headers."""
        try:
            first_row = self.worksheet.row_values(1)
            if not first_row or first_row != HEADERS:
                self.worksheet.update('A1', [HEADERS])
                self._format_headers()
        except Exception as e:
            logger.warning(f"Could not check/set headers: {e}")

    def get_existing_links(self) -> set:
        """Get all existing post links in the sheet for deduplication."""
        try:
            links = self.worksheet.col_values(10)  # Column J
            return set(links[1:]) if len(links) > 1 else set()
        except Exception as e:
            logger.error(f"Error fetching existing links: {e}")
            return set()

    def _build_row(self, post: Dict, filter_result: Dict) -> list:
        """Build a row from post and filter result."""
        meets_criteria = "Yes" if filter_result.get("passed") else "No"
        reasons = filter_result.get("reasons", [])
        filter_reason = "; ".join(reasons) if reasons else "N/A"

        return [
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            post.get("title", "")[:200],
            f"${filter_result.get('extracted_price')}" if filter_result.get('extracted_price') else "N/A",
            filter_result.get("matched_neighborhood") or "N/A",
            filter_result.get("matched_type") or "N/A",
            meets_criteria,
            filter_reason[:500],
            post.get("author", ""),
            post.get("created_datetime", "")[:10],
            post.get("url", ""),
            str(post.get("score", 0)),
            str(post.get("num_comments", 0)),
            ""
        ]

    def add_listings(self, listings: List[tuple]) -> int:
        """Add multiple listings to the spreadsheet in a single batch."""
        if not listings:
            return 0

        existing_links = self.get_existing_links()

        # Build rows for non-duplicate listings
        rows = []
        for post, filter_result in listings:
            url = post.get("url", "")
            if url in existing_links:
                continue
            rows.append(self._build_row(post, filter_result))
            existing_links.add(url)

        if not rows:
            return 0

        try:
            self.worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info(f"Added {len(rows)} listings to sheet")
            return len(rows)
        except Exception as e:
            logger.error(f"Error adding listings to sheet: {e}")
            return 0
