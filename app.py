"""
app.py
------
Streamlit web UI for the AI Interior Design Agent.

Run with:
    streamlit run app.py

Set your OpenAI key first:
    export OPENAI_API_KEY="sk-..."
"""

import json
import os

import pandas as pd
import streamlit as st

import database as db
from agent import InteriorDesignAgent, run_agent

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Interior Design Agent",
    page_icon="🏠",
    layout="wide",
)

st.title("🏠 AI Interior Design Agent")
st.caption(
    "Reads room briefs, searches the real product catalog, checks budget & layout, "
    "and generates a design rationale and Bill of Quantities."
)

# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    demo_mode = st.checkbox(
        "Demo Mode",
        value=False,
        help="Skip OpenAI. Uses deterministic product selection with catalog, budget, and layout tools.",
    )

    api_key_input = st.text_input(
        "OpenAI API Key",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
        help="Not required when Demo Mode is enabled.",
        disabled=demo_mode,
    )

    if demo_mode:
        st.info("Demo Mode: no API key needed.")

    st.divider()
    st.markdown("**Guardrails**")
    st.markdown(
        """
        -  Only real catalog products
        -  In-stock items only
        -  Budget enforced
        -  Layout fit checked
        -  No invented products
        -  No structural advice
        -  No delivery promises
        """
    )

# ---------------------------------------------------------------------------
# Load room briefs from database
# ---------------------------------------------------------------------------

try:
    briefs = db.list_room_briefs()
except Exception as exc:
    st.error(f"Could not load database: {exc}")
    st.stop()

if not briefs:
    st.warning("No room briefs found in interior_company_catalog.db")
    st.stop()

brief_options = {f"{b['brief_id']} — {b['room_type']}": b["brief_id"] for b in briefs}
selected_label = st.selectbox("Select a room brief", list(brief_options.keys()))
selected_brief_id = brief_options[selected_label]
brief = db.get_room_brief(selected_brief_id)

# ---------------------------------------------------------------------------
# Show the room brief
# ---------------------------------------------------------------------------

st.subheader("Room Brief")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Room", brief["room_type"])
    st.metric("Budget", f"₹{brief['budget_inr']:,}")

with col2:
    st.metric("Length", f"{brief['length_cm']} cm")
    st.metric("Width", f"{brief['width_cm']} cm")

with col3:
    st.metric("Ceiling", f"{brief['ceiling_cm']} cm")
    st.metric("Style", brief["style_preference"])

with st.expander("Full brief details", expanded=False):
    st.write(f"**Must-haves:** {brief['must_haves']}")
    st.write(f"**Constraints:** {brief['constraints']}")
    st.write(f"**Customer note:** {brief['customer_note']}")

# ---------------------------------------------------------------------------
# Run the agent
# ---------------------------------------------------------------------------

st.divider()

if st.button("🎨 Generate Design", type="primary", use_container_width=True):
    if not demo_mode and not api_key_input:
        st.error("Please enter your OpenAI API key in the sidebar, or enable Demo Mode.")
    else:
        spinner_msg = (
            "Demo mode: searching catalog, checking budget & layout…"
            if demo_mode
            else "Agent is searching catalog, checking budget & layout…"
        )
        with st.spinner(spinner_msg):
            try:
                result = run_agent(
                    selected_brief_id,
                    api_key=api_key_input or None,
                    demo_mode=demo_mode,
                )
            except Exception as exc:
                st.error(f"Agent error: {exc}")
                st.stop()

        if demo_mode:
            st.caption("Running in Demo Mode — deterministic selection, no OpenAI.")

        if result["status"] == "error":
            st.error(result.get("message", "Unknown error"))
            if result.get("raw_response"):
                with st.expander("Raw agent response"):
                    st.code(result["raw_response"])
            st.stop()

        if result["status"] == "failed":
            st.warning(result.get("message", "Design failed validation."))
            if result.get("violations"):
                st.error("Violations:\n" + "\n".join(f"- {v}" for v in result["violations"]))
            if result.get("design"):
                with st.expander("Partial design (failed validation)"):
                    st.json(result["design"])
            st.stop()

        # Success!
        design = result["design"]
        replan_count = result.get("replan_count", 0)

        if replan_count > 0:
            st.info(f"Agent replanned {replan_count} time(s) to meet constraints.")

        # Design rationale
        st.subheader("Design Rationale")
        st.markdown(design.get("design_rationale", "_No rationale provided._"))

        # Selected items
        st.subheader("Selected Products")
        selected = design.get("selected_items", [])
        if selected:
            items_df = pd.DataFrame(selected)
            display_cols = [c for c in ["item_id", "name", "category", "price_inr", "why"] if c in items_df.columns]
            st.dataframe(items_df[display_cols], use_container_width=True, hide_index=True)
        else:
            st.write("No items selected.")

        # BOQ
        st.subheader("Bill of Quantities (BOQ)")
        boq = design.get("boq", {})
        boq_lines = boq.get("line_items", [])

        if boq_lines:
            boq_df = pd.DataFrame(boq_lines)
            st.dataframe(boq_df, use_container_width=True, hide_index=True)

            bcol1, bcol2, bcol3 = st.columns(3)
            with bcol1:
                st.metric("Subtotal", f"₹{boq.get('subtotal_inr', 0):,}")
            with bcol2:
                st.metric("Budget", f"₹{boq.get('budget_inr', 0):,}")
            with bcol3:
                remaining = boq.get("remaining_inr", 0)
                st.metric(
                    "Remaining",
                    f"₹{remaining:,}",
                    delta=f"{'under' if remaining >= 0 else 'OVER'} budget",
                    delta_color="normal" if remaining >= 0 else "inverse",
                )
        else:
            st.write("No BOQ lines.")

        # Constraint notes
        notes = design.get("constraint_notes") or []
        if notes:
            st.subheader("Constraint Notes")
            for note in notes:
                st.write(f"- {note}")

        # Raw JSON for developers
        with st.expander("Full design JSON"):
            st.code(json.dumps(design, indent=2, default=str), language="json")

# ---------------------------------------------------------------------------
# Catalog browser (helpful for demos)
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Browse Catalog")

search_col1, search_col2, search_col3 = st.columns(3)
with search_col1:
    cat_filter = st.text_input("Category", placeholder="e.g. Sofa")
with search_col2:
    style_filter = st.text_input("Style", placeholder="e.g. Scandinavian")
with search_col3:
    room_filter = st.text_input("Room type", placeholder="e.g. Living Room")

if st.button("Search catalog"):
    products = db.search_catalog(
        category=cat_filter or None,
        style_keyword=style_filter or None,
        room_type=room_filter or None,
        in_stock_only=True,
    )
    if products:
        pdf = pd.DataFrame(products)
        show_cols = [
            "item_id", "name", "category", "price_inr",
            "width_cm", "depth_cm", "style_tags", "in_stock",
        ]
        st.dataframe(pdf[show_cols], use_container_width=True, hide_index=True)
        st.caption(f"{len(products)} in-stock product(s) found.")
    else:
        st.info("No matching products.")
