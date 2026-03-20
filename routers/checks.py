"""API endpoints for indicator checks and price updates."""

import os
from datetime import datetime
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_db
from services.indicator_checker import run_batch_checks, run_indicator_check, check_single_indicator, get_due_indicators
from services.price_tracker import update_all_prices

router = APIRouter(prefix="/api", tags=["checks"])


@router.post("/check/run")
async def run_checks(
    company_id: Optional[int] = Query(None),
    budget: Optional[int] = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Run all due indicator checks. Optionally filter by company and set budget."""
    result = await run_batch_checks(db, company_id=company_id, budget=budget)
    return result


@router.post("/check/company/{company_id}")
async def run_company_checks(company_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Run checks for a specific company only."""
    rows = await db.execute_fetchall("SELECT id FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")
    result = await run_batch_checks(db, company_id=company_id, budget=100)
    return result


@router.post("/check/indicator/{indicator_id}")
async def force_check_indicator(indicator_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Force-check a single indicator regardless of schedule."""
    rows = await db.execute_fetchall(
        """SELECT i.*, c.name as company_name, c.ticker as company_ticker,
                  c.exchange as company_exchange, c.currency as company_currency
           FROM indicators i JOIN companies c ON i.company_id = c.id
           WHERE i.id = ?""",
        (indicator_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Indicator not found")

    ind = dict(rows[0])
    company = {
        'id': ind['company_id'],
        'name': ind['company_name'],
        'ticker': ind['company_ticker'],
        'exchange': ind.get('company_exchange', ''),
        'currency': ind.get('company_currency', ''),
    }

    result = await run_indicator_check(db, ind, company)
    return result


@router.get("/check/status")
async def check_status(db: aiosqlite.Connection = Depends(get_db)):
    """Show status of the check system."""
    # Last check time
    last_reading = await db.execute_fetchall(
        "SELECT MAX(checked_at) as last_check FROM indicator_readings"
    )
    last_check = last_reading[0]['last_check'] if last_reading else None

    # Total indicators
    total = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM indicators")
    total_count = total[0]['cnt']

    # Due indicators
    budget = int(os.getenv('DAILY_CHECK_BUDGET', '50'))
    due = await get_due_indicators(db, budget=999)
    due_count = len(due)

    # Readings today
    today = datetime.utcnow().strftime('%Y-%m-%d')
    today_readings = await db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM indicator_readings WHERE checked_at >= ?",
        (today,),
    )
    today_count = today_readings[0]['cnt']

    # Status breakdown
    status_rows = await db.execute_fetchall(
        "SELECT status, COUNT(*) as cnt FROM indicators GROUP BY status"
    )
    status_breakdown = {r['status']: r['cnt'] for r in status_rows}

    return {
        'last_check': last_check,
        'total_indicators': total_count,
        'due_for_check': due_count,
        'checked_today': today_count,
        'daily_budget': budget,
        'status_breakdown': status_breakdown,
    }


@router.post("/prices/update")
async def update_prices(db: aiosqlite.Connection = Depends(get_db)):
    """Update all company prices via web search."""
    result = await update_all_prices(db)
    return result
