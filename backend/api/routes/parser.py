"""
api/routes/parser.py
POST /api/parse — parse a raw EDI file into structured JSON.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.services import edi_parser, audit
from backend.utils.file_handler import save_upload

router = APIRouter(prefix="/api", tags=["parse"])


@router.post("/parse")
async def parse_edi(file: UploadFile = File(...)):
    """
    Upload and parse an EDI file.
    Returns EDITransactionSchema as JSON.
    """
    content = await file.read()
    try:
        raw = content.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}")

    saved = save_upload(file.filename or "upload.edi", content)

    try:
        transaction = edi_parser.parse(raw, source_file=str(saved))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    audit.record(
        action="PARSE",
        module="edi_parser",
        input_summary=f"file={file.filename}",
        result=f"type={transaction.transaction_type}, icn={transaction.interchange_control_number}",
    )

    return transaction.model_dump(mode="json")
