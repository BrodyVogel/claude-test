"""Indicator checker service — uses Claude API with web search to check indicators."""

import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
import anthropic
from dotenv import load_dotenv

load_dotenv()

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


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


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


def _parse_response(response_text: str) -> dict:
    """Parse structured fields from Claude's response text."""
    result = {
        'value': None,
        'date': None,
        'source_url': None,
        'confidence': None,
        'context': None,
    }

    patterns = {
        'value': r'VALUE:\s*(.+?)(?:\n|$)',
        'date': r'DATE:\s*(.+?)(?:\n|$)',
        'source_url': r'SOURCE_URL:\s*(.+?)(?:\n|$)',
        'confidence': r'CONFIDENCE:\s*(.+?)(?:\n|$)',
        'context': r'CONTEXT:\s*(.+?)(?:\n|$)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, response_text, re.IGNORECASE)
        if match:
            result[key] = match.group(1).strip()

    return result


def _extract_text_from_response(response) -> str:
    """Extract all text content from an Anthropic API response."""
    texts = []
    for block in response.content:
        if block.type == 'text':
            texts.append(block.text)
    return '\n'.join(texts)


def check_single_indicator(
    indicator: dict,
    company: dict,
) -> dict:
    """Check a single indicator using Claude API with web search.

    Returns a dict with: value_text, value_numeric, source_url, source_snippet,
    status, confidence, raw_response, error
    """
    client = _get_client()

    prompt = f"""Find the most recent value for this indicator:

Indicator: {indicator['name']}
Data source: {indicator['data_source']}
Company context: {company['name']} ({company['ticker']})
Previous value: {indicator.get('current_value', 'N/A')}
Bear threshold: {indicator.get('bear_threshold', 'N/A')}
Bull threshold: {indicator.get('bull_threshold', 'N/A')}

Search for the most current data point from the specified data source. Return your answer in this exact format:

VALUE: [the value you found]
DATE: [the date of the data point, or "current" if it's a live/real-time value]
SOURCE_URL: [the URL where you found this]
CONFIDENCE: [high/medium/low — how confident you are this is the correct, current value]
CONTEXT: [1-2 sentences of relevant context about the reading]
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = _extract_text_from_response(response)
        parsed = _parse_response(response_text)

        value_text = parsed['value'] or indicator.get('current_value', '')
        value_numeric = parse_numeric_value(value_text)

        return {
            'value_text': value_text,
            'value_numeric': value_numeric,
            'source_url': parsed['source_url'],
            'source_snippet': parsed['context'],
            'confidence': parsed['confidence'],
            'raw_response': response_text,
            'error': None,
        }

    except anthropic.APIError as e:
        logger.error("API error checking indicator %s: %s", indicator['name'], e)
        return {
            'value_text': None,
            'value_numeric': None,
            'source_url': None,
            'source_snippet': None,
            'confidence': None,
            'raw_response': None,
            'error': str(e),
        }
    except Exception as e:
        logger.error("Unexpected error checking indicator %s: %s", indicator['name'], e)
        return {
            'value_text': None,
            'value_numeric': None,
            'source_url': None,
            'source_snippet': None,
            'confidence': None,
            'raw_response': None,
            'error': str(e),
        }


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


async def run_indicator_check(
    db: aiosqlite.Connection,
    indicator: dict,
    company: dict,
) -> dict:
    """Run a single indicator check: API call, store reading, update status, generate alerts."""
    now = datetime.utcnow().isoformat()

    result = check_single_indicator(indicator, company)

    if result['error']:
        logger.warning("Check failed for %s: %s", indicator['name'], result['error'])
        return {
            'indicator_id': indicator['id'],
            'indicator_name': indicator['name'],
            'status': 'error',
            'error': result['error'],
        }

    # Get historical readings for trending analysis
    hist_rows = await db.execute_fetchall(
        """SELECT value_text, value_numeric, checked_at
           FROM indicator_readings
           WHERE indicator_id = ?
           ORDER BY checked_at DESC LIMIT 10""",
        (indicator['id'],),
    )
    historical = [dict(r) for r in hist_rows]

    # Determine status
    new_status = determine_status(
        result['value_numeric'],
        indicator.get('bear_threshold', ''),
        indicator.get('bull_threshold', ''),
        historical,
    )

    # Store reading
    await db.execute(
        """INSERT INTO indicator_readings
           (indicator_id, value_text, value_numeric, source_url, source_snippet, checked_at, status_at_reading, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            indicator['id'],
            result['value_text'],
            result['value_numeric'],
            result['source_url'],
            result['source_snippet'],
            now,
            new_status,
            f"Confidence: {result['confidence']}" if result['confidence'] else None,
        ),
    )

    # Update indicator
    await db.execute(
        """UPDATE indicators SET
           current_value = ?, current_value_numeric = ?,
           last_checked_at = ?, status = ?, updated_at = ?
           WHERE id = ?""",
        (
            result['value_text'],
            result['value_numeric'],
            now,
            new_status,
            now,
            indicator['id'],
        ),
    )

    await db.commit()

    old_status = indicator.get('status', 'green')
    return {
        'indicator_id': indicator['id'],
        'indicator_name': indicator['name'],
        'company_name': company.get('name', ''),
        'status': 'checked',
        'old_status': old_status,
        'new_status': new_status,
        'value': result['value_text'],
        'source_url': result['source_url'],
        'changed': old_status != new_status,
    }


async def run_batch_checks(
    db: aiosqlite.Connection,
    company_id: Optional[int] = None,
    budget: Optional[int] = None,
) -> dict:
    """Run checks for all due indicators. Returns summary."""
    if budget is None:
        budget = int(os.getenv('DAILY_CHECK_BUDGET', '50'))

    due_indicators = await get_due_indicators(db, budget=budget, company_id=company_id)

    if not due_indicators:
        return {
            'checked': 0,
            'skipped': 0,
            'errors': 0,
            'status_changes': 0,
            'results': [],
            'message': 'No indicators due for checking',
        }

    results = []
    errors = 0
    status_changes = 0

    for ind in due_indicators:
        company = {
            'id': ind['company_id'],
            'name': ind['company_name'],
            'ticker': ind['company_ticker'],
            'exchange': ind.get('company_exchange', ''),
            'currency': ind.get('company_currency', ''),
        }

        logger.info("Checking: %s — %s", company['name'], ind['name'])
        check_result = await run_indicator_check(db, ind, company)
        results.append(check_result)

        if check_result['status'] == 'error':
            errors += 1
        elif check_result.get('changed'):
            status_changes += 1

        # Rate limit: 2-second delay between API calls
        if ind != due_indicators[-1]:
            time.sleep(2)

    # Run alert engine after all checks
    from services.alert_engine import run_full_alert_check
    await run_full_alert_check(db)

    return {
        'checked': len(results) - errors,
        'errors': errors,
        'status_changes': status_changes,
        'results': results,
        'message': f'Checked {len(results)} indicators ({errors} errors, {status_changes} status changes)',
    }
