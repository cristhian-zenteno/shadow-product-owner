"""
Normalize and extract Mermaid diagram source so it renders in standard parsers.

LLM output often omits the diagram-type declaration (e.g. sequenceDiagram),
embeds diagrams in the plain answer field, or produces multi-line Note blocks
that Mermaid cannot parse.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

_DIAGRAM_TYPE_RE = re.compile(
    r"^\s*(sequenceDiagram|graph\s+\w+|flowchart\s+\w+|classDiagram|"
    r"stateDiagram(?:-v2)?|erDiagram|gantt|pie|gitGraph|journey|C4Context)\b",
    re.I | re.M,
)

_SEQUENCE_ARROW_RE = re.compile(
    r"^\s*\w+\s*(?:->>|-->>|--x|-x|->)\+?\s*\w+\s*:",
    re.I,
)

_SEQUENCE_KEYWORD_RE = re.compile(
    r"^\s*(?:participant|actor|Note\b|loop\b|alt\b|else\b|opt\b|par\b|rect\b|"
    r"activate\b|deactivate\b|end\b)\b",
    re.I,
)

_NOTE_RE = re.compile(r"^(\s*Note\s+(?:left of|right of|over)\s+[^:]+:\s*)(.*)$", re.I)


def strip_fenced_code(text: str) -> str:
    """Return the inner source of a fenced code block, or the text unchanged."""
    text = text.strip()
    fence_match = re.match(
        r"^```(?:mermaid)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE
    )
    if fence_match:
        return fence_match.group(1).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines)
        if end > 1 and lines[-1].strip() == "```":
            end -= 1
        return "\n".join(lines[start:end]).strip()
    return text


def looks_like_sequence_diagram(source: str) -> bool:
    """Return True when source appears to be a Mermaid sequence diagram body."""
    source = strip_fenced_code(source)
    lines = [line for line in source.splitlines() if line.strip()]
    if not lines:
        return False
    sequence_lines = sum(
        1
        for line in lines
        if _SEQUENCE_ARROW_RE.match(line) or _SEQUENCE_KEYWORD_RE.match(line)
    )
    return sequence_lines >= 2


def _merge_multiline_notes(lines: list[str]) -> list[str]:
    """Merge orphaned continuation lines into the preceding Note statement."""
    merged: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _NOTE_RE.match(stripped) or not merged:
            merged.append(stripped)
            continue
        if _NOTE_RE.match(merged[-1]):
            merged[-1] = f"{merged[-1]} {stripped}"
            continue
        merged.append(stripped)
    return merged


def _sanitize_note_text(note_text: str) -> str:
    """Replace characters that commonly break Mermaid Note parsing."""
    sanitized = note_text.replace("&", "and")
    sanitized = sanitized.replace("→", "->")
    sanitized = re.sub(r"\s*>\s*0", " greater than 0", sanitized)
    return sanitized.strip()


def _sanitize_notes(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        match = _NOTE_RE.match(line)
        if not match:
            result.append(line)
            continue
        prefix, note_text = match.groups()
        result.append(f"{prefix}{_sanitize_note_text(note_text)}")
    return result


def normalize_mermaid_source(source: str) -> str:
    """
    Return Mermaid source that standard renderers can parse.

    - Strips markdown fences
    - Adds ``sequenceDiagram`` when missing but content is a sequence diagram
    - Merges multi-line Note blocks into a single line
    - Sanitizes Note text that contains ``&``, ``→``, or ``>`` comparisons
    """
    source = strip_fenced_code(source)
    if not source:
        return source

    is_sequence = looks_like_sequence_diagram(source)
    if not _DIAGRAM_TYPE_RE.search(source) and is_sequence:
        source = f"sequenceDiagram\n{source}"

    if is_sequence or source.lstrip().startswith("sequenceDiagram"):
        lines = _sanitize_notes(_merge_multiline_notes(source.splitlines()))
        return "\n".join(lines).strip()

    return source.strip()


def split_answer_and_diagram(answer: str) -> Tuple[str, Optional[str]]:
    """
    When the model embeds a sequence diagram in the answer field, split it out.

    Returns:
        (remaining_answer, diagram_source_or_none)
    """
    lines = answer.splitlines()
    diagram_start: Optional[int] = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _SEQUENCE_ARROW_RE.match(stripped) or _NOTE_RE.match(stripped):
            diagram_start = index
            break

    if diagram_start is None:
        return answer, None

    before = "\n".join(lines[:diagram_start]).strip()
    diagram_source = "\n".join(lines[diagram_start:]).strip()
    if not diagram_source:
        return answer, None

    remaining = before or "Here is the requested diagram."
    return remaining, diagram_source


def format_mermaid_block(diagram: str) -> str:
    """Wrap normalized Mermaid source in a standard fenced block for storage."""
    source = normalize_mermaid_source(diagram)
    return f"```mermaid\n{source}\n```"
