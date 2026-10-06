"""
engines/companion_guide_engine.py
Companion Guide Reader and Rule Extraction Engine.
Reads .docx and .pdf guides from the Companion_Guide folder.
Companion Guide is PRIMARY source of truth (AR-09).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from backend.models.schemas import (
    CompanionGuideRuleSchema,
    CompanionGuideSchema,
    ErrorSchema,
    RuleSource,
    Severity,
)
from backend.utils.file_handler import COMPANION_GUIDE_DIR

# ---------------------------------------------------------------------------
# Known guide file mappings
# ---------------------------------------------------------------------------

_GUIDE_MAP: dict[str, str] = {
    "837P": "837P_Companion_Guide.docx",
    "837I": "837I_Companion_Guide.docx",
    "278": "278_Companion_Guide.docx",
    "834": "EDI_834_Companion_Guide.docx",
    "820": "820_Version_ 218_Companion_Guide.docx",
    "277CA": "X12 HIPAA 277 Claim Acknowledgement (X214) - Stedi EDI Guides.pdf",
    "999": "X12 HIPAA 999 Implementation Acknowledgment (X231) - Stedi EDI Guides.pdf",
}

# Cache of loaded guides keyed by transaction_type
_guide_cache: dict[str, CompanionGuideSchema] = {}


# ---------------------------------------------------------------------------
# Text Extraction
# ---------------------------------------------------------------------------

def _extract_docx_text(file_path: Path) -> str:
    """Extract full text from a .docx file."""
    try:
        from docx import Document  # python-docx
        doc = Document(str(file_path))
        parts = []
        for para in doc.paragraphs:
            parts.append(para.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        return "\n".join(parts)
    except Exception as exc:
        return f"[ERROR extracting docx: {exc}]"


def _extract_pdf_text(file_path: Path) -> str:
    """Extract full text from a PDF file."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n".join(text_parts)
    except Exception as exc:
        return f"[ERROR extracting pdf: {exc}]"


def _extract_guide_text(file_path: Path) -> str:
    if file_path.suffix.lower() == ".docx":
        return _extract_docx_text(file_path)
    if file_path.suffix.lower() == ".pdf":
        return _extract_pdf_text(file_path)
    return file_path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Rule Extraction Heuristics
# ---------------------------------------------------------------------------

# Patterns that suggest a mandatory/conditional rule statement
_MANDATORY_PATTERNS = [
    re.compile(r"\bMUST\b", re.IGNORECASE),
    re.compile(r"\bREQUIRED\b", re.IGNORECASE),
    re.compile(r"\bMANDATORY\b", re.IGNORECASE),
    re.compile(r"\bSHALL\b", re.IGNORECASE),
]

_CONDITIONAL_PATTERNS = [
    re.compile(r"\bIF\b.+\bTHEN\b", re.IGNORECASE),
    re.compile(r"\bWHEN\b", re.IGNORECASE),
    re.compile(r"\bCONDITIONAL\b", re.IGNORECASE),
]

# Segment identifier pattern
_SEGMENT_RE = re.compile(r"\b([A-Z]{2,3})\b")
_ELEMENT_RE = re.compile(r"\b([A-Z]{2,3}\d{2})\b")
_LOOP_RE = re.compile(r"\bLoop\s+([\w]+)\b", re.IGNORECASE)

# Canonical list of real X12 segment IDs. The regexes above match ANY 2-3
# letter uppercase word sitting near "must/required/shall/mandatory" in the
# guide's raw extracted text — which, unfiltered, also matches ordinary
# prose acronyms (e.g. "ICD", "LIN", "CAS" used as plain words rather than
# segment references), producing fabricated "mandatory segment missing"
# errors on perfectly valid files. Only IDs in this set are accepted as
# genuine segment identifiers.
_VALID_SEGMENT_IDS: frozenset[str] = frozenset({
    "ISA", "IEA", "GS", "GE", "ST", "SE", "BHT", "BPR", "TRN", "REF", "DTM",
    "N1", "N2", "N3", "N4", "NM1", "PER", "CLM", "DTP", "HI", "SV1", "SV2",
    "SV3", "LX", "PWK", "CR1", "CRC", "AMT", "QTY", "HL", "PRV", "SBR", "PAT",
    "MOA", "PLB", "CLP", "CAS", "SVC", "INS", "HD", "IDC", "UM", "HSD", "HCR",
    "AK1", "AK2", "AK3", "AK4", "AK5", "AK9", "IK3", "IK4", "IK5", "STC",
    "QC", "TL", "DMG", "K3", "NTE", "CTP",
})


def _extract_rules_from_text(text: str, transaction_type: str) -> list[CompanionGuideRuleSchema]:
    """
    Heuristic rule extraction from guide text.
    Identifies lines containing mandatory/conditional rule language
    and associates them with segment/element references.
    """
    rules: list[CompanionGuideRuleSchema] = []
    lines = text.splitlines()
    current_loop = ""

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Track loop context
        loop_match = _LOOP_RE.search(line_stripped)
        if loop_match:
            current_loop = loop_match.group(1)

        is_mandatory = any(p.search(line_stripped) for p in _MANDATORY_PATTERNS)
        is_conditional = any(p.search(line_stripped) for p in _CONDITIONAL_PATTERNS)

        if not (is_mandatory or is_conditional):
            continue

        # Extract segment and element references
        element_matches = _ELEMENT_RE.findall(line_stripped)
        segment_matches = _SEGMENT_RE.findall(line_stripped)

        if element_matches:
            # Strip the trailing 2-digit element number to recover the
            # segment ID (e.g. "SE01" -> "SE", "CLM05" -> "CLM"). Blindly
            # slicing the first 3 characters corrupted 2-letter segment IDs
            # (e.g. "SE01"[:3] == "SE0", which is not a real segment).
            segment_id = element_matches[0][:-2]
        elif segment_matches:
            segment_id = segment_matches[0]
        else:
            segment_id = ""
        element_id = element_matches[0] if element_matches else ""

        # Reject anything that is not a recognized X12 segment ID — without
        # this filter, ordinary prose acronyms near "must/required" get
        # treated as fabricated "mandatory segments".
        if segment_id not in _VALID_SEGMENT_IDS:
            continue

        # Use surrounding lines for context
        context_start = max(0, i - 1)
        context_end = min(len(lines), i + 2)
        rule_text = " ".join(lines[context_start:context_end]).strip()

        rule = CompanionGuideRuleSchema(
            segment=segment_id,
            element=element_id,
            loop=current_loop,
            rule_text=rule_text[:500],  # cap length
            mandatory=is_mandatory,
            condition="conditional" if is_conditional else "",
            page_reference=f"line_{i+1}",
        )
        rules.append(rule)

    return rules


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_guide(transaction_type: str, force_reload: bool = False) -> CompanionGuideSchema:
    """
    Load and cache a Companion Guide for the given transaction type.
    Returns a CompanionGuideSchema with extracted rules.
    """
    if transaction_type in _guide_cache and not force_reload:
        return _guide_cache[transaction_type]

    file_name = _GUIDE_MAP.get(transaction_type)
    if not file_name:
        raise ValueError(f"No Companion Guide configured for transaction type: {transaction_type}")

    file_path = COMPANION_GUIDE_DIR / file_name
    if not file_path.exists():
        raise FileNotFoundError(f"Companion Guide file not found: {file_path}")

    text = _extract_guide_text(file_path)
    rules = _extract_rules_from_text(text, transaction_type)

    guide = CompanionGuideSchema(
        guide_name=file_name,
        version="",
        transaction_type=transaction_type,
        rules=rules,
        source_file=str(file_path),
    )
    _guide_cache[transaction_type] = guide
    return guide


def get_guide_rules(transaction_type: str) -> list[CompanionGuideRuleSchema]:
    """Return rules for a transaction type, loading guide if needed."""
    guide = load_guide(transaction_type)
    return guide.rules


# ---------------------------------------------------------------------------
# Per-qualifier NM1 rules — sourced directly from each companion guide.
#
# Structure: { transaction_type: { nm101_qualifier: rule_dict } }
#
# rule_dict keys:
#   nm108       – set of allowed NM108 (ID-code qualifier) values
#   nm108_sev   – "ERROR" or "WARNING" (default WARNING for receiver)
#   npi_required– True when NM108=XX must carry a 10-digit NPI in NM109
#   id_required – True when NM109 must not be empty whenever NM108 is set
#   name_required–True when NM103 (last/org name) must be populated
#   description – human-readable label
#   loop        – loop ID from guide
#
# Sources:
#   837P → 837P_Companion_Guide.docx
#   837I → 837I_Companion_Guide.docx
#   278  → 278_Companion_Guide.docx
#   834  → uses N1, not NM1 — no NM1 rules
#   820  → uses N1, not NM1 — no NM1 rules
#   277CA/999 → acknowledgment responses, no payer-specific NM1 constraints
# ---------------------------------------------------------------------------

def _rule(desc: str, loop: str, nm108: set, npi_req: bool = False,
          id_req: bool = False, name_req: bool = False,
          nm108_sev: str = "ERROR") -> dict:
    return {
        "description": desc, "loop": loop, "nm108": nm108,
        "npi_required": npi_req, "id_required": id_req,
        "name_required": name_req, "nm108_sev": nm108_sev,
    }


_NM1_RULES_BY_TX: dict[str, dict[str, dict]] = {
    # ── 837P Professional Claim ─────────────────────────────────────────────
    # Source: 837P_Companion_Guide.docx table
    "837P": {
        "41":  _rule("Submitter Name",            "1000A", {"46"},        id_req=True,   name_req=True),
        "40":  _rule("Receiver Name",             "1000B", {"46"},        nm108_sev="WARNING"),        # guide table says PR, but PR is not a valid ID Code Qualifier (code list 66) and the guide's own sample uses 46 (ETIN) — same as 837I
        "85":  _rule("Billing Provider",          "2010AA", {"XX"},       npi_req=True, id_req=True, name_req=True),
        "IL":  _rule("Subscriber / Insured",      "2010BA", {"MI", "HN"}, id_req=True,  name_req=True),
        "PR":  _rule("Payer",                     "2010BB", {"PI"},       id_req=True,  name_req=True),
        "DN":  _rule("Referring Provider",        "2310A",  {"XX"},       npi_req=True),
        "82":  _rule("Rendering Provider",        "2310B",  {"XX"},       npi_req=True),
        "77":  _rule("Service Facility",          "2310C",  {"XX"},       npi_req=True),  # guide: NM108=XX, NPI
        "DQ":  _rule("Supervising Provider",      "2310D",  {"XX"},       npi_req=True),
        "1P":  _rule("Ordering Provider",         "2310E",  {"XX"},       npi_req=True),
        "QD":  _rule("Patient (if not subscriber)", "2330", set()),
        "TT":  _rule("Crossover Payer",           "2330B",  {"PI"},       id_req=True),
    },
    # ── 837I Institutional Claim ────────────────────────────────────────────
    # Source: 837I_Companion_Guide.docx table
    # Key differences vs 837P:
    #   • NM1*71 Attending Physician (loop 2310A)  — 837I only
    #   • NM1*72 Operating Physician (loop 2310B)  — 837I only
    #   • NM1*82 Rendering Provider (loop 2310D)
    #   • NM1*77 Service Facility (loop 2310E)
    #   • NM1*DN Referring Provider (loop 2310F)
    "837I": {
        "41":  _rule("Submitter Name",            "1000A",  {"46"},       id_req=True,  name_req=True),
        "40":  _rule("Receiver Name",             "1000B",  {"46"},       nm108_sev="WARNING"),  # 837I guide: NM108=46 (ETIN)
        "85":  _rule("Billing Provider",          "2010AA", {"XX"},       npi_req=True, id_req=True, name_req=True),
        "IL":  _rule("Subscriber / Insured",      "2010BA", {"MI"},       id_req=True,  name_req=True),
        "PR":  _rule("Payer",                     "2010BB", {"PI"},       id_req=True,  name_req=True),
        "71":  _rule("Attending Physician",       "2310A",  {"XX"},       npi_req=True),  # 837I only
        "72":  _rule("Operating Physician",       "2310B",  {"XX"},       npi_req=True),  # 837I only
        "82":  _rule("Rendering Provider",        "2310D",  {"XX"},       npi_req=True),
        "77":  _rule("Service Facility",          "2310E",  {"XX"},       npi_req=True),
        "DN":  _rule("Referring Provider",        "2310F",  {"XX"},       npi_req=True),
        "QD":  _rule("Patient (if not subscriber)", "2330", set()),
        "TT":  _rule("Crossover Payer",           "2330B",  {"PI"},       id_req=True),
    },
    # ── 278 Health Care Authorization Request ────────────────────────────────
    # Source: 278_Companion_Guide.docx table
    # Completely different qualifier set from 837x
    "278": {
        "X3":  _rule("UMO (Review Entity / Payer)", "2010A", {"PI", "24"}, id_req=True, name_req=True),
        "1P":  _rule("Requestor — Practitioner",   "2010B",  {"XX"},       npi_req=True, id_req=True, name_req=True),
        "FA":  _rule("Requestor — Facility",       "2010B",  {"XX"},       id_req=True,  name_req=True),
        "PR":  _rule("Requestor — Payer",          "2010B",  {"PI"},       id_req=True),
        "IL":  _rule("Subscriber",                 "2010C",  {"MI"},       id_req=True,  name_req=True),
        "QC":  _rule("Patient / Dependent",        "2010D",  set()),                     # no ID qualifier per guide
        "SJ":  _rule("Service Provider",           "2000E",  {"XX"},       npi_req=True, id_req=True),
        "DN":  _rule("Referring / Ordering Provider", "2000E", {"XX"},     npi_req=True),
    },
    # 834 and 820 use N1 (not NM1) for entity names — no NM1 rules apply
}

# ---------------------------------------------------------------------------
# Per-qualifier DTP rules — sourced directly from each companion guide.
#
# Structure: { transaction_type: { dtp01_qualifier: rule_dict } }
#
# rule_dict keys:
#   description – human-readable label
#   formats     – set of allowed DTP02 format codes
#   loop        – loop ID from guide
#
# Sources (authoritative quotes from each guide):
#   837P: DTP*472 DTP02=RD8 (but sample shows D8; both accepted per user)
#         DTP*435 DTP02=D8 (if present)
#         DTP*096 DTP02=D8 (if present)
#   837I: DTP*472 DTP02=RD8 (service date, loop 2400)
#         DTP*435 DTP02=DT  "Admission Date and Hour: CCYYMMDDHHMM"
#         DTP*096 DTP02=TM  "Discharge Hour" (time only, not date)
#         DTP*434 DTP02=RD8 "Statement From and To Date: CCYYMMDD-CCYYMMDD"
#   278:  DTP*472 DTP02=RD8 (service dates)
#         DTP*007 DTP02=D8 or RD8 (effective/termination dates)
#         DTP*AAH DTP02=D8 or RD8 (authorization dates)
#   834:  DTP*007 DTP02=D8 or RD8 (certification dates)
#         DTP*300 DTP02=D8 (enrollment benefit date)
#         DTP*336 DTP02=D8 (benefit date)
# ---------------------------------------------------------------------------

def _dtp(desc: str, loop: str, formats: set) -> dict:
    return {"description": desc, "loop": loop, "formats": formats}


_DTP_RULES_BY_TX: dict[str, dict[str, dict]] = {
    "837P": {
        # Service date — guide table says RD8; sample uses D8; both accepted
        "472": _dtp("Service Date",                   "2400", {"D8", "RD8"}),
        # Claim-level dates
        "435": _dtp("Admission Date",                 "2300", {"D8"}),
        "096": _dtp("Discharge Date",                 "2300", {"D8"}),
        "304": _dtp("Last Date Worked",               "2300", {"D8"}),
        "360": _dtp("Start of Care Date",             "2300", {"D8"}),
        "361": _dtp("Last Certification Date",        "2300", {"D8"}),
        "484": _dtp("Initial Treatment Date",         "2300", {"D8"}),
        "455": _dtp("Last Menstrual Period",          "2300", {"D8"}),
        "471": _dtp("Onset of Current Symptom",      "2300", {"D8"}),
        "090": _dtp("Report Start Date",             "2300", {"D8"}),
        "091": _dtp("Report End Date",               "2300", {"D8"}),
        "444": _dtp("Current Illness / Injury Date", "2300", {"D8"}),
        "439": _dtp("Accident Date",                 "2300", {"D8"}),
        "050": _dtp("Repricer Received Date",        "2300", {"D8"}),
        "102": _dtp("Issue Date",                    "2300", {"D8"}),
    },
    "837I": {
        # Service date (2400) — D8 or RD8
        "472": _dtp("Service Date",                   "2400", {"D8", "RD8"}),
        # 837I-specific claim dates — guide quotes exact formats:
        "435": _dtp("Admission Date and Hour",        "2300", {"DT"}),      # guide: DT=CCYYMMDDHHMM
        "096": _dtp("Discharge Hour",                 "2300", {"TM"}),      # guide: TM=HHMM (time only)
        "434": _dtp("Statement From and To Dates",    "2300", {"RD8"}),     # guide: RD8=CCYYMMDD-CCYYMMDD
        # Shared claim-level dates (same formats as 837P)
        "304": _dtp("Last Date Worked",               "2300", {"D8"}),
        "360": _dtp("Start of Care Date",             "2300", {"D8"}),
        "484": _dtp("Initial Treatment Date",         "2300", {"D8"}),
        "090": _dtp("Report Start Date",              "2300", {"D8"}),
        "091": _dtp("Report End Date",                "2300", {"D8"}),
        "444": _dtp("Current Illness / Injury Date",  "2300", {"D8"}),
        "439": _dtp("Accident Date",                  "2300", {"D8"}),
    },
    "278": {
        "472": _dtp("Service Date",                   "2000E", {"D8", "RD8"}),
        "007": _dtp("Effective / Certification Date", "2000E", {"D8", "RD8"}),
        "AAH": _dtp("Authorization Period Start",     "2000E", {"D8", "RD8"}),
        "AAI": _dtp("Authorization Period End",       "2000E", {"D8", "RD8"}),
        "435": _dtp("Admission Date",                 "2000E", {"D8", "DT"}),
        "096": _dtp("Discharge Date",                 "2000E", {"D8"}),
    },
    "834": {
        # Loop 2000E / 2750 — Effective / Reporting Category Date
        "007": _dtp("Effective / Certification Date", "2000E", {"D8", "RD8"}),
        # Loop 2000 — MEMBER LEVEL DATES (D8 only per guide)
        "300": _dtp("Enrollment Signature Date",      "2000",  {"D8"}),   # also valid in loop 2300
        "301": _dtp("COBRA Qualifying Event",          "2000",  {"D8"}),
        "303": _dtp("Maintenance Effective Date",      "2000",  {"D8"}),   # also valid in loop 2300
        "336": _dtp("Employment Begin Date",           "2000",  {"D8"}),
        "337": _dtp("Employment End Date",             "2000",  {"D8"}),
        "338": _dtp("Medicare Begin Date",             "2000",  {"D8"}),
        "339": _dtp("Medicare End Date",               "2000",  {"D8"}),
        "340": _dtp("COBRA Begin Date",                "2000",  {"D8"}),
        "341": _dtp("COBRA End Date",                  "2000",  {"D8"}),
        "356": _dtp("Eligibility Begin Date",          "2000",  {"D8"}),
        "357": _dtp("Eligibility End Date",            "2000",  {"D8"}),
        "385": _dtp("Credited Service Begin Date",     "2000",  {"D8"}),
        "386": _dtp("Credited Service End Date",       "2000",  {"D8"}),
        "473": _dtp("Medicaid Begin Date",             "2000",  {"D8"}),
        "474": _dtp("Medicaid End Date",               "2000",  {"D8"}),
        # Loop 2200 — DISABILITY ELIGIBILITY DATES
        "360": _dtp("Initial Disability Period Start", "2200",  {"D8"}),
        "361": _dtp("Initial Disability Period End",   "2200",  {"D8"}),
        # Loop 2300 — HEALTH COVERAGE DATES (348 or 349 required per guide)
        "343": _dtp("Premium Paid to Date End",        "2300",  {"D8", "RD8"}),
        "348": _dtp("Benefit Begin Date",              "2300",  {"D8", "RD8"}),
        "349": _dtp("Benefit End Date",                "2300",  {"D8", "RD8"}),
        "543": _dtp("Last Premium Paid Date",          "2300",  {"D8", "RD8"}),
        "695": _dtp("Previous Period",                 "2300",  {"D8", "RD8"}),
    },
    "820": {
        # 820 has very limited DTP use; BPR16 is the main date
    },
}

# Shared date format validators
_NPI_RE    = re.compile(r"^\d{10}$")
_DATE_D8_RE  = re.compile(r"^\d{8}$")
_DATE_RD8_RE = re.compile(r"^\d{8}-\d{8}$")
_DATE_DT_RE  = re.compile(r"^\d{12}$")
_TIME_TM_RE  = re.compile(r"^\d{4,6}$")    # TM format: HHMM or HHMMSS


def _validate_nm1_segments(
    segments: list[str],
    element_sep: str,
    transaction_type: str,
) -> list[ErrorSchema]:
    """
    Validate each NM1 segment against the companion guide rules for its entity
    qualifier and transaction type.

    Errors use qualifier-encoded segment labels (e.g. 'NM1-85') so the UI
    pins each error to the correct NM1 occurrence only, never to others.
    """
    errors: list[ErrorSchema] = []
    tx_rules = _NM1_RULES_BY_TX.get(transaction_type, {})
    nm1_segs = [s for s in segments if s.split(element_sep)[0].strip() == "NM1"]

    for nm1 in nm1_segs:
        parts = [p.strip() for p in nm1.split(element_sep)]
        qualifier = parts[1] if len(parts) > 1 else ""
        rule = tx_rules.get(qualifier)
        if not rule:
            continue  # qualifier not covered by this tx-type's guide — skip

        seg_label = f"NM1-{qualifier}"
        loop      = rule["loop"]
        prefix    = f"{rule['description']} ({seg_label}, Loop {loop})"
        nm108_sev = Severity.ERROR if rule.get("nm108_sev", "ERROR") == "ERROR" else Severity.WARNING

        # ── NM103: organisation/last name required? ──────────────────────
        nm103 = parts[3] if len(parts) > 3 else ""
        if rule.get("name_required") and not nm103:
            errors.append(ErrorSchema(
                severity=Severity.ERROR, segment=seg_label, element="NM103", loop=loop,
                description=f"{prefix}: Name (NM103) is required but empty.",
                source=RuleSource.COMPANION_GUIDE, rule_reference="CG-NM1-103",
                suggested_correction=f"Populate NM103 with the {rule['description']} name.",
            ))

        # ── NM108: ID-code qualifier must be in the allowed set ───────────
        nm108 = parts[8] if len(parts) > 8 else ""
        nm109 = parts[9].rstrip("~").strip() if len(parts) > 9 else ""
        allowed_nm108 = rule.get("nm108", set())

        if allowed_nm108 and nm108 and nm108 not in allowed_nm108:
            errors.append(ErrorSchema(
                severity=nm108_sev, segment=seg_label, element="NM108", loop=loop,
                description=(
                    f"{prefix}: ID Code Qualifier NM108='{nm108}' is not expected per the "
                    f"{transaction_type} Companion Guide. Expected: {', '.join(sorted(allowed_nm108))}."
                ),
                source=RuleSource.COMPANION_GUIDE, rule_reference="CG-NM1-108",
                suggested_correction=f"Set NM108 to {' or '.join(sorted(allowed_nm108))}.",
            ))

        # ── NM109: ID value must be present when NM108 is set ────────────
        if rule.get("id_required") and nm108 and not nm109:
            errors.append(ErrorSchema(
                severity=Severity.ERROR, segment=seg_label, element="NM109", loop=loop,
                description=f"{prefix}: Identifier (NM109) is required but empty.",
                source=RuleSource.COMPANION_GUIDE, rule_reference="CG-NM1-109",
                suggested_correction=f"Provide the {rule['description']} identifier in NM109.",
            ))

        # ── NM109: 10-digit NPI validation when guide says NPI required ───
        if rule.get("npi_required") and nm108 == "XX":
            if not nm109:
                errors.append(ErrorSchema(
                    severity=Severity.ERROR, segment=seg_label, element="NM109", loop=loop,
                    description=f"{prefix}: NPI (NM109) is required but empty.",
                    source=RuleSource.COMPANION_GUIDE, rule_reference="CG-NM1-NPI",
                    suggested_correction="Provide a valid 10-digit NPI in NM109.",
                ))
            elif not _NPI_RE.match(nm109):
                errors.append(ErrorSchema(
                    severity=Severity.ERROR, segment=seg_label, element="NM109", loop=loop,
                    description=(
                        f"{prefix}: NPI '{nm109}' is invalid — must be exactly 10 digits "
                        f"per {transaction_type} Companion Guide."
                    ),
                    source=RuleSource.COMPANION_GUIDE, rule_reference="CG-NM1-NPI",
                    suggested_correction="Provide a valid 10-digit NPI in NM109.",
                ))

    return errors


def _validate_dtp_segments(
    segments: list[str],
    element_sep: str,
    transaction_type: str,
) -> list[ErrorSchema]:
    """
    Validate each DTP segment against the companion guide rules for its qualifier
    and transaction type.

    Errors use qualifier-encoded labels (e.g. 'DTP-472', 'DTP-435') so the UI
    pins each error to the correct DTP occurrence only.
    """
    errors: list[ErrorSchema] = []
    tx_rules = _DTP_RULES_BY_TX.get(transaction_type, {})
    dtp_segs = [s for s in segments if s.split(element_sep)[0].strip() == "DTP"]

    for dtp in dtp_segs:
        parts = [p.strip() for p in dtp.split(element_sep)]
        qualifier = parts[1] if len(parts) > 1 else ""
        rule      = tx_rules.get(qualifier)
        seg_label = f"DTP-{qualifier}"
        prefix    = rule["description"] if rule else f"DTP qualifier {qualifier}"
        loop      = rule["loop"] if rule else ""
        allowed_formats = rule["formats"] if rule else {"D8", "RD8", "DT", "TM"}

        dtp02 = parts[2] if len(parts) > 2 else ""
        dtp03 = parts[3].rstrip("~").strip() if len(parts) > 3 else ""

        # ── DTP02 format code ─────────────────────────────────────────────
        if dtp02 and dtp02 not in allowed_formats:
            errors.append(ErrorSchema(
                severity=Severity.WARNING, segment=seg_label, element="DTP02", loop=loop,
                description=(
                    f"{prefix} ({seg_label}): DTP02 format code '{dtp02}' is not expected "
                    f"per {transaction_type} Companion Guide. "
                    f"Allowed: {', '.join(sorted(allowed_formats))}."
                ),
                source=RuleSource.COMPANION_GUIDE, rule_reference="CG-DTP-02",
                suggested_correction=f"Set DTP02 to {' or '.join(sorted(allowed_formats))}.",
            ))

        # ── DTP03 value must be present when DTP02 is set ────────────────
        if dtp02 and not dtp03:
            errors.append(ErrorSchema(
                severity=Severity.ERROR, segment=seg_label, element="DTP03", loop=loop,
                description=f"{prefix} ({seg_label}): Date value (DTP03) is required but empty.",
                source=RuleSource.COMPANION_GUIDE, rule_reference="CG-DTP-03",
                suggested_correction="Provide a valid date value in DTP03.",
            ))
        elif dtp03:
            # ── Format-specific value validation ──────────────────────────
            if dtp02 == "D8" and not _DATE_D8_RE.match(dtp03):
                errors.append(ErrorSchema(
                    severity=Severity.ERROR, segment=seg_label, element="DTP03", loop=loop,
                    description=(
                        f"{prefix} ({seg_label}): '{dtp03}' does not match D8 (CCYYMMDD)."
                    ),
                    source=RuleSource.COMPANION_GUIDE, rule_reference="CG-DTP-03",
                    suggested_correction="Use 8-digit date CCYYMMDD, e.g. 20240115.",
                ))
            elif dtp02 == "RD8" and not _DATE_RD8_RE.match(dtp03):
                errors.append(ErrorSchema(
                    severity=Severity.ERROR, segment=seg_label, element="DTP03", loop=loop,
                    description=(
                        f"{prefix} ({seg_label}): '{dtp03}' does not match RD8 "
                        f"(CCYYMMDD-CCYYMMDD)."
                    ),
                    source=RuleSource.COMPANION_GUIDE, rule_reference="CG-DTP-03",
                    suggested_correction="Use date-range format CCYYMMDD-CCYYMMDD.",
                ))
            elif dtp02 == "DT" and not _DATE_DT_RE.match(dtp03):
                errors.append(ErrorSchema(
                    severity=Severity.ERROR, segment=seg_label, element="DTP03", loop=loop,
                    description=(
                        f"{prefix} ({seg_label}): '{dtp03}' does not match DT "
                        f"(CCYYMMDDHHMM — 12 digits)."
                    ),
                    source=RuleSource.COMPANION_GUIDE, rule_reference="CG-DTP-03",
                    suggested_correction="Use 12-digit datetime CCYYMMDDHHMM, e.g. 202401151430.",
                ))
            elif dtp02 == "TM" and not _TIME_TM_RE.match(dtp03):
                errors.append(ErrorSchema(
                    severity=Severity.ERROR, segment=seg_label, element="DTP03", loop=loop,
                    description=(
                        f"{prefix} ({seg_label}): '{dtp03}' does not match TM format "
                        f"(HHMM or HHMMSS — 4 or 6 digits)."
                    ),
                    source=RuleSource.COMPANION_GUIDE, rule_reference="CG-DTP-03",
                    suggested_correction="Use 4-digit time HHMM, e.g. 1430.",
                ))

    return errors


def validate_against_guide(
    transaction_type: str,
    segments: list[str],
    element_sep: str = "*",
) -> list[ErrorSchema]:
    """
    Validate parsed segments against Companion Guide mandatory rules.
    Returns list of ErrorSchema violations.

    Three validation passes:
      1. Mandatory segment presence (heuristic extraction from guide text)
      2. Per-qualifier NM1 content validation (guide-verified rule tables)
      3. Per-qualifier DTP date/format validation (guide-verified rule tables)

    NM1 validation is applied only to transaction types that use NM1 for entity
    names (837P, 837I, 278).  834 and 820 use N1 segments instead.
    DTP validation is applied to all transaction types with defined DTP rules.
    """
    errors: list[ErrorSchema] = []


    try:
        guide = load_guide(transaction_type)
    except (ValueError, FileNotFoundError) as exc:
        errors.append(ErrorSchema(
            severity=Severity.WARNING,
            segment="",
            description=f"Companion Guide not available: {exc}",
            source=RuleSource.COMPANION_GUIDE,
            rule_reference="CG-LOAD",
        ))
        return errors

    # --- Pass 1: Mandatory segment presence ---
    present_segments: set[str] = set()
    for seg in segments:
        seg_id = seg.split(element_sep)[0].strip()
        present_segments.add(seg_id)

    mandatory_rules = [
        r for r in guide.rules
        if r.mandatory and r.segment and r.condition != "conditional"
    ]
    for rule in mandatory_rules:
        if rule.segment not in present_segments:
            errors.append(ErrorSchema(
                severity=Severity.ERROR,
                segment=rule.segment,
                element=rule.element,
                loop=rule.loop,
                description=f"Mandatory segment '{rule.segment}' missing per Companion Guide.",
                source=RuleSource.COMPANION_GUIDE,
                rule_reference=rule.rule_id,
                suggested_correction=f"Add required segment '{rule.segment}'."
            ))

    # --- Pass 2: Per-qualifier NM1 validation (companion guide entity rules) ---
    # 834 and 820 use N1 (not NM1) for entity names — do NOT apply NM1 rules to them.
    if transaction_type in {"837P", "837I", "837D", "278"}:
        errors.extend(_validate_nm1_segments(segments, element_sep, transaction_type))

    # --- Pass 3: Per-qualifier DTP validation (companion guide date rules) ---
    if transaction_type in _DTP_RULES_BY_TX:
        errors.extend(_validate_dtp_segments(segments, element_sep, transaction_type))

    return errors


def search_guide(transaction_type: str, query: str) -> list[CompanionGuideRuleSchema]:
    """Search guide rules by keyword."""
    rules = get_guide_rules(transaction_type)
    query_lower = query.lower()
    return [r for r in rules if query_lower in r.rule_text.lower()
            or query_lower in r.segment.lower()
            or query_lower in r.element.lower()]


def list_available_guides() -> list[dict]:
    """List all configured Companion Guides and their availability."""
    result = []
    for tx_type, file_name in _GUIDE_MAP.items():
        path = COMPANION_GUIDE_DIR / file_name
        result.append({
            "transaction_type": tx_type,
            "file_name": file_name,
            "available": path.exists(),
            "cached": tx_type in _guide_cache,
            "rule_count": len(_guide_cache[tx_type].rules) if tx_type in _guide_cache else None,
        })
    return result
