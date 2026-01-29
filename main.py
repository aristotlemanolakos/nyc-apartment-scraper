#!/usr/bin/env python3
"""
NYC Apartment Scraper

Scrapes apartment listing subreddits, uses AI to parse and filter them,
and adds matching listings to a Google Sheet.

Usage:
    python main.py              # Run once
    python main.py --daemon     # Run continuously every N minutes
    python main.py --test       # Test mode (no sheets update)
"""

import argparse
import logging
import os
import sys
import time

import yaml

from ai_parser import AIListingParser
from scraper import RedditScraper
from sheets import SheetsManager
from storage import SeenPostsStorage


def setup_logging(log_file: str = None, verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"Error parsing config file: {e}")
        sys.exit(1)


def get_subreddits(config: dict) -> list:
    """Get subreddit list from config. Supports both old and new format."""
    scraping = config["scraping"]
    value = scraping.get("subreddits", scraping.get("subreddit", []))
    if isinstance(value, str):
        return [value]
    # Flatten in case of nested lists
    result = []
    for item in value:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


def run_scrape_cycle(
    scraper: RedditScraper,
    parser: AIListingParser,
    sheets: SheetsManager,
    storage: SeenPostsStorage,
    test_mode: bool = False,
) -> dict:
    """Run a single scrape cycle. Returns stats dict."""
    logger = logging.getLogger(__name__)
    stats = {"fetched": 0, "new": 0, "passed": 0, "added": 0}

    posts = scraper.fetch_new_posts(limit=50)
    stats["fetched"] = len(posts)
    if not posts:
        return stats

    new_posts = storage.filter_unseen(posts)
    stats["new"] = len(new_posts)
    if not new_posts:
        return stats

    results = parser.parse_listings(new_posts)
    stats["passed"] = sum(1 for _, r in results if r.get("passed"))

    if results and not test_mode and sheets.worksheet:
        stats["added"] = sheets.add_listings(results)

    storage.mark_many_seen([p["id"] for p in new_posts])
    return stats


def main():
    parser = argparse.ArgumentParser(description="NYC Apartment Scraper")
    parser.add_argument("--config", "-c", default="config.yaml", help="Path to config file")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run continuously")
    parser.add_argument("--test", "-t", action="store_true", help="Test mode (no sheets update)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    config = load_config(args.config)

    log_file = config.get("storage", {}).get("log_file")
    setup_logging(log_file, args.verbose)
    logger = logging.getLogger(__name__)

    # Initialize components
    subreddits = get_subreddits(config)
    scraper = RedditScraper(subreddits=subreddits, user_agent=config["scraping"]["user_agent"])

    ai_config = config.get("ai", {})
    api_key = ai_config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("No API key found. Set 'ai.api_key' in config.yaml or ANTHROPIC_API_KEY env var.")
        sys.exit(1)

    ai_parser = AIListingParser(
        api_key=api_key,
        model=ai_config.get("model", "claude-sonnet-4-20250514"),
        neighborhoods=config["neighborhoods"],
        apartment_types=config["apartment_types"],
        exclude_terms=config["exclude_terms"],
        price_min=config["price"]["min"],
        price_max=config["price"]["max"],
    )

    storage = SeenPostsStorage(storage_file=config["storage"]["seen_posts_file"])

    sheets = SheetsManager(
        credentials_file=config["google_sheets"]["credentials_file"],
        sheet_id=config["google_sheets"]["sheet_id"],
        worksheet_name=config["google_sheets"]["worksheet_name"]
    )
    if not args.test:
        if not sheets.connect():
            logger.error("Failed to connect to Google Sheets. Use --test to skip.")
            sys.exit(1)
        sheets.ensure_headers()
    else:
        logger.info("TEST MODE")

    logger.info(f"Subreddits: {', '.join(subreddits)}")
    logger.info(f"Price: ${config['price']['min']}-${config['price']['max']} | "
                f"{len(config['neighborhoods'])} neighborhoods | "
                f"{storage.get_count()} seen")

    interval = config["scraping"]["interval_minutes"] * 60

    def log_stats(stats):
        logger.info(
            f"Done: {stats['fetched']} fetched, {stats['new']} new, "
            f"{stats['passed']} passed, {stats['added']} added"
        )

    if args.daemon:
        logger.info(f"Daemon mode (every {config['scraping']['interval_minutes']} min)")
        try:
            while True:
                log_stats(run_scrape_cycle(scraper, ai_parser, sheets, storage, args.test))
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
    else:
        log_stats(run_scrape_cycle(scraper, ai_parser, sheets, storage, args.test))


if __name__ == "__main__":
    main()
