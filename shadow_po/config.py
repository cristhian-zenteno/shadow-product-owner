"""
Application configuration loader for Shadow PO.

Loads and validates settings.yaml using Pydantic for type safety.
All required fields must be present, and missing configuration raises clear errors.
"""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class WhisperConfig(BaseModel):
    """Configuration for faster-whisper transcription."""
    model_size: str = Field(..., description="Whisper model size (base, small, medium, large-v3)")
    device: str = Field(default="cpu", description="Device to run on (cpu or cuda)")
    compute_type: str = Field(default="int8", description="Compute type for inference")


class ModelConfig(BaseModel):
    """Configuration for LLM model."""
    name: str = Field(..., description="Model identifier (e.g., nvidia/nemotron-3-ultra-550b-a55b)")
    temperature: float = Field(default=0.2, description="Model temperature for generation")
    timeout: float = Field(
        default=60,
        ge=0,
        description="HTTP read timeout in seconds for chat and other LLM calls",
    )
    generate_docs_timeout: float = Field(
        default=300,
        ge=0,
        description="HTTP read timeout in seconds for Generate docs (large structured output)",
    )
    generate_docs_max_completion_tokens: int = Field(
        default=16384,
        gt=0,
        description="Max tokens for Generate docs structured output (four markdown files)",
    )


class PrivacyConfig(BaseModel):
    """Configuration for privacy scrubbing."""
    codenames: list[str] = Field(default_factory=list, description="Custom codenames to redact")


class Settings(BaseModel):
    """Application settings loaded from settings.yaml."""
    
    workspaces_root: str = Field(..., description="Root directory for feature workspaces")
    model: ModelConfig = Field(..., description="LLM model configuration")
    searxng_url: str = Field(..., description="URL for local SearXNG instance")
    whisper: WhisperConfig = Field(..., description="Whisper transcription configuration")
    embedding_model: str = Field(..., description="Sentence-transformers model for embeddings")
    privacy: Optional[PrivacyConfig] = Field(default=None, description="Privacy configuration")
    
    @field_validator('workspaces_root')
    @classmethod
    def validate_workspaces_root(cls, v: str) -> str:
        """Ensure workspaces_root is not empty."""
        if not v or not v.strip():
            raise ValueError("workspaces_root cannot be empty")
        return v.strip()
    
    @field_validator('searxng_url')
    @classmethod
    def validate_searxng_url(cls, v: str) -> str:
        """Ensure searxng_url is not empty."""
        if not v or not v.strip():
            raise ValueError("searxng_url cannot be empty")
        return v.strip()
    
    @field_validator('embedding_model')
    @classmethod
    def validate_embedding_model(cls, v: str) -> str:
        """Ensure embedding_model is not empty."""
        if not v or not v.strip():
            raise ValueError("embedding_model cannot be empty")
        return v.strip()
    
    @property
    def model_name(self) -> str:
        """Convenience accessor for model.name (maintains backward compatibility)."""
        return self.model.name
    
    @property
    def whisper_model_size(self) -> str:
        """Convenience accessor for whisper.model_size (maintains backward compatibility)."""
        return self.whisper.model_size


def load_settings(settings_path: str = "settings.yaml") -> Settings:
    """
    Load and validate application settings from YAML file.
    
    Args:
        settings_path: Path to settings.yaml file (default: "settings.yaml")
    
    Returns:
        Settings: Validated settings object
    
    Raises:
        FileNotFoundError: If settings.yaml does not exist
        ValueError: If required fields are missing or invalid
        yaml.YAMLError: If YAML parsing fails
    """
    settings_file = Path(settings_path)
    
    if not settings_file.exists():
        raise FileNotFoundError(
            f"Settings file not found: {settings_path}\n"
            f"Please create a settings.yaml file with required configuration. "
            f"See settings.yaml.example for template."
        )
    
    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse settings.yaml: {e}")
    
    if data is None:
        raise ValueError("settings.yaml is empty")
    
    try:
        return Settings(**data)
    except Exception as e:
        raise ValueError(
            f"Invalid settings configuration: {e}\n"
            f"Please check that all required fields are present and correctly formatted."
        )
