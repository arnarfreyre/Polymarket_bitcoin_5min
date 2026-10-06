"""Load 1-second BTCUSDT spot klines from Binance into bitcoin_prices.

Usage (from this folder, with this folder's .venv):
    .venv/bin/python load_bitcoin_prices.py                        # uses START_DATE / END_DATE below
    .venv/bin/python load_bitcoin_prices.py 2026-06-01 2026-08-01  # or pass them on the command line
    .venv/bin/python load_bitcoin_prices.py 2026-06-01 2026-08-01 --out DIR
                                     # write one Parquet file per day to DIR instead of the DB
                                     # (used by ../populate_bitcoin_5m.py, which does the insert)

Both dates are inclusive (UTC days). The range is fetched one day at a time (86,400 rows), so at
most one day is in memory. Each day is deleted before it is inserted, so re-running a range
doesn't duplicate rows.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
from binance_vision import fetch_data

START_DATE = '2026-08-01'
END_DATE = '2026-09-22'

DB_PATH = "/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb"
TICKER = "BTCUSDT"
COLUMNS = [
    "open_time", "close_time", "open", "high", "low", "close", "volume",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def day_chunks(start: date, end: date):
    """Yield (chunk_start, chunk_end) pairs, inclusive, one per UTC day."""
    cur = start
    while cur <= end:
        yield cur, cur
        cur += timedelta(days=1)


def fetch_days(start: date, end: date):
    """Yield (chunk_start, chunk_end, df) per day that has data."""
    for chunk_start, chunk_end in day_chunks(start, end):
        res = fetch_data(ticker=TICKER, start_date=chunk_start, end_date=chunk_end,
                         market="spot", data_type="klines", interval="1s")
        df = res.data
        if res.missing or res.failed:
            print(f"  warning: missing={res.missing} failed={res.failed}")
        if df is None or df.empty:
            print(f"{chunk_start} .. {chunk_end}: no data")
            continue
        yield chunk_start, chunk_end, df[COLUMNS]


def dump(start: date, end: date, out_dir: Path) -> None:
    """Write each day to out_dir/<day>.parquet, without touching the DB."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for chunk_start, chunk_end, df in fetch_days(start, end):
        df.columns = [c.upper() for c in COLUMNS]
        df.to_parquet(out_dir / f"{chunk_start}.parquet", index=False)
        print(f"{chunk_start} .. {chunk_end}: fetched {len(df):,} rows")


def load(start: date, end: date) -> None:
    con = duckdb.connect(DB_PATH)
    try:
        for chunk_start, chunk_end, df in fetch_days(start, end):
            con.execute("BEGIN")
            con.execute(
                "DELETE FROM bitcoin_prices WHERE OPEN_TIME >= ? AND OPEN_TIME < ?",
                [pd.Timestamp(chunk_start, tz="UTC"), pd.Timestamp(chunk_end + timedelta(days=1), tz="UTC")],
            )
            con.execute(f"INSERT INTO bitcoin_prices ({', '.join(c.upper() for c in COLUMNS)}) "
                        f"SELECT * FROM df")
            con.execute("COMMIT")
            print(f"{chunk_start} .. {chunk_end}: inserted {len(df):,} rows")

        total = con.execute("SELECT count(*) FROM bitcoin_prices").fetchone()[0]
        print(f"\nbitcoin_prices now has {total:,} rows")
    finally:
        con.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    out_dir = None
    if "--out" in args:
        i = args.index("--out")
        out_dir = Path(args[i + 1])
        del args[i:i + 2]
    start_arg, end_arg = args if len(args) == 2 else (START_DATE, END_DATE)
    start, end = date.fromisoformat(start_arg), date.fromisoformat(end_arg)
    if out_dir:
        dump(start, end, out_dir)
    else:
        load(start, end)
