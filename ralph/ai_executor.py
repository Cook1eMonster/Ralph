"""AI Executor for Ralph.

Provides a unified interface for AI operations, routing to either
Claude (via subprocess) or local Ollama based on configuration.
"""

import asyncio
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from .models import AIConfig, AIProvider, TaskNode, Tree

logger = logging.getLogger(__name__)


class AIExecutor:
    """Execute AI tasks using the configured provider."""

    def __init__(self, config: AIConfig):
        """Initialize with AI configuration.

        Args:
            config: The AI configuration specifying which provider to use.
        """
        self.config = config
        self._ollama_available: Optional[bool] = None

    async def check_ollama(self) -> bool:
        """Check if Ollama is available."""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            import ollama
            await asyncio.to_thread(ollama.list)
            self._ollama_available = True
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            self._ollama_available = False

        return self._ollama_available

    # =========================================================================
    # Planning
    # =========================================================================

    async def plan(self, requirements: str, project_name: str = "Project") -> Optional[Tree]:
        """Generate a task tree from requirements.

        Args:
            requirements: The project requirements/description.
            project_name: Name for the project.

        Returns:
            A Tree object, or None if planning failed.
        """
        if self.config.planning == AIProvider.CLAUDE:
            return await self._plan_with_claude(requirements, project_name)
        else:
            return await self._plan_with_ollama(requirements, project_name)

    async def _plan_with_claude(self, requirements: str, project_name: str) -> Optional[Tree]:
        """Use Claude to generate a task tree."""
        prompt = f'''You are a software architect. Break down this project into a hierarchical task tree.

Project Name: {project_name}

Requirements:
{requirements}

Output ONLY valid JSON with this structure (no markdown, no explanation):
{{
  "name": "{project_name}",
  "context": "Brief project description",
  "children": [
    {{
      "name": "Feature Area 1",
      "status": "pending",
      "context": "What this area covers",
      "children": [
        {{
          "name": "Specific Task 1.1",
          "status": "pending",
          "spec": "2-3 sentences describing exactly what to build",
          "files": ["path/to/file1.py"],
          "acceptance": ["pytest tests/", "ruff check ."]
        }}
      ]
    }}
  ]
}}

Make tasks small (~60k tokens of context each). Each leaf task should touch 1-3 files.'''

        try:
            # Call Claude CLI
            result = await asyncio.to_thread(
                subprocess.run,
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(f"Claude failed: {result.stderr}")
                return None

            # Parse JSON from output
            return self._parse_tree_json(result.stdout)

        except subprocess.TimeoutExpired:
            logger.error("Claude timed out")
            return None
        except FileNotFoundError:
            logger.error("Claude CLI not found")
            return None
        except Exception as e:
            logger.error(f"Planning with Claude failed: {e}")
            return None

    async def _plan_with_ollama(self, requirements: str, project_name: str) -> Optional[Tree]:
        """Use local Ollama to generate a task tree."""
        if not await self.check_ollama():
            logger.error("Ollama not available for planning")
            return None

        prompt = f'''You are a software architect. Break down this project into a hierarchical task tree.

Project Name: {project_name}

Requirements:
{requirements}

Output ONLY valid JSON with this structure (no markdown, no explanation):
{{
  "name": "{project_name}",
  "context": "Brief project description",
  "children": [
    {{
      "name": "Feature Area 1",
      "status": "pending",
      "context": "What this area covers",
      "children": [
        {{
          "name": "Specific Task 1.1",
          "status": "pending",
          "spec": "2-3 sentences describing exactly what to build",
          "files": ["path/to/file1.py"],
          "acceptance": ["pytest tests/"]
        }}
      ]
    }}
  ]
}}

Make tasks small. Each leaf task should touch 1-3 files.'''

        try:
            import ollama

            response = await asyncio.to_thread(
                ollama.chat,
                model=self.config.planning_model,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response["message"]["content"]
            return self._parse_tree_json(content)

        except Exception as e:
            logger.error(f"Planning with Ollama failed: {e}")
            return None

    def _parse_tree_json(self, text: str) -> Optional[Tree]:
        """Parse JSON tree from LLM output."""
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        # Try to find raw JSON
        json_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        try:
            data = json.loads(text)
            return Tree(**data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse tree JSON: {e}")
            return None

    # =========================================================================
    # Context Retrieval
    # =========================================================================

    async def get_context(self, task: TaskNode, project_path: str) -> dict:
        """Get relevant context for a task.

        Always uses local ChromaDB + embeddings regardless of config,
        since this is purely local and fast.

        Args:
            task: The task to get context for.
            project_path: Path to the project.

        Returns:
            Dict with suggested_read_first, relevant_files, summaries.
        """
        try:
            from .context import ContextEngine

            engine = ContextEngine(project_path=project_path)

            # Build search query from task
            query = task.name
            if task.spec:
                query += " " + task.spec
            if task.context:
                query += " " + task.context

            # Get suggestions
            results = engine.search(query, top_k=10)

            return {
                "suggested_read_first": [r["filepath"] for r in results[:5]],
                "relevant_files": [r["filepath"] for r in results],
                "search_results": results,
            }

        except Exception as e:
            logger.error(f"Context retrieval failed: {e}")
            return {
                "suggested_read_first": task.read_first or [],
                "relevant_files": task.files or [],
                "search_results": [],
            }

    # =========================================================================
    # Coding
    # =========================================================================

    async def code(
        self,
        task: TaskNode,
        context: dict,
        project_path: str,
    ) -> Optional[str]:
        """Generate code for a task.

        Args:
            task: The task to implement.
            context: Context from get_context().
            project_path: Path to the project.

        Returns:
            Generated code as a string, or None if failed.
        """
        if self.config.coding == AIProvider.CLAUDE:
            return await self._code_with_claude(task, context, project_path)
        else:
            return await self._code_with_ollama(task, context, project_path)

    async def _code_with_claude(
        self,
        task: TaskNode,
        context: dict,
        project_path: str,
    ) -> Optional[str]:
        """Use Claude to generate code."""
        # Build context string
        context_files = []
        for filepath in context.get("suggested_read_first", [])[:3]:
            try:
                full_path = Path(project_path) / filepath
                if full_path.exists():
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    context_files.append(f"=== {filepath} ===\n{content[:2000]}")
            except Exception:
                pass

        context_str = "\n\n".join(context_files) if context_files else "No context files."

        prompt = f'''Implement this task:

Task: {task.name}
Spec: {task.spec or "No spec provided"}

Files to modify: {", ".join(task.files) if task.files else "Determine from context"}

Relevant context:
{context_str}

Write clean, well-structured code. Output the complete file contents.'''

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=project_path,
            )

            if result.returncode != 0:
                logger.error(f"Claude coding failed: {result.stderr}")
                return None

            return result.stdout

        except Exception as e:
            logger.error(f"Coding with Claude failed: {e}")
            return None

    async def _code_with_ollama(
        self,
        task: TaskNode,
        context: dict,
        project_path: str,
    ) -> Optional[str]:
        """Use local Ollama to generate code."""
        if not await self.check_ollama():
            logger.error("Ollama not available for coding")
            return None

        # Build context string
        context_files = []
        for filepath in context.get("suggested_read_first", [])[:3]:
            try:
                full_path = Path(project_path) / filepath
                if full_path.exists():
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    context_files.append(f"=== {filepath} ===\n{content[:2000]}")
            except Exception:
                pass

        context_str = "\n\n".join(context_files) if context_files else "No context files."

        prompt = f'''Implement this task:

Task: {task.name}
Spec: {task.spec or "No spec provided"}

Files to modify: {", ".join(task.files) if task.files else "Determine from context"}

Relevant context:
{context_str}

Write clean, well-structured code. Output the complete file contents.'''

        try:
            import ollama

            response = await asyncio.to_thread(
                ollama.chat,
                model=self.config.coding_model,
                messages=[{"role": "user", "content": prompt}],
            )

            return response["message"]["content"]

        except Exception as e:
            logger.error(f"Coding with Ollama failed: {e}")
            return None


# Convenience function
def get_executor(config: Optional[AIConfig] = None) -> AIExecutor:
    """Get an AI executor with the given or default config."""
    if config is None:
        from .global_config import get_global_config
        config = get_global_config()
    return AIExecutor(config)


__all__ = ["AIExecutor", "get_executor"]
