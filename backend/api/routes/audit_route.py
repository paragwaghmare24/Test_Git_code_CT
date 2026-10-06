"""
api/routes/audit_route.py
GET /api/audit — retrieve audit log entries.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.services.audit import get_log

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit")
async def get_audit_log(date: str = Query(default=None, description="Date in YYYY-MM-DD format")):
    """Return audit log entries for a given date (defaults to today)."""
    entries = get_log(date)
    return {"entries": entries, "count": len(entries)}
