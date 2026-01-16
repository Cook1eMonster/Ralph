"""Global configuration storage for Ralph.

Stores user preferences like AI configuration in ~/.ralph/config.json
"""

import json
from pathlib import Path
from typing import Optional

from .models import AIConfig


def get_config_dir() -> Path:
    """Get the Ralph config directory."""
    config_dir = Path.home() / ".ralph"
    config_dir.mkdir(exist_ok=True)
    return config_dir


def get_global_config() -> AIConfig:
    """Load global AI configuration."""
    config_file = get_config_dir() / "config.json"
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            return AIConfig(**data)
        except (json.JSONDecodeError, ValueError):
            pass
    return AIConfig()  # defaults


def save_global_config(config: AIConfig) -> None:
    """Save global AI configuration."""
    config_file = get_config_dir() / "config.json"
    config_file.write_text(
        json.dumps(config.model_dump(), indent=2),
        encoding="utf-8",
    )


def get_last_project_id() -> Optional[str]:
    """Get the last used project ID."""
    config_file = get_config_dir() / "last_project.txt"
    if config_file.exists():
        return config_file.read_text(encoding="utf-8").strip() or None
    return None


def save_last_project_id(project_id: str) -> None:
    """Save the last used project ID."""
    config_file = get_config_dir() / "last_project.txt"
    config_file.write_text(project_id, encoding="utf-8")
