"""Indicator checker service — parsing and status determination utilities.

The API-based checking functions have been removed. Indicator data now comes
via the sweep import endpoint (routers/sweep_import.py).
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

FREQUENCY_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "semiannual": 180,
    "semiannually": 180,
    "annual": 365,
    "annually": 365,
}

# Frequencies that are not auto-checked
MANUAL_FREQUENCIES = {"once", "event", "pre-earnings"}


def _is_check_due(last_checked_at: Optional[str], frequency: str) -> bool:
    freq_lower = frequency.lower().strip()

    if freq_lower in MANUAL_FREQUENCIES:
        return False

    if not last_checked_at:
        return True

    interval_days = FREQUENCY_DAYS.get(freq_lower)
    if interval_days is None:
        return False

    try:
        last_checked = datetime.fromisoformat(last_checked_at)
    except (ValueError, TypeError):
        return True

    return datetime.utcnow() >= last_checked + timedelta(days=interval_days)


def parse_numeric_value(text: str) -> Optional[float]:
    """Parse a numeric value from text like '$113.71', '873K', '6.11%', '¥157', etc."""
    if not text:
        return None
    cleaned = text.strip()

    # Remove common prefixes/suffixes
    cleaned = re.sub(r'^[~≈≤≥<>$¥€£₩]+', '', cleaned)
    cleaned = re.sub(r'\s*\(.*?\)\s*$', '', cleaned)  # remove trailing parens
    cleaned = cleaned.strip()

    # Handle ranges like "50–55" — take midpoint
    range_match = re.match(r'^(-?[\d,.]+)\s*[–\-to]+\s*(-?[\d,.]+)', cleaned)
    if range_match:
        try:
            low = float(range_match.group(1).replace(',', ''))
            high = float(range_match.group(2).replace(',', ''))
            return (low + high) / 2
        except ValueError:
            pass

    # Extract number with optional suffix
    num_match = re.match(r'^(-?[\d,.]+)\s*(%|K|M|B|T|bps)?', cleaned, re.IGNORECASE)
    if not num_match:
        return None

    try:
        val = float(num_match.group(1).replace(',', ''))
    except ValueError:
        return None

    suffix = (num_match.group(2) or '').upper()
    multipliers = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000, 'T': 1_000_000_000_000}
    if suffix in multipliers:
        val *= multipliers[suffix]
    elif suffix == '%':
        pass  # keep as-is, the threshold comparison will also be in %
    elif suffix == 'BPS':
        val /= 100  # convert basis points to percentage

    return val


def _parse_threshold_direction_and_value(threshold_text: str) -> tuple[Optional[str], Optional[float]]:
    """Parse a threshold like '<860K', '>6.5%', '>$120 4wk' into (direction, numeric_value).

    Returns ('>', value), ('<', value), or (None, None) if unparsable.
    """
    if not threshold_text:
        return None, None

    text = threshold_text.strip()
    if text.lower() in ('n/a', 'na', '—', '-', ''):
        return None, None

    # Extract direction
    direction = None
    if text.startswith('>=') or text.startswith('≥'):
        direction = '>='
        text = text[2:] if text[0] in '>' else text[1:]
    elif text.startswith('<=') or text.startswith('≤'):
        direction = '<='
        text = text[2:] if text[0] in '<' else text[1:]
    elif text.startswith('>'):
        direction = '>'
        text = text[1:]
    elif text.startswith('<'):
        direction = '<'
        text = text[1:]

    if not direction:
        return None, None

    val = parse_numeric_value(text)
    return direction, val


def determine_status(
    value_numeric: Optional[float],
    bear_threshold: str,
    bull_threshold: str,
    historical_readings: list[dict],
) -> str:
    """Determine indicator status based on value vs thresholds.

    Returns: 'red', 'amber', 'green', or 'manual_review'
    """
    bear_dir, bear_val = _parse_threshold_direction_and_value(bear_threshold)
    bull_dir, bull_val = _parse_threshold_direction_and_value(bull_threshold)

    # If both thresholds are non-numeric, needs manual review
    if bear_val is None and bull_val is None:
        # Check for n/a — informational only
        bear_lower = (bear_threshold or '').strip().lower()
        bull_lower = (bull_threshold or '').strip().lower()
        if bear_lower in ('n/a', 'na', '', '—') and bull_lower in ('n/a', 'na', '', '—'):
            return 'green'
        return 'manual_review'

    if value_numeric is None:
        return 'manual_review'

    # Check bear threshold breach
    if bear_val is not None and bear_dir:
        bear_breached = False
        if bear_dir in ('>', '>='):
            bear_breached = value_numeric > bear_val if bear_dir == '>' else value_numeric >= bear_val
        elif bear_dir in ('<', '<='):
            bear_breached = value_numeric < bear_val if bear_dir == '<' else value_numeric <= bear_val
        if bear_breached:
            return 'red'

    # Check bull threshold breach
    if bull_val is not None and bull_dir:
        bull_breached = False
        if bull_dir in ('>', '>='):
            bull_breached = value_numeric > bull_val if bull_dir == '>' else value_numeric >= bull_val
        elif bull_dir in ('<', '<='):
            bull_breached = value_numeric < bull_val if bull_dir == '<' else value_numeric <= bull_val
        if bull_breached:
            return 'red'

    # Check trending toward threshold (need 3+ readings)
    if len(historical_readings) >= 3:
        recent = sorted(historical_readings, key=lambda r: r.get('checked_at', ''))[-3:]
        numerics = [r.get('value_numeric') for r in recent if r.get('value_numeric') is not None]
        if len(numerics) >= 3:
            # Simple linear velocity: change per reading
            velocity = (numerics[-1] - numerics[0]) / (len(numerics) - 1)
            if velocity != 0:
                # Project 2 readings ahead (~30-60 days depending on frequency)
                projected = numerics[-1] + velocity * 2

                # Would projected value breach bear?
                if bear_val is not None and bear_dir:
                    if bear_dir in ('>', '>=') and projected > bear_val and numerics[-1] <= bear_val:
                        return 'amber'
                    if bear_dir in ('<', '<=') and projected < bear_val and numerics[-1] >= bear_val:
                        return 'amber'

                # Would projected value breach bull?
                if bull_val is not None and bull_dir:
                    if bull_dir in ('>', '>=') and projected > bull_val and numerics[-1] <= bull_val:
                        return 'amber'
                    if bull_dir in ('<', '<=') and projected < bull_val and numerics[-1] >= bull_val:
                        return 'amber'

    return 'green'


async def get_due_indicators(db: aiosqlite.Connection, budget: int = 50, company_id: Optional[int] = None) -> list[dict]:
    """Get indicators that are due for checking, respecting budget limits.

    Priority: RED status first, then AMBER, then longest since last check.
    """
    query = """
        SELECT i.*, c.name as company_name, c.ticker as company_ticker,
               c.exchange as company_exchange, c.currency as company_currency
        FROM indicators i
        JOIN companies c ON i.company_id = c.id
    """
    params = []
    if company_id:
        query += " WHERE i.company_id = ?"
        params.append(company_id)

    query += """
        ORDER BY
            CASE i.status WHEN 'red' THEN 0 WHEN 'amber' THEN 1 ELSE 2 END,
            COALESCE(i.last_checked_at, '2000-01-01') ASC
    """

    rows = await db.execute_fetchall(query, params)
    due = []
    for r in rows:
        ind = dict(r)
        if _is_check_due(ind.get('last_checked_at'), ind['check_frequency']):
            due.append(ind)
            if len(due) >= budget:
                break
    return due
