"""Fresh restart of the DB: drop every view and every table except bitcoin_prices (and its indexes)."""
import duckdb

DB_PATH = "/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb"
KEEP = {"bitcoin_prices"}

con = duckdb.connect(DB_PATH)
try:
    before = con.execute("SELECT count(*) FROM bitcoin_prices").fetchone()[0]
    for (name,) in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall():
        con.execute(f'DROP VIEW IF EXISTS "{name}"')
        print(f"dropped view {name}")
    for (name,) in con.execute("SELECT index_name FROM duckdb_indexes()").fetchall():
        con.execute(f'DROP INDEX IF EXISTS "{name}"')
        print(f"dropped index {name}")
    for (name,) in con.execute("SELECT table_name FROM duckdb_tables()").fetchall():
        if name not in KEEP:
            con.execute(f'DROP TABLE IF EXISTS "{name}"')
            print(f"dropped table {name}")
    con.execute("CHECKPOINT")
    after = con.execute("SELECT count(*) FROM bitcoin_prices").fetchone()[0]
    print(f"bitcoin_prices rows: {before} -> {after}")
finally:
    con.close()
