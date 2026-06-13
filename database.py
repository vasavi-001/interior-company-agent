"""
database.py
-----------
Handles all SQLite reads for the interior design agent.

We only READ from the database — the agent never writes or invents products.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Default path to the catalog database (same folder as this file).
DB_PATH = Path(__file__).parent / "interior_company_catalog.db"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a read-only style connection to SQLite."""
    path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # rows behave like dictionaries
    return conn


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row into a plain Python dictionary."""
    return dict(row)


# ---------------------------------------------------------------------------
# Room briefs
# ---------------------------------------------------------------------------


def list_room_briefs(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return every room brief in the database."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM room_briefs ORDER BY brief_id"
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_room_brief(
    brief_id: str, db_path: str | Path | None = None
) -> dict[str, Any] | None:
    """Fetch one room brief by its ID. Returns None if not found."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM room_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


# ---------------------------------------------------------------------------
# Catalog products
# ---------------------------------------------------------------------------


def get_product_by_id(
    item_id: str, db_path: str | Path | None = None
) -> dict[str, Any] | None:
    """Fetch a single catalog item. Returns None if the ID does not exist."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM catalog WHERE item_id = ?",
            (item_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def search_catalog(
    *,
    category: str | None = None,
    room_type: str | None = None,
    style_keyword: str | None = None,
    max_price_inr: int | None = None,
    keyword: str | None = None,
    in_stock_only: bool = True,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Search the product catalog with optional filters.

    Guardrail: by default we only return in-stock items (in_stock = 1).
    """
    query = "SELECT * FROM catalog WHERE 1=1"
    params: list[Any] = []

    if in_stock_only:
        query += " AND in_stock = 1"

    if category:
        query += " AND LOWER(category) = LOWER(?)"
        params.append(category)

    if room_type:
        # room_types is a comma-separated list like "Living Room,Bedroom"
        query += " AND LOWER(room_types) LIKE LOWER(?)"
        params.append(f"%{room_type}%")

    if style_keyword:
        query += " AND LOWER(style_tags) LIKE LOWER(?)"
        params.append(f"%{style_keyword}%")

    if max_price_inr is not None:
        # Skip items with unknown price (NULL) when a budget cap is set.
        query += " AND price_inr IS NOT NULL AND price_inr <= ?"
        params.append(max_price_inr)

    if keyword:
        query += " AND (LOWER(name) LIKE LOWER(?) OR LOWER(category) LIKE LOWER(?))"
        params.append(f"%{keyword}%")
        params.append(f"%{keyword}%")

    query += " ORDER BY price_inr ASC NULLS LAST, name ASC"

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    return [row_to_dict(r) for r in rows]


def product_exists_and_in_stock(
    item_id: str, db_path: str | Path | None = None
) -> bool:
    """Return True only if the product exists in the catalog and is in stock."""
    product = get_product_by_id(item_id, db_path)
    return product is not None and product.get("in_stock") == 1
