"""Token estimation logic.

Pure functions for estimating token usage of tasks.
All functions are pure - no I/O, no side effects.
"""

from typing import Literal

from pydantic import BaseModel

from .models import TaskNode

# =============================================================================
# Token Estimation Constants
# =============================================================================

TARGET_TOKENS = 60000  # Target tokens per task
TOKENS_PER_CHAR = 0.25  # ~4 chars per token average
BASE_OVERHEAD = 15000  # System prompt, tool definitions, etc.
TOKENS_PER_FILE = 2500  # Average file read
TOKENS_PER_TOOL_CALL = 500  # Average tool call overhead


# =============================================================================
# Value Objects
# =============================================================================

Complexity = Literal["low", "medium", "high"]


class TokenCount(BaseModel):
    """Value object representing token usage estimate for a task.

    This is a detailed breakdown of estimated token consumption,
    helping ensure tasks fit within context limits.
    """

    base_overhead: int
    context_tokens: int
    task_tokens: int
    file_reads: int
    tool_calls: int
    buffer: int
    total: int
    target: int
    fits: bool
    utilization: float
    complexity: Complexity


# =============================================================================
# Estimation Functions
# =============================================================================


def estimate_complexity(task: TaskNode) -> Complexity:
    """Estimate task complexity based on heuristics.

    Analyzes task name and file count to determine complexity level.
    This affects tool call estimates and overall token budget.

    Args:
        task: The task to analyze

    Returns:
        Complexity level: "low", "medium", or "high"
    """
    name_lower = task.name.lower()

    # High complexity indicators
    high_indicators = [
        "refactor",
        "rewrite",
        "migrate",
        "integration",
        "architecture",
        "security",
        "performance",
        "optimization",
    ]
    if any(ind in name_lower for ind in high_indicators):
        return "high"

    # Medium complexity indicators
    medium_indicators = [
        "implement",
        "create",
        "build",
        "add",
        "feature",
        "endpoint",
        "component",
    ]
    if any(ind in name_lower for ind in medium_indicators):
        return "medium"

    # File count also affects complexity
    if len(task.files) > 3:
        return "high"
    if len(task.files) > 1:
        return "medium"

    return "low"


def estimate_tokens(
    task: TaskNode,
    context: str,
    target: int = TARGET_TOKENS,
) -> TokenCount:
    """Estimate token usage for a task.

    Calculates a detailed breakdown of estimated token consumption
    including context, task description, file reads, and tool calls.

    Args:
        task: The task to estimate
        context: Accumulated context string
        target: Target token budget (default: TARGET_TOKENS)

    Returns:
        TokenCount with detailed breakdown
    """
    # Context tokens
    context_tokens = int(len(context) * TOKENS_PER_CHAR)

    # Task description tokens
    task_text = task.name
    if task.spec:
        task_text += f"\n{task.spec}"
    task_tokens = int(len(task_text) * TOKENS_PER_CHAR)

    # File reads estimate
    file_count = len(task.read_first) + len(task.files)
    file_reads = file_count * TOKENS_PER_FILE

    # Tool calls estimate (based on complexity)
    complexity = estimate_complexity(task)
    tool_multiplier = {"low": 8, "medium": 15, "high": 25}
    tool_calls = tool_multiplier[complexity] * TOKENS_PER_TOOL_CALL

    # Response buffer (for generated code, explanations)
    buffer = int(target * 0.2)

    # Total
    total = BASE_OVERHEAD + context_tokens + task_tokens + file_reads + tool_calls + buffer

    return TokenCount(
        base_overhead=BASE_OVERHEAD,
        context_tokens=context_tokens,
        task_tokens=task_tokens,
        file_reads=file_reads,
        tool_calls=tool_calls,
        buffer=buffer,
        total=total,
        target=target,
        fits=total <= target,
        utilization=round(total / target * 100, 1),
        complexity=complexity,
    )
