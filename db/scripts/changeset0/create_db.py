import duckdb
from pathlib import Path

db_path = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb")
db_path.parent.mkdir(parents=True, exist_ok=True)

duckdb.connect(str(db_path)).close()