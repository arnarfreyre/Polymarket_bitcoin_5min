from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DB_PATH = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb")
sql_path = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/schema/ddl/tables/market_trades.sql")


con = duckdb.connect(str(DB_PATH))

sql = Path.read_text(sql_path)

try:
    try:
        con.execute(sql)
        print("Execution successful")
        tables = con.execute("SHOW TABLES").fetchall()
        print(f"\n{DB_PATH} now has {len(tables)} table(s):")
        for (name,) in tables:
            print(f"  - {name}")

    except Exception as e:
        print(f"Execution not successful \n {e}")
finally:
    con.close()