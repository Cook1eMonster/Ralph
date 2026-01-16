"""Result monad for explicit error handling in domain operations.

This module provides a Result type (also known as Either monad) for representing
operations that can succeed with a value or fail with an error. This approach
makes error handling explicit and composable, avoiding exceptions for expected
failure cases.

Example usage:
    >>> def divide(a: int, b: int) -> Result[float, str]:
    ...     if b == 0:
    ...         return Err("Division by zero")
    ...     return Ok(a / b)
    ...
    >>> result = divide(10, 2)
    >>> if is_ok(result):
    ...     print(f"Result: {result.value}")
    Result: 5.0
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Represents a successful result containing a value.

    Attributes:
        value: The success value of type T.
    """

    value: T


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """Represents a failed result containing an error.

    Attributes:
        error: The error value of type E.
    """

    error: E


# Type alias for a result that is either Ok[T] or Err[E]
# Using Union here as TypeVar aliases don't work with | syntax at runtime
Result = Union[Ok[T], Err[E]]  # noqa: UP007


def is_ok(result: Ok[T] | Err[E]) -> bool:
    """Check if a result is successful.

    Args:
        result: The result to check.

    Returns:
        True if the result is Ok, False if it is Err.
    """
    return isinstance(result, Ok)


def is_err(result: Ok[T] | Err[E]) -> bool:
    """Check if a result is an error.

    Args:
        result: The result to check.

    Returns:
        True if the result is Err, False if it is Ok.
    """
    return isinstance(result, Err)


def map_result(result: Ok[T] | Err[E], fn: Callable[[T], U]) -> Ok[U] | Err[E]:
    """Apply a function to the value inside an Ok result.

    If the result is Ok, applies fn to the value and returns Ok with the new value.
    If the result is Err, returns the Err unchanged.

    Args:
        result: The result to transform.
        fn: Function to apply to the Ok value.

    Returns:
        A new Result with the transformed value, or the original Err.
    """
    if isinstance(result, Ok):
        return Ok(fn(result.value))
    return result


def flat_map(result: Ok[T] | Err[E], fn: Callable[[T], Ok[U] | Err[E]]) -> Ok[U] | Err[E]:
    """Chain operations that return Results.

    If the result is Ok, applies fn to the value and returns its Result.
    If the result is Err, returns the Err unchanged.

    This is useful for sequencing operations that may each fail.

    Args:
        result: The result to chain from.
        fn: Function that takes the Ok value and returns a new Result.

    Returns:
        The Result from applying fn, or the original Err.
    """
    if isinstance(result, Ok):
        return fn(result.value)
    return result


def unwrap_or(result: Ok[T] | Err[E], default: T) -> T:
    """Extract the value from a Result, using a default if it's an error.

    Args:
        result: The result to unwrap.
        default: The value to return if result is Err.

    Returns:
        The Ok value if successful, otherwise the default.
    """
    if isinstance(result, Ok):
        return result.value
    return default
