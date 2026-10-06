"""
api/routes/export.py
POST /api/export — export parsed EDI to Excel.
GET  /api/export/list — list generated Excel outputs.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.services import edi_parser, edi_validator, edi_to_excel, audit
from backend.utils.file_handler import save_upload, list_outputs

router = APIRouter(prefix="/api", tags=["export"])


@router.post("/export")
async def export_to_excel(
    file: UploadFile = File(...),
    partner_name: str = Form(default=""),
    run_validation: str = Form(default="true"),
):
    """
    Parse an EDI file and export it to Excel.
    Optionally runs validation and includes results in the export.
    Returns path to the generated .xlsx file.
    """
    content = await file.read()
    raw = content.decode("utf-8", errors="replace")
    saved = save_upload(file.filename or "upload.edi", content)

    try:
        transaction = edi_parser.parse(raw, source_file=str(saved))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    val_result = None
    if run_validation.lower() == "true":
        val_result = edi_validator.validate_raw(
            raw, source_file=str(saved), partner_name=partner_name or None
        )

    out_path = edi_to_excel.export_to_excel([(transaction, val_result)])

    audit.record(
        action="EXPORT_EXCEL",
        module="edi_to_excel",
        input_summary=f"file={file.filename}",
        result=f"output={out_path.name}",
    )

    return {"output_file": str(out_path), "file_name": out_path.name}


@router.get("/export/{filename}")
async def download_export(filename: str):
    """Download a previously generated Excel export."""
    from backend.utils.file_handler import OUTPUTS_DIR, _safe_path
    try:
        file_path = _safe_path(OUTPUTS_DIR, filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/export/list/all")
async def list_exports():
    """List all generated export files."""
    return {"files": list_outputs()}
