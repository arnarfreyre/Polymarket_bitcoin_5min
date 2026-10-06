# Polymarket Bitcoin 5-minute markets

Local DuckDB of Polymarket "Bitcoin Up or Down" 5-minute markets (their trades and price history) plus 1-second Binance BTCUSDT prices, with notebooks for analysis.

## 1. Fix the paths first

Every script hardcodes `/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min`. Replace it with your own project location in each file you plan to run:

**Needed for the setup below**
- `db/scripts/changeset0/create_db.py`
- `db/scripts/changeset0/initialize_raw_tables.py`
- `db/scripts/initialize_tables.py`
- `db/pipeline/populate_poly_btc.py` (`ROOT`)
- `db/pipeline/bitcoin 1s/load_bitcoin_prices.py` (`DB_PATH`)
- `db/scripts/apply_index.py`
- `db/scripts/populate_table.py` (also `temp_dir`, plus `threads`, `memory_limit`, `max_temp_dir_size`, which are tuned for an 11-core / 18 GB Mac)

**Other files with the path**
- `db/pipeline/populate_bitcoin_5m.py` (`ROOT`)
- `db/scripts/create_table.py`
- `db/scripts/changeset0/create_views.py`
- `db/schema/alters/done/2026-22-09/rename_bitcoin_trades.py` and `db/schema/alters/done/2026-29-09/reset_db_keep_bitcoin_prices.py` (one-off migrations already applied, not part of setup)
- `db/pipeline/old/populate_bitcoin_5m_markets.ipynb` and `db/pipeline/old/populate_bitcoin_5m_trades.ipynb`
- `notebooks/inspect db/analyse data.ipynb`
- `notebooks/inspect db/inspect_bitcoin_prices.ipynb`
- `notebooks/inspect db/plot_market.ipynb`
- `notebooks/project/compare_true_winrate.ipynb`
- `notebooks/test bitcoin.ipynb`
- `notebooks/trader_strategies.ipynb`

Find any you missed with:
`grep -rln "/Users/arnar" . --include='*.py' --include='*.sql' --include='*.ipynb' --exclude-dir=.venv`

## 2. Python environments

- Project venv at `.venv/` (needs `duckdb`, `pandas`, `requests`; run scripts with `.venv/bin/python`).
- A second venv at `db/pipeline/bitcoin 1s/.venv/` with `duckdb`, `pandas`, `binance-vision` (provides `fetch_data`).

## 3. Initialize the database (run once, in this order)

1. `.venv/bin/python db/scripts/changeset0/create_db.py` creates the empty `db/polymarket.duckdb`.
2. `.venv/bin/python db/scripts/changeset0/initialize_raw_tables.py` creates the raw tables `btc_summary`, `btc_trades`, `btc_history`, `bitcoin_prices` from `db/schema/ddl/raw/`.
3. `.venv/bin/python db/scripts/initialize_tables.py` creates the derived `MARKET_TRADES` table (empty) from `db/schema/ddl/tables/`.

## 4. Populate

DuckDB allows only one writer, so run these one at a time and close any notebook connected to the DB.

1. **Polymarket data:** set `DATE_START` / `DATE_END` in `db/pipeline/populate_poly_btc.py`, then run it. It fills `btc_summary`, `btc_trades`, `btc_history`. Re-running a range doesn't duplicate rows.
2. **BTC prices:** from `db/pipeline/bitcoin 1s/`, run `.venv/bin/python load_bitcoin_prices.py 2026-08-01 2026-09-22` (dates inclusive, or edit `START_DATE` / `END_DATE`). It fills `bitcoin_prices`.
3. **Indexes (optional, speeds up queries):** `.venv/bin/python db/scripts/apply_index.py`.
4. **`MARKET_TRADES`:** `.venv/bin/python db/scripts/populate_table.py` builds it from `btc_trades` joined with `btc_summary`. It refuses to run if the table already has rows; `DELETE FROM MARKET_TRADES` first to reload.

## Known gaps

- `db/pipeline/populate_bitcoin_5m.py` is the newer loader (tables `bitcoin_5m_markets`, `bitcoin_5m_trades`, `bitcoin_prices`), but this repo has no DDL for the `bitcoin_5m_*` tables, and the derived-table DDL it rebuilds (`positions`, `market_prices`) only exists under `old/` folders. It won't work from scratch without restoring those, so the steps above use `populate_poly_btc.py`.
- `db/scripts/changeset0/create_views.py` finds no `.sql` files, because the views were moved to `db/schema/views/old/`. Skip it.
