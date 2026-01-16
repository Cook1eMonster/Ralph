"""Ollama client wrapper with Result-based error handling.

Provides a clean interface to Ollama for embeddings and summarization,
wrapping the existing functions from context.py.
"""

from pathlib import Path

from ralph.domain.shared.result import Err, Ok, Result


# Default models from context.py CONFIG
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_SUMMARY_MODEL = "qwen2.5-coder:7b"


class OllamaClient:
    """Client for Ollama embeddings and summarization.

    Wraps the Ollama API calls with Result-based error handling.
    Uses lazy imports to avoid requiring ollama when not needed.

    Example:
        client = OllamaClient()
        if client.is_available():
            result = client.get_embedding("def hello(): pass")
            if isinstance(result, Ok):
                embedding = result.value  # list[float]
    """

    def __init__(
        self,
        embed_model: str = DEFAULT_EMBED_MODEL,
        summary_model: str = DEFAULT_SUMMARY_MODEL,
    ) -> None:
        """Initialize the Ollama client.

        Args:
            embed_model: Model to use for embeddings.
            summary_model: Model to use for summarization.
        """
        self._embed_model = embed_model
        self._summary_model = summary_model
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Check if Ollama is available.

        Returns:
            True if ollama package is installed and server is reachable.
        """
        if self._available is not None:
            return self._available

        try:
            import ollama
            # Try a simple operation to verify server is running
            ollama.list()
            self._available = True
        except ImportError:
            self._available = False
        except Exception:
            self._available = False

        return self._available

    def get_embedding(self, text: str) -> Result[list[float], str]:
        """Get embedding vector for text.

        Args:
            text: Text to embed (truncated to 2000 chars).

        Returns:
            Ok(list[float]) with embedding vector if successful,
            Err(str) with error message if failed.
        """
        try:
            import ollama
        except ImportError:
            return Err("ollama package not installed")

        try:
            # Truncate to avoid exceeding context limits
            truncated_text = text[:2000]
            response = ollama.embeddings(
                model=self._embed_model,
                prompt=truncated_text,
            )
            return Ok(response["embedding"])

        except Exception as e:
            return Err(f"Embedding error: {e}")

    def summarize_file(self, path: Path) -> Result[str, str]:
        """Summarize a code file.

        Args:
            path: Path to the file to summarize.

        Returns:
            Ok(str) with summary if successful,
            Err(str) with error message if failed.
        """
        try:
            import ollama
        except ImportError:
            return Err("ollama package not installed")

        # Read file content
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            return Err(f"File not found: {path}")
        except PermissionError:
            return Err(f"Permission denied: {path}")
        except OSError as e:
            return Err(f"Error reading file: {e}")

        # Truncate large files
        lines = content.split("\n")
        if len(lines) > 2000:
            content = (
                "\n".join(lines[:1000])
                + "\n\n[...truncated...]\n\n"
                + "\n".join(lines[-500:])
            )

        prompt = f"""Summarize this code file concisely. Focus on:
- What it does (purpose)
- Key exports/functions/classes
- Dependencies it uses
- How it fits in the codebase

File: {path.name}
```
{content[:15000]}
```

Summary (be concise, ~10-15 lines):"""

        try:
            response = ollama.generate(
                model=self._summary_model,
                prompt=prompt,
                options={"num_predict": 500},
            )
            return Ok(response["response"].strip())

        except Exception as e:
            return Err(f"Summary error for {path}: {e}")

    def generate(self, prompt: str, max_tokens: int = 500) -> Result[str, str]:
        """Generate text using the summary model.

        Args:
            prompt: Prompt to send to the model.
            max_tokens: Maximum tokens to generate.

        Returns:
            Ok(str) with generated text if successful,
            Err(str) with error message if failed.
        """
        try:
            import ollama
        except ImportError:
            return Err("ollama package not installed")

        try:
            response = ollama.generate(
                model=self._summary_model,
                prompt=prompt,
                options={"num_predict": max_tokens},
            )
            return Ok(response["response"].strip())

        except Exception as e:
            return Err(f"Generation error: {e}")
