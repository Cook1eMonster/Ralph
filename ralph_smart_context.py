#!/usr/bin/env python3
"""
ralph_smart_context.py - Intelligent context assembly using local AI.

Before spawning a Claude subagent:
1. Use Ollama to summarize read_first files (if large)
2. Extract code patterns using local AI
3. Compress context to ~30% of original size
4. Send compressed context to Claude

Result: 3x more effective token usage.
"""

from pathlib import Path
from typing import List, Dict
import ollama


def extract_code_patterns(filepath: Path, model: str = "qwen2.5-coder:7b") -> Dict[str, str]:
    """
    Extract reusable patterns from a file using local AI.

    Returns:
        {
            "imports": "Common imports used",
            "error_handling": "How errors are handled",
            "testing_patterns": "Test structure",
            "naming_conventions": "Variable/function naming",
            "architecture": "Overall structure"
        }
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return {}

    prompt = f"""Analyze this code and extract reusable patterns. Be concise.

File: {filepath.name}
```
{content[:8000]}
```

Extract these patterns (2-3 lines each):
1. Imports: What libraries/modules are used?
2. Error handling: How are errors handled?
3. Testing: What testing patterns are used?
4. Naming: Variable/function naming conventions?
5. Architecture: Overall code organization pattern?

Format as JSON:
```json
{{
  "imports": "...",
  "error_handling": "...",
  "testing_patterns": "...",
  "naming_conventions": "...",
  "architecture": "..."
}}
```"""

    try:
        response = ollama.generate(
            model=model,
            prompt=prompt,
            options={"num_predict": 400, "temperature": 0.3}
        )

        # Extract JSON from response
        text = response["response"]
        import json

        # Find JSON block
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0]
        elif "{" in text:
            json_str = text[text.find("{"):text.rfind("}")+1]
        else:
            return {}

        return json.loads(json_str)
    except Exception as e:
        print(f"  Pattern extraction failed for {filepath}: {e}")
        return {}


def smart_compress_context(
    read_first_files: List[str],
    task_description: str,
    project_root: Path
) -> Dict[str, any]:
    """
    Intelligently compress context using local AI.

    Args:
        read_first_files: Files Claude should understand
        task_description: What Claude needs to implement
        project_root: Project root directory

    Returns:
        {
            "summaries": {filepath: summary},
            "patterns": {filepath: extracted_patterns},
            "key_snippets": {filepath: relevant_code_blocks},
            "context_size_reduction": percentage
        }
    """
    from ralph_context import ContextEngine, summarize_file

    engine = ContextEngine(project_root)
    compressed = {
        "summaries": {},
        "patterns": {},
        "key_snippets": {},
        "original_chars": 0,
        "compressed_chars": 0,
    }

    for filepath in read_first_files:
        full_path = project_root / filepath
        if not full_path.exists():
            continue

        try:
            content = full_path.read_text()
            original_size = len(content)
            compressed["original_chars"] += original_size

            # If file is large (>500 lines), summarize
            lines = content.split("\n")
            if len(lines) > 500:
                print(f"  Compressing {filepath} ({len(lines)} lines)...")

                # Get AI summary
                summary = summarize_file(full_path)
                compressed["summaries"][filepath] = summary
                compressed["compressed_chars"] += len(summary)

                # Extract patterns
                patterns = extract_code_patterns(full_path)
                if patterns:
                    compressed["patterns"][filepath] = patterns
                    compressed["compressed_chars"] += len(str(patterns))

            else:
                # Small file, include full content
                compressed["key_snippets"][filepath] = content
                compressed["compressed_chars"] += original_size

        except Exception as e:
            print(f"  Error processing {filepath}: {e}")

    # Calculate compression ratio
    if compressed["original_chars"] > 0:
        ratio = (compressed["compressed_chars"] / compressed["original_chars"]) * 100
        compressed["context_size_reduction"] = f"{ratio:.1f}%"
    else:
        compressed["context_size_reduction"] = "0%"

    return compressed


def build_compressed_prompt(task: Dict, compressed_context: Dict) -> str:
    """
    Build a Claude prompt using compressed context.

    Instead of:
        - Read file X (1000 lines) → 250k tokens

    Use:
        - Summary of X (50 lines) → 12k tokens
        - Patterns from X (20 lines) → 5k tokens
        - Key snippets (100 lines) → 25k tokens
        Total: 42k tokens (83% reduction!)
    """
    prompt_parts = [
        f"<task>{task.get('name', 'unnamed')}</task>",
        ""
    ]

    if task.get("spec"):
        prompt_parts.append(f"<spec>{task['spec']}</spec>")
        prompt_parts.append("")

    # Add file summaries
    if compressed_context["summaries"]:
        prompt_parts.append("<file_summaries>")
        prompt_parts.append("These files are large. Here are AI-generated summaries:")
        prompt_parts.append("")
        for filepath, summary in compressed_context["summaries"].items():
            prompt_parts.append(f"### {filepath}")
            prompt_parts.append(summary)
            prompt_parts.append("")
        prompt_parts.append("</file_summaries>")
        prompt_parts.append("")

    # Add extracted patterns
    if compressed_context["patterns"]:
        prompt_parts.append("<code_patterns>")
        prompt_parts.append("Follow these patterns found in the codebase:")
        prompt_parts.append("")
        for filepath, patterns in compressed_context["patterns"].items():
            prompt_parts.append(f"### {filepath}")
            for key, value in patterns.items():
                if value:
                    prompt_parts.append(f"**{key}:** {value}")
            prompt_parts.append("")
        prompt_parts.append("</code_patterns>")
        prompt_parts.append("")

    # Add key snippets (small files)
    if compressed_context["key_snippets"]:
        prompt_parts.append("<reference_files>")
        prompt_parts.append("Read these files completely (they are small):")
        prompt_parts.append("")
        for filepath, content in compressed_context["key_snippets"].items():
            prompt_parts.append(f"### {filepath}")
            prompt_parts.append("```")
            prompt_parts.append(content)
            prompt_parts.append("```")
            prompt_parts.append("")
        prompt_parts.append("</reference_files>")

    prompt_parts.append("<instructions>")
    prompt_parts.append("1. Follow the patterns shown above EXACTLY")
    prompt_parts.append("2. Read summaries to understand structure")
    prompt_parts.append("3. If you need full file contents, read them with the Read tool")
    prompt_parts.append("4. Implement the task according to spec")
    prompt_parts.append("5. Match existing code style precisely")
    prompt_parts.append("</instructions>")

    return "\n".join(prompt_parts)


# Example usage in ralph_tree.py:
"""
def build_subagent_prompt_smart(task, path, tree):
    from ralph_smart_context import smart_compress_context, build_compressed_prompt

    read_first = task.get("read_first", [])
    project_root = Path.cwd()

    # Compress context using local AI
    compressed = smart_compress_context(
        read_first_files=read_first,
        task_description=task.get("name", ""),
        project_root=project_root
    )

    print(f"  Context compressed: {compressed['context_size_reduction']}")

    # Build prompt with compressed context
    return build_compressed_prompt(task, compressed)
"""
