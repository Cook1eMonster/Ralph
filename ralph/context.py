"""ChromaDB context engine for Ralph.

Handles codebase indexing with embeddings for semantic search.
Uses Ollama for embeddings (nomic-embed-text) and summaries (qwen2.5-coder:7b).

This is the main context engine - ralph_context.py imports from here.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Optional reranker for better search quality (lazy-loaded for fast startup)
_RERANKER = None
_RERANKER_MODEL = "BAAI/bge-reranker-large"
_reranker_available: Optional[bool] = None


def get_reranker():
    """Lazy-load the reranker on first use."""
    global _RERANKER, _reranker_available
    if _reranker_available is None:
        try:
            from sentence_transformers import CrossEncoder
            _RERANKER = CrossEncoder(_RERANKER_MODEL)
            _reranker_available = True
            logger.info(f"Reranker loaded: {_RERANKER_MODEL}")
        except ImportError:
            _reranker_available = False
    return _RERANKER if _reranker_available else None


# Configuration
CONFIG = {
    "embed_model": "nomic-embed-text",
    "summary_model": "qwen2.5-coder:7b",
    "chunk_size": 50,
    "chunk_overlap": 10,
    "max_file_lines": 500,
    "top_k_results": 10,
    "rerank_candidates": 30,
    "use_reranker": True,
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


class IndexResult:
    """Result of an indexing operation."""

    def __init__(
        self,
        indexed: int = 0,
        updated: int = 0,
        skipped: int = 0,
        removed: int = 0,
        errors: int = 0,
        total_chunks: int = 0,
        error_message: Optional[str] = None,
    ):
        self.indexed = indexed
        self.updated = updated
        self.skipped = skipped
        self.removed = removed
        self.errors = errors
        self.total_chunks = total_chunks
        self.error_message = error_message

    def to_dict(self) -> dict:
        return {
            "indexed": self.indexed,
            "updated": self.updated,
            "skipped": self.skipped,
            "removed": self.removed,
            "errors": self.errors,
            "total_chunks": self.total_chunks,
            "error_message": self.error_message,
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
    if filepath.suffix.lower() not in CONFIG["extensions"]:
        return False

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


def get_file_hash(filepath: Path) -> Optional[str]:
    """Get hash of file contents for change detection."""
    try:
        content = filepath.read_bytes()
        return hashlib.md5(content).hexdigest()
    except (PermissionError, OSError):
        return None


def chunk_file(filepath: Path) -> list[dict]:
    """Split file into chunks for embedding."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning(f"Could not read {filepath}: {e}")
        return []

    lines = content.split("\n")
    chunks = []

    if len(lines) <= CONFIG["chunk_size"]:
        chunks.append({
            "content": content,
            "start_line": 1,
            "end_line": len(lines),
            "filepath": str(filepath),
        })
    else:
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


def get_embedding(text: str, model: str = None) -> Optional[list[float]]:
    """Get embedding vector from Ollama."""
    try:
        import ollama
        model = model or CONFIG["embed_model"]
        response = ollama.embeddings(model=model, prompt=text[:2000])
        return response["embedding"]
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return None


def summarize_file(filepath: Path, model: str = None) -> str:
    """Summarize a large file using local model."""
    try:
        import ollama
    except ImportError:
        return ""

    model = model or CONFIG["summary_model"]

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    lines = content.split("\n")
    if len(lines) > 2000:
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
        logger.error(f"Summary error for {filepath}: {e}")
        return ""


class ContextEngine:
    """ChromaDB-based context engine for a project."""

    def __init__(self, project_path: str = None, db_path: Optional[str] = None):
        """Initialize the context engine.

        Args:
            project_path: Path to the project codebase (default: auto-detect)
            db_path: Optional custom path for ChromaDB storage
        """
        if project_path:
            self.project_root = Path(project_path)
        else:
            self.project_root = get_project_root()

        self.db_path = Path(db_path) if db_path else self.project_root / CONFIG["db_path"]

        self._client = None
        self._collection = None
        self._file_hashes: dict = {}
        self._hash_file = self.db_path / "file_hashes.json"

    def _ensure_initialized(self) -> bool:
        """Lazy initialization of ChromaDB."""
        if self._client is not None:
            return True

        try:
            import chromadb
            from chromadb.config import Settings

            self.db_path.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=str(self.db_path),
                settings=Settings(anonymized_telemetry=False)
            )

            self._collection = self._client.get_or_create_collection(
                name="codebase",
                metadata={"hnsw:space": "cosine"}
            )

            # Load file hashes
            if self._hash_file.exists():
                self._file_hashes = json.loads(self._hash_file.read_text())

            return True

        except ImportError:
            logger.error("chromadb not installed. Run: pip install chromadb")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            return False

    def _save_hashes(self):
        """Save file hashes to disk."""
        self._hash_file.write_text(json.dumps(self._file_hashes, indent=2))

    @property
    def collection(self):
        """Get the ChromaDB collection (for backward compatibility)."""
        self._ensure_initialized()
        return self._collection

    @property
    def file_hashes(self) -> dict:
        """Get file hashes dict (for backward compatibility)."""
        return self._file_hashes

    def index(
        self,
        force: bool = False,
        verbose: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> IndexResult:
        """Index the codebase.

        Args:
            force: If True, re-index all files even if unchanged
            verbose: If True, print progress messages
            progress_callback: Optional callback(current, total, filepath, status)
                              for progress updates

        Returns:
            IndexResult with statistics
        """
        if not self._ensure_initialized():
            return IndexResult(error_message="Failed to initialize ChromaDB")

        result = IndexResult()

        if verbose:
            print(f"Indexing codebase at {self.project_root}")
            print(f"Using embedding model: {CONFIG['embed_model']}")

        # Find all files to index
        files_to_index = []
        for ext in CONFIG["extensions"]:
            files_to_index.extend(self.project_root.rglob(f"*{ext}"))

        files_to_index = [f for f in files_to_index if should_index_file(f)]
        total_files = len(files_to_index)

        if verbose:
            print(f"Found {total_files} files to process")

        if progress_callback:
            progress_callback(0, total_files, "", "scanning")

        for i, filepath in enumerate(files_to_index):
            try:
                rel_path = str(filepath.relative_to(self.project_root))
            except ValueError:
                continue

            if verbose and (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{total_files}...")

            if progress_callback:
                progress_callback(i, total_files, rel_path, "indexing")

            # Check if file changed
            current_hash = get_file_hash(filepath)
            if current_hash is None:
                result.errors += 1
                continue

            stored_hash = self._file_hashes.get(rel_path)

            if not force and stored_hash == current_hash:
                result.skipped += 1
                continue

            if verbose:
                print(f"  [Updating] {rel_path}...")

            # Remove old embeddings for this file
            try:
                existing = self._collection.get(where={"filepath": rel_path})
                if existing["ids"]:
                    self._collection.delete(ids=existing["ids"])
            except Exception:
                pass

            # Chunk and embed
            chunks = chunk_file(filepath)
            if not chunks:
                result.errors += 1
                continue

            for j, chunk in enumerate(chunks):
                embedding = get_embedding(chunk["content"])
                if not embedding:
                    result.errors += 1
                    continue

                chunk_id = f"{rel_path}::{j}"
                self._collection.add(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk["content"][:5000]],
                    metadatas=[{
                        "filepath": rel_path,
                        "start_line": chunk["start_line"],
                        "end_line": chunk["end_line"],
                        "chunk_index": j,
                    }]
                )

            # Update hash
            self._file_hashes[rel_path] = current_hash

            if stored_hash:
                result.updated += 1
            else:
                result.indexed += 1

        # Final progress update
        if progress_callback:
            progress_callback(total_files, total_files, "", "complete")

        # Cleanup stale entries for deleted files
        if verbose:
            print("\nCleaning up stale entries...")

        current_rel_paths = {str(f.relative_to(self.project_root)) for f in files_to_index}

        for stored_rel_path in list(self._file_hashes.keys()):
            if stored_rel_path not in current_rel_paths:
                if verbose:
                    print(f"  [Removing] {stored_rel_path}")
                try:
                    self._collection.delete(where={"filepath": stored_rel_path})
                except Exception:
                    pass
                del self._file_hashes[stored_rel_path]
                result.removed += 1

        self._save_hashes()
        result.total_chunks = self._collection.count()

        if verbose:
            print(f"\nIndexing complete:")
            print(f"  New files indexed: {result.indexed}")
            print(f"  Files updated: {result.updated}")
            print(f"  Files unchanged: {result.skipped}")
            print(f"  Files removed: {result.removed}")
            print(f"  Errors: {result.errors}")
            print(f"  Total chunks in DB: {result.total_chunks}")

        return result

    def search(self, query: str, top_k: int = None) -> list[dict]:
        """Search for relevant files/chunks with optional reranking.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of search results with filepath, similarity, snippet
        """
        if not self._ensure_initialized():
            return []

        top_k = top_k or CONFIG["top_k_results"]

        # Get more candidates if reranking is enabled
        reranker = get_reranker() if CONFIG["use_reranker"] else None
        use_rerank = reranker is not None
        n_candidates = CONFIG["rerank_candidates"] if use_rerank else top_k

        embedding = get_embedding(query)
        if embedding is None:
            return []

        results = self._collection.query(
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
                    "similarity": 1 - distance,
                    "start_line": meta["start_line"],
                    "end_line": meta["end_line"],
                    "snippet": results["documents"][0][i][:500],
                }

        ranked = list(seen_files.values())

        # Apply reranking if available
        if use_rerank and len(ranked) > 1:
            pairs = [(query, r["snippet"]) for r in ranked]
            scores = reranker.predict(pairs)
            for i, r in enumerate(ranked):
                r["rerank_score"] = float(scores[i])
            ranked = sorted(ranked, key=lambda x: x["rerank_score"], reverse=True)
        else:
            ranked = sorted(ranked, key=lambda x: x["similarity"], reverse=True)

        return ranked[:top_k]

    def suggest_read_first(self, task_name: str, task_context: str = "", top_k: int = 5) -> list[str]:
        """Suggest read_first files based on task description."""
        query = f"{task_name}. {task_context}".strip()
        results = self.search(query, top_k=top_k * 2)

        suggested = []
        for r in results[:top_k]:
            if r["similarity"] > 0.3:
                suggested.append(r["filepath"])

        return suggested

    def get_file_summary(self, filepath: str) -> str:
        """Get or generate summary for a file."""
        full_path = self.project_root / filepath
        if not full_path.exists():
            return ""

        try:
            lines = full_path.read_text().split("\n")
        except Exception:
            return ""

        if len(lines) <= CONFIG["max_file_lines"]:
            return ""

        print(f"  Summarizing {filepath} ({len(lines)} lines)...")
        return summarize_file(full_path)

    def get_context_for_task(self, task: dict) -> dict:
        """Get enriched context for a Ralph Tree task.

        Returns:
            {
                "suggested_read_first": [...],
                "relevant_files": [...],
                "summaries": {...},
                "search_results": [...]
            }
        """
        task_name = task.get("name", "")
        task_context = task.get("context", "")
        existing_files = task.get("files", [])
        existing_read_first = task.get("read_first", [])

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
        if not self._ensure_initialized():
            return {
                "initialized": False,
                "error": "ChromaDB not available",
            }

        return {
            "initialized": True,
            "project_root": str(self.project_root),
            "db_path": str(self.db_path),
            "total_chunks": self._collection.count(),
            "indexed_files": len(self._file_hashes),
            "embed_model": CONFIG["embed_model"],
            "summary_model": CONFIG["summary_model"],
        }


# =============================================================================
# Convenience Functions
# =============================================================================


def index_project(
    project_path: str,
    db_path: Optional[str] = None,
    force: bool = False,
    progress_callback: Optional[callable] = None,
) -> IndexResult:
    """Convenience function to index a project.

    Args:
        project_path: Path to the project codebase
        db_path: Optional custom path for ChromaDB storage
        force: If True, re-index all files
        progress_callback: Optional callback(current, total, filepath, status)

    Returns:
        IndexResult with statistics
    """
    engine = ContextEngine(project_path, db_path)
    return engine.index(force=force, verbose=False, progress_callback=progress_callback)


def search_project(project_path: str, query: str, db_path: Optional[str] = None, top_k: int = 10) -> list[dict]:
    """Convenience function to search a project.

    Args:
        project_path: Path to the project codebase
        query: Search query
        db_path: Optional custom path for ChromaDB storage
        top_k: Number of results

    Returns:
        List of search results
    """
    engine = ContextEngine(project_path, db_path)
    return engine.search(query, top_k=top_k)


def get_project_index_status(project_path: str, db_path: Optional[str] = None) -> dict:
    """Get indexing status for a project.

    Args:
        project_path: Path to the project codebase
        db_path: Optional custom path for ChromaDB storage

    Returns:
        Status dictionary
    """
    engine = ContextEngine(project_path, db_path)
    return engine.status()
