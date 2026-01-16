"""Context engine wrapper with Result-based error handling.

Provides a cleaner interface to the existing ContextEngine from context.py,
using composition to delegate to the underlying implementation.
"""

from dataclasses import dataclass
from pathlib import Path

from ralph.domain.shared.result import Err, Ok, Result


@dataclass(frozen=True)
class SearchResult:
    """Result from a semantic search query.

    Attributes:
        filepath: Relative path to the matched file.
        similarity: Similarity score (0-1, higher is better).
        start_line: Starting line number of the matched chunk.
        end_line: Ending line number of the matched chunk.
        snippet: Text snippet from the matched region.
    """

    filepath: str
    similarity: float
    start_line: int
    end_line: int
    snippet: str


class ContextEngineWrapper:
    """Wrapper around the existing ContextEngine with Result-based API.

    Provides a cleaner interface for semantic search and context
    suggestions, delegating to the underlying ContextEngine
    implementation.

    Example:
        wrapper = ContextEngineWrapper("/path/to/project")
        result = wrapper.search("authentication middleware")
        if isinstance(result, Ok):
            for search_result in result.value:
                print(f"{search_result.filepath}: {search_result.similarity}")
    """

    def __init__(
        self,
        project_path: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        """Initialize the context engine wrapper.

        Args:
            project_path: Path to the project codebase (auto-detected if None).
            db_path: Custom path for ChromaDB storage (default: .ralph_context).
        """
        self._project_path = str(project_path) if project_path else None
        self._db_path = str(db_path) if db_path else None
        self._engine = None
        self._available: bool | None = None

    def _ensure_engine(self) -> Result[None, str]:
        """Lazily initialize the underlying ContextEngine.

        Returns:
            Ok(None) if engine is ready, Err(str) if initialization failed.
        """
        if self._engine is not None:
            return Ok(None)

        try:
            from ralph.context import ContextEngine

            self._engine = ContextEngine(
                project_path=self._project_path,
                db_path=self._db_path,
            )
            return Ok(None)

        except ImportError as e:
            return Err(f"Context engine dependencies not available: {e}")
        except Exception as e:
            return Err(f"Failed to initialize context engine: {e}")

    def is_available(self) -> bool:
        """Check if the context engine is available.

        Returns:
            True if ChromaDB and required dependencies are installed.
        """
        if self._available is not None:
            return self._available

        result = self._ensure_engine()
        self._available = isinstance(result, Ok)
        return self._available

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> Result[list[SearchResult], str]:
        """Search for relevant files/chunks in the codebase.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results to return.

        Returns:
            Ok(list[SearchResult]) with ranked results if successful,
            Err(str) with error message if failed.
        """
        init_result = self._ensure_engine()
        if isinstance(init_result, Err):
            return init_result

        try:
            raw_results = self._engine.search(query, top_k=top_k)

            results = [
                SearchResult(
                    filepath=r["filepath"],
                    similarity=r.get("similarity", 0.0),
                    start_line=r.get("start_line", 1),
                    end_line=r.get("end_line", 1),
                    snippet=r.get("snippet", ""),
                )
                for r in raw_results
            ]

            return Ok(results)

        except Exception as e:
            return Err(f"Search error: {e}")

    def suggest_read_first(
        self,
        task_name: str,
        context: str = "",
        top_k: int = 5,
    ) -> Result[list[str], str]:
        """Suggest files to read before working on a task.

        Uses semantic search to find files relevant to the task,
        returning file paths that should be read for context.

        Args:
            task_name: Name of the task being worked on.
            context: Additional context about the task.
            top_k: Maximum number of suggestions.

        Returns:
            Ok(list[str]) with suggested file paths if successful,
            Err(str) with error message if failed.
        """
        init_result = self._ensure_engine()
        if isinstance(init_result, Err):
            return init_result

        try:
            suggestions = self._engine.suggest_read_first(
                task_name=task_name,
                task_context=context,
                top_k=top_k,
            )
            return Ok(suggestions)

        except Exception as e:
            return Err(f"Suggestion error: {e}")

    def get_context_for_task(
        self,
        task_name: str,
        task_context: str = "",
        files: list[str] | None = None,
        read_first: list[str] | None = None,
    ) -> Result[dict, str]:
        """Get enriched context for a task.

        Returns suggested files, relevant search results, and
        summaries for large files.

        Args:
            task_name: Name of the task.
            task_context: Additional context about the task.
            files: Files the task will modify.
            read_first: Files already specified to read first.

        Returns:
            Ok(dict) with context data if successful,
            Err(str) with error message if failed.
        """
        init_result = self._ensure_engine()
        if isinstance(init_result, Err):
            return init_result

        try:
            task_dict = {
                "name": task_name,
                "context": task_context,
                "files": files or [],
                "read_first": read_first or [],
            }

            context = self._engine.get_context_for_task(task_dict)
            return Ok(context)

        except Exception as e:
            return Err(f"Context retrieval error: {e}")

    def index(self, force: bool = False, verbose: bool = False) -> Result[dict, str]:
        """Index the codebase for semantic search.

        Args:
            force: If True, re-index all files even if unchanged.
            verbose: If True, print progress messages.

        Returns:
            Ok(dict) with indexing statistics if successful,
            Err(str) with error message if failed.
        """
        init_result = self._ensure_engine()
        if isinstance(init_result, Err):
            return init_result

        try:
            result = self._engine.index(force=force, verbose=verbose)
            return Ok(result.to_dict())

        except Exception as e:
            return Err(f"Indexing error: {e}")

    def status(self) -> Result[dict, str]:
        """Get the current index status.

        Returns:
            Ok(dict) with status information if successful,
            Err(str) with error message if failed.
        """
        init_result = self._ensure_engine()
        if isinstance(init_result, Err):
            return init_result

        try:
            status = self._engine.status()
            return Ok(status)

        except Exception as e:
            return Err(f"Status retrieval error: {e}")
