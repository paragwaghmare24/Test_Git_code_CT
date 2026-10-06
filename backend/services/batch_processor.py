"""
services/batch_processor.py
Batch Processing Service.
Processes multiple EDI files, generates consolidated report (PR-05).
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from backend.models.schemas import BatchExecutionSchema, ValidationResultSchema
from backend.services import edi_validator
from backend.services.reporting import build_batch_report


def process_batch(
    file_paths: list[str | Path],
    partner_name: Optional[str] = None,
) -> tuple[BatchExecutionSchema, object]:
    """
    Validate a list of EDI files.
    Returns (BatchExecutionSchema, ReportSchema).
    """
    execution_id = str(uuid.uuid4())
    results: list[ValidationResultSchema] = []
    pass_count = 0
    fail_count = 0
    warning_count = 0

    started_at = datetime.now(UTC)

    for fp in file_paths:
        fp = Path(fp)
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
            result = edi_validator.validate_raw(
                content, source_file=str(fp), partner_name=partner_name
            )
        except Exception as exc:
            from backend.models.schemas import ErrorSchema, RuleSource, Severity, ValidationStatus
            result = ValidationResultSchema(
                status=ValidationStatus.FAIL,
                error_count=1,
                warning_count=0,
                errors=[ErrorSchema(
                    severity=Severity.ERROR,
                    segment="",
                    description=f"Failed to process file: {exc}",
                    source=RuleSource.SYNTAX,
                    rule_reference="BATCH-ERR",
                )],
                source_file=str(fp),
                transaction_type="UNKNOWN",
            )

        results.append(result)

        from backend.models.schemas import ValidationStatus
        if result.status == ValidationStatus.PASS:
            pass_count += 1
        elif result.status == ValidationStatus.WARNING:
            warning_count += 1
        else:
            fail_count += 1

    completed_at = datetime.now(UTC)

    batch = BatchExecutionSchema(
        execution_id=execution_id,
        started_at=started_at,
        completed_at=completed_at,
        file_count=len(file_paths),
        pass_count=pass_count,
        fail_count=fail_count,
        warning_count=warning_count,
        results=results,
    )

    report = build_batch_report(batch)
    return batch, report
