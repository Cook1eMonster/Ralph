"""Request/Response schemas for the Ralph API.

These Pydantic models define the API contract for request and response bodies.
They are separate from the domain models in ralph.models.
"""

from typing import Optional

from pydantic import BaseModel

from ralph.models import (
    TaskNode,
    TaskStatus,
    TaskWithPath,
    TokenEstimate,
    Tree,
    TreeStats,
)


# =============================================================================
# Project Schemas
# =============================================================================


class CreateProjectRequest(BaseModel):
    """Request to create a new project."""

    name: str
    path: str
    github_url: Optional[str] = None
    target_tokens: int = 60000
    venv_path: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    """Request to update project settings."""

    name: Optional[str] = None
    github_url: Optional[str] = None
    target_tokens: Optional[int] = None
    venv_path: Optional[str] = None


class GitSyncStatus(BaseModel):
    """Status of git synchronization."""

    is_git_repo: bool
    has_remote: bool
    was_behind: bool
    pulled: bool
    commits_pulled: int
    error: Optional[str] = None


class IndexStatus(BaseModel):
    """Status of codebase indexing."""

    indexed: int
    updated: int
    skipped: int
    errors: int
    total_chunks: int
    error_message: Optional[str] = None


class LaunchResponse(BaseModel):
    """Response from launching a project."""

    script_path: str
    command: str
    git_sync: Optional[GitSyncStatus] = None
    index_status: Optional[IndexStatus] = None


# =============================================================================
# Task Schemas
# =============================================================================


class UpdateStatusRequest(BaseModel):
    """Request to update a task's status."""

    status: TaskStatus


class AddTaskRequest(BaseModel):
    """Request to add a new task."""

    parent_path: str  # Dot-separated path
    task: TaskNode


class GeneratePlanRequest(BaseModel):
    """Request to generate a project plan."""

    use_ai: bool = True


# =============================================================================
# Response Schemas
# =============================================================================


class TreeResponse(BaseModel):
    """Response containing a tree and its stats."""

    tree: Tree
    stats: TreeStats


class NextTaskResponse(BaseModel):
    """Response for the next task endpoint."""

    task: Optional[TaskWithPath] = None
    context: str = ""
    estimate: Optional[TokenEstimate] = None
    prompt: str = ""


class EstimateItem(BaseModel):
    """A single task with its token estimate."""

    task: TaskWithPath
    estimate: TokenEstimate


# =============================================================================
# Worker Schemas
# =============================================================================


class AssignWorkersRequest(BaseModel):
    """Request to assign tasks to workers."""

    count: int = 4


# =============================================================================
# Self-Healing Schemas
# =============================================================================


class HealingRequest(BaseModel):
    """Request to run self-healing on a task."""

    task_path: str  # Dot-separated path to task
    max_attempts: int = 3


class ValidationResultResponse(BaseModel):
    """Result of a single validation command."""

    success: bool
    command: str
    stdout: str
    stderr: str
    return_code: int


class HealingResponse(BaseModel):
    """Response from self-healing."""

    success: bool
    attempts: int
    file_fixed: Optional[str] = None
    validations: list[ValidationResultResponse] = []
    error: Optional[str] = None


# =============================================================================
# Ollama Schemas
# =============================================================================


class OllamaStatusResponse(BaseModel):
    """Status of Ollama service and models."""

    available: bool
    loaded_models: list[str]
    configured_models: list[str]
