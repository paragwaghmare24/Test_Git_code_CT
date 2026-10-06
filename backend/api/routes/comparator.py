"""
api/routes/comparator.py
POST /api/compare        — compare two EDI files.
POST /api/compare/export — compare and download Excel report.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from backend.services import edi_comparator, audit
from backend.utils.file_handler import save_upload

router = APIRouter(prefix="/api", tags=["compare"])


@router.post("/compare")
async def compare_edi(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
):
    """
    Upload two EDI files and compare them field by field.
    Returns ComparisonResultSchema.
    """
    content_a = await file_a.read()
    content_b = await file_b.read()

    try:
        raw_a = content_a.decode("utf-8", errors="replace")
        raw_b = content_b.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read files: {exc}")

    save_upload(file_a.filename or "a.edi", content_a)
    save_upload(file_b.filename or "b.edi", content_b)

    try:
        result = edi_comparator.compare_raw(
            raw_a, raw_b,
            file_a_name=file_a.filename or "File A",
            file_b_name=file_b.filename or "File B",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    audit.record(
        action="COMPARE",
        module="edi_comparator",
        input_summary=f"file_a={file_a.filename}, file_b={file_b.filename}",
        result=f"differences={result.total_differences}",
    )

    return result.model_dump(mode="json")


@router.post("/compare/export")
async def export_comparison_excel(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
):
    """
    Compare two EDI files and return a detailed Excel comparison report.
    """
    content_a = await file_a.read()
    content_b = await file_b.read()

    try:
        raw_a = content_a.decode("utf-8", errors="replace")
        raw_b = content_b.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read files: {exc}")

    try:
        result = edi_comparator.compare_raw(
            raw_a, raw_b,
            file_a_name=file_a.filename or "File A",
            file_b_name=file_b.filename or "File B",
        )
        excel_bytes = edi_comparator.generate_comparison_excel(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    audit.record(
        action="COMPARE_EXPORT",
        module="edi_comparator",
        input_summary=f"file_a={file_a.filename}, file_b={file_b.filename}",
        result=f"differences={result.total_differences}",
    )

    filename = f"comparison_{file_a.filename or 'A'}_vs_{file_b.filename or 'B'}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
