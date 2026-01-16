"""Pydantic models for Ralph."""

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a task in the tree."""

    PENDING = "pending"
    IN_PROGRESS = "in-progress"
    DONE = "done"
    BLOCKED = "blocked"


class AIProvider(str, Enum):
    """AI provider options."""
    CLAUDE = "claude"
    LOCAL = "local"  # Ollama


class AIConfig(BaseModel):
    """AI provider configuration for different task types."""
    planning: AIProvider = AIProvider.CLAUDE
    context: AIProvider = AIProvider.LOCAL
    coding: AIProvider = AIProvider.CLAUDE

    # Local AI model settings (single LLM for both planning and coding)
    local_model: str = "qwen2.5-coder:7b"  # Used for planning and coding
    embed_model: str = "nomic-embed-text"  # Used for context/embeddings

    # Backwards compatibility aliases
    @property
    def planning_model(self) -> str:
        return self.local_model

    @property
    def coding_model(self) -> str:
        return self.local_model


class TaskNode(BaseModel):
    """A node in the task tree (can be a task or a grouping)."""

    name: str
    status: TaskStatus = TaskStatus.PENDING
    spec: Optional[str] = None
    context: Optional[str] = None
    read_first: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    children: list["TaskNode"] = Field(default_factory=list)

    def is_leaf(self) -> bool:
        """Check if this node is a leaf (executable task)."""
        return len(self.children) == 0


class Tree(BaseModel):
    """The root of a task tree (factory plan)."""

    name: str
    context: str = ""
    children: list[TaskNode] = Field(default_factory=list)


class Project(BaseModel):
    """A managed project configuration."""

    id: str = Field(description="URL-safe slug, e.g., 'anespreop'")
    name: str = Field(description="Human-readable name")
    path: str = Field(description="Absolute path to codebase")
    github_url: Optional[str] = None
    target_tokens: int = 60000
    venv_path: Optional[str] = Field(default=None, description="Path to Python venv (e.g., ./venv or absolute path)")
    ai_config: Optional[AIConfig] = None


class Worker(BaseModel):
    """A parallel worker assignment."""

    id: int
    branch: str
    task: str
    path: str  # Dot-separated path in tree, e.g., "Root.Feature.Task"
    status: Literal["assigned", "in-progress", "done"] = "assigned"


class WorkerList(BaseModel):
    """Collection of worker assignments."""

    workers: list[Worker] = Field(default_factory=list)


class Config(BaseModel):
    """Agent configuration."""

    agent: str = "claude"
    agent_cmd: str = "claude -p"
    target_tokens: int = 60000


class FolderEntry(BaseModel):
    """A filesystem entry for the folder browser."""

    name: str
    path: str
    is_dir: bool
    children: Optional[list["FolderEntry"]] = None


class TokenEstimate(BaseModel):
    """Token usage estimate for a task."""

    base_overhead: int
    context_tokens: int
    task_tokens: int
    file_reads: int
    tool_calls: int
    buffer: int
    total: int
    target: int
    fits: bool
    utilization: float
    complexity: Literal["low", "medium", "high"]


class TaskWithPath(BaseModel):
    """A task node with its path in the tree."""

    task: TaskNode
    path: list[str]


class TreeStats(BaseModel):
    """Statistics about a task tree."""

    total: int
    done: int
    pending: int
    in_progress: int
    blocked: int

    @property
    def progress_percent(self) -> float:
        """Calculate completion percentage."""
        if self.total == 0:
            return 0.0
        return round(self.done / self.total * 100, 1)


class ProjectSummary(BaseModel):
    """Summary of a project for the dashboard."""

    id: str
    name: str
    path: str
    github_url: Optional[str] = None
    stats: Optional[TreeStats] = None
