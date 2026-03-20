import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "monitoring.db")


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(SCHEMA_SQL)
        await db.commit()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    exchange TEXT,
    currency TEXT NOT NULL,
    current_rating TEXT NOT NULL,
    current_price REAL,
    price_updated_at TEXT,
    blended_price_target REAL NOT NULL,
    scenario_doc_path TEXT,
    scenario_doc_uploaded_at TEXT,
    last_full_assessment_at TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    raw_weight REAL,
    effective_weight REAL,
    implied_price REAL NOT NULL,
    contribution REAL,
    fy_revenue TEXT,
    fy_ebitda TEXT,
    fy_eps TEXT,
    fy_fcf TEXT,
    narrative_summary TEXT,
    trigger_conditions TEXT,
    sort_order INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    current_value TEXT,
    current_value_numeric REAL,
    bear_threshold TEXT,
    bear_threshold_numeric REAL,
    bull_threshold TEXT,
    bull_threshold_numeric REAL,
    check_frequency TEXT NOT NULL,
    data_source TEXT NOT NULL,
    added_from TEXT,
    is_shared INTEGER DEFAULT 0,
    shared_indicator_group TEXT,
    last_checked_at TEXT,
    next_check_due TEXT,
    status TEXT DEFAULT 'green',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS indicator_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_id INTEGER NOT NULL REFERENCES indicators(id) ON DELETE CASCADE,
    value_text TEXT NOT NULL,
    value_numeric REAL,
    source_url TEXT,
    source_snippet TEXT,
    checked_at TEXT NOT NULL,
    status_at_reading TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    indicator_id INTEGER,
    tier TEXT NOT NULL CHECK(tier IN ('red', 'amber', 'green')),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    affected_scenario TEXT,
    suggested_action TEXT,
    is_active INTEGER DEFAULT 1,
    acknowledged_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    assessment_type TEXT NOT NULL,
    content TEXT NOT NULL,
    indicator_summary TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    price REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scenarios_company ON scenarios(company_id);
CREATE INDEX IF NOT EXISTS idx_indicators_company ON indicators(company_id);
CREATE INDEX IF NOT EXISTS idx_indicator_readings_indicator ON indicator_readings(indicator_id);
CREATE INDEX IF NOT EXISTS idx_alerts_company ON alerts(company_id);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(is_active);
CREATE INDEX IF NOT EXISTS idx_assessments_company ON assessments(company_id);
CREATE INDEX IF NOT EXISTS idx_price_history_company ON price_history(company_id);
"""
