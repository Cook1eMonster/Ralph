"""File persistence layer for Ralph.

Handles reading/writing JSON files for projects, trees, workers, etc.
Each project has its own folder under projects/.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Config, Project, Tree, WorkerList, TaskNode, TaskStatus


PROJECTS_DIR = Path(__file__).parent.parent / "projects"
RECENT_FILE = Path(__file__).parent.parent / "recent.json"
MAX_RECENT = 10


def ensure_projects_dir() -> Path:
    """Ensure the projects directory exists."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return PROJECTS_DIR


def get_project_dir(project_id: str) -> Path:
    """Get the directory for a specific project."""
    return PROJECTS_DIR / project_id


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    import re
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "project"


# =============================================================================
# Project Management
# =============================================================================


def list_projects() -> list[Project]:
    """List all projects."""
    ensure_projects_dir()
    projects = []

    for folder in PROJECTS_DIR.iterdir():
        if folder.is_dir():
            config_file = folder / "config.json"
            if config_file.exists():
                try:
                    data = json.loads(config_file.read_text(encoding="utf-8"))
                    projects.append(Project(**data))
                except (json.JSONDecodeError, ValueError):
                    pass  # Skip invalid projects

    return projects


def get_project(project_id: str) -> Optional[Project]:
    """Get a project by ID."""
    config_file = get_project_dir(project_id) / "config.json"
    if not config_file.exists():
        return None

    data = json.loads(config_file.read_text(encoding="utf-8"))
    return Project(**data)


def create_project(
    name: str,
    path: str,
    github_url: Optional[str] = None,
    target_tokens: int = 60000,
    venv_path: Optional[str] = None,
) -> Project:
    """Create a new project."""
    ensure_projects_dir()

    project_id = slugify(name)

    # Ensure unique ID
    base_id = project_id
    counter = 1
    while get_project_dir(project_id).exists():
        project_id = f"{base_id}-{counter}"
        counter += 1

    # Auto-detect venv if not provided
    if venv_path is None:
        venv_path = detect_venv(path)

    project = Project(
        id=project_id,
        name=name,
        path=path,
        github_url=github_url,
        target_tokens=target_tokens,
        venv_path=venv_path,
    )

    # Create project directory and save config
    project_dir = get_project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    config_file = project_dir / "config.json"
    config_file.write_text(
        json.dumps(project.model_dump(), indent=2),
        encoding="utf-8",
    )

    # Create default requirements.md
    req_file = project_dir / "requirements.md"
    if not req_file.exists():
        req_file.write_text(
            f"""# {name} Requirements

## Goals
- Define your project goals here

## Priorities
- What matters most?

## Backlog
- Features to build

## Skip
- What to avoid
""",
            encoding="utf-8",
        )

    return project


def delete_project(project_id: str) -> bool:
    """Delete a project and all its data."""
    import shutil

    project_dir = get_project_dir(project_id)
    if not project_dir.exists():
        return False

    shutil.rmtree(project_dir)

    # Clean up recent.json
    remove_from_recent(project_id)

    return True


def remove_from_recent(project_id: str) -> None:
    """Remove a project from the recent list."""
    recent = load_recent()
    if project_id in recent:
        recent.remove(project_id)
        RECENT_FILE.write_text(
            json.dumps({"recent": recent}, indent=2),
            encoding="utf-8",
        )


def update_project(project: Project) -> None:
    """Update a project's configuration."""
    config_file = get_project_dir(project.id) / "config.json"
    config_file.write_text(
        json.dumps(project.model_dump(), indent=2),
        encoding="utf-8",
    )


# =============================================================================
# Recent Projects
# =============================================================================


def load_recent() -> list[str]:
    """Load list of recently accessed project IDs, most recent first."""
    if not RECENT_FILE.exists():
        return []
    try:
        data = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
        return data.get("recent", [])
    except (json.JSONDecodeError, ValueError):
        return []


def update_recent(project_id: str) -> None:
    """Update recent list, moving project_id to the top."""
    recent = load_recent()
    # Remove if already present
    if project_id in recent:
        recent.remove(project_id)
    # Add to front
    recent.insert(0, project_id)
    # Trim to max
    recent = recent[:MAX_RECENT]
    # Save
    RECENT_FILE.write_text(
        json.dumps({"recent": recent}, indent=2),
        encoding="utf-8",
    )


def get_projects_by_recent() -> list[Project]:
    """Get all projects ordered by recent access (most recent first).

    Projects not in recent list appear at the end.
    """
    recent_ids = load_recent()
    all_projects = list_projects()

    # Build lookup
    project_map = {p.id: p for p in all_projects}

    # Order by recent
    ordered = []
    for pid in recent_ids:
        if pid in project_map:
            ordered.append(project_map.pop(pid))

    # Add remaining projects (not in recent)
    ordered.extend(project_map.values())

    return ordered


# =============================================================================
# Tree Management
# =============================================================================


def load_tree(project_id: str) -> Optional[Tree]:
    """Load the task tree for a project."""
    tree_file = get_project_dir(project_id) / "tree.json"
    if not tree_file.exists():
        return None

    data = json.loads(tree_file.read_text(encoding="utf-8"))
    return Tree(**data)


def save_tree(project_id: str, tree: Tree) -> None:
    """Save the task tree for a project."""
    tree_file = get_project_dir(project_id) / "tree.json"
    tree_file.write_text(
        json.dumps(tree.model_dump(), indent=2),
        encoding="utf-8",
    )


def create_empty_tree(project_id: str, name: str) -> Tree:
    """Create an empty tree structure."""
    tree = Tree(
        name=name,
        context="",
        children=[
            TaskNode(
                name="Warehouse: Core Infrastructure",
                status=TaskStatus.PENDING,
                context="Shared dependencies and core modules",
                children=[],
            ),
            TaskNode(
                name="Line: Main Features",
                status=TaskStatus.PENDING,
                context="Primary feature development",
                children=[],
            ),
        ],
    )
    save_tree(project_id, tree)
    return tree


# =============================================================================
# Workers
# =============================================================================


def load_workers(project_id: str) -> WorkerList:
    """Load worker assignments for a project."""
    workers_file = get_project_dir(project_id) / "workers.json"
    if not workers_file.exists():
        return WorkerList()

    data = json.loads(workers_file.read_text(encoding="utf-8"))
    return WorkerList(**data)


def save_workers(project_id: str, workers: WorkerList) -> None:
    """Save worker assignments for a project."""
    workers_file = get_project_dir(project_id) / "workers.json"
    workers_file.write_text(
        json.dumps(workers.model_dump(), indent=2),
        encoding="utf-8",
    )


# =============================================================================
# Requirements
# =============================================================================


def load_requirements(project_id: str) -> str:
    """Load requirements for a project."""
    req_file = get_project_dir(project_id) / "requirements.md"
    if not req_file.exists():
        return ""
    return req_file.read_text(encoding="utf-8")


def save_requirements(project_id: str, content: str) -> None:
    """Save requirements for a project."""
    req_file = get_project_dir(project_id) / "requirements.md"
    req_file.write_text(content, encoding="utf-8")


# =============================================================================
# Progress Log
# =============================================================================


def append_progress(project_id: str, entry: str) -> None:
    """Append an entry to the progress log."""
    progress_file = get_project_dir(project_id) / "progress.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with progress_file.open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {entry}\n")


# =============================================================================
# Venv Detection & Launch Scripts
# =============================================================================


def detect_venv(project_path: str) -> Optional[str]:
    """Auto-detect Python venv in a project directory."""
    project = Path(project_path)

    # Common venv locations to check
    venv_candidates = [
        project / "venv",
        project / ".venv",
        project / "env",
        project / ".env",
        # Monorepo patterns
        project / "apps" / "backend" / "venv",
        project / "apps" / "backend" / "api" / "venv",
        project / "backend" / "venv",
    ]

    for venv_path in venv_candidates:
        # Check for Windows venv
        activate_script = venv_path / "Scripts" / "activate.bat"
        if activate_script.exists():
            return str(venv_path)

        # Check for Unix venv
        activate_script = venv_path / "bin" / "activate"
        if activate_script.exists():
            return str(venv_path)

    return None


def get_launch_script_content(project: Project) -> str:
    """Generate the content of a launch script for a project."""
    ralph_dir = Path(__file__).parent.parent.absolute()
    project_dir = get_project_dir(project.id).absolute()

    lines = [
        "@echo off",
        f"REM Launch script for {project.name}",
        f"REM Generated by Ralph",
        "",
        f"echo ============================================================",
        f"echo {project.name} - Ralph Development Environment",
        f"echo ============================================================",
        "",
    ]

    # Activate venv if configured
    if project.venv_path:
        venv_path = Path(project.venv_path)
        if not venv_path.is_absolute():
            venv_path = Path(project.path) / venv_path

        activate_script = venv_path / "Scripts" / "activate.bat"
        lines.extend([
            "REM Activate Python virtual environment",
            f'if exist "{activate_script}" (',
            f'    call "{activate_script}"',
            "    echo [OK] Virtual environment activated",
            ") else (",
            f'    echo [WARN] Venv not found: {activate_script}',
            ")",
            "",
        ])

    # Change to project directory
    lines.extend([
        "REM Change to project directory",
        f'cd /d "{project.path}"',
        "",
    ])

    # Set Ralph environment variables
    lines.extend([
        "REM Set Ralph environment",
        f'set RALPH_PROJECT_ID={project.id}',
        f'set RALPH_PROJECT_DIR={project_dir}',
        f'set RALPH_DIR={ralph_dir}',
        "",
    ])

    # Install Ralph in the venv if needed
    lines.extend([
        "REM Ensure Ralph is available in this environment",
        f'pip show ralph >nul 2>&1 || pip install -e "{ralph_dir}" --quiet',
        "",
    ])

    # Git pull (optional)
    lines.extend([
        "REM Pull latest changes (if git repo)",
        'if exist ".git" (',
        "    echo.",
        "    echo [1/3] Pulling latest changes...",
        "    git pull origin main 2>nul || git pull origin master 2>nul || echo No remote configured",
        ")",
        "",
    ])

    # Show status
    lines.extend([
        "echo.",
        "echo [2/3] Current progress:",
        "echo ------------------------------------------------------------",
        f'python -m ralph.cli status --project {project.id} 2>nul || echo No tree configured yet',
        "",
        "echo.",
        "echo [3/3] Next task:",
        "echo ------------------------------------------------------------",
        f'python -m ralph.cli next --project {project.id} 2>nul || echo No tasks available',
        "",
    ])

    # Ready message
    lines.extend([
        "echo.",
        "echo ============================================================",
        "echo Ready to work! Commands:",
        f"echo   ralph done       - Mark task complete",
        f"echo   ralph validate   - Run acceptance checks",
        f"echo   ralph next       - Get next task",
        "echo ============================================================",
        "",
    ])

    return "\n".join(lines)


def generate_launch_script(project: Project) -> Path:
    """Generate a launch script for a project and return its path."""
    project_dir = get_project_dir(project.id)
    script_path = project_dir / "start.bat"

    content = get_launch_script_content(project)
    script_path.write_text(content, encoding="utf-8")

    return script_path


# =============================================================================
# Git Operations
# =============================================================================


class GitSyncResult:
    """Result of a git sync operation."""

    def __init__(
        self,
        is_git_repo: bool = False,
        has_remote: bool = False,
        was_behind: bool = False,
        pulled: bool = False,
        commits_pulled: int = 0,
        error: Optional[str] = None,
    ):
        self.is_git_repo = is_git_repo
        self.has_remote = has_remote
        self.was_behind = was_behind
        self.pulled = pulled
        self.commits_pulled = commits_pulled
        self.error = error

    def to_dict(self) -> dict:
        return {
            "is_git_repo": self.is_git_repo,
            "has_remote": self.has_remote,
            "was_behind": self.was_behind,
            "pulled": self.pulled,
            "commits_pulled": self.commits_pulled,
            "error": self.error,
        }


def check_git_status(project_path: str) -> GitSyncResult:
    """Check if a project's git repo is behind remote and needs pulling."""
    import subprocess

    project = Path(project_path)
    git_dir = project / ".git"

    # Check if it's a git repo
    if not git_dir.exists():
        return GitSyncResult(is_git_repo=False)

    result = GitSyncResult(is_git_repo=True)

    try:
        # Check if there's a remote configured
        remote_check = subprocess.run(
            ["git", "remote"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if not remote_check.stdout.strip():
            result.has_remote = False
            return result

        result.has_remote = True

        # Fetch from remote to update refs
        subprocess.run(
            ["git", "fetch"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Check how many commits behind
        behind_check = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..@{u}"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if behind_check.returncode == 0:
            commits_behind = int(behind_check.stdout.strip() or "0")
            result.was_behind = commits_behind > 0
            result.commits_pulled = commits_behind

    except subprocess.TimeoutExpired:
        result.error = "Git operation timed out"
    except Exception as e:
        result.error = str(e)

    return result


def git_pull(project_path: str) -> GitSyncResult:
    """Pull latest changes from remote if behind."""
    import subprocess

    # First check status
    result = check_git_status(project_path)

    if not result.is_git_repo:
        return result

    if not result.has_remote:
        return result

    if result.error:
        return result

    if not result.was_behind:
        # Already up to date
        return result

    try:
        # Try to pull (try main first, then master)
        pull_result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if pull_result.returncode != 0:
            # Try master branch
            pull_result = subprocess.run(
                ["git", "pull", "origin", "master"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

        if pull_result.returncode == 0:
            result.pulled = True
        else:
            result.error = pull_result.stderr.strip() or "Pull failed"
            result.pulled = False

    except subprocess.TimeoutExpired:
        result.error = "Git pull timed out"
        result.pulled = False
    except Exception as e:
        result.error = str(e)
        result.pulled = False

    return result
