"""
Shadow PO — Streamlit Entry Point (Component J)

Run with:
    streamlit run app.py

Requires:
    - settings.yaml in the project root
    - NVIDIA_API_KEY in .env (for chat and generate docs)
    - SearXNG running locally on the URL configured in settings.yaml
"""

import os
from pathlib import Path

# Load .env if present (before any other import that might need the key)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional at runtime

import streamlit as st

# -------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# -------------------------------------------------------------------------
st.set_page_config(
    page_title="Shadow PO",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------------------------------------------------------
# UI imports (after page config)
# -------------------------------------------------------------------------
from shadow_po.ui_workspace import render_workspace_sidebar
from shadow_po.ui_chat import render_chat_panel
from shadow_po.ui_upload import render_upload_panel
from shadow_po.ui_generate import render_generate_panel


# -------------------------------------------------------------------------
# App shell
# -------------------------------------------------------------------------

def main() -> None:
    # Sidebar — workspace picker
    active_workspace = render_workspace_sidebar()

    if active_workspace is None:
        st.title("🤖 Shadow PO")
        st.info(
            "Create or select a **feature workspace** in the sidebar to get started."
        )
        st.markdown(
            """
            **Shadow PO** is your AI-powered cognitive partner for product requirement refinement.

            ### How to use

            1. **Create a workspace** for the feature you're working on (e.g. `one-click-checkout`)
            2. **Upload documents** — specs, PDFs, requirement docs
            3. **Upload recordings** — meeting audio or video (transcribed locally, never uploaded)
            4. **Chat** to explore and clarify the requirements
            5. When you're ready, **Generate docs** to package everything into structured artifacts

            ### Privacy
            All processing is local. Nothing leaves your machine without passing through
            the privacy scrubber first.
            """
        )
        return

    # Header
    st.title(f"🤖 Shadow PO — {active_workspace.name}")

    # Main content tabs
    tab_chat, tab_upload, tab_generate = st.tabs([
        "💬 Chat",
        "📎 Upload",
        "📦 Generate Docs",
    ])

    with tab_chat:
        render_chat_panel(active_workspace)

    with tab_upload:
        render_upload_panel(active_workspace)

    with tab_generate:
        render_generate_panel(active_workspace)


if __name__ == "__main__" or True:
    main()
