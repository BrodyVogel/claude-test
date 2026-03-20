"""PDF extraction for Step 7b Scenario Analysis documents using pdfplumber."""

import re
from typing import Optional

# Fuzzy column name mapping
COLUMN_MAP = {
    "indicator": "name",
    "metric": "name",
    "current": "current_value",
    "current value": "current_value",
    "bear threshold": "bear_threshold",
    "bear thr.": "bear_threshold",
    "bear thr": "bear_threshold",
    "bear": "bear_threshold",
    "bull threshold": "bull_threshold",
    "bull thr.": "bull_threshold",
    "bull thr": "bull_threshold",
    "bull": "bull_threshold",
    "frequency": "check_frequency",
    "freq.": "check_frequency",
    "freq": "check_frequency",
    "source": "data_source",
    "data source": "data_source",
    "added from": "added_from",
    "added": "added_from",
    "step": "added_from",
}


def _normalize_header(header: str) -> Optional[str]:
    if not header:
        return None
    h = header.strip().lower()
    if h in COLUMN_MAP:
        return COLUMN_MAP[h]
    # Partial matching
    for key, val in COLUMN_MAP.items():
        if key in h or h in key:
            return val
    return None


def extract_monitoring_framework(pdf_path: str) -> dict:
    """Extract the monitoring framework table from a Step 7b PDF.

    Returns:
        {
            "indicators": [
                {
                    "name": "...",
                    "current_value": "...",
                    "bear_threshold": "...",
                    "bull_threshold": "...",
                    "check_frequency": "...",
                    "data_source": "...",
                    "added_from": "..."
                },
                ...
            ],
            "scenarios": [...],  # extracted scenario data if found
            "raw_text": "..."    # raw text from monitoring framework pages
        }
    """
    import pdfplumber

    result = {"indicators": [], "scenarios": [], "raw_text": ""}
    framework_pages = []

    with pdfplumber.open(pdf_path) as pdf:
        # Find pages with monitoring framework
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if re.search(r"monitoring\s+framework", text, re.IGNORECASE):
                framework_pages.append(i)
                result["raw_text"] += f"\n--- Page {i + 1} ---\n{text}"

        # Extract tables from those pages
        for page_idx in framework_pages:
            page = pdf.pages[page_idx]
            tables = page.extract_tables()
            for table in tables:
                indicators = _parse_indicator_table(table)
                if indicators:
                    result["indicators"].extend(indicators)

        # Try to extract scenario data from the full document
        result["scenarios"] = _extract_scenarios(pdf)

    return result


def _parse_indicator_table(table: list[list]) -> list[dict]:
    """Parse a table into indicator dicts using fuzzy header matching."""
    if not table or len(table) < 2:
        return []

    # Map headers
    headers = table[0]
    col_mapping = {}
    for i, h in enumerate(headers):
        mapped = _normalize_header(h)
        if mapped:
            col_mapping[i] = mapped

    # Need at least the name column
    name_cols = [i for i, v in col_mapping.items() if v == "name"]
    if not name_cols:
        return []

    indicators = []
    for row in table[1:]:
        if not row or all(not cell for cell in row):
            continue
        indicator = {}
        for col_idx, field_name in col_mapping.items():
            if col_idx < len(row):
                val = row[col_idx]
                if val:
                    indicator[field_name] = str(val).strip()
        if indicator.get("name"):
            # Set defaults for missing fields
            indicator.setdefault("current_value", "")
            indicator.setdefault("bear_threshold", "")
            indicator.setdefault("bull_threshold", "")
            indicator.setdefault("check_frequency", "Monthly")
            indicator.setdefault("data_source", "Unknown")
            indicator.setdefault("added_from", "")
            indicators.append(indicator)

    return indicators


def _extract_scenarios(pdf) -> list[dict]:
    """Try to extract scenario data (weights, prices) from the PDF.

    This is best-effort — manual entry is the primary flow.
    """
    scenarios = []
    full_text = ""
    for page in pdf.pages:
        full_text += (page.extract_text() or "") + "\n"

    # Look for scenario probability patterns like "Bear (30%)" or "Bear: 30%"
    pattern = re.compile(
        r"(bear|base|bull|tail|geopolitical|upside|downside)\s*"
        r"[\(:]\s*(\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    )
    for match in pattern.finditer(full_text):
        scenarios.append(
            {
                "name": match.group(1).strip().title(),
                "raw_weight": float(match.group(2)) / 100,
                "source": "pdf_extraction",
            }
        )

    return scenarios
