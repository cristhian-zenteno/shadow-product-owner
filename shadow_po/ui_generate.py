"""
Streamlit UI — "Generate docs" Button (Component J)

Renders the generate button and displays the resulting file paths and
a preview of each generated file.
"""

import streamlit as st
from pathlib import Path


def render_generate_panel(workspace_path: Path) -> None:
    """
    Render the "Generate docs" button and output preview.

    Args:
        workspace_path: Path to the currently active workspace root
    """
    st.subheader("📦 Generate Docs")
    st.markdown(
        "Package your current understanding of this feature into four "
        "structured Markdown files: business rules, Gherkin scenarios, "
        "a Mermaid diagram, and open questions."
    )

    if st.button("🚀 Generate docs", type="primary", key="generate_btn"):
        _run_generate(workspace_path)

    # Show past runs
    output_dir = workspace_path / "output"
    if output_dir.exists():
        runs = sorted(
            [d for d in output_dir.iterdir() if d.is_dir()],
            reverse=True,
        )
        if runs:
            st.markdown("---")
            st.subheader("📂 Past runs")
            selected_run = st.selectbox(
                "View run",
                options=[r.name for r in runs],
                key="run_selector",
            )
            if selected_run:
                _preview_run(output_dir / selected_run)


def _run_generate(workspace_path: Path) -> None:
    """Execute generate_docs() and display the output."""
    from shadow_po import generate_docs as gd
    from shadow_po import privacy
    from shadow_po.config import load_settings

    # Ensure scrubber is ready
    if privacy._scrubber is None:
        settings = load_settings()
        codenames = settings.privacy.codenames if settings.privacy else []
        privacy.initialize(custom_codenames=codenames)

    with st.spinner("Generating docs — this may take a moment…"):
        try:
            settings = load_settings()
            output_path = gd.generate_docs(
                workspace_path=workspace_path,
                model_name=settings.model.name,
                timeout=settings.model.generate_docs_timeout,
                max_completion_tokens=settings.model.generate_docs_max_completion_tokens,
            )
            st.success(f"✅ Docs generated: `{output_path}`")
            _preview_run(output_path)
        except RuntimeError as exc:
            if "NVIDIA_API_KEY" in str(exc):
                st.error(
                    "⚠️ NVIDIA_API_KEY not set. Add it to your `.env` file and restart."
                )
            else:
                st.error(f"Generation failed: {exc}")
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")


def _preview_run(run_dir: Path) -> None:
    """Show an expandable preview of each file in a run folder."""
    file_labels = {
        "business-rules.md": "📋 Business Rules",
        "scenarios.md": "🧪 Scenarios",
        "diagram.md": "📊 Diagram",
        "open-questions.md": "❓ Open Questions",
    }

    for filename, label in file_labels.items():
        file_path = run_dir / filename
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            with st.expander(f"{label} — `{filename}`"):
                if filename == "diagram.md":
                    from shadow_po.ui_chat import _render_message_content

                    _render_message_content(content)
                else:
                    st.markdown(content)
