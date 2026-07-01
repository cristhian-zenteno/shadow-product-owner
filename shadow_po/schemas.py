"""
Pydantic schemas for structured LLM output - Component F

Two separate schemas per SPECIFY.md §8:
- ShadowPOAnswer: conversational chat answer (plain-language + optional Gherkin/diagram)
- GeneratedDocs:  "Generate docs" four-file package (used by Component I)
"""

from typing import Optional
from pydantic import BaseModel, Field


class ShadowPOAnswer(BaseModel):
    """
    Schema for a single chat answer from the LLM.

    Conversational, not a finished deliverable — it answers the current
    question and may include supporting artefacts when relevant.

    Fields:
        answer:   Plain-language response to the question (always present)
        gherkin:  Gherkin scenario(s) if the question called for one (optional)
        diagram:  Mermaid diagram if the question called for one (optional)
        grounded: True if web search results were used in the answer
        grounding_note: Human-readable note when grounding was unavailable
    """

    answer: str = Field(
        ...,
        description="Plain-language answer to the developer's question",
        min_length=1,
    )
    gherkin: Optional[str] = Field(
        default=None,
        description="Gherkin scenario(s) if the question requested them",
    )
    diagram: Optional[str] = Field(
        default=None,
        description="Mermaid diagram source if the question requested one",
    )
    grounded: bool = Field(
        default=False,
        description="Whether web search results contributed to this answer",
    )
    grounding_note: Optional[str] = Field(
        default=None,
        description=(
            "Set when web grounding was attempted but unavailable, so the "
            "answer explicitly flags this rather than answering as if grounded"
        ),
    )


class GeneratedDocs(BaseModel):
    """
    Schema for the four-file 'Generate docs' output package.

    Each field maps directly to one file written into the timestamped
    output folder by Component I.  The model produces all four in one call;
    Component I splits them into separate files.
    """

    business_rules: str = Field(
        ...,
        description=(
            "business-rules.md content: feature objective, PO-said vs "
            "PO-meant translation, key rules and constraints"
        ),
        min_length=1,
    )
    scenarios: str = Field(
        ...,
        description=(
            "scenarios.md content: Gherkin happy-path and edge-case scenarios"
        ),
        min_length=1,
    )
    diagram: str = Field(
        ...,
        description=(
            "diagram.md content: Mermaid architecture/flow diagram source"
        ),
        min_length=1,
    )
    open_questions: str = Field(
        ...,
        description=(
            "open-questions.md content: critical questions still worth "
            "raising with the PO (already filtered against answered-questions.md)"
        ),
        min_length=1,
    )
