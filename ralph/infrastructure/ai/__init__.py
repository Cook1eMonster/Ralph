"""AI infrastructure for Ralph.

Provides wrappers around AI services (Ollama, ChromaDB) with
Result-based error handling for embeddings, summarization,
and semantic search.
"""

from ralph.infrastructure.ai.context_engine import (
    ContextEngineWrapper,
    SearchResult,
)
from ralph.infrastructure.ai.ollama import OllamaClient

__all__ = [
    "OllamaClient",
    "ContextEngineWrapper",
    "SearchResult",
]
