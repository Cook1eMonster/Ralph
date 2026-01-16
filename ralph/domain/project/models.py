"""Project domain models.

This module contains the core domain models for the project aggregate.
These are pure data structures with no I/O or side effects.
"""

from pydantic import BaseModel, Field


class Project(BaseModel):
    """A managed project configuration.

    Represents a codebase that Ralph is managing tasks for.
    The project configuration includes paths, optional GitHub integration,
    and token budgeting for AI agents.
    """

    id: str = Field(description="URL-safe slug, e.g., 'anespreop'")
    name: str = Field(description="Human-readable name")
    path: str = Field(description="Absolute path to codebase")
    github_url: str | None = None
    target_tokens: int = 60000
    venv_path: str | None = Field(
        default=None,
        description="Path to Python venv (e.g., ./venv or absolute path)",
    )


class ProjectSummary(BaseModel):
    """Summary of a project for dashboard display.

    A lightweight view of a project suitable for listing
    in the dashboard without loading full task tree data.
    """

    id: str
    name: str
    path: str
    github_url: str | None = None
    total_tasks: int = 0
    completed_tasks: int = 0
    progress_percent: float = 0.0
