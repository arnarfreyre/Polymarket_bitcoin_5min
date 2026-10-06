import duckdb
from pathlib import Path

DB_PATH = "/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb"

con = duckdb.connect(DB_PATH,read_only=False)

query = """ 
ALTER TABLE IF EXISTS bitcoin_5m_raw
RENAME TO bitcoin_5m_trades;
"""

con.execute(query)
con.close()
print("Alter successfull")
