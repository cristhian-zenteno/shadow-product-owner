"""
Streamlit UI — Chat Panel (Component J)

Renders the interactive chat interface wired to pipeline.answer_question().
Saves each turn via chat_history.save_turn() and detects answered questions
via answered_questions.detect_answered_question().
"""

import re
import streamlit as st
from pathlib import Path
import uuid

from shadow_po.mermaid_format import (
    format_mermaid_block,
    looks_like_sequence_diagram,
    normalize_mermaid_source,
    strip_fenced_code,
)

_MERMAID_FENCE_RE = re.compile(
    r"```mermaid\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _format_assistant_content(answer_obj) -> str:
    """Build the assistant message stored in chat history."""
    assistant_text = answer_obj.answer
    if answer_obj.gherkin:
        gherkin_source = strip_fenced_code(answer_obj.gherkin)
        assistant_text += f"\n\n**Gherkin:**\n```gherkin\n{gherkin_source}\n```"
    if answer_obj.diagram:
        assistant_text += f"\n\n**Diagram:**\n{format_mermaid_block(answer_obj.diagram)}"
    return assistant_text


def _render_mermaid_block(source: str) -> None:
    """Render a diagram preview plus a copyable source block."""
    normalized = normalize_mermaid_source(source)
    try:
        st.mermaid(normalized)
    except Exception:
        pass
    st.code(normalized, language="mermaid")


def _render_message_content(content: str) -> None:
    """
    Render chat message content.

    Mermaid diagrams are shown as copyable code blocks instead of being
    rendered inline, so developers can paste them into external tools.
    """
    if _MERMAID_FENCE_RE.search(content):
        last_end = 0
        for match in _MERMAID_FENCE_RE.finditer(content):
            before = content[last_end : match.start()]
            if before.strip():
                st.markdown(before)
            _render_mermaid_block(match.group(1).strip())
            last_end = match.end()
        remaining = content[last_end:]
        if remaining.strip():
            st.markdown(remaining)
        return

    if "**Diagram:**" in content:
        before, _, diagram_part = content.partition("**Diagram:**")
        if before.strip():
            st.markdown(before)
        st.markdown("**Diagram:**")
        _render_mermaid_block(strip_fenced_code(diagram_part))
        return

    if looks_like_sequence_diagram(content):
        _render_mermaid_block(content)
        return

    st.markdown(content)


def render_chat_panel(workspace_path: Path) -> None:
    """
    Render the full chat panel for a feature workspace.

    Handles:
    - Conversation selection / creation
    - Displaying message history
    - Sending new questions to the LLM pipeline
    - Saving turns and detecting answered questions

    Args:
        workspace_path: Path to the currently active workspace root
    """
    from shadow_po import chat_history, privacy, answered_questions as aq

    # Ensure privacy scrubber is ready
    _ensure_scrubber()

    # -----------------------------------------------------------------------
    # Conversation management
    # -----------------------------------------------------------------------
    conv_key = f"conv_id_{workspace_path.name}"

    existing_convs = chat_history.list_conversations(workspace_path)

    with st.expander("💬 Conversation", expanded=True):
        col_select, col_new = st.columns([3, 1])

        with col_new:
            if st.button("🆕 New conversation", key=f"new_conv_{workspace_path.name}"):
                st.session_state[conv_key] = _new_conversation_id()
                st.rerun()

        with col_select:
            if existing_convs:
                current = st.session_state.get(conv_key, existing_convs[-1])
                if current not in existing_convs:
                    existing_convs = [current] + existing_convs
                selected = st.selectbox(
                    "Load conversation",
                    options=existing_convs,
                    index=existing_convs.index(current) if current in existing_convs else 0,
                    key=f"conv_select_{workspace_path.name}",
                )
                st.session_state[conv_key] = selected
            else:
                if conv_key not in st.session_state:
                    st.session_state[conv_key] = _new_conversation_id()
                st.caption(f"Conversation: `{st.session_state[conv_key]}`")

    conversation_id = st.session_state.get(conv_key, _new_conversation_id())
    pending_key = f"chat_pending_{workspace_path.name}_{conversation_id}"

    # -----------------------------------------------------------------------
    # Load and display history
    # -----------------------------------------------------------------------
    try:
        messages = chat_history.load_conversation(workspace_path, conversation_id)
    except FileNotFoundError:
        messages = []

    # st.chat_input is only pinned to the viewport bottom in the main app body.
    # Inside tabs it renders inline, so keep all messages above the input and
    # never render new turns below it.
    with st.container(height=500):
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            with st.chat_message(role):
                _render_message_content(content)

        pending_question = st.session_state.get(pending_key)
        if pending_question:
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    _handle_assistant_turn(
                        workspace_path,
                        conversation_id,
                        pending_question,
                        aq,
                    )
            del st.session_state[pending_key]
            st.rerun()

    # -----------------------------------------------------------------------
    # Input — always the last element in this panel
    # -----------------------------------------------------------------------
    user_input = st.chat_input(
        "Ask a question about this feature…",
        key=f"chat_input_{workspace_path.name}",
    )

    if user_input:
        chat_history.save_turn(workspace_path, conversation_id, "user", user_input)
        st.session_state[pending_key] = user_input
        st.rerun()


def _new_conversation_id() -> str:
    return str(uuid.uuid4())[:8]


def _handle_assistant_turn(
    workspace_path: Path,
    conversation_id: str,
    user_input: str,
    aq_module,
) -> None:
    """Call the pipeline, persist the assistant turn, and detect answered questions."""
    from shadow_po import chat_history

    answer_obj = _call_pipeline(workspace_path, user_input)
    if answer_obj is None:
        return

    assistant_text = _format_assistant_content(answer_obj)

    chat_history.save_turn(
        workspace_path, conversation_id, "assistant", assistant_text
    )

    try:
        updated_messages = chat_history.load_conversation(
            workspace_path, conversation_id
        )
        qa_pair = aq_module.detect_answered_question(
            conversation_history=updated_messages[:-1],
            new_message=user_input,
        )
        if qa_pair:
            aq_module.record_answer_and_reindex(workspace_path, qa_pair)
            st.toast(f"Recorded answered question: {qa_pair.question[:80]}")
    except Exception:
        pass  # detection failure is non-fatal


def _ensure_scrubber() -> None:
    from shadow_po import privacy
    if privacy._scrubber is None:
        from shadow_po.config import load_settings
        settings = load_settings()
        codenames = settings.privacy.codenames if settings.privacy else []
        privacy.initialize(custom_codenames=codenames)


def _call_pipeline(workspace_path: Path, question: str):
    """Call answer_question and handle errors gracefully."""
    from shadow_po import pipeline
    from shadow_po.config import load_settings

    try:
        settings = load_settings()
        return pipeline.answer_question(
            workspace_path=workspace_path,
            question=question,
            searxng_url=settings.searxng_url,
            model_name=settings.model.name,
            timeout=settings.model.timeout,
        )
    except RuntimeError as exc:
        if "NVIDIA_API_KEY" in str(exc):
            st.error(
                "⚠️ NVIDIA_API_KEY not set. Add it to your `.env` file and restart."
            )
        else:
            st.error(f"Pipeline error: {exc}")
        return None
    except Exception as exc:
        st.error(f"Unexpected error: {exc}")
        return None
