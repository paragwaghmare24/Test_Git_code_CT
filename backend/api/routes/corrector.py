"""
api/routes/corrector.py
POST /api/correct/propose — propose corrections
POST /api/correct/apply   — apply approved corrections
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.services import edi_validator, auto_correction, audit
from backend.models.schemas import CorrectionSchema
from backend.utils.file_handler import save_upload, save_output

router = APIRouter(prefix="/api", tags=["correct"])


@router.post("/correct/propose")
async def propose_corrections(
    file: UploadFile = File(...),
    partner_name: str = Form(default=""),
):
    """
    Validate a file and return proposed corrections.
    Does NOT apply any changes (PR-04).
    """
    content = await file.read()
    raw = content.decode("utf-8", errors="replace")
    saved = save_upload(file.filename or "upload.edi", content)

    val_result = edi_validator.validate_raw(
        raw, source_file=str(saved), partner_name=partner_name or None
    )
    proposals = auto_correction.propose_corrections(val_result, raw)

    audit.record(
        action="PROPOSE_CORRECTIONS",
        module="auto_correction",
        input_summary=f"file={file.filename}",
        result=f"proposals={len(proposals.corrections)}",
    )

    return proposals.model_dump(mode="json")


class ApplyRequest(BaseModel):
    raw_edi: str
    corrections: list[CorrectionSchema]
    approval_token: str


@router.post("/correct/apply")
async def apply_corrections(request: ApplyRequest):
    """
    Apply user-approved corrections to EDI content.
    All corrections must have approved_by set (PR-04).
    """
    try:
        corrected = auto_correction.apply_corrections(
            request.raw_edi,
            request.corrections,
            request.approval_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    filename = f"corrected_{request.approval_token[:8]}.edi"
    saved = save_output(filename, corrected)

    audit.record(
        action="APPLY_CORRECTIONS",
        module="auto_correction",
        input_summary=f"corrections={len(request.corrections)}",
        result=f"output={filename}",
    )

    return {"corrected_file": str(saved), "edi": corrected}
