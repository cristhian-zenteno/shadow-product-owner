"""
Tests for settings configuration loader.

Validates that settings.yaml is correctly loaded and validated,
and that missing or invalid configurations raise clear errors.
"""

import pytest
from pathlib import Path

from shadow_po.config import load_settings, Settings


def test_load_valid_settings():
    """Test loading a valid settings.yaml fixture."""
    settings = load_settings("tests/fixtures/settings_valid.yaml")
    
    # Verify all required fields are populated
    assert settings.workspaces_root == "test_workspaces/"
    assert settings.model.name == "nvidia/nemotron-3-ultra-550b-a55b"
    assert settings.model.temperature == 0.2
    assert settings.searxng_url == "http://localhost:8080"
    assert settings.whisper.model_size == "base"
    assert settings.whisper.device == "cpu"
    assert settings.whisper.compute_type == "int8"
    assert settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.privacy is not None
    assert settings.privacy.codenames == ["Project Titan", "Project Alpha"]
    
    # Verify convenience accessors work
    assert settings.model_name == "nvidia/nemotron-3-ultra-550b-a55b"
    assert settings.whisper_model_size == "base"


def test_load_missing_required_field():
    """Test that missing required fields raise clear errors."""
    with pytest.raises(ValueError) as exc_info:
        load_settings("tests/fixtures/settings_missing_field.yaml")
    
    # Verify error message is clear about what went wrong
    error_msg = str(exc_info.value)
    assert "Invalid settings configuration" in error_msg
    # Pydantic validation will mention the missing field
    assert "model" in error_msg.lower() or "field required" in error_msg.lower()


def test_load_nonexistent_file():
    """Test that missing settings file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError) as exc_info:
        load_settings("nonexistent_settings.yaml")
    
    # Verify error message is helpful
    error_msg = str(exc_info.value)
    assert "Settings file not found" in error_msg
    assert "nonexistent_settings.yaml" in error_msg
    assert "settings.yaml.example" in error_msg


def test_empty_workspaces_root():
    """Test that empty workspaces_root is rejected."""
    # Create a minimal invalid settings dict
    invalid_settings = {
        "workspaces_root": "",  # Empty string
        "model": {"name": "test-model", "temperature": 0.2},
        "searxng_url": "http://localhost:8080",
        "whisper": {"model_size": "base"},
        "embedding_model": "test-model"
    }
    
    with pytest.raises(ValueError) as exc_info:
        Settings(**invalid_settings)
    
    error_msg = str(exc_info.value)
    assert "workspaces_root" in error_msg.lower()


def test_empty_searxng_url():
    """Test that empty searxng_url is rejected."""
    invalid_settings = {
        "workspaces_root": "workspaces/",
        "model": {"name": "test-model", "temperature": 0.2},
        "searxng_url": "",  # Empty string
        "whisper": {"model_size": "base"},
        "embedding_model": "test-model"
    }
    
    with pytest.raises(ValueError) as exc_info:
        Settings(**invalid_settings)
    
    error_msg = str(exc_info.value)
    assert "searxng_url" in error_msg.lower()


def test_empty_embedding_model():
    """Test that empty embedding_model is rejected."""
    invalid_settings = {
        "workspaces_root": "workspaces/",
        "model": {"name": "test-model", "temperature": 0.2},
        "searxng_url": "http://localhost:8080",
        "whisper": {"model_size": "base"},
        "embedding_model": ""  # Empty string
    }
    
    with pytest.raises(ValueError) as exc_info:
        Settings(**invalid_settings)
    
    error_msg = str(exc_info.value)
    assert "embedding_model" in error_msg.lower()


def test_privacy_optional():
    """Test that privacy config is optional and defaults appropriately."""
    minimal_settings = {
        "workspaces_root": "workspaces/",
        "model": {"name": "test-model", "temperature": 0.2},
        "searxng_url": "http://localhost:8080",
        "whisper": {"model_size": "base"},
        "embedding_model": "test-model"
        # privacy not provided
    }
    
    settings = Settings(**minimal_settings)
    assert settings.privacy is None or settings.privacy.codenames == []


def test_default_whisper_values():
    """Test that whisper config has sensible defaults."""
    minimal_settings = {
        "workspaces_root": "workspaces/",
        "model": {"name": "test-model", "temperature": 0.2},
        "searxng_url": "http://localhost:8080",
        "whisper": {"model_size": "base"},  # Only required field
        "embedding_model": "test-model"
    }
    
    settings = Settings(**minimal_settings)
    assert settings.whisper.device == "cpu"  # Default
    assert settings.whisper.compute_type == "int8"  # Default


def test_default_model_temperature():
    """Test that model temperature has a default."""
    minimal_settings = {
        "workspaces_root": "workspaces/",
        "model": {"name": "test-model"},  # temperature not provided
        "searxng_url": "http://localhost:8080",
        "whisper": {"model_size": "base"},
        "embedding_model": "test-model"
    }
    
    settings = Settings(**minimal_settings)
    assert settings.model.temperature == 0.2  # Default


def test_default_model_timeouts():
    """Test that LLM timeout settings have sensible defaults."""
    minimal_settings = {
        "workspaces_root": "workspaces/",
        "model": {"name": "test-model"},
        "searxng_url": "http://localhost:8080",
        "whisper": {"model_size": "base"},
        "embedding_model": "test-model",
    }

    settings = Settings(**minimal_settings)
    assert settings.model.timeout == 60
    assert settings.model.generate_docs_timeout == 300
    assert settings.model.generate_docs_max_completion_tokens == 16384
