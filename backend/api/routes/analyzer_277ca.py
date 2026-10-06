"""
api/routes/analyzer_277ca.py
POST /api/analyze/277ca — analyze a 277CA claim acknowledgment.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.services import analyzer_277ca, audit
from backend.utils.file_handler import save_upload

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze/277ca")
async def analyze_277ca(file: UploadFile = File(...)):
    """
    Upload and analyze a 277CA Claim Acknowledgment.
    Returns Analysis277CAResultSchema.
    """
    content = await file.read()
    raw = content.decode("utf-8", errors="replace")
    saved = save_upload(file.filename or "277ca.edi", content)

    try:
        result = analyzer_277ca.analyze_raw(raw, source_file=str(saved))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    audit.record(
        action="ANALYZE_277CA",
        module="analyzer_277ca",
        input_summary=f"file={file.filename}",
        result=f"claims={len(result.claim_analyses)}",
    )

    return result.model_dump(mode="json")
