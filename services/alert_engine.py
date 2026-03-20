"""Alert generation engine. Phase 1 skeleton — generates rating divergence alerts."""

import aiosqlite
from services.rating_logic import compute_suggested_rating, rating_divergence


async def check_rating_alerts(db: aiosqlite.Connection, company_id: int):
    """Check if the suggested rating diverges from current rating and create/update alerts."""
    row = await db.execute_fetchall(
        "SELECT id, current_rating, current_price, blended_price_target FROM companies WHERE id = ?",
        (company_id,),
    )
    if not row:
        return
    company = row[0]
    current_rating = company[1]
    current_price = company[2]
    blended_target = company[3]

    if not current_price or current_price <= 0:
        return

    suggested = compute_suggested_rating(current_price, blended_target)
    divergence = rating_divergence(current_rating, suggested)

    # Deactivate old rating alerts for this company
    await db.execute(
        "UPDATE alerts SET is_active = 0 WHERE company_id = ? AND category = 'price_level' AND is_active = 1",
        (company_id,),
    )

    if divergence:
        await db.execute(
            """INSERT INTO alerts (company_id, tier, category, title, description, suggested_action)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                company_id,
                divergence["tier"],
                divergence["category"],
                divergence["title"],
                divergence["description"],
                divergence["suggested_action"],
            ),
        )
    await db.commit()
