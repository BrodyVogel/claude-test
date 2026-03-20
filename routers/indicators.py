from datetime import datetime

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from models import IndicatorCreate, IndicatorUpdate, ReadingCreate

router = APIRouter(prefix="/api", tags=["indicators"])


@router.post("/companies/{company_id}/indicators")
async def create_indicator(company_id: int, ind: IndicatorCreate, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT id FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")

    cursor = await db.execute(
        """INSERT INTO indicators (company_id, name, current_value, current_value_numeric,
           bear_threshold, bear_threshold_numeric, bull_threshold, bull_threshold_numeric,
           check_frequency, data_source, added_from, is_shared, shared_indicator_group, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            company_id,
            ind.name,
            ind.current_value,
            ind.current_value_numeric,
            ind.bear_threshold,
            ind.bear_threshold_numeric,
            ind.bull_threshold,
            ind.bull_threshold_numeric,
            ind.check_frequency,
            ind.data_source,
            ind.added_from,
            ind.is_shared,
            ind.shared_indicator_group,
            ind.status or "green",
        ),
    )
    await db.commit()
    return {"id": cursor.lastrowid, "message": "Indicator created"}


@router.put("/indicators/{indicator_id}")
async def update_indicator(indicator_id: int, update: IndicatorUpdate, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM indicators WHERE id = ?", (indicator_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Indicator not found")

    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [indicator_id]
    await db.execute(f"UPDATE indicators SET {set_clause} WHERE id = ?", values)
    await db.commit()
    return {"message": "Indicator updated"}


@router.delete("/indicators/{indicator_id}")
async def delete_indicator(indicator_id: int, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM indicators WHERE id = ?", (indicator_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Indicator not found")
    await db.execute("DELETE FROM indicators WHERE id = ?", (indicator_id,))
    await db.commit()
    return {"message": "Indicator deleted"}


@router.get("/indicators/shared")
async def get_shared_indicators(db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall(
        """SELECT i.*, c.name as company_name, c.ticker
           FROM indicators i JOIN companies c ON i.company_id = c.id
           WHERE i.is_shared = 1
           ORDER BY i.shared_indicator_group, c.name"""
    )
    groups = {}
    for r in rows:
        d = dict(r)
        group = d.get("shared_indicator_group") or "ungrouped"
        groups.setdefault(group, []).append(d)
    return groups


# --- Readings ---

@router.post("/indicators/{indicator_id}/readings")
async def create_reading(indicator_id: int, reading: ReadingCreate, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM indicators WHERE id = ?", (indicator_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Indicator not found")

    cursor = await db.execute(
        """INSERT INTO indicator_readings (indicator_id, value_text, value_numeric,
           source_url, source_snippet, checked_at, status_at_reading, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            indicator_id,
            reading.value_text,
            reading.value_numeric,
            reading.source_url,
            reading.source_snippet,
            reading.checked_at,
            reading.status_at_reading,
            reading.notes,
        ),
    )

    # Update indicator's current value and last_checked
    await db.execute(
        """UPDATE indicators SET current_value = ?, current_value_numeric = ?,
           last_checked_at = ?, status = COALESCE(?, status), updated_at = ?
           WHERE id = ?""",
        (
            reading.value_text,
            reading.value_numeric,
            reading.checked_at,
            reading.status_at_reading,
            datetime.utcnow().isoformat(),
            indicator_id,
        ),
    )
    await db.commit()
    return {"id": cursor.lastrowid, "message": "Reading recorded"}


@router.get("/indicators/{indicator_id}/readings")
async def get_readings(indicator_id: int, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall(
        "SELECT * FROM indicator_readings WHERE indicator_id = ? ORDER BY checked_at DESC",
        (indicator_id,),
    )
    return [dict(r) for r in rows]
