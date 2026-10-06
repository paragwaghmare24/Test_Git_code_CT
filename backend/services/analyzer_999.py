"""
services/analyzer_999.py
999 Implementation Acknowledgment Analyzer.
Reads AK5/IK5 codes and maps to human-readable explanations.
Processing Rule PR-06.
"""

from __future__ import annotations

from backend.models.schemas import (
    AK5StatusSchema,
    Analysis999ResultSchema,
    Analysis999Schema,
    ErrorSchema,
    RuleSource,
    Severity,
)
from backend.services import edi_parser


# ---------------------------------------------------------------------------
# AK5/IK5 Code Tables
# ---------------------------------------------------------------------------

_AK5_01_CODES: dict[str, str] = {
    "A": "Accepted",
    "E": "Accepted But Errors Were Noted",
    "M": "Rejected, Message Authentication Code (MAC) Failed",
    "P": "Partially Accepted — At Least One Transaction Set Was Rejected",
    "R": "Rejected",
    "W": "Rejected, Assurance Failed Validity Tests",
    "X": "Rejected, Content After Decryption Could Not Be Analyzed",
}

_AK5_ERROR_CODES: dict[str, str] = {
    "1": "Transaction Set Not Supported",
    "2": "Transaction Set Trailer Missing",
    "3": "Transaction Set Control Number in Header and Trailer Do Not Match",
    "4": "Number of Included Segments Does Not Match Actual Count",
    "5": "One or More Segments in Error",
    "6": "Missing or Invalid Transaction Set Identifier",
    "7": "Missing or Invalid Transaction Set Control Number",
    "8": "Authentication Key Name Unknown",
    "9": "Encryption Key Name Unknown",
    "10": "Requested Service (Authentication or Encryption) Not Available",
    "11": "Unknown Security Recipient",
    "12": "Incorrect Message Length (Encryption Only)",
    "13": "Message Authentication Code Failed",
    "15": "Unknown Security Originator",
    "16": "Syntax Error in Decrypted Text",
    "17": "Security Not Supported",
    "18": "Transaction Set Not in Functional Group",
    "19": "Invalid Transaction Set Implementation Convention Reference",
    "23": "Transaction Set Control Number Not Unique within the Functional Group",
    "24": "S3E Security End Segment Missing for S3S Security Start Segment",
    "25": "S3S Security Start Segment Missing for S3E Security End Segment",
    "26": "S4E Security End Segment Missing for S4S Security Start Segment",
    "27": "S4S Security Start Segment Missing for S4E Security End Segment",
    "I5": "Implementation One or More Segments in Error",
    "I6": "Implementation Convention Not Supported",
}

_AK3_SEGMENT_ERROR_CODES: dict[str, str] = {
    "1": "Unrecognized Segment ID",
    "2": "Unexpected Segment",
    "3": "Mandatory Segment Missing",
    "4": "Loop Occurs Over Maximum Times",
    "5": "Segment Exceeds Maximum Use",
    "6": "Segment Not in Defined Transaction Set",
    "7": "Segment Not in Proper Sequence",
    "8": "Segment Has Data Element Errors",
    "I4": "Implementation 'Not Used' Segment Present",
    "I6": "Implementation-Dependent Segment Missing",
    "I7": "Implementation-Dependent Segment Present",
    "I8": "Looping Order Error",
    "I9": "Segment Exceeds Maximum Use as per Implementation Guideline",
}

_AK4_ELEMENT_ERROR_CODES: dict[str, str] = {
    "1": "Mandatory Data Element Missing",
    "2": "Conditional Required Data Element Missing",
    "3": "Too Many Data Elements",
    "4": "Data Element Too Short",
    "5": "Data Element Too Long",
    "6": "Invalid Character in Data Element",
    "7": "Invalid Code Value",
    "8": "Invalid Date",
    "9": "Invalid Time",
    "10": "Exclusion Condition Violated",
    "12": "Too Many Repetitions",
    "13": "Too Many Components",
    "I6": "Code Value Not Used in Implementation Guideline",
    "I7": "Implementation-Dependent Data Element Missing",
    "I8": "Implementation-Dependent Conditional Data Element Missing",
    "I9": "Implementation-Dependent Data Element Present",
    "I10": "Data Element Not Used in Implementation Guideline",
    "I11": "Implementation Too Few Repetitions",
    "I12": "Implementation Pattern Match Failure",
    "I13": "Data Element Value Not Referenced in this Implementation Convention",
}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _analyze_transaction_set(
    ts_segs: list[str], element_sep: str
) -> Analysis999Schema:
    """Analyze a single 999 transaction set."""
    errors: list[ErrorSchema] = []
    reason_codes: list[str] = []
    ak5_status: AK5StatusSchema | None = None
    transaction_set_id = ""
    overall_status = "Unknown"

    for seg in ts_segs:
        parts = seg.split(element_sep)
        seg_id = parts[0].strip()

        if seg_id == "AK2" and len(parts) > 1:
            transaction_set_id = parts[1].strip()

        elif seg_id == "AK3":
            # Segment error note
            seg_name = parts[1].strip() if len(parts) > 1 else ""
            seg_position = parts[2].strip() if len(parts) > 2 else ""
            error_code = parts[4].strip() if len(parts) > 4 else ""
            desc = _AK3_SEGMENT_ERROR_CODES.get(error_code, f"Unknown code {error_code}")
            errors.append(ErrorSchema(
                severity=Severity.ERROR,
                segment=seg_name,
                element=f"Position {seg_position}",
                description=f"Segment Error: {desc}",
                source=RuleSource.HIPAA,
                rule_reference=f"AK3-{error_code}",
            ))
            reason_codes.append(f"AK3:{error_code}")

        elif seg_id in {"AK4", "IK4"}:
            # Element error note
            elem_pos = parts[1].strip() if len(parts) > 1 else ""
            error_code = parts[3].strip() if len(parts) > 3 else ""
            bad_value = parts[4].strip() if len(parts) > 4 else ""
            desc = _AK4_ELEMENT_ERROR_CODES.get(error_code, f"Unknown code {error_code}")
            errors.append(ErrorSchema(
                severity=Severity.ERROR,
                segment="",
                element=f"Position {elem_pos}",
                description=f"Element Error: {desc}" + (f" (value: '{bad_value}')" if bad_value else ""),
                source=RuleSource.HIPAA,
                rule_reference=f"AK4-{error_code}",
            ))
            reason_codes.append(f"AK4:{error_code}")

        elif seg_id in {"AK5", "IK5"}:
            ak5_01 = parts[1].strip() if len(parts) > 1 else ""
            ak5_02 = parts[2].strip() if len(parts) > 2 else None
            ak5_03 = parts[3].strip() if len(parts) > 3 else None
            ak5_status = AK5StatusSchema(
                ak5_01=ak5_01,
                ak5_02=ak5_02,
                ak5_03=ak5_03,
                human_readable=_AK5_01_CODES.get(ak5_01, f"Unknown status '{ak5_01}'"),
            )
            overall_status = _AK5_01_CODES.get(ak5_01, ak5_01)

            # Add error details for rejection codes
            if ak5_02:
                desc = _AK5_ERROR_CODES.get(ak5_02, f"Unknown error code {ak5_02}")
                errors.append(ErrorSchema(
                    severity=Severity.ERROR,
                    segment="AK5",
                    element="AK502",
                    description=f"Transaction Set Error: {desc}",
                    source=RuleSource.HIPAA,
                    rule_reference=f"AK5-{ak5_02}",
                ))
                reason_codes.append(f"AK5:{ak5_02}")

    summary_parts = [f"Transaction Set '{transaction_set_id}': {overall_status}"]
    if reason_codes:
        summary_parts.append(f"Reason codes: {', '.join(reason_codes)}")

    return Analysis999Schema(
        transaction_set_id=transaction_set_id,
        status=overall_status,
        ak5_status=ak5_status,
        errors=errors,
        reason_codes=reason_codes,
        human_readable_summary=" | ".join(summary_parts),
    )


def analyze_raw(raw_content: str, source_file: str = "") -> Analysis999ResultSchema:
    """
    Parse and analyze a 999 Implementation Acknowledgment.
    Returns Analysis999ResultSchema.
    """
    transaction = edi_parser.parse(raw_content, source_file=source_file)
    element_sep = (
        transaction.isa_segment.raw[3]
        if transaction.isa_segment and len(transaction.isa_segment.raw) > 3
        else "*"
    )

    analyses: list[Analysis999Schema] = []
    overall_status = "Accepted"

    for group in transaction.groups:
        for ts in group.transaction_sets:
            seg_raws = [s.raw for s in ts.segments]
            analysis = _analyze_transaction_set(seg_raws, element_sep)
            analyses.append(analysis)
            # If any rejected, overall is rejected
            if analysis.ak5_status and analysis.ak5_status.ak5_01 in {"R", "M", "W", "X"}:
                overall_status = "Rejected"
            elif analysis.ak5_status and analysis.ak5_status.ak5_01 in {"P", "E"}:
                if overall_status == "Accepted":
                    overall_status = "Partial"

    return Analysis999ResultSchema(
        source_file=source_file,
        overall_status=overall_status,
        transaction_analyses=analyses,
    )


def analyze_file(file_path: str) -> Analysis999ResultSchema:
    """Analyze a 999 file from disk."""
    from pathlib import Path
    content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    return analyze_raw(content, source_file=file_path)
