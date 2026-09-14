from __future__ import annotations

import sqlite3
import time
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None => autocommit; we open explicit BEGIN/COMMIT where batching matters.
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def apply_migrations(conn: sqlite3.Connection) -> list[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "filename TEXT PRIMARY KEY, applied_ms INTEGER NOT NULL)"
    )
    applied = {row["filename"] for row in conn.execute("SELECT filename FROM schema_migrations")}
    newly_applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations(filename, applied_ms) VALUES (?, ?)",
            (path.name, int(time.time() * 1000)),
        )
        newly_applied.append(path.name)
    return newly_applied
