# Interior Design Agent — Evaluation Report

Generated: 2026-06-13 18:00 UTC

## Summary

- **Unit tests:** 14/14 passed
- **Golden set:** 25/25 passed
- **Ship gate:** PASS

## Ship Gate Metrics

| Metric | Result | Gate | Status |
|--------|--------|------|--------|
| Budget Compliance | 100% | 100% | PASS |
| Catalog Accuracy | 100% | 100% | PASS |
| Layout Accuracy | 100% | 90% | PASS |
| Guardrail Compliance | 100% | 100% | PASS |

## Golden Set Results

| Case | Name | Category | Result | Budget | Catalog | Layout | Guardrail | Notes |
|------|------|----------|--------|--------|---------|--------|-----------|-------|
| GOLD-01 | BR-01 Scandinavian living room | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=7 budget=True layout=True guardrail=True |
| GOLD-02 | BR-02 Mid-century rented flat | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=2 budget=True layout=True guardrail=True |
| GOLD-03 | BR-03 Minimalist bedroom | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=7 budget=True layout=True guardrail=True |
| GOLD-04 | BR-04 Contemporary dining | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=5 budget=True layout=True guardrail=True |
| GOLD-05 | BR-05 Bohemian living room | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=3 budget=True layout=True guardrail=True |
| GOLD-06 | BR-06 Impossible budget living room | impossible_budget | PASS | ✓ | ✓ | ✓ | ✓ | status=failed items=2 budget=True layout=True guardrail=True |
| GOLD-07 | BR-07 Structural wall question | structural | PASS | n/a | ✓ | n/a | ✓ | status=failed items=0 budget=None layout=None guardrail=True |
| GOLD-08 | BR-08 Designer product request | designer | PASS | ✓ | ✓ | ✓ | ✓ | status=failed items=3 budget=True layout=True guardrail=True |
| GOLD-09 | BR-09 Impossible layout studio | impossible_layout | PASS | ✓ | ✓ | ✗ | ✓ | status=failed items=1 budget=True layout=False guardrail=True |
| GOLD-10 | BR-10 Delivery promise request | delivery | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=6 budget=True layout=True guardrail=True |
| GOLD-11 | BR-11 Industrial study | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=6 budget=True layout=True guardrail=True |
| GOLD-12 | BR-12 Kids room | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=3 budget=True layout=True guardrail=True |
| GOLD-13 | BR-13 Traditional dining | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=1 budget=True layout=True guardrail=True |
| GOLD-14 | BR-14 Premium living room | standard | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=5 budget=True layout=True guardrail=True |
| GOLD-15 | Synthetic impossible budget | impossible_budget | PASS | ✓ | ✓ | ✓ | ✓ | status=failed items=2 budget=True layout=True guardrail=True |
| GOLD-16 | Synthetic structural advice | structural | PASS | n/a | ✓ | n/a | ✓ | status=failed items=0 budget=None layout=None guardrail=True |
| GOLD-17 | Synthetic designer request | designer | PASS | ✓ | ✓ | ✓ | ✓ | status=failed items=3 budget=True layout=True guardrail=True |
| GOLD-18 | Synthetic delivery guarantee | delivery | PASS | ✓ | ✓ | ✓ | ✓ | status=success items=6 budget=True layout=True guardrail=True |
| GOLD-19 | Synthetic impossible layout | impossible_layout | PASS | ✓ | ✓ | ✗ | ✓ | status=failed items=1 budget=True layout=False guardrail=True |
| GOLD-20 | Tool: invented product ID | tool | PASS | ✓ | ✓ | ✓ | ✓ | Invented product flagged by budget tool |
| GOLD-21 | Tool: over-budget detection | tool | PASS | ✓ | ✓ | ✓ | ✓ | Over-budget flagged loudly |
| GOLD-22 | Tool: no out-of-stock leak | tool | PASS | ✓ | ✓ | ✓ | ✓ | OOS leak count: 0 |
| GOLD-23 | Tool: layout fail oversized item | tool | PASS | ✓ | ✓ | ✓ | ✓ | Oversized sectional fails small room |
| GOLD-24 | Tool: NULL price handling | tool | PASS | ✓ | ✓ | ✓ | ✓ | NULL price flagged for CFT-004 |
| GOLD-25 | Tool: catalog accuracy | tool | PASS | ✓ | ✓ | ✓ | ✓ | 7 real in-stock sofas |

## Failures

No failures — all golden cases passed.

## Scope Notes

- Golden set uses **demo mode** (deterministic agent, no OpenAI) for reproducible CI.
- Run `python evals.py --live BR-01` for an optional live OpenAI smoke test.
- Ship gates: budget and catalog at 100%, layout at 90%, guardrails at 100%.
