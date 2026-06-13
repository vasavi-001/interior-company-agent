# Decision Log – AI Interior Design Agent

## Overview

The goal of this project was to build an AI Interior Design Agent capable of generating realistic, budget-compliant room designs using a real product catalog while demonstrating reliable tool use, guardrails, and evaluation rigor.

Given the assignment's emphasis on product judgment and evaluation, I intentionally optimized for reliability and explainability rather than breadth of features or UI polish.

---

# Scope Strategy

The assignment explicitly recommended solving one room well rather than attempting whole-home planning.

I therefore optimized for reliability and depth rather than breadth.

The project focuses on generating high-confidence recommendations for a single room using:

* Real catalog products
* Budget validation
* Layout validation
* Re-planning
* Evaluation

I intentionally avoided broader but lower-confidence features such as whole-home planning, visual rendering, and advanced spatial optimization.

Although the provided database contained multiple room types, I kept the planning workflow room-centric and focused on producing reliable recommendations rather than attempting a complete home-design system.

---

# What I Scoped In

### Catalog Search Tool

Searches the SQLite catalog using category, style, inventory status, and room suitability.

### Budget Calculator Tool

Validates that recommendations remain within customer budget.

### Layout Fit Checker

Applies a footprint-based heuristic to ensure selected furniture fits within room constraints.

### Re-Planning Workflow

Allows the agent to revise selections when budget or layout constraints fail.

### Guardrails

Handles situations where the correct response is refusal, redirection, or explanation rather than recommendation.

### Evaluation Harness

Includes golden datasets, deterministic scorers, adversarial testing, and ship gates.

---

# What I Scoped Out

### Visual Rendering

Not included.

Reason:

The assignment emphasized reasoning, tool use, and evaluation rather than image generation.

---

### CAD-Level Layout Planning

Not included.

Reason:

A lightweight, explainable layout heuristic was sufficient for demonstrating layout reasoning within the assignment constraints.

---

### Multi-Room Optimization

Not included.

Reason:

I prioritized depth and reliability for individual room planning.

---

### User Accounts and Authentication

Not included.

Reason:

The assignment explicitly recommended focusing on core functionality over infrastructure and UI polish.

---

# Architecture Decisions

## Why SQLite?

The provided database was treated as the source of truth.

The assignment requires recommendations to remain grounded in catalog inventory rather than generated from model knowledge.

---

## Why Tools Instead of Pure Prompting?

A pure LLM approach could:

* Hallucinate products
* Ignore budget constraints
* Recommend furniture that does not fit

To reduce these risks, I separated deterministic tasks into dedicated tools.

### Catalog Search Tool

Responsible for retrieval.

### Budget Tool

Responsible for arithmetic and budget validation.

### Layout Tool

Responsible for fit validation.

The model is primarily responsible for reasoning, prioritization, and explanation.

---

## Why Re-Planning?

Interior design involves multiple constraints.

The first recommendation may not satisfy:

* Budget
* Room dimensions
* Inventory constraints

The agent therefore evaluates its own recommendations and retries when constraints fail.

This makes the workflow closer to an agent than a single-shot chatbot.

---

# How I Used AI Tools

Cursor was used primarily as an implementation accelerator rather than as an autonomous builder.

I used AI assistance for:

* Initial project scaffolding
* Streamlit UI generation
* Database integration
* Boilerplate code

However, several important product decisions were made manually.

## Areas Where I Overrode AI Suggestions

### Evaluation Strategy

The initial implementation focused primarily on happy-path testing.

I expanded the evaluation harness to include:

* Impossible budgets
* Structural advice requests
* Designer product requests
* Delivery guarantee requests
* Layout failures

---

### Demo Mode

The original implementation depended on an OpenAI API key.

I added a deterministic Demo Mode to allow testing and demonstration without external dependencies.

---

### Guardrails

Rather than relying entirely on prompts, I added validation logic to enforce:

* Catalog grounding
* Budget compliance
* Layout compliance
* Structural advice refusal
* Delivery guarantee refusal

This reduced dependence on model behavior and improved reliability.

---

# Evaluation Philosophy

The assignment explicitly emphasizes proving that the product works.

I therefore treated evaluation as a first-class feature rather than an afterthought.

The evaluation harness includes:

### Golden Dataset

25 test cases.

### Deterministic Scorers

* Catalog Accuracy
* Budget Compliance
* Layout Compliance
* Guardrail Compliance

### Subjective Review

Style coherence scoring using a written rubric.

### Ship Gate

Explicit thresholds required before the system is considered deployable.

---

# What Would Break In Production

Although the MVP performs well on the evaluation suite, several production risks remain.

## Inventory Freshness

Catalog availability can change rapidly.

Recommendations may become stale if inventory updates are delayed.

---

## Missing Product Metadata

Some products may lack:

* Dimensions
* Prices
* Style tags

This directly impacts recommendation quality.

---

## Complex Room Geometry

The current layout checker assumes a rectangular room footprint.

It does not account for:

* Door placement
* Window placement
* Walkways
* Traffic flow

---

## Subjective Design Preferences

Two customers requesting the same style may still prefer different outcomes.

A production system would require stronger personalization.

---

## Explanation Quality

Design rationales remain subjective and could benefit from additional evaluation layers.

---

# What I Would Build Next

If given additional time, I would prioritize:

### Visual Mood Boards

Generate visual room concepts alongside recommendations.

### Improved Style Ranking

Use semantic retrieval or embeddings for stronger style matching.

### Human-in-the-Loop Review

Allow designers to review and refine recommendations before customer delivery.

### Better Spatial Planning

Move beyond footprint heuristics to richer layout optimization.

### Feedback Loops

Collect customer and designer feedback to continuously improve recommendation quality.

---

# Final Reflection

The most important lesson from this exercise was that reliable AI products depend less on model intelligence and more on constraints, tooling, and evaluation.

The strongest improvements came not from generating better responses, but from:

* Grounding recommendations in real catalog data
* Separating deterministic logic into tools
* Building evaluation coverage for edge cases
* Defining explicit ship criteria

If deployed in production, I would continue investing in evaluation and reliability before expanding feature scope.
