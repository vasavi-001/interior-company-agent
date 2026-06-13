"""
tools.py
--------
The three tools the interior design agent can use:

1. Catalog Search   — find real products from SQLite
2. Budget Calculator — sum prices and check budget
3. Layout Fit Checker — see if items fit in the room
"""

from __future__ import annotations

from typing import Any

import database as db


# ---------------------------------------------------------------------------
# Tool 1: Catalog Search
# ---------------------------------------------------------------------------


def catalog_search(
    room_type: str | None = None,
    category: str | None = None,
    style_keyword: str | None = None,
    max_price_inr: int | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    """
    Search the company catalog. Never invents products — only DB rows.

    Returns a dict with:
      - success: bool
      - count: number of matches
      - products: list of product dicts
      - message: human-readable summary
    """
    products = db.search_catalog(
        room_type=room_type,
        category=category,
        style_keyword=style_keyword,
        max_price_inr=max_price_inr,
        keyword=keyword,
        in_stock_only=True,  # guardrail: no out-of-stock items
    )

    return {
        "success": True,
        "count": len(products),
        "products": products,
        "message": (
            f"Found {len(products)} in-stock product(s)"
            + (f" in category '{category}'" if category else "")
            + (f" for room '{room_type}'" if room_type else "")
            + "."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 2: Budget Calculator
# ---------------------------------------------------------------------------


def budget_calculator(
    item_ids: list[str],
    budget_inr: int,
) -> dict[str, Any]:
    """
    Calculate total cost for a list of catalog item IDs.

    Guardrail: flags budget overrun loudly — never silent exceed.
    Items with NULL price are flagged as 'price_unknown'.
    """
    line_items: list[dict[str, Any]] = []
    total = 0
    warnings: list[str] = []

    for item_id in item_ids:
        product = db.get_product_by_id(item_id)

        if product is None:
            warnings.append(f"INVALID: '{item_id}' does not exist in catalog.")
            line_items.append({"item_id": item_id, "status": "not_found"})
            continue

        if product.get("in_stock") != 1:
            warnings.append(f"OUT OF STOCK: '{item_id}' ({product['name']}).")
            line_items.append(
                {
                    "item_id": item_id,
                    "name": product["name"],
                    "status": "out_of_stock",
                }
            )
            continue

        price = product.get("price_inr")
        if price is None:
            warnings.append(f"PRICE UNKNOWN: '{item_id}' ({product['name']}).")
            line_items.append(
                {
                    "item_id": item_id,
                    "name": product["name"],
                    "price_inr": None,
                    "status": "price_unknown",
                }
            )
            continue

        total += price
        line_items.append(
            {
                "item_id": item_id,
                "name": product["name"],
                "category": product["category"],
                "price_inr": price,
                "status": "ok",
            }
        )

    remaining = budget_inr - total
    within_budget = total <= budget_inr and not any(
        w.startswith("INVALID") or w.startswith("OUT OF STOCK") for w in warnings
    )

    if total > budget_inr:
        warnings.append(
            f"BUDGET EXCEEDED: total ₹{total:,} > budget ₹{budget_inr:,} "
            f"(over by ₹{total - budget_inr:,})."
        )

    return {
        "success": within_budget,
        "budget_inr": budget_inr,
        "total_inr": total,
        "remaining_inr": remaining,
        "within_budget": within_budget,
        "line_items": line_items,
        "warnings": warnings,
        "message": (
            f"Total ₹{total:,} of ₹{budget_inr:,} budget. "
            + ("Within budget." if within_budget else "OVER BUDGET — replan needed.")
        ),
    }


# ---------------------------------------------------------------------------
# Tool 3: Layout Fit Checker
# ---------------------------------------------------------------------------


def _footprint_area_cm2(product: dict[str, Any]) -> int | None:
    """Floor footprint = width × depth. Returns None if dimensions missing."""
    w, d = product.get("width_cm"), product.get("depth_cm")
    if w is None or d is None:
        return None
    return w * d


def layout_fit_checker(
    room_length_cm: int,
    room_width_cm: int,
    item_ids: list[str],
    *,
    walkway_cm: int = 60,
) -> dict[str, Any]:
    """
    Check whether selected items can reasonably fit in the room.

    Simple MVP rules (beginner-friendly):
      - Each item's width and depth must be <= room length and width.
      - Combined floor footprint must not exceed ~70% of room floor area
        (leaves space for walkways and circulation).
      - Height is checked against ceiling only when both are known.

    This is NOT structural advice — only basic spatial sanity checks.
    """
    room_floor_area = room_length_cm * room_width_cm
    max_usable_area = int(room_floor_area * 0.70)

    items_report: list[dict[str, Any]] = []
    total_footprint = 0
    issues: list[str] = []
    all_fit = True

    for item_id in item_ids:
        product = db.get_product_by_id(item_id)
        if product is None:
            issues.append(f"'{item_id}' not in catalog.")
            all_fit = False
            continue

        w = product.get("width_cm")
        d = product.get("depth_cm")
        h = product.get("height_cm")
        item_ok = True
        item_issues: list[str] = []

        # Check individual item fits through the "door" of the room dimensions.
        if w and d:
            fits_length = w <= room_length_cm and d <= room_width_cm
            fits_width = w <= room_width_cm and d <= room_length_cm
            if not (fits_length or fits_width):
                item_ok = False
                item_issues.append(
                    f"Footprint {w}×{d} cm too large for room "
                    f"{room_length_cm}×{room_width_cm} cm."
                )
            footprint = w * d
            total_footprint += footprint
        else:
            item_issues.append("Missing width/depth — cannot verify footprint.")
            item_ok = False

        items_report.append(
            {
                "item_id": item_id,
                "name": product["name"],
                "width_cm": w,
                "depth_cm": d,
                "height_cm": h,
                "fits": item_ok,
                "issues": item_issues,
            }
        )

        if not item_ok:
            all_fit = False

    if total_footprint > max_usable_area:
        all_fit = False
        issues.append(
            f"Combined footprint {total_footprint:,} cm² exceeds safe usable area "
            f"{max_usable_area:,} cm² (70% of {room_floor_area:,} cm² room floor)."
        )

    return {
        "success": all_fit,
        "room_length_cm": room_length_cm,
        "room_width_cm": room_width_cm,
        "room_floor_area_cm2": room_floor_area,
        "max_usable_area_cm2": max_usable_area,
        "total_footprint_cm2": total_footprint,
        "walkway_clearance_cm": walkway_cm,
        "items": items_report,
        "issues": issues,
        "all_fit": all_fit,
        "message": (
            "All items fit the room layout."
            if all_fit
            else "Layout issues found — replan with smaller or fewer items."
        ),
    }


# ---------------------------------------------------------------------------
# Tool registry (used by agent.py to map OpenAI tool calls to Python functions)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "catalog_search",
            "description": (
                "Search the company product catalog. "
                "Only returns real in-stock products from the database. "
                "Never invent items — always use this before recommending products."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_type": {
                        "type": "string",
                        "description": "Room type, e.g. 'Living Room', 'Bedroom'.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Product category, e.g. 'Sofa', 'Bed', 'Rug'.",
                    },
                    "style_keyword": {
                        "type": "string",
                        "description": "Style tag to match, e.g. 'Scandinavian'.",
                    },
                    "max_price_inr": {
                        "type": "integer",
                        "description": "Maximum price per item in INR.",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Free-text search in product name or category.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "budget_calculator",
            "description": (
                "Calculate total cost for a list of catalog item IDs against a budget. "
                "Use after selecting products to verify the design stays within budget."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of catalog item_id values, e.g. ['SOF-001'].",
                    },
                    "budget_inr": {
                        "type": "integer",
                        "description": "Customer budget in INR.",
                    },
                },
                "required": ["item_ids", "budget_inr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "layout_fit_checker",
            "description": (
                "Check if selected catalog items fit the room dimensions. "
                "Use room length and width from the brief. Not structural advice."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_length_cm": {"type": "integer"},
                    "room_width_cm": {"type": "integer"},
                    "item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["room_length_cm", "room_width_cm", "item_ids"],
            },
        },
    },
]


def run_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool by name. Used by the agent loop."""
    if tool_name == "catalog_search":
        return catalog_search(**arguments)
    if tool_name == "budget_calculator":
        return budget_calculator(**arguments)
    if tool_name == "layout_fit_checker":
        return layout_fit_checker(**arguments)
    return {"success": False, "message": f"Unknown tool: {tool_name}"}
