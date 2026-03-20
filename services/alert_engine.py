"""Alert generation engine — evaluates all alert conditions after check runs."""

import logging
from datetime import datetime, timedelta

import aiosqlite

from services.rating_logic import compute_suggested_rating, compute_upside, rating_divergence

logger = logging.getLogger(__name__)


async def run_full_alert_check(db: aiosqlite.Connection):
    """Run all alert checks across all companies."""
    rows = await db.execute_fetchall("SELECT * FROM companies")
    for company in rows:
        company = dict(company)
        await check_rating_alerts(db, company['id'])
        await check_indicator_alerts(db, company['id'])
        await check_staleness_alerts(db, company)
        await check_upside_shift_alerts(db, company)


async def check_rating_alerts(db: aiosqlite.Connection, company_id: int):
    """Check if the suggested rating diverges from current rating and create/update alerts."""
    row = await db.execute_fetchall(
        "SELECT id, current_rating, current_price, blended_price_target FROM companies WHERE id = ?",
        (company_id,),
    )
    if not row:
        return
    company = dict(row[0])
    current_rating = company['current_rating']
    current_price = company['current_price']
    blended_target = company['blended_price_target']

    if not current_price or current_price <= 0:
        return

    suggested = compute_suggested_rating(current_price, blended_target)
    divergence = rating_divergence(current_rating, suggested)

    # Deactivate old rating alerts
    await db.execute(
        "UPDATE alerts SET is_active = 0 WHERE company_id = ? AND category = 'price_level' AND is_active = 1",
        (company_id,),
    )

    if divergence:
        await _upsert_alert(db, company_id, None, divergence['tier'], 'price_level',
                            divergence['title'], divergence['description'],
                            suggested_action=divergence.get('suggested_action'))
    await db.commit()


async def check_indicator_alerts(db: aiosqlite.Connection, company_id: int):
    """Generate alerts for indicator threshold breaches and correlated movements."""
    indicators = await db.execute_fetchall(
        "SELECT * FROM indicators WHERE company_id = ?", (company_id,)
    )

    direction_changes = []  # track which direction indicators moved

    for ind in indicators:
        ind = dict(ind)
        indicator_id = ind['id']
        status = ind.get('status', 'green')

        if status == 'red':
            # Threshold breach alert
            await _upsert_alert(
                db, company_id, indicator_id, 'red', 'threshold_breach',
                f"{ind['name']} — threshold breached",
                f"{ind['name']} current value ({ind.get('current_value', '?')}) has crossed a threshold. "
                f"Bear: {ind.get('bear_threshold', 'N/A')}, Bull: {ind.get('bull_threshold', 'N/A')}.",
                affected_scenario=_guess_affected_scenario(ind),
                suggested_action=f"Review {ind['name']} and assess impact on scenario weights.",
            )

        elif status == 'amber':
            await _upsert_alert(
                db, company_id, indicator_id, 'amber', 'trending_toward',
                f"{ind['name']} — trending toward threshold",
                f"{ind['name']} ({ind.get('current_value', '?')}) is trending toward a threshold at current velocity.",
                affected_scenario=_guess_affected_scenario(ind),
                suggested_action=f"Monitor {ind['name']} closely at next check.",
            )

        elif status == 'green':
            # Deactivate old threshold alerts for this indicator
            await db.execute(
                """UPDATE alerts SET is_active = 0
                   WHERE indicator_id = ? AND category IN ('threshold_breach', 'trending_toward') AND is_active = 1""",
                (indicator_id,),
            )

        # Track directional movement for correlation check
        readings = await db.execute_fetchall(
            """SELECT value_numeric, checked_at FROM indicator_readings
               WHERE indicator_id = ? AND value_numeric IS NOT NULL
               ORDER BY checked_at DESC LIMIT 2""",
            (indicator_id,),
        )
        if len(readings) >= 2:
            latest = readings[0]['value_numeric']
            previous = readings[1]['value_numeric']
            if latest is not None and previous is not None and previous != 0:
                change = (latest - previous) / abs(previous)
                if abs(change) > 0.01:  # >1% change
                    direction_changes.append({
                        'name': ind['name'],
                        'direction': 'up' if change > 0 else 'down',
                        'change_pct': change * 100,
                    })

    # Correlated movement check
    if len(direction_changes) >= 3:
        up_count = sum(1 for d in direction_changes if d['direction'] == 'up')
        down_count = sum(1 for d in direction_changes if d['direction'] == 'down')

        if down_count >= 3:
            names = ', '.join(d['name'] for d in direction_changes if d['direction'] == 'down')
            await _upsert_alert(
                db, company_id, None, 'amber', 'correlation',
                f"{down_count} indicators moved down together",
                f"Multiple indicators declined since last check: {names}. Consider reviewing thesis.",
                suggested_action="Review whether correlated declines signal a scenario shift.",
            )
        elif up_count >= 3:
            names = ', '.join(d['name'] for d in direction_changes if d['direction'] == 'up')
            await _upsert_alert(
                db, company_id, None, 'amber', 'correlation',
                f"{up_count} indicators moved up together",
                f"Multiple indicators improved since last check: {names}.",
                suggested_action="Consider whether correlated gains warrant an upgrade review.",
            )

    await db.commit()


async def check_staleness_alerts(db: aiosqlite.Connection, company: dict):
    """Generate alerts for stale scenario docs or missing assessments."""
    company_id = company['id']
    now = datetime.utcnow()

    # Scenario doc staleness (>90 days)
    doc_uploaded = company.get('scenario_doc_uploaded_at')
    last_assessment = company.get('last_full_assessment_at')

    if doc_uploaded:
        try:
            uploaded_dt = datetime.fromisoformat(doc_uploaded)
            if now - uploaded_dt > timedelta(days=90):
                # Check if there's been a recent assessment
                assessment_stale = True
                if last_assessment:
                    try:
                        assess_dt = datetime.fromisoformat(last_assessment)
                        if now - assess_dt <= timedelta(days=45):
                            assessment_stale = False
                    except (ValueError, TypeError):
                        pass

                if assessment_stale:
                    await _upsert_alert(
                        db, company_id, None, 'red', 'staleness',
                        f"Scenario document is stale ({company['name']})",
                        f"Scenario doc was uploaded {(now - uploaded_dt).days} days ago and no "
                        f"assessment has been run in the last 45 days.",
                        suggested_action="Run a monthly mini-assessment or update the scenario document.",
                    )
        except (ValueError, TypeError):
            pass

    await db.commit()


async def check_upside_shift_alerts(db: aiosqlite.Connection, company: dict):
    """Alert if upside/downside has shifted >10pp due to price movement."""
    company_id = company['id']
    current_price = company.get('current_price')
    target = company.get('blended_price_target')
    if not current_price or not target or current_price <= 0:
        return

    # Get previous price (second most recent)
    rows = await db.execute_fetchall(
        """SELECT price FROM price_history
           WHERE company_id = ?
           ORDER BY recorded_at DESC LIMIT 2""",
        (company_id,),
    )
    if len(rows) < 2:
        return

    prev_price = rows[1]['price']
    if not prev_price or prev_price <= 0:
        return

    current_upside = compute_upside(current_price, target)
    prev_upside = compute_upside(prev_price, target)

    if current_upside is not None and prev_upside is not None:
        shift = abs(current_upside - prev_upside)
        if shift >= 0.10:  # 10 percentage points
            await _upsert_alert(
                db, company_id, None, 'amber', 'price_level',
                f"Upside shifted {shift*100:.1f}pp for {company['name']}",
                f"Upside moved from {prev_upside*100:.1f}% to {current_upside*100:.1f}% "
                f"(price: {prev_price} → {current_price}). Review price target.",
                suggested_action="Verify price target assumptions still hold.",
            )

    await db.commit()


def _guess_affected_scenario(indicator: dict) -> str | None:
    """Guess which scenario is most affected by an indicator breach."""
    bear_thr = indicator.get('bear_threshold', '')
    bull_thr = indicator.get('bull_threshold', '')
    status = indicator.get('status', 'green')

    if not bear_thr and not bull_thr:
        return None

    # If bear threshold is crossed, Bear scenario is becoming more likely
    # If bull threshold is crossed, Bull scenario is more likely
    # This is a simplification — real logic would need threshold direction parsing
    if status == 'red':
        if bear_thr and bear_thr.lower() not in ('n/a', 'na', '—'):
            return 'Bear'
    return None


async def _upsert_alert(
    db: aiosqlite.Connection,
    company_id: int,
    indicator_id: int | None,
    tier: str,
    category: str,
    title: str,
    description: str,
    affected_scenario: str | None = None,
    suggested_action: str | None = None,
):
    """Create or update an alert, avoiding duplicates."""
    # Check for existing active alert with same category and indicator
    if indicator_id:
        existing = await db.execute_fetchall(
            """SELECT id FROM alerts
               WHERE company_id = ? AND indicator_id = ? AND category = ? AND is_active = 1""",
            (company_id, indicator_id, category),
        )
    else:
        existing = await db.execute_fetchall(
            """SELECT id FROM alerts
               WHERE company_id = ? AND indicator_id IS NULL AND category = ? AND is_active = 1
               AND title = ?""",
            (company_id, category, title),
        )

    if existing:
        # Update existing alert
        await db.execute(
            """UPDATE alerts SET tier = ?, title = ?, description = ?,
               affected_scenario = ?, suggested_action = ?
               WHERE id = ?""",
            (tier, title, description, affected_scenario, suggested_action, existing[0]['id']),
        )
    else:
        await db.execute(
            """INSERT INTO alerts
               (company_id, indicator_id, tier, category, title, description, affected_scenario, suggested_action)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_id, indicator_id, tier, category, title, description,
             affected_scenario, suggested_action),
        )
