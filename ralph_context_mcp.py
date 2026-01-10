#!/usr/bin/env python3
"""
MCP Server for Ralph Context - Semantic codebase search for Claude.

Exposes ralph_context functionality as MCP tools so Claude can:
- Search codebase semantically
- Get file summaries
- Find related files for a task

Setup:
    pip install mcp chromadb ollama

    # Add to Claude Code settings (~/.claude/settings.json):
    {
      "mcpServers": {
        "ralph-context": {
          "command": "python",
          "args": ["/path/to/ralph_context_mcp.py"],
          "cwd": "/path/to/your/project",
          "env": {
            "RALPH_PROJECT_ROOT": "/path/to/your/project"
          }
        }
      }
    }

    # Note: RALPH_PROJECT_ROOT is needed when .git is in a parent directory
    # but you only want to index a subdirectory.

    # Or use uvx for isolated environment:
    {
      "mcpServers": {
        "ralph-context": {
          "command": "uvx",
          "args": ["--from", "mcp", "python", "/path/to/ralph_context_mcp.py"],
          "cwd": "/path/to/your/project"
        }
      }
    }
"""

import json
import os
import sys
from pathlib import Path

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Import the context engine
try:
    from ralph_context import ContextEngine, CONFIG
except ImportError:
    # Try relative import if running from different directory
    sys.path.insert(0, str(Path(__file__).parent))
    from ralph_context import ContextEngine, CONFIG


# Initialize server
server = Server("ralph-context")

# Lazy-loaded engine (initialized on first use)
_engine = None


def get_engine() -> ContextEngine:
    """Get or create the context engine."""
    global _engine
    if _engine is None:
        # Use RALPH_PROJECT_ROOT env var if set, otherwise auto-detect
        project_root = os.environ.get("RALPH_PROJECT_ROOT")
        if project_root:
            _engine = ContextEngine(project_root=Path(project_root))
        else:
            _engine = ContextEngine()
    return _engine


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
        Tool(
            name="codebase_search",
            description="Search the codebase semantically. Use this to find files related to a concept, feature, or pattern. Returns ranked list of relevant files with similarity scores.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query (e.g., 'patient authentication', 'database models', 'API endpoints for scheduling')"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="suggest_related_files",
            description="Suggest files to read before working on a task. Use this when starting a new feature to understand existing patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Description of the task you're about to work on"
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context about the task (optional)",
                        "default": ""
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of suggestions (default: 5)",
                        "default": 5
                    }
                },
                "required": ["task_description"]
            }
        ),
        Tool(
            name="summarize_file",
            description="Get an AI-generated summary of a file. Useful for understanding large files quickly.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file (relative to project root)"
                    }
                },
                "required": ["filepath"]
            }
        ),
        Tool(
            name="index_status",
            description="Check the status of the codebase index. Shows if indexing is needed.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="reindex_codebase",
            description="Re-index the codebase. Use this if files have changed significantly.",
            inputSchema={
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "description": "Force re-index all files (default: false, only indexes changed files)",
                        "default": False
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    engine = get_engine()

    if name == "codebase_search":
        query = arguments.get("query", "")
        top_k = arguments.get("top_k", 10)

        if engine.collection.count() == 0:
            return [TextContent(
                type="text",
                text="Index is empty. Run `python ralph_context.py index` first, or use the reindex_codebase tool."
            )]

        results = engine.search(query, top_k=top_k)

        if not results:
            return [TextContent(type="text", text="No results found.")]

        output = [f"**Search results for:** {query}\n"]
        for i, r in enumerate(results, 1):
            sim_pct = r["similarity"] * 100
            output.append(f"{i}. [{sim_pct:.1f}%] `{r['filepath']}`")
            output.append(f"   Lines {r['start_line']}-{r['end_line']}")

        return [TextContent(type="text", text="\n".join(output))]

    elif name == "suggest_related_files":
        task = arguments.get("task_description", "")
        context = arguments.get("context", "")
        top_k = arguments.get("top_k", 5)

        if engine.collection.count() == 0:
            return [TextContent(
                type="text",
                text="Index is empty. Run `python ralph_context.py index` first."
            )]

        suggestions = engine.suggest_read_first(task, context, top_k=top_k)

        if not suggestions:
            return [TextContent(type="text", text="No suggestions found.")]

        output = [f"**Suggested files for:** {task}\n"]
        output.append("Read these files to understand existing patterns:\n")
        for f in suggestions:
            output.append(f"- `{f}`")

        return [TextContent(type="text", text="\n".join(output))]

    elif name == "summarize_file":
        filepath = arguments.get("filepath", "")

        full_path = engine.project_root / filepath
        if not full_path.exists():
            return [TextContent(type="text", text=f"File not found: {filepath}")]

        summary = engine.get_file_summary(filepath)

        if not summary:
            # File is small, just note that
            try:
                lines = full_path.read_text().split("\n")
                return [TextContent(
                    type="text",
                    text=f"File `{filepath}` is small ({len(lines)} lines). No summary needed - read directly."
                )]
            except Exception as e:
                return [TextContent(type="text", text=f"Error reading file: {e}")]

        output = [f"**Summary of `{filepath}`:**\n", summary]
        return [TextContent(type="text", text="\n".join(output))]

    elif name == "index_status":
        status = engine.status()
        output = ["**Codebase Index Status**\n"]
        output.append(f"- Project: `{status['project_root']}`")
        output.append(f"- Indexed files: {status['indexed_files']}")
        output.append(f"- Total chunks: {status['total_chunks']}")
        output.append(f"- Embedding model: {status['embed_model']}")
        output.append(f"- Summary model: {status['summary_model']}")

        if status['total_chunks'] == 0:
            output.append("\n**Index is empty.** Run `python ralph_context.py index` to build it.")

        return [TextContent(type="text", text="\n".join(output))]

    elif name == "reindex_codebase":
        force = arguments.get("force", False)

        output = ["**Reindexing codebase...**\n"]

        try:
            stats = engine.index(force=force)
            output.append(f"- New files indexed: {stats['indexed']}")
            output.append(f"- Files updated: {stats['updated']}")
            output.append(f"- Files unchanged: {stats['skipped']}")
            output.append(f"- Errors: {stats['errors']}")
            output.append(f"- Total chunks in DB: {engine.collection.count()}")
        except Exception as e:
            output.append(f"Error during indexing: {e}")

        return [TextContent(type="text", text="\n".join(output))]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
