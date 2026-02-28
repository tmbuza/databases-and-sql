import sqlite3
from pathlib import Path

db_path = Path("data") / "cdi-retail.sqlite"
schema = Path("data/sql/cdi-retail-schema.sql").read_text(encoding="utf-8")
seed = Path("data/sql/cdi-retail-seed.sql").read_text(encoding="utf-8")

if db_path.exists():
    db_path.unlink()

con = sqlite3.connect(db_path)
try:
    con.executescript(schema)
    con.executescript(seed)
finally:
    con.close()

print(f"Wrote {db_path}")
