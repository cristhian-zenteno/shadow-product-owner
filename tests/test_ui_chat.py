"""
Tests for chat UI formatting helpers.
"""

from shadow_po.ui_chat import _format_assistant_content
from shadow_po.mermaid_format import format_mermaid_block, strip_fenced_code
from shadow_po.schemas import ShadowPOAnswer


def test_strip_fenced_code_from_mermaid_block():
    raw = "```mermaid\ngraph TD\n  A --> B\n```"
    assert strip_fenced_code(raw) == "graph TD\n  A --> B"


def test_strip_fenced_code_passthrough_for_plain_source():
    raw = "graph TD\n  A --> B"
    assert strip_fenced_code(raw) == raw


def test_format_mermaid_block_wraps_plain_source():
    result = format_mermaid_block("graph TD\n  A --> B")
    assert result == "```mermaid\ngraph TD\n  A --> B\n```"


def test_format_mermaid_block_normalizes_existing_fence():
    wrapped = "```mermaid\ngraph TD\n  A --> B\n```"
    result = format_mermaid_block(wrapped)
    assert result == "```mermaid\ngraph TD\n  A --> B\n```"


def test_format_assistant_content_includes_copyable_diagram_block():
    answer = ShadowPOAnswer(
        answer="Here is the checkout flow.",
        diagram="graph TD\n  A[Cart] --> B[Checkout]",
    )
    text = _format_assistant_content(answer)
    assert "**Diagram:**" in text
    assert "```mermaid\ngraph TD\n  A[Cart] --> B[Checkout]\n```" in text


def test_format_assistant_content_strips_duplicate_gherkin_fences():
    answer = ShadowPOAnswer(
        answer="Scenario below.",
        gherkin="```gherkin\nGiven a user\nWhen they act\nThen it works\n```",
    )
    text = _format_assistant_content(answer)
    assert text.count("```gherkin") == 1
    assert "Given a user\nWhen they act\nThen it works" in text
