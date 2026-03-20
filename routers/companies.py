import json
import os
from datetime import datetime

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from database import get_db
from models import CompanyCreate, CompanyUpdate, ScenarioCreate, ScenarioUpdate
from services.alert_engine import check_rating_alerts
from services.pdf_extractor import extract_monitoring_framework
from services.rating_logic import compute_suggested_rating, compute_upside

router = APIRouter(prefix="/api", tags=["companies"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)


@router.post("/companies")
async def create_company(company: CompanyCreate, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute(
        """INSERT INTO companies (name, ticker, exchange, currency, current_rating,
           current_price, blended_price_target, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            company.name,
            company.ticker,
            company.exchange,
            company.currency,
            company.current_rating,
            company.current_price,
            company.blended_price_target,
            company.notes,
        ),
    )
    await db.commit()
    company_id = cursor.lastrowid

    # Record initial price
    if company.current_price:
        await db.execute(
            "INSERT INTO price_history (company_id, price, recorded_at) VALUES (?, ?, ?)",
            (company_id, company.current_price, datetime.utcnow().isoformat()),
        )
        await db.commit()

    # Check for rating alerts
    await check_rating_alerts(db, company_id)

    return {"id": company_id, "message": "Company created"}


@router.get("/companies")
async def list_companies(db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall(
        "SELECT * FROM companies ORDER BY name"
    )
    companies = [dict(r) for r in rows]
    for c in companies:
        if c["current_price"] and c["blended_price_target"]:
            c["suggested_rating"] = compute_suggested_rating(c["current_price"], c["blended_price_target"])
            c["upside"] = compute_upside(c["current_price"], c["blended_price_target"])
        else:
            c["suggested_rating"] = None
            c["upside"] = None
        # Get alert counts
        alert_rows = await db.execute_fetchall(
            "SELECT tier, COUNT(*) as cnt FROM alerts WHERE company_id = ? AND is_active = 1 GROUP BY tier",
            (c["id"],),
        )
        c["alert_counts"] = {r["tier"]: r["cnt"] for r in alert_rows}
    return companies


@router.get("/companies/{company_id}")
async def get_company(company_id: int, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")
    company = dict(rows[0])

    if company["current_price"] and company["blended_price_target"]:
        company["suggested_rating"] = compute_suggested_rating(company["current_price"], company["blended_price_target"])
        company["upside"] = compute_upside(company["current_price"], company["blended_price_target"])
    else:
        company["suggested_rating"] = None
        company["upside"] = None

    # Scenarios
    scenario_rows = await db.execute_fetchall(
        "SELECT * FROM scenarios WHERE company_id = ? ORDER BY sort_order, id", (company_id,)
    )
    company["scenarios"] = [dict(r) for r in scenario_rows]

    # Indicators with latest reading
    indicator_rows = await db.execute_fetchall(
        "SELECT * FROM indicators WHERE company_id = ? ORDER BY id", (company_id,)
    )
    indicators = []
    for ind in indicator_rows:
        ind_dict = dict(ind)
        latest = await db.execute_fetchall(
            "SELECT * FROM indicator_readings WHERE indicator_id = ? ORDER BY checked_at DESC LIMIT 1",
            (ind_dict["id"],),
        )
        ind_dict["latest_reading"] = dict(latest[0]) if latest else None
        indicators.append(ind_dict)
    company["indicators"] = indicators

    # Active alerts
    alert_rows = await db.execute_fetchall(
        "SELECT * FROM alerts WHERE company_id = ? AND is_active = 1 ORDER BY created_at DESC",
        (company_id,),
    )
    company["alerts"] = [dict(r) for r in alert_rows]

    return company


@router.put("/companies/{company_id}")
async def update_company(company_id: int, update: CompanyUpdate, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")

    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields["updated_at"] = datetime.utcnow().isoformat()

    # Track price changes
    if "current_price" in fields and fields["current_price"]:
        fields["price_updated_at"] = datetime.utcnow().isoformat()
        await db.execute(
            "INSERT INTO price_history (company_id, price, recorded_at) VALUES (?, ?, ?)",
            (company_id, fields["current_price"], datetime.utcnow().isoformat()),
        )

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [company_id]
    await db.execute(f"UPDATE companies SET {set_clause} WHERE id = ?", values)
    await db.commit()

    # Re-check rating alerts
    await check_rating_alerts(db, company_id)

    return {"message": "Company updated"}


@router.delete("/companies/{company_id}")
async def delete_company(company_id: int, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")
    await db.execute("DELETE FROM companies WHERE id = ?", (company_id,))
    await db.commit()
    return {"message": "Company deleted"}


# --- Scenarios ---

@router.post("/companies/{company_id}/scenarios")
async def create_scenario(company_id: int, scenario: ScenarioCreate, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT id FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")

    contribution = None
    if scenario.effective_weight is not None and scenario.implied_price is not None:
        contribution = scenario.effective_weight * scenario.implied_price

    cursor = await db.execute(
        """INSERT INTO scenarios (company_id, name, raw_weight, effective_weight, implied_price,
           contribution, fy_revenue, fy_ebitda, fy_eps, fy_fcf,
           narrative_summary, trigger_conditions, sort_order)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            company_id,
            scenario.name,
            scenario.raw_weight,
            scenario.effective_weight,
            scenario.implied_price,
            contribution or scenario.contribution,
            scenario.fy_revenue,
            scenario.fy_ebitda,
            scenario.fy_eps,
            scenario.fy_fcf,
            scenario.narrative_summary,
            scenario.trigger_conditions,
            scenario.sort_order,
        ),
    )
    await db.commit()
    return {"id": cursor.lastrowid, "message": "Scenario created"}


@router.put("/scenarios/{scenario_id}")
async def update_scenario(scenario_id: int, update: ScenarioUpdate, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Scenario not found")

    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [scenario_id]
    await db.execute(f"UPDATE scenarios SET {set_clause} WHERE id = ?", values)
    await db.commit()
    return {"message": "Scenario updated"}


@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: int, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Scenario not found")
    await db.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
    await db.commit()
    return {"message": "Scenario deleted"}


# --- PDF Upload ---

@router.post("/companies/{company_id}/upload-scenario-doc")
async def upload_scenario_doc(
    company_id: int,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await db.execute_fetchall("SELECT id FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Save the file
    filename = f"company_{company_id}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    # Update company record
    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE companies SET scenario_doc_path = ?, scenario_doc_uploaded_at = ?, updated_at = ? WHERE id = ?",
        (filepath, now, now, company_id),
    )
    await db.commit()

    # Extract monitoring framework
    try:
        extracted = extract_monitoring_framework(filepath)
    except Exception as e:
        return {
            "message": "PDF uploaded but extraction failed. Use manual entry.",
            "error": str(e),
            "doc_path": filepath,
            "indicators": [],
            "scenarios": [],
        }

    return {
        "message": "PDF uploaded and parsed",
        "doc_path": filepath,
        "indicators": extracted["indicators"],
        "scenarios": extracted["scenarios"],
        "raw_text_preview": extracted["raw_text"][:2000] if extracted["raw_text"] else "",
    }
