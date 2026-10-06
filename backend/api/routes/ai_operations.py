"""
api/routes/ai_operations.py
AI-Powered Operation Endpoints — AI-assisted equivalents of the Python engine.
All endpoints require a pre-approved request_id from /api/ai/approve.
Governance: AR-06, BR-04. GHCP models only. No external APIs.

Routes:
  POST /api/ai/op/validate      — AI-assisted EDI validation
  POST /api/ai/op/generate      — AI-assisted EDI generation guidance
  POST /api/ai/op/analyze/999   — AI-assisted 999 analysis
  POST /api/ai/op/analyze/277ca — AI-assisted 277CA analysis
  POST /api/ai/op/compare       — AI-assisted EDI comparison
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.services import (
    edi_parser,
    edi_validator,
    analyzer_999,
    analyzer_277ca,
    edi_comparator,
    edi_generator,
    audit,
)
from backend.utils.ai_gate import AINotApprovedError, require_ai_approval, record_ai_result
from backend.utils.file_handler import save_upload
from backend.utils import gemini_client
from backend.api.routes.validator import _build_segment_detail

_AI_MODEL_LABEL = "Gemini" if gemini_client.is_available() else "rule-engine"

def _legacy_ai_disabled():
    raise HTTPException(410, "Legacy summary-only AI operations are retired. Use /api/ai/tasks with proposal approval.")


router = APIRouter(prefix="/api/ai/op", tags=["ai-operations"], dependencies=[Depends(_legacy_ai_disabled)])


# ---------------------------------------------------------------------------
# Helpers — AI explanation generators (rule-based, structured)
# ---------------------------------------------------------------------------

_AI_ERROR_HINTS: dict[str, str] = {
    "ISA": "Interchange envelope error — verify sender/receiver ISA IDs match the trading partner agreement and all 16 ISA fields are present.",
    "GS": "Functional Group error — ensure GS01 matches the transaction type (HC for 837, FA for 999) and GS02/03 match the partner agreement.",
    "NM1": "Name/ID segment error — check that the entity qualifier (NM101) is correct and the ID code (NM109) is the valid NPI, member ID, or TIN.",
    "CLM": "Claim segment error — CLM01 must be unique per submitter per day; CLM05 must use a valid place-of-service code.",
    "DTP": "Date error — verify DTP03 uses D8 format (CCYYMMDD) and the DTP01 qualifier matches the date type required.",
    "REF": "Reference error — confirm the qualifier (REF01) is approved by the companion guide and the value (REF02) is properly formatted.",
    "HI": "Diagnosis code error — ensure all ICD-10-CM codes in HI are valid, active, and use the ABK/ABF qualifiers without decimal points.",
    "SV1": "Service line error — verify CPT/HCPCS code is active and the amount (SV102) is numeric with correct decimal placement.",
    "SV2": "Institutional service line error — revenue code (SV201) must be 4 digits and match an active revenue code.",
    "PRV": "Provider taxonomy error — PRV03 must be a valid 10-digit NUCC taxonomy code approved for this transaction type.",
    "SBR": "Subscriber information error — SBR01 payer responsibility code must be P (primary), S (secondary), or T (tertiary).",
    "HL": "Hierarchical level error — HL02 parent ID must reference an existing HL01; HL03 level codes must follow 20/22/23 hierarchy for 837.",
    "SE": "Transaction set trailer error — SE01 segment count must match the actual segment count between ST and SE (inclusive).",
    "GE": "Functional group trailer error — GE01 must equal the count of transaction sets in the group.",
    "IEA": "Interchange trailer error — IEA01 must equal the count of functional groups and IEA02 must match ISA13.",
}

_AK5_MEANINGS: dict[str, str] = {
    "A": "Accepted — no errors found. No action required.",
    "E": "Accepted with Errors — transaction was accepted but contains recoverable errors. Review AK3/AK4 for the specific elements flagged.",
    "R": "Rejected — transaction was rejected and must be corrected and resubmitted. Review AK3/AK4 error segments for specific correction guidance.",
    "M": "Rejected, Message Authentication Code (MAC) Failed — contact trading partner for MAC validation issue.",
    "W": "Rejected, Not Supported — the transaction type is not supported by this trading partner. Verify transaction type agreement.",
    "X": "Rejected, Content After Interchange Trailer — malformed file; content was found after IEA. Correct file structure before resubmission.",
}

_AK9_MEANINGS: dict[str, str] = {
    "A": "Accepted — entire functional group accepted.",
    "E": "Accepted, Errors Noted — group accepted with errors. See AK5 for transaction-level detail.",
    "M": "Partially Accepted — some transaction sets accepted. Resubmit only the rejected transactions.",
    "R": "Rejected — entire functional group rejected. Correct all errors and resubmit the full group.",
    "P": "Partially Accepted (legacy) — equivalent to M.",
}

_IK4_ERROR_CODES: dict[str, str] = {
    "1": "Mandatory element missing — this element is required; provide a valid value.",
    "2": "Conditional element missing — a related element requires this one to be present.",
    "3": "Too many elements — reduce the number of elements in this segment.",
    "4": "Data element too short — increase the value length to meet the minimum requirement.",
    "5": "Data element too long — truncate the value to the maximum allowed length.",
    "6": "Invalid character in data element — remove non-printable or disallowed characters.",
    "7": "Invalid code value — replace with an allowed code from the companion guide value set.",
    "8": "Incorrect data element — the element value does not conform to the data type.",
    "9": "Unused segment present — remove the segment; it is not used in this implementation.",
    "10": "Too many segments in a loop — reduce segments to comply with loop repetition limit.",
    "12": "Loop not used — remove the entire loop; it is not permitted in this implementation.",
    "13": "Loop exceeds maximum uses — reduce the number of loop iterations.",
    "I5": "Implementation-defined — refer to the companion guide for specific correction requirements.",
    "I6": "Code value not in implementation-defined value set — use a code listed in the companion guide.",
    "I7": "Balancing error — numeric amounts do not balance across related segments.",
    "I8": "Implementation-defined qualifier error — qualifier not in the allowed set for this transaction.",
    "I9": "Implementation-dependent segment not in proper sequence — reorder segments per the companion guide.",
    "I10": "Implementation-dependent loop not in proper sequence — reorder loops per the companion guide.",
    "I11": "Implementation-dependent element not used — remove element; not used in this implementation.",
    "I12": "Too few occurrences — additional repetitions of this element are required.",
}

_STC_A1_MEANING = "Acknowledged / Receipt — claim received and is being processed."
_STC_A2_MEANING = "Accepted for Adjudication — claim accepted and forwarded to adjudication."
_STC_A3_MEANING = "Claim Accepted and Paid — no further action required."
_STC_A4_MEANING = "Accepted for Forwarding — claim accepted and forwarded to another payer."
_STC_R3_MEANING = "Claim Rejected — claim must be corrected and resubmitted."
_STC_R4_MEANING = "Secondary claim rejected — resubmit after primary payer EOB is applied."
_STC_DEFAULT = "Refer to the companion guide and ANSI X12 277CA specification for the exact action code meaning."

_STC_HINTS: dict[str, str] = {
    "A1": _STC_A1_MEANING, "A2": _STC_A2_MEANING, "A3": _STC_A3_MEANING,
    "A4": _STC_A4_MEANING, "R3": _STC_R3_MEANING, "R4": _STC_R4_MEANING,
}


def _ai_explain_error(error: dict) -> str:
    """Generate a structured AI explanation for a single validation error."""
    seg = error.get("segment", "").split("-")[0].strip().upper()
    desc = error.get("description", "")
    correction = error.get("suggested_correction", "")
    hint = _AI_ERROR_HINTS.get(seg, "")
    parts = [f"Error in {seg} segment: {desc}"]
    if hint:
        parts.append(f"Guidance: {hint}")
    if correction:
        parts.append(f"Suggested fix: {correction}")
    return " | ".join(parts)


def _ai_summary_for_validation(result_dict: dict, user_prompt: str) -> str:
    """Build an AI summary for a validation result."""
    status = result_dict.get("status", "UNKNOWN")
    error_count = result_dict.get("error_count", 0)
    warning_count = result_dict.get("warning_count", 0)
    tx_type = result_dict.get("transaction_type", "EDI")

    lines = [
        f"[AI Validation Analysis — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}]",
        f"Transaction: {tx_type} | Status: {status} | Errors: {error_count} | Warnings: {warning_count}",
        "",
    ]

    if user_prompt:
        lines += [f"Additional instruction: {user_prompt}", ""]

    if status == "PASS" and error_count == 0:
        lines += [
            "✓ File is fully compliant with X12 5010 rules and companion guide requirements.",
            "✓ All mandatory elements are present, code values are valid, and segment structure is correct.",
            "✓ No resubmission or correction action required.",
        ]
    elif status == "FAIL":
        lines += [
            f"✗ {error_count} validation error(s) must be corrected before submission.",
            "",
            "Priority Corrections (from AI analysis):",
        ]
        errors = result_dict.get("errors", [])
        for i, err in enumerate(errors[:10], 1):
            lines.append(f"  {i}. {_ai_explain_error(err)}")
        if len(errors) > 10:
            lines.append(f"  … and {len(errors) - 10} more errors. Resolve priority items first.")
    else:
        lines += [
            f"⚠ {warning_count} warning(s) detected. File may be submitted but review is recommended.",
        ]

    if warning_count > 0:
        lines += ["", "Warning Summary:"]
        for w in result_dict.get("warnings", [])[:5]:
            lines.append(f"  • {w.get('description', '')}")

    return "\n".join(lines)


def _ai_summary_for_999(result_dict: dict, user_prompt: str) -> str:
    """Build an AI enriched summary for 999 analysis."""
    lines = [
        f"[AI 999 Analysis — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}]",
        "",
    ]
    if user_prompt:
        lines += [f"Additional instruction: {user_prompt}", ""]

    tx_analyses = result_dict.get("transaction_analyses", [])
    for ta in tx_analyses:
        ik5 = ta.get("ik5_code", ta.get("ak5_code", ""))
        ctrl = ta.get("transaction_set_control_number", ta.get("control_number", "?"))
        status_text = _AK5_MEANINGS.get(ik5, f"Code {ik5} — refer to X12 5010 999 spec.")
        lines += [
            f"Transaction {ctrl}: {ik5} — {status_text}",
        ]
        seg_errors = ta.get("segment_errors", ta.get("errors", []))
        for err in seg_errors[:5]:
            ik4_code = str(err.get("ik4_code", err.get("ak4_code", err.get("error_code", ""))))
            elem_hint = _IK4_ERROR_CODES.get(ik4_code, "")
            seg_id = err.get("segment_id", err.get("segment", ""))
            lines.append(f"  • Segment {seg_id}: {elem_hint or err.get('description','')}")

    ak9 = result_dict.get("ak9_code", result_dict.get("overall_status", ""))
    ak9_text = _AK9_MEANINGS.get(ak9, "")
    if ak9:
        lines += ["", f"Group Status ({ak9}): {ak9_text}"]

    lines += ["", "Recommended Actions:"]
    if any(ta.get("ik5_code", ta.get("ak5_code", "")) == "R" for ta in tx_analyses):
        lines.append("  1. Correct all elements flagged in IK4/AK4 segments and resubmit the rejected transactions.")
        lines.append("  2. Verify segment counts in ST/SE match actual segments between those markers.")
        lines.append("  3. Confirm ISA/GS control numbers are sequential and unique for the trading partner.")
    else:
        lines.append("  ✓ All transactions accepted. No resubmission required.")

    return "\n".join(lines)


def _ai_summary_for_277ca(result_dict: dict, user_prompt: str) -> str:
    """Build an AI enriched summary for 277CA analysis."""
    lines = [
        f"[AI 277CA Analysis — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}]",
        "",
    ]
    if user_prompt:
        lines += [f"Additional instruction: {user_prompt}", ""]

    claim_analyses = result_dict.get("claim_analyses", [])
    accepted = [c for c in claim_analyses if str(c.get("claim_status_category_code", "")).startswith("A")]
    rejected = [c for c in claim_analyses if str(c.get("claim_status_category_code", "")).startswith("R")]

    lines += [
        f"Claims Reviewed: {len(claim_analyses)} total | Accepted: {len(accepted)} | Requires Action: {len(rejected)}",
        "",
    ]

    for claim in claim_analyses[:20]:
        claim_id = claim.get("claim_id", claim.get("patient_control_number", "?"))
        stc_code = claim.get("claim_status_category_code", "")
        stc_hint = _STC_HINTS.get(stc_code, _STC_DEFAULT)
        stc_detail = claim.get("claim_status_code", "")
        lines.append(f"  Claim {claim_id}: {stc_code}/{stc_detail} — {stc_hint}")

    if len(claim_analyses) > 20:
        lines.append(f"  … {len(claim_analyses) - 20} additional claims not shown.")

    lines += ["", "AI Recommended Actions:"]
    if rejected:
        lines.append(f"  • {len(rejected)} claim(s) require attention — correct and resubmit after resolving the denial reason.")
        lines.append("  • Contact the payer for claim-specific denial reason codes not listed in the 277CA.")
        lines.append("  • Verify NPI, member ID, and date of service against original submission.")
    if accepted:
        lines.append(f"  • {len(accepted)} claim(s) are proceeding — no action required unless payment differs from expected.")

    return "\n".join(lines)


def _ai_summary_for_comparison(result_dict: dict, user_prompt: str) -> str:
    """Build an AI enriched summary for comparison results."""
    total_diff = result_dict.get("total_differences", 0)
    records = result_dict.get("record_comparisons", [])
    matched = sum(1 for r in records if r.get("total_differences", 0) == 0)
    total_records = len(records)

    lines = [
        f"[AI Comparison Analysis — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}]",
        f"Records: {total_records} total | Matched: {matched} | With Differences: {total_records - matched}",
        f"Total Element Differences: {total_diff}",
        "",
    ]
    if user_prompt:
        lines += [f"Additional instruction: {user_prompt}", ""]

    # Categorize difference types
    diff_counts: dict[str, int] = {}
    segment_diffs: dict[str, int] = {}
    for rec in records:
        for diff in rec.get("differences", []):
            dtype = diff.get("difference_type", "VALUE_CHANGE")
            diff_counts[dtype] = diff_counts.get(dtype, 0) + 1
            seg = diff.get("segment", "").split("-")[0].strip().upper()
            if seg:
                segment_diffs[seg] = segment_diffs.get(seg, 0) + 1

    if diff_counts:
        lines += ["Difference Pattern Breakdown:"]
        for dtype, count in sorted(diff_counts.items(), key=lambda x: -x[1]):
            if dtype == "VALUE_CHANGE":
                lines.append(f"  • VALUE_CHANGE ({count}): Element values differ — likely resubmission, correction, or configuration change.")
            elif dtype == "MISSING":
                lines.append(f"  • MISSING ({count}): Segments present in File A but absent in File B — possible mapping gap or omission.")
            elif dtype == "EXTRA":
                lines.append(f"  • EXTRA ({count}): Segments in File B not in File A — additional data elements or new segments added.")
            elif dtype == "MISMATCH":
                lines.append(f"  • MISMATCH ({count}): Structural mismatch — segment identifiers or loop positions differ.")

    if segment_diffs:
        top_segs = sorted(segment_diffs.items(), key=lambda x: -x[1])[:5]
        lines += ["", f"Most-Affected Segments: {', '.join(f'{s}({c})' for s, c in top_segs)}"]
        for seg, _ in top_segs:
            hint = _AI_ERROR_HINTS.get(seg, "")
            if hint:
                lines.append(f"  {seg}: {hint}")

    lines += ["", "AI Business Impact Assessment:"]
    if total_diff == 0:
        lines.append("  ✓ Files are functionally identical. No reconciliation action required.")
    else:
        if "CLM" in segment_diffs:
            lines.append("  ⚠ CLM differences detected — verify claim IDs and amounts match source system before resubmission.")
        if "NM1" in segment_diffs:
            lines.append("  ⚠ NM1 (Name/ID) differences — check provider NPI, member ID, and payer ID consistency.")
        if "DTP" in segment_diffs:
            lines.append("  ⚠ DTP (Date) differences — verify service dates, admission dates, and authorization dates.")
        if "HI" in segment_diffs:
            lines.append("  ⚠ HI (Diagnosis) differences — confirm ICD-10 codes match the clinical documentation.")
        if "SV1" in segment_diffs or "SV2" in segment_diffs:
            lines.append("  ⚠ Service line (SV1/SV2) differences — reimbursement impact possible; reconcile with fee schedule.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Route: AI-assisted EDI Validation
# ---------------------------------------------------------------------------

@router.post("/validate")
async def ai_validate(
    file: UploadFile = File(...),
    request_id: str = Form(...),
    user_prompt: str = Form(default=""),
    partner_name: str = Form(default=""),
):
    """
    AI-assisted EDI validation.
    Runs the Python validation engine, then augments each error with AI explanations.
    Requires pre-approved request_id.
    """
    try:
        require_ai_approval(request_id)
    except (AINotApprovedError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    content = await file.read()
    try:
        raw = content.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}")

    saved = save_upload(file.filename or "upload.edi", content)

    result = edi_validator.validate_raw(
        raw,
        source_file=str(saved),
        partner_name=partner_name or None,
    )

    result_dict = result.model_dump(mode="json")

    # Build segment-level detail for UI visualization (mirrors Python validation endpoint)
    segments_detail: list[dict] = []
    try:
        transaction = edi_parser.parse(raw, source_file=str(saved))
        errors_raw = result_dict.get("errors", [])
        warnings_raw = result_dict.get("warnings", [])
        if transaction.isa_segment:
            segments_detail.append(_build_segment_detail(transaction.isa_segment, "*", errors_raw, warnings_raw))
        for group in transaction.groups:
            if group.gs_segment:
                segments_detail.append(_build_segment_detail(group.gs_segment, "*", errors_raw, warnings_raw))
            for ts in group.transaction_sets:
                if ts.st_segment:
                    segments_detail.append(_build_segment_detail(ts.st_segment, "*", errors_raw, warnings_raw))
                for seg in ts.segments:
                    segments_detail.append(_build_segment_detail(seg, "*", errors_raw, warnings_raw))
                if ts.se_segment:
                    segments_detail.append(_build_segment_detail(ts.se_segment, "*", errors_raw, warnings_raw))
            if group.ge_segment:
                segments_detail.append(_build_segment_detail(group.ge_segment, "*", errors_raw, warnings_raw))
        if transaction.iea_segment:
            segments_detail.append(_build_segment_detail(transaction.iea_segment, "*", errors_raw, warnings_raw))
    except Exception:
        pass
    result_dict["segments_detail"] = segments_detail
    result_dict["segment_count"] = len(segments_detail)

    # Augment each error with AI explanation
    for err in result_dict.get("errors", []):
        err["ai_explanation"] = _ai_explain_error(err)
    for warn in result_dict.get("warnings", []):
        warn["ai_explanation"] = _ai_explain_error(warn)

    rule_summary = _ai_summary_for_validation(result_dict, user_prompt)
    gemini_text, gemini_error = gemini_client.generate(
        gemini_client.analysis_prompt_for_validation(result_dict, user_prompt)
    )

    result_dict["ai_generated"] = True
    result_dict["ai_summary"] = gemini_text if gemini_text else rule_summary
    result_dict["ai_model"] = _AI_MODEL_LABEL
    result_dict["ai_model_status"] = "ok" if gemini_text else "failed"
    if gemini_error:
        result_dict["ai_error"] = gemini_error
    result_dict["ai_timestamp"] = datetime.utcnow().isoformat()

    record_ai_result(request_id, f"AI Validation: {result.status} — {result.error_count} errors, {result.warning_count} warnings")
    audit.record(
        action="AI_VALIDATE",
        module="AI_OPERATIONS",
        input_summary=f"file={file.filename}, request_id={request_id}",
        result=f"status={result.status}, errors={result.error_count}, warnings={result.warning_count}",
        ai_used=True,
        ai_request_id=request_id,
    )

    return JSONResponse(content=result_dict)


# ---------------------------------------------------------------------------
# Route: AI-assisted 999 Analysis
# ---------------------------------------------------------------------------

@router.post("/analyze/999")
async def ai_analyze_999(
    file: UploadFile = File(...),
    request_id: str = Form(...),
    user_prompt: str = Form(default=""),
):
    """
    AI-assisted 999 acknowledgment analysis.
    Runs the Python 999 analyzer and augments each transaction with AI explanations.
    Requires pre-approved request_id.
    """
    try:
        require_ai_approval(request_id)
    except (AINotApprovedError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    content = await file.read()
    try:
        raw = content.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}")

    saved = save_upload(file.filename or "upload.edi", content)

    result = analyzer_999.analyze(raw)
    result_dict = result if isinstance(result, dict) else result.model_dump(mode="json")

    # Augment transaction analyses with AI explanations
    for ta in result_dict.get("transaction_analyses", []):
        ik5 = ta.get("ik5_code", ta.get("ak5_code", ""))
        ta["ai_status_explanation"] = _AK5_MEANINGS.get(ik5, f"Code {ik5}: refer to X12 5010 999 spec.")
        for err in ta.get("segment_errors", ta.get("errors", [])):
            ik4_code = str(err.get("ik4_code", err.get("ak4_code", err.get("error_code", ""))))
            err["ai_explanation"] = _IK4_ERROR_CODES.get(ik4_code, "Refer to companion guide for this error code.")

    ak9 = result_dict.get("ak9_code", result_dict.get("overall_status", ""))
    result_dict["ai_group_status_explanation"] = _AK9_MEANINGS.get(ak9, "")

    rule_summary = _ai_summary_for_999(result_dict, user_prompt)
    gemini_text, gemini_error = gemini_client.generate(
        gemini_client.analysis_prompt_for_999(result_dict, user_prompt)
    )

    result_dict["ai_generated"] = True
    result_dict["ai_summary"] = gemini_text if gemini_text else rule_summary
    result_dict["ai_model"] = _AI_MODEL_LABEL
    result_dict["ai_model_status"] = "ok" if gemini_text else "failed"
    if gemini_error:
        result_dict["ai_error"] = gemini_error
    result_dict["ai_timestamp"] = datetime.utcnow().isoformat()

    record_ai_result(request_id, f"AI 999 Analysis: {len(result_dict.get('transaction_analyses', []))} transactions reviewed")
    audit.record(
        action="AI_ANALYZE_999",
        module="AI_OPERATIONS",
        input_summary=f"file={file.filename}, request_id={request_id}",
        result=f"transactions_reviewed={len(result_dict.get('transaction_analyses', []))}",
        ai_used=True,
        ai_request_id=request_id,
    )

    return JSONResponse(content=result_dict)


# ---------------------------------------------------------------------------
# Route: AI-assisted 277CA Analysis
# ---------------------------------------------------------------------------

@router.post("/analyze/277ca")
async def ai_analyze_277ca(
    file: UploadFile = File(...),
    request_id: str = Form(...),
    user_prompt: str = Form(default=""),
):
    """
    AI-assisted 277CA claim acknowledgment analysis.
    Runs the Python 277CA analyzer and augments each claim with AI explanations.
    Requires pre-approved request_id.
    """
    try:
        require_ai_approval(request_id)
    except (AINotApprovedError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    content = await file.read()
    try:
        raw = content.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}")

    saved = save_upload(file.filename or "upload.edi", content)

    result = analyzer_277ca.analyze(raw)
    result_dict = result if isinstance(result, dict) else result.model_dump(mode="json")

    # Augment claim analyses with AI action guidance
    for claim in result_dict.get("claim_analyses", []):
        stc_code = claim.get("claim_status_category_code", "")
        claim["ai_action_guidance"] = _STC_HINTS.get(stc_code, _STC_DEFAULT)

    rule_summary = _ai_summary_for_277ca(result_dict, user_prompt)
    gemini_text, gemini_error = gemini_client.generate(
        gemini_client.analysis_prompt_for_277ca(result_dict, user_prompt)
    )

    result_dict["ai_generated"] = True
    result_dict["ai_summary"] = gemini_text if gemini_text else rule_summary
    result_dict["ai_model"] = _AI_MODEL_LABEL
    result_dict["ai_model_status"] = "ok" if gemini_text else "failed"
    if gemini_error:
        result_dict["ai_error"] = gemini_error
    result_dict["ai_timestamp"] = datetime.utcnow().isoformat()

    record_ai_result(request_id, f"AI 277CA Analysis: {len(result_dict.get('claim_analyses', []))} claims reviewed")
    audit.record(
        action="AI_ANALYZE_277CA",
        module="AI_OPERATIONS",
        input_summary=f"file={file.filename}, request_id={request_id}",
        result=f"claims_reviewed={len(result_dict.get('claim_analyses', []))}",
        ai_used=True,
        ai_request_id=request_id,
    )

    return JSONResponse(content=result_dict)


# ---------------------------------------------------------------------------
# Route: AI-assisted EDI Comparison
# ---------------------------------------------------------------------------

@router.post("/compare")
async def ai_compare(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    request_id: str = Form(...),
    user_prompt: str = Form(default=""),
):
    """
    AI-assisted EDI comparison.
    Runs the Python comparison engine and augments results with AI pattern analysis.
    Requires pre-approved request_id.
    """
    try:
        require_ai_approval(request_id)
    except (AINotApprovedError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    content_a = await file_a.read()
    content_b = await file_b.read()

    try:
        raw_a = content_a.decode("utf-8", errors="replace")
        raw_b = content_b.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read files: {exc}")

    saved_a = save_upload(file_a.filename or "file_a.edi", content_a)
    saved_b = save_upload(file_b.filename or "file_b.edi", content_b)

    result = edi_comparator.compare(raw_a, raw_b, str(saved_a), str(saved_b))
    result_dict = result if isinstance(result, dict) else result.model_dump(mode="json")

    # Augment each difference with AI resolution guidance
    for diff in result_dict.get("differences", []):
        seg = diff.get("segment", "").split("-")[0].strip().upper()
        hint = _AI_ERROR_HINTS.get(seg, "")
        if hint:
            diff["ai_resolution_hint"] = hint
        elif diff.get("difference_type") == "MISSING":
            diff["ai_resolution_hint"] = "Segment present in File A but absent in File B — check if this is an optional segment that was intentionally omitted."
        elif diff.get("difference_type") == "EXTRA":
            diff["ai_resolution_hint"] = "Segment in File B not present in File A — verify this addition is intentional and supported by the companion guide."
        else:
            diff["ai_resolution_hint"] = "Compare values against source system data to determine which file is correct."

    for rec in result_dict.get("record_comparisons", []):
        for diff in rec.get("differences", []):
            seg = diff.get("segment", "").split("-")[0].strip().upper()
            hint = _AI_ERROR_HINTS.get(seg, "")
            if hint:
                diff["ai_resolution_hint"] = hint

    rule_summary = _ai_summary_for_comparison(result_dict, user_prompt)
    gemini_text, gemini_error = gemini_client.generate(
        gemini_client.analysis_prompt_for_comparison(result_dict, user_prompt)
    )

    result_dict["ai_generated"] = True
    result_dict["ai_summary"] = gemini_text if gemini_text else rule_summary
    result_dict["ai_model"] = _AI_MODEL_LABEL
    result_dict["ai_model_status"] = "ok" if gemini_text else "failed"
    if gemini_error:
        result_dict["ai_error"] = gemini_error
    result_dict["ai_timestamp"] = datetime.utcnow().isoformat()

    total_diff = result_dict.get("total_differences", 0)
    record_ai_result(request_id, f"AI Comparison: {total_diff} differences found")
    audit.record(
        action="AI_COMPARE",
        module="AI_OPERATIONS",
        input_summary=f"file_a={file_a.filename}, file_b={file_b.filename}, request_id={request_id}",
        result=f"total_differences={total_diff}",
        ai_used=True,
        ai_request_id=request_id,
    )

    return JSONResponse(content=result_dict)


# ---------------------------------------------------------------------------
# Route: AI-assisted EDI Generation Guidance
# ---------------------------------------------------------------------------

_GEN_FIELD_ALIASES: dict[str, str] = {
    "sender id": "sender_id",
    "receiver id": "receiver_id",
    "billing provider name": "billing_provider_name",
    "billing provider npi": "billing_provider_npi",
    "subscriber last name": "subscriber_last_name",
    "subscriber first name": "subscriber_first_name",
    "subscriber id": "subscriber_id",
    "member id": "member_id",
    "dob": "dob",
    "date of birth": "dob",
    "gender": "gender",
    "claim number": "claim_number",
    "claim amount": "claim_amount",
    "diagnosis code": "diagnosis_code",
    "procedure code": "procedure_code",
    "revenue code": "revenue_code",
    "service date": "service_date",
    "service type": "service_type",
    "place of service": "place_of_service",
    "rendering provider npi": "rendering_provider_npi",
    "authorization number": "authorization_number",
    "type of bill": "type_of_bill",
}


def _normalize_field_name(raw_name: str) -> str:
    name = (raw_name or "").strip().lower()
    collapsed = re.sub(r"\s+", " ", name)
    if collapsed in _GEN_FIELD_ALIASES:
        return _GEN_FIELD_ALIASES[collapsed]
    return re.sub(r"[^a-z0-9]+", "_", collapsed).strip("_")


def _extract_prompt_updates(user_prompt: str) -> dict[str, str]:
    """Extract prompt-driven field updates from natural language instructions."""
    updates: dict[str, str] = {}
    prompt = (user_prompt or "").strip()
    if not prompt:
        return updates

    pattern_cmd = re.compile(
        r"(?:set|change|update|replace)\s+([a-zA-Z0-9 _\-/]+?)\s*(?:to|=)\s*([^\n;,]+)",
        re.IGNORECASE,
    )
    for match in pattern_cmd.finditer(prompt):
        field = _normalize_field_name(match.group(1))
        value = match.group(2).strip().strip('"\'')
        if field and value:
            updates[field] = value

    for line in prompt.splitlines():
        if ":" not in line:
            continue
        left, right = line.split(":", 1)
        field = _normalize_field_name(left)
        value = right.strip().strip('"\'')
        if field and value:
            updates[field] = value

    return updates


def _parse_context_kv_pairs(business_context: str) -> dict[str, str]:
    """Parse context text like 'field: value' into generation input fields."""
    parsed: dict[str, str] = {}
    for line in (business_context or "").splitlines():
        if ":" not in line:
            continue
        left, right = line.split(":", 1)
        field = _normalize_field_name(left)
        value = right.strip()
        if field and value:
            parsed[field] = value
    return parsed

@router.post("/generate")
async def ai_generate(
    transaction_type: str = Form(...),
    request_id: str = Form(...),
    user_prompt: str = Form(default=""),
    business_context: str = Form(default=""),
    source_data_json: str = Form(default=""),
):
    """
    AI-assisted EDI generation.
    Builds final EDI from source data and applies user prompt updates before generation.
    Requires pre-approved request_id.
    """
    try:
        require_ai_approval(request_id)
    except (AINotApprovedError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    now = datetime.utcnow().isoformat()
    tx_type = transaction_type.upper()

    source_data: dict[str, str] = {}
    if source_data_json.strip():
        try:
            decoded = json.loads(source_data_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid source_data_json: {exc}")
        if not isinstance(decoded, dict):
            raise HTTPException(status_code=400, detail="source_data_json must be a JSON object.")
        source_data = {
            _normalize_field_name(str(k)): str(v).strip()
            for k, v in decoded.items()
            if v is not None and str(v).strip() != ""
        }

    # Backward compatible fallback for existing clients that pass context as key:value lines.
    if business_context.strip():
        for k, v in _parse_context_kv_pairs(business_context).items():
            source_data.setdefault(k, v)

    prompt_updates = _extract_prompt_updates(user_prompt)
    final_data = dict(source_data)
    final_data.update(prompt_updates)

    if not final_data:
        raise HTTPException(
            status_code=422,
            detail=(
                "No source generation data provided. Enter field values (manual or file mode) "
                "before running AI Processing in Generation tab."
            ),
        )

    required_fields = edi_generator.get_required_fields(tx_type)
    missing_fields = [f for f in required_fields if not final_data.get(f)]
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail=(
                "Cannot generate EDI: missing required fields after applying AI prompt updates: "
                f"{', '.join(missing_fields)}"
            ),
        )

    try:
        edi = edi_generator.generate(tx_type, final_data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    applied_updates = [{"field": k, "value": v} for k, v in prompt_updates.items()]

    rule_summary = (
        f"AI generated EDI for {tx_type}. "
        f"Applied {len(applied_updates)} prompt-based field update(s)."
    )
    gemini_text, gemini_error = gemini_client.generate(
        gemini_client.analysis_prompt_for_generate(tx_type, applied_updates, user_prompt)
    )

    result = {
        "ai_generated": True,
        "ai_model": _AI_MODEL_LABEL,
        "ai_model_status": "ok" if gemini_text else "failed",
        "ai_timestamp": now,
        "transaction_type": tx_type,
        "edi": edi,
        "final_data": final_data,
        "applied_updates": applied_updates,
        "ai_summary": gemini_text if gemini_text else rule_summary,
    }
    if gemini_error:
        result["ai_error"] = gemini_error

    record_ai_result(request_id, f"AI Generate EDI: {tx_type}, updates={len(applied_updates)}")
    audit.record(
        action="AI_GENERATE",
        module="AI_OPERATIONS",
        input_summary=f"transaction_type={transaction_type}, request_id={request_id}",
        result=f"edi_generated, updates={len(applied_updates)}",
        ai_used=True,
        ai_request_id=request_id,
    )

    return JSONResponse(content=result)


_GENERATION_GUIDANCE: dict[str, dict] = {
    "837P": {
        "required_segments": ["ISA", "GS", "ST", "BHT", "NM1*41 (Submitter)", "NM1*40 (Receiver)",
                               "HL*20 (Billing Provider)", "NM1*85 (Billing Provider Name/NPI)", "PRV (Taxonomy)",
                               "HL*22 (Subscriber)", "NM1*IL (Subscriber)", "DMG (DOB/Gender)", "SBR",
                               "CLM (Claim)", "DTP*472 (Service Date)", "HI (Diagnosis)", "LX", "SV1 (Procedure)", "SE", "GE", "IEA"],
        "segment_guidance": {
            "ISA": "ISA06=Sender ID (15 chars, padded); ISA08=Receiver ID (15 chars, padded); ISA15=P (production) or T (test)",
            "CLM": "CLM01=unique submitter claim ID; CLM02=total charge (no $ sign); CLM05-1=place of service (e.g. 11=office); CLM05-3=frequency (1=original)",
            "NM1*85": "NM1*85*2*OrganizationName***XX*NPI; NM109=10-digit NPI",
            "NM1*IL": "NM1*IL*1*LastName*FirstName***MI*MemberID",
            "HI": "HI*ABK:ICD10Code (primary diag, no dot); additional: HI*ABF:ICD10Code",
            "SV1": "SV1*HC:CPTCode:Modifier*Amount*UN*Units**1:2:3 (diagnosis pointer)",
            "DTP*472": "DTP*472*D8*CCYYMMDD (service from date) or DTP*472*RD8*CCYYMMDD-CCYYMMDD (range)",
        },
        "pre_checks": [
            "Verify NPI is 10 digits and active in NPPES",
            "Confirm ICD-10-CM codes are valid for the date of service (no decimal points in EDI)",
            "Ensure CPT/HCPCS codes are active and allowed per the companion guide",
            "Verify member eligibility for the date of service",
            "Confirm taxonomy code matches the rendering provider specialty",
        ],
        "companion_notes": "837P is used for professional services. Use 837I for institutional/UB-04 claims. Verify place of service codes with each trading partner.",
    },
    "837I": {
        "required_segments": ["ISA", "GS", "ST", "BHT", "NM1*41", "NM1*40",
                               "HL*20 (Billing)", "NM1*85", "HL*22 (Subscriber)", "NM1*IL", "SBR",
                               "CLM", "DTP*435 (Admission)", "DTP*096 (Discharge)", "HI (Principal Diag)",
                               "HI (Procedure/DRG)", "LX", "SV2 (Revenue Line)", "SE", "GE", "IEA"],
        "segment_guidance": {
            "CLM": "CLM01=claim ID; CLM02=total charges; CLM05-1=facility type (e.g. 11=inpatient); CLM05-3=frequency",
            "SV2": "SV2*RevCode*HC:ProcCode*Amount*UN*Units",
            "HI (DRG)": "HI*BF:PrincipalDiag*...*DR:DRGCode",
        },
        "pre_checks": [
            "Verify facility NPI and type of bill code match payer requirements",
            "Confirm admission and discharge dates in DTP*435/096",
            "Validate revenue codes against UB-04 billing guidelines",
        ],
        "companion_notes": "837I uses revenue codes (SV2) instead of CPT (SV1). Type of bill in CLM05 drives adjudication rules.",
    },
    "278": {
        "required_segments": ["ISA", "GS", "ST", "BHT", "NM1*X3 (Utilization Reviewer)",
                               "NM1*1P (Requesting Provider)", "HL*20 (Provider)", "HL*22 (Subscriber)",
                               "NM1*IL (Member)", "DMG", "HL*19 or HL*EV (Service)", "UM (Service Review)",
                               "DTP (Service Dates)", "HSD (Units/Duration)", "HI (Diagnosis)", "SE", "GE", "IEA"],
        "segment_guidance": {
            "UM": "UM*AR*I**...*1 (1=initial request, 2=concurrent, 3=retrospective)",
            "BHT": "BHT*0007*13*ReferenceID*Date*Time*RU for prior auth request",
        },
        "pre_checks": [
            "Confirm UM*01 service type code matches the procedure being authorized",
            "Verify requesting provider NPI matches submitter credentials",
            "Include all supporting diagnosis codes per clinical documentation",
        ],
        "companion_notes": "278 is the prior authorization transaction. Use BHT*0007*13 for initial request. Response comes as 278 with UM*AR*2 approval or UM*AR*3 denial.",
    },
}


def _build_generation_guidance(tx_type: str, user_prompt: str, business_context: str) -> dict:
    """Build structured generation guidance for the requested transaction type."""
    base = _GENERATION_GUIDANCE.get(tx_type, {})
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    summary_lines = [
        f"[AI Generation Guidance — {tx_type} — {now}]",
    ]
    if user_prompt:
        summary_lines += ["", f"User instruction: {user_prompt}"]
    if business_context:
        summary_lines += ["", f"Business context provided: {business_context[:300]}"]

    if base:
        summary_lines += [
            "",
            f"Transaction: {tx_type} (X12 5010)",
            f"Required segment count: {len(base.get('required_segments', []))} mandatory segments",
            "",
            "Segment Mapping Summary:",
        ]
        for seg, guidance in (base.get("segment_guidance", {}) or {}).items():
            summary_lines.append(f"  • {seg}: {guidance}")

        summary_lines += ["", "Pre-submission Checklist:"]
        for check in (base.get("pre_checks", []) or []):
            summary_lines.append(f"  ☐ {check}")

        sample = _generate_sample_structure(tx_type)
        summary_lines += ["", "Minimal segment structure:", sample]
    else:
        summary_lines += [
            "",
            f"Transaction type {tx_type} — use the X12 5010 Implementation Guide for segment specifications.",
            "Common requirements for all EDI transactions:",
            "  • ISA/IEA interchange envelope with valid sender/receiver IDs",
            "  • GS/GE functional group with matching control numbers",
            "  • ST/SE transaction set with correct segment count",
            "  • All mandatory (M) elements populated per the companion guide",
        ]

    return {
        "summary": "\n".join(summary_lines),
        "required_segments": base.get("required_segments", []),
        "segment_guidance": base.get("segment_guidance", {}),
        "pre_checks": base.get("pre_checks", []),
        "sample_structure": _generate_sample_structure(tx_type),
        "companion_notes": base.get("companion_notes", f"Refer to the X12 5010 {tx_type} Implementation Guide."),
    }


def _generate_sample_structure(tx_type: str) -> str:
    """Generate a commented sample EDI structure skeleton."""
    samples: dict[str, str] = {
        "837P": (
            "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *231214*1200*^*00501*000000001*0*P*:\n"
            "GS*HC*SENDER*RECEIVER*20231214*1200*1*X*005010X222A1\n"
            "ST*837*0001*005010X222A1\n"
            "BHT*0019*00*BATCHID001*20231214*1200*CH\n"
            "NM1*41*2*SUBMITTER NAME***XX*1234567890\n"
            "PER*IC*CONTACT NAME*TE*5555551234\n"
            "NM1*40*2*PAYER NAME***PI*PAYERID\n"
            "HL*1**20*1\n"
            "NM1*85*2*BILLING PROVIDER***XX*1234567890\n"
            "N3*123 MAIN ST\n"
            "N4*ANYTOWN*CA*90210\n"
            "PRV*BI*PXC*207Q00000X\n"
            "HL*2*1*22*0\n"
            "SBR*P*18*GROUP001****CI\n"
            "NM1*IL*1*DOE*JOHN****MI*MEM123456\n"
            "DMG*D8*19800101*M\n"
            "CLM*CLAIM001*150.00***11:B:1*Y*A*Y*I\n"
            "DTP*472*D8*20231214\n"
            "HI*ABK:Z0000\n"
            "LX*1\n"
            "SV1*HC:99213*150.00*UN*1**1\n"
            "SE*20*0001\n"
            "GE*1*1\n"
            "IEA*1*000000001"
        ),
        "278": (
            "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *231214*1200*^*00501*000000001*0*P*:\n"
            "GS*HS*SENDER*RECEIVER*20231214*1200*1*X*005010X217\n"
            "ST*278*0001*005010X217\n"
            "BHT*0007*13*AUTH001*20231214*1200*RU\n"
            "HL*1**20*1\n"
            "NM1*X3*2*PAYER NAME***PI*PAYERID\n"
            "HL*2*1*21*1\n"
            "NM1*1P*2*PROVIDER NAME***XX*1234567890\n"
            "HL*3*2*22*1\n"
            "NM1*IL*1*DOE*JOHN****MI*MEM123456\n"
            "DMG*D8*19800101*M\n"
            "HL*4*3*EV*0\n"
            "UM*AR*I**...*1\n"
            "HSD*VS*10*DA\n"
            "DTP*472*D8*20231214\n"
            "HI*BF:Z0000\n"
            "SE*16*0001\n"
            "GE*1*1\n"
            "IEA*1*000000001"
        ),
    }
    return samples.get(tx_type, f"# See X12 5010 {tx_type} Implementation Guide for sample structure.")


# ---------------------------------------------------------------------------
# Route: General-purpose AI Q&A / Follow-up Chat
# ---------------------------------------------------------------------------

@router.post("/ask")
async def ai_ask(
    request_id: str = Form(...),
    panel: str = Form(default=""),
    user_instruction: str = Form(...),
    context: str = Form(default=""),
    history: str = Form(default="[]"),
):
    """
    General-purpose AI Q&A endpoint.

    Used for:
      - AI Processing Mode on panels that have no dedicated AI endpoint
        (Excel Export, TP Mapping, Companion Guide).
      - Follow-up / chat messages from any panel after an AI task completes.
        The same request_id approved for the initial action can be reused for
        follow-up questions within the same session.

    The user_instruction is the PRIMARY directive.
    context and history ground the response without replacing the instruction.
    Requires a pre-approved request_id.
    """
    try:
        require_ai_approval(request_id)
    except (AINotApprovedError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if not user_instruction or not user_instruction.strip():
        raise HTTPException(status_code=422, detail="user_instruction is required and cannot be empty.")

    try:
        parsed_history: list[dict] = json.loads(history) if history.strip() else []
        if not isinstance(parsed_history, list):
            parsed_history = []
    except json.JSONDecodeError:
        parsed_history = []

    prompt = gemini_client.analysis_prompt_for_ask(
        panel=panel or "EDI Accelerator",
        user_instruction=user_instruction.strip(),
        context=context or "",
        history=parsed_history,
    )

    gemini_text, gemini_error = gemini_client.generate(prompt, max_tokens=2048)

    fallback_answer = (
        f"[AI Unavailable — Gemini not configured]\n\n"
        f"Your instruction: {user_instruction}\n\n"
        "Please configure the GEMINI_API_KEY environment variable to enable AI responses."
    )

    result = {
        "answer": gemini_text if gemini_text else fallback_answer,
        "ai_model": _AI_MODEL_LABEL,
        "ai_model_status": "ok" if gemini_text else "failed",
        "ai_timestamp": datetime.utcnow().isoformat(),
        "panel": panel,
    }
    if gemini_error:
        result["ai_error"] = gemini_error

    record_ai_result(request_id, f"AI Ask ({panel}): {user_instruction[:80]}")
    audit.record(
        action="AI_ASK",
        module="AI_OPERATIONS",
        input_summary=f"panel={panel}, request_id={request_id}, instruction_len={len(user_instruction)}",
        result=f"answer_len={len(result['answer'])}",
        ai_used=True,
        ai_request_id=request_id,
    )

    return JSONResponse(content=result)
