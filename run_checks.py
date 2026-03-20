"""CLI script to run indicator checks and price updates. Can be called from cron."""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('run_checks')


async def main():
    import aiosqlite
    from database import DB_PATH, init_db
    from services.indicator_checker import run_batch_checks
    from services.price_tracker import update_all_prices

    # Verify API key
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Create a .env file with your key.")
        sys.exit(1)

    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Parse CLI args
        mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
        company_id = None
        if len(sys.argv) > 2:
            try:
                company_id = int(sys.argv[2])
            except ValueError:
                pass

        if mode in ('all', 'indicators'):
            logger.info("=" * 60)
            logger.info("RUNNING INDICATOR CHECKS")
            logger.info("=" * 60)

            budget = int(os.getenv('DAILY_CHECK_BUDGET', '50'))
            result = await run_batch_checks(db, company_id=company_id, budget=budget)

            logger.info("Checked: %d | Errors: %d | Status changes: %d",
                        result['checked'], result['errors'], result['status_changes'])

            for r in result['results']:
                status_icon = {'checked': 'OK', 'error': 'ERR'}.get(r['status'], '??')
                changed = ' [CHANGED]' if r.get('changed') else ''
                logger.info("  [%s] %s — %s: %s%s",
                            status_icon,
                            r.get('company_name', ''),
                            r['indicator_name'],
                            r.get('value', r.get('error', '?')),
                            changed)

        if mode in ('all', 'prices'):
            logger.info("=" * 60)
            logger.info("UPDATING PRICES")
            logger.info("=" * 60)

            result = await update_all_prices(db)

            logger.info("Updated: %d | Errors: %d", result['updated'], result['errors'])

            for r in result['results']:
                if r['status'] == 'updated':
                    logger.info("  %s: %s → %s (upside: %s)",
                                r['ticker'],
                                r.get('old_price', '?'),
                                r['new_price'],
                                f"{r['upside']*100:.1f}%" if r.get('upside') is not None else '?')
                else:
                    logger.info("  %s: ERROR — %s", r['ticker'], r.get('error', '?'))

        logger.info("Done.")


if __name__ == '__main__':
    print("""
Coverage Monitor — Check Runner
================================
Usage:
  python run_checks.py              # Run all checks (indicators + prices)
  python run_checks.py indicators   # Run indicator checks only
  python run_checks.py prices       # Run price updates only
  python run_checks.py all [ID]     # Run all checks, optionally for one company
""")
    asyncio.run(main())
