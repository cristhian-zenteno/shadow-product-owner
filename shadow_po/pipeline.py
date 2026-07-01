"""
LLM Orchestration - Component F

Wires together:
- Component B (privacy scrubber)  — question scrubbed before use
- Component D (RAG retrieval)     — per-feature document chunks
- Component E (web grounding)     — live SearXNG search, only when needed
- NVIDIA NIM API via ChatNVIDIA   — structured output with Pydantic schema

Public API:
    get_llm()               → ChatNVIDIA instance (raises if key missing)
    answer_question(...)    → ShadowPOAnswer (schema-validated)

Per PLAN.md Risk R4: if grounding is unavailable the answer explicitly says so.
Per PLAN.md Risk R1: nothing reaches the model unscrubbed.
"""

import os
import logging
from typing import Optional, List

from shadow_po.schemas import ShadowPOAnswer
from shadow_po.web_grounding import GroundingUnavailable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Grounding decision keywords
# ---------------------------------------------------------------------------
# Questions that mention these terms plausibly need current/public information
# and should trigger a web search.  Questions answerable from local docs alone
# should not trigger a (slow) search on every turn.
import re

_GHERKIN_PATTERNS = [
    re.compile(r"\bgherkin\b", re.I),
    re.compile(r"\bbdd\b", re.I),
    re.compile(r"\b(write|show|give|create|provide|draft).{0,40}\bscenario", re.I),
    re.compile(r"\bscenario.{0,20}\b(gherkin|bdd|format)\b", re.I),
    re.compile(r"\bin (gherkin|bdd)\b", re.I),
    re.compile(r"\bas (a )?(gherkin|bdd)\b", re.I),
]

_DIAGRAM_PATTERNS = [
    re.compile(r"\bdiagram\b", re.I),
    re.compile(r"\bflowchart\b", re.I),
    re.compile(r"\bflow chart\b", re.I),
    re.compile(r"\bmermaid\b", re.I),
    re.compile(r"\bsequence diagram\b", re.I),
    re.compile(
        r"\b(write|show|give|create|provide|draw|sketch).{0,40}\b"
        r"(diagram|flowchart|flow chart)\b",
        re.I,
    ),
    re.compile(r"\bvisuali[sz]e\b", re.I),
]

_GROUNDING_PATTERNS = [
    re.compile(r"\bindustry standard", re.I),
    re.compile(r"\bbest practices?\b", re.I),
    re.compile(r"\bcurrent\b", re.I),
    re.compile(r"\blatest\b", re.I),
    re.compile(r"\btoday\b", re.I),
    re.compile(r"\bmodern\b", re.I),
    re.compile(r"\btrend\b", re.I),
    re.compile(r"\bpopular\b", re.I),
    re.compile(r"\bcommon approach\b", re.I),
    re.compile(r"\brecommended\b", re.I),
    re.compile(r"\bstate[- ]of[- ]the[- ]art\b", re.I),
    re.compile(r"\bregulation\b", re.I),
    re.compile(r"\bcompliance\b", re.I),
    re.compile(r"\bgdpr\b", re.I),
    re.compile(r"\bpci\b", re.I),
    re.compile(r"\biso\b", re.I),
    re.compile(r"\brfc\b", re.I),
    re.compile(r"\bhow does .{0,30} work\b", re.I),
    re.compile(r"\bwhat is .{0,30}\?", re.I),
    re.compile(r"\bwhat are .{0,30}\?", re.I),
]


def _requests_gherkin(question: str) -> bool:
    """True when the developer explicitly asked for a Gherkin scenario."""
    return any(p.search(question) for p in _GHERKIN_PATTERNS)


def _requests_diagram(question: str) -> bool:
    """True when the developer explicitly asked for a Mermaid diagram."""
    return any(p.search(question) for p in _DIAGRAM_PATTERNS)


def _needs_grounding(question: str) -> bool:
    """
    Heuristic: does this question plausibly need current public information
    that wouldn't be in the workspace documents?

    Uses word-boundary regex patterns to avoid false positives from substring
    matches (e.g. "What does" should NOT match "What is / What are").
    """
    return any(p.search(question) for p in _GROUNDING_PATTERNS)


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def get_llm(
    model_name: str = "nvidia/nemotron-ultra-253b-v1",
    timeout: float = 60,
    max_completion_tokens: Optional[int] = None,
):
    """
    Return a configured ChatNVIDIA instance.

    Raises a clear RuntimeError if NVIDIA_API_KEY is not set rather than
    failing deep inside a chain call with a cryptic auth error.

    Args:
        model_name: NVIDIA NIM model identifier (default: nemotron-ultra-253b)
        timeout:    HTTP read timeout in seconds (default: 60)
        max_completion_tokens: Cap on generated tokens (default: ChatNVIDIA's 1024)

    Returns:
        ChatNVIDIA instance ready for structured-output chaining

    Raises:
        RuntimeError: If NVIDIA_API_KEY environment variable is not set
    """
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NVIDIA_API_KEY environment variable is not set.\n"
            "Set it in your .env file or environment before starting the app."
        )

    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
    except ImportError as exc:
        raise RuntimeError(
            "langchain-nvidia-ai-endpoints is not installed.\n"
            "Run: uv add langchain-nvidia-ai-endpoints"
        ) from exc

    if max_completion_tokens is not None:
        logger.info(
            f"Initialising ChatNVIDIA with model: {model_name} "
            f"(timeout={timeout}s, max_completion_tokens={max_completion_tokens})"
        )
    else:
        logger.info(
            f"Initialising ChatNVIDIA with model: {model_name} (timeout={timeout}s)"
        )

    llm_kwargs = {
        "model": model_name,
        "api_key": api_key,
        "temperature": 0.2,
        "timeout": timeout,
    }
    if max_completion_tokens is not None:
        llm_kwargs["max_completion_tokens"] = max_completion_tokens

    return ChatNVIDIA(**llm_kwargs)


# ---------------------------------------------------------------------------
# Chat chain
# ---------------------------------------------------------------------------

def answer_question(
    workspace_path,
    question: str,
    searxng_url: str = "http://localhost:8080",
    model_name: str = "nvidia/nemotron-ultra-253b-v1",
    k: int = 5,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    timeout: float = 60,
) -> ShadowPOAnswer:
    """
    Answer a developer question by assembling:
    1. Scrubbed question
    2. Relevant RAG chunks from this workspace's index (Component D)
    3. Live web search snippets — only when genuinely needed (Component E)
    4. NVIDIA NIM LLM call with structured output (Component F)

    Args:
        workspace_path: Path to the feature workspace root
        question:       Raw question from the developer (scrubbed internally)
        searxng_url:    URL of the local SearXNG instance
        model_name:     NVIDIA NIM model identifier
        k:              Number of RAG chunks to retrieve
        embedding_model: sentence-transformers model used at indexing time
        timeout:        HTTP read timeout in seconds for the LLM call

    Returns:
        ShadowPOAnswer (schema-validated Pydantic model)

    Raises:
        RuntimeError: If privacy scrubber not initialised or NVIDIA_API_KEY missing
    """
    from shadow_po import privacy
    from shadow_po import knowledge_base as kb
    from shadow_po import web_grounding

    if privacy._scrubber is None:
        raise RuntimeError(
            "Privacy scrubber not initialised. "
            "Call privacy.initialize() before answer_question()."
        )

    # 1. Scrub the question (Zero-Trust boundary)
    scrubbed_question = privacy.scrub(question)
    logger.info(f"Scrubbed question: '{scrubbed_question[:80]}'")

    # 2. Retrieve relevant RAG chunks from this workspace
    chunks: List[str] = kb.retrieve(
        workspace_path=workspace_path,
        query=scrubbed_question,
        k=k,
        embedding_model=embedding_model,
    )
    logger.info(f"Retrieved {len(chunks)} RAG chunks")

    # 3. Decide whether to call web grounding
    grounded = False
    grounding_note: Optional[str] = None
    web_snippets: List[str] = []

    if _needs_grounding(scrubbed_question):
        logger.info("Question may need web grounding — calling SearXNG")
        search_result = web_grounding.search_web(
            query=scrubbed_question,
            searxng_url=searxng_url,
        )

        if isinstance(search_result, GroundingUnavailable):
            # Risk R4: tell the model — and therefore the user — grounding failed
            grounding_note = (
                f"Web grounding was attempted but SearXNG was unavailable: "
                f"{search_result.reason}. "
                "This answer is based on workspace documents only."
            )
            logger.warning(f"Grounding unavailable: {search_result.reason}")
        else:
            web_snippets = [
                f"[{r['title']}]({r['url']}): {r['snippet']}"
                for r in search_result
                if r.get("snippet")
            ]
            grounded = bool(web_snippets)
            logger.info(f"Web grounding returned {len(web_snippets)} snippets")
    else:
        logger.info("Question answerable from local docs — skipping web grounding")

    # 4. Assemble the prompt
    wants_gherkin = _requests_gherkin(scrubbed_question)
    wants_diagram = _requests_diagram(scrubbed_question)
    prompt = _build_prompt(
        question=scrubbed_question,
        chunks=chunks,
        web_snippets=web_snippets,
        grounding_note=grounding_note,
        wants_gherkin=wants_gherkin,
        wants_diagram=wants_diagram,
    )

    # 5. Call the LLM with structured output
    llm = get_llm(model_name=model_name, timeout=timeout)
    structured_llm = llm.with_structured_output(ShadowPOAnswer)

    logger.info("Calling NVIDIA NIM LLM")
    raw_answer: ShadowPOAnswer = structured_llm.invoke(prompt)

    # Patch grounding metadata onto the returned schema object
    # (structured output may not set these correctly from the prompt alone)
    raw_answer.grounded = grounded
    if grounding_note:
        raw_answer.grounding_note = grounding_note

    # Per SPECIFY.md §8: Gherkin/diagram only when explicitly requested
    if not wants_gherkin:
        raw_answer.gherkin = None
    if wants_diagram:
        from shadow_po.mermaid_format import normalize_mermaid_source, split_answer_and_diagram

        if not raw_answer.diagram:
            cleaned_answer, extracted = split_answer_and_diagram(raw_answer.answer)
            if extracted:
                raw_answer.answer = cleaned_answer
                raw_answer.diagram = extracted
        if raw_answer.diagram:
            raw_answer.diagram = normalize_mermaid_source(raw_answer.diagram)
    else:
        raw_answer.diagram = None

    logger.info("LLM call complete — returning schema-validated answer")

    return raw_answer


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def _build_prompt(
    question: str,
    chunks: List[str],
    web_snippets: List[str],
    grounding_note: Optional[str],
    wants_gherkin: bool = False,
    wants_diagram: bool = False,
) -> str:
    """
    Assemble the full prompt sent to the LLM.

    Args:
        question:       Scrubbed developer question
        chunks:         Retrieved RAG chunks (may be empty)
        web_snippets:   Formatted web search results (may be empty)
        grounding_note: Reason string if grounding was unavailable (or None)

    Returns:
        Prompt string ready for the LLM
    """
    sections = [
        "You are Shadow PO, an expert AI assistant helping software engineers "
        "understand ambiguous product requirements.\n"
        "Answer the developer's question clearly and concisely, grounded in the "
        "provided context.\n\n"
        "Only populate the `gherkin` and `diagram` fields when the developer "
        "explicitly asks for a Gherkin scenario or a Mermaid diagram (e.g. "
        "'show me a diagram', 'write a Gherkin scenario'). For ordinary "
        "questions, leave both fields null and answer in plain language only. "
        "Do not include Gherkin or diagrams just because they might be helpful.\n"
    ]

    if wants_diagram:
        sections.append(
            "## Diagram requirements\n"
            "The developer asked for a Mermaid diagram. Put the full diagram "
            "source in the `diagram` field only — not in `answer`.\n"
            "- Start with a valid declaration: `sequenceDiagram`, "
            "`flowchart TD`, etc.\n"
            "- For sequence diagrams, declare arrows as `A->>B: message`.\n"
            "- Each `Note` must be a single line; use `and` instead of `&`.\n"
            "- Avoid `>` comparisons inside Note text (write 'greater than 0').\n"
            "- Do not wrap the diagram in markdown code fences.\n"
        )

    if wants_gherkin:
        sections.append(
            "## Gherkin requirements\n"
            "Put the full scenario in the `gherkin` field only — not in `answer`.\n"
        )

    if chunks:
        sections.append("## Relevant workspace documents\n")
        for i, chunk in enumerate(chunks, 1):
            sections.append(f"### Chunk {i}\n{chunk}\n")
    else:
        sections.append(
            "## Relevant workspace documents\n"
            "_No indexed documents found for this workspace. "
            "Answer from general knowledge._\n"
        )

    if web_snippets:
        sections.append("## Web search results\n")
        for snippet in web_snippets:
            sections.append(f"- {snippet}\n")

    if grounding_note:
        sections.append(f"## Grounding note\n{grounding_note}\n")

    sections.append(f"## Developer question\n{question}")

    return "\n".join(sections)
