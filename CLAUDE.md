# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Research on Polymarket's "Bitcoin Up or Down" 5-minute markets (slug `btc-updown-5m-<unix ts>`, ts is a multiple of 300; 288 windows per UTC day). The repo holds a Polymarket API wrapper, a local DuckDB of market/trade/BTC-price data with loader scripts, and analysis notebooks. There is no git repo, test suite, linter or build step, and no README/requirements file.

Trading bots (`bots/…`, VM deploy scripts) are referenced in `run_code.txt` and in memory notes but are **not present in this checkout**. Don't assume `bots/` exists.

## Running things

- Use the project venv: `.venv/bin/python <script>`. Scripts are run directly and configured by editing constants at the top of the file (no CLI args).
- `db/pipeline/bitcoin 1s/` has its **own** `.venv` (Binance 1s BTCUSDT loader); `populate_bitcoin_5m.py` calls it as a subprocess.
- Scripts hardcode absolute paths (`/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/...`) for the DB and schema dirs.
- DuckDB allows one writer: close notebooks' connections (or open `read_only=True`) before running a loader. `db/polymarket.duckdb.tmp` / `db/tmp_duckdb/` are DuckDB spill files.

## Layout

- `polymarket_api/` — thin `requests` wrappers. `PolymarketClient` (`client.py`) exposes `.gamma` (market/event discovery), `.clob` (price history, books), `.data` (trades); base URLs in `_base.py`.
- `db/pipeline/` — bulk loaders into DuckDB:
  - `populate_bitcoin_5m.py`: loads `bitcoin_5m_markets`, `bitcoin_5m_trades`, `bitcoin_prices` for `DATE_START..DATE_END`; deletes the date range first (re-runs don't duplicate), drops indexes from `db/schema/indexes/*.sql` during load and rebuilds them after, then rebuilds derived tables. Fetches windows in parallel threads, bulk-loads via temp JSON + `read_json` (much faster than parameter inserts).
  - `populate_poly_btc.py`: older loader for `btc_summary` / `btc_trades` / `btc_history` (one Gamma event + paged trades + CLOB price history per window); `RELOAD=False` only fetches markets not yet loaded.
- `db/schema/` — SQL: `ddl/raw` (raw tables), `ddl/tables` (derived, e.g. `market_trades.sql` joins trades with market summary), `views`, `indexes`, `alters/done/<date>/` (one-off migration scripts, already applied), and `old/` subfolders (superseded).
- `db/scripts/` — helpers that run every `.sql` in a schema dir (`initialize_tables.py`, `create_table.py`, `apply_index.py`, `changeset0/*`).
- `notebooks/` — analysis (`inspect db/`, `project/`, `model bitcoin/` with paper-derived feature scripts, `trader_strategies.ipynb`).
- `test.py` — scratch script pulling a day of windows from Gamma (`eventMetadata.priceToBeat` / `finalPrice`).

## Gotchas

- The current `polymarket.duckdb` contains `btc_summary`, `btc_trades`, `btc_history`, `bitcoin_prices`, `MARKET_TRADES` (the old schema, reset 2026-09-29), while `populate_bitcoin_5m.py` targets the newer `bitcoin_5m_*` tables. Check `SHOW TABLES` and the DDL before assuming which exists.
- Market resolution: Up wins if final price ≥ price to beat; settlement uses a Chainlink TWAP, not a spot tick.
- Gamma/Data APIs rate-limit (429); loaders retry with backoff, so keep parallelism modest.
