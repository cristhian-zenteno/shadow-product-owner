"""
Tests for Web Grounding - Component E

All tests use mocked HTTP calls — no live SearXNG instance required.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from shadow_po import web_grounding
from shadow_po.web_grounding import GroundingUnavailable


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def privacy_scrubber():
    """Ensure the privacy scrubber is initialised for every test in this module."""
    from shadow_po import privacy
    original = privacy._scrubber
    privacy.initialize(custom_codenames=["ProjectTitan"])
    yield
    privacy._scrubber = original


def _make_searxng_response(results: list) -> MagicMock:
    """Helper: return a mock requests.Response with the given SearXNG result list."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": results}
    return mock_resp


SAMPLE_RESULTS = [
    {
        "title": "OAuth 2.0 Best Practices",
        "url": "https://example.com/oauth",
        "content": "OAuth 2.0 is an industry-standard protocol for authorisation.",
    },
    {
        "title": "Secure Token Storage",
        "url": "https://example.com/tokens",
        "content": "Tokens should be stored in HTTPOnly cookies.",
    },
    {
        "title": "API Security Guide",
        "url": "https://example.com/api-security",
        "content": "Always validate and sanitise API inputs.",
    },
]


# ---------------------------------------------------------------------------
# Task E-1: SearXNG client wrapper
# ---------------------------------------------------------------------------

def test_search_web_returns_structured_results():
    """
    Acceptance: search_web() returns a list of {title, url, snippet} dicts.
    """
    with patch("requests.post", return_value=_make_searxng_response(SAMPLE_RESULTS)):
        results = web_grounding.search_web(
            "OAuth 2.0 best practices",
            searxng_url="http://localhost:8080",
        )

    assert isinstance(results, list), "Should return a list when SearXNG responds"
    assert len(results) == 3

    for item in results:
        assert "title" in item, "Each result must have a 'title'"
        assert "url" in item, "Each result must have a 'url'"
        assert "snippet" in item, "Each result must have a 'snippet'"


def test_search_web_result_content():
    """
    Verify the title, url, and snippet values are mapped correctly from the
    SearXNG JSON response.
    """
    with patch("requests.post", return_value=_make_searxng_response(SAMPLE_RESULTS)):
        results = web_grounding.search_web("oauth", searxng_url="http://localhost:8080")

    assert results[0]["title"] == "OAuth 2.0 Best Practices"
    assert results[0]["url"] == "https://example.com/oauth"
    assert "authorisation" in results[0]["snippet"]


def test_search_web_respects_num_results():
    """search_web() should return at most num_results items."""
    with patch("requests.post", return_value=_make_searxng_response(SAMPLE_RESULTS)):
        results = web_grounding.search_web(
            "security",
            searxng_url="http://localhost:8080",
            num_results=2,
        )

    assert len(results) <= 2


def test_search_web_empty_results():
    """search_web() returns an empty list (not GroundingUnavailable) when
    SearXNG responds 200 but has no matching results."""
    with patch("requests.post", return_value=_make_searxng_response([])):
        results = web_grounding.search_web("xyzzy", searxng_url="http://localhost:8080")

    assert isinstance(results, list)
    assert results == []


def test_search_web_hits_correct_endpoint():
    """search_web() calls the /search endpoint on the configured SearXNG URL."""
    with patch("requests.post", return_value=_make_searxng_response([])) as mock_post:
        web_grounding.search_web("test query", searxng_url="http://localhost:8080")

    call_url = mock_post.call_args[0][0]
    assert call_url == "http://localhost:8080/search"


def test_search_web_passes_format_json():
    """search_web() always requests JSON format from SearXNG."""
    with patch("requests.post", return_value=_make_searxng_response([])) as mock_post:
        web_grounding.search_web("test query", searxng_url="http://localhost:8080")

    data = mock_post.call_args[1]["data"]
    assert data.get("format") == "json"


def test_search_web_requires_privacy_scrubber():
    """search_web() raises RuntimeError if the privacy scrubber is not initialised."""
    from shadow_po import privacy
    original = privacy._scrubber
    privacy._scrubber = None

    try:
        with pytest.raises(RuntimeError, match="Privacy scrubber not initialised"):
            web_grounding.search_web("any query")
    finally:
        privacy._scrubber = original


# ---------------------------------------------------------------------------
# Task E-2: Scrub queries before they leave the machine
# ---------------------------------------------------------------------------

def test_query_is_scrubbed_before_http_call():
    """
    Acceptance: a query containing a fake secret must never reach the
    outbound HTTP call unscrubbed.

    We capture the actual form data passed to requests.post and confirm
    the raw secret is not in it.
    """
    fake_key = "sk-abcdef1234567890abcdef1234567890abcdef12"
    raw_query = f"What is the best practice for key {fake_key}?"

    captured_data = {}

    def capturing_post(url, data=None, **kwargs):
        captured_data.update(data or {})
        return _make_searxng_response([])

    with patch("requests.post", side_effect=capturing_post):
        web_grounding.search_web(raw_query, searxng_url="http://localhost:8080")

    sent_query = captured_data.get("q", "")
    assert fake_key not in sent_query, (
        f"Raw API key must not appear in the outbound query. Got: {sent_query}"
    )
    assert "[API_KEY]" in sent_query, (
        "Scrubbed [API_KEY] placeholder must appear in the outbound query"
    )


def test_codename_is_scrubbed_before_http_call():
    """Custom codenames configured in settings must be redacted before sending."""
    raw_query = "Tell me about ProjectTitan payment integration"

    captured_data = {}

    def capturing_post(url, data=None, **kwargs):
        captured_data.update(data or {})
        return _make_searxng_response([])

    with patch("requests.post", side_effect=capturing_post):
        web_grounding.search_web(raw_query, searxng_url="http://localhost:8080")

    sent_query = captured_data.get("q", "")
    assert "ProjectTitan" not in sent_query, (
        "Codename must be redacted before the query leaves the machine"
    )
    assert "[CODENAME]" in sent_query


def test_scrubbed_query_reaches_searxng():
    """Even after scrubbing, the query's non-sensitive content reaches SearXNG."""
    raw_query = "best practices for authentication systems"

    captured_data = {}

    def capturing_post(url, data=None, **kwargs):
        captured_data.update(data or {})
        return _make_searxng_response([])

    with patch("requests.post", side_effect=capturing_post):
        web_grounding.search_web(raw_query, searxng_url="http://localhost:8080")

    sent_query = captured_data.get("q", "")
    assert "authentication" in sent_query, (
        "Non-sensitive query content must still reach SearXNG after scrubbing"
    )


# ---------------------------------------------------------------------------
# Task E-3: Graceful "no grounding available" path (Risk R4)
# ---------------------------------------------------------------------------

def test_searxng_unreachable_returns_unavailable():
    """
    Acceptance: when SearXNG is unreachable, search_web() returns a
    GroundingUnavailable sentinel — not an empty list, not an exception.
    """
    import requests as req_lib

    with patch("requests.post", side_effect=req_lib.exceptions.ConnectionError("refused")):
        result = web_grounding.search_web("test query", searxng_url="http://localhost:8080")

    assert isinstance(result, GroundingUnavailable), (
        "Connection error must return GroundingUnavailable, not raise or return []"
    )
    assert result.reason, "GroundingUnavailable must include a reason string"


def test_searxng_timeout_returns_unavailable():
    """Timeout produces GroundingUnavailable, not an exception."""
    import requests as req_lib

    with patch("requests.post", side_effect=req_lib.exceptions.Timeout("timed out")):
        result = web_grounding.search_web(
            "test query",
            searxng_url="http://localhost:8080",
            timeout=5,
        )

    assert isinstance(result, GroundingUnavailable)
    assert "timed out" in result.reason.lower() or "timeout" in result.reason.lower()


def test_searxng_http_error_returns_unavailable():
    """Non-200 HTTP response returns GroundingUnavailable."""
    mock_resp = MagicMock()
    mock_resp.status_code = 503

    with patch("requests.post", return_value=mock_resp):
        result = web_grounding.search_web("test query", searxng_url="http://localhost:8080")

    assert isinstance(result, GroundingUnavailable)
    assert "503" in result.reason


def test_searxng_invalid_json_returns_unavailable():
    """Invalid JSON response body returns GroundingUnavailable."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("No JSON object")

    with patch("requests.post", return_value=mock_resp):
        result = web_grounding.search_web("test query", searxng_url="http://localhost:8080")

    assert isinstance(result, GroundingUnavailable)


def test_unavailable_is_distinct_from_empty_list():
    """
    GroundingUnavailable must be distinguishable from an empty results list
    so callers can give different responses in each case.
    """
    import requests as req_lib

    # Simulate unreachable
    with patch("requests.post", side_effect=req_lib.exceptions.ConnectionError()):
        unavailable = web_grounding.search_web("q", searxng_url="http://localhost:8080")

    # Simulate reachable but no results
    with patch("requests.post", return_value=_make_searxng_response([])):
        empty = web_grounding.search_web("q", searxng_url="http://localhost:8080")

    assert isinstance(unavailable, GroundingUnavailable)
    assert isinstance(empty, list)
    assert unavailable != empty  # They must be distinguishable
