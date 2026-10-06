"""
utils/ai_gate.py
AI Consent Enforcement — AR-06, BR-04, AI Governance rules.
AI (GHCP only) requires explicit per-invocation user approval.
No AI call is made without a stored approval record.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from backend.utils.file_handler import AUDIT_LOG_DIR

_PENDING_DIR = AUDIT_LOG_DIR / "ai_pending"
_PENDING_DIR.mkdir(parents=True, exist_ok=True)


class AINotApprovedError(Exception):
    """Raised when an AI action is attempted without explicit user approval."""


def request_ai_approval(action: str, context: str = "") -> str:
    """
    Create a pending AI approval record.
    Returns request_id that must be confirmed before AI is invoked.
    """
    request_id = str(uuid.uuid4())
    record = {
        "request_id": request_id,
        "requested_action": action,
        "context": context,
        "approved": False,
        "timestamp": datetime.utcnow().isoformat(),
        "model": "Gemini",
        "result": None,
    }
    pending_file = _PENDING_DIR / f"{request_id}.json"
    pending_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return request_id


def approve_ai_request(request_id: str) -> dict:
    """
    Mark a pending AI request as approved.
    Returns the approval record.
    """
    pending_file = _PENDING_DIR / f"{request_id}.json"
    if not pending_file.exists():
        raise ValueError(f"AI request not found: {request_id}")
    record = json.loads(pending_file.read_text(encoding="utf-8"))
    record["approved"] = True
    record["approved_at"] = datetime.utcnow().isoformat()
    pending_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def check_ai_approved(request_id: str) -> bool:
    """Return True only if the request exists and was explicitly approved."""
    pending_file = _PENDING_DIR / f"{request_id}.json"
    if not pending_file.exists():
        return False
    record = json.loads(pending_file.read_text(encoding="utf-8"))
    return record.get("approved", False) is True


def require_ai_approval(request_id: str) -> None:
    """
    Guard function. Raises AINotApprovedError if not approved.
    Call this before every AI invocation.
    """
    if not check_ai_approved(request_id):
        raise AINotApprovedError(
            f"AI action requires explicit user approval. Request ID: {request_id}"
        )


def get_pending_requests() -> list[dict]:
    """Return all pending (unapproved) AI requests."""
    results = []
    for f in _PENDING_DIR.glob("*.json"):
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
            if not record.get("approved", False):
                results.append(record)
        except (json.JSONDecodeError, OSError):
            continue
    return results


def record_ai_result(request_id: str, result_summary: str) -> None:
    """Record the outcome of an approved AI invocation."""
    pending_file = _PENDING_DIR / f"{request_id}.json"
    if pending_file.exists():
        record = json.loads(pending_file.read_text(encoding="utf-8"))
        record["result"] = result_summary
        record["completed_at"] = datetime.utcnow().isoformat()
        pending_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
