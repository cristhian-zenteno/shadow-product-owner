"""
Chat History - Component G

Persists conversation turns to per-feature workspace files.
Each conversation is a Markdown file under progress/chat/<conversation_id>.md.
Turns are appended, never rewritten — the file grows as the conversation continues.

Per SPECIFY.md §6:
- Each conversation is its own file, identified by conversation_id
- New turns are appended, not overwritten
- A new conversation only starts explicitly; resuming continues the same file
- Nothing unscrubbed is ever written (caller responsibility — verified in tests)
"""

from pathlib import Path
from typing import Union, List, Dict
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ChatTurn:
    """A single message in a conversation."""

    def __init__(self, role: str, content: str, timestamp: str = ""):
        self.role = role          # "user" | "assistant"
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_markdown(self) -> str:
        """Render this turn as a Markdown block for storage."""
        role_label = "**User**" if self.role == "user" else "**Assistant**"
        return (
            f"### {role_label} — {self.timestamp}\n\n"
            f"{self.content}\n\n"
            f"---\n"
        )

    @classmethod
    def from_dict(cls, d: Dict) -> "ChatTurn":
        return cls(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            timestamp=d.get("timestamp", ""),
        )


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def _conversation_path(workspace_path: Union[str, Path], conversation_id: str) -> Path:
    """Return the Path for a conversation file, without creating it."""
    return Path(workspace_path) / "progress" / "chat" / f"{conversation_id}.md"


def save_turn(
    workspace_path: Union[str, Path],
    conversation_id: str,
    role: str,
    content: str,
) -> Path:
    """
    Append one message turn to a conversation file.

    Creates the file on the first turn; appends on all subsequent turns.
    The file is never rewritten — only appended to.

    Per SPECIFY.md §6: text written here must already be scrubbed by the
    caller (pipeline.answer_question scrubs input; this function does not
    add a second scrub pass so callers remain in control of the boundary).

    Args:
        workspace_path:   Path to the feature workspace root
        conversation_id:  Identifier for this conversation (e.g. a UUID or slug)
        role:             "user" or "assistant"
        content:          Text of the message (must already be scrubbed)

    Returns:
        Path to the conversation file

    Raises:
        FileNotFoundError: If the workspace or its progress/chat/ folder doesn't exist
        ValueError: If role is not "user" or "assistant"
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        raise FileNotFoundError(
            f"Workspace not found: {workspace_path}\n"
            "Create it with workspace.create_workspace() first."
        )

    if role not in ("user", "assistant"):
        raise ValueError(
            f"Invalid role '{role}'. Must be 'user' or 'assistant'."
        )

    chat_dir = workspace / "progress" / "chat"

    if not chat_dir.exists():
        raise FileNotFoundError(
            f"progress/chat/ directory not found in workspace: {workspace_path}\n"
            "Ensure the workspace was created with workspace.create_workspace()."
        )

    conv_file = chat_dir / f"{conversation_id}.md"
    turn = ChatTurn(role=role, content=content)

    # Write header on first turn, otherwise just append
    if not conv_file.exists():
        header = (
            f"# Conversation: {conversation_id}\n\n"
            f"**Workspace:** {workspace.name}  \n"
            f"**Started:** {turn.timestamp}\n\n"
            f"---\n\n"
        )
        conv_file.write_text(header + turn.to_markdown(), encoding="utf-8")
        logger.info(f"Created conversation file: {conv_file}")
    else:
        with conv_file.open("a", encoding="utf-8") as f:
            f.write(turn.to_markdown())
        logger.info(f"Appended turn to conversation: {conv_file}")

    return conv_file


def list_conversations(workspace_path: Union[str, Path]) -> List[str]:
    """
    Return all saved conversation IDs for a feature workspace.

    Scans progress/chat/ for .md files and returns their stems (filenames
    without the .md extension) as conversation IDs.

    Args:
        workspace_path: Path to the feature workspace root

    Returns:
        Sorted list of conversation ID strings (may be empty)

    Raises:
        FileNotFoundError: If the workspace does not exist
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace_path}")

    chat_dir = workspace / "progress" / "chat"

    if not chat_dir.exists():
        return []

    ids = sorted(
        f.stem for f in chat_dir.iterdir()
        if f.is_file() and f.suffix == ".md"
    )

    logger.info(f"Found {len(ids)} conversations in workspace '{workspace.name}'")

    return ids


def load_conversation(
    workspace_path: Union[str, Path],
    conversation_id: str,
) -> List[Dict]:
    """
    Load the full message history for a conversation.

    Parses the stored Markdown file back into an ordered list of message dicts,
    each with keys: role, content, timestamp.

    Args:
        workspace_path:  Path to the feature workspace root
        conversation_id: ID of the conversation to load

    Returns:
        List of {"role": str, "content": str, "timestamp": str} dicts,
        in chronological order (oldest first)

    Raises:
        FileNotFoundError: If the workspace or conversation file doesn't exist
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace_path}")

    conv_file = _conversation_path(workspace, conversation_id)

    if not conv_file.exists():
        raise FileNotFoundError(
            f"Conversation '{conversation_id}' not found in workspace "
            f"'{workspace.name}'.\n"
            f"Expected file: {conv_file}"
        )

    raw = conv_file.read_text(encoding="utf-8")
    messages = _parse_conversation(raw)

    logger.info(
        f"Loaded conversation '{conversation_id}': "
        f"{len(messages)} turns"
    )

    return messages


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

def _parse_conversation(raw: str) -> List[Dict]:
    """
    Parse a stored Markdown conversation back into a list of message dicts.

    Format written by save_turn():
        ### **User** — <timestamp>

        <content>

        ---
        ### **Assistant** — <timestamp>

        <content>

        ---

    Returns list of {"role", "content", "timestamp"} dicts.
    """
    messages: List[Dict] = []
    current_role: str = ""
    current_timestamp: str = ""
    current_lines: List[str] = []

    def _flush():
        if current_role and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                messages.append({
                    "role": current_role,
                    "content": content,
                    "timestamp": current_timestamp,
                })

    for line in raw.splitlines():
        # Detect a turn header: ### **User** — timestamp
        if line.startswith("### **User**") or line.startswith("### **Assistant**"):
            _flush()
            current_lines = []
            current_role = "user" if "**User**" in line else "assistant"
            # Extract timestamp after " — "
            parts = line.split(" — ", 1)
            current_timestamp = parts[1].strip() if len(parts) > 1 else ""
        elif line.strip() == "---":
            # Separator between turns — skip
            continue
        elif current_role:
            current_lines.append(line)

    _flush()

    return messages
