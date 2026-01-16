"""Domain value objects for Ralph.

Immutable value objects representing core domain concepts.
These provide type safety and domain-specific operations.
"""

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TaskPath:
    """Immutable path to a task in the tree.

    Represents the hierarchical location of a task using a tuple of
    segment names from root to leaf. Provides navigation operations
    for traversing the tree structure.

    Example:
        path = TaskPath.from_string("Root.Backend.API.Endpoints")
        parent = path.parent()  # Root.Backend.API
        child = path.child("Users")  # Root.Backend.API.Endpoints.Users
    """

    segments: tuple[str, ...]

    @classmethod
    def from_string(cls, path: str, separator: str = ".") -> "TaskPath":
        """Create a TaskPath from a dot-separated (or custom separator) string.

        Args:
            path: String path like "Root.Backend.API"
            separator: Character(s) separating segments, defaults to "."

        Returns:
            New TaskPath with parsed segments
        """
        if not path:
            return cls(segments=())
        return cls(segments=tuple(path.split(separator)))

    @classmethod
    def from_list(cls, segments: list[str]) -> "TaskPath":
        """Create a TaskPath from a list of segment names.

        Args:
            segments: List of path segments like ["Root", "Backend", "API"]

        Returns:
            New TaskPath with the provided segments
        """
        return cls(segments=tuple(segments))

    def __str__(self) -> str:
        """Return the path as a dot-separated string."""
        return ".".join(self.segments)

    def parent(self) -> "TaskPath":
        """Return a new TaskPath without the last segment.

        Returns:
            New TaskPath representing the parent location,
            or empty TaskPath if already at root
        """
        if len(self.segments) <= 1:
            return TaskPath(segments=())
        return TaskPath(segments=self.segments[:-1])

    def child(self, name: str) -> "TaskPath":
        """Return a new TaskPath with an appended segment.

        Args:
            name: Name of the child segment to append

        Returns:
            New TaskPath with the child segment added
        """
        return TaskPath(segments=self.segments + (name,))

    @property
    def leaf_name(self) -> str:
        """Return the last segment of the path (the task name).

        Returns:
            The final segment, or empty string if path is empty
        """
        if not self.segments:
            return ""
        return self.segments[-1]

    def __bool__(self) -> bool:
        """Return True if the path has any segments."""
        return len(self.segments) > 0


@dataclass(frozen=True)
class TokenCount:
    """Token estimation breakdown for task sizing.

    Breaks down estimated token usage into categories to help
    ensure tasks fit within the target context window (~60k tokens).

    Attributes:
        base_overhead: System prompt, tool definitions, etc.
        context: Accumulated context from parent nodes
        task_description: Task name, spec, and requirements
        file_reads: Estimated tokens from reading files
        tool_calls: Estimated tokens from tool invocations
        buffer: Response buffer for generated code and explanations
    """

    base_overhead: int
    context: int
    task_description: int
    file_reads: int
    tool_calls: int
    buffer: int

    @property
    def total(self) -> int:
        """Calculate the total estimated token count.

        Returns:
            Sum of all token categories
        """
        return (
            self.base_overhead
            + self.context
            + self.task_description
            + self.file_reads
            + self.tool_calls
            + self.buffer
        )

    def utilization(self, target: int) -> float:
        """Calculate the percentage of target tokens used.

        Args:
            target: Target token budget (e.g., 60000)

        Returns:
            Percentage as a float (e.g., 75.5 for 75.5%)
        """
        if target <= 0:
            return 0.0
        return round(self.total / target * 100, 1)

    def fits(self, target: int) -> bool:
        """Check if the estimated tokens fit within the target budget.

        Args:
            target: Target token budget (e.g., 60000)

        Returns:
            True if total tokens are at or below target
        """
        return self.total <= target


@dataclass(frozen=True)
class BranchName:
    """Git branch name value object.

    Represents a normalized git branch name suitable for
    feature branch workflows. Handles conversion from task
    names to valid branch names.

    Attributes:
        value: The normalized branch name string
    """

    value: str

    @classmethod
    def from_task_name(cls, name: str) -> "BranchName":
        """Create a branch name from a task name.

        Normalizes the task name by:
        - Removing special characters (keeping alphanumeric, spaces, hyphens)
        - Converting spaces to hyphens
        - Converting to lowercase
        - Truncating to 50 characters max
        - Adding 'feat/' prefix

        Args:
            name: Task name to convert

        Returns:
            New BranchName with normalized value

        Example:
            BranchName.from_task_name("Add User Authentication!")
            # -> BranchName(value="feat/add-user-authentication")
        """
        # Remove special characters, keep alphanumeric, spaces, and hyphens
        branch = re.sub(r"[^a-zA-Z0-9\s-]", "", name)
        # Replace whitespace with hyphens
        branch = re.sub(r"\s+", "-", branch.strip())
        # Lowercase and truncate
        branch = branch.lower()[:50]
        # Remove any trailing hyphens from truncation
        branch = branch.rstrip("-")
        return cls(value=f"feat/{branch}")

    def __str__(self) -> str:
        """Return the branch name string."""
        return self.value


@dataclass(frozen=True)
class Complexity:
    """Task complexity rating.

    Represents a task's estimated complexity level based on
    keywords in the task name and the number of files involved.
    Used for token estimation and task sizing.

    Attributes:
        level: Complexity level - "low", "medium", or "high"
    """

    level: Literal["low", "medium", "high"]

    # Keywords indicating high complexity tasks
    _HIGH_INDICATORS: tuple[str, ...] = (
        "refactor",
        "rewrite",
        "migrate",
        "integration",
        "architecture",
        "security",
        "performance",
        "optimization",
    )

    # Keywords indicating medium complexity tasks
    _MEDIUM_INDICATORS: tuple[str, ...] = (
        "implement",
        "create",
        "build",
        "add",
        "feature",
        "endpoint",
        "component",
    )

    @classmethod
    def estimate(cls, task_name: str, file_count: int) -> "Complexity":
        """Estimate complexity from task name and file count.

        Complexity rules:
        - High: Contains refactor/rewrite/migrate keywords, or >3 files
        - Medium: Contains implement/create/build keywords, or >1 file
        - Low: Otherwise

        Args:
            task_name: Name of the task to analyze
            file_count: Number of files the task will touch

        Returns:
            New Complexity with estimated level

        Example:
            Complexity.estimate("Refactor authentication module", 2)
            # -> Complexity(level="high")
        """
        name_lower = task_name.lower()

        # Check for high complexity indicators
        if any(ind in name_lower for ind in cls._HIGH_INDICATORS):
            return cls(level="high")

        # File count can bump to high
        if file_count > 3:
            return cls(level="high")

        # Check for medium complexity indicators
        if any(ind in name_lower for ind in cls._MEDIUM_INDICATORS):
            return cls(level="medium")

        # File count can bump to medium
        if file_count > 1:
            return cls(level="medium")

        return cls(level="low")

    def __str__(self) -> str:
        """Return the complexity level string."""
        return self.level
