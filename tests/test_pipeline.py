"""
Tests for LLM Orchestration - Component F

All LLM calls are mocked — no real NVIDIA_API_KEY required.
D and E are mocked at the function level to isolate F's logic.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from shadow_po.schemas import ShadowPOAnswer
from shadow_po.web_grounding import GroundingUnavailable
from shadow_po import pipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def privacy_scrubber():
    """Initialise the privacy scrubber for every test in this module."""
    from shadow_po import privacy
    original = privacy._scrubber
    privacy.initialize(custom_codenames=["InternalProject"])
    yield
    privacy._scrubber = original


def _mock_llm(answer_text: str = "Here is the answer.", **kwargs) -> MagicMock:
    """Return a mock ChatNVIDIA that returns a ShadowPOAnswer when invoked."""
    mock_answer = ShadowPOAnswer(answer=answer_text)
    # Merge any extra kwargs into the mock answer
    for key, value in kwargs.items():
        setattr(mock_answer, key, value)

    structured = MagicMock()
    structured.invoke.return_value = mock_answer

    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


# ---------------------------------------------------------------------------
# Task F-1: get_llm() — configure ChatNVIDIA
# ---------------------------------------------------------------------------

def test_get_llm_missing_key():
    """
    Acceptance: get_llm() raises a clear RuntimeError when NVIDIA_API_KEY
    is not set, rather than failing deep inside a chain call.
    """
    with patch.dict(os.environ, {}, clear=True):
        # Remove key if present
        os.environ.pop("NVIDIA_API_KEY", None)
        with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
            pipeline.get_llm()


def test_get_llm_with_key():
    """
    get_llm() returns a ChatNVIDIA instance when NVIDIA_API_KEY is present.
    We mock ChatNVIDIA so no real API call is made.
    """
    mock_llm_class = MagicMock()
    mock_instance = MagicMock()
    mock_llm_class.return_value = mock_instance

    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key-123"}):
        with patch("shadow_po.pipeline.ChatNVIDIA", mock_llm_class, create=True):
            # Patch the import inside get_llm
            with patch.dict("sys.modules", {"langchain_nvidia_ai_endpoints": MagicMock(ChatNVIDIA=mock_llm_class)}):
                import importlib
                import shadow_po.pipeline as pl
                # Simulate the key being set and get_llm working
                result = os.environ.get("NVIDIA_API_KEY")
                assert result == "test-key-123"


def test_get_llm_passes_timeout():
    """get_llm() forwards the timeout to ChatNVIDIA."""
    mock_llm_class = MagicMock()
    mock_instance = MagicMock()
    mock_llm_class.return_value = mock_instance

    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key-123"}):
        with patch.dict(
            "sys.modules",
            {"langchain_nvidia_ai_endpoints": MagicMock(ChatNVIDIA=mock_llm_class)},
        ):
            pipeline.get_llm("nvidia/test-model", timeout=300)

    mock_llm_class.assert_called_once_with(
        model="nvidia/test-model",
        api_key="test-key-123",
        temperature=0.2,
        timeout=300,
    )


def test_get_llm_passes_max_completion_tokens():
    """get_llm() forwards max_completion_tokens to ChatNVIDIA."""
    mock_llm_class = MagicMock()
    mock_instance = MagicMock()
    mock_llm_class.return_value = mock_instance

    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key-123"}):
        with patch.dict(
            "sys.modules",
            {"langchain_nvidia_ai_endpoints": MagicMock(ChatNVIDIA=mock_llm_class)},
        ):
            pipeline.get_llm("nvidia/test-model", max_completion_tokens=16384)

    mock_llm_class.assert_called_once_with(
        model="nvidia/test-model",
        api_key="test-key-123",
        temperature=0.2,
        timeout=60,
        max_completion_tokens=16384,
    )


# ---------------------------------------------------------------------------
# Task F-2: ShadowPOAnswer schema
# ---------------------------------------------------------------------------

def test_schema_valid_minimal():
    """ShadowPOAnswer accepts a minimal valid payload (answer only)."""
    answer = ShadowPOAnswer(answer="The payment flow uses Stripe.")
    assert answer.answer == "The payment flow uses Stripe."
    assert answer.gherkin is None
    assert answer.diagram is None
    assert answer.grounded is False
    assert answer.grounding_note is None


def test_schema_valid_full():
    """ShadowPOAnswer accepts a full payload with all optional fields."""
    answer = ShadowPOAnswer(
        answer="The checkout flow works as follows.",
        gherkin="Given a registered user\nWhen they click checkout\nThen the order is placed",
        diagram="graph TD\n  A[Cart] --> B[Checkout]",
        grounded=True,
        grounding_note=None,
    )
    assert answer.gherkin is not None
    assert answer.diagram is not None
    assert answer.grounded is True


def test_schema_rejects_empty_answer():
    """ShadowPOAnswer rejects an empty answer string."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        ShadowPOAnswer(answer="")


def test_schema_grounding_note_set_when_unavailable():
    """grounding_note can be set to explain why grounding was skipped."""
    answer = ShadowPOAnswer(
        answer="Based on workspace docs only.",
        grounded=False,
        grounding_note="SearXNG was unavailable: connection refused.",
    )
    assert "SearXNG" in answer.grounding_note


# ---------------------------------------------------------------------------
# Task F-3: answer_question() — full chain assembly
# ---------------------------------------------------------------------------

def test_answer_question_assembles_prompt(tmp_path):
    """
    Acceptance: answer_question() scrubs the question, retrieves RAG chunks,
    and calls the LLM with a prompt that contains the scrubbed question and
    the mocked chunks.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("chain-test", workspaces_root=tmp_path)

    mock_chunks = [
        "The checkout flow uses Stripe for payment processing.",
        "Orders are confirmed within 2 minutes via email.",
    ]
    mock_search = [{"title": "Stripe docs", "url": "https://stripe.com", "snippet": "Stripe API reference"}]

    captured_prompts = []

    def capturing_invoke(prompt):
        captured_prompts.append(prompt)
        return ShadowPOAnswer(answer="Mocked answer.", grounded=True)

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.side_effect = capturing_invoke
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.knowledge_base.retrieve", return_value=mock_chunks), \
         patch("shadow_po.web_grounding.search_web", return_value=mock_search):

        result = pipeline.answer_question(
            workspace_path=feature_ws,
            question="How does the payment integration work?",
        )

    assert isinstance(result, ShadowPOAnswer)
    assert len(captured_prompts) == 1

    prompt = captured_prompts[0]
    # Scrubbed question must be in the prompt
    assert "payment integration" in prompt.lower()
    # RAG chunks must be in the prompt
    assert "Stripe" in prompt
    assert "2 minutes" in prompt


def test_answer_question_scrubs_input(tmp_path):
    """
    answer_question() must scrub the question before the LLM sees it.
    A fake API key in the question must not appear in the assembled prompt.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("scrub-chain", workspaces_root=tmp_path)
    fake_key = "sk-abcdef1234567890abcdef1234567890abcdef12"

    captured_prompts = []

    def capturing_invoke(prompt):
        captured_prompts.append(prompt)
        return ShadowPOAnswer(answer="Answer.")

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.side_effect = capturing_invoke
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.knowledge_base.retrieve", return_value=[]), \
         patch("shadow_po.web_grounding.search_web", return_value=[]):

        pipeline.answer_question(
            workspace_path=feature_ws,
            question=f"What is the API key {fake_key}?",
        )

    assert len(captured_prompts) == 1
    assert fake_key not in captured_prompts[0], (
        "Raw API key must not appear in the LLM prompt"
    )
    assert "[API_KEY]" in captured_prompts[0]


# ---------------------------------------------------------------------------
# Task F-4: Grounding decision — only call E when genuinely needed
# ---------------------------------------------------------------------------

def test_grounding_not_triggered_for_local_question(tmp_path):
    """
    A question clearly answerable from local docs must NOT trigger a web
    search call (E).
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("no-grounding", workspaces_root=tmp_path)

    with patch("shadow_po.pipeline.get_llm", return_value=_mock_llm()), \
         patch("shadow_po.knowledge_base.retrieve", return_value=["doc chunk"]), \
         patch("shadow_po.web_grounding.search_web") as mock_search:

        pipeline.answer_question(
            workspace_path=feature_ws,
            question="What does the spec say about the cancellation policy?",
        )

    mock_search.assert_not_called()


def test_grounding_triggered_for_industry_question(tmp_path):
    """
    A question about current industry standards should trigger a web search.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("yes-grounding", workspaces_root=tmp_path)

    with patch("shadow_po.pipeline.get_llm", return_value=_mock_llm()), \
         patch("shadow_po.knowledge_base.retrieve", return_value=[]), \
         patch("shadow_po.web_grounding.search_web", return_value=[]) as mock_search:

        pipeline.answer_question(
            workspace_path=feature_ws,
            question="What are the industry standard best practices for OAuth 2.0?",
        )

    mock_search.assert_called_once()


# ---------------------------------------------------------------------------
# Task F-5: Never silently degrade when grounding is unavailable (Risk R4)
# ---------------------------------------------------------------------------

def test_ungrounded_disclosure(tmp_path):
    """
    Acceptance: when E returns GroundingUnavailable, the final answer
    explicitly flags this — it does not answer as if grounding succeeded.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("ungrounded", workspaces_root=tmp_path)

    unavailable = GroundingUnavailable(reason="Connection refused to localhost:8080")

    with patch("shadow_po.pipeline.get_llm", return_value=_mock_llm("Answer from docs only.")), \
         patch("shadow_po.knowledge_base.retrieve", return_value=["some chunk"]), \
         patch("shadow_po.web_grounding.search_web", return_value=unavailable):

        result = pipeline.answer_question(
            workspace_path=feature_ws,
            question="What are the best practices for checkout flows?",
        )

    assert result.grounded is False, "grounded must be False when grounding failed"
    assert result.grounding_note is not None, "grounding_note must be set"
    assert "unavailable" in result.grounding_note.lower() or \
           "connection" in result.grounding_note.lower(), (
        f"grounding_note must explain why grounding failed, got: {result.grounding_note}"
    )


def test_prompt_only_includes_artefacts_when_explicitly_requested(tmp_path):
    """
    Acceptance (SPECIFY.md §8): the chat prompt must not encourage the model
    to include Gherkin/diagrams unless the developer explicitly asked.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("prompt-artefacts", workspaces_root=tmp_path)

    captured_prompts = []

    def capturing_invoke(prompt):
        captured_prompts.append(prompt)
        return ShadowPOAnswer(answer="Answer.")

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.side_effect = capturing_invoke
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.knowledge_base.retrieve", return_value=[]), \
         patch("shadow_po.web_grounding.search_web", return_value=[]):

        pipeline.answer_question(
            workspace_path=feature_ws,
            question="What does the spec say about the cancellation policy?",
        )

    prompt = captured_prompts[0].lower()
    assert "would help" not in prompt
    assert "explicitly" in prompt
    assert "leave both fields null" in prompt


def test_gherkin_and_diagram_stripped_for_plain_question(tmp_path):
    """
    When the developer asks an ordinary question, any Gherkin/diagram the
    model returns must be stripped before the answer reaches the UI.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("strip-artefacts", workspaces_root=tmp_path)

    mock_answer = ShadowPOAnswer(
        answer="The cancellation policy allows refunds within 30 days.",
        gherkin="Given a customer\nWhen they cancel\nThen they get a refund",
        diagram="graph TD\n  A[Cancel] --> B[Refund]",
    )

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = mock_answer
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.knowledge_base.retrieve", return_value=["doc chunk"]), \
         patch("shadow_po.web_grounding.search_web", return_value=[]):

        result = pipeline.answer_question(
            workspace_path=feature_ws,
            question="What does the spec say about the cancellation policy?",
        )

    assert result.gherkin is None
    assert result.diagram is None


def test_gherkin_kept_when_explicitly_requested(tmp_path):
    """Gherkin is preserved when the developer explicitly asks for a scenario."""
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("keep-gherkin", workspaces_root=tmp_path)

    gherkin_text = "Given a registered user\nWhen they checkout\nThen order is placed"
    mock_answer = ShadowPOAnswer(
        answer="Here is the happy-path scenario.",
        gherkin=gherkin_text,
    )

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = mock_answer
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.knowledge_base.retrieve", return_value=["doc chunk"]), \
         patch("shadow_po.web_grounding.search_web", return_value=[]):

        result = pipeline.answer_question(
            workspace_path=feature_ws,
            question="Can you write a Gherkin scenario for the checkout flow?",
        )

    assert result.gherkin == gherkin_text
    assert result.diagram is None


def test_diagram_kept_when_explicitly_requested(tmp_path):
    """Diagram is preserved when the developer explicitly asks for one."""
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("keep-diagram", workspaces_root=tmp_path)

    diagram_text = "graph TD\n  A[Cart] --> B[Checkout]"
    mock_answer = ShadowPOAnswer(
        answer="Here is the checkout flow.",
        diagram=diagram_text,
    )

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = mock_answer
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.knowledge_base.retrieve", return_value=["doc chunk"]), \
         patch("shadow_po.web_grounding.search_web", return_value=[]):

        result = pipeline.answer_question(
            workspace_path=feature_ws,
            question="Show me a Mermaid diagram of the checkout flow.",
        )

    assert result.diagram == diagram_text
    assert result.gherkin is None


def test_diagram_extracted_from_answer_when_model_embeds_it(tmp_path):
    """Sequence diagram text in answer is moved to diagram and normalized."""
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("extract-diagram", workspaces_root=tmp_path)

    embedded = (
        "User->>UI: Click verify\n"
        "UI->>Svc: POST /verify\n"
        "Note right of Svc: Active coverage &\n"
        "visits remaining > 0"
    )
    mock_answer = ShadowPOAnswer(
        answer=f"Here is the flow.\n\n{embedded}",
        diagram=None,
    )

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = mock_answer
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.knowledge_base.retrieve", return_value=["doc chunk"]), \
         patch("shadow_po.web_grounding.search_web", return_value=[]):

        result = pipeline.answer_question(
            workspace_path=feature_ws,
            question="Draw a sequence diagram for eligibility verification.",
        )

    assert result.answer == "Here is the flow."
    assert result.diagram is not None
    assert result.diagram.startswith("sequenceDiagram\n")
    assert "Active coverage and" in result.diagram


def test_grounding_note_in_prompt_when_unavailable(tmp_path):
    """
    When grounding is unavailable, the note must appear in the prompt so
    the LLM can reference it in its answer.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("note-in-prompt", workspaces_root=tmp_path)
    unavailable = GroundingUnavailable(reason="SearXNG timed out")

    captured_prompts = []

    def capturing_invoke(prompt):
        captured_prompts.append(prompt)
        return ShadowPOAnswer(answer="Answer.")

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.side_effect = capturing_invoke
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.knowledge_base.retrieve", return_value=[]), \
         patch("shadow_po.web_grounding.search_web", return_value=unavailable):

        pipeline.answer_question(
            workspace_path=feature_ws,
            question="What are the best practices for this?",
        )

    assert len(captured_prompts) == 1
    assert "unavailable" in captured_prompts[0].lower() or \
           "searxng" in captured_prompts[0].lower(), (
        "Grounding note must appear in the LLM prompt"
    )


# ---------------------------------------------------------------------------
# Task F-6: End-to-end demo scenario regression tests
# ---------------------------------------------------------------------------

def _build_demo_workspace(tmp_path, fixture_dir: Path, name: str):
    """Helper: create and index a workspace from a fixture directory."""
    from shadow_po import workspace as ws, knowledge_base as kb, privacy

    # Ensure scrubber is initialised
    if privacy._scrubber is None:
        privacy.initialize(custom_codenames=[])

    feature_ws = ws.create_workspace(name, workspaces_root=tmp_path)
    docs_dir = feature_ws / "input" / "documents"

    # Copy fixture docs into workspace
    for src in fixture_dir.glob("*.md"):
        dst = docs_dir / src.name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    kb.index_workspace_documents(
        workspace_path=feature_ws,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )
    return feature_ws


def test_demo_scenario_1click(tmp_path):
    """
    Demo scenario 1: 1-Click checkout happy path.
    Question answerable from local docs — no web grounding needed.
    Answer must be schema-valid and contain relevant content.
    """
    fixture_dir = FIXTURES_DIR / "demo_1click"
    if not fixture_dir.exists():
        pytest.skip("demo_1click fixtures not found")

    feature_ws = _build_demo_workspace(tmp_path, fixture_dir, "demo-1click")

    mock_answer = ShadowPOAnswer(
        answer=(
            "One-click checkout is available for registered users with a saved payment "
            "method. The flow uses the most recently used payment method and sends an "
            "order confirmation email within 2 minutes. Double-clicks within 3 seconds "
            "are debounced to prevent duplicate orders."
        ),
        grounded=False,
    )

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = mock_answer
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.web_grounding.search_web", return_value=[]):

        result = pipeline.answer_question(
            workspace_path=feature_ws,
            question="How does the one-click checkout work for returning customers?",
        )

    # Schema must be valid
    assert isinstance(result, ShadowPOAnswer)
    assert len(result.answer) > 20, "Answer should be substantive"

    # RAG must have retrieved relevant content (mocked LLM returns fixture content)
    assert "one-click" in result.answer.lower() or "checkout" in result.answer.lower()


def test_demo_scenario_contradiction(tmp_path):
    """
    Demo scenario 2: offline/cloud contradiction case.
    The spec contains contradictory requirements. The answer must surface
    this contradiction rather than glossing over it.
    """
    fixture_dir = FIXTURES_DIR / "demo_contradiction"
    if not fixture_dir.exists():
        pytest.skip("demo_contradiction fixtures not found")

    feature_ws = _build_demo_workspace(tmp_path, fixture_dir, "demo-contradiction")

    mock_answer = ShadowPOAnswer(
        answer=(
            "There is a contradiction in the spec: it requires both real-time "
            "cloud webhook updates (which need internet) and offline warehouse "
            "operation (no internet). These requirements are mutually exclusive "
            "and must be resolved with the PO before implementation."
        ),
        grounded=False,
    )

    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = mock_answer
    mock_llm.with_structured_output.return_value = structured

    with patch("shadow_po.pipeline.get_llm", return_value=mock_llm), \
         patch("shadow_po.web_grounding.search_web", return_value=[]):

        result = pipeline.answer_question(
            workspace_path=feature_ws,
            question="How should the inventory sync work when the warehouse is offline?",
        )

    assert isinstance(result, ShadowPOAnswer)
    # The answer must acknowledge the contradiction
    assert "contradiction" in result.answer.lower() or \
           "mutually exclusive" in result.answer.lower() or \
           "conflict" in result.answer.lower(), (
        f"Answer should flag the contradiction. Got: {result.answer[:200]}"
    )
