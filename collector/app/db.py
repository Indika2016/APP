from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import DictRow, dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


async def get_connection(database_url: str) -> psycopg.AsyncConnection[DictRow]:
    return await psycopg.AsyncConnection.connect(database_url, row_factory=dict_row, autocommit=True)


def _split_statements(sql: str) -> list[str]:
    """Split a migration file into individual statements.

    psycopg3 sends a parameter-less execute() over the simple query protocol,
    which *can* run multiple ';'-separated statements in one call -- but that
    behavior isn't something to build a schema on. Statements here are plain
    CREATE TABLE/INDEX with no semicolons inside string literals, so a naive
    split is safe and makes execution explicit and debuggable.
    """
    statements = []
    for raw in sql.split(";"):
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


async def apply_migrations(conn: psycopg.AsyncConnection[DictRow]) -> list[str]:
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(filename TEXT PRIMARY KEY, applied_ms BIGINT NOT NULL)"
    )
    applied = {row["filename"] for row in await fetchall(conn, "SELECT filename FROM schema_migrations")}
    newly_applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        async with conn.transaction():
            for statement in _split_statements(path.read_text(encoding="utf-8")):
                await conn.execute(statement)
            await conn.execute(
                "INSERT INTO schema_migrations (filename, applied_ms) VALUES (%s, %s)",
                (path.name, int(time.time() * 1000)),
            )
        newly_applied.append(path.name)
    return newly_applied


async def fetchone(conn: psycopg.AsyncConnection[DictRow], sql: str, params: Any = None) -> DictRow | None:
    cur = await conn.execute(sql, params)
    return await cur.fetchone()


async def fetchall(conn: psycopg.AsyncConnection[DictRow], sql: str, params: Any = None) -> list[DictRow]:
    cur = await conn.execute(sql, params)
    return await cur.fetchall()
