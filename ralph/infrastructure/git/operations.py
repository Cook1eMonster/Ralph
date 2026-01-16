"""Git operations wrapper with Result-based error handling.

Provides clean interfaces for git operations, wrapping the existing
functions from storage.py.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ralph.domain.shared.result import Err, Ok, Result


@dataclass(frozen=True)
class GitStatus:
    """Result of a git status check.

    Attributes:
        is_git_repo: Whether the path is a git repository.
        has_remote: Whether a remote is configured.
        is_behind: Whether the local branch is behind remote.
        commits_behind: Number of commits behind remote.
    """

    is_git_repo: bool
    has_remote: bool = False
    is_behind: bool = False
    commits_behind: int = 0


@dataclass(frozen=True)
class PullResult:
    """Result of a git pull operation.

    Attributes:
        pulled: Whether changes were actually pulled.
        commits_pulled: Number of commits pulled.
        was_already_up_to_date: Whether repo was already up to date.
    """

    pulled: bool
    commits_pulled: int = 0
    was_already_up_to_date: bool = False


class GitOperations:
    """Git operations with Result-based error handling.

    Wraps git commands with clean interfaces and explicit error handling.
    Uses subprocess to execute git commands.

    Example:
        git = GitOperations()
        result = git.check_status(Path("/path/to/repo"))
        if isinstance(result, Ok):
            status = result.value
            if status.is_behind:
                pull_result = git.pull(Path("/path/to/repo"))
    """

    def __init__(self, timeout: int = 60) -> None:
        """Initialize git operations.

        Args:
            timeout: Default timeout in seconds for git commands.
        """
        self._timeout = timeout

    def check_status(self, path: Path) -> Result[GitStatus, str]:
        """Check the git status of a repository.

        Fetches from remote and checks if local is behind.

        Args:
            path: Path to the git repository.

        Returns:
            Ok(GitStatus) with status information if successful,
            Err(str) with error message if failed.
        """
        git_dir = path / ".git"

        # Check if it's a git repo
        if not git_dir.exists():
            return Ok(GitStatus(is_git_repo=False))

        try:
            # Check for remote
            remote_result = subprocess.run(
                ["git", "remote"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=10,
            )

            if not remote_result.stdout.strip():
                return Ok(GitStatus(is_git_repo=True, has_remote=False))

            # Fetch to update refs
            subprocess.run(
                ["git", "fetch"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

            # Check how many commits behind
            behind_result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..@{u}"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=10,
            )

            commits_behind = 0
            if behind_result.returncode == 0:
                commits_behind = int(behind_result.stdout.strip() or "0")

            return Ok(
                GitStatus(
                    is_git_repo=True,
                    has_remote=True,
                    is_behind=commits_behind > 0,
                    commits_behind=commits_behind,
                )
            )

        except subprocess.TimeoutExpired:
            return Err("Git operation timed out")
        except ValueError as e:
            return Err(f"Error parsing git output: {e}")
        except OSError as e:
            return Err(f"Git command failed: {e}")

    def pull(self, path: Path) -> Result[PullResult, str]:
        """Pull latest changes from remote.

        Attempts to pull from origin/main, falls back to origin/master.

        Args:
            path: Path to the git repository.

        Returns:
            Ok(PullResult) with pull information if successful,
            Err(str) with error message if failed.
        """
        # First check status
        status_result = self.check_status(path)
        if isinstance(status_result, Err):
            return status_result

        status = status_result.value

        if not status.is_git_repo:
            return Err("Not a git repository")

        if not status.has_remote:
            return Err("No remote configured")

        if not status.is_behind:
            return Ok(
                PullResult(
                    pulled=False,
                    commits_pulled=0,
                    was_already_up_to_date=True,
                )
            )

        try:
            # Try main first
            pull_result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=120,
            )

            if pull_result.returncode != 0:
                # Try master
                pull_result = subprocess.run(
                    ["git", "pull", "origin", "master"],
                    cwd=str(path),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

            if pull_result.returncode == 0:
                return Ok(
                    PullResult(
                        pulled=True,
                        commits_pulled=status.commits_behind,
                        was_already_up_to_date=False,
                    )
                )
            else:
                error_msg = pull_result.stderr.strip() or "Pull failed"
                return Err(error_msg)

        except subprocess.TimeoutExpired:
            return Err("Git pull timed out")
        except OSError as e:
            return Err(f"Git pull failed: {e}")

    def is_git_repo(self, path: Path) -> bool:
        """Check if a path is a git repository.

        Args:
            path: Path to check.

        Returns:
            True if the path contains a .git directory.
        """
        return (path / ".git").exists()

    def get_current_branch(self, path: Path) -> Result[str, str]:
        """Get the current branch name.

        Args:
            path: Path to the git repository.

        Returns:
            Ok(str) with branch name if successful,
            Err(str) with error message if failed.
        """
        if not self.is_git_repo(path):
            return Err("Not a git repository")

        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return Ok(result.stdout.strip())
            else:
                return Err(result.stderr.strip() or "Failed to get branch")

        except subprocess.TimeoutExpired:
            return Err("Git command timed out")
        except OSError as e:
            return Err(f"Git command failed: {e}")

    def create_branch(self, path: Path, branch_name: str) -> Result[None, str]:
        """Create and checkout a new branch.

        Args:
            path: Path to the git repository.
            branch_name: Name of the branch to create.

        Returns:
            Ok(None) if successful, Err(str) with error message if failed.
        """
        if not self.is_git_repo(path):
            return Err("Not a git repository")

        try:
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return Ok(None)
            else:
                return Err(result.stderr.strip() or "Failed to create branch")

        except subprocess.TimeoutExpired:
            return Err("Git command timed out")
        except OSError as e:
            return Err(f"Git command failed: {e}")

    def checkout_branch(self, path: Path, branch_name: str) -> Result[None, str]:
        """Checkout an existing branch.

        Args:
            path: Path to the git repository.
            branch_name: Name of the branch to checkout.

        Returns:
            Ok(None) if successful, Err(str) with error message if failed.
        """
        if not self.is_git_repo(path):
            return Err("Not a git repository")

        try:
            result = subprocess.run(
                ["git", "checkout", branch_name],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return Ok(None)
            else:
                return Err(result.stderr.strip() or "Failed to checkout branch")

        except subprocess.TimeoutExpired:
            return Err("Git command timed out")
        except OSError as e:
            return Err(f"Git command failed: {e}")
