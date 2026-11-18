"""Shared FastAPI dependencies.

``require_principal`` is a module-level constant now that ``get_db`` lives in
:mod:`app.state` rather than the entry point, so there is no import cycle to
avoid by wrapping it in a factory at app-construction time.
"""

from __future__ import annotations

from .auth import build_principal_dependency
from .state import get_db

require_principal = build_principal_dependency(get_db)
