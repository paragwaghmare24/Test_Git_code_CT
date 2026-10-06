"""
api/routes/batch.py
POST /api/batch — process a batch of EDI files.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from typing import List

from backend.services import batch_processor, edi_to_excel, audit
from backend.utils.file_handler import save_upload

router = APIRouter(prefix="/api", tags=["batch"])


@router.post("/batch")
async def process_batch(
    files: List[UploadFile] = File(...),
    partner_name: str = Form(default=""),
    export_excel: str = Form(default="true"),
):
    """
    Upload multiple EDI files for batch validation.
    Returns BatchExecutionSchema + optional Excel export path.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    saved_paths = []
    for f in files:
        content = await f.read()
        saved = save_upload(f.filename or "upload.edi", content)
        saved_paths.append(saved)

    batch, report = batch_processor.process_batch(
        saved_paths, partner_name=partner_name or None
    )

    excel_path = None
    if export_excel.lower() == "true":
        from backend.services import edi_parser
        pairs = []
        for result in batch.results:
            try:
                from pathlib import Path
                content = Path(result.source_file).read_text(encoding="utf-8", errors="replace")
                tx = edi_parser.parse(content, source_file=result.source_file)
                pairs.append((tx, result))
            except Exception:
                pass
        if pairs:
            out = edi_to_excel.export_to_excel(pairs, output_filename=f"batch_{batch.execution_id[:8]}.xlsx")
            excel_path = str(out)
            batch.report_path = str(out)

    audit.record(
        action="BATCH_PROCESS",
        module="batch_processor",
        input_summary=f"files={len(files)}, partner={partner_name}",
        result=f"pass={batch.pass_count}, fail={batch.fail_count}",
    )

    return {
        "batch": batch.model_dump(mode="json"),
        "report": report.model_dump(mode="json"),
        "excel_output": excel_path,
    }
