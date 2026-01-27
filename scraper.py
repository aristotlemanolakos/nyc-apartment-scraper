"""
Reddit scraper module for fetching new apartment listings.
"""

import requests
import time
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RedditScraper:
    """Scrapes new posts from a subreddit's JSON endpoint."""

    BASE_URL = "https://www.reddit.com/r/{subreddit}/new.json"

    def __init__(self, subreddit: str, user_agent: str):
        self.subreddit = subreddit
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent
        })
        self.last_request_time = 0
        self.min_request_interval = 2  # Reddit rate limit: be nice

    def _rate_limit(self):
        """Ensure we don't hit Reddit too frequently."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def fetch_new_posts(self, limit: int = 25) -> List[Dict]:
        """
        Fetch the newest posts from the subreddit.

        Args:
            limit: Number of posts to fetch (max 100)

        Returns:
            List of post data dictionaries
        """
        self._rate_limit()

        url = self.BASE_URL.format(subreddit=self.subreddit)
        params = {"limit": min(limit, 100)}

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            posts = []

            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                posts.append(self._extract_post_info(post_data))

            logger.info(f"Fetched {len(posts)} posts from r/{self.subreddit}")
            return posts

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching posts: {e}")
            return []
        except ValueError as e:
            logger.error(f"Error parsing JSON response: {e}")
            return []

    def _extract_post_info(self, post_data: Dict) -> Dict:
        """Extract relevant information from a Reddit post."""
        created_utc = post_data.get("created_utc", 0)
        created_dt = datetime.utcfromtimestamp(created_utc) if created_utc else None

        return {
            "id": post_data.get("id", ""),
            "title": post_data.get("title", ""),
            "selftext": post_data.get("selftext", ""),
            "author": post_data.get("author", "[deleted]"),
            "created_utc": created_utc,
            "created_datetime": created_dt.isoformat() if created_dt else "",
            "url": f"https://www.reddit.com{post_data.get('permalink', '')}",
            "score": post_data.get("score", 0),
            "num_comments": post_data.get("num_comments", 0),
            "flair": post_data.get("link_flair_text", ""),
            "is_self": post_data.get("is_self", True),
        }
