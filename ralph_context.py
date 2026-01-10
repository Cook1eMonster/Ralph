#!/usr/bin/env python3
"""
ralph_context.py - Local AI-powered context engine for Ralph Tree.

Uses Ollama + ChromaDB to:
1. Index your codebase with embeddings
2. Find semantically relevant files for any task
3. Summarize large files to fit in context
4. Auto-suggest read_first files

Requirements:
    pip install chromadb ollama

Setup:
    ollama pull nomic-embed-text
    ollama pull codellama:13b
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("chromadb not installed. Run: pip install chromadb")
    sys.exit(1)

try:
    import ollama
except ImportError:
    print("ollama not installed. Run: pip install ollama")
    sys.exit(1)

# Optional reranker for better search quality (lazy-loaded for fast startup)
RERANKER = None
RERANKER_MODEL = "BAAI/bge-reranker-large"  # 560M params, high quality
_reranker_available = None  # None = not checked, True/False = checked


def get_reranker():
    """Lazy-load the reranker on first use."""
    global RERANKER, _reranker_available
    if _reranker_available is None:
        try:
            from sentence_transformers import CrossEncoder
            RERANKER = CrossEncoder(RERANKER_MODEL)
            _reranker_available = True
            print(f"  Reranker loaded: {RERANKER_MODEL}")
        except ImportError:
            _reranker_available = False
    return RERANKER if _reranker_available else None


# Configuration
CONFIG = {
    "embed_model": "nomic-embed-text",        # Better embeddings, 768 dims
    "summary_model": "qwen2.5-coder:7b",      # Code-specialized, excellent quality
    "chunk_size": 50,  # lines per chunk (smaller for embedding context limits)
    "chunk_overlap": 10,
    "max_file_lines": 500,  # files larger than this get summarized
    "top_k_results": 10,
    "rerank_candidates": 30,  # Get more candidates, then rerank to top_k
    "use_reranker": True,  # Enable reranking if available
    "db_path": ".ralph_context",
    "extensions": [
        ".py", ".ts", ".tsx", ".js", ".jsx",
        ".json", ".yaml", ".yml", ".md",
        ".sql", ".html", ".css", ".scss",
        ".sh", ".bash", ".dockerfile",
    ],
    "ignore_dirs": [
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", "coverage", ".pytest_cache",
        ".ralph_context", ".nx", ".turbo",
    ],
    "ignore_files": [
        "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        "*.min.js", "*.min.css", "*.map",
    ],
}


def get_project_root() -> Path:
    """Find project root (has package.json, pyproject.toml, or .git)."""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if any((parent / marker).exists() for marker in [".git", "package.json", "pyproject.toml"]):
            return parent
    return current


def should_index_file(filepath: Path) -> bool:
    """Check if file should be indexed."""
    # Check extension
    if filepath.suffix.lower() not in CONFIG["extensions"]:
        return False

    # Check ignore patterns - use parts for cross-platform compatibility
    path_parts = filepath.parts
    for ignore_dir in CONFIG["ignore_dirs"]:
        if ignore_dir in path_parts:
            return False

    for pattern in CONFIG["ignore_files"]:
        if pattern.startswith("*"):
            if filepath.name.endswith(pattern[1:]):
                return False
        elif filepath.name == pattern:
            return False

    return True


def get_file_hash(filepath: Path) -> str:
    """Get hash of file contents for change detection."""
    try:
        content = filepath.read_bytes()
        return hashlib.md5(content).hexdigest()
    except (PermissionError, OSError):
        return None  # Skip locked/inaccessible files


def chunk_file(filepath: Path) -> list[dict]:
    """Split file into chunks for embedding."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"  Warning: Could not read {filepath}: {e}")
        return []

    lines = content.split("\n")
    chunks = []

    # For small files, single chunk
    if len(lines) <= CONFIG["chunk_size"]:
        chunks.append({
            "content": content,
            "start_line": 1,
            "end_line": len(lines),
            "filepath": str(filepath),
        })
    else:
        # Split into overlapping chunks
        step = CONFIG["chunk_size"] - CONFIG["chunk_overlap"]
        for i in range(0, len(lines), step):
            chunk_lines = lines[i:i + CONFIG["chunk_size"]]
            if chunk_lines:
                chunks.append({
                    "content": "\n".join(chunk_lines),
                    "start_line": i + 1,
                    "end_line": min(i + len(chunk_lines), len(lines)),
                    "filepath": str(filepath),
                })

    return chunks


def get_embedding(text: str, model: str = None) -> list[float]:
    """Get embedding vector from Ollama."""
    model = model or CONFIG["embed_model"]
    try:
        # Truncate to ~2000 chars to stay within embedding model context limits
        response = ollama.embeddings(model=model, prompt=text[:2000])
        return response["embedding"]
    except Exception as e:
        print(f"  Embedding error: {e}")
        return None


def summarize_file(filepath: Path, model: str = None) -> str:
    """Summarize a large file using local model."""
    model = model or CONFIG["summary_model"]

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    # Truncate if very large
    lines = content.split("\n")
    if len(lines) > 2000:
        # Take first 1000 and last 500 lines
        content = "\n".join(lines[:1000]) + "\n\n[...truncated...]\n\n" + "\n".join(lines[-500:])

    prompt = f"""Summarize this code file concisely. Focus on:
- What it does (purpose)
- Key exports/functions/classes
- Dependencies it uses
- How it fits in the codebase

File: {filepath.name}
```
{content[:15000]}
```

Summary (be concise, ~10-15 lines):"""

    try:
        response = ollama.generate(model=model, prompt=prompt, options={"num_predict": 500})
        return response["response"].strip()
    except Exception as e:
        print(f"  Summary error for {filepath}: {e}")
        return ""


class ContextEngine:
    """Main context engine using ChromaDB and Ollama."""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or get_project_root()
        self.db_path = self.project_root / CONFIG["db_path"]
        self.db_path.mkdir(exist_ok=True)

        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="codebase",
            metadata={"hnsw:space": "cosine"}
        )

        # Load file hashes for change detection
        self.hash_file = self.db_path / "file_hashes.json"
        self.file_hashes = self._load_hashes()

    def _load_hashes(self) -> dict:
        """Load stored file hashes."""
        if self.hash_file.exists():
            return json.loads(self.hash_file.read_text())
        return {}

    def _save_hashes(self):
        """Save file hashes."""
        self.hash_file.write_text(json.dumps(self.file_hashes, indent=2))

    def index(self, force: bool = False) -> dict:
        """Index the codebase. Returns stats."""
        print(f"Indexing codebase at {self.project_root}")
        print(f"Using embedding model: {CONFIG['embed_model']}")

        stats = {"indexed": 0, "skipped": 0, "updated": 0, "errors": 0}

        # Find all files to index
        files_to_index = []
        for ext in CONFIG["extensions"]:
            files_to_index.extend(self.project_root.rglob(f"*{ext}"))

        files_to_index = [f for f in files_to_index if should_index_file(f)]
        print(f"Found {len(files_to_index)} files to process")

        for i, filepath in enumerate(files_to_index):
            rel_path = str(filepath.relative_to(self.project_root))

            # Progress
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(files_to_index)}...")

            # Check if file changed
            current_hash = get_file_hash(filepath)
            if current_hash is None:
                stats["errors"] += 1
                continue  # Skip inaccessible files
            stored_hash = self.file_hashes.get(rel_path)

            if not force and stored_hash == current_hash:
                stats["skipped"] += 1
                continue

            # Remove old embeddings for this file
            try:
                existing = self.collection.get(where={"filepath": rel_path})
                if existing["ids"]:
                    self.collection.delete(ids=existing["ids"])
            except Exception:
                pass

            # Chunk and embed
            chunks = chunk_file(filepath)
            if not chunks:
                stats["errors"] += 1
                continue

            for j, chunk in enumerate(chunks):
                embedding = get_embedding(chunk["content"])
                if not embedding:  # None or empty list
                    stats["errors"] += 1
                    continue

                chunk_id = f"{rel_path}::{j}"
                self.collection.add(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk["content"][:5000]],  # Store truncated for retrieval
                    metadatas=[{
                        "filepath": rel_path,
                        "start_line": chunk["start_line"],
                        "end_line": chunk["end_line"],
                        "chunk_index": j,
                    }]
                )

            # Update hash
            self.file_hashes[rel_path] = current_hash

            if stored_hash:
                stats["updated"] += 1
            else:
                stats["indexed"] += 1

        self._save_hashes()

        print(f"\nIndexing complete:")
        print(f"  New files indexed: {stats['indexed']}")
        print(f"  Files updated: {stats['updated']}")
        print(f"  Files unchanged: {stats['skipped']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Total chunks in DB: {self.collection.count()}")

        return stats

    def search(self, query: str, top_k: int = None) -> list[dict]:
        """Search for relevant files/chunks with optional reranking."""
        top_k = top_k or CONFIG["top_k_results"]

        # Get more candidates if reranking is enabled (lazy-load reranker)
        reranker = get_reranker() if CONFIG["use_reranker"] else None
        use_rerank = reranker is not None
        n_candidates = CONFIG["rerank_candidates"] if use_rerank else top_k

        embedding = get_embedding(query)
        if embedding is None:
            return []

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_candidates,
            include=["documents", "metadatas", "distances"]
        )

        # Dedupe by file, keep best chunk per file
        seen_files = {}
        for i, meta in enumerate(results["metadatas"][0]):
            filepath = meta["filepath"]
            distance = results["distances"][0][i]

            if filepath not in seen_files or distance < seen_files[filepath]["distance"]:
                seen_files[filepath] = {
                    "filepath": filepath,
                    "distance": distance,
                    "similarity": 1 - distance,  # cosine similarity
                    "start_line": meta["start_line"],
                    "end_line": meta["end_line"],
                    "snippet": results["documents"][0][i][:500],
                }

        ranked = list(seen_files.values())

        # Apply reranking if available
        if use_rerank and len(ranked) > 1:
            pairs = [(query, r["snippet"]) for r in ranked]
            scores = reranker.predict(pairs)
            # Combine with original similarity for stability
            for i, r in enumerate(ranked):
                r["rerank_score"] = float(scores[i])
            ranked = sorted(ranked, key=lambda x: x["rerank_score"], reverse=True)
        else:
            # Sort by embedding similarity
            ranked = sorted(ranked, key=lambda x: x["similarity"], reverse=True)

        return ranked[:top_k]

    def suggest_read_first(self, task_name: str, task_context: str = "", top_k: int = 5) -> list[str]:
        """Suggest read_first files based on task description."""
        query = f"{task_name}. {task_context}".strip()
        results = self.search(query, top_k=top_k * 2)  # Get more, then filter

        # Return just file paths
        suggested = []
        for r in results[:top_k]:
            if r["similarity"] > 0.3:  # Relevance threshold
                suggested.append(r["filepath"])

        return suggested

    def get_file_summary(self, filepath: str) -> str:
        """Get or generate summary for a file."""
        full_path = self.project_root / filepath
        if not full_path.exists():
            return ""

        # Check if file is large enough to need summary
        try:
            lines = full_path.read_text().split("\n")
        except Exception:
            return ""

        if len(lines) <= CONFIG["max_file_lines"]:
            return ""  # No summary needed, file is small

        # Generate summary
        print(f"  Summarizing {filepath} ({len(lines)} lines)...")
        return summarize_file(full_path)

    def get_context_for_task(self, task: dict) -> dict:
        """
        Get enriched context for a Ralph Tree task.

        Returns:
            {
                "suggested_read_first": [...],
                "relevant_files": [...],
                "summaries": {...},
                "patterns": "..."
            }
        """
        task_name = task.get("name", "")
        task_context = task.get("context", "")
        existing_files = task.get("files", [])
        existing_read_first = task.get("read_first", [])

        # Search for relevant files
        query = f"{task_name}. {task_context}"
        if existing_files:
            query += f" Related to: {', '.join(existing_files)}"

        results = self.search(query, top_k=15)

        # Suggest read_first (exclude already specified)
        suggested_read_first = []
        for r in results:
            if r["filepath"] not in existing_read_first and r["filepath"] not in existing_files:
                if r["similarity"] > 0.35:
                    suggested_read_first.append(r["filepath"])
        suggested_read_first = suggested_read_first[:5]

        # Get summaries for large relevant files
        summaries = {}
        all_relevant = existing_read_first + existing_files + suggested_read_first[:3]
        for filepath in all_relevant:
            summary = self.get_file_summary(filepath)
            if summary:
                summaries[filepath] = summary

        return {
            "suggested_read_first": suggested_read_first,
            "relevant_files": [r["filepath"] for r in results[:10]],
            "summaries": summaries,
            "search_results": results[:5],
        }

    def status(self) -> dict:
        """Get index status."""
        return {
            "project_root": str(self.project_root),
            "db_path": str(self.db_path),
            "total_chunks": self.collection.count(),
            "indexed_files": len(self.file_hashes),
            "embed_model": CONFIG["embed_model"],
            "summary_model": CONFIG["summary_model"],
        }


def cmd_index(args):
    """Index the codebase."""
    engine = ContextEngine()
    engine.index(force=args.force)


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
