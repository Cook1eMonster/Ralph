"""Ollama model manager for VRAM lifecycle management."""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Models to keep loaded in VRAM
# Format: (model_name, is_embedding_model)
MODELS = [
    ("qwen2.5-coder:7b", False),
    ("nomic-embed-text", True),
]

OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaManager:
    """Manages Ollama model loading/unloading for VRAM optimization."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url
        self.loaded_models: list[str] = []
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=300.0)  # 5 min timeout for model loading
        return self._client

    async def _close_client(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def load_model(self, model: str, is_embedding: bool = False) -> bool:
        """Load a model into VRAM by making a keep_alive request.

        Ollama keeps models in VRAM when you make a request with keep_alive.
        Setting keep_alive to -1 keeps the model loaded indefinitely.

        For embedding models, use the /api/embeddings endpoint.
        For generation models, use the /api/generate endpoint.
        """
        try:
            client = await self._get_client()

            if is_embedding:
                # Embedding models use the embeddings endpoint
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": model,
                        "prompt": "test",  # Minimal prompt to load model
                        "keep_alive": -1,  # Keep loaded indefinitely
                    },
                )
            else:
                # Generation models use the generate endpoint
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": "",
                        "keep_alive": -1,  # Keep loaded indefinitely
                    },
                )

            if response.status_code == 200:
                logger.info(f"Loaded model '{model}' into VRAM (keep_alive=-1)")
                self.loaded_models.append(model)
                return True
            else:
                logger.error(f"Failed to load model '{model}': {response.status_code}")
                return False

        except httpx.ConnectError:
            logger.error(f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?")
            return False
        except Exception as e:
            logger.error(f"Error loading model '{model}': {e}")
            return False

    async def unload_model(self, model: str, is_embedding: bool = False) -> bool:
        """Unload a model from VRAM by setting keep_alive to 0."""
        try:
            client = await self._get_client()

            if is_embedding:
                # Embedding models use the embeddings endpoint
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": model,
                        "prompt": "test",
                        "keep_alive": 0,  # Unload immediately
                    },
                )
            else:
                # Generation models use the generate endpoint
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": "",
                        "keep_alive": 0,  # Unload immediately
                    },
                )

            if response.status_code == 200:
                logger.info(f"Unloaded model '{model}' from VRAM")
                if model in self.loaded_models:
                    self.loaded_models.remove(model)
                return True
            else:
                logger.error(f"Failed to unload model '{model}': {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error unloading model '{model}': {e}")
            return False

    async def load_all_models(self) -> dict[str, bool]:
        """Load all configured models into VRAM."""
        results = {}
        for model, is_embedding in MODELS:
            logger.info(f"Loading model '{model}' into VRAM...")
            results[model] = await self.load_model(model, is_embedding)
        return results

    async def unload_all_models(self) -> dict[str, bool]:
        """Unload all loaded models from VRAM."""
        results = {}
        for model, is_embedding in MODELS:
            logger.info(f"Unloading model '{model}' from VRAM...")
            results[model] = await self.unload_model(model, is_embedding)
        await self._close_client()
        return results

    async def check_ollama_status(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def list_running_models(self) -> list[str]:
        """List models currently loaded in Ollama."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/ps")
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
            return []
        except Exception as e:
            logger.error(f"Error listing running models: {e}")
            return []


# Global manager instance
_manager: Optional[OllamaManager] = None


def get_ollama_manager() -> OllamaManager:
    """Get the global Ollama manager instance."""
    global _manager
    if _manager is None:
        _manager = OllamaManager()
    return _manager


async def startup_load_models() -> None:
    """Load models at application startup."""
    manager = get_ollama_manager()

    if not await manager.check_ollama_status():
        logger.warning("Ollama is not running. Models will not be preloaded.")
        logger.warning("Start Ollama with 'ollama serve' to enable AI features.")
        return

    logger.info("Loading Ollama models into VRAM...")
    results = await manager.load_all_models()

    for model, success in results.items():
        if success:
            logger.info(f"  - {model}: loaded")
        else:
            logger.warning(f"  - {model}: failed to load")


async def shutdown_unload_models() -> None:
    """Unload models at application shutdown."""
    manager = get_ollama_manager()

    if not await manager.check_ollama_status():
        logger.info("Ollama not accessible, skipping model unload.")
        return

    logger.info("Unloading Ollama models from VRAM...")
    results = await manager.unload_all_models()

    for model, success in results.items():
        if success:
            logger.info(f"  - {model}: unloaded")
        else:
            logger.warning(f"  - {model}: failed to unload")
