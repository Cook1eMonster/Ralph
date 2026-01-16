"""FastAPI routes for Ralph."""

from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import core, storage
from .models import (
    FolderEntry,
    Project,
    ProjectSummary,
    TaskNode,
    TaskStatus,
    TaskWithPath,
    TokenEstimate,
    Tree,
    TreeStats,
    Worker,
    WorkerList,
)


# =============================================================================
# Request/Response Models
# =============================================================================


class CreateProjectRequest(BaseModel):
    name: str
    path: str
    github_url: Optional[str] = None
    target_tokens: int = 60000
    venv_path: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    github_url: Optional[str] = None
    target_tokens: Optional[int] = None
    venv_path: Optional[str] = None


class GitSyncStatus(BaseModel):
    is_git_repo: bool
    has_remote: bool
    was_behind: bool
    pulled: bool
    commits_pulled: int
    error: Optional[str] = None


class IndexStatus(BaseModel):
    indexed: int
    updated: int
    skipped: int
    errors: int
    total_chunks: int
    error_message: Optional[str] = None


class LaunchResponse(BaseModel):
    script_path: str
    command: str
    git_sync: Optional[GitSyncStatus] = None
    index_status: Optional[IndexStatus] = None


class UpdateStatusRequest(BaseModel):
    status: TaskStatus


class AddTaskRequest(BaseModel):
    parent_path: str  # Dot-separated path
    task: TaskNode


class AssignWorkersRequest(BaseModel):
    count: int = 4


class GeneratePlanRequest(BaseModel):
    use_ai: bool = True


class TreeResponse(BaseModel):
    tree: Tree
    stats: TreeStats


class NextTaskResponse(BaseModel):
    task: Optional[TaskWithPath] = None
    context: str = ""
    estimate: Optional[TokenEstimate] = None
    prompt: str = ""


class EstimateItem(BaseModel):
    task: TaskWithPath
    estimate: TokenEstimate


# =============================================================================
# Router
# =============================================================================


router = APIRouter(prefix="/api")


# =============================================================================
# Filesystem Browser
# =============================================================================


@router.get("/browse", response_model=list[FolderEntry])
def browse_filesystem(path: Optional[str] = None, include_files: bool = False):
    """Browse the filesystem for folder selection."""
    if path is None:
        return storage.get_drives()
    return storage.browse_folder(path, include_files)


# =============================================================================
# Project Management
# =============================================================================


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects():
    """List all projects with their stats."""
    projects = storage.list_projects()
    summaries = []

    for project in projects:
        tree = storage.load_tree(project.id)
        stats = core.count_tasks(tree) if tree else None
        summaries.append(
            ProjectSummary(
                id=project.id,
                name=project.name,
                path=project.path,
                github_url=project.github_url,
                stats=stats,
            )
        )

    return summaries


@router.post("/projects", response_model=Project)
def create_project(req: CreateProjectRequest):
    """Create a new project."""
    return storage.create_project(
        name=req.name,
        path=req.path,
        github_url=req.github_url,
        target_tokens=req.target_tokens,
        venv_path=req.venv_path,
    )


@router.patch("/projects/{project_id}", response_model=Project)
def update_project(project_id: str, req: UpdateProjectRequest):
    """Update project settings."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Update fields if provided
    if req.name is not None:
        project.name = req.name
    if req.github_url is not None:
        project.github_url = req.github_url
    if req.target_tokens is not None:
        project.target_tokens = req.target_tokens
    if req.venv_path is not None:
        project.venv_path = req.venv_path

    storage.update_project(project)
    return project


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str):
    """Get a project by ID."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    """Delete a project."""
    if not storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted"}


@router.post("/projects/{project_id}/launch", response_model=LaunchResponse)
def launch_project(project_id: str):
    """Generate and return launch script for the project.

    Before generating the script:
    1. Checks if project is behind GitHub remote
    2. Pulls latest changes if behind
    3. Indexes the codebase in ChromaDB

    Creates a start.bat that:
    1. Activates the project's venv (if configured)
    2. Changes to the project directory
    3. Sets up Ralph in the same environment
    """
    from . import context

    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check and pull from GitHub if behind
    git_result = storage.git_pull(project.path)
    git_sync = GitSyncStatus(
        is_git_repo=git_result.is_git_repo,
        has_remote=git_result.has_remote,
        was_behind=git_result.was_behind,
        pulled=git_result.pulled,
        commits_pulled=git_result.commits_pulled,
        error=git_result.error,
    )

    # Log git sync result
    if git_result.pulled:
        storage.append_progress(
            project_id,
            f"SYNC: Pulled {git_result.commits_pulled} commit(s) from remote"
        )
    elif git_result.error:
        storage.append_progress(
            project_id,
            f"SYNC ERROR: {git_result.error}"
        )

    # Index the codebase in ChromaDB
    # Store index in project's Ralph folder, not in the codebase itself
    project_dir = storage.get_project_dir(project_id)
    index_db_path = project_dir / ".ralph_context"

    index_result = context.index_project(
        project_path=project.path,
        db_path=str(index_db_path),
        force=False,  # Only index changed files
    )

    index_status = IndexStatus(
        indexed=index_result.indexed,
        updated=index_result.updated,
        skipped=index_result.skipped,
        errors=index_result.errors,
        total_chunks=index_result.total_chunks,
        error_message=index_result.error_message,
    )

    # Log indexing result
    if index_result.indexed > 0 or index_result.updated > 0:
        storage.append_progress(
            project_id,
            f"INDEX: {index_result.indexed} new, {index_result.updated} updated, {index_result.total_chunks} total chunks"
        )
    if index_result.error_message:
        storage.append_progress(
            project_id,
            f"INDEX ERROR: {index_result.error_message}"
        )

    script_path = storage.generate_launch_script(project)
    return LaunchResponse(
        script_path=str(script_path),
        command=f'start cmd /k "{script_path}"',
        git_sync=git_sync,
        index_status=index_status,
    )


@router.get("/projects/{project_id}/launch-script")
def get_launch_script(project_id: str):
    """Get the launch script content for a project."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    script_content = storage.get_launch_script_content(project)
    return {"content": script_content}


# =============================================================================
# Tree Management
# =============================================================================


@router.get("/projects/{project_id}/tree", response_model=TreeResponse)
def get_tree(project_id: str):
    """Get the task tree for a project."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        # Create empty tree if none exists
        tree = storage.create_empty_tree(project_id, project.name)

    stats = core.count_tasks(tree)
    return TreeResponse(tree=tree, stats=stats)


@router.put("/projects/{project_id}/tree", response_model=TreeResponse)
def update_tree(project_id: str, tree: Tree):
    """Update the entire task tree."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    storage.save_tree(project_id, tree)
    stats = core.count_tasks(tree)
    return TreeResponse(tree=tree, stats=stats)


@router.post("/projects/{project_id}/generate-plan", response_model=TreeResponse)
def generate_plan(project_id: str, req: GeneratePlanRequest):
    """Generate a factory plan from the codebase.

    TODO: Implement AI-based plan generation.
    For now, creates an empty tree structure.
    """
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # TODO: If req.use_ai, scan codebase and generate with AI
    # For now, create a basic structure
    tree = storage.create_empty_tree(project_id, project.name)
    stats = core.count_tasks(tree)

    return TreeResponse(tree=tree, stats=stats)


# =============================================================================
# Task Management
# =============================================================================


@router.get("/projects/{project_id}/tasks/next", response_model=NextTaskResponse)
def get_next_task(project_id: str, ai_context: bool = False):
    """Get the next pending task."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        return NextTaskResponse()

    task_with_path = core.find_next_task(tree)
    if not task_with_path:
        return NextTaskResponse()

    requirements = storage.load_requirements(project_id)
    context = core.build_context(tree, task_with_path.path, requirements)
    estimate = core.estimate_tokens(task_with_path.task, context, project.target_tokens)
    prompt = core.format_task_prompt(task_with_path.task, context, estimate)

    return NextTaskResponse(
        task=task_with_path,
        context=context,
        estimate=estimate,
        prompt=prompt,
    )


@router.post("/projects/{project_id}/tasks/{task_path}/status")
def update_task_status(project_id: str, task_path: str, req: UpdateStatusRequest):
    """Update a task's status."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Tree not found")

    # Convert dot-separated path to list
    path = task_path.split(".")

    # Update status
    new_tree = core.update_task_status(tree, path, req.status)
    storage.save_tree(project_id, new_tree)

    # Log progress if marked done
    if req.status == TaskStatus.DONE:
        task = core.find_task_by_path(tree, path)
        if task:
            storage.append_progress(project_id, f"DONE: {task.name}")

    stats = core.count_tasks(new_tree)
    return TreeResponse(tree=new_tree, stats=stats)


@router.post("/projects/{project_id}/tasks/add", response_model=TreeResponse)
def add_task(project_id: str, req: AddTaskRequest):
    """Add a new task to the tree."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Tree not found")

    parent_path = req.parent_path.split(".") if req.parent_path else []
    new_tree = core.add_task(tree, parent_path, req.task)
    storage.save_tree(project_id, new_tree)

    stats = core.count_tasks(new_tree)
    return TreeResponse(tree=new_tree, stats=stats)


@router.delete("/projects/{project_id}/tasks/{task_path}", response_model=TreeResponse)
def delete_task(project_id: str, task_path: str):
    """Remove a task from the tree."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Tree not found")

    path = task_path.split(".")
    new_tree = core.prune_task(tree, path)
    storage.save_tree(project_id, new_tree)

    stats = core.count_tasks(new_tree)
    return TreeResponse(tree=new_tree, stats=stats)


@router.get("/projects/{project_id}/tasks/estimates", response_model=list[EstimateItem])
def get_estimates(project_id: str):
    """Get token estimates for all pending tasks."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        return []

    requirements = storage.load_requirements(project_id)
    pending = core.get_all_pending_tasks(tree)

    estimates = []
    for task_with_path in pending:
        context = core.build_context(tree, task_with_path.path, requirements)
        estimate = core.estimate_tokens(
            task_with_path.task, context, project.target_tokens
        )
        estimates.append(EstimateItem(task=task_with_path, estimate=estimate))

    return estimates


# =============================================================================
# Worker Management
# =============================================================================


@router.get("/projects/{project_id}/workers", response_model=WorkerList)
def get_workers(project_id: str):
    """Get worker assignments."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return storage.load_workers(project_id)


@router.post("/projects/{project_id}/workers/assign", response_model=WorkerList)
def assign_workers(project_id: str, req: AssignWorkersRequest):
    """Assign tasks to workers."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Tree not found")

    # Find tasks to assign
    tasks = core.find_n_tasks(tree, req.count)

    # Create worker assignments
    workers = []
    for i, task_with_path in enumerate(tasks):
        worker = core.create_worker(task_with_path.task, task_with_path.path, i + 1)
        workers.append(worker)

    worker_list = WorkerList(workers=workers)
    storage.save_workers(project_id, worker_list)

    return worker_list


@router.post("/projects/{project_id}/workers/{worker_id}/done", response_model=WorkerList)
def complete_worker(project_id: str, worker_id: int):
    """Mark a worker's task as done."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Tree not found")

    workers = storage.load_workers(project_id)

    # Find the worker
    worker = next((w for w in workers.workers if w.id == worker_id), None)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Mark task done
    path = worker.path.split(".")
    new_tree = core.mark_task_done(tree, path)
    storage.save_tree(project_id, new_tree)

    # Update worker status
    worker.status = "done"
    storage.save_workers(project_id, workers)

    # Log progress
    storage.append_progress(project_id, f"DONE (Worker {worker_id}): {worker.task}")

    return workers


# =============================================================================
# Self-Healing
# =============================================================================


class HealingRequest(BaseModel):
    task_path: str  # Dot-separated path to task
    max_attempts: int = 3


class ValidationResultResponse(BaseModel):
    success: bool
    command: str
    stdout: str
    stderr: str
    return_code: int


class HealingResponse(BaseModel):
    success: bool
    attempts: int
    file_fixed: Optional[str] = None
    validations: list[ValidationResultResponse] = []
    error: Optional[str] = None


@router.post("/projects/{project_id}/heal", response_model=HealingResponse)
def heal_task_endpoint(project_id: str, req: HealingRequest):
    """Run self-healing on a task.

    Validates the task against its acceptance criteria and uses AI
    to fix any failures. Retries up to max_attempts times.
    """
    from . import self_heal

    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Tree not found")

    # Find the task
    path = req.task_path.split(".")
    task = core.find_task_by_path(tree, path)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Build context for the AI
    requirements = storage.load_requirements(project_id)
    context = core.build_context(tree, path, requirements)

    # Run self-healing
    result = self_heal.heal_task(
        task=task.model_dump(),
        project_path=project.path,
        task_context=context,
        max_attempts=req.max_attempts,
    )

    # Log result
    if result.success:
        storage.append_progress(
            project_id,
            f"HEALED: {task.name} (after {result.attempts} attempt(s))"
        )
    else:
        storage.append_progress(
            project_id,
            f"HEAL FAILED: {task.name} - {result.error}"
        )

    # Convert to response
    validations = [
        ValidationResultResponse(
            success=v.success,
            command=v.command,
            stdout=v.stdout,
            stderr=v.stderr,
            return_code=v.return_code,
        )
        for v in result.validations
    ]

    return HealingResponse(
        success=result.success,
        attempts=result.attempts,
        file_fixed=result.file_fixed,
        validations=validations,
        error=result.error,
    )


@router.post("/projects/{project_id}/tasks/{task_path}/validate")
def validate_task(project_id: str, task_path: str):
    """Run validation commands for a task without fixing.

    Returns the validation results for diagnostic purposes.
    """
    from . import self_heal

    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tree = storage.load_tree(project_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Tree not found")

    # Find the task
    path = task_path.split(".")
    task = core.find_task_by_path(tree, path)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    acceptance = task.acceptance or []
    if not acceptance:
        return {"success": True, "message": "No acceptance criteria", "validations": []}

    # Run validation
    success, validations = self_heal.run_validation(acceptance, cwd=project.path)

    return {
        "success": success,
        "validations": [
            {
                "success": v.success,
                "command": v.command,
                "stdout": v.stdout,
                "stderr": v.stderr,
                "return_code": v.return_code,
            }
            for v in validations
        ],
    }


# =============================================================================
# Requirements
# =============================================================================


@router.get("/projects/{project_id}/requirements")
def get_requirements(project_id: str):
    """Get project requirements."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = storage.load_requirements(project_id)
    return {"content": content}


@router.put("/projects/{project_id}/requirements")
def update_requirements(project_id: str, content: str):
    """Update project requirements."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    storage.save_requirements(project_id, content)
    return {"status": "updated"}


# =============================================================================
# Ollama Status
# =============================================================================


class OllamaStatusResponse(BaseModel):
    available: bool
    loaded_models: list[str]
    configured_models: list[str]


@router.get("/ollama/status", response_model=OllamaStatusResponse)
async def get_ollama_status():
    """Get Ollama service and model status."""
    from .ollama_manager import MODELS, get_ollama_manager

    manager = get_ollama_manager()
    available = await manager.check_ollama_status()
    loaded = await manager.list_running_models() if available else []

    # Extract just model names from the tuples
    configured = [model for model, _ in MODELS]

    return OllamaStatusResponse(
        available=available,
        loaded_models=loaded,
        configured_models=configured,
    )


@router.post("/ollama/reload")
async def reload_ollama_models():
    """Reload all configured Ollama models into VRAM."""
    from .ollama_manager import get_ollama_manager

    manager = get_ollama_manager()
    if not await manager.check_ollama_status():
        raise HTTPException(status_code=503, detail="Ollama is not running")

    results = await manager.load_all_models()
    return {"results": results}


# =============================================================================
# App Factory
# =============================================================================


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    from contextlib import asynccontextmanager

    from .ollama_manager import shutdown_unload_models, startup_load_models

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifespan - load/unload Ollama models."""
        # Startup: Load models into VRAM
        await startup_load_models()
        yield
        # Shutdown: Unload models from VRAM
        await shutdown_unload_models()

    app = FastAPI(
        title="Ralph",
        description="Task management for autonomous AI coding agents",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.get("/")
    def root():
        return {"name": "Ralph", "version": "2.0.0"}

    return app
