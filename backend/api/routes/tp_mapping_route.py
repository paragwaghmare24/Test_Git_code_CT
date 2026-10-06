"""
api/routes/tp_mapping_route.py
POST /api/tp-mappings/upload — upload a TP mapping file
GET  /api/tp-mappings         — list loaded mappings
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.engines import tp_mapping_engine
from backend.utils.file_handler import save_upload

router = APIRouter(prefix="/api", tags=["tp-mappings"])


@router.post("/tp-mappings/upload")
async def upload_tp_mapping(
    file: UploadFile = File(...),
    partner_name: str = Form(...),
    transaction_type: str = Form(...),
):
    """
    Upload a Trading Partner mapping file (JSON or CSV).
    The mapping is stored in memory for the session.
    """
    content = await file.read()
    saved = save_upload(file.filename or "tp_mapping.json", content)

    try:
        mapping = tp_mapping_engine.load_mapping_from_file(
            saved, partner_name=partner_name, transaction_type=transaction_type.upper()
        )
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "partner_name": mapping.partner_name,
        "transaction_type": mapping.transaction_type,
        "entry_count": len(mapping.entries),
        "message": "TP mapping loaded successfully.",
    }


@router.get("/tp-mappings")
async def list_tp_mappings():
    """List all currently loaded TP mappings."""
    return {"mappings": tp_mapping_engine.list_loaded_mappings()}
