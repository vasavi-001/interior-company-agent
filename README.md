# AI Interior Design Agent

## Overview

This project is a working AI Interior Design Agent built for the Interior Company × Blocks APM Build Challenge.

The agent takes a customer room brief and produces a budget-compliant interior design plan using only products available in the provided catalog database.

The solution prioritizes reliability, evaluation rigor, and explainability over UI complexity.

---

## Quick Demo

If the application does not run immediately, start with the setup steps below to create and activate the virtual environment.

1. Launch the application:

```bash
streamlit run app.py
```

2. Enable **Demo Mode** in the sidebar

3. Select:

```text
BR-01
```

4. Click:

```text
Generate Design
```

5. Review:

* Design rationale
* Product recommendations
* Budget summary
* Bill of Quantities (BOQ)

---

## Setup

### Create Virtual Environment

```bash
python3 -m venv .venv
```

### Activate Virtual Environment

```bash
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Evaluation Harness

```bash
python evals.py
```

### Launch Application

```bash
streamlit run app.py
```

### Demo Mode

If no OpenAI API key is available, enable **Demo Mode** from the sidebar. Demo Mode provides deterministic recommendations and allows the full application and evaluation workflow to be tested without external API dependencies.

   
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
