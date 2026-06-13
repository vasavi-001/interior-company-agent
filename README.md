# AI Interior Design Agent

## Overview

This project is a working AI Interior Design Agent built for the Interior Company × Blocks APM Build Challenge.

The agent takes a customer room brief and produces a budget-compliant interior design plan using only products available in the provided catalog database.

The solution prioritizes reliability, evaluation rigor, and explainability over UI complexity.

---

## Architecture

Customer Brief

↓

AI Agent

↓

Catalog Search Tool

↓

Budget Calculator Tool

↓

Layout Fit Checker Tool

↓

Validation Layer

↓

Design Plan & BOQ

---

## Features

* Uses only products present in the SQLite catalog
* Tracks budget and remaining balance
* Validates furniture fit against room dimensions
* Re-plans when constraints fail
* Refuses structural advice
* Refuses delivery guarantees
* Handles impossible budgets honestly
* Prevents catalog hallucinations
* Demo Mode available without API keys
* Evaluation harness with 25 golden test cases

---

## Tools

### Catalog Search Tool

Retrieves valid products from the catalog database.

### Budget Calculator Tool

Validates that recommendations remain within budget.

### Layout Fit Checker Tool

Ensures selected furniture fits room constraints.

---

## Evaluation

The project includes:

* 25 Golden Test Cases
* Budget Compliance Checks
* Catalog Accuracy Checks
* Layout Validation Checks
* Guardrail Validation Checks
* Ship Gate Metrics

---

## Setup

### Create Virtual Environment

python3 -m venv .venv

source .venv/bin/activate

### Install Dependencies

pip install -r requirements.txt

### Run Evaluation Harness

python evals.py

### Launch Application

streamlit run app.py

Enable Demo Mode in the sidebar if no API key is available.

---

## Project Structure

app.py — Streamlit UI

agent.py — Agent orchestration

database.py — SQLite access layer

tools.py — Catalog, Budget and Layout tools

evals.py — Evaluation harness

interior_company_catalog.db — Source-of-truth catalog

---

## Known Limitations

* Simplified layout heuristic
* No CAD-level spatial planning
* No visual rendering generation
* Single-room planning focus
* Style scoring remains partially subjective

## Submission Deliverables

### Deliverable A — Runnable MVP
- Streamlit application
- Demo Mode available without API keys

### Deliverable B — Evaluation Harness
- Golden Dataset (25 cases)
- Deterministic Scorers
- Ship Gate Metrics
- Results Report

See: evaluation_report.md

### Deliverable C — Decision Log
- Scope decisions
- AI tool usage
- Production risks
- Future roadmap

See: decision_log.md