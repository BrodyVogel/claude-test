"""Sweep import router — accepts JSON file with indicator data and updates the database."""

import logging
import re
from datetime import datetime
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, File, Request, UploadFile

from database import get_db
from services.alert_engine import check_rating_alerts, run_full_alert_check
from services.indicator_checker import determine_status, parse_numeric_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["import"])


def _normalize_indicator_name(name: str) -> str:
    """Normalize indicator name for fuzzy matching: lowercase, strip whitespace."""
    return name.strip().lower()


def _normalize_indicator_name_aggressive(name: str) -> str:
    """More aggressive normalization: also remove parens, dashes, special chars."""
    normalized = _normalize_indicator_name(name)
    normalized = re.sub(r'[()\-–—/\\.,;:\'"]+', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def _match_indicator(sweep_name: str, db_indicators: list[dict]) -> Optional[dict]:
    """Try to match a sweep indicator name to a DB indicator using fuzzy matching."""
    norm_sweep = _normalize_indicator_name(sweep_name)

    # Exact normalized match
    for ind in db_indicators:
        if _normalize_indicator_name(ind['name']) == norm_sweep:
            return ind

    # Aggressive normalization match
    agg_sweep = _normalize_indicator_name_aggressive(sweep_name)
    for ind in db_indicators:
        if _normalize_indicator_name_aggressive(ind['name']) == agg_sweep:
            return ind

    # Substring containment (either direction)
    for ind in db_indicators:
        db_norm = _normalize_indicator_name(ind['name'])
        if norm_sweep in db_norm or db_norm in norm_sweep:
            return ind

    return None


@router.post("/import/sweep")
async def import_sweep(request: Request, file: Optional[UploadFile] = File(None), db: aiosqlite.Connection = Depends(get_db)):
    """Import a sweep JSON file to update prices and indicator readings.

    Accepts either a file upload or a raw JSON body.
    """
    # Parse JSON from file upload or raw body
    if file:
        content = await file.read()
        import json
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON in uploaded file"}, 400
    else:
        data = await request.json()

    sweep_date = data.get("sweep_date", datetime.utcnow().isoformat())
    companies_data = data.get("companies", [])

    if not companies_data:
        return {"error": "No companies in sweep data"}

    summary = {
        "companies_processed": 0,
        "indicators_updated": 0,
        "status_changes": 0,
        "unmatched_indicators": [],
        "errors": [],
    }

    companies_with_price_update = []

    for company_data in companies_data:
        ticker = company_data.get("ticker")
        if not ticker:
            summary["errors"].append("Company entry missing ticker")
            continue

        # Find company by ticker (case-insensitive)
        rows = await db.execute_fetchall(
            "SELECT * FROM companies WHERE LOWER(ticker) = LOWER(?)", (ticker,)
        )
        if not rows:
            summary["errors"].append(f"Company with ticker '{ticker}' not found in database")
            continue

        company = dict(rows[0])
        company_id = company["id"]
        summary["companies_processed"] += 1

        # Update price if provided
        current_price = company_data.get("current_price")
        if current_price is not None:
            await db.execute(
                "UPDATE companies SET current_price = ?, price_updated_at = ?, updated_at = ? WHERE id = ?",
                (current_price, sweep_date, sweep_date, company_id),
            )
            await db.execute(
                "INSERT INTO price_history (company_id, price, recorded_at) VALUES (?, ?, ?)",
                (company_id, current_price, sweep_date),
            )
            companies_with_price_update.append(company_id)

        # Get all indicators for this company
        ind_rows = await db.execute_fetchall(
            "SELECT * FROM indicators WHERE company_id = ?", (company_id,)
        )
        db_indicators = [dict(r) for r in ind_rows]

        # Process each indicator from the sweep
        for ind_data in company_data.get("indicators", []):
            ind_name = ind_data.get("name")
            if not ind_name:
                continue

            matched = _match_indicator(ind_name, db_indicators)
            if not matched:
                summary["unmatched_indicators"].append({
                    "ticker": ticker,
                    "indicator_name": ind_name,
                })
                continue

            indicator_id = matched["id"]

            # Parse value_numeric — use provided or parse from value text
            value_numeric = ind_data.get("value_numeric")
            value_text = ind_data.get("value", "")
            if value_numeric is None and value_text:
                value_numeric = parse_numeric_value(value_text)

            # Get historical readings for trending analysis
            hist_rows = await db.execute_fetchall(
                """SELECT value_text, value_numeric, checked_at
                   FROM indicator_readings
                   WHERE indicator_id = ?
                   ORDER BY checked_at DESC LIMIT 10""",
                (indicator_id,),
            )
            historical = [dict(r) for r in hist_rows]

            # Determine status
            new_status = determine_status(
                value_numeric,
                matched.get("bear_threshold", ""),
                matched.get("bull_threshold", ""),
                historical,
            )

            old_status = matched.get("status", "green")
            if old_status != new_status:
                summary["status_changes"] += 1

            # Insert reading
            source_url = ind_data.get("source_url", "")
            context = ind_data.get("context", "")
            confidence = ind_data.get("confidence", "")

            await db.execute(
                """INSERT INTO indicator_readings
                   (indicator_id, value_text, value_numeric, source_url, source_snippet, checked_at, status_at_reading, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    indicator_id,
                    value_text,
                    value_numeric,
                    source_url,
                    context,
                    sweep_date,
                    new_status,
                    f"Confidence: {confidence}" if confidence else "Imported via sweep",
                ),
            )

            # Update indicator
            await db.execute(
                """UPDATE indicators SET
                   current_value = ?, current_value_numeric = ?,
                   last_checked_at = ?, status = ?, updated_at = ?
                   WHERE id = ?""",
                (value_text, value_numeric, sweep_date, new_status, sweep_date, indicator_id),
            )

            summary["indicators_updated"] += 1

    await db.commit()

    # Run alert engine
    try:
        await run_full_alert_check(db)
    except Exception as e:
        logger.error("Alert engine error: %s", e)
        summary["errors"].append(f"Alert engine error: {str(e)}")

    # Check rating alerts for companies with price updates
    for cid in companies_with_price_update:
        try:
            await check_rating_alerts(db, cid)
        except Exception as e:
            logger.error("Rating alert error for company %d: %s", cid, e)

    await db.commit()

    return {
        "status": "ok",
        "sweep_date": sweep_date,
        "summary": summary,
    }
