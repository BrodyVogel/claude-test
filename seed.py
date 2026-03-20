"""Seed script to populate JHX and Lasertec test data."""

import asyncio
import aiosqlite
from database import DB_PATH, init_db

JHX = {
    "company": {
        "name": "James Hardie Industries",
        "ticker": "JHX",
        "exchange": "ASX",
        "currency": "USD",
        "current_rating": "Outperform",
        "current_price": 19.59,
        "blended_price_target": 23.88,
    },
    "scenarios": [
        {"name": "Bear", "raw_weight": 0.30, "effective_weight": 0.30, "implied_price": 15.88, "sort_order": 0},
        {"name": "Base", "raw_weight": 0.48, "effective_weight": 0.48, "implied_price": 29.21, "sort_order": 1},
        {"name": "Bull", "raw_weight": 0.10, "effective_weight": 0.10, "implied_price": 37.64, "sort_order": 2},
        {"name": "Geopolitical Tail", "raw_weight": 0.12, "effective_weight": 0.12, "implied_price": 11.12, "sort_order": 3},
    ],
    "indicators": [
        {"name": "SF permits (SAAR)", "current_value": "873K", "bear_threshold": "<860K", "bull_threshold": ">920K", "check_frequency": "Monthly", "data_source": "Census Bureau", "added_from": "Step 5b"},
        {"name": "30-yr rate (PMMS)", "current_value": "6.11%", "bear_threshold": ">6.5%", "bull_threshold": "<5.8%", "check_frequency": "Weekly", "data_source": "Freddie Mac", "added_from": "Step 5b"},
        {"name": "Brent crude ($/bbl)", "current_value": "$113.71", "bear_threshold": ">$120 4wk", "bull_threshold": "<$80", "check_frequency": "Daily", "data_source": "EIA / ICE", "added_from": "Step 5b"},
        {"name": "NAHB HMI", "current_value": "38", "bear_threshold": "<30", "bull_threshold": ">50", "check_frequency": "Monthly", "data_source": "NAHB", "added_from": "Step 5b"},
        {"name": "NAHB HMI \u2014 South", "current_value": "35", "bear_threshold": "<28", "bull_threshold": ">45", "check_frequency": "Monthly", "data_source": "NAHB", "added_from": "Step 5b"},
        {"name": "JHX NA vol growth", "current_value": "\u22122%", "bear_threshold": "<\u22125%", "bull_threshold": ">+5%", "check_frequency": "Quarterly", "data_source": "JHX IR", "added_from": "Step 5b"},
        {"name": "Trex rev growth", "current_value": "\u22123.9%", "bear_threshold": "<\u221210%", "bull_threshold": ">+10%", "check_frequency": "Quarterly", "data_source": "Trex IR", "added_from": "Step 5b"},
        {"name": "German permits (YoY)", "current_value": "+6.3%", "bear_threshold": "<0%", "bull_threshold": ">+15%", "check_frequency": "Monthly", "data_source": "Destatis", "added_from": "Step 5b"},
        {"name": "FY26E Adj EPS", "current_value": "$0.75 (est)", "bear_threshold": "n/a", "bull_threshold": "n/a", "check_frequency": "Once", "data_source": "JHX IR", "added_from": "Step 7"},
        {"name": "S&T ASP (implied)", "current_value": "~$1,010", "bear_threshold": "n/a", "bull_threshold": ">$1,030", "check_frequency": "Annual", "data_source": "JHX IR", "added_from": "Step 7"},
        {"name": "CLSA seasonal QoQ check", "current_value": "Q4 flat vs +8.5% avg", "bear_threshold": "n/a", "bull_threshold": "n/a", "check_frequency": "Pre-earnings", "data_source": "CLSA framework", "added_from": "Step 7"},
        {"name": "Regional FC penetration", "current_value": "South highest", "bear_threshold": "n/a", "bull_threshold": "n/a", "check_frequency": "Annual", "data_source": "Census/RBC", "added_from": "Step 7"},
        {"name": "Distribution partner count", "current_value": "3 named", "bear_threshold": "No new by Q2 FY27", "bull_threshold": ">5 named", "check_frequency": "Quarterly", "data_source": "JHX IR", "added_from": "Step 7"},
        {"name": "DR&A sell-through", "current_value": "Up MSD", "bear_threshold": "<flat", "bull_threshold": ">+10%", "check_frequency": "Quarterly", "data_source": "JHX IR", "added_from": "Both"},
    ],
}

LASERTEC = {
    "company": {
        "name": "Lasertec Corporation",
        "ticker": "6920",
        "exchange": "TSE",
        "currency": "JPY",
        "current_rating": "Inline",
        "current_price": 34770,
        "blended_price_target": 35107,
    },
    "scenarios": [
        {"name": "Bear", "raw_weight": 0.18, "effective_weight": 0.212, "implied_price": 20384, "sort_order": 0},
        {"name": "Base", "raw_weight": 0.52, "effective_weight": 0.612, "implied_price": 33812, "sort_order": 1},
        {"name": "Bull", "raw_weight": 0.15, "effective_weight": 0.176, "implied_price": 57346, "sort_order": 2},
    ],
    "indicators": [
        {"name": "Lasertec FY26 orders (\u00a5B)", "current_value": "~\u00a550\u201355 (H1)", "bear_threshold": "<\u00a5150 FY", "bull_threshold": ">\u00a5210 FY", "check_frequency": "Quarterly", "data_source": "Lasertec", "added_from": "Step 5b"},
        {"name": "H2 FY26 ACTIS orders (\u00a5B)", "current_value": "TBD", "bear_threshold": "<\u00a530B", "bull_threshold": ">\u00a580B", "check_frequency": "Quarterly", "data_source": "Lasertec", "added_from": "Step 7"},
        {"name": "ASML EUV bookings (\u20acB)", "current_value": "\u20ac7.4 (Q4)", "bear_threshold": "<\u20ac3 x2 qtrs", "bull_threshold": ">\u20ac6 sustained", "check_frequency": "Quarterly", "data_source": "ASML", "added_from": "Step 5b"},
        {"name": "TSMC capex run-rate ($B)", "current_value": "~$13/qtr", "bear_threshold": "<$11/qtr", "bull_threshold": ">$14/qtr", "check_frequency": "Quarterly", "data_source": "TSMC", "added_from": "Step 5b"},
        {"name": "JPY/USD rate", "current_value": "\u00a5157", "bear_threshold": "<\u00a5140", "bull_threshold": ">\u00a5160", "check_frequency": "Weekly", "data_source": "Market", "added_from": "Step 5b"},
        {"name": "SK Hynix capex (KRW T)", "current_value": "~7\u20138T/qtr", "bear_threshold": "<5T/qtr", "bull_threshold": ">9T/qtr", "check_frequency": "Quarterly", "data_source": "SK Hynix", "added_from": "Step 5b"},
        {"name": "SEMI WFE CY27 ($B)", "current_value": "$135.2", "bear_threshold": ">5% downrev.", "bull_threshold": ">5% up rev.", "check_frequency": "Semiannual", "data_source": "SEMI", "added_from": "Step 5b"},
        {"name": "Intel 14A timeline", "current_value": "2027 (risk 2028)", "bear_threshold": "Delay to 2029+", "bull_threshold": "On track 2027", "check_frequency": "Quarterly", "data_source": "Intel", "added_from": "Step 5b"},
        {"name": "Samsung 1d EUV layers", "current_value": "Curtailed", "bear_threshold": "\u22645 layers", "bull_threshold": "\u22658 layers", "check_frequency": "Semiannual", "data_source": "Samsung", "added_from": "Step 5b"},
        {"name": "KLA Investor Day outcome", "current_value": "Pending Mar 12", "bear_threshold": "Actinic EUV announced", "bull_threshold": "No progress", "check_frequency": "Event", "data_source": "KLA", "added_from": "Step 7"},
        {"name": "Custom ASIC mask orders", "current_value": "Not yet tracked", "bear_threshold": "N/A", "bull_threshold": "Explicit mention", "check_frequency": "Quarterly", "data_source": "Lasertec", "added_from": "Step 7"},
        {"name": "CNT pellicle DRAM adoption", "current_value": "Not confirmed", "bear_threshold": "N/A", "bull_threshold": "SK Hynix/Samsung confirm", "check_frequency": "Semiannual", "data_source": "Industry", "added_from": "Step 7"},
        {"name": "Mask shop vs. fab ACTIS split", "current_value": "Not disclosed", "bear_threshold": "Mask shop only", "bull_threshold": "Fab > mask shop", "check_frequency": "Quarterly", "data_source": "Lasertec", "added_from": "Step 7"},
        {"name": "EUV concentration %", "current_value": "~85%", "bear_threshold": "Declining", "bull_threshold": "Rising above 90%", "check_frequency": "Quarterly", "data_source": "Computed", "added_from": "Step 7"},
    ],
}


async def seed():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        for dataset in [JHX, LASERTEC]:
            c = dataset["company"]

            # Check if already seeded
            existing = await db.execute_fetchall(
                "SELECT id FROM companies WHERE ticker = ? AND exchange = ?",
                (c["ticker"], c.get("exchange")),
            )
            if existing:
                print(f"  {c['ticker']} already exists (id={existing[0][0]}), skipping.")
                continue

            cursor = await db.execute(
                """INSERT INTO companies (name, ticker, exchange, currency, current_rating,
                   current_price, blended_price_target, price_updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (c["name"], c["ticker"], c["exchange"], c["currency"],
                 c["current_rating"], c["current_price"], c["blended_price_target"]),
            )
            company_id = cursor.lastrowid
            print(f"  Created {c['name']} (id={company_id})")

            # Record initial price
            await db.execute(
                "INSERT INTO price_history (company_id, price, recorded_at) VALUES (?, ?, datetime('now'))",
                (company_id, c["current_price"]),
            )

            # Scenarios
            for s in dataset["scenarios"]:
                contribution = (s.get("effective_weight") or 0) * s["implied_price"]
                await db.execute(
                    """INSERT INTO scenarios (company_id, name, raw_weight, effective_weight,
                       implied_price, contribution, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (company_id, s["name"], s["raw_weight"], s["effective_weight"],
                     s["implied_price"], contribution, s["sort_order"]),
                )
            print(f"    Added {len(dataset['scenarios'])} scenarios")

            # Indicators
            for ind in dataset["indicators"]:
                await db.execute(
                    """INSERT INTO indicators (company_id, name, current_value,
                       bear_threshold, bull_threshold, check_frequency, data_source, added_from)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (company_id, ind["name"], ind["current_value"],
                     ind["bear_threshold"], ind["bull_threshold"],
                     ind["check_frequency"], ind["data_source"], ind["added_from"]),
                )
            print(f"    Added {len(dataset['indicators'])} indicators")

            # Check for rating alerts
            from services.rating_logic import compute_suggested_rating, rating_divergence
            suggested = compute_suggested_rating(c["current_price"], c["blended_price_target"])
            div = rating_divergence(c["current_rating"], suggested)
            if div:
                await db.execute(
                    """INSERT INTO alerts (company_id, tier, category, title, description, suggested_action)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (company_id, div["tier"], div["category"], div["title"],
                     div["description"], div["suggested_action"]),
                )
                print(f"    Generated {div['tier']} alert: {div['title']}")
            else:
                print(f"    No rating divergence (current={c['current_rating']}, suggested={suggested})")

        await db.commit()
    print("\nSeed complete!")


if __name__ == "__main__":
    print("Seeding database...")
    asyncio.run(seed())
