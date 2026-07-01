"""
Tests for Pydantic output schemas - Component F

Verifies that ShadowPOAnswer and GeneratedDocs validate correctly.
"""

import pytest
from shadow_po.schemas import ShadowPOAnswer, GeneratedDocs


# ---------------------------------------------------------------------------
# ShadowPOAnswer
# ---------------------------------------------------------------------------

def test_shadow_po_answer_minimal():
    a = ShadowPOAnswer(answer="The feature works by X.")
    assert a.answer == "The feature works by X."
    assert a.gherkin is None
    assert a.diagram is None
    assert a.grounded is False
    assert a.grounding_note is None


def test_shadow_po_answer_full():
    a = ShadowPOAnswer(
        answer="Here is the full breakdown.",
        gherkin="Given a user\nWhen they act\nThen something happens",
        diagram="graph TD\n  A --> B",
        grounded=True,
    )
    assert a.grounded is True
    assert "Given" in a.gherkin
    assert "graph" in a.diagram


def test_shadow_po_answer_empty_answer_rejected():
    with pytest.raises(Exception):
        ShadowPOAnswer(answer="")


def test_shadow_po_answer_grounding_note():
    a = ShadowPOAnswer(
        answer="Answer without grounding.",
        grounded=False,
        grounding_note="SearXNG was unavailable.",
    )
    assert a.grounding_note == "SearXNG was unavailable."


# ---------------------------------------------------------------------------
# GeneratedDocs
# ---------------------------------------------------------------------------

def test_generated_docs_valid():
    d = GeneratedDocs(
        business_rules="## Business Rules\n- Rule 1\n- Rule 2",
        scenarios="## Scenarios\nGiven...\nWhen...\nThen...",
        diagram="```mermaid\ngraph TD\n  A --> B\n```",
        open_questions="## Open Questions\n- Q1\n- Q2",
    )
    assert "Rule 1" in d.business_rules
    assert "Given" in d.scenarios
    assert "mermaid" in d.diagram
    assert "Q1" in d.open_questions


def test_generated_docs_rejects_empty_fields():
    with pytest.raises(Exception):
        GeneratedDocs(
            business_rules="",
            scenarios="some content",
            diagram="some diagram",
            open_questions="some questions",
        )
