"""API endpoint for indicator check status."""

import os
from datetime import datetime

import aiosqlite
from fastapi import APIRouter, Depends

from database import get_db
from services.indicator_checker import get_due_indicators

router = APIRouter(prefix="/api", tags=["checks"])


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
        'daily_budget': int(os.getenv('DAILY_CHECK_BUDGET', '50')),
        'status_breakdown': status_breakdown,
    }
