from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DB_PATH = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb")
VIEWS_PATH = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/schema/views")

sql_files = sorted(VIEWS_PATH.glob("*.sql"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(DB_PATH))
try:
    for path in sql_files:
        sql = path.read_text()
        try:
            con.execute(sql)
        except duckdb.Error as exc:
            raise SystemExit(f"Failed in {path.name}: {exc}") from exc
        print(f"applied {path.name}")
finally:
    con.close()