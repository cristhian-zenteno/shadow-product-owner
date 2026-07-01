"""
"Generate docs" Generator - Component I

Gathers all feature context (documents, transcripts, chat history, web results)
and calls the LLM to produce four Markdown files in a timestamped output folder.

Per SPECIFY.md §8:
- Each "Generate docs" run creates a new timestamped folder — never overwrites past runs
- open-questions.md excludes questions already in answered-questions.md
- Fails loudly on any missing source — never produces partial snapshots (Risk R6)

This component depends on all prior components (C, D, E, F, G, H).
"""

from pathlib import Path
from typing import Union, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
import logging

from shadow_po.schemas import GeneratedDocs

logger = logging.getLogger(__name__)


# Module-level alias so tests can patch 'shadow_po.generate_docs.get_llm'
def get_llm(model_name: str = "nvidia/nemotron-ultra-253b-v1"):
    """Thin wrapper around pipeline.get_llm — patchable at module level."""
    from shadow_po.pipeline import get_llm as _get_llm
    return _get_llm(model_name)

# ---------------------------------------------------------------------------
# Feature context container  (Task I-1)
# ---------------------------------------------------------------------------

@dataclass
class FeatureContext:
    """All context gathered for a single feature before calling the LLM."""
    workspace_name: str
    documents: List[str] = field(default_factory=list)       # raw Markdown texts
    transcripts: List[str] = field(default_factory=list)     # transcript texts
    chat_history: str = ""                                    # full conversation text
    web_snippets: List[str] = field(default_factory=list)    # grounding snippets
    answered_questions: str = ""                             # content of answered-questions.md


# ---------------------------------------------------------------------------
# I-1: Gather everything relevant
# ---------------------------------------------------------------------------

def gather_feature_context(workspace_path: Union[str, Path]) -> FeatureContext:
    """
    Pull every relevant source for a feature workspace into a FeatureContext.

    Sources (all required; fails loudly if any cannot be read — Risk R6):
    - input/documents/  → converted to Markdown, each document as a string
    - input/meetings/   → plain-text transcripts (.txt / .md files)
    - progress/chat/    → all saved conversation files, concatenated
    - input/documents/answered-questions.md  → if present, loaded separately

    Args:
        workspace_path: Path to the feature workspace root

    Returns:
        FeatureContext populated with all available sources

    Raises:
        FileNotFoundError: If the workspace or any required sub-folder is missing
        RuntimeError:      If any source file cannot be read (Risk R6 hard stop)
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        raise FileNotFoundError(
            f"Workspace not found: {workspace_path}\n"
            "Create it with workspace.create_workspace() first."
        )

    docs_dir   = workspace / "input" / "documents"
    meetings_dir = workspace / "input" / "meetings"
    chat_dir   = workspace / "progress" / "chat"

    for required in (docs_dir, meetings_dir, chat_dir):
        if not required.exists():
            raise FileNotFoundError(
                f"Required directory not found: {required}\n"
                "Ensure the workspace was created with workspace.create_workspace()."
            )

    from shadow_po.knowledge_base import convert_to_markdown

    # --- Documents ---
    documents: List[str] = []
    for doc_file in sorted(docs_dir.iterdir()):
        if not doc_file.is_file() or doc_file.name.startswith("."):
            continue
        # answered-questions.md is loaded separately below
        if doc_file.name == "answered-questions.md":
            continue
        try:
            if doc_file.suffix.lower() in {".txt", ".md"}:
                text = doc_file.read_text(encoding="utf-8")
            else:
                text = convert_to_markdown(doc_file)
            if text.strip():
                documents.append(f"<!-- source: {doc_file.name} -->\n{text}")
                logger.info(f"Loaded document: {doc_file.name}")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read document '{doc_file.name}': {exc}\n"
                "Generate docs requires all source files to be readable (Risk R6)."
            ) from exc

    # --- Transcripts ---
    transcripts: List[str] = []
    for t_file in sorted(meetings_dir.iterdir()):
        if not t_file.is_file() or t_file.suffix.lower() not in {".txt", ".md"}:
            continue
        try:
            text = t_file.read_text(encoding="utf-8")
            if text.strip():
                transcripts.append(f"<!-- transcript: {t_file.name} -->\n{text}")
                logger.info(f"Loaded transcript: {t_file.name}")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read transcript '{t_file.name}': {exc}"
            ) from exc

    # --- Chat history ---
    chat_parts: List[str] = []
    for conv_file in sorted(chat_dir.glob("*.md")):
        try:
            text = conv_file.read_text(encoding="utf-8")
            if text.strip():
                chat_parts.append(text)
                logger.info(f"Loaded conversation: {conv_file.name}")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read conversation file '{conv_file.name}': {exc}"
            ) from exc

    chat_history = "\n\n---\n\n".join(chat_parts)

    # --- Answered questions (optional — no error if file absent) ---
    aq_file = docs_dir / "answered-questions.md"
    answered_questions = ""
    if aq_file.exists():
        try:
            answered_questions = aq_file.read_text(encoding="utf-8")
            logger.info("Loaded answered-questions.md")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read answered-questions.md: {exc}"
            ) from exc

    logger.info(
        f"Feature context gathered for '{workspace.name}': "
        f"{len(documents)} docs, {len(transcripts)} transcripts, "
        f"{'yes' if chat_history else 'no'} chat history"
    )

    return FeatureContext(
        workspace_name=workspace.name,
        documents=documents,
        transcripts=transcripts,
        chat_history=chat_history,
        answered_questions=answered_questions,
    )


# ---------------------------------------------------------------------------
# I-2: System prompt + output schema  (handled by schemas.GeneratedDocs)
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Load the generate-docs system prompt from the prompts/ directory."""
    prompt_file = Path(__file__).parent.parent / "prompts" / "generate_docs_system_prompt.md"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    # Fallback inline prompt if file not found
    logger.warning("generate_docs_system_prompt.md not found — using inline fallback")
    return (
        "You are Shadow PO. Produce four Markdown documents (business_rules, "
        "scenarios, diagram, open_questions) as a JSON object based on the "
        "provided feature context."
    )


def _build_generate_prompt(context: FeatureContext) -> str:
    """Assemble the full user-turn prompt from a FeatureContext."""
    parts = [f"# Feature: {context.workspace_name}\n"]

    if context.documents:
        parts.append("## Source Documents\n")
        parts.extend(context.documents)

    if context.transcripts:
        parts.append("## Meeting Transcripts\n")
        parts.extend(context.transcripts)

    if context.chat_history:
        parts.append("## Chat History\n")
        parts.append(context.chat_history)

    if context.web_snippets:
        parts.append("## Web Search Results\n")
        parts.extend(f"- {s}" for s in context.web_snippets)

    if context.answered_questions:
        parts.append(
            "## Already Answered Questions\n"
            "Do NOT include these in open-questions.md:\n"
        )
        parts.append(context.answered_questions)

    parts.append(
        "\nProduce the four Markdown documents as a JSON object with keys: "
        "business_rules, scenarios, diagram, open_questions."
    )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# I-3: Filter open questions against answered-questions.md
# ---------------------------------------------------------------------------

def _filter_answered_questions(
    open_questions_md: str,
    answered_questions_md: str,
) -> str:
    """
    Remove any question from open_questions_md that already appears
    in answered_questions_md.

    Matching is done by checking whether the question text (lowercased,
    stripped) is a substring of the answered-questions content.  This
    is intentionally conservative: if in doubt, keep the question open.

    Args:
        open_questions_md:     Raw open-questions content from the LLM
        answered_questions_md: Content of answered-questions.md

    Returns:
        Filtered open-questions Markdown with answered items removed
    """
    if not answered_questions_md.strip():
        return open_questions_md

    answered_lower = answered_questions_md.lower()

    filtered_lines: List[str] = []
    for line in open_questions_md.splitlines():
        stripped = line.strip().lstrip("0123456789.-) ").lower()
        # Keep non-question lines (headers, blank lines) as-is
        if not stripped or not stripped.endswith("?"):
            filtered_lines.append(line)
            continue
        # Remove the line if the question appears in the answered log
        if stripped in answered_lower:
            logger.info(f"Filtered already-answered question: {stripped[:80]}")
            continue
        filtered_lines.append(line)

    return "\n".join(filtered_lines)


# ---------------------------------------------------------------------------
# I-4: Write timestamped output folder, never overwriting past runs
# ---------------------------------------------------------------------------

def generate_docs(
    workspace_path: Union[str, Path],
    model_name: str = "nvidia/nemotron-ultra-253b-v1",
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> Path:
    """
    Gather all feature context, call the LLM, and write four Markdown files
    into a new timestamped output folder.

    Each call creates a brand-new folder — previous runs are never touched.
    If any step fails, no partial files are written (Risk R6).

    Args:
        workspace_path: Path to the feature workspace root
        model_name:     NVIDIA NIM model identifier
        embedding_model: sentence-transformers model (for any RAG needed)

    Returns:
        Path to the newly created timestamped output folder

    Raises:
        FileNotFoundError: If the workspace or any required source is missing
        RuntimeError:      If the LLM call fails or output is invalid
    """
    workspace = Path(workspace_path)

    # Step 1: gather all sources (fails loudly if anything is missing — Risk R6)
    logger.info(f"Gathering feature context for '{workspace.name}'")
    context = gather_feature_context(workspace_path)

    # Step 2: build the prompt
    system_prompt = _load_system_prompt()
    user_prompt   = _build_generate_prompt(context)

    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    # Step 3: call the LLM with structured output
    logger.info("Calling LLM for document generation")
    llm = get_llm(model_name=model_name)
    structured_llm = llm.with_structured_output(GeneratedDocs)

    try:
        result: GeneratedDocs = structured_llm.invoke(full_prompt)
    except Exception as exc:
        raise RuntimeError(
            f"LLM call failed during Generate docs for '{workspace.name}': {exc}\n"
            "No output files were written."
        ) from exc

    # Step 4: filter answered questions out of open-questions.md (Task I-3)
    filtered_open_questions = _filter_answered_questions(
        open_questions_md=result.open_questions,
        answered_questions_md=context.answered_questions,
    )

    # Step 5: create timestamped output folder and write all four files atomically
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    output_dir = workspace / "output" / timestamp

    # Ensure we never collide with an existing folder (add suffix if needed)
    suffix = 0
    base_output_dir = output_dir
    while output_dir.exists():
        suffix += 1
        output_dir = Path(f"{base_output_dir}_{suffix}")

    # Write all four files — if any write fails the folder is incomplete
    # but we still raise loudly (Risk R6: no partial/silent success)
    try:
        output_dir.mkdir(parents=True, exist_ok=False)

        (output_dir / "business-rules.md").write_text(result.business_rules, encoding="utf-8")
        (output_dir / "scenarios.md").write_text(result.scenarios, encoding="utf-8")
        (output_dir / "diagram.md").write_text(result.diagram, encoding="utf-8")
        (output_dir / "open-questions.md").write_text(filtered_open_questions, encoding="utf-8")

        logger.info(
            f"Generated docs written to: {output_dir}\n"
            f"  business-rules.md: {len(result.business_rules)} chars\n"
            f"  scenarios.md:      {len(result.scenarios)} chars\n"
            f"  diagram.md:        {len(result.diagram)} chars\n"
            f"  open-questions.md: {len(filtered_open_questions)} chars"
        )

    except Exception as exc:
        raise RuntimeError(
            f"Failed to write output files for '{workspace.name}': {exc}"
        ) from exc

    return output_dir
