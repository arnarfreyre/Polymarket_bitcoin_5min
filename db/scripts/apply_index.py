from pathlib import Path
from time import perf_counter

import duckdb
import pandas as pd

DB_PATH = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/polymarket.duckdb")
IDX_DIR = Path("/Users/arnarfreyrerlingsson/Desktop/Polymarket_bitcoin_5min/db/schema/indexes/")

sql_files = sorted(IDX_DIR.glob("*.sql"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

idx_list = [{"Path": p, "sql": p.read_text()} for p in sql_files]
index_df = pd.DataFrame(idx_list)
print(index_df)

con = duckdb.connect(str(DB_PATH), read_only=False)
try:
    total_start = perf_counter()

    for i, row in enumerate(idx_list, start=1):
        name = row["Path"].name
        print(f"\n[{i}/{len(idx_list)}] about to apply {name}")
        print(row["sql"].strip())

        start = perf_counter()
        try:
            con.execute(row["sql"])
        except duckdb.Error as exc:
            raise SystemExit(f"Failed in {name}: {exc}") from exc
        elapsed = perf_counter() - start

        print(f"[{i}/{len(idx_list)}] {name} complete in {elapsed:.3f}s")

    print(f"\nAll {len(idx_list)} files applied in {perf_counter() - total_start:.3f}s")

    indexes = con.execute("SELECT index_name FROM duckdb_indexes() ORDER BY index_name;").fetchall()
    print(f"{DB_PATH} now has {len(indexes)} indexes:")
    for (name,) in indexes:
        print(f"  - {name}")
finally:
    con.close()