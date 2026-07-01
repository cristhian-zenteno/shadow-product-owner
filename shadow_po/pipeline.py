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

def get_llm(model_name: str = "nvidia/nemotron-ultra-253b-v1"):
    """
    Return a configured ChatNVIDIA instance.

    Raises a clear RuntimeError if NVIDIA_API_KEY is not set rather than
    failing deep inside a chain call with a cryptic auth error.

    Args:
        model_name: NVIDIA NIM model identifier (default: nemotron-ultra-253b)

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

    logger.info(f"Initialising ChatNVIDIA with model: {model_name}")

    return ChatNVIDIA(
        model=model_name,
        api_key=api_key,
        temperature=0.2,
    )


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
    prompt = _build_prompt(
        question=scrubbed_question,
        chunks=chunks,
        web_snippets=web_snippets,
        grounding_note=grounding_note,
    )

    # 5. Call the LLM with structured output
    llm = get_llm(model_name=model_name)
    structured_llm = llm.with_structured_output(ShadowPOAnswer)

    logger.info("Calling NVIDIA NIM LLM")
    raw_answer: ShadowPOAnswer = structured_llm.invoke(prompt)

    # Patch grounding metadata onto the returned schema object
    # (structured output may not set these correctly from the prompt alone)
    raw_answer.grounded = grounded
    if grounding_note:
        raw_answer.grounding_note = grounding_note

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
        "provided context. If Gherkin scenarios or a Mermaid diagram would help, "
        "include them.\n"
    ]

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
