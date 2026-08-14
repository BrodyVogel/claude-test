# DEPRECATED: Price updates now come via sweep import. This file is kept for reference.
"""Price tracking service — uses Claude API with web search to get current stock prices."""

import logging
import re
import time
from datetime import datetime

import aiosqlite
import anthropic
from dotenv import load_dotenv

from services.rating_logic import compute_suggested_rating, compute_upside

load_dotenv()

logger = logging.getLogger(__name__)


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _extract_text_from_response(response) -> str:
    texts = []
    for block in response.content:
        if block.type == 'text':
            texts.append(block.text)
    return '\n'.join(texts)


def _parse_price(text: str) -> float | None:
    """Extract a numeric price from response text."""
    # Look for a standalone number (possibly with commas and decimals)
    numbers = re.findall(r'[\d,]+\.?\d*', text)
    if not numbers:
        return None
    # Take the first reasonable number
    for n in numbers:
        try:
            val = float(n.replace(',', ''))
            if val > 0:
                return val
        except ValueError:
            continue
    return None


def fetch_price(company: dict) -> dict:
    """Fetch current stock price for a company using Claude API + web search."""
    client = _get_client()

    currency_hint = ""
    if company.get('currency') == 'JPY':
        currency_hint = " Return the price in Japanese yen (no currency symbol, just the number)."
    elif company.get('currency') == 'USD':
        currency_hint = " Return the price in US dollars (no currency symbol, just the number)."

    prompt = (
        f"What is the current stock price of {company['name']} ({company['ticker']}) "
        f"on the {company.get('exchange', '')}?{currency_hint} "
        f"Return ONLY the price as a number (no currency symbol). "
        f"If the market is closed, return the most recent closing price."
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = _extract_text_from_response(response)
        price = _parse_price(response_text)

        return {
            'price': price,
            'raw_response': response_text,
            'error': None,
        }

    except anthropic.APIError as e:
        logger.error("API error fetching price for %s: %s", company['ticker'], e)
        return {'price': None, 'raw_response': None, 'error': str(e)}
    except Exception as e:
        logger.error("Unexpected error fetching price for %s: %s", company['ticker'], e)
        return {'price': None, 'raw_response': None, 'error': str(e)}


async def update_company_price(db: aiosqlite.Connection, company: dict) -> dict:
    """Fetch and store a new price for one company. Returns summary."""
    result = fetch_price(company)

    if result['error'] or result['price'] is None:
        return {
            'company_id': company['id'],
            'ticker': company['ticker'],
            'status': 'error',
            'error': result['error'] or 'Could not parse price',
        }

    now = datetime.utcnow().isoformat()
    new_price = result['price']
    old_price = company.get('current_price')

    # Store in price_history
    await db.execute(
        "INSERT INTO price_history (company_id, price, recorded_at) VALUES (?, ?, ?)",
        (company['id'], new_price, now),
    )

    # Update company
    await db.execute(
        """UPDATE companies SET current_price = ?, price_updated_at = ?, updated_at = ?
           WHERE id = ?""",
        (new_price, now, now, company['id']),
    )
    await db.commit()

    # Compute new suggested rating
    suggested = compute_suggested_rating(new_price, company['blended_price_target'])
    new_upside = compute_upside(new_price, company['blended_price_target'])
    old_upside = compute_upside(old_price, company['blended_price_target']) if old_price else None

    return {
        'company_id': company['id'],
        'ticker': company['ticker'],
        'status': 'updated',
        'old_price': old_price,
        'new_price': new_price,
        'suggested_rating': suggested,
        'current_rating': company.get('current_rating'),
        'upside': new_upside,
        'old_upside': old_upside,
    }


async def update_all_prices(db: aiosqlite.Connection) -> dict:
    """Update prices for all companies."""
    rows = await db.execute_fetchall("SELECT * FROM companies ORDER BY name")
    companies = [dict(r) for r in rows]

    results = []
    for company in companies:
        logger.info("Updating price: %s (%s)", company['name'], company['ticker'])
        res = await update_company_price(db, company)
        results.append(res)

        # Rate limit
        if company != companies[-1]:
            time.sleep(2)

    # Run alert engine after all price updates
    from services.alert_engine import run_full_alert_check
    await run_full_alert_check(db)

    errors = sum(1 for r in results if r['status'] == 'error')
    return {
        'updated': len(results) - errors,
        'errors': errors,
        'results': results,
        'message': f'Updated {len(results) - errors} prices ({errors} errors)',
    }
