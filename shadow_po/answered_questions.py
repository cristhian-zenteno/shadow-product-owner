"""
Answered-Questions Tracking - Component H

Detects when a chat message answers a previously raised open question,
records the Q&A pair into input/documents/answered-questions.md, and
triggers Component D to re-index that file so the answer becomes
immediately retrievable in future chat turns.

Per SPECIFY.md §7:
- answered-questions.md is append-only (never edited after the fact)
- Each Q&A pair originates from something told to the app during chat
- Recording an answer does NOT modify past output/ snapshots
- After recording, the file is re-indexed via D so future retrieval sees it

This component depends on:
- Component A (workspace manager) — input/documents/ must exist
- Component D (knowledge_base.reindex_file) — H → D feedback loop
- Component F (pipeline) — provides the LLM for answer detection
"""

from pathlib import Path
from typing import Union, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


# Module-level alias so tests can patch 'shadow_po.answered_questions.get_llm'
# The real implementation is imported lazily inside detect_answered_question
# to avoid a circular import at load time (pipeline → answered_questions → pipeline).
def get_llm(model_name: str = "nvidia/nemotron-ultra-253b-v1"):
    """Thin wrapper around pipeline.get_llm — patchable at module level."""
    from shadow_po.pipeline import get_llm as _get_llm
    return _get_llm(model_name)


# ---------------------------------------------------------------------------
# Data type
# ---------------------------------------------------------------------------

@dataclass
class QAPair:
    """A detected question-and-answer pair from a chat conversation."""
    question: str
    answer: str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANSWERED_QUESTIONS_FILENAME = "answered-questions.md"


# ---------------------------------------------------------------------------
# H-1: Detect when a new message answers an open question
# ---------------------------------------------------------------------------

def detect_answered_question(
    conversation_history: list,
    new_message: str,
    model_name: str = "nvidia/nemotron-ultra-253b-v1",
) -> Optional[QAPair]:
    """
    Use the LLM to detect whether new_message is answering a previously
    raised open question from conversation_history.

    Sends a focused prompt to the LLM asking it to identify:
    1. The open question being answered (from prior assistant turns)
    2. The answer provided in new_message

    Returns a QAPair if an answer is detected, or None if the message
    doesn't appear to be answering an open question.

    Args:
        conversation_history: List of {"role", "content"} dicts (prior turns)
        new_message:          The new user message to evaluate
        model_name:           NVIDIA NIM model for detection

    Returns:
        QAPair if an answer is detected, None otherwise

    Raises:
        RuntimeError: If NVIDIA_API_KEY is not set
    """
    from shadow_po import privacy

    # Scrub new message before sending to LLM
    if privacy._scrubber is not None:
        scrubbed_message = privacy.scrub(new_message)
    else:
        raise RuntimeError(
            "Privacy scrubber not initialised. "
            "Call privacy.initialize() before detect_answered_question()."
        )

    # Extract open questions raised by the assistant in prior turns
    open_questions = _extract_open_questions(conversation_history)

    if not open_questions:
        logger.debug("No open questions found in conversation history")
        return None

    # Build a focused detection prompt
    prompt = _build_detection_prompt(
        open_questions=open_questions,
        new_message=scrubbed_message,
    )

    try:
        llm = get_llm(model_name=model_name)
        response = llm.invoke(prompt)

        # Parse the LLM response — expects "QUESTION: ...\nANSWER: ..." format
        qa_pair = _parse_detection_response(response.content)

        if qa_pair:
            logger.info(
                f"Detected answered question: "
                f"Q='{qa_pair.question[:60]}' A='{qa_pair.answer[:60]}'"
            )

        return qa_pair

    except Exception as exc:
        # Detection failure is non-fatal — log and return None
        # (missing an answer detection is acceptable; false positive is not)
        logger.warning(f"Answer detection failed (non-fatal): {exc}")
        return None


def _extract_open_questions(conversation_history: list) -> list:
    """
    Extract questions previously raised by the assistant from conversation
    history. Looks for question marks in assistant messages as a simple
    heuristic.

    Returns list of question strings.
    """
    questions = []
    for turn in conversation_history:
        if turn.get("role") == "assistant":
            content = turn.get("content", "")
            # Extract sentences ending with "?"
            for sentence in content.split("\n"):
                sentence = sentence.strip()
                if sentence.endswith("?") and len(sentence) > 15:
                    questions.append(sentence)
    return questions


def _build_detection_prompt(open_questions: list, new_message: str) -> str:
    """Build the focused detection prompt sent to the LLM."""
    questions_text = "\n".join(f"- {q}" for q in open_questions)

    return (
        "You are analyzing a product requirement chat to detect if a new message "
        "answers a previously raised open question.\n\n"
        "## Previously raised open questions:\n"
        f"{questions_text}\n\n"
        "## New message:\n"
        f"{new_message}\n\n"
        "If the new message clearly answers one of the open questions above, "
        "respond in EXACTLY this format:\n"
        "QUESTION: <the question being answered>\n"
        "ANSWER: <the answer provided>\n\n"
        "If the new message does NOT answer any of the open questions, "
        "respond with exactly: NO_ANSWER"
    )


def _parse_detection_response(response_text: str) -> Optional[QAPair]:
    """
    Parse the LLM detection response.

    Expected formats:
    - "QUESTION: ...\nANSWER: ..."  → returns QAPair
    - "NO_ANSWER"                    → returns None
    """
    text = response_text.strip()

    if "NO_ANSWER" in text.upper() or not text:
        return None

    question = ""
    answer = ""

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("QUESTION:"):
            question = line[len("QUESTION:"):].strip()
        elif line.upper().startswith("ANSWER:"):
            answer = line[len("ANSWER:"):].strip()

    if question and answer:
        return QAPair(question=question, answer=answer)

    # If the format wasn't followed but has content, treat the whole
    # response as evidence of an answer and return None to be safe
    # (better to miss a detection than to record a malformed one)
    logger.debug(f"Could not parse detection response format: {text[:100]}")
    return None


# ---------------------------------------------------------------------------
# H-2: Append detected answers to answered-questions.md
# ---------------------------------------------------------------------------

def record_answer(
    workspace_path: Union[str, Path],
    qa_pair: QAPair,
) -> Path:
    """
    Append a Q&A pair to that feature's answered-questions.md.

    The file is created if it doesn't exist yet (first recorded answer).
    All subsequent calls append — the file is never overwritten.

    Per SPECIFY.md §7: this file lives in input/documents/ alongside
    other source-of-truth files, not in output/.

    Args:
        workspace_path: Path to the feature workspace root
        qa_pair:        Detected Q&A pair to record

    Returns:
        Path to the answered-questions.md file

    Raises:
        FileNotFoundError: If workspace or input/documents/ does not exist
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        raise FileNotFoundError(
            f"Workspace not found: {workspace_path}\n"
            "Create it with workspace.create_workspace() first."
        )

    docs_dir = workspace / "input" / "documents"

    if not docs_dir.exists():
        raise FileNotFoundError(
            f"input/documents/ directory not found in workspace: {workspace_path}\n"
            "Ensure the workspace was created with workspace.create_workspace()."
        )

    aq_file = docs_dir / ANSWERED_QUESTIONS_FILENAME
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    entry = (
        f"## Q&A — {timestamp}\n\n"
        f"**Question:** {qa_pair.question}\n\n"
        f"**Answer:** {qa_pair.answer}\n\n"
        f"---\n\n"
    )

    if not aq_file.exists():
        header = (
            "# Answered Questions\n\n"
            "This file records questions raised during chat that have been "
            "answered by the Product Owner.\n"
            "It is used by 'Generate docs' to exclude already-answered questions "
            "from the open-questions list.\n\n"
            "---\n\n"
        )
        aq_file.write_text(header + entry, encoding="utf-8")
        logger.info(f"Created answered-questions.md: {aq_file}")
    else:
        with aq_file.open("a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(f"Appended Q&A to answered-questions.md: {aq_file}")

    return aq_file


# ---------------------------------------------------------------------------
# H-3: Trigger re-indexing after recording
# ---------------------------------------------------------------------------

def record_answer_and_reindex(
    workspace_path: Union[str, Path],
    qa_pair: QAPair,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> Path:
    """
    Record an answer and immediately re-index answered-questions.md so the
    new answer is retrievable in future chat turns without a full rebuild.

    This is the H → D feedback loop described in PLAN.md §1.

    Args:
        workspace_path:  Path to the feature workspace root
        qa_pair:         Detected Q&A pair to record
        embedding_model: sentence-transformers model used at indexing time

    Returns:
        Path to the answered-questions.md file

    Raises:
        FileNotFoundError: If workspace does not exist
        RuntimeError:      If privacy scrubber is not initialised
    """
    from shadow_po import knowledge_base as kb

    # Step 1: append to answered-questions.md
    aq_file = record_answer(workspace_path, qa_pair)

    # Step 2: re-index only that file (not the full workspace)
    new_chunks = kb.reindex_file(
        workspace_path=workspace_path,
        file_path=aq_file,
        embedding_model=embedding_model,
    )

    logger.info(
        f"Re-indexed answered-questions.md: {new_chunks} chunks now indexed"
    )

    return aq_file
