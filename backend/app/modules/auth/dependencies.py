"""Auth-module-local re-exports of the shared authentication dependencies.

Kept as a thin seam so other modules depend on `app.modules.auth.dependencies`
rather than reaching into `app.core.security` directly, preserving the
modular monolith's module boundaries.
"""

from app.core.security import CurrentUser, get_current_user, require_roles

__all__ = ["CurrentUser", "get_current_user", "require_roles"]
