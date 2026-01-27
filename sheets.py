"""
Google Sheets integration for storing apartment listings.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# Scopes required for Google Sheets API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Column headers for the spreadsheet
HEADERS = [
    "Date Added",
    "Title",
    "Price",
    "Neighborhood",
    "Apartment Type",
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
        """
        Initialize the Sheets manager.

        Args:
            credentials_file: Path to Google service account JSON
            sheet_id: The Google Sheet ID
            worksheet_name: Name of the worksheet tab to use
        """
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
        self.worksheet_name = worksheet_name
        self.client = None
        self.worksheet = None

    def connect(self) -> bool:
        """
        Connect to Google Sheets.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=SCOPES
            )
            self.client = gspread.authorize(creds)

            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(self.sheet_id)

            # Try to get the worksheet, create if it doesn't exist
            try:
                self.worksheet = spreadsheet.worksheet(self.worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                self.worksheet = spreadsheet.add_worksheet(
                    title=self.worksheet_name,
                    rows=1000,
                    cols=len(HEADERS)
                )
                # Add headers to new worksheet
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
            self.worksheet.format('A1:K1', {
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
        """
        Get all existing post links in the sheet.
        Used for deduplication.

        Returns:
            Set of post URLs already in the sheet
        """
        try:
            # Link is in column H (8th column)
            links = self.worksheet.col_values(8)
            # Skip header
            return set(links[1:]) if len(links) > 1 else set()
        except Exception as e:
            logger.error(f"Error fetching existing links: {e}")
            return set()

    def add_listing(self, post: Dict, filter_result: Dict) -> bool:
        """
        Add a single listing to the spreadsheet.

        Args:
            post: The Reddit post data
            filter_result: The filter result with extracted info

        Returns:
            True if added successfully
        """
        try:
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                post.get("title", "")[:200],  # Truncate long titles
                f"${filter_result.get('extracted_price', 'N/A')}" if filter_result.get('extracted_price') else "N/A",
                filter_result.get("matched_neighborhood", "N/A"),
                filter_result.get("matched_type", "N/A"),
                post.get("author", ""),
                post.get("created_datetime", "")[:10],  # Just date
                post.get("url", ""),
                str(post.get("score", 0)),
                str(post.get("num_comments", 0)),
                ""  # Notes column for user
            ]

            self.worksheet.append_row(row, value_input_option="USER_ENTERED")
            logger.info(f"Added listing: {post.get('title', '')[:50]}...")
            return True

        except Exception as e:
            logger.error(f"Error adding listing to sheet: {e}")
            return False

    def add_listings(self, listings: List[tuple]) -> int:
        """
        Add multiple listings to the spreadsheet.
        Checks for duplicates before adding.

        Args:
            listings: List of (post, filter_result) tuples

        Returns:
            Number of listings successfully added
        """
        if not listings:
            return 0

        # Get existing links for deduplication
        existing_links = self.get_existing_links()

        added = 0
        for post, filter_result in listings:
            url = post.get("url", "")
            if url in existing_links:
                logger.debug(f"Skipping duplicate: {url}")
                continue

            if self.add_listing(post, filter_result):
                added += 1
                existing_links.add(url)  # Track newly added

        return added
