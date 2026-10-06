"""
services/edi_validator.py
EDI Validation Orchestrator.
Runs validation in order: Syntax → HIPAA → Companion Guide → TP Mapping → Business Rules.
Processing Rule PR-02.
"""

from __future__ import annotations

from typing import Optional

from backend.engines import hipaa_engine, companion_guide_engine, business_rules_engine
from backend.engines import tp_mapping_engine
from backend.models.schemas import (
    EDITransactionSchema,
    ErrorSchema,
    RuleSource,
    Severity,
    TPMappingSchema,
    ValidationResultSchema,
    ValidationStatus,
)
from backend.services import edi_parser


def validate_raw(
    raw_content: str,
    source_file: str = "",
    partner_name: Optional[str] = None,
    transaction_type_override: Optional[str] = None,
) -> ValidationResultSchema:
    """
    Full validation pipeline for a raw EDI string.
    Steps: Parse → HIPAA → Companion Guide → TP Mapping → Business Rules.
    """
    all_errors: list[ErrorSchema] = []
    all_warnings: list[ErrorSchema] = []

    # --- Step 1: Parse ---
    try:
        transaction = edi_parser.parse(raw_content, source_file=source_file)
    except ValueError as exc:
        return ValidationResultSchema(
            status=ValidationStatus.FAIL,
            error_count=1,
            warning_count=0,
            errors=[ErrorSchema(
                severity=Severity.ERROR,
                segment="ISA",
                description=f"Parse failure: {exc}",
                source=RuleSource.SYNTAX,
                rule_reference="PARSE-001",
            )],
            source_file=source_file,
            transaction_type="UNKNOWN",
        )

    tx_type = transaction_type_override or transaction.transaction_type

    # --- Step 2: HIPAA Structural Validation ---
    hipaa_result = hipaa_engine.validate(transaction)
    all_errors.extend(hipaa_result.errors)
    all_warnings.extend(hipaa_result.warnings)

    # --- Step 3: Companion Guide Validation ---
    flat_segs = _flatten_segments(transaction)
    element_sep = _get_element_sep(transaction)

    cg_errors = companion_guide_engine.validate_against_guide(
        transaction_type=tx_type,
        segments=flat_segs,
        element_sep=element_sep,
    )
    all_errors.extend([e for e in cg_errors if e.severity == Severity.ERROR])
    all_warnings.extend([e for e in cg_errors if e.severity != Severity.ERROR])

    # --- Step 4: TP Mapping Validation (if mapping is loaded) ---
    if partner_name:
        mapping = tp_mapping_engine.get_mapping(partner_name, tx_type)
        if mapping:
            tp_errors = tp_mapping_engine.validate_against_mapping(
                flat_segs, mapping, element_sep
            )
            all_errors.extend([e for e in tp_errors if e.severity == Severity.ERROR])
            all_warnings.extend([e for e in tp_errors if e.severity != Severity.ERROR])

    # --- Step 5: Business Rules Validation ---
    biz_errors = business_rules_engine.validate(transaction, element_sep)
    all_errors.extend([e for e in biz_errors if e.severity == Severity.ERROR])
    all_warnings.extend([e for e in biz_errors if e.severity != Severity.ERROR])

    # Determine final status
    status = ValidationStatus.PASS
    if all_errors:
        status = ValidationStatus.FAIL
    elif all_warnings:
        status = ValidationStatus.WARNING

    return ValidationResultSchema(
        status=status,
        error_count=len(all_errors),
        warning_count=len(all_warnings),
        errors=all_errors,
        warnings=all_warnings,
        source_file=source_file,
        transaction_type=tx_type,
    )


def validate_file(
    file_path: str,
    partner_name: Optional[str] = None,
) -> ValidationResultSchema:
    """Validate an EDI file from disk."""
    from pathlib import Path
    content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    return validate_raw(content, source_file=file_path, partner_name=partner_name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_segments(transaction: EDITransactionSchema) -> list[str]:
    """Extract all raw segment strings from a parsed transaction, including
    the interchange/group envelope segments (ISA/IEA/GS/GE). Omitting these
    caused every companion-guide rule referencing an envelope segment (e.g.
    "the ISA segment must be present") to always false-positive as missing,
    even though the segment is clearly present in the raw file."""
    segs: list[str] = []
    if transaction.isa_segment:
        segs.append(transaction.isa_segment.raw)
    for group in transaction.groups:
        if group.gs_segment:
            segs.append(group.gs_segment.raw)
        for ts in group.transaction_sets:
            if ts.st_segment:
                segs.append(ts.st_segment.raw)
            for seg in ts.segments:
                segs.append(seg.raw)
            if ts.se_segment:
                segs.append(ts.se_segment.raw)
        if group.ge_segment:
            segs.append(group.ge_segment.raw)
    if transaction.iea_segment:
        segs.append(transaction.iea_segment.raw)
    return segs


def _get_element_sep(transaction: EDITransactionSchema) -> str:
    """Extract the element separator from the ISA segment."""
    if transaction.isa_segment and transaction.isa_segment.raw:
        raw = transaction.isa_segment.raw
        if len(raw) > 3:
            return raw[3]
    return "*"
