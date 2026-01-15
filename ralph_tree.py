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
SLICE_REVIEW_FILE = "slice_review.md"

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


def is_slice(node: dict) -> bool:
    """Check if node is a functional slice (has slice field or name starts with 'Slice')."""
    return node.get("slice") is True or node.get("name", "").lower().startswith("slice")


def get_slice_order(node: dict) -> int:
    """Get slice execution order (lower = earlier)."""
    return node.get("order", 999)


def find_current_slice(tree: dict) -> Optional[dict]:
    """
    Find the current active slice (first non-done slice in order).
    Slices are nodes with slice=True or name starting with 'Slice'.
    """
    slices = []

    def collect_slices(node: dict):
        if is_slice(node):
            slices.append(node)
        for child in node.get("children", []):
            collect_slices(child)

    collect_slices(tree)

    # Sort by order
    slices.sort(key=get_slice_order)

    # Return first non-done slice
    for s in slices:
        if get_status(s) != "done":
            return s

    return None


def get_slice_tasks(slice_node: dict) -> list[dict]:
    """Get all leaf tasks within a slice."""
    tasks = []

    def collect_tasks(node: dict):
        if is_leaf(node):
            tasks.append(node)
        else:
            for child in node.get("children", []):
                collect_tasks(child)

    for child in slice_node.get("children", []):
        collect_tasks(child)

    return tasks


def is_slice_complete(slice_node: dict) -> bool:
    """Check if all tasks in a slice are done."""
    tasks = get_slice_tasks(slice_node)
    return all(get_status(t) == "done" for t in tasks) if tasks else False


def count_slice_progress(slice_node: dict) -> tuple[int, int]:
    """Count (done, total) tasks in a slice."""
    tasks = get_slice_tasks(slice_node)
    done = sum(1 for t in tasks if get_status(t) == "done")
    return (done, len(tasks))


def find_next_task_in_node(node: dict, path: list[str] = None) -> Optional[tuple[dict, list[str]]]:
    """Find next pending leaf task via depth-first traversal within a node."""
    if path is None:
        path = []

    current_path = path + [node.get("name", "unnamed")]

    if is_leaf(node):
        if get_status(node) == "pending":
            return (node, current_path)
        return None

    for child in node.get("children", []):
        result = find_next_task_in_node(child, current_path)
        if result:
            return result

    return None


def find_next_task(tree: dict, path: list[str] = None) -> Optional[tuple[dict, list[str]]]:
    """
    Find next pending task, respecting slice boundaries.
    Only returns tasks from the current active slice.
    If no slices defined, falls back to depth-first traversal.
    """
    # Check if tree uses slices
    current_slice = find_current_slice(tree)

    if current_slice:
        # Find next task within the current slice
        for child in current_slice.get("children", []):
            result = find_next_task_in_node(child, [tree.get("name", "root"), current_slice.get("name", "slice")])
            if result:
                return result
        return None
    else:
        # No slices defined, use traditional depth-first
        return find_next_task_in_node(tree, path)


def find_n_tasks_in_node(node: dict, n: int, path: list[str] = None, found: list = None) -> list:
    """Find up to N pending leaf tasks within a node."""
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
        find_n_tasks_in_node(child, n, current_path, found)
        if len(found) >= n:
            break

    return found


def find_n_tasks(tree: dict, n: int) -> list:
    """
    Find up to N pending tasks, respecting slice boundaries.
    Only returns tasks from the current active slice.
    """
    current_slice = find_current_slice(tree)

    if current_slice:
        found = []
        base_path = [tree.get("name", "root"), current_slice.get("name", "slice")]
        for child in current_slice.get("children", []):
            find_n_tasks_in_node(child, n, base_path, found)
            if len(found) >= n:
                break
        return found
    else:
        return find_n_tasks_in_node(tree, n)


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

    # Check if using slices
    current_slice = find_current_slice(tree)

    if current_slice:
        # Check if slice is complete (no more tasks)
        done, total = count_slice_progress(current_slice)

        if done == total and total > 0:
            print("=" * 60)
            print(f"SLICE COMPLETE: {current_slice.get('name')}")
            print("=" * 60)
            print(f"All {total} tasks in this slice are done!")
            print()
            print("Next steps:")
            print("  1. python ralph_tree.py slice-validate  # Run integration tests")
            print("  2. python ralph_tree.py slice-review    # Strategic review")
            print("  3. python ralph_tree.py slice-done      # Proceed to next slice")
            return

        # Show slice context header
        print("=" * 60)
        print(f"CURRENT SLICE: {current_slice.get('name')}")
        print(f"Progress: {done}/{total} tasks ({done/total*100:.0f}%)" if total > 0 else "Progress: 0/0 tasks")
        print("=" * 60)
        print()

    result = find_next_task(tree)

    if not result:
        if current_slice:
            print("All tasks in current slice complete!")
            print("Run: python ralph_tree.py slice-validate")
        else:
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


# =============================================================================
# FUNCTIONAL SLICE COMMANDS
# =============================================================================

def cmd_slice_status() -> None:
    """
    Show status of all slices and current slice progress.
    """
    tree = load_tree()
    current_slice = find_current_slice(tree)

    # Collect all slices
    slices = []

    def collect_slices(node: dict, path: list[str] = None):
        if path is None:
            path = []
        current_path = path + [node.get("name", "unnamed")]

        if is_slice(node):
            done, total = count_slice_progress(node)
            slices.append({
                "node": node,
                "path": current_path,
                "done": done,
                "total": total,
                "order": get_slice_order(node),
                "status": get_status(node)
            })

        for child in node.get("children", []):
            collect_slices(child, current_path)

    collect_slices(tree)

    if not slices:
        print("No functional slices defined in tree.")
        print("\nTo use slices, add 'slice: true' to branch nodes or name them 'Slice N: ...'")
        print("Example:")
        print("""  {
    "name": "Slice 1: User Authentication",
    "slice": true,
    "order": 1,
    "validation": ["pytest tests/auth/"],
    "children": [...]
  }""")
        return

    # Sort by order
    slices.sort(key=lambda s: s["order"])

    print("=" * 70)
    print("FUNCTIONAL SLICES")
    print("=" * 70)

    for s in slices:
        node = s["node"]
        is_current = current_slice and node.get("name") == current_slice.get("name")
        status_icon = "▶" if is_current else " "

        if s["status"] == "done":
            progress_bar = "[████████████████████] 100%"
        elif s["total"] > 0:
            pct = s["done"] / s["total"]
            filled = int(pct * 20)
            progress_bar = f"[{'█' * filled}{'░' * (20 - filled)}] {pct * 100:.0f}%"
        else:
            progress_bar = "[░░░░░░░░░░░░░░░░░░░░] 0%"

        print(f"{status_icon} {node.get('name')[:50]}")
        print(f"  {progress_bar}  ({s['done']}/{s['total']} tasks)")

        if node.get("validation"):
            print(f"  Validation: {', '.join(node['validation'][:2])}")
        print()

    if current_slice:
        print("=" * 70)
        print(f"CURRENT SLICE: {current_slice.get('name')}")
        print("=" * 70)
        done, total = count_slice_progress(current_slice)
        remaining = total - done
        print(f"  Tasks: {done}/{total} done, {remaining} remaining")

        if remaining == 0:
            print()
            print("  ✓ All tasks complete! Ready for slice validation.")
            print("  Run: python ralph_tree.py slice-validate")
    else:
        print("All slices complete!")


def cmd_slice_validate() -> None:
    """
    Validate the current slice (run slice-level integration tests).
    Called after all tasks in a slice are done.
    """
    tree = load_tree()
    current_slice = find_current_slice(tree)

    if not current_slice:
        print("No active slice to validate.")
        print("All slices may be complete, or no slices defined.")
        return

    # Check if all tasks in slice are done
    done, total = count_slice_progress(current_slice)
    if done < total:
        print(f"Slice not complete: {done}/{total} tasks done")
        print(f"Complete remaining {total - done} tasks first.")
        print("\nRun: python ralph_tree.py next")
        return

    validation = current_slice.get("validation", [])
    slice_name = current_slice.get("name", "unnamed")

    print("=" * 70)
    print(f"VALIDATING SLICE: {slice_name}")
    print("=" * 70)

    if not validation:
        print("No validation criteria defined for this slice.")
        print("\nAdd 'validation' field to the slice:")
        print('  "validation": ["pytest tests/feature/", "npm run test:feature"]')
        print()
        print("Proceeding to slice review...")
        print("Run: python ralph_tree.py slice-review")
        return

    all_passed = True
    results = []

    for cmd in validation:
        print(f"\n$ {cmd}")
        try:
            completed = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for slice validation
            )
            passed = completed.returncode == 0
            output = completed.stdout + completed.stderr
            if passed:
                print(f"  ✓ PASSED")
            else:
                print(f"  ✗ FAILED (exit code {completed.returncode})")
                # Show first few lines of error
                error_lines = output.strip().split("\n")[:10]
                for line in error_lines:
                    print(f"    {line}")
        except subprocess.TimeoutExpired:
            passed = False
            output = "Command timed out after 10 minutes"
            print(f"  ✗ TIMEOUT")
        except Exception as e:
            passed = False
            output = str(e)
            print(f"  ✗ ERROR: {e}")

        results.append((cmd, passed, output))
        if not passed:
            all_passed = False

    print()
    print("=" * 70)

    if all_passed:
        print("✓ SLICE VALIDATION PASSED")
        print("=" * 70)
        print()
        print("Next: Run slice review before proceeding to next slice:")
        print("  python ralph_tree.py slice-review")
    else:
        print("✗ SLICE VALIDATION FAILED")
        print("=" * 70)
        print()
        print("Fix the issues before proceeding to the next slice.")
        print("Failed checks:")
        for cmd, passed, output in results:
            if not passed:
                print(f"  - {cmd}")


def cmd_slice_review() -> None:
    """
    Generate strategic review questions for the completed slice.
    Claude asks 5-10 questions about obstacles, strategy, and next steps.
    """
    tree = load_tree()
    requirements = load_requirements()
    current_slice = find_current_slice(tree)

    if not current_slice:
        print("No active slice to review.")
        return

    slice_name = current_slice.get("name", "unnamed")
    done, total = count_slice_progress(current_slice)

    # Build context for the review prompt
    tasks = get_slice_tasks(current_slice)
    completed_tasks = [t for t in tasks if get_status(t) == "done"]

    # Collect all slices for context
    all_slices = []

    def collect_slices(node: dict):
        if is_slice(node):
            all_slices.append(node)
        for child in node.get("children", []):
            collect_slices(child)

    collect_slices(tree)
    all_slices.sort(key=get_slice_order)

    # Find next slices
    current_order = get_slice_order(current_slice)
    next_slices = [s for s in all_slices if get_slice_order(s) > current_order][:3]

    print("=" * 70)
    print(f"SLICE REVIEW: {slice_name}")
    print("=" * 70)
    print(f"Tasks completed: {done}/{total}")
    print()

    # Generate the review prompt for Claude
    review_prompt = f"""# Slice Review: {slice_name}

You just completed a functional slice. Before proceeding, review progress and strategy.

## Completed in this Slice
{chr(10).join(f"- {t.get('name')}" for t in completed_tasks)}

## Project Requirements
{requirements if requirements else "(No requirements.md found)"}

## Upcoming Slices
{chr(10).join(f"- {s.get('name')}" for s in next_slices) if next_slices else "This is the final slice."}

---

## REVIEW QUESTIONS

Answer these questions with the user before proceeding:

### Progress Assessment
1. Did the implementation match the original intent? Any deviations?
2. What technical debt was introduced (if any)?
3. Are there any edge cases or error handling gaps?

### Obstacles Identified
4. What unexpected challenges came up during this slice?
5. Are there any blockers for the next slice?

### Strategy Reassessment
6. Based on what we learned, should any upcoming tasks be:
   - **Split** into smaller pieces?
   - **Merged** together?
   - **Pruned** entirely?
   - **Reordered** for dependencies?

7. Are the acceptance criteria for upcoming slices still appropriate?

### User Input Needed
8. Any requirements that need clarification before continuing?
9. Any new features to add or scope changes?
10. Ready to proceed to the next slice?

---

After discussing, run:
  python ralph_tree.py slice-done    # Mark slice complete, proceed to next
"""

    print(review_prompt)

    # Also save to file for reference
    review_file = Path(SLICE_REVIEW_FILE)
    review_file.write_text(review_prompt, encoding="utf-8")
    print("=" * 70)
    print(f"Review saved to: {SLICE_REVIEW_FILE}")
    print()
    print("Discuss the questions above, then:")
    print("  python ralph_tree.py slice-done    # Complete slice, proceed to next")


def cmd_slice_done() -> None:
    """
    Mark the current slice as done and proceed to the next.
    """
    tree = load_tree()
    current_slice = find_current_slice(tree)

    if not current_slice:
        print("No active slice to complete.")
        return

    slice_name = current_slice.get("name", "unnamed")
    done, total = count_slice_progress(current_slice)

    if done < total:
        print(f"Warning: {total - done} tasks still pending in this slice.")
        print("Complete all tasks before marking the slice done.")
        print("\nRun: python ralph_tree.py next")
        return

    # Mark the slice as done
    current_slice["status"] = "done"
    save_tree(tree)

    print("=" * 70)
    print(f"✓ SLICE COMPLETE: {slice_name}")
    print("=" * 70)

    # Find next slice
    next_slice = find_current_slice(tree)

    if next_slice:
        next_done, next_total = count_slice_progress(next_slice)
        print(f"\nNEXT SLICE: {next_slice.get('name')}")
        print(f"  Tasks: {next_total} ({next_done} already done)")

        if next_slice.get("context"):
            print(f"\n  Context: {next_slice.get('context')[:200]}")

        print()
        print("Start working on the next slice:")
        print("  python ralph_tree.py next")
    else:
        print("\n🎉 ALL SLICES COMPLETE!")
        print()
        print("Project appears to be done. Verify with:")
        print("  python ralph_tree.py status")

    # Auto-reindex
    auto_reindex()


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



# =============================================================================
# SUBAGENT EXECUTION - Fresh context execution inspired by get-shit-done
# =============================================================================

EXECUTION_LOG_FILE = "execution.log"


def build_subagent_prompt(task: dict, path: list[str], tree: dict) -> str:
    """
    Build a focused prompt for a fresh subagent.
    Only includes essential context to maximize effective token usage.
    """
    context = build_context(tree, path)
    read_first = task.get("read_first", [])
    spec = task.get("spec", "")
    files = task.get("files", [])
    acceptance = task.get("acceptance", [])

    prompt_parts = [
        "<task>",
        f"  <name>{task.get('name', 'unnamed')}</name>",
    ]

    if spec:
        prompt_parts.append(f"  <spec>{spec}</spec>")

    prompt_parts.append("</task>")
    prompt_parts.append("")

    if read_first:
        prompt_parts.append("<read_first>")
        prompt_parts.append("MANDATORY: Read these files BEFORE writing any code to understand existing patterns:")
        for f in read_first:
            prompt_parts.append(f"  - {f}")
        prompt_parts.append("</read_first>")
        prompt_parts.append("")

    if files:
        prompt_parts.append("<files_to_modify>")
        for f in files:
            prompt_parts.append(f"  - {f}")
        prompt_parts.append("</files_to_modify>")
        prompt_parts.append("")

    if acceptance:
        prompt_parts.append("<acceptance_criteria>")
        prompt_parts.append("ALL of these must pass before task is complete:")
        for a in acceptance:
            prompt_parts.append(f"  - {a}")
        prompt_parts.append("</acceptance_criteria>")
        prompt_parts.append("")

    if context:
        prompt_parts.append("<context>")
        prompt_parts.append(context)
        prompt_parts.append("</context>")
        prompt_parts.append("")

    prompt_parts.append("<instructions>")
    prompt_parts.append("1. Read ALL files listed in read_first to understand existing patterns")
    prompt_parts.append("2. Implement the task according to the spec")
    prompt_parts.append("3. Follow existing code conventions and patterns exactly")
    prompt_parts.append("4. Run acceptance criteria commands to verify your work")
    prompt_parts.append("5. If all checks pass, commit your changes:")
    prompt_parts.append("   git add -A && git commit -m \"" + task.get('name', 'task')[:50] + "\"")
    prompt_parts.append("6. When complete, output: TASK_COMPLETE")
    prompt_parts.append("7. If blocked, output: TASK_BLOCKED: <reason>")
    prompt_parts.append("</instructions>")

    return "\n".join(prompt_parts)


def spawn_subagent(prompt: str, branch: Optional[str] = None, worker_id: int = 1,
                   wait: bool = True, verbose: bool = False) -> dict:
    """
    Spawn a Claude Code subagent with fresh context.
    """
    config = load_config()
    agent_cmd = config.get("agent_cmd", "claude -p")

    result = {
        "worker_id": worker_id,
        "branch": branch,
        "status": "unknown",
        "output": "",
        "exit_code": -1
    }

    # Setup git branch if specified
    if branch:
        try:
            branch_check = subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                capture_output=True, text=True
            )
            if branch_check.returncode != 0:
                subprocess.run(["git", "checkout", "main"], capture_output=True)
                subprocess.run(["git", "pull", "origin", "main"], capture_output=True)
                subprocess.run(["git", "checkout", "-b", branch], capture_output=True)
                print(f"  Created branch: {branch}")
            else:
                subprocess.run(["git", "checkout", branch], capture_output=True)
                print(f"  Switched to branch: {branch}")
        except Exception as e:
            print(f"  Warning: Git branch setup failed: {e}")

    cmd_parts = agent_cmd.split()

    try:
        if verbose:
            print(f"\n{'='*60}")
            print(f"SUBAGENT {worker_id} OUTPUT:")
            print(f"{'='*60}\n")

            process = subprocess.Popen(
                cmd_parts + [prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            output_lines = []
            for line in iter(process.stdout.readline, ''):
                print(line, end='')
                output_lines.append(line)

            process.wait()
            result["output"] = "".join(output_lines)
            result["exit_code"] = process.returncode

        elif wait:
            completed = subprocess.run(
                cmd_parts + [prompt],
                capture_output=True,
                text=True,
                timeout=3600
            )
            result["output"] = completed.stdout + completed.stderr
            result["exit_code"] = completed.returncode

        else:
            process = subprocess.Popen(
                cmd_parts + [prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            result["pid"] = process.pid
            result["status"] = "running"
            result["exit_code"] = 0
            return result

        if "TASK_COMPLETE" in result["output"]:
            result["status"] = "complete"
        elif "TASK_BLOCKED" in result["output"]:
            result["status"] = "blocked"
        elif result["exit_code"] == 0:
            result["status"] = "complete"
        else:
            result["status"] = "failed"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["output"] = "Subagent timed out after 1 hour"
    except FileNotFoundError:
        result["status"] = "error"
        result["output"] = f"Agent command not found: {agent_cmd}"
    except Exception as e:
        result["status"] = "error"
        result["output"] = str(e)

    log_entry = f"Worker {worker_id} | Branch: {branch} | Status: {result['status']}\n"
    with open(EXECUTION_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)

    return result


def run_validation(acceptance: list[str]) -> tuple[bool, list[tuple[str, bool, str]]]:
    """
    Run acceptance criteria commands.
    Returns (all_passed, results) where results is list of (cmd, passed, output).
    """
    results = []
    all_passed = True

    for cmd in acceptance:
        try:
            completed = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per check
            )
            passed = completed.returncode == 0
            output = completed.stdout + completed.stderr
        except subprocess.TimeoutExpired:
            passed = False
            output = "Command timed out after 5 minutes"
        except Exception as e:
            passed = False
            output = str(e)

        results.append((cmd, passed, output))
        if not passed:
            all_passed = False

    return all_passed, results


def build_fix_prompt(task: dict, validation_results: list[tuple[str, bool, str]], attempt: int) -> str:
    """
    Build a prompt for a subagent to fix validation failures.
    Includes the error output so the agent knows what to fix.
    """
    prompt_parts = [
        "<fix_request>",
        f"  <task>{task.get('name', 'unnamed')}</task>",
        f"  <attempt>{attempt}</attempt>",
        "</fix_request>",
        "",
        "<validation_failures>",
        "The following acceptance criteria checks FAILED. Fix all issues:",
        ""
    ]

    for cmd, passed, output in validation_results:
        if not passed:
            prompt_parts.append(f"<failed_check>")
            prompt_parts.append(f"  <command>{cmd}</command>")
            prompt_parts.append(f"  <output>")
            # Truncate very long outputs but keep enough for context
            truncated_output = output[:8000] if len(output) > 8000 else output
            prompt_parts.append(truncated_output)
            prompt_parts.append(f"  </output>")
            prompt_parts.append(f"</failed_check>")
            prompt_parts.append("")

    prompt_parts.append("</validation_failures>")
    prompt_parts.append("")

    files = task.get("files", [])
    if files:
        prompt_parts.append("<files_to_check>")
        for f in files:
            prompt_parts.append(f"  - {f}")
        prompt_parts.append("</files_to_check>")
        prompt_parts.append("")

    prompt_parts.append("<instructions>")
    prompt_parts.append("1. Read the error output carefully to understand what failed")
    prompt_parts.append("2. Read the relevant files that need fixing")
    prompt_parts.append("3. Make the minimal changes needed to fix the errors")
    prompt_parts.append("4. Do NOT refactor or change unrelated code")
    prompt_parts.append("5. After fixing, commit your changes:")
    prompt_parts.append(f"   git add -A && git commit -m \"fix: {task.get('name', 'task')[:40]} (attempt {attempt})\"")
    prompt_parts.append("6. When complete, output: TASK_COMPLETE")
    prompt_parts.append("7. If you cannot fix it, output: TASK_BLOCKED: <reason>")
    prompt_parts.append("</instructions>")

    return "\n".join(prompt_parts)


def auto_merge_branch(branch: str, delete_after: bool = True) -> bool:
    """
    Merge a branch back to main and optionally delete it.
    Returns True if merge succeeded.
    """
    try:
        # Stash any uncommitted changes
        subprocess.run(["git", "stash"], capture_output=True)

        # Switch to main and pull latest
        result = subprocess.run(["git", "checkout", "main"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  Failed to checkout main: {result.stderr}")
            return False

        subprocess.run(["git", "pull", "origin", "main"], capture_output=True)

        # Merge the branch
        result = subprocess.run(["git", "merge", branch, "--no-edit"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  Merge conflict or error: {result.stderr}")
            # Try to abort merge
            subprocess.run(["git", "merge", "--abort"], capture_output=True)
            subprocess.run(["git", "checkout", branch], capture_output=True)
            return False

        # Push to remote
        result = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  Warning: Push failed: {result.stderr}")

        # Delete branch if requested
        if delete_after:
            subprocess.run(["git", "branch", "-d", branch], capture_output=True)
            subprocess.run(["git", "push", "origin", "--delete", branch], capture_output=True)

        print(f"  Merged {branch} into main")
        return True

    except Exception as e:
        print(f"  Merge error: {e}")
        return False


MAX_FIX_ATTEMPTS = 3  # Maximum number of fix attempts before giving up


def cmd_execute(verbose: bool = False, auto_done: bool = False, auto_merge: bool = False, max_retries: int = MAX_FIX_ATTEMPTS) -> None:
    """
    Execute the next task using a fresh Claude subagent.
    Spawns a new Claude Code process with only essential context.
    If validation fails, spawns fix subagents to automatically resolve issues.
    """
    tree = load_tree()
    result = find_next_task(tree)

    if not result:
        print("No pending tasks to execute.")
        return

    task, path = result
    branch = task_to_branch_name(task.get("name", "task"))

    print("=" * 70)
    print("SUBAGENT EXECUTION")
    print("=" * 70)
    print(f"Task: {task.get('name')}")
    print(f"Branch: {branch}")
    print(f"Mode: {'verbose (streaming)' if verbose else 'quiet (wait for completion)'}")
    print(f"Max fix attempts: {max_retries}")
    print("=" * 70)

    prompt = build_subagent_prompt(task, path, tree)
    prompt_tokens = int(len(prompt) * TOKENS_PER_CHAR)
    print(f"Prompt size: ~{prompt_tokens:,} tokens")
    print(f"Available for work: ~{TARGET_TOKENS - prompt_tokens:,} tokens")
    print()

    task["status"] = "in-progress"
    save_tree(tree)

    print("Spawning subagent with fresh context...")
    exec_result = spawn_subagent(
        prompt=prompt,
        branch=branch,
        worker_id=1,
        wait=True,
        verbose=verbose
    )

    print()
    print("=" * 70)
    print(f"EXECUTION RESULT: {exec_result['status'].upper()}")
    print("=" * 70)

    if exec_result["status"] == "complete":
        print("Subagent completed successfully!")

        # Auto-validate if acceptance criteria defined
        acceptance = task.get("acceptance", [])
        validation_passed = True
        validation_results = []

        if acceptance:
            print()
            print("Running validation...")
            validation_passed, validation_results = run_validation(acceptance)
            for cmd, passed, output in validation_results:
                status = "PASS" if passed else "FAIL"
                print(f"  [{status}] {cmd}")

            # If validation failed, spawn fix subagents
            fix_attempt = 0
            while not validation_passed and fix_attempt < max_retries:
                fix_attempt += 1
                print()
                print("=" * 70)
                print(f"FIX ATTEMPT {fix_attempt}/{max_retries}")
                print("=" * 70)

                # Build fix prompt with error details
                fix_prompt = build_fix_prompt(task, validation_results, fix_attempt)
                fix_tokens = int(len(fix_prompt) * TOKENS_PER_CHAR)
                print(f"Fix prompt size: ~{fix_tokens:,} tokens")

                print("Spawning fix subagent...")
                fix_result = spawn_subagent(
                    prompt=fix_prompt,
                    branch=branch,  # Stay on same branch
                    worker_id=1,
                    wait=True,
                    verbose=verbose
                )

                if fix_result["status"] == "blocked":
                    print("Fix subagent reported blocked - cannot auto-fix")
                    if "TASK_BLOCKED:" in fix_result["output"]:
                        reason = fix_result["output"].split("TASK_BLOCKED:")[-1].strip()[:200]
                        print(f"Reason: {reason}")
                    break

                if fix_result["status"] != "complete":
                    print(f"Fix subagent failed: {fix_result['status']}")
                    continue

                # Re-run validation
                print()
                print("Re-running validation...")
                validation_passed, validation_results = run_validation(acceptance)
                for cmd, passed, output in validation_results:
                    status = "PASS" if passed else "FAIL"
                    print(f"  [{status}] {cmd}")

            if not validation_passed:
                print()
                print("=" * 70)
                print(f"VALIDATION FAILED after {fix_attempt} fix attempt(s)")
                print("=" * 70)
                print("Task NOT marked done. Manual intervention required.")
                print(f"Branch: {branch}")
                print()
                print("Failed checks:")
                for cmd, passed, output in validation_results:
                    if not passed:
                        print(f"  - {cmd}")
                task["status"] = "pending"
                save_tree(tree)
                return

            print()
            print("=" * 70)
            if fix_attempt > 0:
                print(f"VALIDATION PASSED after {fix_attempt} fix attempt(s)")
            else:
                print("VALIDATION PASSED")
            print("=" * 70)

        if auto_done:
            mark_done(tree, path)
            save_tree(tree)
            print(f"Task marked as done: {task.get('name')}")

            # Auto-merge if requested
            if auto_merge:
                print()
                print("Merging to main...")
                if auto_merge_branch(branch):
                    print("Branch merged and cleaned up.")
                else:
                    print("Auto-merge failed. Manual merge required.")

            auto_reindex()
        else:
            print()
            print("Next steps:")
            print("  1. Review the changes on branch:", branch)
            print("  2. Run: python ralph_tree.py validate")
            print("  3. Run: python ralph_tree.py done")

    elif exec_result["status"] == "blocked":
        print("Subagent reported blocked.")
        task["status"] = "blocked"
        save_tree(tree)
        if "TASK_BLOCKED:" in exec_result["output"]:
            reason = exec_result["output"].split("TASK_BLOCKED:")[-1].strip()[:200]
            print(f"Reason: {reason}")

    elif exec_result["status"] == "failed":
        print("Subagent failed.")
        task["status"] = "pending"
        save_tree(tree)
        print(f"Exit code: {exec_result['exit_code']}")
        if not verbose:
            print("Run with --verbose to see full output")

    elif exec_result["status"] == "timeout":
        print("Subagent timed out (1 hour limit).")
        task["status"] = "pending"
        save_tree(tree)

    elif exec_result["status"] == "error":
        print(f"Error: {exec_result['output']}")
        task["status"] = "pending"
        save_tree(tree)


def cmd_execute_parallel(n: int = 4, verbose: bool = False, auto_merge: bool = False) -> None:
    """
    Execute N tasks in parallel using fresh Claude subagents.
    Each subagent runs on its own git branch with isolated context.
    """
    import concurrent.futures
    import threading

    tree = load_tree()
    tasks = find_n_tasks(tree, n)

    if not tasks:
        print("No pending tasks to execute.")
        return

    print("=" * 70)
    print(f"PARALLEL EXECUTION: {len(tasks)} workers")
    print("=" * 70)

    workers = []
    for i, (task, path) in enumerate(tasks, 1):
        branch = task_to_branch_name(task.get("name", f"task-{i}"))
        prompt = build_subagent_prompt(task, path, tree)

        workers.append({
            "id": i,
            "task": task,
            "path": path,
            "branch": branch,
            "prompt": prompt
        })

        print(f"  Worker {i}: {task.get('name')[:50]}")
        print(f"           Branch: {branch}")
        task["status"] = "in-progress"

    save_tree(tree)

    workers_data = {
        "workers": [
            {
                "id": w["id"],
                "branch": w["branch"],
                "task": w["task"].get("name"),
                "path": ".".join(w["path"]),
                "status": "running"
            }
            for w in workers
        ]
    }
    save_workers(workers_data)

    print()
    print("=" * 70)
    print("SPAWNING SUBAGENTS...")
    print("=" * 70)

    def execute_worker(worker: dict) -> dict:
        result = spawn_subagent(
            prompt=worker["prompt"],
            branch=worker["branch"],
            worker_id=worker["id"],
            wait=True,
            verbose=False
        )
        result["task_name"] = worker["task"].get("name")
        result["path"] = worker["path"]
        return result

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as executor:
        future_to_worker = {
            executor.submit(execute_worker, w): w
            for w in workers
        }

        for future in concurrent.futures.as_completed(future_to_worker):
            worker = future_to_worker[future]
            try:
                result = future.result()
                results.append(result)
                print(f"  Worker {result['worker_id']} finished: {result['status']}")
            except Exception as e:
                print(f"  Worker {worker['id']} error: {e}")
                results.append({
                    "worker_id": worker["id"],
                    "status": "error",
                    "output": str(e),
                    "task_name": worker["task"].get("name"),
                    "path": worker["path"],
                    "branch": worker["branch"]
                })

    print()
    print("=" * 70)
    print("EXECUTION RESULTS")
    print("=" * 70)

    completed = 0
    failed = 0
    blocked = 0

    tree = load_tree()

    for result in results:
        status_icon = {
            "complete": "OK",
            "failed": "FAIL",
            "blocked": "BLOCK",
            "error": "ERR",
            "timeout": "TIME"
        }.get(result["status"], "?")

        print(f"  [{status_icon}] Worker {result['worker_id']}: {result['status']}")
        print(f"        Task: {result.get('task_name', 'unknown')[:50]}")
        print(f"        Branch: {result.get('branch', 'unknown')}")

        if result["status"] == "complete":
            mark_done(tree, result["path"])
            completed += 1
            if auto_merge:
                if auto_merge_branch(result["branch"]):
                    print(f"        Merged to main")
        elif result["status"] == "blocked":
            blocked += 1
        else:
            failed += 1
        print()

    save_tree(tree)

    workers_data = load_workers()
    for w in workers_data.get("workers", []):
        for r in results:
            if w["id"] == r["worker_id"]:
                w["status"] = r["status"]
    save_workers(workers_data)

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Completed: {completed}")
    print(f"  Failed: {failed}")
    print(f"  Blocked: {blocked}")
    print()

    if completed > 0:
        print("Completed branches to merge:")
        for r in results:
            if r["status"] == "complete":
                print(f"  git merge {r['branch']}")
        print()
        print("Run 'python ralph_tree.py merge' for full merge instructions.")

    if failed > 0 or blocked > 0:
        print()
        print("Failed/blocked tasks reset to pending for retry.")

    auto_reindex()


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

Functional Slices (vertical feature slices):
  slices            Show all slices and current slice progress
  slice-validate    Run slice integration tests (after all tasks done)
  slice-review      Generate 5-10 strategic review questions
  slice-done        Mark slice complete, proceed to next slice

  Slice Workflow:
    1. Complete all tasks in current slice
    2. slice-validate   # Run integration tests
    3. slice-review     # Discuss strategy with user
    4. slice-done       # Proceed to next slice

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

Autonomous Execution (spawns fresh subagents):
  execute           Execute next task with fresh Claude subagent
  execute --verbose Stream subagent output in real-time
  execute --auto    Auto-validate, mark done, reindex if successful
  execute --merge   Auto-merge branch to main after completion
  execute --retries N  Max fix attempts if validation fails (default: 3)
  execute-parallel <N>  Execute N tasks in parallel (default: 4)
  execute-parallel --merge  Auto-merge all completed branches

Task Fields:
  name              Task description (required)
  status            pending / in-progress / done / blocked
  spec              Brief spec to lock intent (2-3 sentences)
  read_first        Files to read before coding (ensures consistency)
  files             Files to create/modify
  acceptance        Commands to verify completion (QA loop)
  context           Additional context for this task

Slice Fields (for slice nodes):
  slice             true (marks node as a functional slice)
  order             Execution order (lower = earlier)
  validation        Slice-level integration tests
  dependencies      Other slices this depends on

Example tree.json with slices:
  {
    "name": "Project",
    "children": [
      {
        "name": "Slice 1: User Auth",
        "slice": true,
        "order": 1,
        "validation": ["pytest tests/auth/"],
        "children": [
          {"name": "Create User model", "status": "pending"},
          {"name": "Add login endpoint", "status": "pending"}
        ]
      }
    ]
  }

Slice Workflow:
  python ralph_tree.py slices         # See slice progress
  python ralph_tree.py next           # Get next task (within current slice)
  # ... complete all tasks in slice ...
  python ralph_tree.py slice-validate # Run integration tests
  python ralph_tree.py slice-review   # Review strategy
  python ralph_tree.py slice-done     # Move to next slice
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
    elif cmd == "execute":
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        auto_done = "--auto" in sys.argv
        auto_merge = "--merge" in sys.argv
        # Parse --retries N
        max_retries = MAX_FIX_ATTEMPTS
        for i, arg in enumerate(sys.argv):
            if arg == "--retries" and i + 1 < len(sys.argv):
                try:
                    max_retries = int(sys.argv[i + 1])
                except ValueError:
                    pass
        cmd_execute(verbose=verbose, auto_done=auto_done, auto_merge=auto_merge, max_retries=max_retries)
    elif cmd == "execute-parallel":
        n = 4
        for arg in sys.argv[2:]:
            if arg.isdigit():
                n = int(arg)
                break
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        auto_merge = "--merge" in sys.argv
        cmd_execute_parallel(n=n, verbose=verbose, auto_merge=auto_merge)
    # Slice commands
    elif cmd == "slices":
        cmd_slice_status()
    elif cmd == "slice-status":
        cmd_slice_status()
    elif cmd == "slice-validate":
        cmd_slice_validate()
    elif cmd == "slice-review":
        cmd_slice_review()
    elif cmd == "slice-done":
        cmd_slice_done()
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
