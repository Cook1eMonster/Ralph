#!/usr/bin/env python3
"""
ralph_pattern_library.py - Accumulate and reuse code patterns across tasks.

After each task completion:
1. Extract patterns from what Claude wrote
2. Store in pattern library (vector DB)
3. Before next task: retrieve relevant patterns
4. Claude follows established patterns automatically

Result: Consistency improves over time, less rediscovery.
"""

from pathlib import Path
from typing import List, Dict
import json
import ollama
from ralph_context import ContextEngine, get_embedding


class PatternLibrary:
    """
    Stores and retrieves code patterns using ChromaDB.

    Patterns include:
    - Error handling approaches
    - Testing structures
    - API endpoint patterns
    - Database query patterns
    - Component structures
    """

    def __init__(self, project_root: Path = None):
        self.engine = ContextEngine(project_root)
        self.project_root = self.engine.project_root
        self.pattern_file = self.project_root / ".ralph_context" / "patterns.json"
        self.patterns = self._load_patterns()

    def _load_patterns(self) -> Dict:
        """Load stored patterns."""
        if self.pattern_file.exists():
            return json.loads(self.pattern_file.read_text())
        return {"patterns": [], "version": 1}

    def _save_patterns(self):
        """Save patterns to disk."""
        self.pattern_file.parent.mkdir(exist_ok=True)
        self.pattern_file.write_text(json.dumps(self.patterns, indent=2))

    def extract_pattern_from_task(
        self,
        task_name: str,
        modified_files: List[str],
        model: str = "qwen2.5-coder:7b"
    ) -> Dict:
        """
        After task completion, extract learned patterns.

        Args:
            task_name: What was implemented
            modified_files: Files that were changed
            model: Ollama model to use

        Returns:
            {
                "task": "Add user login endpoint",
                "category": "api_endpoint",
                "pattern": "Use async/await, validate with joi, return JWT",
                "example_code": "...",
                "files": ["src/api/auth.ts"],
                "timestamp": "2025-01-15T10:30:00"
            }
        """
        if not modified_files:
            return None

        # Read first modified file for pattern extraction
        first_file = self.project_root / modified_files[0]
        if not first_file.exists():
            return None

        try:
            content = first_file.read_text()[:5000]  # First 5k chars
        except Exception:
            return None

        prompt = f"""A task was just completed: "{task_name}"

Modified file: {modified_files[0]}
```
{content}
```

Extract the reusable pattern in 2-3 sentences. Focus on:
- What approach was used
- Key libraries/patterns applied
- How it fits with the task

Also categorize it (api_endpoint, database, component, testing, validation, error_handling, etc.)

Format as JSON:
```json
{{
  "category": "...",
  "pattern": "...",
  "example_code": "..."
}}
```"""

        try:
            response = ollama.generate(
                model=model,
                prompt=prompt,
                options={"num_predict": 300, "temperature": 0.3}
            )

            text = response["response"]

            # Extract JSON
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0]
            elif "{" in text:
                json_str = text[text.find("{"):text.rfind("}")+1]
            else:
                return None

            data = json.loads(json_str)

            # Build pattern entry
            from datetime import datetime
            pattern = {
                "task": task_name,
                "category": data.get("category", "general"),
                "pattern": data.get("pattern", ""),
                "example_code": data.get("example_code", content[:500]),
                "files": modified_files,
                "timestamp": datetime.utcnow().isoformat(),
            }

            return pattern

        except Exception as e:
            print(f"  Pattern extraction failed: {e}")
            return None

    def add_pattern(self, pattern: Dict):
        """Add a pattern to the library."""
        if not pattern:
            return

        # Embed the pattern for semantic search
        pattern_text = f"{pattern['task']}. {pattern['pattern']}"
        embedding = get_embedding(pattern_text)

        if embedding:
            # Store in ChromaDB
            pattern_id = f"pattern_{len(self.patterns['patterns'])}"
            self.engine.collection.add(
                ids=[pattern_id],
                embeddings=[embedding],
                documents=[pattern["pattern"]],
                metadatas=[{
                    "type": "pattern",
                    "category": pattern["category"],
                    "task": pattern["task"],
                }]
            )

        # Also store in JSON for easy access
        self.patterns["patterns"].append(pattern)
        self._save_patterns()

        print(f"  ✓ Pattern learned: {pattern['category']} - {pattern['task']}")

    def find_relevant_patterns(
        self,
        task_name: str,
        task_context: str = "",
        top_k: int = 3
    ) -> List[Dict]:
        """
        Find patterns relevant to an upcoming task.

        Args:
            task_name: Task to implement
            task_context: Additional context
            top_k: Number of patterns to return

        Returns:
            List of relevant patterns with examples
        """
        query = f"{task_name}. {task_context}"
        embedding = get_embedding(query)

        if not embedding:
            return []

        try:
            results = self.engine.collection.query(
                query_embeddings=[embedding],
                n_results=top_k * 2,
                where={"type": "pattern"},
                include=["metadatas", "distances"]
            )

            # Filter and return
            patterns = []
            for i, meta in enumerate(results["metadatas"][0]):
                # Find full pattern in JSON store
                task = meta.get("task", "")
                for p in self.patterns["patterns"]:
                    if p["task"] == task:
                        patterns.append(p)
                        break

                if len(patterns) >= top_k:
                    break

            return patterns

        except Exception as e:
            print(f"  Pattern search failed: {e}")
            return []

    def get_patterns_by_category(self, category: str) -> List[Dict]:
        """Get all patterns in a category."""
        return [
            p for p in self.patterns["patterns"]
            if p["category"] == category
        ]

    def get_pattern_summary(self) -> Dict:
        """Get summary of learned patterns."""
        categories = {}
        for p in self.patterns["patterns"]:
            cat = p["category"]
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_patterns": len(self.patterns["patterns"]),
            "categories": categories,
            "recent": self.patterns["patterns"][-5:] if self.patterns["patterns"] else []
        }


def enhance_prompt_with_patterns(
    task: Dict,
    base_prompt: str,
    library: PatternLibrary
) -> str:
    """
    Add relevant patterns to a subagent prompt.

    Before:
        - Claude implements from scratch

    After:
        - Claude sees 3 similar patterns from past tasks
        - Follows established approach
        - Consistency maintained
    """
    task_name = task.get("name", "")
    task_context = task.get("context", "")

    relevant_patterns = library.find_relevant_patterns(
        task_name=task_name,
        task_context=task_context,
        top_k=3
    )

    if not relevant_patterns:
        return base_prompt

    pattern_section = [
        "",
        "<learned_patterns>",
        "The codebase has established these patterns from previous tasks.",
        "Follow these patterns to maintain consistency:",
        ""
    ]

    for i, p in enumerate(relevant_patterns, 1):
        pattern_section.append(f"### Pattern {i}: {p['task']}")
        pattern_section.append(f"**Category:** {p['category']}")
        pattern_section.append(f"**Approach:** {p['pattern']}")
        if p.get("example_code"):
            pattern_section.append("**Example:**")
            pattern_section.append("```")
            pattern_section.append(p["example_code"][:300])
            pattern_section.append("```")
        pattern_section.append("")

    pattern_section.append("</learned_patterns>")
    pattern_section.append("")

    # Insert patterns before instructions
    if "<instructions>" in base_prompt:
        parts = base_prompt.split("<instructions>")
        return parts[0] + "\n".join(pattern_section) + "<instructions>" + parts[1]
    else:
        return base_prompt + "\n".join(pattern_section)


# Hooks for ralph_tree.py integration:
"""
# In cmd_done() - after marking task complete:
def cmd_done():
    tree = load_tree()
    result = find_next_task(tree)
    task, path = result

    # Extract and store pattern
    library = PatternLibrary()
    modified_files = task.get("files", [])
    pattern = library.extract_pattern_from_task(
        task_name=task.get("name"),
        modified_files=modified_files
    )
    if pattern:
        library.add_pattern(pattern)

    mark_done(tree, path)
    save_tree(tree)

# In build_subagent_prompt() - before spawning:
def build_subagent_prompt(task, path, tree):
    base_prompt = ... # existing prompt

    # Add learned patterns
    library = PatternLibrary()
    enhanced_prompt = enhance_prompt_with_patterns(task, base_prompt, library)

    return enhanced_prompt
"""
