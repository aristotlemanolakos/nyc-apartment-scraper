"""
AI-powered parser for apartment listings using Claude.
Replaces regex and fuzzy matching with natural language understanding.
"""

import json
import logging
from typing import Dict, List, Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)


class AIListingParser:
    """
    Uses Claude to parse apartment listings and extract structured criteria.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        neighborhoods: List[str] = None,
        apartment_types: List[str] = None,
        exclude_terms: List[str] = None,
        price_min: int = 0,
        price_max: int = 99999,
    ):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.neighborhoods = neighborhoods or []
        self.apartment_types = apartment_types or []
        self.exclude_terms = exclude_terms or []
        self.price_min = price_min
        self.price_max = price_max

    def _build_system_prompt(self) -> str:
        """Build the system prompt with configured criteria."""
        return """You are an expert at parsing NYC apartment rental listings from Reddit.
Your job is to extract structured information from listing posts.

You must respond with ONLY a valid JSON object (no markdown, no explanation).
"""

    def _build_user_prompt(self, title: str, body: str, flair: str) -> str:
        """Build the user prompt with the listing and criteria."""
        neighborhoods_str = ", ".join(self.neighborhoods) if self.neighborhoods else "any"
        types_str = ", ".join(self.apartment_types) if self.apartment_types else "any"
        exclude_str = ", ".join(self.exclude_terms) if self.exclude_terms else "none"

        return f"""Analyze this NYC apartment listing and extract information.

POST FLAIR: {flair or "None"}
POST TITLE: {title}
POST BODY: {body or "No body text"}

TARGET NEIGHBORHOODS (what we're looking for): {neighborhoods_str}
TARGET APARTMENT TYPES (what we're looking for): {types_str}
EXCLUSION TERMS (things we want to avoid): {exclude_str}

Extract and return a JSON object with these fields:

{{
  "is_offering": boolean,  // true if this is someone offering/listing an apartment, false if someone is LOOKING for an apartment
  "price": number or null,  // monthly rent in USD, null if not mentioned
  "neighborhood": string or null,  // the neighborhood mentioned, null if none found. Use the canonical name from TARGET NEIGHBORHOODS if it matches
  "apartment_type": string or null,  // e.g. "studio", "1br", "2br", null if not clear. Use canonical name from TARGET APARTMENT TYPES if it matches
  "has_exclusion": boolean,  // true if any exclusion terms apply (sublet, roommate situation, room share, etc.)
  "exclusion_reason": string or null,  // which exclusion term matched, if any
  "matches_criteria": boolean,  // true if: is_offering=true AND neighborhood matches one of TARGET NEIGHBORHOODS AND no exclusions
  "confidence": "high" | "medium" | "low",  // your confidence in the extraction
  "summary": string  // brief 1-sentence summary of the listing
}}

Important rules:
- is_offering should be false if the post contains phrases like "looking for", "searching", "need apartment", "seeking"
- For neighborhoods, match against TARGET NEIGHBORHOODS (including common abbreviations like LES=Lower East Side, FiDi=Financial District, Wburg=Williamsburg)
- has_exclusion should be true for sublets, subleases, room shares, roommate situations, shared apartments
- price should be the monthly rent amount only (not deposits, broker fees, etc.)
- matches_criteria is the key decision: does this listing match what we want?

Respond with ONLY the JSON object."""

    def parse_listing(self, post: Dict) -> Dict:
        """
        Parse a single listing using Claude.

        Returns a dict with:
        - passed: bool - whether the listing matches criteria
        - reasons: list - explanations
        - extracted_price: int or None
        - matched_type: str or None
        - matched_neighborhood: str or None
        - ai_response: dict - full AI response
        """
        title = post.get("title", "")
        body = post.get("selftext", "")
        flair = post.get("flair", "")

        result = {
            "passed": False,
            "reasons": [],
            "extracted_price": None,
            "matched_type": None,
            "matched_neighborhood": None,
            "ai_response": None,
        }

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self._build_system_prompt(),
                messages=[
                    {"role": "user", "content": self._build_user_prompt(title, body, flair)}
                ],
            )

            # Extract the response text
            response_text = response.content[0].text.strip()

            # Parse JSON response
            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            ai_data = json.loads(response_text)
            result["ai_response"] = ai_data

            # Extract fields from AI response
            result["extracted_price"] = ai_data.get("price")
            result["matched_type"] = ai_data.get("apartment_type")
            result["matched_neighborhood"] = ai_data.get("neighborhood")

            # Build reasons list
            if not ai_data.get("is_offering"):
                result["reasons"].append("Not an offering (appears to be a request)")
                return result

            if ai_data.get("has_exclusion"):
                exclusion = ai_data.get("exclusion_reason", "exclusion term found")
                result["reasons"].append(f"Excluded: {exclusion}")
                return result

            price = ai_data.get("price")
            if price is not None:
                if price < self.price_min:
                    result["reasons"].append(f"Price ${price} below minimum ${self.price_min}")
                    return result
                elif price > self.price_max:
                    result["reasons"].append(f"Price ${price} above maximum ${self.price_max}")
                    return result
                else:
                    result["reasons"].append(f"Price ${price} within range")
            else:
                result["reasons"].append("No price detected")

            if ai_data.get("apartment_type"):
                result["reasons"].append(f"Apartment type: {ai_data['apartment_type']}")
            else:
                result["reasons"].append("No apartment type detected")

            if ai_data.get("neighborhood"):
                result["reasons"].append(f"Neighborhood: {ai_data['neighborhood']}")
            else:
                result["reasons"].append("No matching neighborhood found")
                return result  # Neighborhood is required

            # Check if AI determined it matches criteria
            if ai_data.get("matches_criteria"):
                result["passed"] = True
                result["reasons"].append(f"AI summary: {ai_data.get('summary', 'N/A')}")
            else:
                result["reasons"].append("AI determined listing does not match criteria")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            result["reasons"].append(f"AI parsing error: {e}")
        except Exception as e:
            logger.error(f"AI parsing failed: {e}")
            result["reasons"].append(f"AI error: {e}")

        return result

    def parse_listings(self, posts: List[Dict]) -> List[tuple]:
        """
        Parse multiple listings.

        Returns list of (post, parse_result) tuples for ALL posts.
        Each result includes 'passed' boolean so caller can filter if needed.
        """
        all_results = []
        passed_count = 0
        for post in posts:
            result = self.parse_listing(post)
            all_results.append((post, result))
            if result["passed"]:
                passed_count += 1
                logger.info(f"Post passed (AI): {post.get('title', '')[:50]}...")
            else:
                logger.info(f"Post filtered (AI): {post.get('title', '')[:50]}... - {result['reasons'][0] if result['reasons'] else 'unknown'}")

        logger.info(f"AI parsed {len(posts)} posts -> {passed_count} meet criteria")
        return all_results
