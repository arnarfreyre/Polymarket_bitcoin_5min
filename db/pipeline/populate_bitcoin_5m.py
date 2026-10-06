"""Load Polymarket "Bitcoin Up or Down" 5-minute markets, their trades and/or 1s BTCUSDT prices
into the raw tables.

Set the config below and run the file. For each selected table the date range is deleted first,
so re-running a range never duplicates rows. Indexes on the Polymarket tables are dropped before
loading and rebuilt from db/schema/indexes/*.sql afterwards (also if the load fails).

After a successful load the derived tables in DERIVED are rebuilt from the raw tables.

bitcoin_prices comes from Binance via "bitcoin 1s/load_bitcoin_prices.py", which needs that
folder's own .venv. It runs as a subprocess while the Polymarket data downloads, fetching one day
at a time and writing one Parquet file per day to a temp dir (only one process can write to the
DuckDB file); this script inserts them at the end, one day per insert.
"""
import json
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import requests

# ---- config ------------------------------------------------------------------------------------
DATE_START = "2026-08-01"   # UTC, inclusive
DATE_END = "2026-09-27"     # UTC, inclusive
TABLES = [
    "bitcoin_prices",
    "bitcoin_5m_markets",
    "bitcoin_5m_trades",
]



#TABLES = ["bitcoin_5m_markets","bitcoin_5m_trades",]

# derived tables rebuilt after the load: db/schema/ddl/tables/<name>.sql, then db/schema/tables/<name>.sql
DERIVED = ["positions", "market_prices"]

N_MARKETS = 100   # markets per trades insert
N_RUNNERS = 16     # parallel API requests
MEMORY_LIMIT = "6GB"   # DuckDB's cap for this run (its default is 80 % of RAM); the derived-table rebuild spills to disk beyond it
THREADS = 6            # DuckDB threads (its default is every core): the derived-table rebuild would otherwise max the CPU
# ------------------------------------------------------------------------------------------------

ROOT = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min")
DB_PATH = str(ROOT / "db/polymarket.duckdb")
SCHEMA_DIR = ROOT / "db/schema"
IDX_DIR = SCHEMA_DIR / "indexes"
GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"
DATA_TRADES = "https://data-api.polymarket.com/trades"
PAGE = 1000          # max trades per request
MAX_OFFSET = 10000   # Data API refuses offsets above this
_local = threading.local()  # one requests.Session per worker thread
MARKETS_TMP = f"{tempfile.gettempdir()}/bitcoin_5m_markets_batch.json"
TRADES_TMP = f"{tempfile.gettempdir()}/bitcoin_5m_trades_batch.json"
RAW_TABLES = ("bitcoin_5m_markets", "bitcoin_5m_trades", "bitcoin_prices")
PRICES_DIR = ROOT / "db/pipeline/bitcoin 1s"
PRICES_PYTHON = PRICES_DIR / ".venv/bin/python"
PRICES_SCRIPT = PRICES_DIR / "load_bitcoin_prices.py"

# markets: table column -> type (rows are flattened to these keys by flatten_market)
MARKET_COLUMNS = {
    "MARKET_ID": "VARCHAR", "CONDITION_ID": "VARCHAR", "QUESTION_ID": "VARCHAR", "SLUG": "VARCHAR",
    "EVENT_ID": "VARCHAR", "EVENT_SLUG": "VARCHAR", "QUESTION": "VARCHAR", "RESOLUTION_SOURCE": "VARCHAR",
    "EVENT_START_TIME": "TIMESTAMPTZ", "END_DATE": "TIMESTAMPTZ", "START_DATE": "TIMESTAMPTZ",
    "CREATED_AT": "TIMESTAMPTZ", "CLOSED_TIME": "TIMESTAMPTZ", "UMA_END_DATE": "TIMESTAMPTZ",
    "UP_TOKEN_ID": "VARCHAR", "DOWN_TOKEN_ID": "VARCHAR",
    "UP_PRICE": "DOUBLE", "DOWN_PRICE": "DOUBLE", "RESULT": "VARCHAR",
    "UMA_RESOLUTION_STATUS": "VARCHAR", "AUTOMATICALLY_RESOLVED": "BOOLEAN",
    "ACTIVE": "BOOLEAN", "CLOSED": "BOOLEAN",
    "VOLUME": "DOUBLE", "LAST_TRADE_PRICE": "DOUBLE",
    "ORDER_PRICE_MIN_TICK_SIZE": "DOUBLE", "ORDER_MIN_SIZE": "DOUBLE",
    "FEES_ENABLED": "BOOLEAN", "FEE_TYPE": "VARCHAR", "FEE_RATE": "DOUBLE", "FEE_EXPONENT": "DOUBLE",
    "FEE_TAKER_ONLY": "BOOLEAN", "FEE_REBATE_RATE": "DOUBLE",
    "MAKER_BASE_FEE": "INTEGER", "TAKER_BASE_FEE": "INTEGER",
}
MARKETS_INSERT = (
    f"INSERT INTO bitcoin_5m_markets ({', '.join(MARKET_COLUMNS)}) "
    f"SELECT {', '.join(MARKET_COLUMNS)} "
    f"FROM read_json('{MARKETS_TMP}', format = 'array', columns = "
    f"{{{', '.join(f'{c}: {t!r}' for c, t in MARKET_COLUMNS.items())}}})"
)

# trades: API field -> (table column, type)
TRADE_FIELDS = {
    "conditionId": ("CONDITION_ID", "VARCHAR"), "slug": ("SLUG", "VARCHAR"),
    "eventSlug": ("EVENT_SLUG", "VARCHAR"), "title": ("TITLE", "VARCHAR"), "icon": ("ICON", "VARCHAR"),
    "timestamp": ("TIMESTAMP", "BIGINT"), "side": ("SIDE", "VARCHAR"), "outcome": ("OUTCOME", "VARCHAR"),
    "outcomeIndex": ("OUTCOME_INDEX", "INTEGER"), "asset": ("ASSET", "VARCHAR"),
    "price": ("PRICE", "DOUBLE"), "size": ("SIZE", "DOUBLE"),
    "transactionHash": ("TRANSACTION_HASH", "VARCHAR"), "proxyWallet": ("PROXY_WALLET", "VARCHAR"),
    "name": ("NAME", "VARCHAR"), "pseudonym": ("PSEUDONYM", "VARCHAR"), "bio": ("BIO", "VARCHAR"),
    "profileImage": ("PROFILE_IMAGE", "VARCHAR"),
    "profileImageOptimized": ("PROFILE_IMAGE_OPTIMIZED", "VARCHAR"),
}
# Rows are written to a temp JSON file and bulk-loaded from it
# (passing rows as Python parameters is ~1000 rows/s, far too slow).
TRADES_INSERT = (
    f"INSERT INTO bitcoin_5m_trades ({', '.join(col for col, _ in TRADE_FIELDS.values())}) "
    f"SELECT {', '.join(f'to_timestamp({k})' if k == 'timestamp' else k for k in TRADE_FIELDS)} "
    f"FROM read_json('{TRADES_TMP}', format = 'array', columns = "
    f"{{{', '.join(f'{k}: {t!r}' for k, (_, t) in TRADE_FIELDS.items())}}})"
)


def get_session():
    """Return this thread's requests.Session (Session isn't guaranteed thread-safe)."""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def get_json(url, params):
    """GET with retries; backs off on rate limits (429) and errors."""
    for attempt in range(8):
        try:
            resp = get_session().get(url, params=params, timeout=30)
            if resp.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests")
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == 7:
                raise
            time.sleep(min(2 ** attempt, 30))


def gamma_batch(slugs):
    params = [("closed", "true"), ("limit", len(slugs))] + [("slug", s) for s in slugs]
    return get_json(GAMMA_MARKETS, params)


def day_markets(pool, day):
    """Return the Gamma market objects for the 288 five-minute markets of a UTC day."""
    first = int(day.timestamp())
    slugs = [f"btc-updown-5m-{first + k * 300}" for k in range(288)]
    batches = [slugs[j:j + 50] for j in range(0, len(slugs), 50)]
    markets = [m for batch in pool.map(gamma_batch, batches) for m in batch]
    return sorted(markets, key=lambda m: m["slug"])


def flatten_market(m):
    """Gamma market object -> one table row (JSON-string fields split into columns)."""
    outcomes = json.loads(m.get("outcomes") or "[]")
    prices = [float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
    tokens = json.loads(m.get("clobTokenIds") or "[]")
    up, down = outcomes.index("Up"), outcomes.index("Down")
    event = (m.get("events") or [{}])[0]
    fees = m.get("feeSchedule") or {}
    return {
        "MARKET_ID": m.get("id"), "CONDITION_ID": m["conditionId"], "QUESTION_ID": m.get("questionID"),
        "SLUG": m["slug"], "EVENT_ID": event.get("id"), "EVENT_SLUG": event.get("slug"),
        "QUESTION": m.get("question"), "RESOLUTION_SOURCE": m.get("resolutionSource"),
        "EVENT_START_TIME": m.get("eventStartTime"), "END_DATE": m.get("endDate"),
        "START_DATE": m.get("startDate"), "CREATED_AT": m.get("createdAt"),
        "CLOSED_TIME": m.get("closedTime"), "UMA_END_DATE": m.get("umaEndDate"),
        "UP_TOKEN_ID": tokens[up] if tokens else None, "DOWN_TOKEN_ID": tokens[down] if tokens else None,
        "UP_PRICE": prices[up] if prices else None, "DOWN_PRICE": prices[down] if prices else None,
        "RESULT": outcomes[prices.index(1.0)] if 1.0 in prices else None,
        "UMA_RESOLUTION_STATUS": m.get("umaResolutionStatus"),
        "AUTOMATICALLY_RESOLVED": m.get("automaticallyResolved"),
        "ACTIVE": m.get("active"), "CLOSED": m.get("closed"),
        "VOLUME": m.get("volumeNum"), "LAST_TRADE_PRICE": m.get("lastTradePrice"),
        "ORDER_PRICE_MIN_TICK_SIZE": m.get("orderPriceMinTickSize"), "ORDER_MIN_SIZE": m.get("orderMinSize"),
        "FEES_ENABLED": m.get("feesEnabled"), "FEE_TYPE": m.get("feeType"),
        "FEE_RATE": fees.get("rate"), "FEE_EXPONENT": fees.get("exponent"),
        "FEE_TAKER_ONLY": fees.get("takerOnly"), "FEE_REBATE_RATE": fees.get("rebateRate"),
        "MAKER_BASE_FEE": m.get("makerBaseFee"), "TAKER_BASE_FEE": m.get("takerBaseFee"),
    }


def market_trades(slug, condition_id):
    """Page through all taker trades of one market."""
    trades, offset = [], 0
    while offset <= MAX_OFFSET:
        page = get_json(DATA_TRADES, {"market": condition_id, "takerOnly": "true",
                                      "limit": PAGE, "offset": offset})
        trades += page
        if len(page) < PAGE:
            return trades
        offset += PAGE
    print(f"  WARNING {slug}: hit the API offset cap, only {len(trades)} trades loaded")
    return trades


def bulk_insert(con, rows, tmp_file, insert_sql):
    """Write rows to a temp JSON file and load them with one INSERT."""
    if rows:
        with open(tmp_file, "w") as f:
            json.dump(rows, f)
        con.execute(insert_sql)


def drop_indexes(con, tables):
    """Drop every index on the given tables (inserts are much faster without them)."""
    names = [n for (n,) in con.execute(
        "SELECT index_name FROM duckdb_indexes() WHERE table_name IN ?", [list(tables)]).fetchall()]
    for name in names:
        con.execute(f"DROP INDEX IF EXISTS {name}")
    print(f"dropped indexes: {', '.join(names) or '(none)'}")


def create_indexes(con):
    """Create the indexes in db/schema/indexes/*.sql (CREATE INDEX IF NOT EXISTS)."""
    for path in sorted(IDX_DIR.glob("*.sql")):
        t = time.time()
        con.execute(path.read_text())
        print(f"built {path.stem} in {fmt(time.time() - t)}")


def start_prices_fetch(out_dir):
    """Start load_bitcoin_prices.py in its own venv, writing Parquet files to out_dir."""
    return subprocess.Popen([str(PRICES_PYTHON), str(PRICES_SCRIPT), DATE_START, DATE_END,
                             "--out", str(out_dir)], cwd=PRICES_DIR)


def insert_prices(con, proc, out_dir, start, end):
    """Wait for the prices subprocess, then replace the date range in bitcoin_prices one day at a time:
    each day is its own delete + insert of that day's Parquet file (86,400 rows), never the whole range."""
    if proc.poll() is None:
        print("waiting for the bitcoin prices download...")
    if proc.wait() != 0:
        raise RuntimeError(f"load_bitcoin_prices.py failed (exit code {proc.returncode})")
    deleted = inserted = 0
    day = start
    while day <= end:
        path = out_dir / f"{day:%Y-%m-%d}.parquet"
        con.execute("BEGIN")
        d = con.execute("DELETE FROM bitcoin_prices WHERE OPEN_TIME >= to_timestamp(?) AND OPEN_TIME < to_timestamp(?)",
                        [day.timestamp(), (day + timedelta(days=1)).timestamp()]).fetchone()[0]
        n = 0
        if path.exists():
            n = con.execute("INSERT INTO bitcoin_prices BY NAME SELECT * FROM read_parquet(?)",
                            [str(path)]).fetchone()[0]
        con.execute("COMMIT")
        print(f"bitcoin_prices {day:%Y-%m-%d}: deleted {d}, inserted {n} rows")
        deleted, inserted = deleted + d, inserted + n
        day += timedelta(days=1)
    print(f"bitcoin_prices: deleted {deleted}, inserted {inserted} rows")


def rebuild_derived(con):
    """Drop, recreate and refill each table in DERIVED."""
    for name in DERIVED:
        t = time.time()
        con.execute((SCHEMA_DIR / "ddl/tables" / f"{name}.sql").read_text())
        con.execute((SCHEMA_DIR / "tables" / f"{name}.sql").read_text())
        n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        print(f"rebuilt {name}: {n} rows in {fmt(time.time() - t)}")


def fmt(seconds):
    return str(timedelta(seconds=int(seconds)))


def main():
    unknown = set(TABLES) - set(RAW_TABLES)
    if unknown or not TABLES:
        raise SystemExit(f"TABLES must be a non-empty subset of {RAW_TABLES}, got {TABLES}")
    pm_tables = [t for t in TABLES if t != "bitcoin_prices"]

    start = datetime.fromisoformat(DATE_START).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(DATE_END).replace(tzinfo=timezone.utc)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    print(f"loading {', '.join(TABLES)} for {DATE_START} to {DATE_END} ({len(days)} days)")

    t0 = time.time()
    # Start the Binance download first so it runs while the Polymarket data downloads.
    prices_dir = Path(tempfile.mkdtemp(prefix="bitcoin_prices_"))
    prices_proc = start_prices_fetch(prices_dir) if "bitcoin_prices" in TABLES else None
    con = duckdb.connect(DB_PATH)
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"SET threads = {THREADS}")
    try:
        if pm_tables:
            load_polymarket(con, pm_tables, days, t0)
        if prices_proc:
            insert_prices(con, prices_proc, prices_dir, start, end)
        rebuild_derived(con)
    finally:
        if prices_proc and prices_proc.poll() is None:
            prices_proc.kill()
        shutil.rmtree(prices_dir, ignore_errors=True)
        for table in TABLES:
            print(f"{table}: {con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]} rows total")
        con.close()
        print(f"=== done in {fmt(time.time() - t0)}")


def load_polymarket(con, tables, days, t0):
    """Replace the markets and/or trades of the given days (dropping and rebuilding indexes)."""
    # Days are UTC, 288 markets each. Markets are always fetched from Gamma (the trades need
    # their condition ids) but only inserted if bitcoin_5m_markets is selected.
    load_markets = "bitcoin_5m_markets" in tables
    load_trades = "bitcoin_5m_trades" in tables
    start, end = days[0], days[-1]
    total_markets = len(days) * 288
    done = 0
    try:
        drop_indexes(con, tables)

        # Delete the whole date range up front, so re-running never duplicates rows.
        # Slugs compare correctly as text since the unix timestamps all have the same length.
        first_slug = f"btc-updown-5m-{int(start.timestamp())}"
        after_last_slug = f"btc-updown-5m-{int((end + timedelta(days=1)).timestamp())}"
        for table in tables:
            deleted = con.execute(f"DELETE FROM {table} WHERE SLUG >= ? AND SLUG < ?",
                                  [first_slug, after_last_slug]).fetchone()[0]
            print(f"deleted {deleted} existing {table} rows")

        # API calls run N_RUNNERS at a time in worker threads; all DuckDB writes stay on this thread.
        with ThreadPoolExecutor(N_RUNNERS) as pool:
            for i, day in enumerate(days, 1):
                tag = f"[day {i}/{len(days)}] {day:%Y-%m-%d}"
                markets = day_markets(pool, day)
                if load_markets:
                    bulk_insert(con, [flatten_market(m) for m in markets], MARKETS_TMP, MARKETS_INSERT)
                print(f"{tag} | markets: {len(markets)}/288")

                if not load_trades:
                    done += 288
                    continue
                day_rows = 0
                ids = [(m["slug"], m["conditionId"]) for m in markets]
                for j in range(0, len(ids), N_MARKETS):
                    batch = ids[j:j + N_MARKETS]
                    trades = [t for market in pool.map(lambda m: market_trades(*m), batch) for t in market]
                    bulk_insert(con, trades, TRADES_TMP, TRADES_INSERT)
                    day_rows += len(trades)

                    done += len(batch)
                    elapsed = time.time() - t0
                    eta = elapsed / done * (total_markets - done)
                    print(f"{tag} | trades for markets {j + len(batch)}/{len(ids)} | rows: {len(trades)} | "
                          f"elapsed {fmt(elapsed)} | ETA {fmt(eta)}")
                done += 288 - len(ids)  # keeps the ETA right on days with missing markets
                print(f"{tag} | done, {day_rows} trades")
    finally:
        # Rebuild the indexes even if the load failed or was interrupted.
        print("building indexes...")
        create_indexes(con)


if __name__ == "__main__":
    main()
