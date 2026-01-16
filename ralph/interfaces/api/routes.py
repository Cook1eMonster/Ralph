"""API routes for Ralph.

This module provides the REST API interface. Currently delegates to
ralph.api for backward compatibility, but the structure is in place
to migrate to application services.

The schemas are defined in ralph.interfaces.api.schemas and can be
imported from there for type hints. The actual route implementations
remain in ralph.api until they are migrated to use application services.

Example future migration:
    from ralph.application.services import ProjectService
    from ralph.interfaces.api.schemas import CreateProjectRequest

    @router.post("/projects")
    def create_project(req: CreateProjectRequest):
        service = ProjectService()
        return service.create_project(req.name, req.path, ...)
"""

from ralph.api import create_app, router

__all__ = ["router", "create_app"]
