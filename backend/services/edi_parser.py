"""
services/edi_parser.py
EDI Parser Service — converts raw X12 EDI into structured EDITransactionSchema.
Deterministic. No AI. No assumptions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from backend.models.schemas import (
    EDITransactionSchema,
    ElementSchema,
    FunctionalGroup,
    SegmentSchema,
    TransactionSet,
)


# ---------------------------------------------------------------------------
# Separator Detection
# ---------------------------------------------------------------------------

def _terminator_is_valid(raw_clean: str, element_sep: str, segment_term: str) -> bool:
    """
    A correctly detected terminator must split ISA from a GS segment that
    immediately follows it — GS always comes directly after ISA in valid X12,
    regardless of how ISA's fields are padded. This is a deterministic check,
    unlike testing whether the guessed character merely recurs somewhere
    (which can produce false positives when the guess happens to match a
    digit inside a date or control number).
    """
    if segment_term == "\n":
        _, sep, rest = raw_clean.partition("\n")
        return bool(sep) and rest.lstrip("\r\n ").startswith("GS" + element_sep)
    flat = re.sub(r"[\r\n]+", "", raw_clean)
    _, sep, rest = flat.partition(segment_term)
    return bool(sep) and rest.startswith("GS" + element_sep)


def _detect_separators(raw: str) -> tuple[str, str, str]:
    """
    Detect element separator, component separator and segment terminator from ISA.
    Returns (element_sep, component_sep, segment_term).

    ISA is conventionally a fixed-width segment totalling exactly 105 characters
    (positions 0-104), with the segment terminator at position 105. This only
    holds when ISA02/ISA04/ISA06/ISA08 are padded to their full conventional
    widths (10/10/15/15 chars). Real-world files (hand-built test files, or
    files from systems that don't strictly pad) frequently do not follow this,
    which makes position 105 land on an arbitrary character instead of the
    true terminator — and since that wrong character usually won't put GS
    right after ISA, splitting on it silently collapses the entire file into
    a single "segment" (or produces garbage fragments).

    To stay robust, the fixed-width guess is verified (GS must immediately
    follow ISA once split). If it doesn't hold up, we fall back to locating
    the terminator by anchoring on the GS segment directly, which works
    regardless of ISA padding.
    Supports tilde (~), newline (\\n / \\r\\n), and other single-char terminators.
    """
    raw_clean = raw.strip()
    if not raw_clean.startswith("ISA"):
        return "*", ":", "~"

    # ISA element separator is always at position 3
    element_sep = raw_clean[3]

    # ISA is fixed-width = exactly 105 chars (positions 0-104).
    # Position 104 = ISA16 (component separator), position 105 = segment terminator.
    component_sep = ":"
    segment_term = "~"
    if len(raw_clean) > 105:
        component_sep = raw_clean[104] if raw_clean[104] not in (element_sep, " ") else ":"
        candidate = raw_clean[105]
        if candidate in ("\n", "\r"):
            segment_term = "\n"
        elif candidate not in (" ", element_sep):
            segment_term = candidate
    else:
        # Very short content — fall back to splitting by element_sep
        parts = raw_clean.split(element_sep)
        component_sep = parts[16][0] if len(parts) > 16 and parts[16] else ":"
        segment_term = "~"

    if not _terminator_is_valid(raw_clean, element_sep, segment_term):
        m = re.search(r"GS" + re.escape(element_sep), raw_clean[16:])
        if m:
            gs_idx = 16 + m.start()
            term_char = raw_clean[gs_idx - 1] if gs_idx > 0 else segment_term
            segment_term = "\n" if term_char in ("\n", "\r") else term_char
            if component_sep in (element_sep, " ", "", segment_term):
                component_sep = ":"

    return element_sep, component_sep, segment_term


# ---------------------------------------------------------------------------
# Segment Parser
# ---------------------------------------------------------------------------

_SEGMENT_NAMES: dict[str, str] = {
    "ISA": "Interchange Control Header",
    "IEA": "Interchange Control Trailer",
    "GS": "Functional Group Header",
    "GE": "Functional Group Trailer",
    "ST": "Transaction Set Header",
    "SE": "Transaction Set Trailer",
    "BPR": "Financial Information",
    "TRN": "Reassociation Trace Number",
    "REF": "Reference Identification",
    "DTM": "Date/Time Reference",
    "N1": "Name",
    "N3": "Address Information",
    "N4": "Geographic Location",
    "NM1": "Individual or Organizational Name",
    "CLM": "Claim Information",
    "DTP": "Date or Time Period",
    "HI": "Health Care Diagnosis Code",
    "SV1": "Professional Service",
    "SV2": "Institutional Service",
    "SV3": "Dental Service",
    "LX": "Header Number",
    "PWK": "Paperwork",
    "CR1": "Ambulance Transport Information",
    "CRC": "Conditions Indicator",
    "AMT": "Monetary Amount",
    "QTY": "Quantity",
    "HL": "Hierarchical Level",
    "PRV": "Provider Information",
    "SBR": "Subscriber Information",
    "PAT": "Patient Information",
    "MOA": "Medicare Outpatient Adjudication",
    "PLB": "Provider Level Adjustment",
    "CLP": "Claim Payment Information",
    "CAS": "Claim Adjustment",
    "SVC": "Service Payment Information",
    "INS": "Insured Benefit",
    "HD": "Health Coverage",
    "IDC": "Identification Card",
    "UM": "Health Care Services Review Information",
    "HSD": "Health Care Services Delivery",
    "AK1": "Functional Acknowledgment Header",
    "AK2": "Transaction Set Response Header",
    "AK3": "Data Segment Note",
    "AK4": "Data Element Note",
    "AK5": "Transaction Set Response Trailer",
    "AK9": "Functional Acknowledgment Trailer",
    "IK3": "Implementation Data Segment Note",
    "IK4": "Implementation Data Element Note",
    "IK5": "Implementation Transaction Set Response Trailer",
    "999": "Implementation Acknowledgment",
    "277": "Health Care Claim Acknowledgment",
    "STC": "Health Care Claim Status",
    "QC": "Patient Information",
    "TL": "Transaction Totals",
}


def _parse_segment(raw_seg: str, element_sep: str, component_sep: str,
                    position: int) -> SegmentSchema:
    """Parse a single raw segment string into SegmentSchema."""
    parts = raw_seg.split(element_sep)
    seg_id = parts[0].strip()
    elements: list[ElementSchema] = []
    for i, part in enumerate(parts[1:], start=1):
        elements.append(ElementSchema(
            element_id=f"{seg_id}{i:02d}",
            description="",
            value=part.strip(),
            required=False,
        ))
    return SegmentSchema(
        segment_id=seg_id,
        name=_SEGMENT_NAMES.get(seg_id, ""),
        loop="",
        position=position,
        raw=raw_seg,
        elements=elements,
    )


# ---------------------------------------------------------------------------
# Loop Detector (lightweight heuristic for major loops)
# ---------------------------------------------------------------------------

_LOOP_MAP: dict[str, dict[str, str]] = {
    "837P": {
        "1000A": "NM1",  # Submitter
        "1000B": "NM1",  # Receiver
        "2000A": "HL",   # Billing Provider
        "2010AA": "NM1",
        "2000B": "HL",   # Subscriber
        "2010BA": "NM1",
        "2300": "CLM",   # Claim
        "2400": "LX",    # Service Line
    },
    "837I": {
        "2000A": "HL",
        "2300": "CLM",
        "2400": "LX",
    },
}


# ---------------------------------------------------------------------------
# Transaction Type Detection
# ---------------------------------------------------------------------------

def _detect_transaction_type(st_segment: str, element_sep: str) -> str:
    """Detect transaction type from ST01 element."""
    parts = st_segment.split(element_sep)
    if len(parts) < 2:
        return "UNKNOWN"
    st01 = parts[1].strip()
    type_map = {
        "837": "837",  # refined by GS08 or loop
        "278": "278",
        "834": "834",
        "820": "820",
        "999": "999",
        "277": "277CA",
        "271": "271",
        "270": "270",
        "835": "835",
    }
    return type_map.get(st01, st01)


def _refine_837_type(segments: list[str], element_sep: str) -> str:
    """
    Determine whether a 837 is Professional (P), Institutional (I), or Dental (D).
    837P uses SV1 (Professional Service).
    837I uses SV2 (Institutional Service).
    837D uses SV3 (Dental Service).
    Falls back to GS08 version identifier check.
    """
    seg_ids = {s.split(element_sep)[0].strip() for s in segments}
    if "SV3" in seg_ids:
        return "837D"
    if "SV2" in seg_ids:
        return "837I"
    if "SV1" in seg_ids:
        return "837P"
    # Fallback: check GS08 for version identifier
    for seg in segments:
        parts = seg.split(element_sep)
        if parts[0].strip() == "GS" and len(parts) > 8:
            gs08 = parts[8].strip()
            if "X223" in gs08 or "X224" in gs08:
                return "837I"
            if "X222" in gs08:
                return "837P"
            if "X224A2" in gs08 or "DNTL" in seg.upper() or "DENTAL" in seg.upper():
                return "837D"
    return "837P"


# ---------------------------------------------------------------------------
# Main Parser
# ---------------------------------------------------------------------------

def parse(raw_content: str, source_file: str = "") -> EDITransactionSchema:
    """
    Parse a raw X12 EDI string into EDITransactionSchema.
    Raises ValueError if content is not valid EDI.
    """
    if not raw_content or not raw_content.strip():
        raise ValueError("EDI content is empty.")

    raw = raw_content.strip()
    element_sep, component_sep, segment_term = _detect_separators(raw)

    # Split into segments based on the detected terminator.
    # Newline-terminated files must NOT have newlines stripped first.
    if segment_term == "\n":
        # Each line is one segment; strip carriage returns and blank lines
        raw_segments = [s.strip() for s in re.split(r"\r?\n", raw) if s.strip()]
    else:
        # Tilde (~) or other single-char terminator: flatten newlines then split
        flat = re.sub(r"[\r\n]+", "", raw)
        raw_segments = [s.strip() for s in flat.split(segment_term) if s.strip()]

    if not raw_segments or not raw_segments[0].startswith("ISA"):
        raise ValueError("EDI content does not begin with ISA segment.")

    if len(raw_segments) < 2 or not raw_segments[1].startswith("GS" + element_sep):
        # Detection (including the GS-anchored fallback) could not find a
        # terminator that actually separates segments — GS must always be
        # the segment right after ISA in valid X12, so if it isn't, the
        # content has no recognizable segment boundaries. Fail clearly here
        # instead of silently treating the whole file (or bogus fragments of
        # it) as "segments" and letting downstream engines crash on
        # truncated/garbled element access.
        raise ValueError(
            "EDI content does not contain a recognizable segment terminator "
            "(expected '~', newline, or another consistent delimiter between "
            "segments). The file may be corrupted or missing separators."
        )

    # Parse all segments
    parsed_segments: list[SegmentSchema] = [
        _parse_segment(s, element_sep, component_sep, i)
        for i, s in enumerate(raw_segments)
    ]

    # ISA fields
    isa_seg = parsed_segments[0]
    sender_id = isa_seg.elements[5].value if len(isa_seg.elements) > 5 else ""
    receiver_id = isa_seg.elements[7].value if len(isa_seg.elements) > 7 else ""
    icn = isa_seg.elements[12].value if len(isa_seg.elements) > 12 else ""
    interchange_date = isa_seg.elements[8].value if len(isa_seg.elements) > 8 else ""
    interchange_time = isa_seg.elements[9].value if len(isa_seg.elements) > 9 else ""

    iea_seg = next((s for s in parsed_segments if s.segment_id == "IEA"), None)

    # Build functional groups
    groups: list[FunctionalGroup] = []
    i = 0
    while i < len(parsed_segments):
        seg = parsed_segments[i]
        if seg.segment_id == "GS":
            group = FunctionalGroup(gs_segment=seg)
            group.group_control_number = seg.elements[5].value if len(seg.elements) > 5 else ""
            group.functional_identifier = seg.elements[0].value if seg.elements else ""
            i += 1
            while i < len(parsed_segments) and parsed_segments[i].segment_id != "GE":
                inner = parsed_segments[i]
                if inner.segment_id == "ST":
                    ts = TransactionSet(st_segment=inner)
                    ts.transaction_set_control_number = (
                        inner.elements[1].value if len(inner.elements) > 1 else ""
                    )
                    ts.transaction_type = _detect_transaction_type(inner.raw, element_sep)
                    i += 1
                    while i < len(parsed_segments) and parsed_segments[i].segment_id != "SE":
                        ts.segments.append(parsed_segments[i])
                        i += 1
                    if i < len(parsed_segments):
                        ts.se_segment = parsed_segments[i]
                        i += 1
                    group.transaction_sets.append(ts)
                else:
                    i += 1
            if i < len(parsed_segments):
                group.ge_segment = parsed_segments[i]
                i += 1
            groups.append(group)
        else:
            i += 1

    # Determine transaction type
    tx_type = "UNKNOWN"
    if groups and groups[0].transaction_sets:
        tx_type = groups[0].transaction_sets[0].transaction_type
    if tx_type == "837":
        all_segs = [s.raw for g in groups for ts in g.transaction_sets for s in ts.segments]
        tx_type = _refine_837_type(all_segs, element_sep)

    return EDITransactionSchema(
        transaction_type=tx_type,
        interchange_control_number=icn,
        sender_id=sender_id.strip(),
        receiver_id=receiver_id.strip(),
        interchange_date=interchange_date,
        interchange_time=interchange_time,
        isa_segment=isa_seg,
        iea_segment=iea_seg,
        groups=groups,
        raw_content=raw_content,
        source_file=source_file,
    )


def parse_file(file_path: str | Path) -> EDITransactionSchema:
    """Parse an EDI file from the file system."""
    p = Path(file_path)
    content = p.read_text(encoding="utf-8", errors="replace")
    return parse(content, source_file=str(p))
