"""
services/reporting.py
Reporting Service — generates summary ReportSchema from validation/batch results.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.models.schemas import (
    BatchExecutionSchema,
    ReportSchema,
    ValidationResultSchema,
)


def build_validation_report(result: ValidationResultSchema) -> ReportSchema:
    """Build a ReportSchema from a single validation result."""
    return ReportSchema(
        summary={
            "source_file": result.source_file,
            "transaction_type": result.transaction_type,
            "status": result.status.value,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "executed_at": result.executed_at.isoformat(),
        },
        errors=result.errors,
        warnings=result.warnings,
        corrections=[],
        statistics={
            "total_issues": result.error_count + result.warning_count,
            "pass_rate": 0.0 if result.error_count > 0 else 1.0,
        },
        source_files=[result.source_file],
    )


def build_batch_report(batch: BatchExecutionSchema) -> ReportSchema:
    """Build a consolidated ReportSchema from a batch execution."""
    all_errors = []
    all_warnings = []
    for r in batch.results:
        all_errors.extend(r.errors)
        all_warnings.extend(r.warnings)

    pass_rate = (batch.pass_count / batch.file_count) if batch.file_count > 0 else 0.0

    return ReportSchema(
        summary={
            "execution_id": batch.execution_id,
            "file_count": batch.file_count,
            "pass_count": batch.pass_count,
            "fail_count": batch.fail_count,
            "warning_count": batch.warning_count,
            "started_at": batch.started_at.isoformat(),
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        },
        errors=all_errors,
        warnings=all_warnings,
        corrections=[],
        statistics={
            "pass_rate": round(pass_rate, 4),
            "fail_rate": round(1 - pass_rate, 4),
            "total_errors": len(all_errors),
            "total_warnings": len(all_warnings),
        },
        source_files=[r.source_file for r in batch.results],
    )
