#!/usr/bin/env python3
"""Test the filter logic with sample data."""

from filter import ApartmentFilter

# Sample config
filter_ = ApartmentFilter(
    price_min=1500,
    price_max=2800,
    apartment_types=["studio", "1br", "1 br", "1 bed", "1 bedroom", "one bedroom"],
    neighborhoods=["williamsburg", "east village", "lower east side", "les", "bushwick"],
    exclude_terms=["sublease", "sublet", "roommate", "room for rent", "shared"]
)

# Test posts that should PASS
passing_tests = [
    {
        "title": "[Offering] Beautiful 1BR in East Village - $2400/mo",
        "selftext": "Spacious one bedroom apartment, renovated kitchen, laundry in building.",
        "flair": "Offering",
        "id": "1"
    },
    {
        "title": "[Offering] Studio in Wburg for $2100",
        "selftext": "Cozy studio near Bedford Ave L train. Available Feb 1.",
        "flair": "Offering",
        "id": "2"
    },
    {
        "title": "[Offering] 1 bed LES apartment $2500",
        "selftext": "Lower east side gem, walk to Katz's deli.",
        "flair": "Offering",
        "id": "3"
    },
]

# Test posts that should FAIL
failing_tests = [
    {
        "title": "[Offering] Room for rent in Williamsburg - $1200",
        "selftext": "Looking for a roommate to share 2br apartment.",
        "flair": "Offering",
        "id": "4",
        "expected_reason": "exclude term"
    },
    {
        "title": "[Offering] 1BR Sublet in East Village $2000",
        "selftext": "Sublease available for 3 months.",
        "flair": "Offering",
        "id": "5",
        "expected_reason": "sublet"
    },
    {
        "title": "[Offering] Amazing 1BR in Upper East Side - $2200",
        "selftext": "Beautiful apartment on the UES.",
        "flair": "Offering",
        "id": "6",
        "expected_reason": "wrong neighborhood"
    },
    {
        "title": "[Offering] 1BR in Williamsburg - $4500/mo",
        "selftext": "Luxury apartment with amazing views.",
        "flair": "Offering",
        "id": "7",
        "expected_reason": "too expensive"
    },
    {
        "title": "Looking for 1BR in Williamsburg under $2500",
        "selftext": "I need an apartment ASAP",
        "flair": "Looking",
        "id": "8",
        "expected_reason": "not an offering"
    },
]

print("=" * 60)
print("Testing PASSING listings")
print("=" * 60)

for post in passing_tests:
    result = filter_.filter_listing(post)
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"\n{status}: {post['title'][:50]}...")
    print(f"  Price: ${result['extracted_price']}")
    print(f"  Neighborhood: {result['matched_neighborhood']}")
    print(f"  Type: {result['matched_type']}")
    print(f"  Reasons: {result['reasons']}")

print("\n" + "=" * 60)
print("Testing FAILING listings")
print("=" * 60)

for post in failing_tests:
    result = filter_.filter_listing(post)
    status = "✅ CORRECTLY REJECTED" if not result["passed"] else "❌ INCORRECTLY PASSED"
    print(f"\n{status}: {post['title'][:50]}...")
    print(f"  Expected reason: {post['expected_reason']}")
    print(f"  Actual reasons: {result['reasons']}")

print("\n" + "=" * 60)
print("Price extraction tests")
print("=" * 60)

price_tests = [
    "$2,500/mo",
    "$2500",
    "2500/month",
    "rent: $2100",
    "asking $1800",
    "$2.5k/mo",  # This one might not work
]

for text in price_tests:
    price = filter_.extract_price(text)
    print(f"  '{text}' -> ${price}")

print("\n✅ All tests complete!")
