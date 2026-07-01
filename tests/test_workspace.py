"""
Tests for workspace management (Component A).

Verifies per-feature folder structure creation and idempotent behavior.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from shadow_po.workspace import create_workspace


@pytest.fixture
def temp_workspaces_root():
    """Create a temporary directory for workspaces during tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    # Cleanup after test
    shutil.rmtree(temp_dir)


def test_create_workspace_creates_all_folders(temp_workspaces_root):
    """
    Test that create_workspace creates all required subdirectories.
    
    Acceptance criteria: Calling create_workspace("1-click-checkout") creates
    workspaces/1-click-checkout/{input/documents, input/meetings, progress/chat, output}
    """
    feature_name = "1-click-checkout"
    workspace_path = create_workspace(feature_name, temp_workspaces_root)
    
    # Assert the workspace directory exists
    assert workspace_path.exists()
    assert workspace_path.is_dir()
    
    # Assert all 4 required subdirectories exist
    assert (workspace_path / "input" / "documents").exists()
    assert (workspace_path / "input" / "meetings").exists()
    assert (workspace_path / "progress" / "chat").exists()
    assert (workspace_path / "output").exists()
    
    # Verify they are directories
    assert (workspace_path / "input" / "documents").is_dir()
    assert (workspace_path / "input" / "meetings").is_dir()
    assert (workspace_path / "progress" / "chat").is_dir()
    assert (workspace_path / "output").is_dir()


def test_create_workspace_idempotent_no_data_loss(temp_workspaces_root):
    """
    Test that calling create_workspace again on an existing workspace doesn't error or wipe data.
    
    Acceptance criteria: Calling it again on an existing workspace doesn't error or wipe anything.
    """
    feature_name = "test-feature"
    
    # First creation
    workspace_path = create_workspace(feature_name, temp_workspaces_root)
    
    # Create a test file to verify data isn't wiped
    test_file = workspace_path / "input" / "documents" / "test.md"
    test_content = "This is important data that should not be deleted"
    test_file.write_text(test_content)
    
    # Second creation (should be idempotent)
    workspace_path_second = create_workspace(feature_name, temp_workspaces_root)
    
    # Assert no error occurred and path is the same
    assert workspace_path == workspace_path_second
    
    # Assert the test file still exists with original content
    assert test_file.exists()
    assert test_file.read_text() == test_content
    
    # Assert all directories still exist
    assert (workspace_path / "input" / "documents").exists()
    assert (workspace_path / "input" / "meetings").exists()
    assert (workspace_path / "progress" / "chat").exists()
    assert (workspace_path / "output").exists()


def test_create_workspace_empty_name_raises_error(temp_workspaces_root):
    """Test that empty feature names raise a ValueError."""
    with pytest.raises(ValueError, match="feature_name cannot be empty"):
        create_workspace("", temp_workspaces_root)
    
    with pytest.raises(ValueError, match="feature_name cannot be empty"):
        create_workspace("   ", temp_workspaces_root)


def test_create_workspace_multiple_features_isolated(temp_workspaces_root):
    """Test that multiple feature workspaces remain isolated from each other."""
    feature1 = "feature-one"
    feature2 = "feature-two"
    
    workspace1 = create_workspace(feature1, temp_workspaces_root)
    workspace2 = create_workspace(feature2, temp_workspaces_root)
    
    # Assert both exist and are different
    assert workspace1.exists()
    assert workspace2.exists()
    assert workspace1 != workspace2
    
    # Create a file in feature1
    test_file1 = workspace1 / "input" / "documents" / "spec.md"
    test_file1.write_text("Feature 1 spec")
    
    # Assert it doesn't appear in feature2
    test_file2 = workspace2 / "input" / "documents" / "spec.md"
    assert test_file1.exists()
    assert not test_file2.exists()


def test_list_workspaces(temp_workspaces_root):
    """
    Test that list_workspaces returns only valid workspaces.
    
    Acceptance criteria: list_workspaces() returns every subfolder that has 
    the expected 4-folder shape; ignores anything that doesn't (e.g. a stray file).
    """
    from shadow_po.workspace import list_workspaces
    
    # Create 2 valid workspaces
    create_workspace("valid-workspace-1", temp_workspaces_root)
    create_workspace("valid-workspace-2", temp_workspaces_root)
    
    # Create a stray file in workspaces root
    stray_file = temp_workspaces_root / "stray_file.txt"
    stray_file.write_text("This should be ignored")
    
    # Create an incomplete workspace (missing some required folders)
    incomplete_workspace = temp_workspaces_root / "incomplete-workspace"
    incomplete_workspace.mkdir()
    (incomplete_workspace / "input").mkdir()
    (incomplete_workspace / "input" / "documents").mkdir()
    # Missing other required folders - this should be ignored
    
    # List workspaces
    workspaces = list_workspaces(temp_workspaces_root)
    
    # Assert only the 2 valid workspaces are listed
    assert len(workspaces) == 2
    assert "valid-workspace-1" in workspaces
    assert "valid-workspace-2" in workspaces
    
    # Assert stray file and incomplete workspace are not listed
    assert "stray_file.txt" not in workspaces
    assert "incomplete-workspace" not in workspaces
    
    # Assert the list is sorted
    assert workspaces == sorted(workspaces)


def test_list_workspaces_nonexistent_root():
    """Test that list_workspaces returns empty list when workspaces_root doesn't exist."""
    from shadow_po.workspace import list_workspaces
    
    nonexistent_path = Path("nonexistent_workspaces_directory_xyz")
    workspaces = list_workspaces(nonexistent_path)
    
    assert workspaces == []
