"""
main.py
EDI Accelerator Platform — FastAPI Application Entry Point.
Phase 3 Layer 2: Navigation / Orchestrator.

Architecture: React UI → FastAPI → Processing Services → Rule Engines → Reports
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the Python path for relative imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import (
    validator,
    parser,
    generator,
    comparator,
    corrector,
    analyzer_999,
    analyzer_277ca,
    export,
    batch,
    audit_route,
    companion_guide_route,
    tp_mapping_route,
    ai_route,
    ai_operations,
    ai_tasks,
)

# ---------------------------------------------------------------------------
# Application Factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EDI Accelerator Platform",
    description=(
        "Healthcare EDI Generation, Parsing, Validation, Comparison, "
        "Correction, and Analysis Platform.\n\n"
        "Supported Transactions: 837P, 837I, 278, 834, 820, 999, 277CA\n\n"
        "AI is disabled by default. Requires explicit user approval per invocation."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow React dev server
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Route Registration
# ---------------------------------------------------------------------------

app.include_router(parser.router)
app.include_router(validator.router)
app.include_router(generator.router)
app.include_router(comparator.router)
app.include_router(corrector.router)
app.include_router(analyzer_999.router)
app.include_router(analyzer_277ca.router)
app.include_router(export.router)
app.include_router(batch.router)
app.include_router(audit_route.router)
app.include_router(companion_guide_route.router)
app.include_router(tp_mapping_route.router)
app.include_router(ai_route.router)
app.include_router(ai_operations.router)
app.include_router(ai_tasks.router)


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health_check():
    """Platform health check."""
    return {
        "status": "healthy",
        "platform": "EDI Accelerator Platform",
        "version": "1.0.0",
        "ai_mode": "disabled_by_default",
    }


@app.get("/", tags=["system"])
async def root():
    return {
        "message": "EDI Accelerator Platform is running.",
        "docs": "/docs",
        "health": "/health",
    }


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(Path(__file__).parent)],
    )
