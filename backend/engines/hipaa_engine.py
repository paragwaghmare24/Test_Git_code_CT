"""
engines/hipaa_engine.py
HIPAA X12 Structural and Syntax Validation Engine.
All rules are deterministic. No AI.
Enforces: VR-01 through VR-12 from LLM.md
"""

from __future__ import annotations

import re
from typing import Optional

from backend.models.schemas import (
    EDITransactionSchema,
    ErrorSchema,
    RuleSource,
    Severity,
    ValidationResultSchema,
    ValidationStatus,
)


# ---------------------------------------------------------------------------
# X12 Data Type Validators
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{8}$")          # CCYYMMDD
_ISA_DATE_RE = re.compile(r"^\d{6}$")       # YYMMDD — ISA09 only
_TIME_RE = re.compile(r"^\d{4}(\d{2})?$")  # HHMM or HHMMSS
_NPI_RE = re.compile(r"^\d{10}$")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")
_AN_RE = re.compile(r"^[\x20-\x7E]*$")     # Printable ASCII


def _is_valid_date(value: str) -> bool:
    if not _DATE_RE.match(value):
        return False
    try:
        y, m, d = int(value[:4]), int(value[4:6]), int(value[6:8])
        if m < 1 or m > 12 or d < 1 or d > 31:
            return False
    except ValueError:
        return False
    return True


def _is_valid_isa_date(value: str) -> bool:
    """ISA09 (Interchange Date) is uniquely fixed at 6-digit YYMMDD in X12 —
    every other date element in the standard (BHT, DTP, GS04, etc.) uses
    8-digit CCYYMMDD. Applying the CCYYMMDD check to ISA09 falsely rejects
    every valid interchange."""
    if not _ISA_DATE_RE.match(value):
        return False
    try:
        yy, m, d = int(value[:2]), int(value[2:4]), int(value[4:6])
        if m < 1 or m > 12 or d < 1 or d > 31:
            return False
    except ValueError:
        return False
    return True


def _is_valid_time(value: str) -> bool:
    return bool(_TIME_RE.match(value))


def _is_valid_npi(value: str) -> bool:
    return bool(_NPI_RE.match(value))


# ---------------------------------------------------------------------------
# ISA Segment Rules
# ---------------------------------------------------------------------------

_ISA_ELEMENT_COUNT = 16


def validate_isa(isa_segment: str, errors: list[ErrorSchema]) -> dict:
    """
    Validate the ISA (Interchange Control Header) segment.
    Returns parsed ISA fields as dict.
    VR-01: ISA must have exactly 16 elements.
    """
    if not isa_segment.startswith("ISA"):
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="ISA",
            element="ISA00",
            description="File does not begin with ISA segment.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-01",
            suggested_correction="Ensure file starts with 'ISA' segment."
        ))
        return {}

    sep = isa_segment[3]  # element separator is 4th char
    parts = isa_segment.split(sep)

    if len(parts) < _ISA_ELEMENT_COUNT + 1:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="ISA",
            element="ISA",
            description=f"ISA segment has {len(parts) - 1} elements; expected {_ISA_ELEMENT_COUNT}.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-01",
            suggested_correction=f"ISA segment must have exactly {_ISA_ELEMENT_COUNT} elements."
        ))
        return {}

    return {
        "element_sep": sep,
        "isa01": parts[1].strip(),   # Authorization Information Qualifier
        "isa02": parts[2].strip(),   # Authorization Information
        "isa03": parts[3].strip(),   # Security Information Qualifier
        "isa04": parts[4].strip(),   # Security Information
        "isa05": parts[5].strip(),   # Interchange ID Qualifier (Sender)
        "isa06": parts[6].strip(),   # Interchange Sender ID
        "isa07": parts[7].strip(),   # Interchange ID Qualifier (Receiver)
        "isa08": parts[8].strip(),   # Interchange Receiver ID
        "isa09": parts[9].strip(),   # Interchange Date
        "isa10": parts[10].strip(),  # Interchange Time
        "isa11": parts[11].strip(),  # Repetition Separator
        "isa12": parts[12].strip(),  # Interchange Control Version Number
        "isa13": parts[13].strip(),  # Interchange Control Number
        "isa14": parts[14].strip(),  # Acknowledgment Requested
        "isa15": parts[15].strip(),  # Interchange Usage Indicator
        "component_sep": parts[16][0] if len(parts) > 16 else ":",
    }


def validate_iea_match(isa_fields: dict, iea_segment: str, errors: list[ErrorSchema]) -> None:
    """VR-02: ISA13 must match IEA02."""
    if not iea_segment or not isa_fields:
        return
    sep = isa_fields.get("element_sep", "*")
    parts = iea_segment.split(sep)
    if len(parts) < 3:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="IEA",
            element="IEA02",
            description="IEA segment is malformed.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-02",
        ))
        return
    iea02 = parts[2].strip().rstrip("~").strip()
    isa13 = isa_fields.get("isa13", "")
    if isa13 != iea02:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="IEA",
            element="IEA02",
            description=f"Interchange Control Number mismatch: ISA13='{isa13}', IEA02='{iea02}'.",
            source=RuleSource.HIPAA,
            rule_reference="VR-02",
            suggested_correction=f"IEA02 must equal ISA13 value '{isa13}'."
        ))


def validate_gs_ge_match(gs_segment: str, ge_segment: str, element_sep: str,
                          errors: list[ErrorSchema]) -> Optional[str]:
    """VR-03: GS06 must match GE02."""
    if not gs_segment or not ge_segment:
        return None
    gs_parts = gs_segment.split(element_sep)
    ge_parts = ge_segment.split(element_sep)
    if len(gs_parts) < 7 or len(ge_parts) < 3:
        return None
    gs06 = gs_parts[6].strip()
    ge02 = ge_parts[2].strip().rstrip("~").strip()
    if gs06 != ge02:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="GE",
            element="GE02",
            description=f"Group Control Number mismatch: GS06='{gs06}', GE02='{ge02}'.",
            source=RuleSource.HIPAA,
            rule_reference="VR-03",
            suggested_correction=f"GE02 must equal GS06 value '{gs06}'."
        ))
    return gs06


def validate_st_se_match(st_segment: str, se_segment: str, element_sep: str,
                          errors: list[ErrorSchema]) -> None:
    """VR-04: ST02 must match SE02."""
    if not st_segment or not se_segment:
        return
    st_parts = st_segment.split(element_sep)
    se_parts = se_segment.split(element_sep)
    if len(st_parts) < 3 or len(se_parts) < 3:
        return
    st02 = st_parts[2].strip()
    se02 = se_parts[2].strip().rstrip("~").strip()
    if st02 != se02:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="SE",
            element="SE02",
            description=f"Transaction Set Control Number mismatch: ST02='{st02}', SE02='{se02}'.",
            source=RuleSource.HIPAA,
            rule_reference="VR-04",
            suggested_correction=f"SE02 must equal ST02 value '{st02}'."
        ))


def validate_se_segment_count(segments: list[str], se_segment: str,
                               element_sep: str, errors: list[ErrorSchema]) -> None:
    """VR-05: SE01 segment count must match actual segment count."""
    if not se_segment:
        return
    se_parts = se_segment.split(element_sep)
    if len(se_parts) < 2:
        return
    try:
        declared = int(se_parts[1].strip())
    except ValueError:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="SE",
            element="SE01",
            description="SE01 is not a valid integer.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-05",
        ))
        return
    actual = len(segments)
    if declared != actual:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="SE",
            element="SE01",
            description=f"Segment count mismatch: SE01='{declared}', actual='{actual}'.",
            source=RuleSource.HIPAA,
            rule_reference="VR-05",
            suggested_correction=f"SE01 should be {actual}."
        ))


# ---------------------------------------------------------------------------
# Element Data Type Validation Helpers
# ---------------------------------------------------------------------------

def check_date_element(segment_id: str, element_ref: str, value: str,
                        errors: list[ErrorSchema]) -> None:
    """VR-09: Validate date elements."""
    if value and not _is_valid_date(value):
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment=segment_id,
            element=element_ref,
            description=f"Invalid date format '{value}'. Expected CCYYMMDD.",
            source=RuleSource.HIPAA,
            rule_reference="VR-09",
            suggested_correction="Use format CCYYMMDD, e.g. 20240115."
        ))


def check_isa_date_element(value: str, errors: list[ErrorSchema]) -> None:
    """VR-09: Validate ISA09 (Interchange Date) — 6-digit YYMMDD, not CCYYMMDD."""
    if value and not _is_valid_isa_date(value):
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="ISA",
            element="ISA09",
            description=f"Invalid date format '{value}'. Expected YYMMDD (6 digits).",
            source=RuleSource.HIPAA,
            rule_reference="VR-09",
            suggested_correction="Use format YYMMDD, e.g. 260930."
        ))


def check_time_element(segment_id: str, element_ref: str, value: str,
                        errors: list[ErrorSchema]) -> None:
    """VR-10: Validate time elements."""
    if value and not _is_valid_time(value):
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment=segment_id,
            element=element_ref,
            description=f"Invalid time format '{value}'. Expected HHMM or HHMMSS.",
            source=RuleSource.HIPAA,
            rule_reference="VR-10",
            suggested_correction="Use format HHMM or HHMMSS, e.g. 1430."
        ))


def check_npi_element(segment_id: str, element_ref: str, value: str,
                       errors: list[ErrorSchema]) -> None:
    """VR-11: Validate NPI elements."""
    if value and not _is_valid_npi(value):
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment=segment_id,
            element=element_ref,
            description=f"Invalid NPI '{value}'. NPI must be 10 digits.",
            source=RuleSource.HIPAA,
            rule_reference="VR-11",
            suggested_correction="Provide a valid 10-digit NPI."
        ))


# ---------------------------------------------------------------------------
# Main HIPAA Validation Entry Point
# ---------------------------------------------------------------------------

def validate(transaction: EDITransactionSchema) -> ValidationResultSchema:
    """
    Run all HIPAA structural validations on a parsed EDI transaction.
    Returns a ValidationResultSchema.

    Uses the pre-parsed EDITransactionSchema instead of re-splitting raw_content.
    Re-splitting raw_content with a hardcoded or heuristically-detected segment
    terminator was unreliable for newline-terminated EDI files: after stripping
    newlines, position 105 of the flattened ISA yields the first character of the
    GS segment ('G') instead of the real terminator, causing all segment-level
    checks (NPI validation, GS/GE, ST/SE counts) to operate on garbage data.
    Unqualified NM1 errors from that code path bled onto every NM1 occurrence
    in the UI (including NM1*PR, NM1*40, etc.).
    """
    errors: list[ErrorSchema] = []
    warnings: list[ErrorSchema] = []

    if not transaction.raw_content.strip():
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="ISA",
            element="",
            description="EDI content is empty.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-01",
        ))
        return _build_result(errors, warnings, transaction)

    # ── ISA structural validation (VR-01, VR-09, VR-10) ────────────────────
    isa_raw = transaction.isa_segment.raw if transaction.isa_segment else ""
    if not isa_raw:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="ISA",
            description="No ISA segment found in EDI content.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-01",
        ))
        return _build_result(errors, warnings, transaction)

    isa_fields = validate_isa(isa_raw, errors)
    if not isa_fields:
        return _build_result(errors, warnings, transaction)

    element_sep = isa_fields["element_sep"]

    # VR-09: ISA interchange date (ISA09 is uniquely 6-digit YYMMDD, not CCYYMMDD)
    check_isa_date_element(isa_fields.get("isa09", ""), errors)
    # VR-10: ISA interchange time
    check_time_element("ISA", "ISA10", isa_fields.get("isa10", ""), errors)

    # ── IEA control number match (VR-02) ────────────────────────────────────
    if not transaction.iea_segment:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="IEA",
            description="IEA segment not found. Interchange is not properly terminated.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-02",
        ))
    else:
        validate_iea_match(isa_fields, transaction.iea_segment.raw, errors)

    # ── GS/GE functional group pair matching (VR-03) ────────────────────────
    gs_count = len(transaction.groups)
    ge_count = sum(1 for g in transaction.groups if g.ge_segment)
    if gs_count != ge_count:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="GS/GE",
            description=f"Unmatched GS/GE segments: {gs_count} GS vs {ge_count} GE.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-03",
        ))
    else:
        for group in transaction.groups:
            gs_raw = group.gs_segment.raw if group.gs_segment else ""
            ge_raw = group.ge_segment.raw if group.ge_segment else ""
            if gs_raw and ge_raw:
                validate_gs_ge_match(gs_raw, ge_raw, element_sep, errors)

    # ── ST/SE transaction set pair matching (VR-04) and segment count (VR-05)
    st_count = sum(len(g.transaction_sets) for g in transaction.groups)
    se_count = sum(
        sum(1 for ts in g.transaction_sets if ts.se_segment)
        for g in transaction.groups
    )
    if st_count != se_count:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="ST/SE",
            description=f"Unmatched ST/SE segments: {st_count} ST vs {se_count} SE.",
            source=RuleSource.SYNTAX,
            rule_reference="VR-04",
        ))
    else:
        for group in transaction.groups:
            for ts in group.transaction_sets:
                st_raw = ts.st_segment.raw if ts.st_segment else ""
                se_raw = ts.se_segment.raw if ts.se_segment else ""
                if st_raw and se_raw:
                    validate_st_se_match(st_raw, se_raw, element_sep, errors)
                # VR-05: SE01 segment count (includes ST and SE in the count)
                ts_seg_raws: list[str] = []
                if ts.st_segment:
                    ts_seg_raws.append(ts.st_segment.raw)
                ts_seg_raws.extend(seg.raw for seg in ts.segments)
                if ts.se_segment:
                    ts_seg_raws.append(ts.se_segment.raw)
                if se_raw:
                    validate_se_segment_count(ts_seg_raws, se_raw, element_sep, errors)

    # ── NPI validation — VR-11 ───────────────────────────────────────────────
    # Scan all NM1 segments for ID-code qualifier XX (= NPI).
    # The qualifier is encoded in the segment label (e.g. "NM1-85") so the UI
    # pins each NPI error to the correct NM1 occurrence only and never bleeds it
    # onto unrelated NM1 rows (NM1*PR, NM1*40, etc.).
    for group in transaction.groups:
        for ts in group.transaction_sets:
            for seg in ts.segments:
                if seg.segment_id == "NM1":
                    parts = [p.strip() for p in seg.raw.split(element_sep)]
                    entity_qualifier = parts[1] if len(parts) > 1 else ""
                    nm108 = parts[8] if len(parts) > 8 else ""
                    nm109 = parts[9].rstrip("~").strip() if len(parts) > 9 else ""
                    if nm108 == "XX":
                        seg_label = (
                            f"NM1-{entity_qualifier}" if entity_qualifier else "NM1"
                        )
                        check_npi_element(seg_label, "NM109", nm109, errors)

    return _build_result(errors, warnings, transaction)


def _build_result(errors: list[ErrorSchema], warnings: list[ErrorSchema],
                  transaction: EDITransactionSchema) -> ValidationResultSchema:
    status = ValidationStatus.PASS
    if errors:
        status = ValidationStatus.FAIL
    elif warnings:
        status = ValidationStatus.WARNING
    return ValidationResultSchema(
        status=status,
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors,
        warnings=warnings,
        source_file=transaction.source_file,
        transaction_type=transaction.transaction_type,
    )
