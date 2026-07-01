"""
Streamlit UI — Workspace Picker (Component J)

Renders the sidebar for workspace selection and creation.
Reads from and writes to session_state["active_workspace"].
"""

import streamlit as st
from pathlib import Path
from shadow_po import workspace as ws
from shadow_po.config import load_settings


def render_workspace_sidebar() -> Path | None:
    """
    Render the workspace picker in the Streamlit sidebar.

    Returns the currently selected workspace Path, or None if none selected.
    Updates st.session_state["active_workspace"] on change.
    """
    settings = load_settings()
    workspaces_root = Path(settings.workspaces_root)

    st.sidebar.title("🗂 Shadow PO")
    st.sidebar.markdown("---")

    # --- Create new workspace ---
    st.sidebar.subheader("New Feature Workspace")
    new_name = st.sidebar.text_input(
        "Feature name",
        placeholder="e.g. one-click-checkout",
        key="new_workspace_name",
    )
    if st.sidebar.button("➕ Create workspace", key="create_ws_btn"):
        if new_name.strip():
            try:
                created = ws.create_workspace(
                    new_name.strip(), workspaces_root=workspaces_root
                )
                st.session_state["active_workspace"] = created
                st.sidebar.success(f"Created: {new_name.strip()}")
                st.rerun()
            except Exception as exc:
                st.sidebar.error(f"Failed to create workspace: {exc}")
        else:
            st.sidebar.warning("Enter a feature name first.")

    st.sidebar.markdown("---")

    # --- Select existing workspace ---
    existing = ws.list_workspaces(workspaces_root=workspaces_root)

    if not existing:
        st.sidebar.info("No workspaces yet. Create one above.")
        return None

    st.sidebar.subheader("Existing Workspaces")

    active = st.session_state.get("active_workspace")
    active_name = active.name if isinstance(active, Path) else (active or "")

    selected_name = st.sidebar.radio(
        "Select workspace",
        options=existing,
        index=existing.index(active_name) if active_name in existing else 0,
        key="workspace_radio",
    )

    selected_path = workspaces_root / selected_name
    st.session_state["active_workspace"] = selected_path

    st.sidebar.markdown("---")
    st.sidebar.caption(f"📁 `{selected_path}`")

    return selected_path
