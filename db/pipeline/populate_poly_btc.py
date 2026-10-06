"""Load Polymarket "Bitcoin Up or Down" 5-minute windows into the raw tables btc_summary, btc_trades
and btc_history (one window = what pm_window.py fetches: Gamma summary, Data API trades, CLOB price history).

Set the config below and run the file. With RELOAD the date range is deleted from the three tables first; without
it only the markets not in btc_summary yet are fetched (so a stopped run picks up where it left off). Either way
re-running a range never duplicates rows.

For each UTC day, its 288 windows are fetched N_RUNNERS at a time (each window: its Gamma event, its trades paged
until an empty page, the price history of each token), then the day is inserted.
"""
import json
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import requests

# ---- config ------------------------------------------------------------------------------------
DATE_START = "2026-03-01"   # UTC, inclusive
DATE_END = "2026-05-31"     # UTC, inclusive
N_RUNNERS = 8               # windows fetched in parallel
RELOAD = False              # True: delete the range and fetch it all again; False: fetch only markets not loaded yet
# ------------------------------------------------------------------------------------------------

ROOT = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min")
DB_PATH = str(ROOT / "db/polymarket.duckdb")
GAMMA = "https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{}"
TRADES = "https://data-api.polymarket.com/trades"
HISTORY = "https://clob.polymarket.com/prices-history"
_local = threading.local()  # one requests.Session per worker thread

def snake(key):
    """API camelCase key -> UPPER_SNAKE column name."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key).upper()


# Every field of the Gamma event (EVENT_ prefix) and of its market object (no prefix), as
# (API key, type[, column name when it isn't snake(key)]). Nested objects / lists that stay whole are JSON.
MARKET_FIELDS = [
    ("id", "VARCHAR", "MARKET_ID"), ("question", "VARCHAR"), ("conditionId", "VARCHAR"),
    ("questionID", "VARCHAR"), ("slug", "VARCHAR"), ("description", "VARCHAR"), ("image", "VARCHAR"),
    ("icon", "VARCHAR"), ("resolutionSource", "VARCHAR"), ("marketMakerAddress", "VARCHAR"),
    ("comboStatus", "VARCHAR"), ("groupItemThreshold", "DOUBLE"),
    # time
    ("eventStartTime", "TIMESTAMPTZ"), ("endDate", "TIMESTAMPTZ"), ("startDate", "TIMESTAMPTZ"),
    ("endDateIso", "DATE"), ("startDateIso", "DATE"), ("createdAt", "TIMESTAMPTZ"),
    ("updatedAt", "TIMESTAMPTZ"), ("closedTime", "TIMESTAMPTZ"), ("umaEndDate", "TIMESTAMPTZ"),
    ("acceptingOrdersTimestamp", "TIMESTAMPTZ"),
    # outcomes / resolution (the JSON-string fields are kept as they come)
    ("outcomes", "VARCHAR"), ("outcomePrices", "VARCHAR"), ("clobTokenIds", "VARCHAR"),
    ("umaResolutionStatus", "VARCHAR"), ("umaResolutionStatuses", "VARCHAR"),
    ("automaticallyResolved", "BOOLEAN"), ("automaticallyActive", "BOOLEAN"), ("manualActivation", "BOOLEAN"),
    # status
    ("active", "BOOLEAN"), ("closed", "BOOLEAN"), ("archived", "BOOLEAN"), ("new", "BOOLEAN"),
    ("featured", "BOOLEAN"), ("restricted", "BOOLEAN"), ("approved", "BOOLEAN"), ("ready", "BOOLEAN"),
    ("funded", "BOOLEAN"), ("hasReviewedDates", "BOOLEAN"), ("acceptingOrders", "BOOLEAN"),
    ("enableOrderBook", "BOOLEAN"), ("clearBookOnStart", "BOOLEAN"), ("pendingDeployment", "BOOLEAN"),
    ("deploying", "BOOLEAN"), ("cyom", "BOOLEAN"), ("rfqEnabled", "BOOLEAN"),
    ("pagerDutyNotificationEnabled", "BOOLEAN"), ("showGmpSeries", "BOOLEAN"), ("showGmpOutcome", "BOOLEAN"),
    ("negRisk", "BOOLEAN"), ("negRiskOther", "BOOLEAN"), ("holdingRewardsEnabled", "BOOLEAN"),
    # trading
    ("volume", "DOUBLE"), ("volumeNum", "DOUBLE"), ("volumeClob", "DOUBLE"),
    ("liquidity", "DOUBLE"), ("liquidityNum", "DOUBLE"), ("liquidityAmm", "DOUBLE"), ("liquidityClob", "DOUBLE"),
    ("competitive", "DOUBLE"), ("lastTradePrice", "DOUBLE"), ("bestBid", "DOUBLE"), ("bestAsk", "DOUBLE"),
    ("spread", "DOUBLE"), ("oneHourPriceChange", "DOUBLE"), ("oneDayPriceChange", "DOUBLE"),
    ("orderPriceMinTickSize", "DOUBLE"), ("orderMinSize", "DOUBLE"),
    ("rewardsMinSize", "DOUBLE"), ("rewardsMaxSpread", "DOUBLE"),
    # fees
    ("feesEnabled", "BOOLEAN"), ("feeType", "VARCHAR"), ("makerBaseFee", "INTEGER"), ("takerBaseFee", "INTEGER"),
    ("makerRebatesFeeShareBps", "INTEGER"), ("cryptoMarketConfigId", "VARCHAR"), ("version", "VARCHAR"),
]
EVENT_FIELDS = [
    ("id", "VARCHAR"), ("ticker", "VARCHAR"), ("slug", "VARCHAR"), ("description", "VARCHAR"),
    ("resolutionSource", "VARCHAR"), ("image", "VARCHAR"), ("icon", "VARCHAR"), ("seriesSlug", "VARCHAR"),
    ("startTime", "TIMESTAMPTZ", "EVENT_STARTTIME"), ("startDate", "TIMESTAMPTZ"),
    ("creationDate", "TIMESTAMPTZ"), ("endDate", "TIMESTAMPTZ"), ("createdAt", "TIMESTAMPTZ"),
    ("updatedAt", "TIMESTAMPTZ"), ("closedTime", "TIMESTAMPTZ"),
    ("active", "BOOLEAN"), ("closed", "BOOLEAN"), ("archived", "BOOLEAN"), ("new", "BOOLEAN"),
    ("featured", "BOOLEAN"), ("restricted", "BOOLEAN"), ("enableOrderBook", "BOOLEAN"),
    ("automaticallyResolved", "BOOLEAN"), ("automaticallyActive", "BOOLEAN"), ("cyom", "BOOLEAN"),
    ("showAllOutcomes", "BOOLEAN"), ("showMarketImages", "BOOLEAN"), ("negRisk", "BOOLEAN"),
    ("enableNegRisk", "BOOLEAN"), ("negRiskAugmented", "BOOLEAN"), ("pendingDeployment", "BOOLEAN"),
    ("deploying", "BOOLEAN"),
    ("volume", "DOUBLE"), ("liquidity", "DOUBLE"), ("liquidityAmm", "DOUBLE"), ("liquidityClob", "DOUBLE"),
    ("openInterest", "DOUBLE"), ("competitive", "DOUBLE"), ("commentCount", "INTEGER"),
    ("series", "JSON"), ("tags", "JSON"), ("eventMetadata", "JSON", "EVENT_METADATA"), ("version", "VARCHAR"),
]


def spec(fields, prefix=""):
    """[(API key, type[, column])] -> [(API key, type, column)]"""
    return [(f[0], f[1], f[2] if len(f) > 2 else prefix + snake(f[0])) for f in fields]


MARKET_SPEC = spec(MARKET_FIELDS)
EVENT_SPEC = spec(EVENT_FIELDS, "EVENT_")
# the first columns are the summary of pm_window.py, then the parts of the market's nested objects, then the two objects' fields
SUMMARY_FIRST = {
    "SLUG": "VARCHAR", "TITLE": "VARCHAR", "CONDITION_ID": "VARCHAR",
    "UP_TOKEN_ID": "VARCHAR", "DOWN_TOKEN_ID": "VARCHAR", "RESOLUTION_SOURCE": "VARCHAR",
    "START": "TIMESTAMPTZ", "END": "TIMESTAMPTZ", "TWAP_LOOKBACK_S": "INTEGER",
    "PRICE_TO_BEAT": "DOUBLE", "FINAL_PRICE": "DOUBLE", "MOVE_USD": "DOUBLE", "WINNER": "VARCHAR",
    "VOLUME": "DOUBLE", "N_TRADES": "INTEGER",
}
SUMMARY_NESTED = {
    "RESULT": "VARCHAR", "UP_PRICE": "DOUBLE", "DOWN_PRICE": "DOUBLE",
    "FEE_RATE": "DOUBLE", "FEE_EXPONENT": "DOUBLE", "FEE_TAKER_ONLY": "BOOLEAN", "FEE_REBATE_RATE": "DOUBLE",
    "CRYPTO_ASSET": "VARCHAR", "CRYPTO_DURATION": "VARCHAR", "TWAP_ENABLED": "BOOLEAN",
    "RAW_EVENT": "JSON",   # the whole Gamma event object (market included), so no field is ever lost
}


def summary_columns():
    cols = dict(SUMMARY_FIRST)
    cols.update(SUMMARY_NESTED)
    for _, t, col in MARKET_SPEC + EVENT_SPEC:
        if col in cols:   # SLUG, CONDITION_ID, RESOLUTION_SOURCE, VOLUME: the summary's own column is the same value
            continue
        cols[col] = t
    return cols


# table -> {column: type}. Rows are flattened to these keys by fetch_window and bulk-loaded from a temp
# JSON file (passing rows as Python parameters is ~1000 rows/s, far too slow).
COLUMNS = {
    "btc_summary": summary_columns(),
    "btc_trades": {
        "SLUG": "VARCHAR", "CONDITION_ID": "VARCHAR", "EVENT_SLUG": "VARCHAR", "TITLE": "VARCHAR",
        "ICON": "VARCHAR", "TIMESTAMP": "BIGINT", "SECS_INTO_WINDOW": "INTEGER", "SIDE": "VARCHAR",
        "OUTCOME": "VARCHAR", "OUTCOME_INDEX": "INTEGER", "ASSET": "VARCHAR", "PRICE": "DOUBLE",
        "SIZE": "DOUBLE", "TX": "VARCHAR", "WALLET": "VARCHAR", "NAME": "VARCHAR", "PSEUDONYM": "VARCHAR",
        "BIO": "VARCHAR", "PROFILE_IMAGE": "VARCHAR", "PROFILE_IMAGE_OPTIMIZED": "VARCHAR",
    },
    "btc_history": {
        "SLUG": "VARCHAR", "TOKEN_ID": "VARCHAR", "OUTCOME": "VARCHAR", "TIMESTAMP": "BIGINT", "PRICE": "DOUBLE",
    },
}


def insert_sql(table, path):
    """INSERT one table's rows from a newline-delimited JSON file. The unix-seconds TIMESTAMP columns are stored as
    TIMESTAMPTZ; "END" is a reserved word, so every name is quoted."""
    cols = COLUMNS[table]
    return (
        f"INSERT INTO {table} ({', '.join(f'\"{c}\"' for c in cols)}) "
        f"SELECT {', '.join('to_timestamp(TIMESTAMP)' if c == 'TIMESTAMP' else f'\"{c}\"' for c in cols)} "
        f"FROM read_json('{path}', format = 'newline_delimited', columns = "
        f"{{{', '.join(f'\"{c}\": {t!r}' for c, t in cols.items())}}})"
    )


def get_session():
    """Return this thread's requests.Session (Session isn't guaranteed thread-safe)."""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers["User-Agent"] = "populate-poly-btc/1.0"
    return _local.session


def get_json(url, params=None):
    """GET with retries; backs off on rate limits (429) and errors. Returns None on 400 / 404 (a retry won't help)."""
    for attempt in range(8):
        try:
            resp = get_session().get(url, params=params, timeout=30)
            if resp.status_code in (400, 404):
                return None
            if resp.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests")
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == 7:
                raise
            time.sleep(min(2 ** attempt, 30))


def value(obj, key, type_):
    """A field of an API object; numbers that come as strings ('18591.18') become floats."""
    v = (obj or {}).get(key)
    return float(v) if type_ == "DOUBLE" and isinstance(v, str) and v != "" else v


def fetch_window(ts):
    """The summary row, the trade rows and the price history rows of the window starting at unix time ts;
    None if the window has no market."""
    slug = f"btc-updown-5m-{ts}"

    # 1. Market metadata: strike, settlement, outcome, token ids
    ev = get_json(GAMMA.format(ts))
    if not ev or not ev.get("markets"):
        return None
    m = ev["markets"][0]
    meta = ev.get("eventMetadata") or {}
    fees = m.get("feeSchedule") or {}
    crypto = m.get("cryptoMarketConfig") or {}
    # windows Polymarket created but never opened have no outcomePrices (or tokens): they are stored as they are
    outcomes = json.loads(m.get("outcomes") or "[]")
    prices = json.loads(m.get("outcomePrices") or "[]")
    tokens = dict(zip(outcomes, json.loads(m.get("clobTokenIds") or "[]")))
    ptb, final = value(meta, "priceToBeat", "DOUBLE"), value(meta, "finalPrice", "DOUBLE")

    # 2. Every trade (Data API returns newest first; page with offset until an empty page)
    trades = []
    while page := get_json(TRADES, dict(market=m["conditionId"], limit=10000, offset=len(trades))):
        trades.extend(page)
    trades.sort(key=lambda t: t["timestamp"])

    # 3. Price history of each token, from an hour before the window to 5 minutes after it
    history = []
    for outcome, token in tokens.items():
        points = (get_json(HISTORY, dict(market=token, startTs=ts - 3600, endTs=ts + 600, fidelity=1))
                  or {}).get("history", [])
        history += [{"SLUG": slug, "TOKEN_ID": token, "OUTCOME": outcome, "TIMESTAMP": p["t"], "PRICE": p["p"]}
                    for p in points]
    history.sort(key=lambda r: (r["TIMESTAMP"], r["OUTCOME"]))

    summary = {
        "TITLE": ev.get("title"), "UP_TOKEN_ID": tokens.get("Up"), "DOWN_TOKEN_ID": tokens.get("Down"),
        "START": m.get("eventStartTime"), "END": m.get("endDate"),
        "TWAP_LOOKBACK_S": crypto.get("twapLookbackSeconds"),
        "PRICE_TO_BEAT": ptb, "FINAL_PRICE": final,
        "MOVE_USD": None if ptb is None or final is None else final - ptb,
        "WINNER": next((o for o, p in zip(outcomes, prices) if p == "1"), "unresolved"),
        "N_TRADES": len(trades),
        "RESULT": next((o for o, p in zip(outcomes, prices) if p == "1"), None),
        "UP_PRICE": float(prices[outcomes.index("Up")]) if "Up" in outcomes and prices else None,
        "DOWN_PRICE": float(prices[outcomes.index("Down")]) if "Down" in outcomes and prices else None,
        "FEE_RATE": fees.get("rate"), "FEE_EXPONENT": fees.get("exponent"),
        "FEE_TAKER_ONLY": fees.get("takerOnly"), "FEE_REBATE_RATE": fees.get("rebateRate"),
        "CRYPTO_ASSET": crypto.get("asset"), "CRYPTO_DURATION": crypto.get("duration"),
        "TWAP_ENABLED": crypto.get("twapEnabled"), "RAW_EVENT": ev,
    }
    for obj, fields in ((ev, EVENT_SPEC), (m, MARKET_SPEC)):
        for key, type_, col in fields:
            summary.setdefault(col, value(obj, key, type_))
    summary["SLUG"] = m["slug"]   # the market's own (= the event's)
    trade_rows = [{"SLUG": slug, "CONDITION_ID": t.get("conditionId"), "EVENT_SLUG": t.get("eventSlug"),
                   "TITLE": t.get("title"), "ICON": t.get("icon"), "TIMESTAMP": t["timestamp"],
                   "SECS_INTO_WINDOW": t["timestamp"] - ts, "SIDE": t.get("side"), "OUTCOME": t.get("outcome"),
                   "OUTCOME_INDEX": t.get("outcomeIndex"), "ASSET": t.get("asset"), "PRICE": t.get("price"),
                   "SIZE": t.get("size"), "TX": t.get("transactionHash"), "WALLET": t.get("proxyWallet"),
                   "NAME": t.get("name"), "PSEUDONYM": t.get("pseudonym"), "BIO": t.get("bio"),
                   "PROFILE_IMAGE": t.get("profileImage"),
                   "PROFILE_IMAGE_OPTIMIZED": t.get("profileImageOptimized")} for t in trades]
    return summary, trade_rows, history


def fmt(seconds):
    return str(timedelta(seconds=int(seconds)))


def main():
    start = datetime.fromisoformat(DATE_START).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(DATE_END).replace(tzinfo=timezone.utc)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    print(f"loading {', '.join(COLUMNS)} for {DATE_START} to {DATE_END} ({len(days)} days)")

    t0 = time.time()
    con = duckdb.connect(DB_PATH)
    try:
        # Slugs compare correctly as text since the unix timestamps all have the same length.
        first_slug = f"btc-updown-5m-{int(start.timestamp())}"
        after_last_slug = f"btc-updown-5m-{int((end + timedelta(days=1)).timestamp())}"
        loaded = set()
        if RELOAD:
            # Delete the whole date range up front, so re-running never duplicates rows.
            for table in COLUMNS:
                deleted = con.execute(f"DELETE FROM {table} WHERE SLUG >= ? AND SLUG < ?",
                                      [first_slug, after_last_slug]).fetchone()[0]
                print(f"deleted {deleted} existing {table} rows")
        else:
            # Keep what's there and fetch only the windows not in btc_summary yet. A day's three tables are
            # inserted in one transaction, so a window in btc_summary has its trades and history too.
            loaded = {s for (s,) in con.execute("SELECT SLUG FROM btc_summary WHERE SLUG >= ? AND SLUG < ?",
                                                [first_slug, after_last_slug]).fetchall()}
            print(f"RELOAD off: {len(loaded)} markets already loaded, skipping them")

        todo = []   # (day, the window starts still to fetch)
        for day in days:
            first = int(day.timestamp())
            stamps = [ts for ts in range(first, first + 86400, 300) if f"btc-updown-5m-{ts}" not in loaded]
            if stamps:
                todo.append((day, stamps))
        print(f"{len(todo)} days to fetch")

        with ThreadPoolExecutor(N_RUNNERS) as pool, tempfile.TemporaryDirectory() as tmp:
            for i, (day, stamps) in enumerate(todo, 1):
                windows = [w for w in pool.map(fetch_window, stamps) if w]
                rows = {"btc_summary": [w[0] for w in windows],
                        "btc_trades": [r for w in windows for r in w[1]],
                        "btc_history": [r for w in windows for r in w[2]]}

                con.execute("BEGIN")
                for table, table_rows in rows.items():
                    if table_rows:
                        path = Path(tmp) / f"{table}.json"
                        path.write_text("".join(json.dumps(r) + "\n" for r in table_rows))
                        con.execute(insert_sql(table, path))
                con.execute("COMMIT")

                elapsed = time.time() - t0
                eta = elapsed / i * (len(todo) - i)
                print(f"[day {i}/{len(todo)}] {day:%Y-%m-%d} | markets {len(windows)}/{len(stamps)} | inserted: "
                      f"{len(rows['btc_summary'])} summary, {len(rows['btc_trades'])} trades, "
                      f"{len(rows['btc_history'])} history | elapsed {fmt(elapsed)} | ETA {fmt(eta)}")
    finally:
        con.close()
        print(f"=== done in {fmt(time.time() - t0)}")


if __name__ == "__main__":
    main()
