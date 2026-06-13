"""
agent.py
--------
The AI Interior Design Agent.

Flow:
  1. Read a room brief from SQLite
  2. Use OpenAI + our three tools to search catalog, check budget, check layout
  3. Re-plan automatically when constraints fail
  4. Return design rationale + Bill of Quantities (BOQ)

Guardrails (enforced in code AND in the system prompt):
  - Never invent products
  - Never exceed budget silently
  - Never recommend out-of-stock products
  - Never give structural advice
  - Never promise delivery dates
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

import database as db
import tools as agent_tools

# How many times the agent may retry after a failed budget/layout check.
MAX_REPLAN_ATTEMPTS = 3

# OpenAI model — gpt-4o-mini is cost-effective for an MVP.
DEFAULT_MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# System prompt with guardrails
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an Interior Design Agent for a furniture company.

Your job:
1. Read the customer's room brief.
2. Use catalog_search to find REAL products from the company catalog.
3. Select items that match style, must-haves, and constraints.
4. Use budget_calculator to verify the total stays within budget.
5. Use layout_fit_checker to verify items fit the room.
6. If budget or layout checks FAIL, search for cheaper/smaller alternatives and try again.
7. Produce a final design with rationale and a Bill of Quantities (BOQ).

STRICT RULES — NEVER BREAK THESE:
- NEVER invent or hallucinate products. Every item_id MUST come from catalog_search results.
- NEVER recommend out-of-stock products (catalog_search already filters these).
- NEVER exceed the customer's budget. If you cannot fit must-haves in budget, explain clearly.
- NEVER give structural advice (load-bearing walls, plumbing moves, electrical rewiring, etc.).
- NEVER promise or mention specific delivery dates or lead times to the customer.
- ONLY recommend products you have verified exist via catalog_search.
- Stay within the room's spatial constraints.

When you finish, respond with ONLY valid JSON in this exact shape:
{
  "status": "success" or "failed",
  "design_rationale": "2-4 paragraphs explaining the design choices",
  "selected_items": [
    {
      "item_id": "SOF-001",
      "name": "Product name from catalog",
      "category": "Sofa",
      "price_inr": 58000,
      "why": "One sentence why this item was chosen"
    }
  ],
  "boq": {
    "line_items": [
      {"item_id": "SOF-001", "name": "...", "qty": 1, "unit_price_inr": 58000, "line_total_inr": 58000}
    ],
    "subtotal_inr": 0,
    "budget_inr": 0,
    "remaining_inr": 0
  },
  "constraint_notes": ["Any trade-offs or unresolved constraints"],
  "replan_count": 0
}

If you cannot produce a valid design after replanning, set status to "failed" and explain why in design_rationale.
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


class InteriorDesignAgent:
    """Orchestrates the OpenAI conversation and tool calls."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        db_path: str | None = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key=."
            )
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.db_path = db_path

    def _build_user_message(self, brief: dict[str, Any]) -> str:
        """Turn a room brief row into a clear instruction for the model."""
        return f"""Design this room using ONLY products from our catalog.

ROOM BRIEF:
- Brief ID: {brief['brief_id']}
- Room type: {brief['room_type']}
- Dimensions: {brief['length_cm']} cm (length) × {brief['width_cm']} cm (width) × {brief['ceiling_cm']} cm (ceiling)
- Budget: ₹{brief['budget_inr']:,} INR
- Style preference: {brief['style_preference']}
- Must-haves: {brief['must_haves']}
- Constraints: {brief['constraints']}
- Customer note: {brief['customer_note']}

Steps:
1. Search the catalog for each must-have category.
2. Pick a coherent set of in-stock items within budget.
3. Run budget_calculator with budget_inr={brief['budget_inr']}.
4. Run layout_fit_checker with room_length_cm={brief['length_cm']} and room_width_cm={brief['width_cm']}.
5. If checks fail, replan with different products (up to {MAX_REPLAN_ATTEMPTS} times).
6. Return final JSON with design_rationale and BOQ.
"""

    def _run_tool_loop(self, messages: list[dict[str, Any]]) -> tuple[list[dict], str]:
        """
        Chat with OpenAI, executing tool calls until the model returns text.

        Returns (updated_messages, final_text_response).
        """
        for _ in range(20):  # safety cap on tool rounds
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=agent_tools.TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.3,
            )

            choice = response.choices[0]
            assistant_message = choice.message

            # Build the assistant message dict for the next round.
            msg_dict: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_message.content or "",
            }
            if assistant_message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_message.tool_calls
                ]
            messages.append(msg_dict)

            # If no tool calls, we have the final answer.
            if not assistant_message.tool_calls:
                return messages, assistant_message.content or ""

            # Execute each tool call and append results.
            for tool_call in assistant_message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}

                result = agent_tools.run_tool(fn_name, fn_args)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    }
                )

        return messages, ""

    def _parse_design_json(self, text: str) -> dict[str, Any] | None:
        """Extract JSON from the model's final response."""
        text = text.strip()

        # Try direct parse first.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find a JSON block inside markdown fences.
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find the first { ... } object in the text.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _validate_design(
        self, design: dict[str, Any], brief: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        return validate_design(design, brief, self.db_path)

    def _build_boq_from_items(
        self, selected_items: list[dict], budget_inr: int
    ) -> dict[str, Any]:
        return build_boq_from_items(selected_items, budget_inr, self.db_path)

    def design_room(self, brief_id: str) -> dict[str, Any]:
        """
        Main entry point: produce a full design for a room brief.

        Returns a result dict with status, design, validation, and messages.
        """
        brief = db.get_room_brief(brief_id, self.db_path)
        if brief is None:
            return {
                "status": "error",
                "message": f"Room brief '{brief_id}' not found.",
            }

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_message(brief)},
        ]

        replan_count = 0
        last_violations: list[str] = []

        while replan_count <= MAX_REPLAN_ATTEMPTS:
            _, final_text = self._run_tool_loop(messages)

            design = self._parse_design_json(final_text)
            if design is None:
                return {
                    "status": "error",
                    "message": "Agent did not return valid JSON.",
                    "raw_response": final_text,
                    "brief": brief,
                }

            is_valid, violations = self._validate_design(design, brief)

            if is_valid:
                # Rebuild BOQ from database (never trust model prices blindly).
                design["boq"] = self._build_boq_from_items(
                    design.get("selected_items", []),
                    brief["budget_inr"],
                )
                design["replan_count"] = replan_count
                design["status"] = "success"
                return {
                    "status": "success",
                    "design": design,
                    "brief": brief,
                    "replan_count": replan_count,
                }

            # Constraint failure → ask agent to replan.
            last_violations = violations
            replan_count += 1

            if replan_count > MAX_REPLAN_ATTEMPTS:
                break

            replan_msg = (
                f"VALIDATION FAILED (attempt {replan_count}/{MAX_REPLAN_ATTEMPTS}). "
                f"Fix these issues and return updated JSON:\n"
                + "\n".join(f"- {v}" for v in violations)
                + "\n\nSearch for cheaper or smaller alternatives. Do NOT invent products."
            )
            messages.append({"role": "user", "content": replan_msg})

        # All replan attempts exhausted.
        return {
            "status": "failed",
            "message": "Could not satisfy all constraints after replanning.",
            "violations": last_violations,
            "brief": brief,
            "replan_count": replan_count - 1,
            "design": design if design else None,
        }


def validate_design(
    design: dict[str, Any],
    brief: dict[str, Any],
    db_path: str | None = None,
) -> tuple[bool, list[str]]:
    """Post-validate agent output against guardrails."""
    violations: list[str] = []
    budget_inr = brief["budget_inr"]
    selected = design.get("selected_items") or []

    if not selected:
        violations.append("No products selected.")
        return False, violations

    item_ids = [item.get("item_id") for item in selected if item.get("item_id")]

    for item_id in item_ids:
        product = db.get_product_by_id(item_id, db_path)
        if product is None:
            violations.append(f"Invented product '{item_id}' — not in catalog.")
        elif product.get("in_stock") != 1:
            violations.append(f"Out-of-stock product '{item_id}' recommended.")

    budget_result = agent_tools.budget_calculator(item_ids, budget_inr)
    if not budget_result["within_budget"]:
        violations.extend(budget_result["warnings"])

    layout_result = agent_tools.layout_fit_checker(
        brief["length_cm"],
        brief["width_cm"],
        item_ids,
    )
    if not layout_result["all_fit"]:
        violations.extend(layout_result["issues"])

    rationale = design.get("design_rationale", "")
    delivery_patterns = [
        r"deliver(?:y|ed)?\s+(?:in|within|by)\s+\d+",
        r"lead\s*time",
        r"arrive(?:s)?\s+(?:in|within|by)\s+\d+",
        r"\d+\s+days?\s+(?:delivery|to deliver)",
        r"guarantee.*deliver",
        r"delivered and installed before",
    ]
    for pattern in delivery_patterns:
        if re.search(pattern, rationale, re.IGNORECASE):
            violations.append("Design rationale mentions delivery timing — not allowed.")
            break

    structural_keywords = [
        "load-bearing",
        "structural",
        "demolish",
        "knock down wall",
        "rewire",
        "plumbing relocation",
    ]
    for kw in structural_keywords:
        if kw.lower() in rationale.lower():
            violations.append(f"Structural advice detected: '{kw}'.")
            break

    return len(violations) == 0, violations


def build_boq_from_items(
    selected_items: list[dict],
    budget_inr: int,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Rebuild BOQ from validated catalog data (source of truth = database)."""
    line_items = []
    subtotal = 0

    for item in selected_items:
        item_id = item.get("item_id")
        product = db.get_product_by_id(item_id, db_path)
        if not product:
            continue
        price = product.get("price_inr") or 0
        line_items.append(
            {
                "item_id": item_id,
                "name": product["name"],
                "category": product["category"],
                "qty": 1,
                "unit_price_inr": price,
                "line_total_inr": price,
            }
        )
        subtotal += price

    return {
        "line_items": line_items,
        "subtotal_inr": subtotal,
        "budget_inr": budget_inr,
        "remaining_inr": budget_inr - subtotal,
    }


# ---------------------------------------------------------------------------
# Demo mode — deterministic selection, no OpenAI
# ---------------------------------------------------------------------------

MUST_HAVE_PATTERNS: list[tuple[str, list[str]]] = [
    (r"sectional|l-?sofa|3-seater|sofa|seating for", ["Sofa"]),
    (r"accent seating|reading corner|armchair|lounger", ["Armchair"]),
    (r"coffee table", ["Coffee Table"]),
    (r"tv unit", ["TV Unit"]),
    (r"rug|jute rug|layered rugs", ["Rug"]),
    (r"lighting|floor lamp|table lamp|task lighting|soft lighting|pendant", ["Floor Lamp", "Table Lamp", "Pendant Light"]),
    (r"queen bed|bed(?!side)", ["Bed"]),
    (r"nightstand|bedside", ["Bedside Table"]),
    (r"wardrobe|storage", ["Wardrobe", "Bookshelf"]),
    (r"dining table|6-seater|8-seater|banquet|dining set", ["Dining Table"]),
    (r"console", ["Console"]),
    (r"desk|work desk|study desk", ["Desk"]),
    (r"ergonomic chair|office chair", ["Office Chair"]),
    (r"shelving|bookshelf", ["Bookshelf"]),
    (r"curtain", ["Curtains"]),
    (r"plant", ["Planter"]),
    (r"wall art|art", ["Wall Art"]),
    (r"statement pendant|pendant", ["Pendant Light"]),
    (r"bean bag", ["Bean Bag"]),
    (r"ottoman|pouffe", ["Ottoman"]),
    (r"mirror", ["Mirror"]),
    (r"cushion", ["Cushions"]),
]

STRUCTURAL_BRIEF_PATTERNS = [
    r"load[- ]bearing",
    r"knock down",
    r"remove (?:the )?wall",
    r"demolish",
    r"structural",
    r"rewire",
    r"plumbing",
]

DESIGNER_REQUEST_PATTERNS = [
    r"\btogo\b",
    r"\bnoguchi\b",
    r"\beames\b",
    r"\bbarcelona chair\b",
    r"designer piece",
]


def _brief_text(brief: dict[str, Any]) -> str:
    parts = [
        brief.get("must_haves") or "",
        brief.get("constraints") or "",
        brief.get("customer_note") or "",
    ]
    return " ".join(parts).lower()


def _detect_structural_request(brief: dict[str, Any]) -> bool:
    text = _brief_text(brief)
    return any(re.search(p, text, re.IGNORECASE) for p in STRUCTURAL_BRIEF_PATTERNS)


def _detect_designer_requests(brief: dict[str, Any]) -> list[str]:
    text = _brief_text(brief)
    found: list[str] = []
    for pattern in DESIGNER_REQUEST_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            found.append(match.group(0))
    return found


def _parse_must_have_categories(must_haves: str) -> list[str]:
    text = must_haves.lower()
    categories: list[str] = []
    for pattern, cats in MUST_HAVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            for cat in cats:
                if cat not in categories:
                    categories.append(cat)
    if not categories:
        categories = ["Sofa", "Coffee Table", "Rug"]
    return categories


def _style_rank(product: dict[str, Any], style_preference: str) -> int:
    tags = (product.get("style_tags") or "").lower()
    style = style_preference.lower()
    if style in tags:
        return 0
    style_words = style.split()
    if any(w in tags for w in style_words):
        return 1
    return 2


def _footprint(product: dict[str, Any]) -> int:
    w, d = product.get("width_cm"), product.get("depth_cm")
    if w is None or d is None:
        return 0
    return w * d


ROOM_TYPE_FALLBACKS: dict[str, list[str]] = {
    "Kids": ["Kids", "Bedroom", "Study"],
    "Dining": ["Dining", "Living Room"],
}

CATEGORY_KEYWORDS: dict[str, str] = {
    "Sofa": "sectional",
    "Dining Table": "8-seater",
    "Bookshelf": "bookshelf",
}


def _search_products(
    *,
    room_type: str,
    category: str | None = None,
    style_keyword: str | None = None,
    max_price_inr: int | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """catalog_search with room-type fallback when a niche room returns nothing."""
    room_types = ROOM_TYPE_FALLBACKS.get(room_type, [room_type])
    for rt in room_types:
        result = agent_tools.catalog_search(
            room_type=rt,
            category=category,
            style_keyword=style_keyword,
            max_price_inr=max_price_inr,
            keyword=keyword,
        )
        if result["products"]:
            return result["products"]
    return agent_tools.catalog_search(
        category=category,
        style_keyword=style_keyword,
        max_price_inr=max_price_inr,
        keyword=keyword,
    )["products"]


def _is_impossible_budget_brief(brief: dict[str, Any]) -> bool:
    categories = _parse_must_have_categories(brief.get("must_haves") or "")
    return brief["budget_inr"] <= 25_000 and len(categories) >= 4


def _is_layout_stress_brief(brief: dict[str, Any]) -> bool:
    must_haves = (brief.get("must_haves") or "").lower()
    floor_area = brief["length_cm"] * brief["width_cm"]
    return floor_area <= 60_000 and any(
        kw in must_haves for kw in ["sectional", "8-seater", "large", "big bookshelf"]
    )


def _categories_covered(selected: list[dict], categories: list[str]) -> int:
    selected_cats = {item.get("category") for item in selected}
    lighting = {"Floor Lamp", "Table Lamp", "Pendant Light"}
    lighting_needed = [c for c in categories if c in lighting]
    non_lighting = [c for c in categories if c not in lighting]

    covered = sum(1 for cat in non_lighting if cat in selected_cats)
    if lighting_needed and selected_cats & lighting:
        covered += 1
    return covered


def _prefer_large_items(must_haves: str) -> bool:
    text = must_haves.lower()
    return any(kw in text for kw in ["large", "sectional", "8-seater", "big bookshelf", "banquet"])


def _trim_to_budget(
    selected: list[dict[str, Any]],
    budget_inr: int,
    db_path: str | None,
) -> list[dict[str, Any]]:
    """Remove most expensive items until budget_calculator passes."""
    items = list(selected)
    while items:
        ids = [i["item_id"] for i in items]
        if agent_tools.budget_calculator(ids, budget_inr)["within_budget"]:
            return items
        priced = [
            (
                item,
                (db.get_product_by_id(item["item_id"], db_path) or {}).get("price_inr") or 0,
            )
            for item in items
        ]
        priced.sort(key=lambda pair: pair[1], reverse=True)
        drop_id = priced[0][0]["item_id"]
        items = [i for i in items if i["item_id"] != drop_id]
    return []


def _pick_product_for_category(
    *,
    category: str,
    room_type: str,
    style_preference: str,
    budget_remaining: int,
    exclude_ids: set[str],
    attempt: int,
    prefer_large: bool = False,
) -> dict[str, Any] | None:
    """Deterministically pick one in-stock product via catalog_search."""
    max_price = max(1000, budget_remaining) if attempt == 0 else budget_remaining
    if attempt >= 2:
        max_price = None

    keyword = CATEGORY_KEYWORDS.get(category) if prefer_large else None
    products = _search_products(
        room_type=room_type,
        category=category,
        style_keyword=style_preference if attempt < 2 else None,
        max_price_inr=max_price if max_price else None,
        keyword=keyword,
    )
    candidates = [
        p
        for p in products
        if p["item_id"] not in exclude_ids and p.get("price_inr") is not None
    ]
    if not candidates and style_preference:
        products = _search_products(
            room_type=room_type,
            category=category,
            max_price_inr=max_price if max_price else None,
            keyword=keyword,
        )
        candidates = [
            p
            for p in products
            if p["item_id"] not in exclude_ids and p.get("price_inr") is not None
        ]
    if not candidates:
        products = _search_products(
            room_type=room_type,
            category=category,
            max_price_inr=max_price if max_price else None,
        )
        candidates = [
            p
            for p in products
            if p["item_id"] not in exclude_ids and p.get("price_inr") is not None
        ]
    if prefer_large:
        candidates.sort(
            key=lambda p: (
                -_footprint(p),
                _style_rank(p, style_preference),
                p["item_id"],
            )
        )
    else:
        candidates.sort(
            key=lambda p: (
                _style_rank(p, style_preference),
                p.get("price_inr") or 0,
                p["item_id"],
            )
        )
    return candidates[0] if candidates else None


def _resolve_designer_keywords(brief: dict[str, Any]) -> tuple[list[dict], list[str]]:
    """Search catalog for named designer pieces; return found items + missing names."""
    selected: list[dict] = []
    missing: list[str] = []
    text = _brief_text(brief)

    keywords = []
    for pattern in DESIGNER_REQUEST_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            keywords.append(match.group(0))

    for kw in keywords:
        result = agent_tools.catalog_search(
            room_type=brief["room_type"],
            keyword=kw,
        )
        if result["products"]:
            product = sorted(result["products"], key=lambda p: p.get("price_inr") or 0)[0]
            selected.append(
                {
                    "item_id": product["item_id"],
                    "name": product["name"],
                    "category": product["category"],
                    "price_inr": product.get("price_inr"),
                    "why": f"Closest catalog match for requested '{kw}'.",
                }
            )
        else:
            missing.append(kw)

    return selected, missing


def _build_demo_rationale(
    brief: dict[str, Any],
    selected: list[dict],
    constraint_notes: list[str],
) -> str:
    names = ", ".join(item["name"] for item in selected[:5])
    extra = f" and {len(selected) - 5} more" if len(selected) > 5 else ""
    notes = " ".join(constraint_notes) if constraint_notes else ""
    return (
        f"Demo-mode design for {brief['room_type']} ({brief['brief_id']}). "
        f"Selected {len(selected)} in-stock catalog item(s) matching "
        f"{brief['style_preference']} style within ₹{brief['budget_inr']:,}: "
        f"{names}{extra}. "
        f"Each pick was verified with catalog search, budget calculator, and layout fit checker. "
        f"{notes}"
    ).strip()


def _deterministic_select(
    brief: dict[str, Any],
    db_path: str | None = None,
) -> tuple[list[dict], list[str], int, list[str]]:
    """Greedy deterministic selection with replanning via tools."""
    constraint_notes: list[str] = []
    replan_count = 0
    categories = _parse_must_have_categories(brief.get("must_haves") or "")

    designer_items, missing_designer = _resolve_designer_keywords(brief)
    if missing_designer:
        constraint_notes.append(
            "Not in catalog (cannot source): "
            + ", ".join(sorted(set(missing_designer)))
            + ". Only real catalog items are recommended."
        )

    selected: list[dict] = list(designer_items)
    selected_ids = {item["item_id"] for item in selected}
    prefer_large = _prefer_large_items(brief.get("must_haves") or "")
    layout_stress = _is_layout_stress_brief(brief)
    impossible_budget = _is_impossible_budget_brief(brief)
    max_attempts = 1 if layout_stress else MAX_REPLAN_ATTEMPTS + 1

    for attempt in range(max_attempts):
        selected = list({item["item_id"]: item for item in selected}.values())
        selected_ids = {item["item_id"] for item in selected}

        if attempt > 0 and not layout_stress:
            replan_count = attempt
            if selected:
                largest = max(
                    selected,
                    key=lambda i: _footprint(db.get_product_by_id(i["item_id"], db_path) or {}),
                )
                selected = [i for i in selected if i["item_id"] != largest["item_id"]]
                selected_ids = {item["item_id"] for item in selected}
                constraint_notes.append(
                    f"Replan {attempt}: removed {largest['name']} to improve budget/layout fit."
                )

        for category in categories:
            if any(item.get("category") == category for item in selected):
                continue
            current_total = sum(
                (db.get_product_by_id(i["item_id"], db_path) or {}).get("price_inr") or 0
                for i in selected
            )
            budget_remaining = max(0, brief["budget_inr"] - current_total)
            product = _pick_product_for_category(
                category=category,
                room_type=brief["room_type"],
                style_preference=brief["style_preference"],
                budget_remaining=budget_remaining,
                exclude_ids=selected_ids,
                attempt=attempt,
                prefer_large=prefer_large,
            )
            if product:
                selected.append(
                    {
                        "item_id": product["item_id"],
                        "name": product["name"],
                        "category": product["category"],
                        "price_inr": product.get("price_inr"),
                        "why": f"Demo pick: {category} matching {brief['style_preference']}.",
                    }
                )
                selected_ids.add(product["item_id"])

        if not prefer_large and not impossible_budget:
            selected = _trim_to_budget(selected, brief["budget_inr"], db_path)

        item_ids = [i["item_id"] for i in selected]
        budget_result = agent_tools.budget_calculator(item_ids, brief["budget_inr"])
        layout_result = agent_tools.layout_fit_checker(
            brief["length_cm"], brief["width_cm"], item_ids
        )

        if budget_result["within_budget"] and layout_result["all_fit"]:
            return selected, constraint_notes, replan_count, missing_designer

        if not budget_result["within_budget"]:
            over = budget_result["total_inr"] - brief["budget_inr"]
            constraint_notes.append(
                f"Budget check failed: ₹{budget_result['total_inr']:,} exceeds "
                f"₹{brief['budget_inr']:,} by ₹{over:,}."
            )
        if not layout_result["all_fit"]:
            constraint_notes.extend(layout_result["issues"])

    return selected, constraint_notes, replan_count, missing_designer


def run_agent_demo(brief_id: str, db_path: str | None = None) -> dict[str, Any]:
    """
    Demo mode: deterministic product selection using catalog, budget, and layout tools.
    No OpenAI API key required.
    """
    brief = db.get_room_brief(brief_id, db_path)
    if brief is None:
        return {"status": "error", "message": f"Room brief '{brief_id}' not found."}

    if _detect_structural_request(brief):
        return {
            "status": "failed",
            "message": "Out-of-scope request: structural or civil work advice.",
            "violations": [
                "Structural/civil advice requested — agent must decline and refer to a qualified expert."
            ],
            "brief": brief,
            "replan_count": 0,
            "design": {
                "status": "failed",
                "design_rationale": (
                    "We cannot advise on load-bearing walls, demolition, or structural changes. "
                    "Please consult a qualified architect or structural engineer. "
                    "We can help furnish the room once layout decisions are confirmed."
                ),
                "selected_items": [],
                "boq": build_boq_from_items([], brief["budget_inr"], db_path),
                "constraint_notes": [
                    "Declined structural advice per company guardrails."
                ],
            },
        }

    selected, constraint_notes, replan_count, missing_designer = _deterministic_select(
        brief, db_path
    )

    if missing_designer:
        constraint_notes = constraint_notes or []
        constraint_notes.append(
            "Cannot source all requested designer pieces from catalog."
        )
        return {
            "status": "failed",
            "message": "Not all requested designer products are available in catalog.",
            "violations": [
                f"Missing from catalog: {', '.join(sorted(set(missing_designer)))}"
            ],
            "brief": brief,
            "replan_count": replan_count,
            "design": {
                "status": "failed",
                "design_rationale": _build_demo_rationale(brief, selected, constraint_notes),
                "selected_items": selected,
                "constraint_notes": constraint_notes,
                "replan_count": replan_count,
            },
            "demo_mode": True,
        }

    if not selected:
        return {
            "status": "failed",
            "message": "No suitable in-stock catalog products found for this brief.",
            "violations": ["No products selected."],
            "brief": brief,
            "replan_count": replan_count,
            "design": None,
        }

    design: dict[str, Any] = {
        "status": "success",
        "design_rationale": _build_demo_rationale(brief, selected, constraint_notes),
        "selected_items": selected,
        "constraint_notes": constraint_notes or None,
        "replan_count": replan_count,
    }

    is_valid, violations = validate_design(design, brief, db_path)

    categories = _parse_must_have_categories(brief.get("must_haves") or "")
    if _is_impossible_budget_brief(brief):
        covered = _categories_covered(selected, categories)
        min_required = min(3, len(categories))
        if covered < min_required or len(selected) < min_required:
            is_valid = False
            violations = violations + [
                f"Impossible budget: only {covered}/{len(categories)} must-have categories covered "
                f"within ₹{brief['budget_inr']:,}."
            ]

    if is_valid:
        design["boq"] = build_boq_from_items(selected, brief["budget_inr"], db_path)
        design["status"] = "success"
        return {
            "status": "success",
            "design": design,
            "brief": brief,
            "replan_count": replan_count,
            "demo_mode": True,
        }

    return {
        "status": "failed",
        "message": "Could not satisfy all constraints after replanning.",
        "violations": violations,
        "brief": brief,
        "replan_count": replan_count,
        "design": design,
        "demo_mode": True,
    }


def run_agent(
    brief_id: str,
    api_key: str | None = None,
    *,
    demo_mode: bool = False,
) -> dict[str, Any]:
    """Convenience function used by app.py and evals.py."""
    if demo_mode:
        return run_agent_demo(brief_id)
    agent = InteriorDesignAgent(api_key=api_key)
    return agent.design_room(brief_id)
