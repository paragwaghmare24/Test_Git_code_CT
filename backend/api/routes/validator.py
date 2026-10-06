"""
api/routes/validator.py
POST /api/validate — validate a single EDI file.
Returns validation result + full parsed segment structure for UI visualization.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.services import edi_parser, edi_validator, audit
from backend.utils.file_handler import save_upload

router = APIRouter(prefix="/api", tags=["validate"])

# ---------------------------------------------------------------------------
# Segment description metadata for enhanced UI display
# ---------------------------------------------------------------------------

_SEGMENT_BUSINESS_MEANING: dict[str, dict] = {
    "ISA": {"meaning": "Interchange Control Header — defines the start of an EDI interchange, sender/receiver IDs, date, time, control number and version.", "purpose": "Envelope"},
    "IEA": {"meaning": "Interchange Control Trailer — closes the interchange and counts the functional groups.", "purpose": "Envelope"},
    "GS":  {"meaning": "Functional Group Header — groups related transaction sets together with application sender/receiver IDs and date.", "purpose": "Envelope"},
    "GE":  {"meaning": "Functional Group Trailer — closes the functional group and provides a segment count.", "purpose": "Envelope"},
    "ST":  {"meaning": "Transaction Set Header — marks the start of an individual transaction set (e.g., 837P claim).", "purpose": "Envelope"},
    "SE":  {"meaning": "Transaction Set Trailer — marks the end of the transaction set and verifies the segment count.", "purpose": "Envelope"},
    "BHT": {"meaning": "Beginning of Hierarchical Transaction — specifies the type of transaction (original, resubmission, void) and reference ID.", "purpose": "Control"},
    "NM1": {"meaning": "Individual or Organizational Name — identifies an entity (provider, subscriber, payer, etc.) with name and ID.", "purpose": "Name/ID"},
    "PER": {"meaning": "Administrative Communications Contact — provides contact information (phone, email) for the named entity.", "purpose": "Contact"},
    "N3":  {"meaning": "Address Information — street address line for the named entity.", "purpose": "Address"},
    "N4":  {"meaning": "Geographic Location — city, state, zip code for the named entity.", "purpose": "Address"},
    "HL":  {"meaning": "Hierarchical Level — defines the hierarchical relationship between loops (e.g., billing provider → subscriber → patient → claim).", "purpose": "Hierarchy"},
    "PRV": {"meaning": "Provider Information — specifies provider taxonomy code and provider type (billing, rendering, attending).", "purpose": "Provider"},
    "SBR": {"meaning": "Subscriber Information — identifies the insurance subscriber relationship and coverage type.", "purpose": "Subscriber"},
    "PAT": {"meaning": "Patient Information — identifies the patient when different from the subscriber.", "purpose": "Patient"},
    "DMG": {"meaning": "Demographic Information — date of birth, gender, and marital status of the subscriber or patient.", "purpose": "Demographics"},
    "CLM": {"meaning": "Claim Information — the core claim segment; contains claim number, total charge amount, facility type, and claim frequency.", "purpose": "Claim"},
    "DTP": {"meaning": "Date or Time Period — various date references (service date, admission date, discharge date, etc.) qualified by a code.", "purpose": "Date"},
    "REF": {"meaning": "Reference Identification — additional reference numbers (authorization, prior auth, CLIA, NPI, etc.) for the claim or entity.", "purpose": "Reference"},
    "HI":  {"meaning": "Health Care Diagnosis Code — ICD-10-CM diagnosis codes supporting the claim, qualified by code set type.", "purpose": "Diagnosis"},
    "SV1": {"meaning": "Professional Service — procedure code, charge, units, and modifiers for a professional service line.", "purpose": "Service Line"},
    "SV2": {"meaning": "Institutional Service Line — revenue code, procedure code, charge, and units for a facility service line.", "purpose": "Service Line"},
    "LX":  {"meaning": "Line Counter — sequential line number for each service line within a claim.", "purpose": "Line"},
    "PWK": {"meaning": "Paperwork — identifies attached supporting documentation (reports, x-rays, etc.).", "purpose": "Attachment"},
    "AMT": {"meaning": "Monetary Amount — reports specific monetary amounts (patient paid, approved amount, etc.).", "purpose": "Amount"},
    "QTY": {"meaning": "Quantity — reports units of measure related to the service.", "purpose": "Quantity"},
    "CRC": {"meaning": "Conditions Indicator — codes indicating special conditions (e.g., EPSDT, hospice, etc.).", "purpose": "Condition"},
    "CR1": {"meaning": "Ambulance Transport Information — details of ambulance transport for the patient.", "purpose": "Transport"},
    "MOA": {"meaning": "Medicare Outpatient Adjudication — Medicare-specific adjudication information.", "purpose": "Adjudication"},
    "BPR": {"meaning": "Financial Information — remittance payment details including payment amount, payment method, and bank routing.", "purpose": "Payment"},
    "TRN": {"meaning": "Reassociation Trace Number — identifies the payment transaction for reconciliation purposes.", "purpose": "Trace"},
    "CLP": {"meaning": "Claim Payment Information — claim-level adjudication: claim ID, status, charge, payment, patient responsibility.", "purpose": "Claim Payment"},
    "CAS": {"meaning": "Claim Adjustment — adjustment reason codes and amounts at claim or service line level.", "purpose": "Adjustment"},
    "SVC": {"meaning": "Service Payment Information — service line level adjudication with procedure code, charge, and payment.", "purpose": "Service Payment"},
    "PLB": {"meaning": "Provider Level Adjustment — provider-level financial adjustments unrelated to a specific claim.", "purpose": "Adjustment"},
    "AK1": {"meaning": "Functional Acknowledgment Header — begins the acknowledgment of a functional group.", "purpose": "Acknowledgment"},
    "AK2": {"meaning": "Transaction Set Response Header — begins acknowledgment of a specific transaction set.", "purpose": "Acknowledgment"},
    "AK3": {"meaning": "Data Segment Note — identifies a segment in error.", "purpose": "Error"},
    "AK4": {"meaning": "Data Element Note — identifies a specific element in error with error code.", "purpose": "Error"},
    "AK5": {"meaning": "Transaction Set Response Trailer — accepted/rejected status code for the transaction set.", "purpose": "Acknowledgment"},
    "AK9": {"meaning": "Functional Acknowledgment Trailer — accepted/rejected status for the entire functional group.", "purpose": "Acknowledgment"},
    "IK3": {"meaning": "Implementation Data Segment Note — 999-specific: identifies a segment not in compliance.", "purpose": "Error"},
    "IK4": {"meaning": "Implementation Data Element Note — 999-specific: identifies an element in error.", "purpose": "Error"},
    "IK5": {"meaning": "Implementation Transaction Set Response Trailer — 999 acceptance/rejection per transaction set.", "purpose": "Acknowledgment"},
    "UM":  {"meaning": "Health Care Services Review Information — authorization request type, service type, and level of care.", "purpose": "Authorization"},
    "HSD": {"meaning": "Health Care Services Delivery — identifies units, frequency, and duration of service being reviewed.", "purpose": "Authorization"},
    "STC": {"meaning": "Health Care Claim Status — 277CA claim status codes with category and detailed status description.", "purpose": "Status"},
    "INS": {"meaning": "Insured Benefit — benefit enrollment details for the member.", "purpose": "Enrollment"},
    "HD":  {"meaning": "Health Coverage — plan type, coverage type, and insurance line for the member.", "purpose": "Coverage"},
    "BHT": {"meaning": "Beginning of Hierarchical Transaction — transaction reference, type, and date/time.", "purpose": "Control"},
}

_ELEMENT_DESCRIPTIONS: dict[str, dict[int, str]] = {
    "ISA": {1:"Auth Info Qualifier",2:"Auth Info",3:"Security Info Qualifier",4:"Security Info",5:"Interchange ID Qualifier (Sender)",6:"Interchange Sender ID",7:"Interchange ID Qualifier (Receiver)",8:"Interchange Receiver ID",9:"Interchange Date",10:"Interchange Time",11:"Repetition Separator",12:"Interchange Control Version",13:"Interchange Control Number",14:"Acknowledgment Requested",15:"Interchange Usage Indicator",16:"Component Element Separator"},
    "GS": {1:"Functional ID Code",2:"Application Sender Code",3:"Application Receiver Code",4:"Date",5:"Time",6:"Group Control Number",7:"Responsible Agency Code",8:"Version/Release"},
    "ST": {1:"Transaction Set ID Code",2:"Transaction Set Control Number",3:"Implementation Convention Reference"},
    "NM1": {1:"Entity ID Code",2:"Entity Type Qualifier",3:"Last/Org Name",4:"First Name",5:"Middle Name",6:"Name Prefix",7:"Name Suffix",8:"ID Code Qualifier",9:"ID Code (NPI/Member ID)"},
    "CLM": {1:"Claim Submitter's Claim ID",2:"Total Claim Charge Amount",3:"(Not Used)",4:"(Not Used)",5:"Place of Service / Claim Frequency",6:"Provider/Supplier Signature Indicator",7:"Medicare Assignment Code",8:"Benefits Assignment Certification Indicator",9:"Release of Information Code"},
    "DTP": {1:"Date/Time Qualifier",2:"Date/Time Period Format Qualifier",3:"Date/Time Period"},
    "REF": {1:"Reference ID Qualifier",2:"Reference ID",3:"Description"},
    "HI": {1:"Diagnosis Code 1",2:"Diagnosis Code 2",3:"Diagnosis Code 3",4:"Diagnosis Code 4",5:"Diagnosis Code 5",6:"Diagnosis Code 6",7:"Diagnosis Code 7",8:"Diagnosis Code 8"},
    "SV1": {1:"Professional Service (Proc Code)",2:"Line Item Charge Amount",3:"Unit of Basis for Measurement Code",4:"Service Unit Count",5:"Place of Service Code",6:"Service Type Code",7:"Diagnosis Code Pointers"},
    "SV2": {1:"Revenue Code",2:"Procedure Code",3:"Line Item Charge Amount",4:"Unit of Basis for Measurement Code",5:"Service Unit Count"},
    "HL": {1:"Hierarchical ID Number",2:"Hierarchical Parent ID Number",3:"Hierarchical Level Code",4:"Hierarchical Child Code"},
    "DMG": {1:"Date Time Period Format Qualifier",2:"Date of Birth",3:"Gender Code"},
    "PRV": {1:"Provider Code",2:"Reference ID Qualifier",3:"Reference ID (Taxonomy)"},
    "SBR": {1:"Payer Responsibility Sequence Code",2:"Individual Relationship Code",3:"Reference ID (Group Number)",4:"Name",5:"Insurance Type Code",6:"Coordination of Benefits Code",7:"Yes/No",8:"Yes/No",9:"Claim Filing Indicator Code"},
}


def _build_segment_detail(seg, element_sep: str, errors: list, warnings: list) -> dict:
    """Build a detailed segment dict for UI display."""
    seg_id = seg.segment_id
    meta = _SEGMENT_BUSINESS_MEANING.get(seg_id, {})
    elem_descs = _ELEMENT_DESCRIPTIONS.get(seg_id, {})

    # For repeating segments (e.g. NM1, DTP, REF), the first element is a qualifier
    # that distinguishes each occurrence.  Errors created by the validation engines
    # encode the qualifier in the segment field (e.g. "NM1-85", "DTP-472") so they
    # can be pinned to the correct occurrence only.  Errors without a qualifier suffix
    # match all occurrences of that segment type.
    first_elem_value = seg.elements[0].value.strip() if seg.elements else ""

    def _matches(entry: dict) -> bool:
        entry_seg = entry.get("segment", "")
        parts = entry_seg.split("-", 1)
        if parts[0] != seg_id:
            return False
        # Error encoded with a qualifier → only match the occurrence with that qualifier
        if len(parts) > 1:
            return parts[1] == first_elem_value
        # No qualifier → applies to all occurrences of this segment type
        return True

    # Find errors/warnings that reference this specific segment occurrence
    seg_errors = [e for e in errors if _matches(e)]
    seg_warnings = [w for w in warnings if _matches(w)]

    # Build qualifier-enriched business meaning for NM1 and DTP
    _NM1_ENTITY_MEANINGS = {
        "41": "Submitter Name (Loop 1000A) — identifies who is submitting the transaction.",
        "40": "Receiver Name (Loop 1000B) — identifies the payer or clearinghouse receiving the transaction.",
        "85": "Billing Provider (Loop 2010AA) — the provider responsible for the claim; NM109 must be a valid 10-digit NPI.",
        "IL": "Subscriber / Insured (Loop 2010BA) — the primary insured person; NM109 is the Member ID.",
        "PR": "Payer Name (Loop 2010BB) — the insurance company; NM109 is the Payer ID from the trading partner agreement.",
        "DN": "Referring Provider (Loop 2310A) — ordering/referring physician; NM109 must be a valid NPI when NM108=XX.",
        "82": "Rendering Provider (Loop 2310B) — the actual treating provider; NM109 must be a valid 10-digit NPI.",
        "77": "Service Facility Location (Loop 2310C) — lab or facility where service was performed.",
        "DQ": "Supervising Provider — provider supervising the rendering provider.",
        "1P": "Ordering Provider — provider who ordered the service.",
        "QD": "Patient (Loop 2330) — identified when patient differs from subscriber.",
        "FA": "Facility / Crossover Payer.",
        "TT": "Transferred to Entity — payer to which the claim is forwarded.",
        "LI": "Independent Lab.",
    }
    _DTP_QUALIFIER_MEANINGS = {
        "472": "Service Date (DTP*472, Loop 2400) — date(s) on which service was rendered; DTP02 must be D8 (CCYYMMDD) or RD8 (range).",
        "435": "Admission Date (DTP*435, Loop 2300) — institutional admission date; DTP02 must be D8.",
        "096": "Discharge Date (DTP*096, Loop 2300) — institutional discharge date; DTP02 must be D8 or DT.",
        "304": "Last Date Worked (DTP*304) — last date patient was able to work; DTP02 must be D8.",
        "360": "Start of Care Date (DTP*360) — DTP02 must be D8.",
        "361": "Last Certification Date (DTP*361) — DTP02 must be D8.",
        "484": "Initial Treatment Date (DTP*484) — DTP02 must be D8.",
        "455": "Last Menstrual Period (DTP*455) — DTP02 must be D8.",
        "471": "Onset of Current Symptom (DTP*471) — DTP02 must be D8.",
        "090": "Report Start Date (DTP*090) — DTP02 must be D8.",
        "091": "Report End Date (DTP*091) — DTP02 must be D8.",
        "444": "Current Illness / Injury Date (DTP*444) — DTP02 must be D8.",
        "439": "Accident Date (DTP*439) — DTP02 must be D8.",
        "050": "Repricer Received Date (DTP*050) — DTP02 must be D8.",
        "102": "Issue Date (DTP*102) — DTP02 must be D8.",
    }

    enriched_meaning = meta.get("meaning", "")
    if seg_id == "NM1" and first_elem_value:
        enriched_meaning = _NM1_ENTITY_MEANINGS.get(first_elem_value, enriched_meaning)
    elif seg_id == "DTP" and first_elem_value:
        enriched_meaning = _DTP_QUALIFIER_MEANINGS.get(first_elem_value, enriched_meaning)

    elements_detail = []
    for i, elem in enumerate(seg.elements, start=1):
        elem_errors = [
            e for e in seg_errors
            if e.get("element", "") in (elem.element_id, f"{seg_id}{i:02d}", str(i))
        ]
        elements_detail.append({
            "element_id": elem.element_id,
            "position": i,
            "description": elem_descs.get(i, elem.description or f"Element {i}"),
            "value": elem.value,
            "errors": elem_errors,
        })

    return {
        "segment_id": seg_id,
        "name": seg.name or meta.get("meaning", seg_id)[:50],
        "business_meaning": enriched_meaning,
        "purpose": meta.get("purpose", ""),
        "position": seg.position,
        "loop": seg.loop,
        "raw": seg.raw,
        "elements": elements_detail,
        "errors": seg_errors,
        "warnings": seg_warnings,
        "has_error": len(seg_errors) > 0,
        "has_warning": len(seg_warnings) > 0,
    }


@router.post("/validate")
async def validate_edi(
    file: UploadFile = File(...),
    partner_name: str = Form(default=""),
):
    """
    Upload an EDI file for full validation.
    Returns ValidationResultSchema + full parsed segment structure.
    """
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

    # Parse for structural visualization
    try:
        transaction = edi_parser.parse(raw, source_file=str(saved))
    except ValueError:
        transaction = None

    # Build segment-level detail list for UI
    segments_detail: list[dict] = []
    if transaction:
        errors_raw = [e.model_dump(mode="json") for e in result.errors]
        warnings_raw = [w.model_dump(mode="json") for w in result.warnings]

        # ISA segment
        if transaction.isa_segment:
            segments_detail.append(
                _build_segment_detail(transaction.isa_segment, "*", errors_raw, warnings_raw)
            )

        for group in transaction.groups:
            if group.gs_segment:
                segments_detail.append(
                    _build_segment_detail(group.gs_segment, "*", errors_raw, warnings_raw)
                )
            for ts in group.transaction_sets:
                if ts.st_segment:
                    segments_detail.append(
                        _build_segment_detail(ts.st_segment, "*", errors_raw, warnings_raw)
                    )
                for seg in ts.segments:
                    segments_detail.append(
                        _build_segment_detail(seg, "*", errors_raw, warnings_raw)
                    )
                if ts.se_segment:
                    segments_detail.append(
                        _build_segment_detail(ts.se_segment, "*", errors_raw, warnings_raw)
                    )
            if group.ge_segment:
                segments_detail.append(
                    _build_segment_detail(group.ge_segment, "*", errors_raw, warnings_raw)
                )

        if transaction.iea_segment:
            segments_detail.append(
                _build_segment_detail(transaction.iea_segment, "*", errors_raw, warnings_raw)
            )

    audit.record(
        action="VALIDATE",
        module="edi_validator",
        input_summary=f"file={file.filename}, partner={partner_name}",
        result=f"status={result.status.value}, errors={result.error_count}",
    )

    result_dict = result.model_dump(mode="json")
    result_dict["segments_detail"] = segments_detail
    result_dict["segment_count"] = len(segments_detail)
    return result_dict
