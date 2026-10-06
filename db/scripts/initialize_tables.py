from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DB_PATH = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb")
DDL_DIR = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/schema/ddl/tables")

sql_files = sorted(DDL_DIR.glob("*.sql"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(DB_PATH))
try:
    for path in sql_files:
        sql = path.read_text()
        try:
            con.execute(sql)
        except duckdb.Error as exc:
            raise SystemExit(f"Failed in {path.name}: {exc}") from exc
        print(f"Created {path.name}")

    tables = con.execute("SHOW TABLES").fetchall()
    print(f"\n{DB_PATH} now has {len(tables)} table(s):")
    for (name,) in tables:
        print(f"  - {name}")
finally:
    con.close()