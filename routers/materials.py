"""Materials upload router — handles multi-file uploads for coverage materials."""

import logging
import os
import re
from datetime import datetime
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from database import get_db
from services.pdf_extractor import extract_monitoring_framework

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["materials"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _normalize(name: str) -> str:
    """Normalize indicator name: lowercase, strip whitespace."""
    return name.strip().lower()


def _normalize_aggressive(name: str) -> str:
    """Aggressive normalization: also remove parens, dashes, special chars."""
    n = _normalize(name)
    n = re.sub(r'[()\-–—/\\.,;:\'"]+', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def _match_indicator(pdf_name: str, db_indicators: list[dict]) -> Optional[dict]:
    """Fuzzy match a PDF indicator name to a DB indicator."""
    norm = _normalize(pdf_name)

    for ind in db_indicators:
        if _normalize(ind['name']) == norm:
            return ind

    agg = _normalize_aggressive(pdf_name)
    for ind in db_indicators:
        if _normalize_aggressive(ind['name']) == agg:
            return ind

    for ind in db_indicators:
        db_norm = _normalize(ind['name'])
        if norm in db_norm or db_norm in norm:
            return ind

    return None


class ConfirmIndicator(BaseModel):
    name: str
    current_value: Optional[str] = None
    current_value_numeric: Optional[float] = None
    bear_threshold: Optional[str] = None
    bear_threshold_numeric: Optional[float] = None
    bull_threshold: Optional[str] = None
    bull_threshold_numeric: Optional[float] = None
    check_frequency: str = "Monthly"
    data_source: str = "Unknown"
    added_from: Optional[str] = None
    is_shared: Optional[int] = 0
    shared_indicator_group: Optional[str] = None
    status: Optional[str] = "green"


class ConfirmNewRequest(BaseModel):
    indicators: list[ConfirmIndicator]


@router.post("/companies/{company_id}/materials")
async def upload_materials(
    company_id: int,
    scenario_pdf: UploadFile = File(...),
    thesis_pdf: Optional[UploadFile] = File(None),
    model_xlsx: Optional[UploadFile] = File(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Upload coverage materials (scenario PDF required, thesis PDF and model XLSX optional)."""
    # Validate company exists
    rows = await db.execute_fetchall("SELECT * FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")
    company = dict(rows[0])
    now = datetime.utcnow().isoformat()

    files_saved = []
    result = {
        "files_saved": files_saved,
        "indicators_updated": [],
        "new_indicators": [],
        "possibly_removed": [],
        "extraction_errors": [],
    }

    # Save scenario PDF (required)
    scenario_filename = f"company_{company_id}_scenario.pdf"
    scenario_path = os.path.join(UPLOAD_DIR, scenario_filename)
    content = await scenario_pdf.read()
    with open(scenario_path, "wb") as f:
        f.write(content)
    files_saved.append(scenario_filename)

    # Save thesis PDF (optional)
    if thesis_pdf:
        thesis_filename = f"company_{company_id}_thesis.pdf"
        thesis_path = os.path.join(UPLOAD_DIR, thesis_filename)
        content = await thesis_pdf.read()
        with open(thesis_path, "wb") as f:
            f.write(content)
        files_saved.append(thesis_filename)

    # Save model XLSX (optional)
    if model_xlsx:
        model_filename = f"company_{company_id}_model.xlsx"
        model_path = os.path.join(UPLOAD_DIR, model_filename)
        content = await model_xlsx.read()
        with open(model_path, "wb") as f:
            f.write(content)
        files_saved.append(model_filename)

    # Update company record
    await db.execute(
        "UPDATE companies SET scenario_doc_path = ?, scenario_doc_uploaded_at = ?, updated_at = ? WHERE id = ?",
        (scenario_path, now, now, company_id),
    )

    # Extract indicators from scenario PDF
    try:
        extracted = extract_monitoring_framework(scenario_path)
        pdf_indicators = extracted.get("indicators", [])
    except Exception as e:
        logger.error("PDF extraction failed for company %d: %s", company_id, e)
        result["extraction_errors"].append(str(e))
        await db.commit()
        return result

    if not pdf_indicators:
        result["extraction_errors"].append("No indicators found in PDF")
        await db.commit()
        return result

    # Get existing DB indicators for this company
    ind_rows = await db.execute_fetchall(
        "SELECT * FROM indicators WHERE company_id = ?", (company_id,)
    )
    db_indicators = [dict(r) for r in ind_rows]

    # Track which DB indicators were matched
    matched_db_ids = set()

    for pdf_ind in pdf_indicators:
        pdf_name = pdf_ind.get("name", "").strip()
        if not pdf_name:
            continue

        matched = _match_indicator(pdf_name, db_indicators)

        if matched:
            matched_db_ids.add(matched["id"])

            # Check if thresholds or other fields changed
            changes = {}
            for field in ("bear_threshold", "bull_threshold", "check_frequency", "data_source"):
                pdf_val = (pdf_ind.get(field) or "").strip()
                db_val = (matched.get(field) or "").strip()
                if pdf_val and pdf_val != db_val:
                    changes[field] = pdf_val

            if changes:
                changes["updated_at"] = now
                set_clause = ", ".join(f"{k} = ?" for k in changes)
                values = list(changes.values()) + [matched["id"]]
                await db.execute(
                    f"UPDATE indicators SET {set_clause} WHERE id = ?", values
                )
                result["indicators_updated"].append({
                    "id": matched["id"],
                    "name": matched["name"],
                    "changes": {k: v for k, v in changes.items() if k != "updated_at"},
                })
        else:
            # New indicator from PDF — add to pending list
            result["new_indicators"].append({
                "name": pdf_name,
                "current_value": pdf_ind.get("current_value", ""),
                "bear_threshold": pdf_ind.get("bear_threshold", ""),
                "bull_threshold": pdf_ind.get("bull_threshold", ""),
                "check_frequency": pdf_ind.get("check_frequency", "Monthly"),
                "data_source": pdf_ind.get("data_source", "Unknown"),
                "added_from": pdf_ind.get("added_from", "scenario_pdf"),
            })

    # Find DB indicators not in the PDF
    for db_ind in db_indicators:
        if db_ind["id"] not in matched_db_ids:
            result["possibly_removed"].append({
                "id": db_ind["id"],
                "name": db_ind["name"],
                "status": db_ind.get("status", "green"),
            })

    await db.commit()

    return result


@router.post("/companies/{company_id}/materials/confirm-new")
async def confirm_new_indicators(
    company_id: int,
    body: ConfirmNewRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Confirm and add new indicators discovered during materials upload."""
    rows = await db.execute_fetchall("SELECT id FROM companies WHERE id = ?", (company_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Company not found")

    created = []
    for ind in body.indicators:
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
                ind.added_from or "scenario_pdf",
                ind.is_shared,
                ind.shared_indicator_group,
                ind.status or "green",
            ),
        )
        created.append({"id": cursor.lastrowid, "name": ind.name})

    await db.commit()
    return {"message": f"Added {len(created)} indicators", "created": created}
