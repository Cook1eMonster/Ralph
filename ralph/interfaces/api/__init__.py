"""API interface for Ralph.

This module exports the FastAPI router and app factory.
Currently delegates to ralph.api for backward compatibility.
"""

from ralph.interfaces.api.routes import create_app, router

__all__ = ["router", "create_app"]
