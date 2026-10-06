"""
api/routes/analyzer_999.py
POST /api/analyze/999 — analyze a 999 acknowledgment file.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.services import analyzer_999, audit
from backend.utils.file_handler import save_upload

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze/999")
async def analyze_999(file: UploadFile = File(...)):
    """
    Upload and analyze a 999 Implementation Acknowledgment.
    Returns Analysis999ResultSchema.
    """
    content = await file.read()
    raw = content.decode("utf-8", errors="replace")
    saved = save_upload(file.filename or "999.edi", content)

    try:
        result = analyzer_999.analyze_raw(raw, source_file=str(saved))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    audit.record(
        action="ANALYZE_999",
        module="analyzer_999",
        input_summary=f"file={file.filename}",
        result=f"status={result.overall_status}, transactions={len(result.transaction_analyses)}",
    )

    return result.model_dump(mode="json")
