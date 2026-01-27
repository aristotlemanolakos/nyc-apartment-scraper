"""
Local storage for tracking seen posts (deduplication).
"""

import json
import logging
from pathlib import Path
from typing import Set
from datetime import datetime

logger = logging.getLogger(__name__)


class SeenPostsStorage:
    """
    Tracks which Reddit posts have been seen to avoid duplicate processing.
    Stores post IDs in a JSON file.
    """

    def __init__(self, storage_file: str):
        """
        Initialize storage.

        Args:
            storage_file: Path to JSON file for storing seen post IDs
        """
        self.storage_file = Path(storage_file)
        self.seen_posts: Set[str] = set()
        self._load()

    def _load(self):
        """Load seen posts from file."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    self.seen_posts = set(data.get("seen_ids", []))
                    logger.info(f"Loaded {len(self.seen_posts)} seen post IDs")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading seen posts: {e}")
                self.seen_posts = set()
        else:
            logger.info("No existing seen posts file, starting fresh")

    def _save(self):
        """Save seen posts to file."""
        try:
            # Keep only last 10000 posts to prevent unlimited growth
            seen_list = list(self.seen_posts)
            if len(seen_list) > 10000:
                seen_list = seen_list[-10000:]
                self.seen_posts = set(seen_list)

            data = {
                "seen_ids": seen_list,
                "last_updated": datetime.now().isoformat(),
                "count": len(seen_list)
            }

            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)

        except IOError as e:
            logger.error(f"Error saving seen posts: {e}")

    def is_seen(self, post_id: str) -> bool:
        """Check if a post has been seen."""
        return post_id in self.seen_posts

    def mark_seen(self, post_id: str):
        """Mark a post as seen."""
        self.seen_posts.add(post_id)

    def mark_many_seen(self, post_ids: list):
        """Mark multiple posts as seen and save."""
        for post_id in post_ids:
            self.seen_posts.add(post_id)
        self._save()

    def filter_unseen(self, posts: list) -> list:
        """
        Filter a list of posts to only those not yet seen.

        Args:
            posts: List of post dicts with 'id' field

        Returns:
            List of posts that haven't been seen
        """
        unseen = [p for p in posts if not self.is_seen(p.get("id", ""))]
        logger.info(f"Filtered {len(posts)} posts -> {len(unseen)} unseen")
        return unseen

    def get_count(self) -> int:
        """Get number of seen posts."""
        return len(self.seen_posts)
