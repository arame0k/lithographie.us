"""Avoid erasing imported evidence when rebuilding the baseline database."""
import sqlite3
from pathlib import Path

def assert_safe_to_rebuild(path):
    path=Path(path)
    if not path.exists():return
    with sqlite3.connect(path) as conn:
        try:
            n=conn.execute('SELECT COUNT(*) FROM port_hs6_archives').fetchone()[0]
        except sqlite3.OperationalError:
            n=0
    if n:
        raise ValueError(f'rebuild blocked: {n} imported Census archive(s) in {path}; back up or use a new database')
