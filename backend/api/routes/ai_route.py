"""
api/routes/ai_route.py
AI Governance Routes — request approval, approve, list pending.
All AI invocations require explicit user approval (AR-06, PR-10).
Only GHCP models permitted.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.utils.ai_gate import (
    approve_ai_request,
    get_pending_requests,
    record_ai_result,
    request_ai_approval,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AIRequestBody(BaseModel):
    action: str
    context: str = ""


@router.post("/request")
async def request_ai(body: AIRequestBody):
    """
    Create a pending AI approval request.
    Returns request_id — user must POST /approve/{request_id} before AI runs.
    """
    request_id = request_ai_approval(body.action, body.context)
    return {
        "request_id": request_id,
        "message": "AI request created. Please approve before proceeding.",
        "status": "PENDING",
    }


@router.post("/approve/{request_id}")
async def approve_ai(request_id: str):
    """Approve a pending AI request."""
    try:
        record = approve_ai_request(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"request_id": request_id, "approved": True, "record": record}


@router.get("/pending")
async def list_pending():
    """List all pending (unapproved) AI requests."""
    return {"pending": get_pending_requests()}
