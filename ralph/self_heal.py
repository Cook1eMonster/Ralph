"""Self-healing module for Ralph.

Validates tasks against acceptance criteria and uses local AI to fix failures.
Uses Ollama with qwen2.5-coder:7b for code fixes.
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
MODEL = "qwen2.5-coder:7b"
MAX_ATTEMPTS = 3


@dataclass
class ValidationResult:
    """Result of running validation commands."""
    success: bool
    command: str
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0


@dataclass
class HealingResult:
    """Result of a self-healing attempt."""
    success: bool
    attempts: int
    file_fixed: Optional[str] = None
    validations: list[ValidationResult] = field(default_factory=list)
    error: Optional[str] = None


def run_command(command: str, cwd: Optional[str] = None, timeout: int = 60) -> ValidationResult:
    """Run a single validation command and capture output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        return ValidationResult(
            success=result.returncode == 0,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return ValidationResult(
            success=False,
            command=command,
            stderr=f"Command timed out after {timeout}s",
            return_code=-1,
        )
    except Exception as e:
        return ValidationResult(
            success=False,
            command=command,
            stderr=str(e),
            return_code=-1,
        )


def run_validation(commands: list[str], cwd: Optional[str] = None) -> tuple[bool, list[ValidationResult]]:
    """Run all acceptance commands and return results.

    Stops at first failure to focus the AI on one problem at a time.
    """
    results = []

    for cmd in commands:
        logger.info(f"Running validation: {cmd}")
        result = run_command(cmd, cwd=cwd)
        results.append(result)

        if not result.success:
            logger.warning(f"Validation failed: {cmd}")
            break

    all_passed = all(r.success for r in results)
    return all_passed, results


def format_error_for_ai(results: list[ValidationResult]) -> str:
    """Format validation results into error message for AI."""
    lines = []
    for r in results:
        if not r.success:
            lines.append(f"COMMAND FAILED: {r.command}")
            lines.append(f"EXIT CODE: {r.return_code}")
            if r.stdout.strip():
                lines.append(f"STDOUT:\n{r.stdout}")
            if r.stderr.strip():
                lines.append(f"STDERR:\n{r.stderr}")
    return "\n".join(lines)


def get_fix_from_ai(
    file_path: str,
    error_msg: str,
    task_context: str,
    model: str = MODEL,
) -> Optional[str]:
    """Send code + error to local Ollama and get the fixed file back."""
    try:
        import ollama
    except ImportError:
        logger.error("ollama package not installed")
        return None

    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return None

    code = path.read_text(encoding="utf-8")

    # Determine file type for syntax highlighting hint
    ext = path.suffix.lower()
    lang = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
    }.get(ext, "code")

    prompt = f"""You are a Self-Healing AI. A test failed in the project.
Fix the bug in the file provided below so the validation passes.

### TASK CONTEXT
{task_context}

### ERROR LOG
{error_msg}

### FILE TO FIX: {file_path}
### CURRENT CONTENT:
```{lang}
{code}
```

Return ONLY the complete fixed file content, starting with the first line and ending with the last line.
Do not include explanations, markdown formatting, or code fences - just the raw code.
"""

    try:
        logger.info(f"Requesting fix from {model}...")
        response = ollama.generate(model=model, prompt=prompt)
        fixed_code = response["response"].strip()

        # Extract code if wrapped in markdown
        if f"```{lang}" in fixed_code:
            fixed_code = fixed_code.split(f"```{lang}")[1].split("```")[0].strip()
        elif "```python" in fixed_code:
            fixed_code = fixed_code.split("```python")[1].split("```")[0].strip()
        elif "```" in fixed_code:
            fixed_code = fixed_code.split("```")[1].split("```")[0].strip()

        return fixed_code
    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        return None


def heal_file(
    file_path: str,
    acceptance_commands: list[str],
    task_context: str = "",
    cwd: Optional[str] = None,
    max_attempts: int = MAX_ATTEMPTS,
    model: str = MODEL,
) -> HealingResult:
    """Attempt to heal a file by running validation and applying AI fixes.

    Args:
        file_path: Path to the file to fix
        acceptance_commands: List of commands that must pass
        task_context: Context about the task for the AI
        cwd: Working directory for running commands
        max_attempts: Maximum number of fix attempts
        model: Ollama model to use for fixes

    Returns:
        HealingResult with success status and details
    """
    result = HealingResult(success=False, attempts=0, file_fixed=file_path)

    if not acceptance_commands:
        result.error = "No acceptance commands provided"
        return result

    path = Path(file_path)
    if not path.exists():
        result.error = f"File not found: {file_path}"
        return result

    for attempt in range(1, max_attempts + 1):
        result.attempts = attempt
        logger.info(f"Healing attempt {attempt}/{max_attempts}")

        # Run validation
        success, validations = run_validation(acceptance_commands, cwd=cwd)
        result.validations = validations

        if success:
            logger.info(f"Validation passed on attempt {attempt}")
            result.success = True
            return result

        if attempt == max_attempts:
            result.error = f"Max attempts ({max_attempts}) reached"
            return result

        # Get fix from AI
        error_msg = format_error_for_ai(validations)
        fixed_code = get_fix_from_ai(file_path, error_msg, task_context, model=model)

        if not fixed_code:
            result.error = "Failed to get fix from AI"
            return result

        # Apply fix
        try:
            logger.info(f"Applying fix to {file_path}")
            path.write_text(fixed_code, encoding="utf-8")
        except Exception as e:
            result.error = f"Failed to write fix: {e}"
            return result

    return result


def heal_task(
    task: dict,
    project_path: str,
    task_context: str = "",
    max_attempts: int = MAX_ATTEMPTS,
    model: str = MODEL,
) -> HealingResult:
    """Heal a task by fixing its files until acceptance criteria pass.

    Args:
        task: Task dict with 'files' and 'acceptance' keys
        project_path: Root path of the project
        task_context: Additional context about the task
        max_attempts: Maximum fix attempts per file
        model: Ollama model to use

    Returns:
        HealingResult with success status and details
    """
    acceptance = task.get("acceptance", [])
    files = task.get("files", [])

    if not acceptance:
        return HealingResult(
            success=False,
            attempts=0,
            error="No acceptance criteria for this task",
        )

    if not files:
        return HealingResult(
            success=False,
            attempts=0,
            error="No files specified for this task",
        )

    # Use first file as target (could be enhanced to detect which file has errors)
    target_file = files[0] if isinstance(files, list) else files

    # Make path absolute
    if not Path(target_file).is_absolute():
        target_file = str(Path(project_path) / target_file)

    return heal_file(
        file_path=target_file,
        acceptance_commands=acceptance,
        task_context=task_context,
        cwd=project_path,
        max_attempts=max_attempts,
        model=model,
    )
