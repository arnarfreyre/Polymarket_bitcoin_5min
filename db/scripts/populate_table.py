import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DB_PATH = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb")
sql_path = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/schema/tables/market_trades.sql")
TABLE = "MARKET_TRADES"

# MacBook Pro: 11 cores, 18 GB RAM. Leave headroom for macOS and other apps.
threads = 6
memory_limit = "10GB"  # DuckDB spills the sort / join to temp_dir beyond this
temp_dir = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/tmp_duckdb")
max_temp_dir_size = "80GB"  # disk is 111 GB free; cap the spill

temp_dir.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(DB_PATH))
sql = sql_path.read_text()

try:
    try:
        con.execute(f"SET threads = {threads}")
        con.execute(f"SET memory_limit = '{memory_limit}'")
        con.execute(f"SET temp_directory = '{temp_dir}'")
        con.execute(f"SET max_temp_directory_size = '{max_temp_dir_size}'")
        con.execute("SET preserve_insertion_order = true")  # keep the final ORDER BY on disk

        existing = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        if existing:
            raise RuntimeError(
                f"{TABLE} already has {existing:,} rows; a second run would duplicate them. "
                f"Run `DELETE FROM {TABLE}` first if you want to reload."
            )

        print(f"Populating {TABLE} (threads={threads}, memory_limit={memory_limit}, temp={temp_dir}) ...")
        t0 = time.time()
        con.execute(sql)
        print(f"Execution successful in {time.time() - t0:.0f} s")

        rows = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        expected = con.execute(
            "SELECT count(*) FROM btc_trades t JOIN btc_summary s ON s.SLUG = t.SLUG"
        ).fetchone()[0]
        print(f"{TABLE} rows: {rows:,} (expected {expected:,})")

    except Exception as e:
        print(f"Execution not successful \n {e}")
finally:
    con.close()
