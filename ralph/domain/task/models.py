"""Task domain models.

Pure domain models for task tree management. Uses Pydantic for
serialization compatibility with the rest of the codebase.
"""

from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a task in the tree."""

    PENDING = "pending"
    IN_PROGRESS = "in-progress"
    DONE = "done"
    BLOCKED = "blocked"


class TaskNode(BaseModel):
    """A node in the task tree (can be a task or a grouping).

    Leaf nodes (those without children) represent executable tasks.
    Non-leaf nodes are organizational groupings.
    """

    name: str
    status: TaskStatus = TaskStatus.PENDING
    spec: str | None = None
    context: str | None = None
    read_first: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    children: list["TaskNode"] = Field(default_factory=list)

    def is_leaf(self) -> bool:
        """Check if this node is a leaf (executable task).

        Leaf nodes have no children and represent actual work items.
        Non-leaf nodes are organizational containers.
        """
        return len(self.children) == 0


class Tree(BaseModel):
    """The root of a task tree (factory plan).

    Represents the entire project's task breakdown structure.
    The root itself is not a task, but contains the top-level
    task groupings as children.
    """

    name: str
    context: str = ""
    children: list[TaskNode] = Field(default_factory=list)


class TaskWithPath(BaseModel):
    """A task node with its path in the tree.

    The path is a list of node names from root to the task,
    enabling navigation and updates at specific locations.
    """

    task: TaskNode
    path: list[str]
