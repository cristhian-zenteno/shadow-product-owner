"""
Web Grounding - Component E

SearXNG client for live web search grounding.
Queries are scrubbed before leaving the machine (Zero-Trust edge perimeter).
Unavailability is signalled explicitly — never silently swallowed (Risk R4).

This component depends on:
- Component B (privacy scrubber) — queries must be scrubbed before any HTTP call
"""

from typing import List, Dict, Any, Union
import logging

import requests

logger = logging.getLogger(__name__)

# Browser-like UA helps when the instance limiter is enabled; harmless when it is not.
_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (compatible; ShadowPO/1.0; +local web grounding client)"
    ),
}

# ---------------------------------------------------------------------------
# Sentinel for "grounding unavailable" — distinct from "no results found"
# ---------------------------------------------------------------------------

class GroundingUnavailable:
    """
    Sentinel object returned when SearXNG cannot be reached or returns an
    error.  Callers (Component F) must check for this type and tell the model
    it couldn't verify the web rather than answering confidently.

    Using a distinct object (not an empty list) makes the "unavailable" path
    type-checkable:  ``if isinstance(result, GroundingUnavailable): ...``
    """

    def __init__(self, reason: str):
        self.reason = reason

    def __repr__(self) -> str:
        return f"GroundingUnavailable(reason={self.reason!r})"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_web(
    query: str,
    searxng_url: str = "http://localhost:8080",
    num_results: int = 5,
    timeout: int = 10,
) -> Union[List[Dict[str, str]], GroundingUnavailable]:
    """
    Search the web via a local SearXNG instance and return structured results.

    The query is **always scrubbed before the HTTP request is made** so no
    PII or project codenames leave the machine.

    If SearXNG is unreachable, times out, or returns a non-200 response, a
    ``GroundingUnavailable`` sentinel is returned instead of an empty list.
    Callers must distinguish between:
    - ``list`` (possibly empty) → SearXNG responded; these are the results
    - ``GroundingUnavailable`` → SearXNG could not be reached; say so to user

    Args:
        query: Natural-language search query (will be scrubbed before sending)
        searxng_url: Base URL of the local SearXNG instance
        num_results: Maximum number of results to return (default: 5)
        timeout: HTTP request timeout in seconds (default: 10)

    Returns:
        List of ``{"title": str, "url": str, "snippet": str}`` dicts, ordered
        by SearXNG relevance — OR a ``GroundingUnavailable`` sentinel if the
        service could not be reached.

    Example:
        >>> from shadow_po import web_grounding
        >>> result = web_grounding.search_web("OAuth 2.0 best practices")
        >>> if isinstance(result, web_grounding.GroundingUnavailable):
        ...     print("Web grounding not available:", result.reason)
        ... else:
        ...     for r in result:
        ...         print(r["title"], r["url"])
    """
    from shadow_po import privacy

    if privacy._scrubber is None:
        raise RuntimeError(
            "Privacy scrubber not initialised. "
            "Call privacy.initialize() before calling search_web()."
        )

    # Scrub the query before it leaves the machine (Zero-Trust boundary)
    scrubbed_query = privacy.scrub(query)

    logger.info(
        f"Sending scrubbed query to SearXNG at {searxng_url}: "
        f"'{scrubbed_query[:80]}...'"
    )

    payload = {
        "q": scrubbed_query,
        "format": "json",
        "pageno": 1,
    }

    try:
        # POST is the documented JSON API method and bypasses Sec-Fetch bot checks
        # that block GET requests with format=json on limiter-enabled instances.
        response = requests.post(
            f"{searxng_url.rstrip('/')}/search",
            data=payload,
            timeout=timeout,
            headers=_DEFAULT_HEADERS,
        )
    except requests.exceptions.ConnectionError as exc:
        reason = f"Could not connect to SearXNG at {searxng_url}: {exc}"
        logger.warning(reason)
        return GroundingUnavailable(reason=reason)
    except requests.exceptions.Timeout as exc:
        reason = f"SearXNG request timed out after {timeout}s: {exc}"
        logger.warning(reason)
        return GroundingUnavailable(reason=reason)
    except requests.exceptions.RequestException as exc:
        reason = f"SearXNG request failed: {exc}"
        logger.warning(reason)
        return GroundingUnavailable(reason=reason)

    if response.status_code != 200:
        reason = (
            f"SearXNG returned HTTP {response.status_code} "
            f"for query '{scrubbed_query[:60]}'"
        )
        if response.status_code == 403:
            reason += (
                ". JSON format may be disabled — mount docker/searxng/settings.yml "
                "when starting SearXNG (see README §5)."
            )
        logger.warning(reason)
        return GroundingUnavailable(reason=reason)

    try:
        data: Dict[str, Any] = response.json()
    except ValueError as exc:
        reason = f"SearXNG returned invalid JSON: {exc}"
        logger.warning(reason)
        return GroundingUnavailable(reason=reason)

    raw_results: List[Dict[str, Any]] = data.get("results", [])

    structured: List[Dict[str, str]] = [
        {
            "title": str(r.get("title", "")),
            "url": str(r.get("url", "")),
            "snippet": str(r.get("content", r.get("snippet", ""))),
        }
        for r in raw_results[:num_results]
        if r.get("url")  # skip entries without a URL
    ]

    logger.info(
        f"SearXNG returned {len(structured)} results "
        f"for query '{scrubbed_query[:60]}'"
    )

    return structured
