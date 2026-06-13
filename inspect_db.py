"""
inspect_db.py
-------------
Print table names, schemas, and sample rows from interior_company_catalog.db.

Run with:
    python inspect_db.py
"""

from __future__ import annotations

import sqlite3

from database import DB_PATH, get_connection

ROW_LIMIT = 20


def print_table_names(conn: sqlite3.Connection) -> None:
    print("=== Tables ===")
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    for (name,) in rows:
        print(name)
    print()


def print_schema(conn: sqlite3.Connection, table_name: str) -> None:
    print(f"=== Schema: {table_name} ===")
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    for cid, name, col_type, notnull, default, pk in columns:
        flags = []
        if pk:
            flags.append("PK")
        if notnull:
            flags.append("NOT NULL")
        flag_str = f" ({', '.join(flags)})" if flags else ""
        default_str = f" DEFAULT {default!r}" if default is not None else ""
        print(f"  {name}: {col_type}{flag_str}{default_str}")
    print()


def print_sample_rows(conn: sqlite3.Connection, table_name: str, limit: int = ROW_LIMIT) -> None:
    print(f"=== First {limit} rows: {table_name} ===")
    rows = conn.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,)).fetchall()
    if not rows:
        print("  (no rows)")
        print()
        return

    columns = rows[0].keys()
    print("  " + " | ".join(columns))
    print("  " + "-" * (len(columns) * 16))
    for row in rows:
        values = [str(row[col]) if row[col] is not None else "NULL" for col in columns]
        print("  " + " | ".join(values))
    print()


def main() -> None:
    print(f"Database: {DB_PATH}\n")

    with get_connection() as conn:
        print_table_names(conn)
        print_schema(conn, "catalog")
        print_schema(conn, "room_briefs")

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        for (table_name,) in tables:
            print_sample_rows(conn, table_name)


if __name__ == "__main__":
    main()
