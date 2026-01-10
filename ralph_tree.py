#!/usr/bin/env python3
"""
Ralph Tree - Dynamic task tree for autonomous AI agents.

A tree-based task system where:
- Leaf tasks are executed by AI agents (max 80k tokens each)
- Branches can dynamically spawn/prune based on requirements
- Context flows from parent to child nodes
- AI agent governs tree structure (spawn/prune decisions)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

TREE_FILE = "tree.json"
REQUIREMENTS_FILE = "requirements.md"
PROGRESS_FILE = "progress.txt"
CONFIG_FILE = "config.json"
WORKERS_FILE = "workers.json"

# Token estimation constants
TARGET_TOKENS = 100000
TOKENS_PER_CHAR = 0.25  # ~4 chars per token average
BASE_OVERHEAD = 15000   # System prompt, tool definitions, etc.
TOKENS_PER_FILE = 2500  # Average file read
TOKENS_PER_TOOL_CALL = 500  # Average tool call overhead


def load_tree() -> dict:
    """Load the task tree from JSON."""
    path = Path(TREE_FILE)
    if not path.exists():
        return {"name": "Root", "children": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_tree(tree: dict) -> None:
    """Save the task tree to JSON."""
    Path(TREE_FILE).write_text(
        json.dumps(tree, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_requirements() -> str:
    """Load project requirements."""
    path = Path(REQUIREMENTS_FILE)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def append_progress(entry: str) -> None:
    """Append a learning to progress file."""
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{entry}\n")


def load_config() -> dict:
    """Load config with agent settings."""
    path = Path(CONFIG_FILE)
    if not path.exists():
        return {"agent": "claude", "agent_cmd": "claude -p"}
    return json.loads(path.read_text(encoding="utf-8"))


def load_workers() -> dict:
    """Load current worker assignments."""
    path = Path(WORKERS_FILE)
    if not path.exists():
        return {"workers": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_workers(workers: dict) -> None:
    """Save worker assignments."""
    Path(WORKERS_FILE).write_text(
        json.dumps(workers, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def task_to_branch_name(task_name: str) -> str:
    """Convert task name to git branch name."""
    # Lowercase, replace spaces with hyphens, remove special chars
    branch = task_name.lower()
    branch = branch.replace(" ", "-")
    # Keep only alphanumeric and hyphens
    branch = "".join(c for c in branch if c.isalnum() or c == "-")
    # Remove multiple hyphens
    while "--" in branch:
        branch = branch.replace("--", "-")
    # Trim to reasonable length
    branch = branch[:40].strip("-")
    return f"feat/{branch}"


def estimate_tokens(task: dict, context: str) -> dict:
    """
    Estimate tokens needed for a task.
    Returns dict with breakdown and total.
    """
    estimates = {
        "base_overhead": BASE_OVERHEAD,
        "context": int(len(context) * TOKENS_PER_CHAR),
        "task_description": int(len(task.get("name", "")) * TOKENS_PER_CHAR),
        "file_reads": len(task.get("files", [])) * TOKENS_PER_FILE,
        "tool_calls": 15 * TOKENS_PER_TOOL_CALL,  # Estimate 15 tool calls
        "response_buffer": 5000,  # Buffer for agent responses
    }
    estimates["total"] = sum(estimates.values())
    estimates["target"] = TARGET_TOKENS
    estimates["fits"] = estimates["total"] <= TARGET_TOKENS
    estimates["utilization"] = round(estimates["total"] / TARGET_TOKENS * 100, 1)
    return estimates


def estimate_task_complexity(task: dict) -> str:
    """Return complexity rating based on task description heuristics."""
    name = task.get("name", "").lower()
    files = task.get("files", [])

    # Complexity signals
    complex_words = ["refactor", "migrate", "redesign", "overhaul", "complete", "full", "entire", "all"]
    medium_words = ["integrate", "implement", "add", "create", "build"]
    simple_words = ["fix", "update", "rename", "remove", "delete", "change"]

    if any(w in name for w in complex_words) or len(files) > 3:
        return "high"
    elif any(w in name for w in medium_words) or len(files) > 1:
        return "medium"
    elif any(w in name for w in simple_words) or len(files) <= 1:
        return "low"
    return "medium"


def is_leaf(node: dict) -> bool:
    """Check if node is a leaf (executable task)."""
    return "children" not in node or len(node.get("children", [])) == 0


def get_status(node: dict) -> str:
    """Get node status, default to pending."""
    return node.get("status", "pending")


def find_next_task(node: dict, path: list[str] = None) -> Optional[tuple[dict, list[str]]]:
    """Find next pending leaf task via depth-first traversal."""
    if path is None:
        path = []

    current_path = path + [node.get("name", "unnamed")]

    if is_leaf(node):
        if get_status(node) == "pending":
            return (node, current_path)
        return None

    for child in node.get("children", []):
        result = find_next_task(child, current_path)
        if result:
            return result

    return None


def find_n_tasks(node: dict, n: int, path: list[str] = None, found: list = None) -> list:
    """Find up to N pending leaf tasks."""
    if path is None:
        path = []
    if found is None:
        found = []

    if len(found) >= n:
        return found

    current_path = path + [node.get("name", "unnamed")]

    if is_leaf(node):
        if get_status(node) == "pending":
            found.append((node, current_path))
        return found

    for child in node.get("children", []):
        find_n_tasks(child, n, current_path, found)
        if len(found) >= n:
            break

    return found


def build_context(tree: dict, path: list[str]) -> str:
    """Build context string from root to task, including requirements."""
    requirements = load_requirements()

    context_parts = []
    if requirements:
        context_parts.append(f"# Project Requirements\n{requirements}")

    # Walk path and collect context
    node = tree
    for i, name in enumerate(path):
        if i == 0:
            if node.get("context"):
                context_parts.append(f"# {name}\n{node['context']}")
            continue

        for child in node.get("children", []):
            if child.get("name") == name:
                if child.get("context"):
                    context_parts.append(f"# {name}\n{child['context']}")
                node = child
                break

    return "\n\n".join(context_parts)


def format_task(task: dict, context: str, show_estimate: bool = True) -> str:
    """Format task for agent execution."""
    output = []
    output.append("=" * 60)
    output.append("TASK")
    output.append("=" * 60)
    output.append(f"\n## Task: {task.get('name', 'unnamed')}\n")

    # Read First - mandatory files to read before starting
    if task.get("read_first"):
        output.append("## Read First (MANDATORY)")
        output.append("Before coding, read these files to understand existing patterns:\n")
        for f in task["read_first"]:
            output.append(f"- {f}")
        output.append("")

    # Spec - locked intent for the task
    if task.get("spec"):
        output.append("## Spec")
        output.append(task["spec"])
        output.append("")

    if task.get("files"):
        output.append(f"**Files to modify:** {', '.join(task['files'])}")

    if task.get("acceptance"):
        output.append(f"**Acceptance criteria:** {', '.join(task['acceptance'])}")

    if show_estimate:
        est = estimate_tokens(task, context)
        complexity = estimate_task_complexity(task)
        status = "OK" if est["fits"] else "OVERSIZED"
        output.append(f"\n**Estimate:** ~{est['total']:,} tokens ({est['utilization']}% of {TARGET_TOKENS:,}) [{status}]")
        output.append(f"**Complexity:** {complexity}")

    if context:
        output.append(f"\n## Context\n{context}")

    # Code Simplifier requirement
    output.append("""
## Before Marking Done (REQUIRED)
1. Run acceptance checks (validate)
2. Run code-simplifier on modified files:
   "Use code-simplifier to review and simplify the code I just wrote"
3. Only then mark the task as done
""")

    output.append("=" * 60)
    return "\n".join(output)


def mark_done(tree: dict, path: list[str]) -> bool:
    """Mark a task as done by path."""
    node = tree
    for i, name in enumerate(path[:-1]):
        if i == 0:
            continue
        for child in node.get("children", []):
            if child.get("name") == name:
                node = child
                break

    # Find and mark the leaf
    for child in node.get("children", []):
        if child.get("name") == path[-1]:
            child["status"] = "done"
            return True

    # If it's the root itself
    if node.get("name") == path[-1]:
        node["status"] = "done"
        return True

    return False


def count_tasks(node: dict) -> tuple[int, int]:
    """Count (done, total) tasks."""
    if is_leaf(node):
        done = 1 if get_status(node) == "done" else 0
        return (done, 1)

    done_total = (0, 0)
    for child in node.get("children", []):
        child_counts = count_tasks(child)
        done_total = (done_total[0] + child_counts[0], done_total[1] + child_counts[1])

    return done_total


def print_tree(node: dict, indent: int = 0) -> None:
    """Print tree structure."""
    prefix = "  " * indent
    status = ""

    if is_leaf(node):
        s = get_status(node)
        status = " [x]" if s == "done" else " [ ]" if s == "pending" else f" [{s}]"

    print(f"{prefix}- {node.get('name', 'unnamed')}{status}")

    for child in node.get("children", []):
        print_tree(child, indent + 1)


def cmd_next(use_ai_context: bool = False) -> None:
    """Show next task to execute."""
    tree = load_tree()
    result = find_next_task(tree)

    if not result:
        print("All tasks complete!")
        return

    task, path = result
    context = build_context(tree, path)

    # Optionally enrich with AI context
    if use_ai_context:
        # First, sync index to catch up on changes from other machines
        sync_index_if_needed()

        try:
            from ralph_context import ContextEngine
            engine = ContextEngine()
            if engine.collection.count() > 0:
                ai_context = engine.get_context_for_task(task)
                if ai_context.get("suggested_read_first"):
                    print("=" * 60)
                    print("AI SUGGESTED READ_FIRST (from codebase analysis)")
                    print("=" * 60)
                    for f in ai_context["suggested_read_first"]:
                        print(f"  - {f}")
                    print()
                if ai_context.get("summaries"):
                    print("=" * 60)
                    print("FILE SUMMARIES (large files)")
                    print("=" * 60)
                    for filepath, summary in ai_context["summaries"].items():
                        print(f"\n### {filepath}")
                        print(summary)
                    print()
        except ImportError:
            print("Note: ralph_context.py not available. Run without --ai flag.")
        except Exception as e:
            print(f"Note: AI context unavailable: {e}")

    print(format_task(task, context))


def auto_reindex(silent_if_unavailable: bool = True) -> bool:
    """
    Incrementally update the codebase index.
    Only indexes changed files (fast).

    Args:
        silent_if_unavailable: If True, don't print errors when Ollama/chromadb unavailable

    Returns:
        True if indexing ran successfully, False otherwise
    """
    try:
        from ralph_context import ContextEngine
        engine = ContextEngine()
        print("\nUpdating codebase index...")
        stats = engine.index(force=False)  # Incremental, only changed files
        if stats["indexed"] > 0 or stats["updated"] > 0:
            print(f"  Indexed: {stats['indexed']} new, {stats['updated']} updated")
        else:
            print("  Index up to date")
        return True
    except ImportError:
        if not silent_if_unavailable:
            print("  Index skipped: chromadb/ollama not installed")
        return False
    except Exception as e:
        if not silent_if_unavailable:
            print(f"  Index skipped: {e}")
        return False


def sync_index_if_needed() -> None:
    """
    Check if index needs syncing and update if Ollama is available.
    Called on 'next --ai' to catch up on changes made on other machines.
    """
    try:
        from ralph_context import ContextEngine
        import ollama

        # Quick check if Ollama is running
        try:
            ollama.list()
        except Exception:
            print("Note: Ollama not running. Skipping index sync.")
            return

        engine = ContextEngine()

        # Check if index exists
        if engine.collection.count() == 0:
            print("Index is empty. Run: python ralph_context.py index")
            return

        # Run incremental index to catch up on any changes
        stats = engine.index(force=False)
        if stats["indexed"] > 0 or stats["updated"] > 0:
            print(f"Index synced: {stats['indexed']} new, {stats['updated']} updated files")

    except ImportError:
        pass  # Dependencies not installed, skip silently
    except Exception:
        pass  # Any other error, skip silently


def cmd_sync() -> None:
    """
    Check index status and sync with codebase changes.
    Use this after pulling changes from other machines (e.g., laptop without Ollama).
    """
    try:
        from ralph_context import ContextEngine, CONFIG
        import ollama
    except ImportError:
        print("Dependencies not installed. Run: pip install chromadb ollama")
        return

    # Check if Ollama is running
    print("Checking Ollama status...")
    try:
        models = ollama.list()
        model_names = [m.get('name', m.get('model', 'unknown')) for m in models.get('models', [])]
        print(f"  Ollama running. Models: {', '.join(model_names[:5])}")
    except Exception as e:
        print(f"  Ollama not running: {e}")
        print("  Start Ollama and try again.")
        return

    # Check index status
    print("\nChecking index status...")
    engine = ContextEngine()
    status = engine.status()

    print(f"  Project root: {status['project_root']}")
    print(f"  Indexed files: {status['indexed_files']}")
    print(f"  Total chunks: {status['total_chunks']}")
    print(f"  Embed model: {status['embed_model']}")
    print(f"  Summary model: {status['summary_model']}")

    if status['total_chunks'] == 0:
        print("\n  Index is EMPTY. Running full index...")
        stats = engine.index(force=False)
        print(f"\n  Indexed {stats['indexed']} files ({stats['errors']} errors)")
        return

    # Run incremental sync
    print("\nSyncing index with codebase changes...")
    stats = engine.index(force=False)

    print(f"\n{'='*60}")
    print("SYNC COMPLETE")
    print(f"{'='*60}")
    print(f"  New files indexed: {stats['indexed']}")
    print(f"  Files updated: {stats['updated']}")
    print(f"  Files unchanged: {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Total chunks in DB: {engine.collection.count()}")

    if stats['indexed'] == 0 and stats['updated'] == 0:
        print("\n  Index is UP TO DATE")
    else:
        print(f"\n  Synced {stats['indexed'] + stats['updated']} files from laptop/other machine")


def cmd_done() -> None:
    """Mark current task as done."""
    tree = load_tree()
    result = find_next_task(tree)

    if not result:
        print("No pending tasks.")
        return

    task, path = result
    mark_done(tree, path)
    save_tree(tree)
    print(f"Marked done: {task.get('name')}")

    # Auto-reindex to keep embeddings fresh
    auto_reindex()


def cmd_status() -> None:
    """Show tree status."""
    tree = load_tree()
    done, total = count_tasks(tree)

    print(f"Progress: {done}/{total} tasks complete\n")
    print_tree(tree)


def cmd_add(parent_path: str, task_json: str) -> None:
    """Add a task under a parent path (dot-separated)."""
    tree = load_tree()
    new_task = json.loads(task_json)

    # Navigate to parent
    parts = parent_path.split(".") if parent_path else []
    node = tree

    for part in parts:
        found = False
        for child in node.get("children", []):
            if child.get("name") == part:
                node = child
                found = True
                break
        if not found:
            print(f"Parent not found: {part}")
            return

    if "children" not in node:
        node["children"] = []

    node["children"].append(new_task)
    save_tree(tree)
    print(f"Added: {new_task.get('name')}")


def cmd_prune(task_path: str) -> None:
    """Remove a task by path (dot-separated)."""
    tree = load_tree()
    parts = task_path.split(".")

    if len(parts) == 1:
        print("Cannot prune root.")
        return

    # Navigate to parent of target
    node = tree
    for part in parts[:-1]:
        found = False
        for child in node.get("children", []):
            if child.get("name") == part:
                node = child
                found = True
                break
        if not found:
            print(f"Path not found: {part}")
            return

    # Remove target
    target = parts[-1]
    original_len = len(node.get("children", []))
    node["children"] = [c for c in node.get("children", []) if c.get("name") != target]

    if len(node["children"]) < original_len:
        save_tree(tree)
        print(f"Pruned: {target}")
    else:
        print(f"Not found: {target}")


def cmd_init() -> None:
    """Initialize a new tree."""
    tree = {
        "name": "Project",
        "context": "Describe your project here",
        "children": [
            {
                "name": "Feature 1",
                "context": "Context for this feature",
                "children": [
                    {
                        "name": "First task description",
                        "files": ["src/example.py"],
                        "acceptance": ["pytest passes"],
                        "status": "pending"
                    }
                ]
            }
        ]
    }
    save_tree(tree)

    req = """# Requirements

## Scale
- Define your scale targets here

## Priorities
- What matters most?

## Skip
- What to avoid / prune
"""
    Path(REQUIREMENTS_FILE).write_text(req, encoding="utf-8")

    config = {
        "agent": "claude",
        "agent_cmd": "claude -p",
        "target_tokens": 100000
    }
    Path(CONFIG_FILE).write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Initialized tree.json, requirements.md, and config.json")


def cmd_estimate() -> None:
    """Show token estimates for all pending leaf tasks."""
    tree = load_tree()

    def walk_leaves(node: dict, path: list[str] = None):
        if path is None:
            path = []
        current_path = path + [node.get("name", "unnamed")]

        if is_leaf(node) and get_status(node) == "pending":
            context = build_context(tree, current_path)
            est = estimate_tokens(node, context)
            complexity = estimate_task_complexity(node)
            status = "OK" if est["fits"] else "OVER"
            print(f"[{status:4}] {est['utilization']:5.1f}% | {complexity:6} | {node.get('name', 'unnamed')[:50]}")
            return

        for child in node.get("children", []):
            walk_leaves(child, current_path)

    print(f"{'Status':<6} {'Util':>6} | {'Cmplx':6} | Task")
    print("-" * 70)
    walk_leaves(tree)


def cmd_assign(n: int = 4) -> None:
    """
    Assign N tasks to parallel workers.
    Outputs prompts to copy-paste into worker Claude instances.
    """
    tree = load_tree()
    requirements = load_requirements()
    tasks = find_n_tasks(tree, n)

    if not tasks:
        print("No pending tasks to assign.")
        return

    # Save worker assignments
    workers_data = {"workers": []}

    print("=" * 70)
    print(f"ORCHESTRATOR: Assigning {len(tasks)} tasks to workers")
    print("=" * 70)
    print()

    for i, (task, path) in enumerate(tasks, 1):
        branch = task_to_branch_name(task.get("name", f"task-{i}"))
        context = build_context(tree, path)
        files = task.get("files", [])
        acceptance = task.get("acceptance", [])

        workers_data["workers"].append({
            "id": i,
            "branch": branch,
            "task": task.get("name"),
            "path": ".".join(path),
            "status": "assigned"
        })

        read_first = task.get("read_first", [])
        spec = task.get("spec", "")

        print(f"{'='*70}")
        print(f"WORKER {i} - Copy everything below this line to Terminal {i+1}:")
        print(f"{'='*70}")

        prompt_parts = [f"""
You are Worker {i}. Your job is to complete ONE task on a dedicated branch.

## Setup
```bash
git checkout main
git pull origin main
git checkout -b {branch}
```

## Your Task
{task.get("name")}"""]

        if read_first:
            prompt_parts.append("\n## Read First (MANDATORY)\nBefore coding, read these files:\n" + "\n".join(f"- {f}" for f in read_first))

        if spec:
            prompt_parts.append(f"\n## Spec\n{spec}")

        prompt_parts.append(f"""
## Files to create/modify
{', '.join(files) if files else 'Determine based on task'}

## Acceptance criteria
{chr(10).join(f'- {a}' for a in acceptance) if acceptance else '- Code works and passes type checks'}

## Context
{context}

## Before Marking Done (REQUIRED)
1. Run acceptance checks: {', '.join(acceptance) if acceptance else 'tests pass'}
2. Run code-simplifier:
   "Use code-simplifier to review and simplify the code I just wrote"
3. Commit and push:
```bash
git add -A
git commit -m "{task.get("name")}"
git push -u origin {branch}
```

Then say: "Worker {i} complete. Pushed to {branch}"
""")
        print("".join(prompt_parts))
        print()

    save_workers(workers_data)

    print("=" * 70)
    print("ORCHESTRATOR NOTES:")
    print("=" * 70)
    print(f"""
Workers assigned: {len(tasks)}
Branches: {', '.join(w['branch'] for w in workers_data['workers'])}

When all workers report complete, run:
  python ralph_tree.py merge

To check worker status:
  python ralph_tree.py workers
""")


def cmd_workers() -> None:
    """Show current worker assignments."""
    workers = load_workers()

    if not workers.get("workers"):
        print("No workers currently assigned.")
        print("Run: python ralph_tree.py assign <N>")
        return

    print("=" * 60)
    print("CURRENT WORKER ASSIGNMENTS")
    print("=" * 60)

    for w in workers["workers"]:
        print(f"  Worker {w['id']}: [{w['status']:10}] {w['branch']}")
        print(f"           Task: {w['task'][:50]}")
        print()


def cmd_merge() -> None:
    """Generate merge instructions for orchestrator."""
    workers = load_workers()

    if not workers.get("workers"):
        print("No workers to merge.")
        return

    print("=" * 60)
    print("MERGE INSTRUCTIONS")
    print("=" * 60)
    print("""
For each worker branch, run:
```bash
git checkout main
git pull origin main
git merge <branch-name>
# resolve any conflicts
git push origin main
```

Branches to merge:""")

    for w in workers["workers"]:
        print(f"  git merge {w['branch']}")

    print("""
After merging all branches, run:
  python ralph_tree.py done-all

To mark all assigned tasks as complete.
""")


def cmd_done_all() -> None:
    """Mark all assigned worker tasks as done."""
    tree = load_tree()
    workers = load_workers()

    if not workers.get("workers"):
        print("No workers to complete.")
        return

    count = 0
    for w in workers["workers"]:
        path = w["path"].split(".")
        if mark_done(tree, path):
            count += 1
            print(f"  Marked done: {w['task'][:50]}")

    save_tree(tree)

    # Clear workers
    save_workers({"workers": []})

    print(f"\nCompleted {count} tasks. Workers cleared.")

    # Auto-reindex to keep embeddings fresh
    auto_reindex()


def cmd_validate() -> None:
    """
    Run acceptance criteria for current task.
    QA validation loop - ensures task is truly complete before marking done.
    """
    tree = load_tree()
    result = find_next_task(tree)

    if not result:
        print("No pending tasks to validate.")
        return

    task, path = result
    acceptance = task.get("acceptance", [])

    if not acceptance:
        print(f"Task: {task.get('name')}")
        print("No acceptance criteria defined. Add 'acceptance' field to task.")
        print("\nExample: \"acceptance\": [\"pytest\", \"pyright\", \"ruff check\"]")
        return

    print("=" * 60)
    print(f"VALIDATING: {task.get('name')[:50]}")
    print("=" * 60)

    all_passed = True
    results = []

    for cmd in acceptance:
        print(f"\n$ {cmd}")
        exit_code = os.system(cmd)
        if exit_code != 0:
            print(f"  ✗ FAILED (exit code {exit_code})")
            results.append((cmd, False))
            all_passed = False
        else:
            print(f"  ✓ PASSED")
            results.append((cmd, True))

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL CHECKS PASSED")
        print("\nNow run code-simplifier before marking done:")
        print('  "Use code-simplifier to review and simplify the code I just wrote"')
        print("\nThen mark done:")
        print("  python ralph_tree.py done")
    else:
        print("✗ SOME CHECKS FAILED")
        print("\nFix the issues and run validate again:")
        print("  python ralph_tree.py validate")
        print("\nFailed checks:")
        for cmd, passed in results:
            if not passed:
                print(f"  - {cmd}")
    print("=" * 60)


def cmd_assign_one(worker_id: Optional[int] = None) -> None:
    """
    Assign a single task to one worker.
    Enables rolling pipeline - assign new tasks as workers complete.
    """
    tree = load_tree()
    workers_data = load_workers()

    # Find next pending task
    result = find_next_task(tree)
    if not result:
        print("No pending tasks to assign.")
        return

    task, path = result

    # Determine worker ID
    if worker_id is None:
        existing_ids = [w["id"] for w in workers_data.get("workers", [])]
        worker_id = max(existing_ids, default=0) + 1

    # Check if worker ID already exists
    for w in workers_data.get("workers", []):
        if w["id"] == worker_id:
            print(f"Worker {worker_id} already has an assigned task.")
            print(f"Use 'done-one {worker_id}' first, or choose a different ID.")
            return

    branch = task_to_branch_name(task.get("name", f"task-{worker_id}"))
    context = build_context(tree, path)
    files = task.get("files", [])
    acceptance = task.get("acceptance", [])
    read_first = task.get("read_first", [])
    spec = task.get("spec", "")

    # Add to workers list
    workers_data.setdefault("workers", []).append({
        "id": worker_id,
        "branch": branch,
        "task": task.get("name"),
        "path": ".".join(path),
        "status": "assigned"
    })
    save_workers(workers_data)

    # Output worker prompt
    print(f"{'='*70}")
    print(f"WORKER {worker_id} - Copy everything below this line:")
    print(f"{'='*70}")

    prompt_parts = [f"""
You are Worker {worker_id}. Your job is to complete ONE task on a dedicated branch.

## Setup
```bash
git checkout main
git pull origin main
git checkout -b {branch}
```

## Your Task
{task.get("name")}"""]

    if read_first:
        prompt_parts.append("\n## Read First (MANDATORY)\nBefore coding, read these files:\n" + "\n".join(f"- {f}" for f in read_first))

    if spec:
        prompt_parts.append(f"\n## Spec\n{spec}")

    prompt_parts.append(f"""
## Files to modify
{', '.join(files) if files else 'Determine based on task'}

## Acceptance criteria
{chr(10).join(f'- {a}' for a in acceptance) if acceptance else '- Code works and passes type checks'}

## Context
{context}

## Before Marking Done (REQUIRED)
1. Run acceptance checks: {', '.join(acceptance) if acceptance else 'tests pass'}
2. Run code-simplifier:
   "Use code-simplifier to review and simplify the code I just wrote"
3. Commit and push:
```bash
git add -A
git commit -m "{task.get("name")}"
git push -u origin {branch}
```

Then say: "Worker {worker_id} complete. Pushed to {branch}"
""")

    print("".join(prompt_parts))
    print("=" * 70)
    print(f"Assigned to Worker {worker_id} on branch: {branch}")
    print(f"Active workers: {len(workers_data['workers'])}")
    print("=" * 70)


def cmd_done_one(worker_id: int) -> None:
    """
    Mark a single worker's task as done and remove from workers list.
    Enables rolling pipeline - complete tasks individually as workers finish.
    """
    tree = load_tree()
    workers_data = load_workers()

    if not workers_data.get("workers"):
        print("No workers currently assigned.")
        return

    # Find the worker
    worker = None
    worker_index = None
    for i, w in enumerate(workers_data["workers"]):
        if w["id"] == worker_id:
            worker = w
            worker_index = i
            break

    if worker is None:
        print(f"Worker {worker_id} not found.")
        print("Active workers:", [w["id"] for w in workers_data["workers"]])
        return

    # Mark task as done in tree
    path = worker["path"].split(".")
    if mark_done(tree, path):
        save_tree(tree)
        print(f"✓ Marked done: {worker['task'][:50]}")
    else:
        print(f"Warning: Could not find task in tree: {worker['task'][:50]}")

    # Remove worker from list
    workers_data["workers"].pop(worker_index)
    save_workers(workers_data)

    print(f"""
Merge this branch:
```bash
git checkout main
git pull origin main
git merge {worker['branch']}
git push origin main
git branch -d {worker['branch']}
```

Worker {worker_id} cleared. Remaining workers: {len(workers_data['workers'])}
""")

    if workers_data["workers"]:
        print("Active workers:", [w["id"] for w in workers_data["workers"]])
    else:
        print("All workers complete!")

    # Auto-reindex to keep embeddings fresh
    auto_reindex()


def cmd_enrich() -> None:
    """
    Auto-suggest read_first files for all pending tasks using AI context.
    Uses local Ollama embeddings to find semantically relevant files.
    """
    try:
        from ralph_context import ContextEngine
    except ImportError:
        print("ralph_context.py not found. Make sure it's in the same directory.")
        print("Also install: pip install chromadb ollama")
        return

    tree = load_tree()
    engine = ContextEngine()

    if engine.collection.count() == 0:
        print("Index is empty. Run first: python ralph_context.py index")
        return

    def enrich_node(node: dict, path: list[str] = None):
        """Recursively enrich tasks with suggested read_first."""
        if path is None:
            path = []
        current_path = path + [node.get("name", "unnamed")]

        if is_leaf(node) and get_status(node) == "pending":
            # Only enrich if no read_first specified
            if not node.get("read_first"):
                suggestions = engine.suggest_read_first(
                    node.get("name", ""),
                    node.get("context", ""),
                    top_k=3
                )
                if suggestions:
                    node["read_first"] = suggestions
                    print(f"  + {node.get('name')[:40]}")
                    for f in suggestions:
                        print(f"      - {f}")
            return

        for child in node.get("children", []):
            enrich_node(child, current_path)

    print("Enriching tasks with AI-suggested read_first files...")
    print("=" * 60)
    enrich_node(tree)
    save_tree(tree)
    print("=" * 60)
    print("Done. Review tree.json and adjust as needed.")


def cmd_govern() -> None:
    """
    Output a governance prompt to use with Claude.
    Helps Claude review and adjust the tree (spawn/prune/split tasks).
    """
    tree = load_tree()
    requirements = load_requirements()

    prompt = f"""Review my task tree and requirements. Then update tree.json:

1. Mark tasks DONE if the code already exists
2. PRUNE tasks that violate requirements or aren't needed
3. SPLIT tasks that are too big (should fit in ~{TARGET_TOKENS:,} tokens / ~300 lines)
4. ADD missing tasks you identify

## Requirements
{requirements}

## Current Tree
{json.dumps(tree, indent=2)}

Read my codebase to check what's already done. Edit tree.json directly with your changes."""

    print("=" * 60)
    print("GOVERNANCE PROMPT - Give this to Claude:")
    print("=" * 60)
    print(prompt)
    print("=" * 60)


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("""
ralph-tree - Dynamic task tree for AI agents

Core Commands:
  init              Create tree.json, requirements.md, config.json
  next              Show next task with spec, read_first, and context
  next --ai         Show next task with AI-enriched context (requires index)
  done              Mark current task as done
  validate          Run acceptance checks (QA loop) before marking done
  status            Show tree progress
  estimate          Show token estimates for all pending tasks
  govern            Output governance prompt for Claude

AI Context (requires Ollama + ChromaDB):
  enrich            Auto-suggest read_first for all pending tasks
  sync              Check index status and sync with codebase changes

Tree Management:
  add <path> <json> Add task under parent (dot-separated path)
  prune <path>      Remove task by path

Parallel Workers (Batch):
  assign <N>        Assign N tasks to workers (default: 4)
  workers           Show current worker assignments
  merge             Show merge instructions
  done-all          Mark all assigned tasks done, clear workers

Parallel Workers (Rolling Pipeline):
  assign-one [id]   Assign ONE task to a worker (auto-ID if omitted)
  done-one <id>     Complete ONE worker, show merge instructions

Task Fields:
  name              Task description (required)
  status            pending / in-progress / done / blocked
  spec              Brief spec to lock intent (2-3 sentences)
  read_first        Files to read before coding (ensures consistency)
  files             Files to create/modify
  acceptance        Commands to verify completion (QA loop)
  context           Additional context for this task

AI Context Setup (one-time):
  pip install chromadb ollama
  ollama pull nomic-embed-text
  ollama pull codellama:13b
  python ralph_context.py index      # Index codebase (~2 min)

Workflow (includes code-simplifier):
  python ralph_tree.py next          # Get task
  # Claude reads read_first files, codes to spec
  python ralph_tree.py validate      # Run acceptance checks
  # "Use code-simplifier to review and simplify the code"
  python ralph_tree.py done          # Mark complete

Rolling Pipeline:
  python ralph_tree.py assign-one    # → Worker 1
  python ralph_tree.py assign-one    # → Worker 2
  python ralph_tree.py done-one 1    # Worker 1 finished
  python ralph_tree.py assign-one 1  # Re-assign Worker 1
""")
        return

    cmd = sys.argv[1]

    if cmd == "init":
        cmd_init()
    elif cmd == "next":
        use_ai = "--ai" in sys.argv
        cmd_next(use_ai_context=use_ai)
    elif cmd == "done":
        cmd_done()
    elif cmd == "status":
        cmd_status()
    elif cmd == "estimate":
        cmd_estimate()
    elif cmd == "govern":
        cmd_govern()
    elif cmd == "enrich":
        cmd_enrich()
    elif cmd == "sync":
        cmd_sync()
    elif cmd == "assign":
        n = int(sys.argv[2]) if len(sys.argv) >= 3 else 4
        cmd_assign(n)
    elif cmd == "workers":
        cmd_workers()
    elif cmd == "merge":
        cmd_merge()
    elif cmd == "done-all":
        cmd_done_all()
    elif cmd == "validate":
        cmd_validate()
    elif cmd == "assign-one":
        worker_id = int(sys.argv[2]) if len(sys.argv) >= 3 else None
        cmd_assign_one(worker_id)
    elif cmd == "done-one" and len(sys.argv) >= 3:
        cmd_done_one(int(sys.argv[2]))
    elif cmd == "add" and len(sys.argv) >= 4:
        cmd_add(sys.argv[2], sys.argv[3])
    elif cmd == "prune" and len(sys.argv) >= 3:
        cmd_prune(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
