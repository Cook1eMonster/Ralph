"""JSON file storage with Result-based error handling.

Provides a thin wrapper around file I/O operations for JSON data,
returning Result types instead of raising exceptions.
"""

import json
from pathlib import Path
from typing import Any

from ralph.domain.shared.result import Err, Ok, Result


class JsonStorage:
    """Low-level JSON file I/O with Result-based error handling.

    This class wraps basic JSON operations (load/save) and returns
    Result types for explicit error handling. It does not contain
    any domain logic - just file I/O.

    Example:
        storage = JsonStorage()
        result = storage.load_json(Path("config.json"))
        if isinstance(result, Ok):
            data = result.value
        else:
            print(f"Error: {result.error}")
    """

    def load_json(self, path: Path) -> Result[dict[str, Any], str]:
        """Load JSON data from a file.

        Args:
            path: Path to the JSON file to read.

        Returns:
            Ok(dict) if successful, Err(str) with error message if failed.
        """
        try:
            if not path.exists():
                return Err(f"File not found: {path}")

            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return Ok(data)

        except json.JSONDecodeError as e:
            return Err(f"Invalid JSON in {path}: {e}")
        except PermissionError:
            return Err(f"Permission denied reading {path}")
        except OSError as e:
            return Err(f"Error reading {path}: {e}")

    def save_json(
        self,
        path: Path,
        data: dict[str, Any],
        indent: int = 2,
    ) -> Result[None, str]:
        """Save JSON data to a file.

        Args:
            path: Path to the JSON file to write.
            data: Dictionary to serialize as JSON.
            indent: JSON indentation level (default 2).

        Returns:
            Ok(None) if successful, Err(str) with error message if failed.
        """
        try:
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            content = json.dumps(data, indent=indent)
            path.write_text(content, encoding="utf-8")
            return Ok(None)

        except TypeError as e:
            return Err(f"Data not JSON serializable: {e}")
        except PermissionError:
            return Err(f"Permission denied writing {path}")
        except OSError as e:
            return Err(f"Error writing {path}: {e}")
