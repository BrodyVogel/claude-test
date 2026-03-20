import aiosqlite
from fastapi import APIRouter, Depends

from database import get_db
from services.rating_logic import compute_suggested_rating, compute_upside

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard(db: aiosqlite.Connection = Depends(get_db)):
    companies = await db.execute_fetchall("SELECT * FROM companies ORDER BY name")
    result = []
    for c in companies:
        c = dict(c)
        company_id = c["id"]

        # Compute suggested rating
        if c["current_price"] and c["blended_price_target"]:
            c["suggested_rating"] = compute_suggested_rating(c["current_price"], c["blended_price_target"])
            c["upside"] = compute_upside(c["current_price"], c["blended_price_target"])
        else:
            c["suggested_rating"] = None
            c["upside"] = None

        # Alert counts
        alert_rows = await db.execute_fetchall(
            "SELECT tier, COUNT(*) as cnt FROM alerts WHERE company_id = ? AND is_active = 1 GROUP BY tier",
            (company_id,),
        )
        c["alert_counts"] = {r["tier"]: r["cnt"] for r in alert_rows}

        # Indicator summary
        ind_rows = await db.execute_fetchall(
            "SELECT status, COUNT(*) as cnt FROM indicators WHERE company_id = ? GROUP BY status",
            (company_id,),
        )
        c["indicator_status"] = {r["status"]: r["cnt"] for r in ind_rows}

        # Stale indicator count
        stale = await db.execute_fetchall(
            """SELECT COUNT(*) as cnt FROM indicators
               WHERE company_id = ? AND next_check_due IS NOT NULL
               AND next_check_due < datetime('now')""",
            (company_id,),
        )
        c["stale_indicators"] = stale[0]["cnt"] if stale else 0

        # Scenario count
        sc = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM scenarios WHERE company_id = ?", (company_id,)
        )
        c["scenario_count"] = sc[0]["cnt"] if sc else 0

        result.append(c)

    return result
