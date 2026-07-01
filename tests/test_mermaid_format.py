"""
Tests for Mermaid diagram normalization and extraction.
"""

from shadow_po.mermaid_format import (
    format_mermaid_block,
    normalize_mermaid_source,
    split_answer_and_diagram,
)

ELIGIBILITY_SEQUENCE = """\
User->>UI: Clicks "Verify Benefits"
UI->>Svc: POST /eligibility/verify {patientId, appointmentId?}
Svc->>DB: Create record state = UNVERIFIED
Svc->>DB: Update state = PENDING_RESPONSE
Svc->>CH: Send EDI 270 (Loop 2110C/D, EQ01=30 or AD)
CH-->>Svc: Return EDI 271 (EB01=1 Active, EB03=30/AD, EB07>0, HSD=VS)
Svc->>Svc: Parse 271 → Policy Active, PT visits remaining > 0
Svc->>DB: Update state = VERIFIED, store benefits
Svc-->>UI: Return {status: GREEN, remainingVisits, copay, deductible…}
UI->>User: Show Green badge + benefit details

Note right of Svc: Happy path: Active coverage &
PT visits remaining > 0 → GREEN"""


def test_normalize_adds_sequence_diagram_header():
    result = normalize_mermaid_source(ELIGIBILITY_SEQUENCE)
    assert result.startswith("sequenceDiagram\n")


def test_normalize_merges_multiline_note():
    result = normalize_mermaid_source(ELIGIBILITY_SEQUENCE)
    note_lines = [line for line in result.splitlines() if line.strip().startswith("Note")]
    assert len(note_lines) == 1
    assert "Active coverage and" in note_lines[0]
    assert "greater than 0" in note_lines[0]


def test_split_answer_and_diagram_extracts_embedded_sequence():
    answer = f"Below is the flow.\n\n{ELIGIBILITY_SEQUENCE}"
    remaining, diagram = split_answer_and_diagram(answer)
    assert remaining == "Below is the flow."
    assert diagram is not None
    assert "User->>UI" in diagram


def test_format_mermaid_block_produces_copyable_fence():
    block = format_mermaid_block(ELIGIBILITY_SEQUENCE)
    assert block.startswith("```mermaid\nsequenceDiagram\n")
    assert block.endswith("\n```")
