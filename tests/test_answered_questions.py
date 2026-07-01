"""
Tests for Answered-Questions Tracking - Component H

H-1: detect_answered_question() — LLM mocked, no real API needed
H-2: record_answer() — file append behaviour
H-3: record_answer_and_reindex() — reindex triggered after recording
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from shadow_po.answered_questions import QAPair, detect_answered_question, record_answer, record_answer_and_reindex
from shadow_po import answered_questions as aq


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def privacy_scrubber():
    from shadow_po import privacy
    original = privacy._scrubber
    privacy.initialize(custom_codenames=[])
    yield
    privacy._scrubber = original


@pytest.fixture()
def workspace(tmp_path):
    from shadow_po import workspace as ws
    return ws.create_workspace("aq-test", workspaces_root=tmp_path)


# Sample conversation history with an open question from the assistant
HISTORY_WITH_QUESTION = [
    {"role": "user", "content": "What happens when the payment fails?"},
    {
        "role": "assistant",
        "content": (
            "Based on the spec, the user is redirected to an error page. "
            "However, should double-charges be prevented with a debounce or a confirmation dialog?"
        ),
    },
]


# ---------------------------------------------------------------------------
# Task H-1: detect_answered_question()
# ---------------------------------------------------------------------------

def _mock_llm_response(text: str) -> MagicMock:
    """Build a mock LLM whose .invoke() returns a response with .content = text."""
    mock_response = MagicMock()
    mock_response.content = text
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


def test_detect_answer_returns_qa_pair():
    """
    Acceptance: when a new message clearly answers an open question,
    detect_answered_question returns a QAPair with both fields populated.
    """
    llm_text = (
        "QUESTION: Should double-charges be prevented with a debounce "
        "or a confirmation dialog?\n"
        "ANSWER: The PO confirmed use a debounce, not a confirmation dialog."
    )

    with patch("shadow_po.answered_questions.get_llm", return_value=_mock_llm_response(llm_text)):
        result = detect_answered_question(
            conversation_history=HISTORY_WITH_QUESTION,
            new_message="The PO said yes, use a debounce, not a confirmation dialog.",
        )

    assert result is not None, "Should return a QAPair when answer is detected"
    assert isinstance(result, QAPair)
    assert len(result.question) > 10, "Question field should be populated"
    assert len(result.answer) > 5, "Answer field should be populated"
    assert "debounce" in result.answer.lower()


def test_detect_answer_returns_none_for_non_answer():
    """
    When the new message doesn't answer any open question,
    detect_answered_question returns None.
    """
    with patch("shadow_po.answered_questions.get_llm", return_value=_mock_llm_response("NO_ANSWER")):
        result = detect_answered_question(
            conversation_history=HISTORY_WITH_QUESTION,
            new_message="Can you explain the checkout flow again?",
        )

    assert result is None


def test_detect_answer_returns_none_with_no_history():
    """Returns None immediately when history has no open questions."""
    history_no_questions = [
        {"role": "user", "content": "Tell me about the feature."},
        {"role": "assistant", "content": "The feature allows one-click checkout."},
    ]

    # Should not even call the LLM since there are no open questions
    with patch("shadow_po.answered_questions.get_llm") as mock_get_llm:
        result = detect_answered_question(
            conversation_history=history_no_questions,
            new_message="Thanks, that makes sense.",
        )

    assert result is None
    mock_get_llm.assert_not_called()


def test_detect_answer_scrubs_new_message():
    """
    The new message must be scrubbed before being sent to the LLM.
    A fake API key in the message must not reach the LLM prompt.
    """
    fake_key = "sk-abcdef1234567890abcdef1234567890abcdef12"
    captured_prompts = []

    def capturing_invoke(prompt):
        captured_prompts.append(prompt)
        resp = MagicMock()
        resp.content = "NO_ANSWER"
        return resp

    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = capturing_invoke

    with patch("shadow_po.answered_questions.get_llm", return_value=mock_llm):
        detect_answered_question(
            conversation_history=HISTORY_WITH_QUESTION,
            new_message=f"The PO said use key {fake_key} for the integration.",
        )

    assert len(captured_prompts) > 0
    assert fake_key not in captured_prompts[0], (
        "Raw API key must not appear in the detection prompt"
    )


def test_detect_answer_non_fatal_on_llm_error():
    """
    If the LLM call fails, detect_answered_question returns None rather
    than raising — detection failure is non-fatal.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("LLM unavailable")

    with patch("shadow_po.answered_questions.get_llm", return_value=mock_llm):
        result = detect_answered_question(
            conversation_history=HISTORY_WITH_QUESTION,
            new_message="The PO said use a debounce.",
        )

    assert result is None, "LLM failure should return None, not raise"


# ---------------------------------------------------------------------------
# Task H-2: record_answer()
# ---------------------------------------------------------------------------

def test_record_answer_creates_file(workspace):
    """record_answer() creates answered-questions.md on first call."""
    qa = QAPair(
        question="Should double-charges be prevented with debounce?",
        answer="Yes, use a debounce — not a confirmation dialog.",
    )

    path = record_answer(workspace, qa)

    assert path.exists()
    assert path.name == "answered-questions.md"
    assert path.parent == workspace / "input" / "documents"


def test_record_answer_content(workspace):
    """The Q&A content is written correctly to the file."""
    qa = QAPair(
        question="What is the expiry policy for saved cards?",
        answer="Expired cards redirect to regular checkout.",
    )

    path = record_answer(workspace, qa)
    content = path.read_text(encoding="utf-8")

    assert "What is the expiry policy for saved cards?" in content
    assert "Expired cards redirect to regular checkout." in content


def test_record_answer_appends_multiple(workspace):
    """
    Acceptance: record_answer() called twice produces a file with both
    Q&A pairs — no earlier entry is overwritten.
    """
    qa1 = QAPair(question="First question?", answer="First answer.")
    qa2 = QAPair(question="Second question?", answer="Second answer.")

    record_answer(workspace, qa1)
    record_answer(workspace, qa2)

    content = (workspace / "input" / "documents" / "answered-questions.md").read_text(encoding="utf-8")

    assert "First question?" in content
    assert "First answer." in content
    assert "Second question?" in content
    assert "Second answer." in content

    # First entry appears before second entry
    assert content.index("First question?") < content.index("Second question?")


def test_record_answer_missing_workspace(tmp_path):
    """record_answer() raises FileNotFoundError for a nonexistent workspace."""
    qa = QAPair(question="Q?", answer="A.")
    with pytest.raises(FileNotFoundError, match="Workspace not found"):
        record_answer(tmp_path / "ghost", qa)


# ---------------------------------------------------------------------------
# Task H-3: record_answer_and_reindex()
# ---------------------------------------------------------------------------

def test_reindex_triggered_after_recording(workspace, privacy_scrubber):
    """
    Acceptance: after record_answer_and_reindex(), a retrieval query
    for the newly recorded answer surfaces it from the index.
    """
    from shadow_po import knowledge_base as kb

    qa = QAPair(
        question="How are inventory discrepancies handled?",
        answer="Discrepancies over 5 units trigger an automated alert to the warehouse team.",
    )

    # Record and re-index
    record_answer_and_reindex(
        workspace_path=workspace,
        qa_pair=qa,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    # The answer must now be retrievable via RAG
    chunks = kb.retrieve(
        workspace_path=workspace,
        query="What happens with inventory discrepancies?",
        k=3,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    combined = " ".join(chunks)
    assert "discrepanc" in combined.lower() or "alert" in combined.lower(), (
        "Newly recorded answer must be retrievable after reindex. "
        f"Got chunks: {chunks}"
    )


def test_reindex_triggered_only_for_aq_file(workspace, privacy_scrubber):
    """
    reindex_file() is called only on answered-questions.md, not on
    other files in the workspace — incremental, not full rebuild.
    """
    from shadow_po import knowledge_base as kb

    qa = QAPair(question="Test question?", answer="Test answer.")

    with patch.object(kb, "reindex_file", wraps=kb.reindex_file) as mock_reindex:
        record_answer_and_reindex(
            workspace_path=workspace,
            qa_pair=qa,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )

    mock_reindex.assert_called_once()
    call_args = mock_reindex.call_args
    file_arg = Path(call_args.kwargs.get("file_path") or call_args.args[1])
    assert file_arg.name == "answered-questions.md", (
        "reindex_file must be called only on answered-questions.md"
    )


def test_record_answer_and_reindex_requires_scrubber(workspace):
    """record_answer_and_reindex() raises if privacy scrubber not initialised."""
    from shadow_po import privacy
    original = privacy._scrubber
    privacy._scrubber = None

    try:
        qa = QAPair(question="Q?", answer="A.")
        with pytest.raises(RuntimeError, match="Privacy scrubber not initialised"):
            record_answer_and_reindex(workspace, qa)
    finally:
        privacy._scrubber = original
