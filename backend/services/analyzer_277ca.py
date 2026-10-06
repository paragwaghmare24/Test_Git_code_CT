"""
services/analyzer_277ca.py
277CA Claim Acknowledgment Analyzer.
Maps STC category and status codes to human-readable claim status.
Processing Rule PR-07.
"""

from __future__ import annotations

from backend.models.schemas import (
    Analysis277CAClaimSchema,
    Analysis277CAResultSchema,
    STCStatusSchema,
)
from backend.services import edi_parser


# ---------------------------------------------------------------------------
# STC Code Tables
#
# Verified against the official X12 External Code Lists (x12.org/codes,
# successor to the Washington Publishing Company lists):
#   Code Source 507 — Claim Status Category Codes (_STC_CATEGORY_CODES)
#   Code Source 508 — Claim Status Codes (_STC_STATUS_CODES)
# Code Source 508 has 400+ entries; only the subset most relevant to claim
# acknowledgment scenarios is included here. Unmapped codes fall back to
# "Status '<code>'" (see _parse_stc) rather than showing a wrong guess.
# ---------------------------------------------------------------------------

_STC_CATEGORY_CODES: dict[str, str] = {
    # Acknowledgements
    "A0": "Acknowledgement/Forwarded — the claim/encounter has been forwarded to another entity",
    "A1": "Acknowledgement/Receipt — received, not yet accepted for adjudication",
    "A2": "Acknowledgement/Acceptance into adjudication system",
    "A3": "Acknowledgement/Returned as unprocessable claim — rejected, not entered into the adjudication system",
    "A4": "Acknowledgement/Not Found — the claim/encounter cannot be found in the adjudication system",
    "A5": "Acknowledgement/Split Claim — split upon acceptance into the adjudication system",
    "A6": "Acknowledgement/Rejected for Missing Information",
    "A7": "Acknowledgement/Rejected for Invalid Information",
    "A8": "Acknowledgement/Rejected for relational field in error",
    # Pending
    "P0": "Pending/Adjudication or Details — generic pended-claim message",
    "P1": "Pending/In Process — in the adjudication system",
    "P2": "Pending/Payer Review — suspended pending review (medical review, repricing, TPA)",
    "P3": "Pending/Provider Requested Information",
    "P4": "Pending/Patient Requested Information",
    "P5": "Pending/Payer Administrative or System Hold",
    # Finalized
    "F0": "Finalized — adjudication cycle complete, no further action will be taken",
    "F1": "Finalized/Payment — the claim/line has been paid",
    "F2": "Finalized/Denial — the claim/line has been denied",
    "F3": "Finalized/Revised — adjudication information has been changed",
    "F3F": "Finalized/Forwarded — payment made (if any) and forwarded to a subsequent entity",
    "F3N": "Finalized/Not Forwarded — payment made (if any), not forwarded to any subsequent entity",
    "F4": "Finalized/Adjudication Complete — no payment forthcoming",
    # Requests for additional information
    "R0": "Requests for additional Information/General Requests",
    "R1": "Requests for additional Information/Entity Requests",
    "R3": "Requests for additional Information/Claim or Line",
    "R4": "Requests for additional Information/Documentation",
    "R5": "Requests for additional information/more specific detail",
    "R6": "Requests for additional information — regulatory requirements",
    "R7": "Requests for additional information — confirm care is consistent with health plan policy coverage",
    "R8": "Requests for additional information — confirm care is consistent with health plan coverage exceptions",
    # Error / general
    "E0": "Response not possible — error on submitted request data",
    "E1": "Response not possible — system status",
    "E2": "Information holder is not responding; resubmit at a later time",
    "E3": "Correction required — relational fields in error",
    # Search
    "D0": "Data Search Unsuccessful — payer unable to return status for the submitted search criteria",
}

_STC_STATUS_CODES: dict[str, str] = {
    "0": "Cannot provide further status electronically",
    "1": "For more detailed information, see remittance advice",
    "2": "More detailed information in letter",
    "3": "Claim has been adjudicated and is awaiting payment cycle",
    "6": "Balance due from the subscriber",
    "16": "Claim/encounter has been forwarded to entity (requires Entity Code)",
    "17": "Claim/encounter has been forwarded by third party entity to entity (requires Entity Code)",
    "18": "Entity received claim/encounter, but returned invalid status (requires Entity Code)",
    "19": "Entity acknowledges receipt of claim/encounter (requires Entity Code)",
    "20": "Accepted for processing",
    "21": "Missing or invalid information",
    "23": "Returned to Entity (requires Entity Code)",
    "24": "Entity not approved as an electronic submitter (requires Entity Code)",
    "25": "Entity not approved (requires Entity Code)",
    "26": "Entity not found (requires Entity Code)",
    "27": "Policy canceled",
    "29": "Subscriber and policy number/contract number mismatched",
    "30": "Subscriber and subscriber id mismatched",
    "31": "Subscriber and policyholder name mismatched",
    "32": "Subscriber and policy number/contract number not found",
    "33": "Subscriber and subscriber id not found",
    "34": "Subscriber and policyholder name not found",
    "35": "Claim/encounter not found",
    "40": "Waiting for final approval",
    "42": "Awaiting related charges",
    "45": "Awaiting benefit determination",
    "54": "Duplicate of a previously processed claim/line",
    "56": "Awaiting eligibility determination",
    "65": "Claim/line has been paid",
    "78": "Duplicate of an existing claim/line, awaiting processing",
    "81": "Contract/plan does not cover pre-existing conditions",
    "84": "Service not authorized",
    "95": "Requested additional information not received",
    "110": "Claim requires pricing information",
    "116": "Claim submitted to incorrect payer",
    "121": "Service line number greater than maximum allowable for payer",
    "481": "Claim/submission format is invalid",
    "493": "Version/Release/Industry ID code not currently supported by information holder",
    "510": "Future date (requires a second status code identifying the element in error)",
    "511": "Invalid character (requires a second status code identifying the element in error)",
    "512": "Length invalid for receiver's application system",
    "718": "Claim/service not submitted within the required timeframe (timely filing)",
    "746": "Duplicate Submission (information receiver level, Claim Acknowledgement only)",
    "772": "The greatest level of diagnosis code specificity is required",
}



# ---------------------------------------------------------------------------
# Parser Helpers
# ---------------------------------------------------------------------------

def _parse_stc(stc_raw: str, element_sep: str, component_sep: str) -> STCStatusSchema:
    """Parse STC segment into STCStatusSchema."""
    parts = stc_raw.split(element_sep)
    stc_01_raw = parts[1].strip() if len(parts) > 1 else ""
    stc_02 = parts[2].strip() if len(parts) > 2 else ""
    stc_03 = parts[3].strip() if len(parts) > 3 else None

    # STC01 is composite: Category~StatusCode~ActionCode
    comp = stc_01_raw.split(component_sep)
    category = comp[0].strip() if comp else ""
    status_code = comp[1].strip() if len(comp) > 1 else ""

    return STCStatusSchema(
        stc_01=stc_01_raw,
        stc_02=stc_02,
        stc_03=stc_03,
        category_description=_STC_CATEGORY_CODES.get(category, f"Category '{category}'"),
        status_description=_STC_STATUS_CODES.get(status_code, f"Status '{status_code}'"),
    )


def _extract_claim_analyses(
    segments: list[str], element_sep: str, component_sep: str
) -> list[Analysis277CAClaimSchema]:
    """Extract per-claim analysis from a 277CA transaction set."""
    claims: list[Analysis277CAClaimSchema] = []
    current_claim: dict = {}

    for seg_raw in segments:
        parts = seg_raw.split(element_sep)
        seg_id = parts[0].strip()

        if seg_id == "CLP":
            # Save previous claim if exists
            if current_claim:
                claims.append(_build_claim(current_claim, element_sep, component_sep))
                current_claim = {}
            # CLP01=ClaimSubmitterID, CLP02=Status, CLP03=ChargeAmount, ...
            current_claim = {
                "claim_number": parts[1].strip() if len(parts) > 1 else "",
                "status_code": parts[2].strip() if len(parts) > 2 else "",
                "stc_segs": [],
                "nm1_segs": [],
            }

        elif seg_id == "STC" and current_claim:
            current_claim.setdefault("stc_segs", []).append(seg_raw)

        elif seg_id == "NM1" and current_claim:
            current_claim.setdefault("nm1_segs", []).append(seg_raw)

        elif seg_id == "REF" and current_claim:
            ref_parts = parts
            if len(ref_parts) > 2 and ref_parts[1].strip() == "EA":
                # Patient account number / member ID
                current_claim["member_id"] = ref_parts[2].strip()

    # Process last claim
    if current_claim:
        claims.append(_build_claim(current_claim, element_sep, component_sep))

    return claims


def _build_claim(
    raw: dict, element_sep: str, component_sep: str
) -> Analysis277CAClaimSchema:
    """Build an Analysis277CAClaimSchema from raw collected data."""
    stc_status: STCStatusSchema | None = None
    if raw.get("stc_segs"):
        stc_status = _parse_stc(raw["stc_segs"][0], element_sep, component_sep)

    # Extract provider NPI from NM1 segments
    provider_npi = ""
    for nm1_raw in raw.get("nm1_segs", []):
        nm1_parts = nm1_raw.split(element_sep)
        if len(nm1_parts) > 9 and nm1_parts[8].strip() == "XX":
            provider_npi = nm1_parts[9].strip().rstrip("~")
            break

    # Build human-readable summary
    summary_parts = [f"Claim {raw.get('claim_number', 'N/A')}"]
    if stc_status:
        summary_parts.append(stc_status.category_description)
        if stc_status.status_description:
            summary_parts.append(stc_status.status_description)

    return Analysis277CAClaimSchema(
        claim_number=raw.get("claim_number", ""),
        member_id=raw.get("member_id", ""),
        provider_npi=provider_npi,
        status=_STC_CATEGORY_CODES.get(
            raw.get("status_code", ""), raw.get("status_code", "")
        ),
        stc_status=stc_status,
        human_readable_summary=" | ".join(summary_parts),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_raw(raw_content: str, source_file: str = "") -> Analysis277CAResultSchema:
    """
    Parse and analyze a 277CA Claim Acknowledgment.
    Returns Analysis277CAResultSchema.
    """
    transaction = edi_parser.parse(raw_content, source_file=source_file)
    element_sep = (
        transaction.isa_segment.raw[3]
        if transaction.isa_segment and len(transaction.isa_segment.raw) > 3
        else "*"
    )
    component_sep = ":"

    claim_analyses: list[Analysis277CAClaimSchema] = []
    for group in transaction.groups:
        for ts in group.transaction_sets:
            seg_raws = [s.raw for s in ts.segments]
            claims = _extract_claim_analyses(seg_raws, element_sep, component_sep)
            claim_analyses.extend(claims)

    return Analysis277CAResultSchema(
        source_file=source_file,
        claim_analyses=claim_analyses,
    )


def analyze_file(file_path: str) -> Analysis277CAResultSchema:
    """Analyze a 277CA file from disk."""
    from pathlib import Path
    content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    return analyze_raw(content, source_file=file_path)
