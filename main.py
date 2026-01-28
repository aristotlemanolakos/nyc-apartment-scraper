#!/usr/bin/env python3
"""
NYC Apartment Scraper - Main Entry Point

Scrapes r/NYCapartments for new listings, filters them based on your criteria,
and adds matching listings to a Google Sheet.

Usage:
    python main.py              # Run once
    python main.py --daemon     # Run continuously every 5 minutes
    python main.py --test       # Test mode (no sheets update)
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import yaml

from scraper import RedditScraper
from filter import ApartmentFilter
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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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


def run_scrape_cycle(
    scraper: RedditScraper,
    filter_,  # Can be ApartmentFilter or AIListingParser
    sheets: SheetsManager,
    storage: SeenPostsStorage,
    test_mode: bool = False,
    use_ai: bool = False
) -> dict:
    """
    Run a single scrape cycle.

    Returns:
        Dict with stats about the cycle
    """
    logger = logging.getLogger(__name__)
    stats = {
        "fetched": 0,
        "new": 0,
        "passed_filter": 0,
        "added_to_sheet": 0
    }

    # Fetch new posts
    posts = scraper.fetch_new_posts(limit=50)
    stats["fetched"] = len(posts)

    if not posts:
        logger.warning("No posts fetched")
        return stats

    # Filter to unseen posts
    new_posts = storage.filter_unseen(posts)
    stats["new"] = len(new_posts)

    if not new_posts:
        logger.info("No new posts to process")
        return stats

    # Apply apartment filters (AI or regex-based)
    if use_ai:
        all_results = filter_.parse_listings(new_posts)
    else:
        all_results = filter_.filter_listings(new_posts)

    # Count how many meet criteria
    passed_count = sum(1 for _, result in all_results if result.get("passed"))
    stats["passed_filter"] = passed_count

    if all_results:
        logger.info(f"Processed {len(all_results)} listings ({passed_count} meet criteria):")
        for post, result in all_results:
            status = "✓" if result.get("passed") else "✗"
            logger.info(f"  {status} {post['title'][:55]}...")
            if result.get("passed"):
                logger.info(f"    Price: ${result.get('extracted_price', 'N/A')}, "
                           f"Neighborhood: {result.get('matched_neighborhood', 'N/A')}")

    # Add ALL listings to Google Sheets (if not test mode)
    # Each listing has "Meets Criteria" column so user can filter in sheet
    if all_results and not test_mode:
        if sheets.worksheet:
            added = sheets.add_listings(all_results)
            stats["added_to_sheet"] = added
        else:
            logger.warning("Sheets not connected, skipping upload")

    # Mark all fetched posts as seen (not just passed ones)
    # This prevents re-processing rejected posts
    storage.mark_many_seen([p["id"] for p in new_posts])

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="NYC Apartment Scraper - Find your perfect apartment!"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run continuously as a daemon"
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Test mode - don't update Google Sheets"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Setup logging
    log_file = config.get("storage", {}).get("log_file")
    setup_logging(log_file, args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("NYC Apartment Scraper Starting")
    logger.info("=" * 60)

    # Initialize components
    scraper = RedditScraper(
        subreddit=config["scraping"]["subreddit"],
        user_agent=config["scraping"]["user_agent"]
    )

    # Check if AI parsing is enabled
    ai_config = config.get("ai", {})
    use_ai = ai_config.get("enabled", False)

    if use_ai:
        from ai_parser import AIListingParser

        # Get API key from config or environment
        api_key = ai_config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("AI parsing enabled but no API key found.")
            logger.error("Set 'ai.api_key' in config.yaml or ANTHROPIC_API_KEY environment variable.")
            sys.exit(1)

        filter_ = AIListingParser(
            api_key=api_key,
            model=ai_config.get("model", "claude-sonnet-4-20250514"),
            neighborhoods=config["neighborhoods"],
            apartment_types=config["apartment_types"],
            exclude_terms=config["exclude_terms"],
            price_min=config["price"]["min"],
            price_max=config["price"]["max"],
        )
        logger.info(f"Using AI parser (model: {ai_config.get('model', 'claude-sonnet-4-20250514')})")
    else:
        filter_ = ApartmentFilter(
            price_min=config["price"]["min"],
            price_max=config["price"]["max"],
            apartment_types=config["apartment_types"],
            neighborhoods=config["neighborhoods"],
            exclude_terms=config["exclude_terms"]
        )
        logger.info("Using regex/fuzzy matching filter")

    storage = SeenPostsStorage(
        storage_file=config["storage"]["seen_posts_file"]
    )

    # Initialize Google Sheets (unless test mode)
    sheets = SheetsManager(
        credentials_file=config["google_sheets"]["credentials_file"],
        sheet_id=config["google_sheets"]["sheet_id"],
        worksheet_name=config["google_sheets"]["worksheet_name"]
    )

    if not args.test:
        if not sheets.connect():
            logger.error("Failed to connect to Google Sheets")
            logger.error("Run with --test to test without Sheets, or check your credentials")
            sys.exit(1)
        sheets.ensure_headers()
    else:
        logger.info("TEST MODE - Google Sheets updates disabled")

    # Print config summary
    logger.info(f"Price range: ${config['price']['min']} - ${config['price']['max']}")
    logger.info(f"Neighborhoods: {len(config['neighborhoods'])} configured")
    logger.info(f"Apartment types: {config['apartment_types']}")
    logger.info(f"Exclude terms: {len(config['exclude_terms'])} configured")
    logger.info(f"Seen posts tracked: {storage.get_count()}")

    interval = config["scraping"]["interval_minutes"] * 60

    if args.daemon:
        logger.info(f"Running in daemon mode (every {config['scraping']['interval_minutes']} minutes)")
        logger.info("Press Ctrl+C to stop")

        try:
            while True:
                logger.info("-" * 40)
                stats = run_scrape_cycle(scraper, filter_, sheets, storage, args.test, use_ai)
                logger.info(
                    f"Cycle complete: {stats['fetched']} fetched, "
                    f"{stats['new']} new, {stats['passed_filter']} passed, "
                    f"{stats['added_to_sheet']} added"
                )
                logger.info(f"Sleeping for {config['scraping']['interval_minutes']} minutes...")
                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("\nShutting down gracefully...")
            sys.exit(0)

    else:
        # Run once
        stats = run_scrape_cycle(scraper, filter_, sheets, storage, args.test, use_ai)
        logger.info(
            f"Done: {stats['fetched']} fetched, "
            f"{stats['new']} new, {stats['passed_filter']} passed, "
            f"{stats['added_to_sheet']} added"
        )


if __name__ == "__main__":
    main()
