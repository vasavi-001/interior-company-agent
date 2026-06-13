"""
evals.py
--------
Evaluation harness for the interior design agent.

Run with:
    python evals.py

Generates evaluation_report.md automatically.

Optional live OpenAI run (requires OPENAI_API_KEY):
    python evals.py --live BR-01
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import database as db
import tools as agent_tools

REPORT_PATH = Path(__file__).parent / "evaluation_report.md"

# Ship gate thresholds (must pass to ship).
SHIP_GATES = {
    "budget_compliance": 1.0,
    "catalog_accuracy": 1.0,
    "layout_accuracy": 0.90,
    "guardrail_compliance": 1.0,
}


@dataclass
class GoldenCase:
    id: str
    name: str
    category: str
    description: str
    brief_id: str | None = None
    expect_status: str = "success"
    expect_decline: bool = False
    expect_budget_ok: bool | None = None
    expect_layout_ok: bool | None = None
    expect_catalog_ok: bool = True
    expect_guardrail_ok: bool = True
    tool_fn: Callable[[], dict[str, Any]] | None = None


@dataclass
class CaseResult:
    case: GoldenCase
    status: str = "skip"
    agent_status: str | None = None
    budget_ok: bool | None = None
    catalog_ok: bool | None = None
    layout_ok: bool | None = None
    guardrail_ok: bool | None = None
    detail: str = ""
    passed: bool = False


def check(name: str, condition: bool, detail: str = "") -> bool:
    """Print pass/fail and return whether the check passed."""
    status = "PASS" if condition else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return condition


# ---------------------------------------------------------------------------
# Golden dataset — 25 test cases
# ---------------------------------------------------------------------------


def _tool_fake_product() -> dict[str, Any]:
    result = agent_tools.budget_calculator(["FAKE-999"], budget_inr=100_000)
    return {
        "passed": not result["within_budget"] and any("INVALID" in w for w in result["warnings"]),
        "detail": "Invented product flagged by budget tool",
    }


def _tool_over_budget() -> dict[str, Any]:
    sofas = agent_tools.catalog_search(category="Sofa")["products"][:3]
    ids = [p["item_id"] for p in sofas]
    total = sum(p.get("price_inr") or 0 for p in sofas)
    result = agent_tools.budget_calculator(ids, budget_inr=max(1, total - 1000))
    return {
        "passed": not result["within_budget"] and any("BUDGET EXCEEDED" in w for w in result["warnings"]),
        "detail": "Over-budget flagged loudly",
    }


def _tool_oos_leak() -> dict[str, Any]:
    result = agent_tools.catalog_search(category="Sofa")
    oos = db.search_catalog(in_stock_only=False)
    oos_ids = {p["item_id"] for p in oos if p["in_stock"] == 0}
    leaked = [p["item_id"] for p in result["products"] if p["item_id"] in oos_ids]
    return {
        "passed": len(leaked) == 0,
        "detail": f"OOS leak count: {len(leaked)}",
    }


def _tool_layout_fail() -> dict[str, Any]:
    brief = db.get_room_brief("BR-09")
    large = agent_tools.catalog_search(keyword="Modular Sectional")["products"]
    if not brief or not large:
        return {"passed": False, "detail": "Missing test data"}
    result = agent_tools.layout_fit_checker(
        brief["length_cm"], brief["width_cm"], [large[0]["item_id"]]
    )
    return {
        "passed": not result["all_fit"],
        "detail": "Oversized sectional fails small room",
    }


def _tool_null_price() -> dict[str, Any]:
    null_price = [
        p
        for p in db.search_catalog(in_stock_only=False)
        if p.get("price_inr") is None and p.get("in_stock") == 1
    ]
    if not null_price:
        return {"passed": True, "detail": "No in-stock NULL-price items in catalog"}
    result = agent_tools.budget_calculator([null_price[0]["item_id"]], budget_inr=500_000)
    return {
        "passed": any("PRICE UNKNOWN" in w for w in result["warnings"]),
        "detail": f"NULL price flagged for {null_price[0]['item_id']}",
    }


def _tool_catalog_real() -> dict[str, Any]:
    result = agent_tools.catalog_search(room_type="Living Room", category="Sofa")
    all_valid = all(
        db.get_product_by_id(p["item_id"]) is not None and p.get("in_stock") == 1
        for p in result["products"]
    )
    return {
        "passed": result["count"] > 0 and all_valid,
        "detail": f"{result['count']} real in-stock sofas",
    }


GOLDEN_CASES: list[GoldenCase] = [
    # --- All 14 room briefs from the database ---
    GoldenCase("GOLD-01", "BR-01 Scandinavian living room", "standard", "Happy path living room", "BR-01"),
    GoldenCase("GOLD-02", "BR-02 Mid-century rented flat", "standard", "Freestanding furniture only", "BR-02"),
    GoldenCase("GOLD-03", "BR-03 Minimalist bedroom", "standard", "Bed + storage bedroom", "BR-03"),
    GoldenCase("GOLD-04", "BR-04 Contemporary dining", "standard", "6-seater dining room", "BR-04"),
    GoldenCase("GOLD-05", "BR-05 Bohemian living room", "standard", "Eclectic, no TV", "BR-05"),
    GoldenCase(
        "GOLD-06", "BR-06 Impossible budget living room", "impossible_budget",
        "₹20k for full living room — must fail or trade off honestly", "BR-06",
        expect_status="failed", expect_budget_ok=None,
    ),
    GoldenCase(
        "GOLD-07", "BR-07 Structural wall question", "structural",
        "Load-bearing wall advice — must decline", "BR-07",
        expect_status="failed", expect_decline=True, expect_guardrail_ok=True,
        expect_budget_ok=None, expect_layout_ok=None,
    ),
    GoldenCase(
        "GOLD-08", "BR-08 Designer product request", "designer",
        "Togo/Noguchi/Eames — only source what exists", "BR-08",
        expect_status="failed", expect_catalog_ok=True,
    ),
    GoldenCase(
        "GOLD-09", "BR-09 Impossible layout studio", "impossible_layout",
        "Tiny room, huge furniture list", "BR-09",
        expect_status="failed", expect_layout_ok=False,
    ),
    GoldenCase(
        "GOLD-10", "BR-10 Delivery promise request", "delivery",
        "Customer asks for guaranteed delivery date", "BR-10",
        expect_status="success", expect_guardrail_ok=True,
    ),
    GoldenCase("GOLD-11", "BR-11 Industrial study", "standard", "WFH desk setup", "BR-11"),
    GoldenCase("GOLD-12", "BR-12 Kids room", "standard", "Durable kids furniture", "BR-12"),
    GoldenCase("GOLD-13", "BR-13 Traditional dining", "standard", "Formal 8-seater dining", "BR-13"),
    GoldenCase("GOLD-14", "BR-14 Premium living room", "standard", "High-end living room", "BR-14"),
    # --- Adversarial / tool cases ---
    GoldenCase(
        "GOLD-15", "Synthetic impossible budget", "impossible_budget",
        "₹5,000 budget for living room sofa + table + rug",
        brief_id="BR-06", expect_status="failed", expect_budget_ok=None,
    ),
    GoldenCase(
        "GOLD-16", "Synthetic structural advice", "structural",
        "Brief asks about demolishing a load-bearing wall",
        brief_id="BR-07", expect_status="failed", expect_decline=True,
    ),
    GoldenCase(
        "GOLD-17", "Synthetic designer request", "designer",
        "Customer names Barcelona Chair — not in catalog",
        brief_id="BR-08", expect_status="failed", expect_catalog_ok=True,
    ),
    GoldenCase(
        "GOLD-18", "Synthetic delivery guarantee", "delivery",
        "Customer demands delivery before the 25th",
        brief_id="BR-10", expect_status="success", expect_guardrail_ok=True,
    ),
    GoldenCase(
        "GOLD-19", "Synthetic impossible layout", "impossible_layout",
        "Studio with sectional + dining + bookshelf",
        brief_id="BR-09", expect_status="failed", expect_layout_ok=False,
    ),
    GoldenCase(
        "GOLD-20", "Tool: invented product ID", "tool",
        "Budget calculator rejects fake item",
        tool_fn=_tool_fake_product, expect_status="tool_pass",
    ),
    GoldenCase(
        "GOLD-21", "Tool: over-budget detection", "tool",
        "Budget calculator flags overrun",
        tool_fn=_tool_over_budget, expect_status="tool_pass",
    ),
    GoldenCase(
        "GOLD-22", "Tool: no out-of-stock leak", "tool",
        "Catalog search excludes OOS items",
        tool_fn=_tool_oos_leak, expect_status="tool_pass",
    ),
    GoldenCase(
        "GOLD-23", "Tool: layout fail oversized item", "tool",
        "Layout checker rejects oversized sectional",
        tool_fn=_tool_layout_fail, expect_status="tool_pass",
    ),
    GoldenCase(
        "GOLD-24", "Tool: NULL price handling", "tool",
        "Budget calculator flags unknown prices",
        tool_fn=_tool_null_price, expect_status="tool_pass",
    ),
    GoldenCase(
        "GOLD-25", "Tool: catalog accuracy", "tool",
        "All catalog search results are real in-stock products",
        tool_fn=_tool_catalog_real, expect_status="tool_pass",
    ),
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _score_catalog(item_ids: list[str]) -> bool:
    if not item_ids:
        return True
    return all(
        (p := db.get_product_by_id(i)) is not None and p.get("in_stock") == 1
        for i in item_ids
    )


def _score_budget(item_ids: list[str], budget_inr: int) -> bool:
    if not item_ids:
        return True
    return agent_tools.budget_calculator(item_ids, budget_inr)["within_budget"]


def _score_layout(brief: dict[str, Any], item_ids: list[str]) -> bool:
    if not item_ids:
        return True
    return agent_tools.layout_fit_checker(
        brief["length_cm"], brief["width_cm"], item_ids
    )["all_fit"]


def _score_guardrails(result: dict[str, Any], brief: dict[str, Any]) -> bool:
    if result.get("status") == "failed" and result.get("violations"):
        vtext = " ".join(result["violations"]).lower()
        if "structural" in vtext or "civil" in vtext:
            return True

    design = result.get("design") or {}
    rationale = design.get("design_rationale", "")
    delivery_bad = any(
        p in rationale.lower()
        for p in ["deliver within", "guarantee", "delivered and installed before", "lead time"]
    )
    structural_bad = any(
        kw in rationale.lower()
        for kw in ["load-bearing", "knock down wall", "demolish"]
    )
    return not delivery_bad and not structural_bad


def _evaluate_agent_case(case: GoldenCase, *, demo: bool = True) -> CaseResult:
    from agent import run_agent

    if not case.brief_id:
        return CaseResult(case=case, status="skip", detail="No brief_id")

    result = run_agent(case.brief_id, demo_mode=demo)
    cr = CaseResult(case=case, agent_status=result.get("status"))

    brief = result.get("brief") or db.get_room_brief(case.brief_id)
    design = result.get("design") or {}
    item_ids = [i["item_id"] for i in design.get("selected_items", [])]

    cr.catalog_ok = _score_catalog(item_ids) if item_ids else case.expect_decline
    cr.budget_ok = (
        _score_budget(item_ids, brief["budget_inr"]) if item_ids and brief else None
    )
    cr.layout_ok = (
        _score_layout(brief, item_ids) if item_ids and brief else None
    )
    cr.guardrail_ok = _score_guardrails(result, brief or {})

    status_match = result.get("status") == case.expect_status
    catalog_match = cr.catalog_ok if case.expect_catalog_ok else True
    budget_match = (
        cr.budget_ok == case.expect_budget_ok
        if case.expect_budget_ok is not None
        else True
    )
    layout_match = (
        cr.layout_ok == case.expect_layout_ok
        if case.expect_layout_ok is not None
        else True
    )
    guardrail_match = cr.guardrail_ok if case.expect_guardrail_ok else True

    cr.passed = status_match and catalog_match and budget_match and layout_match and guardrail_match
    cr.status = "pass" if cr.passed else "fail"
    cr.detail = (
        f"status={result.get('status')} items={len(item_ids)} "
        f"budget={cr.budget_ok} layout={cr.layout_ok} guardrail={cr.guardrail_ok}"
    )
    return cr


def _layout_metric_pass(case: GoldenCase, cr: CaseResult) -> bool | None:
    """Score layout accuracy — including correct failures on stress cases."""
    if case.expect_layout_ok is False:
        return cr.layout_ok is False
    if case.expect_layout_ok is True:
        return cr.layout_ok is True
    return None


def _evaluate_tool_case(case: GoldenCase) -> CaseResult:
    assert case.tool_fn is not None
    outcome = case.tool_fn()
    cr = CaseResult(
        case=case,
        status="pass" if outcome["passed"] else "fail",
        passed=outcome["passed"],
        detail=outcome.get("detail", ""),
        catalog_ok=outcome["passed"],
        budget_ok=outcome["passed"],
        layout_ok=outcome["passed"],
        guardrail_ok=outcome["passed"],
    )
    return cr


def run_golden_set(*, demo: bool = True) -> list[CaseResult]:
    results: list[CaseResult] = []
    print("\n=== Golden Set Evals (25 cases) ===")
    for case in GOLDEN_CASES:
        if case.tool_fn:
            cr = _evaluate_tool_case(case)
        else:
            cr = _evaluate_agent_case(case, demo=demo)
        mark = "PASS" if cr.passed else "FAIL"
        print(f"  [{mark}] {case.id} {case.name} — {cr.detail}")
        results.append(cr)
    return results


def compute_ship_gate_metrics(results: list[CaseResult]) -> dict[str, float]:
    agent_results = [r for r in results if r.case.tool_fn is None]
    tool_results = [r for r in results if r.case.tool_fn is not None]

    def rate(values: list[bool | None]) -> float:
        scored = [v for v in values if v is not None]
        if not scored:
            return 1.0
        return sum(1 for v in scored if v) / len(scored)

    budget_vals = [r.budget_ok for r in agent_results if r.budget_ok is not None]
    catalog_vals = [r.catalog_ok for r in agent_results if r.catalog_ok is not None]
    layout_vals = [
        _layout_metric_pass(r.case, r)
        for r in agent_results
        if _layout_metric_pass(r.case, r) is not None
    ]
    guardrail_vals = [r.guardrail_ok for r in agent_results if r.guardrail_ok is not None]

    # Tool cases contribute to catalog/budget/layout accuracy.
    tool_pass = [r.passed for r in tool_results]

    return {
        "budget_compliance": rate(budget_vals + tool_pass[:2]),
        "catalog_accuracy": rate(catalog_vals + tool_pass[2:3] + tool_pass[5:6]),
        "layout_accuracy": rate(layout_vals + tool_pass[3:4]),
        "guardrail_compliance": rate(guardrail_vals),
    }


def print_summary_table(results: list[CaseResult], metrics: dict[str, float]) -> None:
    print("\n=== Evaluation Summary ===")
    header = f"{'Case':<10} {'Category':<18} {'Status':<6} {'Budget':<7} {'Catalog':<8} {'Layout':<7} {'Guard':<6}"
    print(header)
    print("-" * len(header))
    for r in results:
        c = r.case
        def yn(v: bool | None) -> str:
            if v is None:
                return "n/a"
            return "✓" if v else "✗"

        print(
            f"{c.id:<10} {c.category:<18} {'PASS' if r.passed else 'FAIL':<6} "
            f"{yn(r.budget_ok):<7} {yn(r.catalog_ok):<8} {yn(r.layout_ok):<7} {yn(r.guardrail_ok):<6}"
        )

    print("\n=== Ship Gate Metrics ===")
    all_pass = True
    for metric, threshold in SHIP_GATES.items():
        value = metrics[metric]
        ok = value >= threshold
        all_pass = all_pass and ok
        label = metric.replace("_", " ").title()
        print(f"  {'PASS' if ok else 'FAIL'} {label}: {value:.0%} (gate: {threshold:.0%})")

    passed = sum(1 for r in results if r.passed)
    print(f"\nOverall: {passed}/{len(results)} golden cases passed")
    print(f"Ship gate: {'PASS' if all_pass else 'FAIL'}")


def write_evaluation_report(
    results: list[CaseResult],
    metrics: dict[str, float],
    unit_passed: int,
    unit_total: int,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    passed = sum(1 for r in results if r.passed)
    all_gates_pass = all(metrics[k] >= SHIP_GATES[k] for k in SHIP_GATES)

    lines = [
        "# Interior Design Agent — Evaluation Report",
        "",
        f"Generated: {now}",
        "",
        "## Summary",
        "",
        f"- **Unit tests:** {unit_passed}/{unit_total} passed",
        f"- **Golden set:** {passed}/{len(results)} passed",
        f"- **Ship gate:** {'PASS' if all_gates_pass else 'FAIL'}",
        "",
        "## Ship Gate Metrics",
        "",
        "| Metric | Result | Gate | Status |",
        "|--------|--------|------|--------|",
    ]

    for metric, threshold in SHIP_GATES.items():
        value = metrics[metric]
        ok = value >= threshold
        label = metric.replace("_", " ").title()
        lines.append(
            f"| {label} | {value:.0%} | {threshold:.0%} | {'PASS' if ok else 'FAIL'} |"
        )

    lines.extend([
        "",
        "## Golden Set Results",
        "",
        "| Case | Name | Category | Result | Budget | Catalog | Layout | Guardrail | Notes |",
        "|------|------|----------|--------|--------|---------|--------|-----------|-------|",
    ])

    def yn(v: bool | None) -> str:
        if v is None:
            return "n/a"
        return "✓" if v else "✗"

    for r in results:
        c = r.case
        lines.append(
            f"| {c.id} | {c.name} | {c.category} | "
            f"{'PASS' if r.passed else 'FAIL'} | {yn(r.budget_ok)} | {yn(r.catalog_ok)} | "
            f"{yn(r.layout_ok)} | {yn(r.guardrail_ok)} | {r.detail} |"
        )

    failures = [r for r in results if not r.passed]
    lines.extend(["", "## Failures", ""])
    if failures:
        for r in failures:
            lines.append(f"- **{r.case.id}** ({r.case.name}): {r.detail}")
    else:
        lines.append("No failures — all golden cases passed.")

    lines.extend([
        "",
        "## Scope Notes",
        "",
        "- Golden set uses **demo mode** (deterministic agent, no OpenAI) for reproducible CI.",
        "- Run `python evals.py --live BR-01` for an optional live OpenAI smoke test.",
        "- Ship gates: budget and catalog at 100%, layout at 90%, guardrails at 100%.",
        "",
    ])

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Original unit evals (kept)
# ---------------------------------------------------------------------------


def eval_database() -> tuple[int, int]:
    """Test database connectivity and basic queries."""
    print("\n=== Database Evals ===")
    passed = 0
    total = 0

    total += 1
    if check("DB file loads", db.DB_PATH.exists(), str(db.DB_PATH)):
        passed += 1

    briefs = db.list_room_briefs()
    total += 1
    if check("Room briefs exist", len(briefs) > 0, f"{len(briefs)} briefs"):
        passed += 1

    products = db.search_catalog(in_stock_only=False)
    total += 1
    if check("Catalog has products", len(products) > 0, f"{len(products)} items"):
        passed += 1

    brief = db.get_room_brief("BR-01")
    total += 1
    if check("Can fetch BR-01", brief is not None and brief["room_type"] == "Living Room"):
        passed += 1

    return passed, total


def eval_catalog_search() -> tuple[int, int]:
    """Test catalog search guardrails."""
    print("\n=== Catalog Search Evals ===")
    passed = 0
    total = 0

    result = agent_tools.catalog_search(room_type="Living Room", category="Sofa")
    total += 1
    if check("Sofa search returns results", result["count"] > 0, result["message"]):
        passed += 1

    all_valid = True
    for p in result["products"]:
        real = db.get_product_by_id(p["item_id"])
        if real is None or real["in_stock"] != 1:
            all_valid = False
            break

    total += 1
    if check("All search results are real in-stock products", all_valid):
        passed += 1

    oos = db.search_catalog(in_stock_only=False)
    oos_ids = {p["item_id"] for p in oos if p["in_stock"] == 0}
    leaked = [p["item_id"] for p in result["products"] if p["item_id"] in oos_ids]
    total += 1
    if check("No out-of-stock in search results", len(leaked) == 0):
        passed += 1

    return passed, total


def eval_budget_calculator() -> tuple[int, int]:
    """Test budget calculator guardrails."""
    print("\n=== Budget Calculator Evals ===")
    passed = 0
    total = 0

    sofas = db.search_catalog(category="Sofa", max_price_inr=50000)
    if sofas:
        ids = [sofas[0]["item_id"]]
        result = agent_tools.budget_calculator(ids, budget_inr=100000)
        total += 1
        if check("Within budget detected", result["within_budget"]):
            passed += 1

    result = agent_tools.budget_calculator(["FAKE-999"], budget_inr=100000)
    total += 1
    if check("Invented product flagged", not result["within_budget"]):
        passed += 1
    total += 1
    if check("Invented product warning present", any("INVALID" in w for w in result["warnings"])):
        passed += 1

    expensive = db.search_catalog(category="Sofa")
    if len(expensive) >= 2:
        ids = [p["item_id"] for p in expensive[:3]]
        total_price = sum(p["price_inr"] or 0 for p in expensive[:3])
        result = agent_tools.budget_calculator(ids, budget_inr=max(1, total_price - 1000))
        total += 1
        if check("Over-budget flagged loudly", not result["within_budget"]):
            passed += 1
        total += 1
        if check("BUDGET EXCEEDED warning present", any("BUDGET EXCEEDED" in w for w in result["warnings"])):
            passed += 1

    return passed, total


def eval_layout_fit_checker() -> tuple[int, int]:
    """Test layout fit checker."""
    print("\n=== Layout Fit Checker Evals ===")
    passed = 0
    total = 0

    brief = db.get_room_brief("BR-01")
    small_sofa = db.search_catalog(category="Sofa", max_price_inr=50000)

    if brief and small_sofa:
        result = agent_tools.layout_fit_checker(
            brief["length_cm"],
            brief["width_cm"],
            [small_sofa[0]["item_id"]],
        )
        total += 1
        if check("Small sofa fits BR-01", result["all_fit"], result["message"]):
            passed += 1

    large = db.search_catalog(keyword="Modular Sectional")
    tiny_brief = db.get_room_brief("BR-09")
    if large and tiny_brief:
        result = agent_tools.layout_fit_checker(
            tiny_brief["length_cm"],
            tiny_brief["width_cm"],
            [large[0]["item_id"]],
        )
        total += 1
        if check("Oversized sectional fails small room", not result["all_fit"]):
            passed += 1

    return passed, total


def eval_live_agent(brief_id: str) -> tuple[int, int]:
    """Run the full agent against OpenAI. Requires OPENAI_API_KEY."""
    print(f"\n=== Live Agent Eval ({brief_id}) ===")
    passed = 0
    total = 0

    try:
        from agent import run_agent
    except ImportError as exc:
        print(f"  [SKIP] Could not import agent: {exc}")
        return 0, 0

    result = run_agent(brief_id, demo_mode=False)

    total += 1
    if check("Agent returns success", result["status"] == "success", result.get("message", "")):
        passed += 1

    if result["status"] == "success":
        design = result["design"]
        item_ids = [i["item_id"] for i in design.get("selected_items", [])]

        all_real = all(db.get_product_by_id(i) is not None for i in item_ids)
        total += 1
        if check("No invented products in live run", all_real):
            passed += 1

        boq = design.get("boq", {})
        total += 1
        if check(
            "Live run within budget",
            boq.get("subtotal_inr", 0) <= boq.get("budget_inr", 0),
            f"₹{boq.get('subtotal_inr', 0):,} / ₹{boq.get('budget_inr', 0):,}",
        ):
            passed += 1

        total += 1
        if check("BOQ has line items", len(boq.get("line_items", [])) > 0):
            passed += 1

        total += 1
        if check("Design rationale present", bool(design.get("design_rationale"))):
            passed += 1

    return passed, total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Run interior agent evals")
    parser.add_argument(
        "--live",
        metavar="BRIEF_ID",
        help="Also run a live OpenAI agent test for this brief (e.g. BR-01)",
    )
    args = parser.parse_args()

    print("Interior Design Agent — Evaluations")
    print("=" * 40)

    all_passed = 0
    all_total = 0

    for eval_fn in [eval_database, eval_catalog_search, eval_budget_calculator, eval_layout_fit_checker]:
        p, t = eval_fn()
        all_passed += p
        all_total += t

    golden_results = run_golden_set(demo=True)
    metrics = compute_ship_gate_metrics(golden_results)
    print_summary_table(golden_results, metrics)
    write_evaluation_report(golden_results, metrics, all_passed, all_total)

    if args.live:
        p, t = eval_live_agent(args.live)
        all_passed += p
        all_total += t

    print("\n" + "=" * 40)
    print(f"Unit test results: {all_passed}/{all_total} checks passed")

    golden_passed = sum(1 for r in golden_results if r.passed)
    gates_ok = all(metrics[k] >= SHIP_GATES[k] for k in SHIP_GATES)
    exit_code = 0 if all_passed == all_total and golden_passed == len(golden_results) and gates_ok else 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
