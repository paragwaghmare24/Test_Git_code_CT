"""
services/audit.py
Audit Service — records every API action to the file-system audit log.
Audit Rule: every action must be traceable (PR-09, AuditSchema).
"""

from __future__ import annotations

from datetime import datetime

from backend.models.schemas import AuditSchema
from backend.utils.file_handler import write_audit_entry, read_audit_log


def record(
    action: str,
    module: str,
    input_summary: str = "",
    result: str = "",
    user: str = "SYSTEM",
    ai_used: bool = False,
    ai_request_id: str | None = None,
) -> AuditSchema:
    """Create and persist an audit record."""
    entry = AuditSchema(
        user=user,
        action=action,
        module=module,
        input_summary=input_summary[:500],   # Cap length — no PHI in logs (SR-01)
        result=result[:500],
        ai_used=ai_used,
        ai_request_id=ai_request_id,
    )
    write_audit_entry(entry.model_dump(mode="json"))
    return entry


def get_log(date_str: str | None = None) -> list[dict]:
    """Retrieve audit log entries for a given date (defaults to today)."""
    return read_audit_log(date_str)
