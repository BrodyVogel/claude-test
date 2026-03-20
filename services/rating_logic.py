"""Rating suggestion logic based on upside/downside to blended price target."""

RATING_TIERS = ["Strong Buy", "Outperform", "Inline", "Underperform", "Sell"]


def compute_suggested_rating(current_price: float, blended_price_target: float) -> str:
    if current_price <= 0:
        return "Inline"
    upside = (blended_price_target - current_price) / current_price
    if upside >= 0.20:
        return "Strong Buy"
    if upside >= 0.10:
        return "Outperform"
    if upside >= -0.10:
        return "Inline"
    if upside >= -0.20:
        return "Underperform"
    return "Sell"


def compute_upside(current_price: float, blended_price_target: float) -> float | None:
    if not current_price or current_price <= 0:
        return None
    return (blended_price_target - current_price) / current_price


def rating_tier_index(rating: str) -> int:
    try:
        return RATING_TIERS.index(rating)
    except ValueError:
        return 2  # default to Inline


def rating_divergence(current_rating: str, suggested_rating: str) -> dict | None:
    """Returns alert info if ratings diverge, or None if they match."""
    if current_rating == suggested_rating:
        return None
    gap = abs(rating_tier_index(current_rating) - rating_tier_index(suggested_rating))
    if gap >= 2:
        return {
            "tier": "red",
            "category": "price_level",
            "title": f"Rating gap: {current_rating} vs suggested {suggested_rating}",
            "description": (
                f"Current rating is '{current_rating}' but price implies "
                f"'{suggested_rating}' (gap of {gap} tiers). Review needed."
            ),
            "suggested_action": f"Consider revising rating to {suggested_rating} or updating price target.",
        }
    return {
        "tier": "amber",
        "category": "price_level",
        "title": f"Rating check: {current_rating} vs suggested {suggested_rating}",
        "description": (
            f"Current rating is '{current_rating}' but price implies "
            f"'{suggested_rating}'. Monitor for further divergence."
        ),
        "suggested_action": "Review price target assumptions at next assessment.",
    }
