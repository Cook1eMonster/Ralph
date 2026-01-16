"""Project application service.

Orchestrates project-level operations by combining domain functions.
All functions are pure - no I/O, no side effects.
"""

from ralph.domain.project import Project, ProjectCreated, ProjectSummary
from ralph.domain.shared import Err, Ok, Result
from ralph.domain.task import TaskStatus, Tree, count_by_status


def get_project_summary(project: Project, tree: Tree) -> ProjectSummary:
    """Create a project summary from project config and task tree.

    Combines project metadata with task tree statistics to create
    a summary suitable for dashboard display.

    Args:
        project: The project configuration.
        tree: The project's task tree.

    Returns:
        ProjectSummary with progress information.
    """
    # Count tasks by status
    counts = count_by_status(tree)
    total = sum(counts.values())
    completed = counts[TaskStatus.DONE]

    # Calculate progress percentage
    progress = 0.0
    if total > 0:
        progress = round(completed / total * 100, 1)

    return ProjectSummary(
        id=project.id,
        name=project.name,
        path=project.path,
        github_url=project.github_url,
        total_tasks=total,
        completed_tasks=completed,
        progress_percent=progress,
    )


def create_project(
    project_id: str,
    name: str,
    path: str,
    github_url: str | None = None,
    target_tokens: int = 60000,
) -> Result[tuple[Project, ProjectCreated], str]:
    """Create a new project configuration.

    Validates inputs and creates a Project instance along with
    a ProjectCreated domain event.

    Args:
        project_id: URL-safe slug for the project (e.g., 'my-project').
        name: Human-readable project name.
        path: Absolute path to the project codebase.
        github_url: Optional GitHub repository URL.
        target_tokens: Target token budget per task (default: 60000).

    Returns:
        Ok((Project, ProjectCreated)) on success, or
        Err(str) with validation error message.
    """
    # Validate project_id
    if not project_id:
        return Err("Project ID cannot be empty")

    if not project_id.replace("-", "").replace("_", "").isalnum():
        return Err(
            "Project ID must contain only alphanumeric characters, "
            "hyphens, and underscores"
        )

    # Validate name
    if not name:
        return Err("Project name cannot be empty")

    if not name.strip():
        return Err("Project name cannot be whitespace only")

    # Validate path
    if not path:
        return Err("Project path cannot be empty")

    # Validate target_tokens
    if target_tokens <= 0:
        return Err("Target tokens must be positive")

    if target_tokens > 200000:
        return Err("Target tokens exceeds maximum (200000)")

    # Create the project
    project = Project(
        id=project_id,
        name=name.strip(),
        path=path,
        github_url=github_url,
        target_tokens=target_tokens,
    )

    # Create the domain event
    event = ProjectCreated(
        project_id=project_id,
        name=name.strip(),
        path=path,
    )

    return Ok((project, event))
