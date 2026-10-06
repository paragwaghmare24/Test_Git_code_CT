"""
api/routes/generator.py
POST /api/generate       — generate EDI from a single structured input dict.
POST /api/generate/upload — generate EDI from an Excel (.xlsx) or JSON file.
                            Excel files with multiple data rows produce a
                            multi-ST batch EDI (one ST/SE per claim row).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.services import edi_generator, audit

router = APIRouter(prefix="/api", tags=["generate"])


class GenerateRequest(BaseModel):
    transaction_type: str
    data: dict


@router.post("/generate")
async def generate_edi(request: GenerateRequest):
    """
    Generate an EDI file from a single structured input dict.
    Raises 422 if any mandatory field is missing.
    Returns { edi, transaction_type }.
    """
    try:
        edi = edi_generator.generate(request.transaction_type, request.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    audit.record(
        action="GENERATE",
        module="edi_generator",
        input_summary=f"type={request.transaction_type}",
        result="generated",
    )

    return {
        "transaction_type": request.transaction_type,
        "edi": edi,
    }


@router.post("/generate/upload")
async def generate_edi_from_file(
    file: UploadFile = File(...),
    transaction_type: str = Form(...),
):
    """
    Generate EDI from an uploaded Excel (.xlsx) or JSON file.

    Excel layout (required):
      Row 1 — column headers matching the transaction-type field schema.
      Rows 2..N — one claim per row.

    • Single-row files (one data row) behave identically to the manual form.
    • Multi-row files produce a batch EDI: one ISA/GS envelope, one ST/SE
      per valid data row.  Rows with missing required fields are skipped;
      the response includes a per-row error list.

    JSON layout:
      Either a single flat dict {{ field: value }} (single claim)
      or a list of flat dicts [ {{...}}, {{...}} ] (batch).

    Returns:
      {{ edi, transaction_type, generated_count, total_rows,
         skipped_count, skipped_rows, parsed_data, missing_fields }}
    """
    content = await file.read()
    filename = (file.filename or "").lower()
    tx_type  = transaction_type.upper()

    records: list[dict] = []

    # ── Parse JSON ──────────────────────────────────────────────────────────
    if filename.endswith(".json"):
        try:
            raw = json.loads(content.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

        if isinstance(raw, dict):
            records = [raw]
        elif isinstance(raw, list):
            if not raw:
                raise HTTPException(status_code=400, detail="JSON array is empty.")
            if not isinstance(raw[0], dict):
                raise HTTPException(
                    status_code=400,
                    detail="JSON array must contain objects (dicts), not scalars.",
                )
            records = raw
        else:
            raise HTTPException(
                status_code=400,
                detail="JSON must be either a flat object {{ field: value }} "
                       "or an array of such objects for batch generation.",
            )

    # ── Parse Excel ──────────────────────────────────────────────────────────
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        try:
            import io
            import openpyxl

            wb   = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            ws   = wb.active
            rows = list(ws.iter_rows(values_only=True))

            if not rows:
                raise HTTPException(status_code=400, detail="Excel file is empty.")

            # Row 1 must be the header row
            raw_headers = rows[0]
            headers     = [
                str(c).strip().lower().replace(" ", "_") if c else ""
                for c in raw_headers
            ]
            # Drop completely empty header columns
            valid_cols = [i for i, h in enumerate(headers) if h]

            if not valid_cols:
                raise HTTPException(
                    status_code=400,
                    detail="Row 1 of the Excel file must contain column headers.",
                )

            data_rows = rows[1:]  # everything after the header
            # Skip rows that are entirely blank
            data_rows = [r for r in data_rows if any(c is not None and str(c).strip() != "" for c in r)]

            if not data_rows:
                raise HTTPException(
                    status_code=400,
                    detail="No data rows found. The Excel file must have at least "
                           "one data row beneath the header row.",
                )

            for row in data_rows:
                row_dict: dict = {}
                for i in valid_cols:
                    if i < len(row):
                        cell_val = row[i]
                        row_dict[headers[i]] = (
                            str(cell_val).strip() if cell_val is not None else ""
                        )
                    else:
                        row_dict[headers[i]] = ""
                records.append(row_dict)

        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Cannot parse Excel file: {exc}")

    else:
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx and .json files are supported for upload-based generation.",
        )

    total_rows = len(records)

    # ── Single-record path (backward-compatible) ─────────────────────────────
    if total_rows == 1:
        data    = records[0]
        required = edi_generator.get_required_fields(tx_type)
        missing  = [f for f in required if not data.get(f)]

        if missing:
            return {
                "transaction_type": tx_type,
                "edi": None,
                "generated_count": 0,
                "total_rows": 1,
                "skipped_count": 1,
                "skipped_rows": [{
                    "row": 2,
                    "missing_fields": missing,
                    "reason": f"Row 2: missing required fields — {', '.join(missing)}",
                }],
                "parsed_data": data,
                "missing_fields": missing,
                "error": (
                    f"Cannot generate EDI: the following required fields are "
                    f"missing or empty: {', '.join(missing)}"
                ),
            }

        try:
            edi = edi_generator.generate(tx_type, data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        audit.record(
            action="GENERATE_FROM_FILE",
            module="edi_generator",
            input_summary=f"type={tx_type}, file={file.filename}, rows=1",
            result="generated 1 claim",
        )

        return {
            "transaction_type": tx_type,
            "edi": edi,
            "generated_count": 1,
            "total_rows": 1,
            "skipped_count": 0,
            "skipped_rows": [],
            "parsed_data": data,
            "missing_fields": [],
        }

    # ── Multi-record batch path ───────────────────────────────────────────────
    try:
        edi, batch_errors, generated_count = edi_generator.generate_batch(tx_type, records)
    except ValueError as exc:
        # Every row failed — nothing generated
        raise HTTPException(status_code=422, detail=str(exc))

    skipped_count = len(batch_errors)

    audit.record(
        action="GENERATE_FROM_FILE_BATCH",
        module="edi_generator",
        input_summary=(
            f"type={tx_type}, file={file.filename}, "
            f"rows={total_rows}, generated={generated_count}, skipped={skipped_count}"
        ),
        result=f"generated {generated_count} claims, skipped {skipped_count}",
    )

    return {
        "transaction_type": tx_type,
        "edi": edi,
        "generated_count": generated_count,
        "total_rows": total_rows,
        "skipped_count": skipped_count,
        "skipped_rows": batch_errors,
        "parsed_data": records[0] if records else {},
        "missing_fields": [],
    }
