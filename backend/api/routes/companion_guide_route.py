"""
api/routes/companion_guide_route.py
GET  /api/companion-guides        — list available guides
GET  /api/companion-guides/{type} — get rules for a transaction type
GET  /api/companion-guides/{type}/search — search rules by keyword
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.engines import companion_guide_engine

router = APIRouter(prefix="/api", tags=["companion-guides"])


@router.get("/companion-guides")
async def list_guides():
    """List all configured Companion Guides and their availability."""
    return {"guides": companion_guide_engine.list_available_guides()}


@router.get("/companion-guides/{transaction_type}")
async def get_guide_rules(transaction_type: str):
    """Get extracted rules for a given transaction type."""
    try:
        guide = companion_guide_engine.load_guide(transaction_type.upper())
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return guide.model_dump(mode="json")


@router.get("/companion-guides/{transaction_type}/search")
async def search_guide_rules(
    transaction_type: str,
    q: str = Query(..., description="Search keyword"),
):
    """Search guide rules by keyword."""
    results = companion_guide_engine.search_guide(transaction_type.upper(), q)
    return {"results": [r.model_dump(mode="json") for r in results], "count": len(results)}
