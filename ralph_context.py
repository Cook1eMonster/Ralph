#!/usr/bin/env python3
"""
ralph_context.py - Local AI-powered context engine for Ralph Tree.

This is a CLI wrapper around ralph.context module.

Uses Ollama + ChromaDB to:
1. Index your codebase with embeddings
2. Find semantically relevant files for any task
3. Summarize large files to fit in context
4. Auto-suggest read_first files

Requirements:
    pip install chromadb ollama

Setup:
    ollama pull nomic-embed-text
    ollama pull qwen2.5-coder:7b
"""

import argparse
import json
import sys
from pathlib import Path

# Import from the ralph package
from ralph.context import (
    CONFIG,
    ContextEngine,
    get_project_root,
    summarize_file,
)


def cmd_index(args):
    """Index the codebase."""
    engine = ContextEngine()
    engine.index(force=args.force, verbose=True)


def cmd_search(args):
    """Search the codebase."""
    engine = ContextEngine()

    if engine.collection.count() == 0:
        print("Index is empty. Run: python ralph_context.py index")
        return

    query = " ".join(args.query)
    print(f"Searching for: {query}\n")

    results = engine.search(query, top_k=args.top)

    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        sim_pct = r["similarity"] * 100
        print(f"{i}. [{sim_pct:.1f}%] {r['filepath']}")
        print(f"   Lines {r['start_line']}-{r['end_line']}")
        if args.verbose:
            snippet = r["snippet"].replace("\n", "\n   ")[:300]
            print(f"   {snippet}...")
        print()


def cmd_suggest(args):
    """Suggest read_first files for a task."""
    engine = ContextEngine()

    if engine.collection.count() == 0:
        print("Index is empty. Run: python ralph_context.py index")
        return

    task_desc = " ".join(args.task)
    print(f"Task: {task_desc}\n")

    suggestions = engine.suggest_read_first(task_desc, top_k=args.top)

    if not suggestions:
        print("No suggestions found.")
        return

    print("Suggested read_first:")
    for filepath in suggestions:
        print(f"  - {filepath}")

    # Output as JSON for piping
    if args.json:
        print(f"\n{json.dumps(suggestions)}")


def cmd_context(args):
    """Get full context for a task (from tree.json or description)."""
    engine = ContextEngine()

    if engine.collection.count() == 0:
        print("Index is empty. Run: python ralph_context.py index")
        return

    # Load task from tree.json or use description
    if args.task:
        task = {"name": " ".join(args.task)}
    else:
        # Try to load current task from ralph_tree
        tree_path = engine.project_root / "tree.json"
        if not tree_path.exists():
            print("No tree.json found. Provide task with --task")
            return

        # Import ralph_tree to get current task
        sys.path.insert(0, str(engine.project_root))
        try:
            from ralph_tree import load_tree, find_next_task
            tree = load_tree()
            result = find_next_task(tree)
            if result:
                task, path = result
            else:
                print("No pending tasks in tree.json")
                return
        except ImportError:
            print("Could not load ralph_tree.py")
            return

    print(f"Getting context for: {task.get('name', 'unknown')}\n")

    context = engine.get_context_for_task(task)

    print("=" * 60)
    print("SUGGESTED READ_FIRST")
    print("=" * 60)
    for f in context["suggested_read_first"]:
        print(f"  - {f}")

    if context["summaries"]:
        print("\n" + "=" * 60)
        print("FILE SUMMARIES (large files)")
        print("=" * 60)
        for filepath, summary in context["summaries"].items():
            print(f"\n### {filepath}")
            print(summary)

    print("\n" + "=" * 60)
    print("RELEVANT FILES")
    print("=" * 60)
    for f in context["relevant_files"]:
        print(f"  - {f}")

    if args.json:
        print(f"\n{json.dumps(context, indent=2)}")


def cmd_summarize(args):
    """Summarize a specific file."""
    engine = ContextEngine()

    filepath = Path(args.file)
    if not filepath.is_absolute():
        filepath = engine.project_root / filepath

    if not filepath.exists():
        print(f"File not found: {filepath}")
        return

    print(f"Summarizing: {filepath}\n")
    summary = summarize_file(filepath)

    if summary:
        print(summary)
    else:
        print("Could not generate summary.")


def cmd_status(args):
    """Show index status."""
    engine = ContextEngine()
    status = engine.status()

    print("Ralph Context Status")
    print("=" * 40)
    for key, value in status.items():
        print(f"  {key}: {value}")


def main():
    parser = argparse.ArgumentParser(
        description="Local AI context engine for Ralph Tree",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ralph_context.py index              # Index codebase (first run)
  python ralph_context.py index --force      # Re-index everything
  python ralph_context.py search auth login  # Find auth-related files
  python ralph_context.py suggest "Add patient scheduling API"
  python ralph_context.py context            # Context for current task
  python ralph_context.py summarize src/services/auth.ts
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Index command
    index_parser = subparsers.add_parser("index", help="Index the codebase")
    index_parser.add_argument("--force", "-f", action="store_true", help="Re-index all files")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search for relevant files")
    search_parser.add_argument("query", nargs="+", help="Search query")
    search_parser.add_argument("--top", "-n", type=int, default=10, help="Number of results")
    search_parser.add_argument("--verbose", "-v", action="store_true", help="Show snippets")

    # Suggest command
    suggest_parser = subparsers.add_parser("suggest", help="Suggest read_first files")
    suggest_parser.add_argument("task", nargs="+", help="Task description")
    suggest_parser.add_argument("--top", "-n", type=int, default=5, help="Number of suggestions")
    suggest_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Context command
    context_parser = subparsers.add_parser("context", help="Get full context for a task")
    context_parser.add_argument("--task", "-t", nargs="+", help="Task description (or uses tree.json)")
    context_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Summarize command
    summarize_parser = subparsers.add_parser("summarize", help="Summarize a file")
    summarize_parser.add_argument("file", help="File to summarize")

    # Status command
    subparsers.add_parser("status", help="Show index status")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "index": cmd_index,
        "search": cmd_search,
        "suggest": cmd_suggest,
        "context": cmd_context,
        "summarize": cmd_summarize,
        "status": cmd_status,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
