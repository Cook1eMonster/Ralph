#!/usr/bin/env python3
"""
ralph_proactive_mcp.py - Automatic MCP integration in Ralph workflows.

Instead of:
    - Claude must remember to call MCP
    - Manual search for each task

Do:
    - Ralph automatically searches MCP before spawning
    - Prompt includes pre-fetched relevant files
    - Claude sees context immediately

Result: No missed context, faster execution.
"""

from pathlib import Path
from typing import Dict, List
from ralph_context import ContextEngine


def auto_fetch_mcp_context(
    task: Dict,
    project_root: Path = None
) -> Dict:
    """
    Automatically fetch MCP context for a task.

    This runs BEFORE spawning a Claude subagent, so Claude
    receives enriched context immediately.

    Returns:
        {
            "suggested_files": [...],
            "file_summaries": {...},
            "similar_implementations": [...],
            "related_patterns": [...]
        }
    """
    engine = ContextEngine(project_root)

    # Check if index exists
    if engine.collection.count() == 0:
        return {
            "suggested_files": [],
            "file_summaries": {},
            "similar_implementations": [],
            "note": "MCP index empty. Run: python ralph_context.py index"
        }

    task_name = task.get("name", "")
    task_context = task.get("context", "")
    existing_files = task.get("files", [])

    context = {
        "suggested_files": [],
        "file_summaries": {},
        "similar_implementations": [],
        "related_patterns": []
    }

    # 1. Find similar implementations
    similar_query = f"{task_name} implementation example"
    similar_results = engine.search(similar_query, top_k=5)
    context["similar_implementations"] = [
        {
            "filepath": r["filepath"],
            "similarity": f"{r['similarity']*100:.0f}%",
            "snippet": r["snippet"][:200]
        }
        for r in similar_results
    ]

    # 2. Suggest additional files to read
    full_context = engine.get_context_for_task(task)
    context["suggested_files"] = full_context.get("suggested_read_first", [])
    context["file_summaries"] = full_context.get("summaries", {})

    # 3. Find related patterns by searching for technical terms
    # Extract key terms from task name
    tech_terms = extract_technical_terms(task_name)
    for term in tech_terms[:3]:
        results = engine.search(term, top_k=3)
        for r in results:
            if r["filepath"] not in existing_files:
                context["related_patterns"].append({
                    "term": term,
                    "filepath": r["filepath"],
                    "relevance": f"{r['similarity']*100:.0f}%"
                })

    return context


def extract_technical_terms(text: str) -> List[str]:
    """
    Extract technical terms from task description.

    "Add user login endpoint with JWT validation"
    → ["login", "JWT", "endpoint", "validation"]
    """
    # Common technical keywords
    keywords = [
        "api", "endpoint", "auth", "login", "logout", "jwt", "token",
        "database", "query", "crud", "create", "read", "update", "delete",
        "model", "schema", "validation", "error", "middleware",
        "component", "route", "controller", "service", "repository",
        "test", "mock", "fixture", "integration", "unit"
    ]

    words = text.lower().split()
    found = []

    for word in words:
        # Remove punctuation
        clean = word.strip(".,;:!?()")
        if clean in keywords and clean not in found:
            found.append(clean)

    # Also extract capitalized words (likely technical: JWT, API, etc.)
    for word in text.split():
        if word.isupper() and len(word) > 1 and word not in found:
            found.append(word)

    return found[:5]  # Top 5 terms


def build_prompt_with_mcp(
    task: Dict,
    base_prompt: str,
    mcp_context: Dict
) -> str:
    """
    Enhance prompt with pre-fetched MCP results.

    Claude no longer needs to call MCP - it's already done.
    """
    if not mcp_context or mcp_context.get("note"):
        # MCP unavailable
        return base_prompt

    sections = []

    # Similar implementations
    if mcp_context.get("similar_implementations"):
        sections.append("<similar_implementations>")
        sections.append("These files contain similar implementations:")
        sections.append("")
        for impl in mcp_context["similar_implementations"][:3]:
            sections.append(f"### {impl['filepath']} (similarity: {impl['similarity']})")
            sections.append(f"```\n{impl['snippet']}\n```")
            sections.append("")
        sections.append("</similar_implementations>")
        sections.append("")

    # Suggested files
    if mcp_context.get("suggested_files"):
        sections.append("<mcp_suggested_files>")
        sections.append("MCP suggests reading these files (semantically related):")
        for f in mcp_context["suggested_files"][:5]:
            sections.append(f"  - {f}")
        sections.append("</mcp_suggested_files>")
        sections.append("")

    # File summaries
    if mcp_context.get("file_summaries"):
        sections.append("<mcp_file_summaries>")
        sections.append("AI-generated summaries of large relevant files:")
        sections.append("")
        for filepath, summary in mcp_context["file_summaries"].items():
            sections.append(f"### {filepath}")
            sections.append(summary)
            sections.append("")
        sections.append("</mcp_file_summaries>")
        sections.append("")

    # Related patterns
    if mcp_context.get("related_patterns"):
        sections.append("<mcp_related_patterns>")
        sections.append("Files related to key technical terms in your task:")
        sections.append("")
        for p in mcp_context["related_patterns"][:5]:
            sections.append(f"  - {p['filepath']} (relates to '{p['term']}', {p['relevance']})")
        sections.append("</mcp_related_patterns>")
        sections.append("")

    mcp_section = "\n".join(sections)

    # Insert MCP context before instructions
    if "<instructions>" in base_prompt:
        parts = base_prompt.split("<instructions>")
        return parts[0] + mcp_section + "<instructions>" + parts[1]
    else:
        return base_prompt + mcp_section


# Integration with ralph_tree.py:
"""
# In build_subagent_prompt():
def build_subagent_prompt(task, path, tree):
    from ralph_proactive_mcp import auto_fetch_mcp_context, build_prompt_with_mcp

    # Build base prompt
    base_prompt = ... # existing logic

    # Auto-fetch MCP context
    print("  Fetching MCP context...")
    mcp_context = auto_fetch_mcp_context(task, project_root=Path.cwd())

    if mcp_context.get("suggested_files"):
        print(f"    MCP suggested {len(mcp_context['suggested_files'])} files")
    if mcp_context.get("similar_implementations"):
        print(f"    Found {len(mcp_context['similar_implementations'])} similar implementations")

    # Enhance prompt with MCP results
    enhanced_prompt = build_prompt_with_mcp(task, base_prompt, mcp_context)

    return enhanced_prompt
"""


def mcp_pre_validate(
    task: Dict,
    project_root: Path = None
) -> List[str]:
    """
    Use MCP to find potential issues BEFORE implementation.

    Searches for:
    - Similar tasks that had validation failures
    - Common error patterns related to this task type
    - Files that often need updates together

    Returns: List of warnings/tips
    """
    engine = ContextEngine(project_root)

    if engine.collection.count() == 0:
        return []

    warnings = []
    task_name = task.get("name", "")

    # Search for error-related files
    error_terms = extract_technical_terms(task_name)
    for term in error_terms:
        error_query = f"{term} error handling validation"
        results = engine.search(error_query, top_k=3)

        for r in results:
            if r["similarity"] > 0.4:
                warnings.append(
                    f"Consider error handling in {r['filepath']} (similar tasks use this pattern)"
                )

    # Check for common co-modifications
    files = task.get("files", [])
    if files and len(files) == 1:
        # Single file - search for commonly modified together
        query = f"{files[0]} imports dependencies"
        results = engine.search(query, top_k=5)

        related_files = [r["filepath"] for r in results if r["filepath"] != files[0]]
        if related_files:
            warnings.append(
                f"This task modifies {files[0]}. Similar changes also modified: "
                f"{', '.join(related_files[:3])}"
            )

    return warnings[:5]  # Max 5 warnings


# Usage in cmd_execute():
"""
def cmd_execute():
    task, path = find_next_task(tree)

    # Pre-validate with MCP
    warnings = mcp_pre_validate(task, project_root=Path.cwd())
    if warnings:
        print("\n  ⚠️  MCP Pre-validation Warnings:")
        for w in warnings:
            print(f"     - {w}")
        print()

    # Continue with execution...
"""
