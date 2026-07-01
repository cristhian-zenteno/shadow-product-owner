"""
Tests for "Generate docs" Generator - Component I

All LLM calls are mocked — no real NVIDIA_API_KEY required.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from shadow_po.schemas import GeneratedDocs
from shadow_po import generate_docs as gd
from shadow_po.generate_docs import FeatureContext, gather_feature_context


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
    return ws.create_workspace("gen-test", workspaces_root=tmp_path)


@pytest.fixture()
def populated_workspace(tmp_path):
    """Workspace with a document, a transcript, and a saved chat turn."""
    from shadow_po import workspace as ws, chat_history

    feature_ws = ws.create_workspace("full-feature", workspaces_root=tmp_path)

    # Document
    (feature_ws / "input" / "documents" / "spec.md").write_text(
        "# One-Click Checkout\n\nUsers complete purchases with a single click.",
        encoding="utf-8",
    )

    # Transcript
    (feature_ws / "input" / "meetings" / "kickoff.txt").write_text(
        "[00:00:01.000 - 00:00:05.000] PO said debounce double-clicks within 3 seconds.",
        encoding="utf-8",
    )

    # Chat turn
    chat_history.save_turn(feature_ws, "session-1", "user", "What about expired cards?")
    chat_history.save_turn(feature_ws, "session-1", "assistant",
                           "Expired cards redirect to regular checkout.")

    return feature_ws


def _mock_llm(docs: GeneratedDocs) -> MagicMock:
    """Return a mock LLM that returns the given GeneratedDocs on invoke()."""
    structured = MagicMock()
    structured.invoke.return_value = docs
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


SAMPLE_DOCS = GeneratedDocs(
    business_rules="## Business Rules\n- Rule 1: Users must be registered.",
    scenarios="## Scenarios\nGiven a registered user\nWhen they click Buy\nThen the order is placed.",
    diagram="```mermaid\ngraph TD\n  A[User] --> B[Checkout]\n```",
    open_questions="## Open Questions\n1. What is the timeout for the payment processor?",
)


# ---------------------------------------------------------------------------
# Task I-1: gather_feature_context()
# ---------------------------------------------------------------------------

def test_gather_context_complete(populated_workspace):
    """
    Acceptance: gather_feature_context() pulls documents, transcripts,
    and chat history from all three source directories.
    """
    ctx = gather_feature_context(populated_workspace)

    assert isinstance(ctx, FeatureContext)
    assert ctx.workspace_name == "full-feature"

    # Documents loaded
    assert len(ctx.documents) >= 1
    assert any("One-Click Checkout" in d for d in ctx.documents)

    # Transcript loaded
    assert len(ctx.transcripts) >= 1
    assert any("debounce" in t for t in ctx.transcripts)

    # Chat history loaded
    assert "expired cards" in ctx.chat_history.lower()


def test_gather_context_includes_answered_questions(populated_workspace):
    """answered-questions.md is loaded separately into answered_questions field."""
    from shadow_po.answered_questions import QAPair, record_answer

    qa = QAPair(
        question="Should expired cards redirect?",
        answer="Yes, redirect to regular checkout.",
    )
    record_answer(populated_workspace, qa)

    ctx = gather_feature_context(populated_workspace)

    assert "redirect" in ctx.answered_questions.lower()


def test_gather_context_empty_workspace(workspace):
    """An empty but valid workspace gathers successfully with empty lists."""
    ctx = gather_feature_context(workspace)

    assert ctx.documents == []
    assert ctx.transcripts == []
    assert ctx.chat_history == ""


def test_gather_context_fails_loudly_on_missing_source(tmp_path):
    """
    Acceptance (Risk R6): if the workspace structure is broken, gather
    raises FileNotFoundError immediately — no partial context is returned.
    """
    # Create a dir that exists but lacks subdirectories
    bare = tmp_path / "bare"
    bare.mkdir()

    with pytest.raises(FileNotFoundError):
        gather_feature_context(bare)


def test_gather_context_workspace_not_found(tmp_path):
    """Raises FileNotFoundError for a nonexistent workspace."""
    with pytest.raises(FileNotFoundError, match="Workspace not found"):
        gather_feature_context(tmp_path / "ghost")


# ---------------------------------------------------------------------------
# Task I-2: output schema validation
# ---------------------------------------------------------------------------

def test_output_schema_valid():
    """GeneratedDocs validates a correct fixture response."""
    docs = GeneratedDocs(
        business_rules="## Business Rules\n- Users must be registered.",
        scenarios="## Scenarios\nGiven a user\nWhen...\nThen...",
        diagram="```mermaid\ngraph TD\n  A --> B\n```",
        open_questions="1. What is the payment timeout?",
    )
    assert "Business Rules" in docs.business_rules
    assert "mermaid" in docs.diagram


def test_output_schema_rejects_empty_fields():
    """GeneratedDocs raises on any empty required field."""
    with pytest.raises(Exception):
        GeneratedDocs(
            business_rules="",
            scenarios="content",
            diagram="content",
            open_questions="content",
        )


# ---------------------------------------------------------------------------
# Task I-3: Filter open questions against answered-questions.md
# ---------------------------------------------------------------------------

def test_open_questions_excludes_answered():
    """
    Acceptance: questions already present in answered-questions.md are
    removed from the generated open-questions list.
    """
    open_qs = (
        "## Open Questions\n\n"
        "1. What is the payment timeout?\n"
        "2. Should expired cards redirect to checkout?\n"
        "3. How are refunds handled after 30 days?\n"
    )

    answered = (
        "## Answered Questions\n\n"
        "**Question:** should expired cards redirect to checkout?\n"
        "**Answer:** Yes, redirect to regular checkout.\n"
    )

    result = gd._filter_answered_questions(open_qs, answered)

    assert "expired cards redirect to checkout" not in result.lower()
    assert "payment timeout" in result.lower()
    assert "refunds handled" in result.lower()


def test_open_questions_unchanged_when_no_answered():
    """When answered-questions.md is empty, open-questions is unchanged."""
    open_qs = "1. What is the payment timeout?\n2. How are refunds handled?"
    result = gd._filter_answered_questions(open_qs, "")
    assert result == open_qs


def test_open_questions_all_answered():
    """When all questions are answered the list body becomes empty."""
    open_qs = "1. should expired cards redirect?\n"
    answered = "**Question:** should expired cards redirect?\n**Answer:** Yes.\n"

    result = gd._filter_answered_questions(open_qs, answered)
    # The answered question line must be gone
    assert "should expired cards redirect?" not in result


# ---------------------------------------------------------------------------
# Task I-4: Two runs create two timestamped folders
# ---------------------------------------------------------------------------

def test_two_runs_create_two_folders(populated_workspace):
    """
    Acceptance: running generate_docs() twice produces two separate
    timestamped folders — the first run is never overwritten.
    """
    with patch("shadow_po.generate_docs.get_llm", return_value=_mock_llm(SAMPLE_DOCS)):
        path1 = gd.generate_docs(populated_workspace)

    with patch("shadow_po.generate_docs.get_llm", return_value=_mock_llm(SAMPLE_DOCS)):
        path2 = gd.generate_docs(populated_workspace)

    assert path1 != path2, "Two runs must produce different output folders"
    assert path1.exists(), "First run folder must still exist after second run"
    assert path2.exists(), "Second run folder must exist"


def test_generate_docs_creates_all_four_files(populated_workspace):
    """generate_docs() writes exactly the four required files."""
    with patch("shadow_po.generate_docs.get_llm", return_value=_mock_llm(SAMPLE_DOCS)):
        output_dir = gd.generate_docs(populated_workspace)

    expected = {"business-rules.md", "scenarios.md", "diagram.md", "open-questions.md"}
    actual = {f.name for f in output_dir.iterdir() if f.is_file()}
    assert expected == actual


def test_generate_docs_file_content(populated_workspace):
    """Each output file contains the LLM-generated content."""
    with patch("shadow_po.generate_docs.get_llm", return_value=_mock_llm(SAMPLE_DOCS)):
        output_dir = gd.generate_docs(populated_workspace)

    assert "Business Rules" in (output_dir / "business-rules.md").read_text(encoding="utf-8")
    assert "mermaid" in (output_dir / "diagram.md").read_text(encoding="utf-8")
    assert "Scenarios" in (output_dir / "scenarios.md").read_text(encoding="utf-8")


def test_generate_docs_output_folder_in_workspace(populated_workspace):
    """Output folder is inside workspace/output/ ."""
    with patch("shadow_po.generate_docs.get_llm", return_value=_mock_llm(SAMPLE_DOCS)):
        output_dir = gd.generate_docs(populated_workspace)

    assert output_dir.parent == populated_workspace / "output"


def test_generate_docs_llm_failure_writes_no_files(populated_workspace):
    """
    Risk R6: if the LLM call fails, no partial output files are written.
    """
    failing_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.side_effect = RuntimeError("LLM timeout")
    failing_llm.with_structured_output.return_value = structured

    with patch("shadow_po.generate_docs.get_llm", return_value=failing_llm):
        with pytest.raises(RuntimeError, match="LLM call failed"):
            gd.generate_docs(populated_workspace)

    # output/ folder should be empty (no partial run written)
    output_dir = populated_workspace / "output"
    written_files = list(output_dir.rglob("*.md"))
    assert written_files == [], (
        f"No output files should exist after a failed run, found: {written_files}"
    )


def test_generate_docs_applies_answered_filter(populated_workspace):
    """
    The open-questions.md in the output excludes questions already recorded
    in answered-questions.md.
    """
    from shadow_po.answered_questions import QAPair, record_answer

    # Record an answered question
    qa = QAPair(
        question="what is the payment processor timeout?",
        answer="The timeout is 30 seconds.",
    )
    record_answer(populated_workspace, qa)

    docs_with_answered_q = GeneratedDocs(
        business_rules="## Rules\n- Rule 1.",
        scenarios="## Scenarios\nGiven...\nWhen...\nThen...",
        diagram="```mermaid\ngraph TD\n  A --> B\n```",
        open_questions=(
            "1. what is the payment processor timeout?\n"
            "2. How are refunds handled after 30 days?\n"
        ),
    )

    with patch("shadow_po.generate_docs.get_llm", return_value=_mock_llm(docs_with_answered_q)):
        output_dir = gd.generate_docs(populated_workspace)

    open_q_content = (output_dir / "open-questions.md").read_text(encoding="utf-8")

    assert "payment processor timeout" not in open_q_content.lower(), (
        "Already-answered question must be excluded from open-questions.md"
    )
    assert "refunds" in open_q_content.lower(), (
        "Unanswered question must still appear in open-questions.md"
    )
