"""
Fuzzy matching filter for apartment listings.
Handles human-written text with typos, abbreviations, and variations.
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


class ApartmentFilter:
    """
    Filters apartment listings based on configurable criteria.
    Uses fuzzy matching to handle variations in human-written text.
    """

    # Common price patterns in listing titles/text
    PRICE_PATTERNS = [
        r'\$\s*([\d,]+)\s*(?:/\s*(?:mo|month|m))?',  # $2500/mo, $2,500/month
        r'([\d,]+)\s*(?:/\s*(?:mo|month|m))',         # 2500/mo
        r'\$\s*([\d,]+)',                              # $2500
        r'rent[:\s]+\$?\s*([\d,]+)',                   # rent: $2500
        r'asking\s+\$?\s*([\d,]+)',                    # asking $2500
    ]

    def __init__(
        self,
        price_min: int,
        price_max: int,
        apartment_types: List[str],
        neighborhoods: List[str],
        exclude_terms: List[str],
        fuzzy_threshold: int = 80
    ):
        self.price_min = price_min
        self.price_max = price_max
        self.apartment_types = [t.lower() for t in apartment_types]
        self.neighborhoods = [n.lower() for n in neighborhoods]
        self.exclude_terms = [t.lower() for t in exclude_terms]
        self.fuzzy_threshold = fuzzy_threshold

        # Compile price patterns
        self.price_regexes = [re.compile(p, re.IGNORECASE) for p in self.PRICE_PATTERNS]

    def extract_price(self, text: str) -> Optional[int]:
        """
        Extract price from listing text.
        Returns the first valid price found, or None.
        """
        for regex in self.price_regexes:
            matches = regex.findall(text)
            for match in matches:
                try:
                    # Remove commas and convert to int
                    price = int(match.replace(",", ""))
                    # Sanity check: reasonable NYC rent range
                    if 500 <= price <= 15000:
                        return price
                except (ValueError, AttributeError):
                    continue
        return None

    def _fuzzy_match_any(self, text: str, terms: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Check if text fuzzy-matches any of the given terms.
        Returns (matched, matched_term).
        Uses word boundary matching to avoid false positives.
        """
        text_lower = text.lower()

        # Sort terms by length (longest first) to match more specific terms first
        sorted_terms = sorted(terms, key=len, reverse=True)

        # First try exact substring match with word boundaries
        for term in sorted_terms:
            # Use word boundary regex for exact matches
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text_lower):
                return True, term

        # Then try fuzzy matching on individual words (for short abbreviations)
        words = text_lower.split()
        for term in sorted_terms:
            # Skip multi-word terms for word-by-word matching
            if len(term.split()) > 1:
                continue

            for word in words:
                # Clean word of punctuation for better matching
                clean_word = re.sub(r'[^\w\s]', '', word)
                # Only fuzzy match words of similar length to avoid false positives
                if len(clean_word) >= 3 and abs(len(clean_word) - len(term)) <= 2:
                    if fuzz.ratio(clean_word, term) >= self.fuzzy_threshold:
                        return True, term

        return False, None

    def _check_apartment_type(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if listing matches desired apartment types."""
        return self._fuzzy_match_any(text, self.apartment_types)

    def _check_neighborhood(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if listing mentions a desired neighborhood."""
        return self._fuzzy_match_any(text, self.neighborhoods)

    def _check_exclusions(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if listing contains terms that should exclude it."""
        return self._fuzzy_match_any(text, self.exclude_terms)

    def _check_offering_tag(self, flair: str) -> bool:
        """
        Check if the post flair indicates it's an apartment offering.
        NYCapartments uses flairs like "[Offering]" for listings.
        """
        flair_lower = flair.lower() if flair else ""
        return "offering" in flair_lower or "listing" in flair_lower

    def filter_listing(self, post: Dict) -> Dict:
        """
        Filter a single listing against all criteria.

        Returns a dict with:
        - passed: bool - whether the listing passes all filters
        - reasons: list - reasons for passing or failing
        - extracted_price: int or None - detected price
        - matched_type: str or None - matched apartment type
        - matched_neighborhood: str or None - matched neighborhood
        """
        title = post.get("title", "")
        body = post.get("selftext", "")
        flair = post.get("flair", "")
        full_text = f"{title} {body}"

        result = {
            "passed": False,
            "reasons": [],
            "extracted_price": None,
            "matched_type": None,
            "matched_neighborhood": None,
        }

        # Check if it's an offering (not a request)
        if not self._check_offering_tag(flair):
            # Also check title for offering indicators
            if any(x in title.lower() for x in ["looking for", "searching for", "need", "seeking", "wanted"]):
                result["reasons"].append("Not an offering (appears to be a request)")
                return result

        # Check for exclusion terms (sublets, roommates, etc.)
        excluded, exclude_term = self._check_exclusions(full_text)
        if excluded:
            result["reasons"].append(f"Excluded term found: '{exclude_term}'")
            return result

        # Extract and check price
        price = self.extract_price(full_text)
        result["extracted_price"] = price

        if price is None:
            result["reasons"].append("No price detected")
            # Don't fail on missing price - might be in comments or negotiable
        elif price < self.price_min:
            result["reasons"].append(f"Price ${price} below minimum ${self.price_min}")
            return result
        elif price > self.price_max:
            result["reasons"].append(f"Price ${price} above maximum ${self.price_max}")
            return result
        else:
            result["reasons"].append(f"Price ${price} within range")

        # Check apartment type
        type_match, matched_type = self._check_apartment_type(full_text)
        if type_match:
            result["matched_type"] = matched_type
            result["reasons"].append(f"Matched apartment type: '{matched_type}'")
        else:
            result["reasons"].append("No matching apartment type found")
            # Don't fail - might be implied or in title differently

        # Check neighborhood
        hood_match, matched_hood = self._check_neighborhood(full_text)
        if hood_match:
            result["matched_neighborhood"] = matched_hood
            result["reasons"].append(f"Matched neighborhood: '{matched_hood}'")
        else:
            result["reasons"].append("No matching neighborhood found")
            return result  # Neighborhood is required

        # If we got here, listing passes
        result["passed"] = True
        return result

    def filter_listings(self, posts: List[Dict]) -> List[Tuple[Dict, Dict]]:
        """
        Filter multiple listings.

        Returns list of (post, filter_result) tuples for ALL posts.
        Each result includes 'passed' boolean so caller can filter if needed.
        """
        all_results = []
        passed_count = 0
        for post in posts:
            result = self.filter_listing(post)
            all_results.append((post, result))
            if result["passed"]:
                passed_count += 1
                logger.info(f"Post passed: {post.get('title', '')[:50]}...")
            else:
                logger.info(f"Post filtered: {post.get('title', '')[:50]}... - {result['reasons'][0] if result['reasons'] else 'unknown'}")

        logger.info(f"Filtered {len(posts)} posts -> {passed_count} meet criteria")
        return all_results
