"""
AI-powered parser for apartment listings using Claude.
"""

import json
import logging
from typing import Dict, List

from anthropic import Anthropic

logger = logging.getLogger(__name__)


class AIListingParser:
    """Uses Claude to parse apartment listings and extract structured criteria."""

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
        return (
            "You are an expert at parsing NYC apartment rental listings from Reddit. "
            "Extract structured information from listing posts. "
            "Respond with ONLY a valid JSON object. No markdown, no explanation."
        )

    def _build_user_prompt(self, title: str, body: str, flair: str) -> str:
        neighborhoods_str = ", ".join(self.neighborhoods) if self.neighborhoods else "any"
        types_str = ", ".join(self.apartment_types) if self.apartment_types else "any"
        exclude_str = ", ".join(self.exclude_terms) if self.exclude_terms else "none"

        return f"""Analyze this NYC apartment listing.

FLAIR: {flair or "None"}
TITLE: {title}
BODY: {body or "No body text"}

TARGET NEIGHBORHOODS: {neighborhoods_str}
TARGET APARTMENT TYPES: {types_str}
EXCLUSION TERMS: {exclude_str}

Return a JSON object:

{{
  "is_offering": boolean,
  "price": number or null,
  "neighborhood": string or null,
  "neighborhood_matches_target": boolean,
  "apartment_type": string or null,
  "has_exclusion": boolean,
  "exclusion_reason": string or null,
  "matches_criteria": boolean,
  "confidence": "high" | "medium" | "low",
  "summary": string
}}

Rules:
- is_offering: false if post says "looking for", "searching", "need apartment", "seeking"
- neighborhood: ALWAYS extract or deduce the neighborhood, even if not in TARGET list. Use cross streets, landmarks, subway stations, zip codes, or any location context to determine the neighborhood. Use canonical NYC neighborhood names.
- neighborhood_matches_target: true only if the neighborhood matches one in TARGET NEIGHBORHOODS (including abbreviations like LES, FiDi, Wburg)
- has_exclusion: true for sublets, subleases, room shares, roommate situations. Lease assignments/takeovers are NOT exclusions.
- price: monthly rent only (not deposits or broker fees)
- apartment_type: use canonical name from TARGET APARTMENT TYPES if it matches
- matches_criteria: true if is_offering AND neighborhood_matches_target AND no exclusions AND price in range ${self.price_min}-${self.price_max} (or price unknown)
- summary: one concise sentence describing the listing"""

    def parse_listing(self, post: Dict) -> Dict:
        """Parse a single listing using Claude."""
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

            response_text = response.content[0].text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            ai_data = json.loads(response_text)
            result["ai_response"] = ai_data

            result["extracted_price"] = ai_data.get("price")
            result["matched_type"] = ai_data.get("apartment_type")
            result["matched_neighborhood"] = ai_data.get("neighborhood")

            # Determine pass/fail with a single concise reason
            if not ai_data.get("is_offering"):
                result["reasons"].append("Not an offering")
                return result

            if ai_data.get("has_exclusion"):
                result["reasons"].append(f"Excluded: {ai_data.get('exclusion_reason', 'exclusion term')}")
                return result

            price = ai_data.get("price")
            if price is not None:
                if price < self.price_min:
                    result["reasons"].append(f"${price} < ${self.price_min} min")
                    return result
                elif price > self.price_max:
                    result["reasons"].append(f"${price} > ${self.price_max} max")
                    return result

            if not ai_data.get("neighborhood_matches_target"):
                hood = ai_data.get("neighborhood", "unknown")
                result["reasons"].append(f"Not in target area ({hood})")
                return result

            if ai_data.get("matches_criteria"):
                result["passed"] = True
                result["reasons"].append(ai_data.get("summary", "Matches criteria"))
            else:
                result["reasons"].append("Does not match criteria")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            result["reasons"].append("AI parse error")
        except Exception as e:
            logger.error(f"AI parsing failed: {e}")
            result["reasons"].append("AI error")

        return result

    def parse_listings(self, posts: List[Dict]) -> List[tuple]:
        """Parse multiple listings. Returns list of (post, result) tuples."""
        all_results = []
        passed_count = 0

        for post in posts:
            result = self.parse_listing(post)
            all_results.append((post, result))
            if result["passed"]:
                passed_count += 1
                logger.info(
                    f"  + {post.get('title', '')[:50]}... "
                    f"${result.get('extracted_price', '?')} {result.get('matched_neighborhood', '')}"
                )

        logger.info(f"Parsed {len(posts)} -> {passed_count} passed")
        return all_results
