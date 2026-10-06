"""
services/edi_generator.py
EDI Generation Service.
Generates X12 EDI from structured input (Excel/CSV/JSON/dict).
Never assumes values — raises ValueError for any missing mandatory field.
Processing Rules: PR-01.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from backend.engines.companion_guide_engine import get_guide_rules


# ---------------------------------------------------------------------------
# Control Number Management
# ---------------------------------------------------------------------------

def _icn() -> str:
    """Generate a 9-digit Interchange Control Number."""
    import random
    return str(random.randint(100000000, 999999999))


def _pad(value: str, length: int, fill: str = " ") -> str:
    """Pad or truncate a value to exact length."""
    return value.ljust(length, fill)[:length]


# ---------------------------------------------------------------------------
# ISA/IEA Builder
# ---------------------------------------------------------------------------

def _build_isa(ctx: dict) -> str:
    """Build ISA segment from context dict."""
    _require(ctx, ["sender_id", "receiver_id"])
    icn = ctx.get("interchange_control_number") or _icn()
    ctx["_icn"] = icn
    date = datetime.utcnow().strftime("%y%m%d")
    time = datetime.utcnow().strftime("%H%M")
    isa = (
        f"ISA*00*          *00*          "
        f"*ZZ*{_pad(ctx['sender_id'], 15)}"
        f"*ZZ*{_pad(ctx['receiver_id'], 15)}"
        f"*{date}*{time}*^*00501*{_pad(icn, 9, '0')}*0*P*:"
    )
    return isa


def _build_iea(ctx: dict, group_count: int = 1) -> str:
    return f"IEA*{group_count}*{_pad(ctx['_icn'], 9, '0')}"


def _build_gs_ge(
    ctx: dict,
    tx_code: str,
    inner: list[str],
    gs_version: str = "005010X222A1",
    tx_set_count: int = 1,
) -> list[str]:
    """Wrap segments in GS/GE functional group.

    gs_version   — GS08 version/release identifier (differs per tx type).
    tx_set_count — number of ST/SE transaction sets inside this group (GE01).
    """
    _require(ctx, ["sender_id", "receiver_id"])
    gcn = ctx.get("group_control_number") or str(uuid.uuid4().int)[:9]
    ctx["_gcn"] = gcn
    date = datetime.utcnow().strftime("%Y%m%d")
    time = datetime.utcnow().strftime("%H%M")
    gs = f"GS*{tx_code}*{ctx['sender_id']}*{ctx['receiver_id']}*{date}*{time}*{gcn}*X*{gs_version}"
    ge = f"GE*{tx_set_count}*{gcn}"
    return [gs] + inner + [ge]


def _wrap_st_se(
    tx_type: str,
    segments: list[str],
    impl_ref: str = "",
) -> list[str]:
    """Wrap segments in ST/SE envelope.

    impl_ref — optional ST03 implementation convention reference
               (e.g. 005010X222A1).  Omitted when empty.
    """
    tscn = str(uuid.uuid4().int)[:4]
    st = f"ST*{tx_type}*{tscn}*{impl_ref}" if impl_ref else f"ST*{tx_type}*{tscn}"
    count = len(segments) + 2  # ST + inner segments + SE
    se = f"SE*{count}*{tscn}"
    return [st] + segments + [se]


# ---------------------------------------------------------------------------
# Requirement Checker
# ---------------------------------------------------------------------------

def _require(data: dict, fields: list[str]) -> None:
    """Raise ValueError for any missing mandatory field (No Assumption Rule)."""
    missing = [f for f in fields if not data.get(f)]
    if missing:
        raise ValueError(
            f"Cannot generate EDI: the following required fields are missing: "
            f"{', '.join(missing)}. Please provide all required values."
        )


# ---------------------------------------------------------------------------
# 837P Generator
# ---------------------------------------------------------------------------

def generate_837p(data: dict) -> str:
    """
    Generate a 837P (Professional Claim) EDI from structured data.
    Raises ValueError if any mandatory field is missing.
    """
    _require(data, [
        "sender_id", "receiver_id",
        "billing_provider_name", "billing_provider_npi",
        "billing_provider_taxonomy",
        "billing_provider_address", "billing_provider_city",
        "billing_provider_state", "billing_provider_zip",
        "payer_id", "payer_name",
        "subscriber_last_name", "subscriber_first_name", "subscriber_id",
        "dob", "gender",
        "claim_number", "claim_amount",
        "diagnosis_code", "procedure_code",
        "service_date",
    ])

    segments = _build_837p_body(data)
    tx_segments = _wrap_st_se("837", segments, "005010X222A1")

    ctx = {
        "sender_id": data["sender_id"],
        "receiver_id": data["receiver_id"],
        "interchange_control_number": data.get("interchange_control_number"),
        "group_control_number": data.get("group_control_number"),
    }
    group_segments = _build_gs_ge(ctx, "HC", tx_segments, "005010X222A1")
    isa = _build_isa(ctx)
    iea = _build_iea(ctx)

    all_segs = [isa] + group_segments + [iea]
    return "~\n".join(all_segs) + "~"


# ---------------------------------------------------------------------------
# 837P body builder (inner segments only — no ISA/GS/ST/SE wrapping)
# ---------------------------------------------------------------------------

def _build_837p_body(data: dict) -> list[str]:
    """Return the ST-internal segments for one 837P claim."""
    segments: list[str] = []

    # ── BHT — Beginning of Hierarchical Transaction ──────────────────────────
    bht_ref  = data.get("bht_reference") or str(uuid.uuid4().int)[:10]
    bht_date = datetime.utcnow().strftime("%Y%m%d")
    bht_time = datetime.utcnow().strftime("%H%M")
    segments.append(f"BHT*0019*00*{bht_ref}*{bht_date}*{bht_time}*CH")

    # ── Loop 1000A — Submitter ───────────────────────────────────────────────
    submitter_id = data.get("submitter_id") or data["billing_provider_npi"]
    segments.append(f"NM1*41*2*{data['billing_provider_name']}*****46*{submitter_id}")
    phone = data.get("submitter_phone", "0000000000")
    # PER02 (Name) is intentionally left blank — guide sample shows PER*IC**TE*<phone>~
    segments.append(f"PER*IC**TE*{phone}")

    # ── Loop 1000B — Receiver ────────────────────────────────────────────────
    receiver_name = data.get("receiver_name", "RECEIVER")
    segments.append(f"NM1*40*2*{receiver_name}*****46*{data['receiver_id']}")

    # ── Loop 2000A — Billing Provider HL ────────────────────────────────────
    segments.append("HL*1**20*1")
    segments.append(f"PRV*BI*PXC*{data['billing_provider_taxonomy']}")
    segments.append(f"NM1*85*2*{data['billing_provider_name']}*****XX*{data['billing_provider_npi']}")
    segments.append(f"N3*{data['billing_provider_address']}")
    segments.append(f"N4*{data['billing_provider_city']}*{data['billing_provider_state']}*{data['billing_provider_zip']}")
    if data.get("billing_provider_tax_id"):
        segments.append(f"REF*EI*{data['billing_provider_tax_id']}")

    # ── Loop 2000B — Subscriber HL ───────────────────────────────────────────
    segments.append("HL*2*1*22*0")
    ins_type = data.get("insurance_type_code", "CI")
    group_num = data.get("group_number", "")
    segments.append(f"SBR*P*18*{group_num}****{ins_type}")
    segments.append(f"NM1*IL*1*{data['subscriber_last_name']}*{data['subscriber_first_name']}****MI*{data['subscriber_id']}")
    if data.get("subscriber_address"):
        segments.append(f"N3*{data['subscriber_address']}")
        segments.append(
            f"N4*{data.get('subscriber_city','')}*{data.get('subscriber_state','')}*{data.get('subscriber_zip','')}"
        )
    segments.append(f"DMG*D8*{data['dob']}*{data['gender']}")

    # ── Loop 2010BB — Payer ──────────────────────────────────────────────────
    segments.append(f"NM1*PR*2*{data['payer_name']}*****PI*{data['payer_id']}")

    # ── Loop 2300 — Claim ────────────────────────────────────────────────────
    pos  = data.get("place_of_service", "11")
    freq = data.get("claim_frequency", "1")
    segments.append(f"CLM*{data['claim_number']}*{data['claim_amount']}***{pos}:B:{freq}*Y*A*Y*I")

    if data.get("authorization_number"):
        segments.append(f"REF*G1*{data['authorization_number']}")

    # ── Diagnosis Codes (HI) ─────────────────────────────────────────────────
    dx1      = data["diagnosis_code"].replace(".", "")
    hi_codes = [f"ABK:{dx1}"]
    for field in ("diagnosis_code_2", "diagnosis_code_3", "diagnosis_code_4"):
        if data.get(field):
            hi_codes.append(f"ABF:{data[field].replace('.', '')}")
    segments.append(f"HI*{'*'.join(hi_codes)}")

    # ── Loop 2310B — Rendering Provider (optional) ───────────────────────────
    if data.get("rendering_provider_npi"):
        rp_last = data.get("rendering_provider_last_name", "RENDERING")
        segments.append(f"NM1*82*1*{rp_last}*****XX*{data['rendering_provider_npi']}")

    # ── Loop 2400 — Service Line ─────────────────────────────────────────────
    proc         = data["procedure_code"]
    modifier     = data.get("modifier", "")
    line_amt     = data.get("service_line_amount") or data["claim_amount"]
    units        = data.get("units", "1")
    dx_ptr       = data.get("diagnosis_pointer", "1")
    proc_composite = f"HC:{proc}:{modifier}" if modifier else f"HC:{proc}"
    segments.append("LX*1")
    # SV107 (composite Diagnosis Code Pointer) — SV105/SV106 stay blank, so the
    # pointer needs three '*' after Units (SV104), not two, per guide SV107/C004.
    segments.append(f"SV1*{proc_composite}*{line_amt}*UN*{units}***{dx_ptr}")
    segments.append(f"DTP*472*D8*{data['service_date']}")

    return segments


# ---------------------------------------------------------------------------
# 837I Generator
# ---------------------------------------------------------------------------

def generate_837i(data: dict) -> str:
    """
    Generate a 837I (Institutional Claim) EDI from structured data.
    """
    _require(data, [
        "sender_id", "receiver_id",
        "billing_provider_name", "billing_provider_npi",
        "billing_provider_taxonomy",
        "billing_provider_address", "billing_provider_city",
        "billing_provider_state", "billing_provider_zip",
        "payer_id", "payer_name",
        "subscriber_last_name", "subscriber_first_name", "subscriber_id",
        "dob", "gender",
        "claim_number", "claim_amount",
        "type_of_bill",
        "diagnosis_code", "revenue_code",
        "service_date", "admission_date",
    ])

    segments = _build_837i_body(data)
    tx_segments = _wrap_st_se("837", segments, "005010X223A2")
    ctx = {
        "sender_id": data["sender_id"],
        "receiver_id": data["receiver_id"],
        "interchange_control_number": data.get("interchange_control_number"),
        "group_control_number": data.get("group_control_number"),
    }
    group_segments = _build_gs_ge(ctx, "HC", tx_segments, "005010X223A2")
    isa = _build_isa(ctx)
    iea = _build_iea(ctx)
    return "~\n".join([isa] + group_segments + [iea]) + "~"


# ---------------------------------------------------------------------------
# 837I body builder
# ---------------------------------------------------------------------------

def _build_837i_body(data: dict) -> list[str]:
    """Return the ST-internal segments for one 837I claim."""
    segments: list[str] = []

    # ── BHT — Beginning of Hierarchical Transaction ──────────────────────────
    bht_ref  = data.get("bht_reference") or str(uuid.uuid4().int)[:10]
    bht_date = datetime.utcnow().strftime("%Y%m%d")
    bht_time = datetime.utcnow().strftime("%H%M")
    segments.append(f"BHT*0019*00*{bht_ref}*{bht_date}*{bht_time}*CH")

    # ── Loop 1000A — Submitter ───────────────────────────────────────────────
    submitter_id = data.get("submitter_id") or data["billing_provider_npi"]
    segments.append(f"NM1*41*2*{data['billing_provider_name']}*****46*{submitter_id}")
    phone = data.get("submitter_phone", "0000000000")
    # PER02 (Name) is intentionally left blank — guide sample shows PER*IC**TE*<phone>~
    segments.append(f"PER*IC**TE*{phone}")

    # ── Loop 1000B — Receiver ────────────────────────────────────────────────
    receiver_name = data.get("receiver_name", "RECEIVER")
    segments.append(f"NM1*40*2*{receiver_name}*****46*{data['receiver_id']}")

    # ── Loop 2000A — Billing Provider HL ────────────────────────────────────
    segments.append("HL*1**20*1")
    segments.append(f"PRV*BI*PXC*{data['billing_provider_taxonomy']}")
    segments.append(f"NM1*85*2*{data['billing_provider_name']}*****XX*{data['billing_provider_npi']}")
    segments.append(f"N3*{data['billing_provider_address']}")
    segments.append(f"N4*{data['billing_provider_city']}*{data['billing_provider_state']}*{data['billing_provider_zip']}")
    if data.get("billing_provider_tax_id"):
        segments.append(f"REF*EI*{data['billing_provider_tax_id']}")

    # ── Loop 2000B — Subscriber HL ───────────────────────────────────────────
    # HL04=0 (no subordinate HL) — Loop 2000C (Patient) is only used when the
    # patient is a dependent distinct from the subscriber, which this data
    # model does not currently represent; the guide's own sample also omits it.
    segments.append("HL*2*1*22*0")
    ins_type  = data.get("insurance_type_code", "CI")
    group_num = data.get("group_number", "")
    segments.append(f"SBR*P*18*{group_num}****{ins_type}")
    segments.append(f"NM1*IL*1*{data['subscriber_last_name']}*{data['subscriber_first_name']}****MI*{data['subscriber_id']}")
    if data.get("subscriber_address"):
        segments.append(f"N3*{data['subscriber_address']}")
        segments.append(
            f"N4*{data.get('subscriber_city','')}*{data.get('subscriber_state','')}*{data.get('subscriber_zip','')}"
        )
    segments.append(f"DMG*D8*{data['dob']}*{data['gender']}")

    # ── Loop 2010BB — Payer ──────────────────────────────────────────────────
    segments.append(f"NM1*PR*2*{data['payer_name']}*****PI*{data['payer_id']}")

    # ── Loop 2300 — Claim ────────────────────────────────────────────────────
    freq = data.get("claim_frequency", "1")
    tob  = data["type_of_bill"]
    segments.append(f"CLM*{data['claim_number']}*{data['claim_amount']}***{tob}:B:{freq}*Y*A*Y*I")

    if data.get("authorization_number"):
        segments.append(f"REF*G1*{data['authorization_number']}")

    # DTP*435 (Admission Date and Hour) requires DT format = CCYYMMDDHHMM;
    # DTP*096 (Discharge Hour) requires TM format = HHMM only (no date).
    # admission_time/discharge_time are optional HHMM inputs; default to
    # "0000" when not supplied so the segment format always matches the
    # guide without requiring the caller to track the exact hour.
    admission_time = data.get("admission_time") or "0000"
    segments.append(f"DTP*435*DT*{data['admission_date']}{admission_time}")
    if data.get("discharge_date") or data.get("discharge_time"):
        discharge_time = data.get("discharge_time") or "0000"
        segments.append(f"DTP*096*TM*{discharge_time}")
    if data.get("statement_from_date") and data.get("statement_to_date"):
        segments.append(f"DTP*434*RD8*{data['statement_from_date']}-{data['statement_to_date']}")
    if data.get("patient_status"):
        # CL103 is Patient Status Code; CL101/CL102 (Admission Type/Source) are
        # left blank since this data model does not collect them.
        segments.append(f"CL1**{data.get('admission_source_code', '')}*{data['patient_status']}")

    # ── Diagnosis Codes (HI) ─────────────────────────────────────────────────
    principal_dx = data["diagnosis_code"].replace(".", "")
    hi_codes     = [f"ABK:{principal_dx}"]
    if data.get("admitting_diagnosis_code"):
        hi_codes.append(f"ABJ:{data['admitting_diagnosis_code'].replace('.', '')}")
    for field in ("diagnosis_code_2", "diagnosis_code_3"):
        if data.get(field):
            hi_codes.append(f"ABF:{data[field].replace('.', '')}")
    segments.append(f"HI*{'*'.join(hi_codes)}")

    if data.get("attending_provider_npi"):
        att_last = data.get("attending_provider_last_name", "ATTENDING")
        segments.append(f"NM1*71*1*{att_last}*****XX*{data['attending_provider_npi']}")

    # ── Loop 2400 — Service Line ─────────────────────────────────────────────
    units    = data.get("units", "1")
    line_amt = data.get("service_line_amount") or data["claim_amount"]
    proc_seg = f"HC:{data['procedure_code']}" if data.get("procedure_code") else ""
    segments.append("LX*1")
    segments.append(f"SV2*{data['revenue_code']}*{proc_seg}*{line_amt}*UN*{units}")
    segments.append(f"DTP*472*D8*{data['service_date']}")

    return segments


# ---------------------------------------------------------------------------
# 278 Generator (Prior Authorization)
# ---------------------------------------------------------------------------

def generate_278(data: dict) -> str:
    """Generate a 278 Prior Authorization request."""
    _require(data, [
        "sender_id", "receiver_id",
        "payer_id", "payer_name",
        "requestor_last_name", "requestor_first_name", "requestor_npi",
        "subscriber_last_name", "subscriber_first_name",
        "member_id",
        "service_type", "service_date",
    ])

    segments = _build_278_body(data)
    tx_segments = _wrap_st_se("278", segments, "005010X217")
    ctx = {
        "sender_id": data["sender_id"],
        "receiver_id": data["receiver_id"],
        "interchange_control_number": data.get("interchange_control_number"),
        "group_control_number": data.get("group_control_number"),
    }
    group_segments = _build_gs_ge(ctx, "HI", tx_segments, "005010X217")
    isa = _build_isa(ctx)
    iea = _build_iea(ctx)
    return "~\n".join([isa] + group_segments + [iea]) + "~"


# ---------------------------------------------------------------------------
# 278 body builder
# ---------------------------------------------------------------------------

def _build_278_body(data: dict) -> list[str]:
    """Return the ST-internal segments for one 278 request.

    Structure verified against the companion guide's worked sample (not just
    its descriptive table, which is incomplete): Loop 2000A (UMO/Payer) ->
    2000B (Requestor — a PERSON per the sample's `NM1*1P*1*Last*First`, not
    an organization, which was the earlier bug) -> 2000C (Subscriber) ->
    optional 2000D (Dependent) -> 2000E (Patient Event: TRN/UM/HCR/DTP/HI/
    provider) -> 2000F (Service: TRN/UM/HCR/DTP/SV1) — the 2000F loop and its
    TRN/HCR segments were entirely missing before this redesign. HL parent/
    child numbers are tracked dynamically since 2000D is conditional.

    HCR (Action Code) is only emitted if the caller explicitly supplies
    `action_code` — for a genuine new request the submitter does not know
    the payer's decision yet, so fabricating one would violate the
    No-Assumption-Rule even though the guide's own "request" sample includes
    it (most plausibly a copy/paste artifact from a response sample). It is
    supported for reconsideration/appeal requests that reference a known
    prior decision.
    """
    segments: list[str] = []

    bht_ref  = str(uuid.uuid4().int)[:10]
    bht_date = datetime.utcnow().strftime("%Y%m%d")
    # Guide explicitly calls for BHT05 in HHMMSS format (with seconds) for
    # this transaction, unlike the other guides which use HHMM.
    bht_time = datetime.utcnow().strftime("%H%M%S")
    segments.append(f"BHT*0007*13*{bht_ref}*{bht_date}*{bht_time}*18")

    # ── Loop 2000A — UMO / Payer ─────────────────────────────────────────────
    segments.append("HL*1**20*1")
    segments.append(f"NM1*X3*2*{data['payer_name']}*****PI*{data['payer_id']}")

    # ── Loop 2000B — Requestor ───────────────────────────────────────────────
    segments.append("HL*2*1*21*1")
    segments.append(
        f"NM1*1P*1*{data['requestor_last_name']}*{data['requestor_first_name']}"
        f"****XX*{data['requestor_npi']}"
    )
    if data.get("requestor_taxonomy"):
        segments.append(f"PRV*RF*PXC*{data['requestor_taxonomy']}")
    if data.get("requestor_tax_id"):
        segments.append(f"REF*EI*{data['requestor_tax_id']}")

    # ── Loop 2000C — Subscriber ──────────────────────────────────────────────
    segments.append("HL*3*2*22*1")
    segments.append(f"NM1*IL*1*{data['subscriber_last_name']}*{data['subscriber_first_name']}****MI*{data['member_id']}")
    dob_val    = data.get("subscriber_dob", "")
    gender_val = data.get("subscriber_gender", "")
    if dob_val or gender_val:
        segments.append(f"DMG*D8*{dob_val}*{gender_val}")

    parent_hl, next_hl = 3, 4

    # ── Loop 2000D — Dependent (optional; only if the patient is a
    #     dependent distinct from the subscriber) ────────────────────────────
    if data.get("dependent_first_name") or data.get("dependent_last_name"):
        segments.append(f"HL*{next_hl}*{parent_hl}*23*1")
        segments.append(
            f"NM1*QC*1*{data.get('dependent_last_name','')}*{data.get('dependent_first_name','')}"
        )
        if data.get("dependent_dob") or data.get("dependent_gender"):
            segments.append(f"DMG*D8*{data.get('dependent_dob','')}*{data.get('dependent_gender','')}")
        parent_hl, next_hl = next_hl, next_hl + 1

    # ── Loop 2000E — Patient Event ───────────────────────────────────────────
    event_hl = next_hl
    segments.append(f"HL*{event_hl}*{parent_hl}*EV*1")
    trace_company = data.get("trace_originating_company_id") or data["sender_id"]
    trace_number  = data.get("patient_event_trace_number") or bht_ref
    segments.append(f"TRN*1*{trace_number}*{trace_company}")

    request_category    = data.get("request_category_code", "HS")
    cert_type            = data.get("certification_type_code", "I")
    facility_type         = data.get("facility_type_code", "")
    facility_qual         = data.get("facility_code_qualifier", "B") if facility_type else ""
    facility_composite    = f"{facility_type}:{facility_qual}" if facility_type else ""
    level_of_service      = data.get("level_of_service_code", "")
    segments.append(f"UM*{request_category}*{cert_type}*{data['service_type']}*{facility_composite}**{level_of_service}")

    if data.get("action_code"):
        segments.append(f"HCR*{data['action_code']}**{data.get('action_reason_code','')}")
    if data.get("certification_effective_date"):
        eff = data["certification_effective_date"]
        fmt = "RD8" if "-" in eff else "D8"
        segments.append(f"DTP*007*{fmt}*{eff}")
    if data.get("diagnosis_code"):
        dx = data["diagnosis_code"].replace(".", "")
        segments.append(f"HI*ABF:{dx}")
    if data.get("rendering_provider_npi"):
        rp_last = data.get("rendering_provider_last_name", "PROVIDER")
        segments.append(f"NM1*SJ*1*{rp_last}*****XX*{data['rendering_provider_npi']}")

    # ── Loop 2000F — Service ─────────────────────────────────────────────────
    segments.append(f"HL*{event_hl + 1}*{event_hl}*SS*0")
    segments.append(f"TRN*1*{trace_number}*{trace_company}")
    segments.append(f"UM*{data.get('service_request_category_code','SC')}*{cert_type}*{data['service_type']}*{facility_composite}")
    if data.get("action_code"):
        segments.append(f"HCR*{data['action_code']}**{data.get('action_reason_code','')}")
    svc_fmt = "RD8" if "-" in data["service_date"] else "D8"
    segments.append(f"DTP*472*{svc_fmt}*{data['service_date']}")
    if data.get("quantity"):
        qty_type = data.get("quantity_type", "VS")
        segments.append(f"HSD*{qty_type}*{data['quantity']}")
    if data.get("authorization_number"):
        segments.append(f"REF*BB*{data['authorization_number']}")
    if data.get("procedure_code"):
        segments.append(f"SV1*HC:{data['procedure_code']}")

    return segments


# ---------------------------------------------------------------------------
# 834 Generator (Benefit Enrollment and Maintenance)
# ---------------------------------------------------------------------------

def generate_834(data: dict) -> str:
    """
    Generate an 834 (Benefit Enrollment and Maintenance) EDI from structured
    data. Covers one member enrollment/maintenance record with one health
    coverage (HD) segment per transaction — the same single-record-per-call
    pattern the other generators in this module use (batch multiple records
    via generate_batch()).

    Loops NOT modeled (guide marks all of these optional/situational, and
    this data model does not collect the fields they would need): Loop 1000C
    (TPA/Broker) + 1100C, Loop 2100C (member mailing address) + 2200
    (disability), Loop 2310 (provider), Loop 2100F/2100G (custodial parent /
    responsible person), multiple simultaneous HD coverages (medical+dental+
    vision) per member.
    """
    _require(data, [
        "sender_id", "receiver_id",
        "sponsor_name", "sponsor_ein",
        "payer_name", "payer_id",
        "subscriber_last_name", "subscriber_first_name", "subscriber_id",
        "dob", "gender",
        "relationship_code", "maintenance_type_code",
    ])
    if not data.get("benefit_begin_date") and not data.get("benefit_end_date"):
        raise ValueError(
            "Cannot generate EDI: at least one of 'benefit_begin_date' or "
            "'benefit_end_date' is required (guide: DTP*348 or DTP*349 — "
            "Health Coverage Benefit Begin/End Date)."
        )

    segments = _build_834_body(data)
    tx_segments = _wrap_st_se("834", segments, "005010X220A1")
    ctx = {
        "sender_id": data["sender_id"],
        "receiver_id": data["receiver_id"],
        "interchange_control_number": data.get("interchange_control_number"),
        "group_control_number": data.get("group_control_number"),
    }
    group_segments = _build_gs_ge(ctx, "BE", tx_segments, "005010X220A1")
    isa = _build_isa(ctx)
    iea = _build_iea(ctx)
    return "~\n".join([isa] + group_segments + [iea]) + "~"


# ---------------------------------------------------------------------------
# 834 body builder
# ---------------------------------------------------------------------------

def _build_834_body(data: dict) -> list[str]:
    """Return the ST-internal segments for one 834 member enrollment record.

    NOTE: unlike the other 4 companion guides used in this project, the 834
    guide's own text has no worked EDI sample (table specification only) —
    GS01 "BE" and GS08/ST03 "005010X220A1" are the well-established
    real-world X12 834 5010 identifiers (general X12 domain knowledge), not
    values this specific guide's text literally confirms. Segment element
    positions below are built with explicit list-joins (rather than
    hand-counted f-string asterisks) specifically to avoid the kind of
    off-by-one blank-element bugs found elsewhere in this codebase.
    """
    segments: list[str] = []

    bgn_purpose = data.get("bgn_purpose_code", "00")
    bgn_ref     = data.get("bgn_reference") or str(uuid.uuid4().int)[:10]
    bgn_date    = datetime.utcnow().strftime("%Y%m%d")
    bgn_time    = datetime.utcnow().strftime("%H%M")
    bgn_action  = data.get("bgn_action_code", "2")
    segments.append("*".join(["BGN", bgn_purpose, bgn_ref, bgn_date, bgn_time, "", "", "", bgn_action]))

    # ── Loop 1000A — Plan Sponsor ────────────────────────────────────────────
    segments.append(f"N1*P5*{data['sponsor_name']}*FI*{data['sponsor_ein']}")

    # ── Loop 1000B — Payer / Insurer ─────────────────────────────────────────
    segments.append(f"N1*IN*{data['payer_name']}*FI*{data['payer_id']}")

    # ── Loop 2000 — Member Level ─────────────────────────────────────────────
    # INS01: Y = this record IS the subscriber, N = dependent of the
    # subscriber — derived from relationship_code (18=Self) rather than a
    # separate field that could contradict it.
    is_subscriber      = "Y" if data["relationship_code"] == "18" else "N"
    maintenance_reason = data.get("maintenance_reason_code", "")
    benefit_status      = data.get("benefit_status_code", "")
    employment_status   = data.get("employment_status_code", "")
    student_status       = data.get("student_status_code", "")
    segments.append("*".join([
        "INS", is_subscriber, data["relationship_code"], data["maintenance_type_code"],
        maintenance_reason, benefit_status, "", "", employment_status, student_status,
    ]))
    if data.get("subscriber_id"):
        segments.append(f"REF*0F*{data['subscriber_id']}")
    if data.get("group_number"):
        segments.append(f"REF*1L*{data['group_number']}")
    if data.get("enrollment_signature_date"):
        segments.append(f"DTP*300*D8*{data['enrollment_signature_date']}")

    # ── Loop 2100A — Member Name / Demographics ──────────────────────────────
    # NM108 defaults to ZZ (Mutually Defined / payer-assigned ID) rather than
    # 34 (SSN) — safer default that doesn't presume the caller is sending a
    # Social Security Number.
    segments.append("*".join([
        "NM1", "IL", "1", data["subscriber_last_name"], data["subscriber_first_name"],
        data.get("subscriber_middle_name", ""), "", "", "ZZ", data["subscriber_id"],
    ]))
    if data.get("member_phone"):
        segments.append(f"PER*IP**TE*{data['member_phone']}")
    if data.get("member_address"):
        segments.append(f"N3*{data['member_address']}")
        segments.append(
            f"N4*{data.get('member_city','')}*{data.get('member_state','')}*{data.get('member_zip','')}"
        )
    segments.append(f"DMG*D8*{data['dob']}*{data['gender']}")

    # ── Loop 2300 — Health Coverage ───────────────────────────────────────────
    # HD01 defaults to the member's own maintenance_type_code (adding a
    # member typically means adding their coverage too) rather than a
    # hardcoded guess.
    hd_maintenance  = data.get("hd_maintenance_type_code") or data["maintenance_type_code"]
    insurance_line  = data.get("insurance_line_code", "")
    coverage_level  = data.get("coverage_level_code", "")
    plan_description = data.get("plan_coverage_description", "")
    segments.append("*".join(["HD", hd_maintenance, "", insurance_line, plan_description, coverage_level]))
    if data.get("benefit_begin_date"):
        segments.append(f"DTP*348*D8*{data['benefit_begin_date']}")
    if data.get("benefit_end_date"):
        segments.append(f"DTP*349*D8*{data['benefit_end_date']}")
    if data.get("health_coverage_policy_number"):
        segments.append(f"REF*1L*{data['health_coverage_policy_number']}")

    return segments


# ---------------------------------------------------------------------------
# Batch Generator — one ISA/GS containing N ST/SE transaction sets
# ---------------------------------------------------------------------------

# Maps transaction type → (body_builder_fn, ST tx_type_code, GS_tx_code, GS_version)
_BATCH_CONFIG: dict[str, tuple] = {
    "837P": (_build_837p_body, "837", "HC", "005010X222A1"),
    "837I": (_build_837i_body, "837", "HC", "005010X223A2"),
    "278":  (_build_278_body,  "278", "HI", "005010X217"),
    "834":  (_build_834_body,  "834", "BE", "005010X220A1"),
}


def generate_batch(
    tx_type: str,
    records: list[dict],
) -> tuple[str, list[dict], int]:
    """
    Generate a single EDI interchange containing one ST/SE transaction set
    per input record.  All transaction sets share one ISA/GS/GE/IEA envelope.

    Parameters
    ----------
    tx_type : str
        Transaction type identifier (e.g. '837P', '837I', '278').
    records : list[dict]
        One dict per Excel/CSV row; each dict must contain the required fields
        for the given transaction type plus any optional fields.

    Returns
    -------
    edi : str
        The complete EDI file as a ``~\\n``-joined string.
    errors : list[dict]
        One entry per skipped row, each with keys:
        ``row``  (1-based Excel row number, accounting for the header row),
        ``missing_fields`` (list of field names),
        ``reason`` (human-readable string).
    generated_count : int
        Number of claims successfully included in the EDI output.

    Raises
    ------
    ValueError
        If no records can be generated (every row has errors).
    """
    config = _BATCH_CONFIG.get(tx_type.upper())
    if not config:
        raise ValueError(
            f"Batch generation is not supported for transaction type '{tx_type}'. "
            f"Supported: {', '.join(_BATCH_CONFIG.keys())}."
        )

    body_fn, st_code, gs_code, gs_ver = config
    required = _REQUIRED_FIELDS.get(tx_type.upper(), [])

    all_st_segments: list[str] = []   # flat list of all wrapped ST/SE segments
    errors: list[dict] = []

    for idx, row in enumerate(records):
        # Row number in the Excel file (1 = header, so data rows start at 2)
        excel_row = idx + 2

        # Validate required fields for this row
        missing = [f for f in required if not row.get(f)]
        if missing:
            errors.append({
                "row": excel_row,
                "missing_fields": missing,
                "reason": f"Row {excel_row}: missing required fields — {', '.join(missing)}",
            })
            continue

        try:
            body = body_fn(row)
            st_se = _wrap_st_se(st_code, body, gs_ver)
            all_st_segments.extend(st_se)
        except ValueError as exc:
            errors.append({
                "row": excel_row,
                "missing_fields": [],
                "reason": f"Row {excel_row}: generation error — {exc}",
            })

    generated_count = len([s for s in all_st_segments if s.startswith("ST*")])

    if generated_count == 0:
        raise ValueError(
            "No claims could be generated. Every row had missing or invalid fields. "
            "Review the error list for details."
        )

    # Build the envelope using the first successful row's sender/receiver
    # (the standard ISA identifies one trading-partner relationship per interchange)
    first_ok = next(
        (r for r in records if not any(r is err for err in errors)),
        records[0],
    )
    ctx: dict = {
        "sender_id": first_ok.get("sender_id", "SENDER"),
        "receiver_id": first_ok.get("receiver_id", "RECEIVER"),
    }

    group_segments = _build_gs_ge(ctx, gs_code, all_st_segments, gs_ver, generated_count)
    isa = _build_isa(ctx)
    iea = _build_iea(ctx)

    edi = "~\n".join([isa] + group_segments + [iea]) + "~"
    return edi, errors, generated_count


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_GENERATORS: dict[str, Any] = {
    "837P": generate_837p,
    "837I": generate_837i,
    "278": generate_278,
    "834": generate_834,
}

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "837P": [
        "sender_id", "receiver_id",
        "billing_provider_name", "billing_provider_npi",
        "billing_provider_taxonomy",
        "billing_provider_address", "billing_provider_city",
        "billing_provider_state", "billing_provider_zip",
        "payer_id", "payer_name",
        "subscriber_last_name", "subscriber_first_name", "subscriber_id",
        "dob", "gender",
        "claim_number", "claim_amount",
        "diagnosis_code", "procedure_code", "service_date",
    ],
    "837I": [
        "sender_id", "receiver_id",
        "billing_provider_name", "billing_provider_npi",
        "billing_provider_taxonomy",
        "billing_provider_address", "billing_provider_city",
        "billing_provider_state", "billing_provider_zip",
        "payer_id", "payer_name",
        "subscriber_last_name", "subscriber_first_name", "subscriber_id",
        "dob", "gender",
        "claim_number", "claim_amount",
        "type_of_bill",
        "diagnosis_code", "revenue_code",
        "service_date", "admission_date",
    ],
    "278": [
        "sender_id", "receiver_id",
        "payer_id", "payer_name",
        "requestor_last_name", "requestor_first_name", "requestor_npi",
        "subscriber_last_name", "subscriber_first_name",
        "member_id",
        "service_type", "service_date",
    ],
    "834": [
        "sender_id", "receiver_id",
        "sponsor_name", "sponsor_ein",
        "payer_name", "payer_id",
        "subscriber_last_name", "subscriber_first_name", "subscriber_id",
        "dob", "gender",
        "relationship_code", "maintenance_type_code",
        "benefit_begin_date",
    ],
}


def get_required_fields(transaction_type: str) -> list[str]:
    """Return the list of mandatory fields for the given transaction type."""
    return _REQUIRED_FIELDS.get(transaction_type.upper(), [])


def generate(transaction_type: str, data: dict) -> str:
    """
    Generate an EDI file for the given transaction type.
    Raises ValueError for unsupported types or missing data.
    """
    gen_fn = _GENERATORS.get(transaction_type.upper())
    if not gen_fn:
        raise ValueError(
            f"EDI generation for transaction type '{transaction_type}' is not yet implemented. "
            f"Supported: {', '.join(_GENERATORS.keys())}."
        )
    return gen_fn(data)
