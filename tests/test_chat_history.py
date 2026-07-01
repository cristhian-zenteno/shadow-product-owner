"""
Tests for Chat History - Component G

Verifies: append-only storage, list/load round-trip, and scrubbing integration.
"""

import pytest
from pathlib import Path
from shadow_po import chat_history


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def workspace(tmp_path):
    """Create a fresh feature workspace for each test."""
    from shadow_po import workspace as ws
    return ws.create_workspace("chat-test", workspaces_root=tmp_path)


@pytest.fixture(autouse=True)
def privacy_scrubber():
    """Initialise privacy scrubber for the scrubbing integration test."""
    from shadow_po import privacy
    original = privacy._scrubber
    privacy.initialize(custom_codenames=[])
    yield
    privacy._scrubber = original


# ---------------------------------------------------------------------------
# Task G-1: Append turns to conversation file
# ---------------------------------------------------------------------------

def test_save_turn_creates_file_on_first_call(workspace):
    """save_turn() creates the conversation file on the first call."""
    path = chat_history.save_turn(workspace, "conv-001", "user", "Hello, what is the feature?")

    assert path.exists(), "Conversation file should be created"
    assert path.name == "conv-001.md"
    assert path.parent == workspace / "progress" / "chat"


def test_save_turn_appends_not_overwrites(workspace):
    """
    Acceptance: saving 3 turns results in all 3 being present in order —
    the file is never truncated or rewritten between calls.
    """
    chat_history.save_turn(workspace, "conv-002", "user", "First message")
    chat_history.save_turn(workspace, "conv-002", "assistant", "First reply")
    chat_history.save_turn(workspace, "conv-002", "user", "Second message")

    content = (workspace / "progress" / "chat" / "conv-002.md").read_text(encoding="utf-8")

    assert "First message" in content
    assert "First reply" in content
    assert "Second message" in content

    # Verify order: first message appears before second message
    assert content.index("First message") < content.index("Second message")


def test_save_turn_all_three_in_order(workspace):
    """All turns are present and in insertion order."""
    turns = [
        ("user", "Turn 1"),
        ("assistant", "Turn 2"),
        ("user", "Turn 3"),
    ]
    for role, content in turns:
        chat_history.save_turn(workspace, "conv-order", role, content)

    messages = chat_history.load_conversation(workspace, "conv-order")

    assert len(messages) == 3
    for i, (role, content) in enumerate(turns):
        assert messages[i]["role"] == role
        assert messages[i]["content"] == content


def test_save_turn_invalid_role(workspace):
    """save_turn() raises ValueError for an invalid role."""
    with pytest.raises(ValueError, match="Invalid role"):
        chat_history.save_turn(workspace, "conv-bad", "system", "content")


def test_save_turn_missing_workspace(tmp_path):
    """save_turn() raises FileNotFoundError for a nonexistent workspace."""
    with pytest.raises(FileNotFoundError, match="Workspace not found"):
        chat_history.save_turn(tmp_path / "ghost", "conv-x", "user", "hi")


# ---------------------------------------------------------------------------
# Task G-2: List and load conversations
# ---------------------------------------------------------------------------

def test_list_conversations_empty(workspace):
    """list_conversations() returns [] when no conversations exist yet."""
    result = chat_history.list_conversations(workspace)
    assert result == []


def test_list_conversations_returns_ids(workspace):
    """list_conversations() returns all conversation IDs present."""
    chat_history.save_turn(workspace, "alpha", "user", "msg")
    chat_history.save_turn(workspace, "beta", "user", "msg")
    chat_history.save_turn(workspace, "gamma", "user", "msg")

    ids = chat_history.list_conversations(workspace)

    assert set(ids) == {"alpha", "beta", "gamma"}


def test_load_conversation_round_trip(workspace):
    """
    Acceptance: a multi-turn conversation round-trips losslessly through
    save_turn() → list_conversations() → load_conversation().
    """
    turns = [
        ("user", "What is the payment flow?"),
        ("assistant", "The payment flow uses Stripe for processing."),
        ("user", "What happens on failure?"),
        ("assistant", "On failure the user is redirected to an error page."),
    ]

    for role, content in turns:
        chat_history.save_turn(workspace, "roundtrip", role, content)

    # Verify it shows up in list
    ids = chat_history.list_conversations(workspace)
    assert "roundtrip" in ids

    # Load and verify content
    messages = chat_history.load_conversation(workspace, "roundtrip")
    assert len(messages) == 4

    for i, (role, content) in enumerate(turns):
        assert messages[i]["role"] == role
        assert messages[i]["content"] == content


def test_load_conversation_not_found(workspace):
    """load_conversation() raises FileNotFoundError for a missing conversation."""
    with pytest.raises(FileNotFoundError, match="not found"):
        chat_history.load_conversation(workspace, "nonexistent-conv")


def test_list_conversations_missing_workspace(tmp_path):
    """list_conversations() raises FileNotFoundError for a nonexistent workspace."""
    with pytest.raises(FileNotFoundError):
        chat_history.list_conversations(tmp_path / "ghost")


def test_multiple_conversations_independent(workspace):
    """Two conversations in the same workspace are independent files."""
    chat_history.save_turn(workspace, "conv-a", "user", "Question about auth")
    chat_history.save_turn(workspace, "conv-b", "user", "Question about payments")

    msgs_a = chat_history.load_conversation(workspace, "conv-a")
    msgs_b = chat_history.load_conversation(workspace, "conv-b")

    assert len(msgs_a) == 1
    assert len(msgs_b) == 1
    assert "auth" in msgs_a[0]["content"]
    assert "payments" in msgs_b[0]["content"]


# ---------------------------------------------------------------------------
# Task G-3: Scrubbing integration — saved chat must not contain raw PII
# ---------------------------------------------------------------------------

def test_saved_chat_is_scrubbed(workspace, tmp_path):
    """
    Acceptance: text saved via save_turn() that came from answer_question()
    must not contain raw PII.

    We simulate the pipeline path: scrub the content before saving (as
    answer_question does), then verify the saved file is clean.

    This test verifies the integration contract at the G boundary, not by
    adding a second scrub inside save_turn() but by confirming the caller
    (pipeline) always passes scrubbed text in.
    """
    from shadow_po import privacy

    fake_email = "dev@example.com"
    raw_content = f"The developer contacted {fake_email} for clarification."

    # Simulate what pipeline.answer_question does: scrub before saving
    scrubbed_content = privacy.scrub(raw_content)

    chat_history.save_turn(workspace, "scrub-test", "assistant", scrubbed_content)

    saved = (workspace / "progress" / "chat" / "scrub-test.md").read_text(encoding="utf-8")

    assert fake_email not in saved, (
        "Raw email must not appear in the saved conversation file"
    )
    assert "[EMAIL]" in saved, (
        "Scrubbed [EMAIL] placeholder must appear in the saved file"
    )


def test_saved_content_survives_reload(workspace):
    """
    Content saved via save_turn() is identical after a load_conversation()
    round-trip — no data is lost or mangled during storage and retrieval.
    """
    long_content = (
        "The checkout feature requires:\n\n"
        "1. A saved payment method for the user\n"
        "2. A confirmed shipping address\n"
        "3. Debounce on double-clicks within 3 seconds\n\n"
        "Edge case: expired card → redirect to regular checkout."
    )

    chat_history.save_turn(workspace, "roundtrip-content", "assistant", long_content)
    messages = chat_history.load_conversation(workspace, "roundtrip-content")

    assert len(messages) == 1
    assert messages[0]["content"] == long_content
