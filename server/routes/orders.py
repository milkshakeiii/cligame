"""
Orders & module-activation routes.

DEPRECATED: All mutation endpoints removed in Phase 8.5 (intent-based architecture).
Use POST /api/commands to enqueue commands instead.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/ships", tags=["orders"])
