"""
Workspace management for Shadow PO.

Handles per-feature folder structure creation and management.
Each feature gets its own isolated workspace under workspaces/<feature-name>/
with the structure defined in SPECIFY.md §1.
"""

from pathlib import Path
from typing import Union, List


def create_workspace(feature_name: str, workspaces_root: Union[str, Path] = "workspaces") -> Path:
    """
    Create a per-feature workspace with the required folder structure.
    
    Structure created:
    workspaces/<feature-name>/
        ├── input/
        │   ├── documents/
        │   └── meetings/
        ├── progress/
        │   └── chat/
        └── output/
    
    Args:
        feature_name: Name of the feature (e.g., "1-click-checkout")
        workspaces_root: Root directory for all workspaces (default: "workspaces")
    
    Returns:
        Path: The created workspace directory path
        
    Raises:
        ValueError: If feature_name is empty or contains invalid characters
    """
    if not feature_name or not feature_name.strip():
        raise ValueError("feature_name cannot be empty")
    
    # Convert to Path objects for consistent handling
    workspaces_root = Path(workspaces_root)
    workspace_path = workspaces_root / feature_name.strip()
    
    # Define the required subdirectory structure
    subdirs = [
        workspace_path / "input" / "documents",
        workspace_path / "input" / "meetings",
        workspace_path / "progress" / "chat",
        workspace_path / "output",
    ]
    
    # Create all directories (exist_ok=True means calling again won't error or wipe data)
    for subdir in subdirs:
        subdir.mkdir(parents=True, exist_ok=True)
    
    return workspace_path


def list_workspaces(workspaces_root: Union[str, Path] = "workspaces") -> List[str]:
    """
    List all valid feature workspaces under the workspaces root directory.
    
    A valid workspace must have the expected 4-folder structure:
    - input/documents/
    - input/meetings/
    - progress/chat/
    - output/
    
    Args:
        workspaces_root: Root directory for all workspaces (default: "workspaces")
    
    Returns:
        List[str]: List of feature names (folder names) that have valid workspace structure
    """
    workspaces_root = Path(workspaces_root)
    
    # If the workspaces root doesn't exist, return empty list
    if not workspaces_root.exists():
        return []
    
    valid_workspaces = []
    
    # Required subdirectories for a valid workspace
    required_structure = [
        "input/documents",
        "input/meetings",
        "progress/chat",
        "output",
    ]
    
    # Iterate through all items in workspaces_root
    for item in workspaces_root.iterdir():
        # Skip if not a directory
        if not item.is_dir():
            continue
        
        # Check if this directory has all required subdirectories
        is_valid = all(
            (item / required_path).exists() and (item / required_path).is_dir()
            for required_path in required_structure
        )
        
        if is_valid:
            valid_workspaces.append(item.name)
    
    return sorted(valid_workspaces)  # Sort for consistent ordering
