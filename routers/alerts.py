from datetime import datetime
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_db

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts")
async def get_alerts(
    company_id: Optional[int] = Query(None),
    tier: Optional[str] = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    query = "SELECT a.*, c.name as company_name, c.ticker FROM alerts a JOIN companies c ON a.company_id = c.id WHERE a.is_active = 1"
    params = []
    if company_id:
        query += " AND a.company_id = ?"
        params.append(company_id)
    if tier:
        query += " AND a.tier = ?"
        params.append(tier)
    query += " ORDER BY CASE a.tier WHEN 'red' THEN 0 WHEN 'amber' THEN 1 ELSE 2 END, a.created_at DESC"
    rows = await db.execute_fetchall(query, params)
    return [dict(r) for r in rows]


@router.put("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.execute(
        "UPDATE alerts SET acknowledged_at = ?, is_active = 0 WHERE id = ?",
        (datetime.utcnow().isoformat(), alert_id),
    )
    await db.commit()
    return {"message": "Alert acknowledged"}
