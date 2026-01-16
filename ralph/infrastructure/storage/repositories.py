"""Repository implementations for domain aggregates.

Provides repository classes that wrap the existing storage.py functions
but return Result types for explicit error handling.
"""

from pathlib import Path

from ralph.domain.project.models import Project
from ralph.domain.shared.result import Err, Ok, Result
from ralph.domain.task.models import Tree
from ralph.domain.worker.models import WorkerPool
from ralph.infrastructure.storage.json_storage import JsonStorage

# Re-use the projects directory path from storage module
PROJECTS_DIR = Path(__file__).parent.parent.parent.parent / "projects"


def _get_project_dir(project_id: str) -> Path:
    """Get the directory for a specific project."""
    return PROJECTS_DIR / project_id


def _ensure_projects_dir() -> Path:
    """Ensure the projects directory exists."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return PROJECTS_DIR


class TreeRepository:
    """Repository for task tree persistence.

    Wraps tree.json file operations with Result-based error handling.
    """

    def __init__(self, storage: JsonStorage | None = None) -> None:
        """Initialize the repository.

        Args:
            storage: JsonStorage instance to use. Creates new one if not provided.
        """
        self._storage = storage or JsonStorage()

    def load(self, project_id: str) -> Result[Tree, str]:
        """Load the task tree for a project.

        Args:
            project_id: ID of the project to load tree for.

        Returns:
            Ok(Tree) if successful, Err(str) with error message if failed.
        """
        tree_file = _get_project_dir(project_id) / "tree.json"

        result = self._storage.load_json(tree_file)
        if isinstance(result, Err):
            return result

        try:
            tree = Tree(**result.value)
            return Ok(tree)
        except Exception as e:
            return Err(f"Invalid tree data for project {project_id}: {e}")

    def save(self, project_id: str, tree: Tree) -> Result[None, str]:
        """Save the task tree for a project.

        Args:
            project_id: ID of the project to save tree for.
            tree: Tree instance to persist.

        Returns:
            Ok(None) if successful, Err(str) with error message if failed.
        """
        tree_file = _get_project_dir(project_id) / "tree.json"
        return self._storage.save_json(tree_file, tree.model_dump())

    def exists(self, project_id: str) -> bool:
        """Check if a tree exists for a project.

        Args:
            project_id: ID of the project to check.

        Returns:
            True if tree.json exists, False otherwise.
        """
        tree_file = _get_project_dir(project_id) / "tree.json"
        return tree_file.exists()


class ProjectRepository:
    """Repository for project configuration persistence.

    Wraps config.json file operations with Result-based error handling.
    """

    def __init__(self, storage: JsonStorage | None = None) -> None:
        """Initialize the repository.

        Args:
            storage: JsonStorage instance to use. Creates new one if not provided.
        """
        self._storage = storage or JsonStorage()

    def list_all(self) -> Result[list[Project], str]:
        """List all projects.

        Returns:
            Ok(list[Project]) with all valid projects,
            Err(str) if the projects directory cannot be read.
        """
        try:
            _ensure_projects_dir()
            projects: list[Project] = []

            for folder in PROJECTS_DIR.iterdir():
                if folder.is_dir():
                    config_file = folder / "config.json"
                    if config_file.exists():
                        result = self._storage.load_json(config_file)
                        if isinstance(result, Ok):
                            try:
                                projects.append(Project(**result.value))
                            except Exception:
                                # Skip invalid project configs
                                pass

            return Ok(projects)

        except PermissionError:
            return Err(f"Permission denied accessing {PROJECTS_DIR}")
        except OSError as e:
            return Err(f"Error listing projects: {e}")

    def get(self, project_id: str) -> Result[Project, str]:
        """Get a project by ID.

        Args:
            project_id: ID of the project to retrieve.

        Returns:
            Ok(Project) if found and valid, Err(str) otherwise.
        """
        config_file = _get_project_dir(project_id) / "config.json"

        result = self._storage.load_json(config_file)
        if isinstance(result, Err):
            return Err(f"Project not found: {project_id}")

        try:
            project = Project(**result.value)
            return Ok(project)
        except Exception as e:
            return Err(f"Invalid project config for {project_id}: {e}")

    def save(self, project: Project) -> Result[None, str]:
        """Save a project configuration.

        Args:
            project: Project instance to persist.

        Returns:
            Ok(None) if successful, Err(str) with error message if failed.
        """
        _ensure_projects_dir()
        project_dir = _get_project_dir(project.id)
        project_dir.mkdir(parents=True, exist_ok=True)

        config_file = project_dir / "config.json"
        return self._storage.save_json(config_file, project.model_dump())

    def exists(self, project_id: str) -> bool:
        """Check if a project exists.

        Args:
            project_id: ID of the project to check.

        Returns:
            True if project config exists, False otherwise.
        """
        config_file = _get_project_dir(project_id) / "config.json"
        return config_file.exists()

    def delete(self, project_id: str) -> Result[None, str]:
        """Delete a project and all its data.

        Args:
            project_id: ID of the project to delete.

        Returns:
            Ok(None) if successful, Err(str) if failed.
        """
        import shutil

        project_dir = _get_project_dir(project_id)
        if not project_dir.exists():
            return Err(f"Project not found: {project_id}")

        try:
            shutil.rmtree(project_dir)
            return Ok(None)
        except PermissionError:
            return Err(f"Permission denied deleting {project_id}")
        except OSError as e:
            return Err(f"Error deleting project {project_id}: {e}")


class WorkerRepository:
    """Repository for worker pool persistence.

    Wraps workers.json file operations with Result-based error handling.
    """

    def __init__(self, storage: JsonStorage | None = None) -> None:
        """Initialize the repository.

        Args:
            storage: JsonStorage instance to use. Creates new one if not provided.
        """
        self._storage = storage or JsonStorage()

    def load(self, project_id: str) -> Result[WorkerPool, str]:
        """Load the worker pool for a project.

        Args:
            project_id: ID of the project to load workers for.

        Returns:
            Ok(WorkerPool) if successful. Returns empty pool if file doesn't exist.
            Err(str) with error message if file exists but is invalid.
        """
        workers_file = _get_project_dir(project_id) / "workers.json"

        if not workers_file.exists():
            # No workers file means empty pool - not an error
            return Ok(WorkerPool())

        result = self._storage.load_json(workers_file)
        if isinstance(result, Err):
            return result

        try:
            pool = WorkerPool(**result.value)
            return Ok(pool)
        except Exception as e:
            return Err(f"Invalid worker data for project {project_id}: {e}")

    def save(self, project_id: str, pool: WorkerPool) -> Result[None, str]:
        """Save the worker pool for a project.

        Args:
            project_id: ID of the project to save workers for.
            pool: WorkerPool instance to persist.

        Returns:
            Ok(None) if successful, Err(str) with error message if failed.
        """
        workers_file = _get_project_dir(project_id) / "workers.json"
        return self._storage.save_json(workers_file, pool.model_dump())

    def exists(self, project_id: str) -> bool:
        """Check if a workers file exists for a project.

        Args:
            project_id: ID of the project to check.

        Returns:
            True if workers.json exists, False otherwise.
        """
        workers_file = _get_project_dir(project_id) / "workers.json"
        return workers_file.exists()
