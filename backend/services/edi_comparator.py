"""
services/edi_comparator.py
EDI Comparison Service.
Compares two EDI files at field/segment/element level with aligned side-by-side diff.
Processing Rule PR-03.
"""

from __future__ import annotations

import difflib
from typing import Optional

from backend.models.schemas import (
    ComparisonResultSchema,
    ComparisonSchema,
    DifferenceType,
    EDITransactionSchema,
    RecordComparisonSchema,
)
from backend.services import edi_parser

# ---------------------------------------------------------------------------
# Element name tables for common X12 segments
# ---------------------------------------------------------------------------

_ELEMENT_NAMES: dict[str, dict[int, str]] = {
    "ISA": {
        1: "Auth Info Qualifier", 2: "Authorization Information",
        3: "Security Info Qualifier", 4: "Security Information",
        5: "Sender ID Qualifier", 6: "Interchange Sender ID",
        7: "Receiver ID Qualifier", 8: "Interchange Receiver ID",
        9: "Interchange Date", 10: "Interchange Time",
        11: "Repetition Separator", 12: "Control Version Number",
        13: "Interchange Control Number", 14: "Acknowledgment Requested",
        15: "Usage Indicator", 16: "Component Element Separator",
    },
    "GS": {1: "Functional ID Code", 2: "Application Sender Code", 3: "Application Receiver Code",
           4: "Date", 5: "Time", 6: "Group Control Number", 7: "Responsible Agency Code",
           8: "Version/Release Identifier"},
    "ST": {1: "Transaction Set ID Code", 2: "Transaction Set Control Number"},
    "BHT": {1: "Hierarchical Structure Code", 2: "Transaction Set Purpose Code",
            3: "Reference ID", 4: "Date", 5: "Time", 6: "Transaction Type Code"},
    "HL": {1: "Hierarchical ID", 2: "Parent HL ID", 3: "Hierarchical Level Code", 4: "Child Code"},
    "NM1": {1: "Entity Identifier Code", 2: "Entity Type Qualifier",
            3: "Name Last / Org Name", 4: "Name First", 5: "Name Middle",
            8: "ID Code Qualifier", 9: "ID Code"},
    "CLM": {1: "Claim Submitter ID", 2: "Total Claim Charge Amount",
            5: "Health Care Service Location", 6: "Provider Signature Indicator",
            7: "Assignment Code", 8: "Benefits Assignment Indicator", 9: "Release of Info Code"},
    "REF": {1: "Reference ID Qualifier", 2: "Reference Identification", 3: "Description"},
    "DTP": {1: "Date/Time Qualifier", 2: "Date Time Period Format", 3: "Date Time Period"},
    "HI": {1: "Health Care Code 1", 2: "Health Care Code 2", 3: "Health Care Code 3"},
    "SV1": {1: "Procedure Code", 2: "Line Charge Amount", 3: "Unit of Measure", 4: "Unit Count",
            6: "Diagnosis Code Pointer"},
    "SV2": {1: "Revenue Code", 2: "Procedure Code", 3: "Line Charge Amount",
            4: "Unit of Measure", 5: "Unit Count"},
    "SV3": {1: "Procedure Code", 2: "Line Charge Amount", 3: "Oral Cavity Designation"},
    "DMG": {1: "Date Format Qualifier", 2: "Date of Birth", 3: "Gender Code"},
    "PRV": {1: "Provider Code", 2: "Reference ID Qualifier", 3: "Reference Identification"},
    "PER": {1: "Contact Function Code", 2: "Name", 3: "Communication Qualifier", 4: "Comm Number"},
    "AK1": {1: "Functional ID Code", 2: "Group Control Number"},
    "AK2": {1: "Transaction Set ID Code", 2: "Transaction Set Control Number"},
    "AK3": {1: "Segment ID", 2: "Segment Position", 3: "Loop ID", 4: "Segment Syntax Error Code"},
    "AK4": {1: "Element Position", 2: "Component Position", 3: "Element Reference Number",
            4: "Element Syntax Error Code", 5: "Copy of Bad Element"},
    "AK5": {1: "Transaction Set Ack Code", 2: "Transaction Set Syntax Error Code"},
    "AK9": {1: "Functional Group Ack Code", 2: "Number of TS Included", 3: "Number of TS Received",
            4: "Number of TS Accepted"},
    "STC": {1: "Health Care Claim Status", 2: "Date", 3: "Action Code", 4: "Monetary Amount"},
    "SE": {1: "Number of Included Segments", 2: "Transaction Set Control Number"},
    "GE": {1: "Number of Included TS", 2: "Group Control Number"},
    "IEA": {1: "Number of Functional Groups", 2: "Interchange Control Number"},
}

_RESOLUTION_MAP: dict[DifferenceType, str] = {
    DifferenceType.MISSING: (
        "Add the missing segment to File A per the transaction set specification. "
        "Verify it is required within this loop."
    ),
    DifferenceType.EXTRA: (
        "Verify whether this additional segment is expected per the companion guide. "
        "Remove from File A if it is not required."
    ),
    DifferenceType.VALUE_CHANGE: (
        "Review the element value against the trading partner specification and companion guide. "
        "Coordinate with your trading partner to align on the expected value."
    ),
    DifferenceType.MISMATCH: (
        "Verify segment count and position order match the transaction set specification. "
        "Ensure all required occurrences are present in the correct loop hierarchy."
    ),
}

_SEGMENT_HINTS: dict[str, str] = {
    "ISA": "Verify ISA05/06 sender ID and ISA07/08 receiver ID against your trading partner setup.",
    "GS": "Check GS01 functional ID code and GS02/03 sender/receiver application codes.",
    "CLM": "Validate claim ID (CLM01), total charge (CLM02), and place-of-service code (CLM05).",
    "NM1": "Check entity ID code (NM101) and name/ID fields against enrollment data.",
    "REF": "Validate reference qualifier (REF01) and number (REF02) against payer requirements.",
    "DTP": "Confirm date format (D8=CCYYMMDD) and value are correct and within allowable ranges.",
    "HI": "Review diagnosis code format (ICD-10-CM, qualifier ABK or BK) and code validity.",
    "SV1": "Verify CPT/HCPCS procedure code, charge amount, and units of service.",
    "SV2": "Verify revenue code, procedure code if applicable, and line charge amount.",
    "SV3": "Verify CDT dental procedure code, oral cavity designation, and charge amount.",
    "HL": "Ensure HL loop hierarchy (billing/subscriber/patient) is consistent between both files.",
    "AK5": "Review AK5 acknowledgment code; resolve reported syntax errors before resubmission.",
    "STC": "Review STC status category and claim status codes per the CAQH CORE STC code set.",
}


def _element_name(segment_id: str, position: int) -> str:
    return _ELEMENT_NAMES.get(segment_id, {}).get(position, f"{segment_id}{position:02d}")


def _build_resolution(segment_id: str, diff_type: DifferenceType) -> str:
    base = _RESOLUTION_MAP.get(diff_type, "Review with your trading partner.")
    hint = _SEGMENT_HINTS.get(segment_id, "")
    return f"{base} {hint}".strip() if hint else base


def _get_all_raw_segments(tx: EDITransactionSchema) -> list[str]:
    """Return all raw segment strings in document order."""
    segs: list[str] = []
    for group in tx.groups:
        if group.gs_segment and group.gs_segment.raw:
            segs.append(group.gs_segment.raw)
        for ts in group.transaction_sets:
            if ts.st_segment and ts.st_segment.raw:
                segs.append(ts.st_segment.raw)
            for seg in ts.segments:
                if seg.raw:
                    segs.append(seg.raw)
    return segs


# ---------------------------------------------------------------------------
# Business-record (claim / authorization) extraction
# ---------------------------------------------------------------------------


def _hl_block_boundaries(
    hl_idx: int,
    raw_segs: list[str],
    hl_positions: list[int],
) -> tuple[int, int]:
    """
    Return (start_idx, end_idx) for the HL block rooted at hl_idx.

    end_idx is the index of the first HL segment whose HL01 ID is NOT a
    descendant of the owning HL.  Descendants are found via BFS over the
    HL parent-child map so that inner patient/dependent loops are correctly
    included within the owning subscriber block.
    """
    parts = raw_segs[hl_idx].split("*")
    owning_id = parts[1].strip() if len(parts) > 1 else ""

    # BFS: collect all descendant HL01 IDs
    descendant_ids: set[str] = {owning_id} if owning_id else set()
    changed = True
    while changed:
        changed = False
        for hi in hl_positions:
            p = raw_segs[hi].split("*")
            hi_id     = p[1].strip() if len(p) > 1 else ""
            hi_parent = p[2].strip() if len(p) > 2 else ""
            if hi_parent in descendant_ids and hi_id not in descendant_ids:
                descendant_ids.add(hi_id)
                changed = True

    end_idx = len(raw_segs)
    for hi in hl_positions:
        if hi <= hl_idx:
            continue
        p = raw_segs[hi].split("*")
        hi_id = p[1].strip() if len(p) > 1 else ""
        if hi_id not in descendant_ids:
            end_idx = hi
            break

    return hl_idx, end_idx

def _find_subscriber_hl(
    owning_hl_idx: int,
    raw_segs: list[str],
    hl_positions: list[int],
) -> int:
    """
    Walk up the HL parent chain from owning_hl_idx and return the index of the
    first HL whose HL03 (level code) equals "22" (subscriber/patient level per
    X12 837 specification).  If no subscriber-level HL is found, return
    owning_hl_idx unchanged (safe fallback).
    """
    # Build HL01-ID → segment index map for upward traversal
    hl_id_to_idx: dict[str, int] = {}
    for hi in hl_positions:
        p = raw_segs[hi].split("*")
        hl_id = p[1].strip() if len(p) > 1 else ""
        if hl_id:
            hl_id_to_idx[hl_id] = hi

    visited: set[int] = set()
    current = owning_hl_idx
    while current not in visited:
        visited.add(current)
        p = raw_segs[current].split("*")
        level = p[3].strip() if len(p) > 3 else ""
        if level == "22":
            return current                  # found subscriber HL
        parent_id = p[2].strip() if len(p) > 2 else ""
        if not parent_id or parent_id not in hl_id_to_idx:
            break                           # reached the root without finding 22
        current = hl_id_to_idx[parent_id]

    # No HL-03="22" found — return original owning HL
    return owning_hl_idx


def _extract_claim_blocks(tx: EDITransactionSchema) -> dict[str, list[str]]:
    """
    For 837P/837I: extract a complete, self-contained context block for each
    CLM, keyed by CLM01 (patient control / claim reference number).

    Transaction boundary rules (per X12 837P 005010X222A1 companion guide):
    ┌─────────────────────────────────────────────────────────────────────┐
    │ Loop 2000A  HL**20   Billing Provider (shared across all claims)     │
    │ Loop 2000B  HL*x*22  Subscriber — primary context for each claim     │
    │   Loop 2300  CLM     Claim Information                               │
    │     Loop 2400  LX    Service Line                                    │
    │ Loop 2000C  HL*x*23  Patient (when different from subscriber)        │
    │   Loop 2300  CLM     Claim under patient                             │
    └─────────────────────────────────────────────────────────────────────┘

    Block construction:
    • Subscriber-level CLM  → block = subscriber HL (2000B) through its full
      descendant scope (includes SBR, NM1*IL, NM1*PR, CLM, HI, LX, SV1...).
    • Patient-level CLM     → block = subscriber HL header (2000B segments up
      to the first child HL) + patient HL scope (2000C through LX/SV1...).
      This ensures subscriber demographics are included for all claim types.
    • No-HL transaction     → entire transaction-set segment list is one claim.
    """
    claims: dict[str, list[str]] = {}
    for group in tx.groups:
        for ts in group.transaction_sets:
            all_segs = ts.segments
            raw_segs = [s.raw for s in all_segs]

            hl_positions = [i for i, s in enumerate(all_segs) if s.segment_id == "HL"]
            clm_positions = [i for i, s in enumerate(all_segs) if s.segment_id == "CLM"]

            for j, ci in enumerate(clm_positions):
                raw = all_segs[ci].raw
                parts = raw.split("*")
                claim_num = parts[1].strip() if len(parts) > 1 else f"CLM_{j}"
                if not claim_num:
                    claim_num = f"CLM_{j}"

                if not hl_positions:
                    # No HL hierarchy — treat entire transaction set as one claim
                    claims[claim_num] = raw_segs
                    continue

                # Find the HL segment immediately before this CLM
                owning_hl_idx: int | None = None
                for hi in reversed(hl_positions):
                    if hi < ci:
                        owning_hl_idx = hi
                        break

                if owning_hl_idx is None:
                    # CLM before any HL: use segments from start to next CLM
                    end = clm_positions[j + 1] if j + 1 < len(clm_positions) else len(all_segs)
                    claims[claim_num] = raw_segs[:end]
                    continue

                # Walk up to find the subscriber-level (22) HL ancestor
                subscriber_hl_idx = _find_subscriber_hl(owning_hl_idx, raw_segs, hl_positions)

                owning_parts = raw_segs[owning_hl_idx].split("*")
                owning_level = owning_parts[3].strip() if len(owning_parts) > 3 else ""

                if owning_level == "22" or subscriber_hl_idx == owning_hl_idx:
                    # CLM is directly under subscriber HL — return full subscriber block
                    _, end_idx = _hl_block_boundaries(subscriber_hl_idx, raw_segs, hl_positions)
                    claims[claim_num] = raw_segs[subscriber_hl_idx:end_idx]
                else:
                    # CLM is under a patient (or other child) HL:
                    # Combine subscriber header + patient block so that subscriber
                    # demographics (SBR, NM1*IL, etc.) are included in the comparison.
                    sub_header_end = owning_hl_idx  # patient HL starts here
                    subscriber_header = raw_segs[subscriber_hl_idx:sub_header_end]

                    _, patient_end = _hl_block_boundaries(owning_hl_idx, raw_segs, hl_positions)
                    patient_block = raw_segs[owning_hl_idx:patient_end]

                    claims[claim_num] = subscriber_header + patient_block

    return claims


def _extract_auth_blocks(tx: EDITransactionSchema) -> dict[str, list[str]]:
    """
    For 278: extract one complete authorization block per subscriber/member.

    Transaction boundary rules (per X12 278N 005010X217 companion guide):
    ┌─────────────────────────────────────────────────────────────────────┐
    │ Loop 2000A  HL**20   Requester/Facility                              │
    │ Loop 2000B  HL*x*21  Subscriber Insurer/Plan                        │
    │ Loop 2000C  HL*x*22  Subscriber/Member — primary auth context       │
    │   NM1*IL   Member demographics                                      │
    │ Loop 2000D  HL*x*23  Dependent (if patient ≠ member)               │
    │ Loop 2000E  HL*x*EV  Service Level (contains UM, DTP, HI)          │
    └─────────────────────────────────────────────────────────────────────┘

    Keying strategy (priority order):
      1. TRN02   — service-level trace/reference number (when present)
      2. NM1*IL NM109 — member ID from subscriber loop
      3. BHT03   — transaction reference ID from BHT segment
      4. HL01    — fallback to subscriber HL number

    One block is produced per subscriber-level HL (HL03="22").
    This prevents the overlapping multi-HL blocks that occur when iterating
    every HL (provider, plan, subscriber, service) independently.

    For 278 files without HL loops: fall back to TRN-based slicing or return
    the entire transaction set as one record.
    """
    auths: dict[str, list[str]] = {}
    for group in tx.groups:
        for ts in group.transaction_sets:
            all_segs = ts.segments
            raw_segs = [s.raw for s in all_segs]

            hl_positions = [i for i, s in enumerate(all_segs) if s.segment_id == "HL"]

            # ── No HL structure ─────────────────────────────────────────────
            if not hl_positions:
                trn_idx = [i for i, s in enumerate(all_segs) if s.segment_id == "TRN"]
                if trn_idx:
                    for j, ti in enumerate(trn_idx):
                        parts = all_segs[ti].raw.split("*")
                        ref = parts[2].strip() if len(parts) > 2 else f"TRN_{j}"
                        end = trn_idx[j + 1] if j + 1 < len(trn_idx) else len(all_segs)
                        auths[ref or f"TRN_{j}"] = [s.raw for s in all_segs[ti:end]]
                else:
                    # Key by BHT03 if present, else "TX_SET"
                    key = "TX_SET"
                    for s in all_segs:
                        if s.segment_id == "BHT":
                            p = s.raw.split("*")
                            bht03 = p[3].strip() if len(p) > 3 else ""
                            if bht03:
                                key = bht03
                                break
                    auths[key] = raw_segs
                continue

            # ── HL-structured 278: iterate SUBSCRIBER-LEVEL HLs (HL03="22") ─
            # Build BHT03 for fallback key (transaction-level reference ID)
            bht03_key = ""
            for s in all_segs:
                if s.segment_id == "BHT":
                    p = s.raw.split("*")
                    bht03_key = p[3].strip() if len(p) > 3 else ""
                    break

            subscriber_hls = [
                hi for hi in hl_positions
                if (raw_segs[hi].split("*")[3].strip() if len(raw_segs[hi].split("*")) > 3 else "") == "22"
            ]

            # If no HL03="22" found, use all HLs that contain UM (service request)
            if not subscriber_hls:
                for hi in hl_positions:
                    _, end_idx = _hl_block_boundaries(hi, raw_segs, hl_positions)
                    block_segs = all_segs[hi:end_idx]
                    if any(s.segment_id in ("UM", "TRN") for s in block_segs):
                        subscriber_hls.append(hi)

            if not subscriber_hls:
                # Last resort: treat entire TS as one auth
                auths[bht03_key or "TX_SET"] = raw_segs
                continue

            for hi in subscriber_hls:
                p = raw_segs[hi].split("*")
                hl_id = p[1].strip() if len(p) > 1 else f"HL_{hi}"

                _, end_idx = _hl_block_boundaries(hi, raw_segs, hl_positions)
                block_raw = raw_segs[hi:end_idx]
                block_segs = all_segs[hi:end_idx]

                # ── Key priority ────────────────────────────────────────────
                key = hl_id  # fallback

                # 1. TRN02 (service-level trace number)
                for s in block_segs:
                    if s.segment_id == "TRN":
                        tp = s.raw.split("*")
                        ref = tp[2].strip() if len(tp) > 2 else ""
                        if ref:
                            key = ref
                            break
                else:
                    # 2. NM1*IL member ID (NM109, the identification code)
                    for s in block_segs:
                        if s.segment_id == "NM1":
                            np_ = s.raw.split("*")
                            if len(np_) > 1 and np_[1].strip() in ("IL", "QC"):
                                mid = np_[9].strip() if len(np_) > 9 else ""
                                if mid:
                                    key = mid
                                    break
                    else:
                        # 3. BHT03 (transaction reference ID)
                        if bht03_key:
                            key = bht03_key

                auths[key] = block_raw

            if not auths:
                auths[bht03_key or "TX_SET"] = raw_segs

    return auths


def _normalize_lx_blocks(raw_segs: list[str]) -> list[str]:
    """
    Reorder service-line (LX loop) sub-blocks within a claim block by LX01
    (the assigned line number), using integer sort.

    Why this is necessary:
    Trading partners occasionally transmit the same claim with service lines
    in a different order (e.g. File A: LX*1, LX*2, LX*3 vs File B: LX*3,
    LX*1, LX*2).  Without normalisation the comparison engine reports false
    differences for every element of every mis-ordered line.

    Algorithm:
    1. All segments before the first LX are the "claim header" — kept as-is.
    2. From the first LX onward, segments are grouped into LX sub-blocks.
    3. Sub-blocks are sorted by LX01 as integer (fallback: string).
    4. Sorted sub-blocks are appended after the claim header.

    For blocks without any LX segment the input is returned unchanged.
    """
    first_lx: int | None = None
    for i, raw in enumerate(raw_segs):
        sid = raw.split("*")[0].strip() if "*" in raw else raw[:3].strip()
        if sid == "LX":
            first_lx = i
            break

    if first_lx is None:
        return raw_segs  # no service lines — nothing to reorder

    header = raw_segs[:first_lx]

    # Group segments into LX sub-blocks keyed by LX01 (line number)
    lx_blocks: dict[int, list[str]] = {}
    order: list[int] = []          # preserve insertion order for dup handling
    current_key: int | None = None

    for raw in raw_segs[first_lx:]:
        sid = raw.split("*")[0].strip() if "*" in raw else raw[:3].strip()
        if sid == "LX":
            parts = raw.split("*")
            try:
                lx_num = int(parts[1].strip()) if len(parts) > 1 else 0
            except ValueError:
                lx_num = 0
            current_key = lx_num
            if lx_num not in lx_blocks:
                lx_blocks[lx_num] = []
                order.append(lx_num)
            lx_blocks[lx_num].append(raw)
        elif current_key is not None:
            lx_blocks[current_key].append(raw)

    # Sort by LX01 integer value
    sorted_lines: list[str] = []
    for key in sorted(lx_blocks.keys()):
        sorted_lines.extend(lx_blocks[key])

    return header + sorted_lines


def _compute_aligned_diff(
    raw_a: list[str],
    raw_b: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Produce aligned side-by-side diff using SequenceMatcher on segment IDs.
    Returns (lines_a, lines_b, statuses) — all same length.
    statuses: 'same' | 'modified' | 'removed' | 'added'
    Empty string in lines_a/lines_b means a gap (no segment on that side).
    """
    ids_a = [r.split("*")[0] if "*" in r else r[:3] for r in raw_a]
    ids_b = [r.split("*")[0] if "*" in r else r[:3] for r in raw_b]

    sm = difflib.SequenceMatcher(None, ids_a, ids_b, autojunk=False)

    lines_a: list[str] = []
    lines_b: list[str] = []
    statuses: list[str] = []

    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            for i, j in zip(range(a0, a1), range(b0, b1)):
                lines_a.append(raw_a[i])
                lines_b.append(raw_b[j])
                statuses.append("same" if raw_a[i] == raw_b[j] else "modified")

        elif op == "replace":
            paired = min(a1 - a0, b1 - b0)
            for k in range(paired):
                ra, rb = raw_a[a0 + k], raw_b[b0 + k]
                lines_a.append(ra)
                lines_b.append(rb)
                statuses.append("modified" if ra != rb else "same")
            for k in range(paired, a1 - a0):
                lines_a.append(raw_a[a0 + k])
                lines_b.append("")
                statuses.append("removed")
            for k in range(paired, b1 - b0):
                lines_a.append("")
                lines_b.append(raw_b[b0 + k])
                statuses.append("added")

        elif op == "delete":
            for i in range(a0, a1):
                lines_a.append(raw_a[i])
                lines_b.append("")
                statuses.append("removed")

        elif op == "insert":
            for j in range(b0, b1):
                lines_a.append("")
                lines_b.append(raw_b[j])
                statuses.append("added")

    return lines_a, lines_b, statuses


def compare_raw(
    content_a: str,
    content_b: str,
    file_a_name: str = "File A",
    file_b_name: str = "File B",
) -> ComparisonResultSchema:
    """
    Compare two raw EDI strings.
    Returns ComparisonResultSchema with field-level differences.
    """
    tx_a = edi_parser.parse(content_a, source_file=file_a_name)
    tx_b = edi_parser.parse(content_b, source_file=file_b_name)
    return _compare_transactions(tx_a, tx_b, file_a_name, file_b_name)


def compare_files(
    file_path_a: str,
    file_path_b: str,
) -> ComparisonResultSchema:
    """Compare two EDI files from disk."""
    from pathlib import Path
    content_a = Path(file_path_a).read_text(encoding="utf-8", errors="replace")
    content_b = Path(file_path_b).read_text(encoding="utf-8", errors="replace")
    return compare_raw(content_a, content_b, file_path_a, file_path_b)


def _compare_transactions(
    tx_a: EDITransactionSchema,
    tx_b: EDITransactionSchema,
    name_a: str,
    name_b: str,
) -> ComparisonResultSchema:
    differences: list[ComparisonSchema] = []

    # --- ISA / envelope header comparison -----------------------------------
    header_fields = [
        ("Transaction Type",           "Transaction Type",           tx_a.transaction_type,           tx_b.transaction_type),
        ("Sender ID",                  "Interchange Sender ID",      tx_a.sender_id,                  tx_b.sender_id),
        ("Receiver ID",                "Interchange Receiver ID",    tx_a.receiver_id,                tx_b.receiver_id),
        ("Interchange Control Number", "Interchange Control Number", tx_a.interchange_control_number, tx_b.interchange_control_number),
        ("Interchange Date",           "Interchange Date",           tx_a.interchange_date,           tx_b.interchange_date),
        ("Interchange Time",           "Interchange Time",           tx_a.interchange_time,           tx_b.interchange_time),
    ]
    for field, elem_name, val_a, val_b in header_fields:
        if val_a != val_b:
            differences.append(ComparisonSchema(
                field=field,
                segment="ISA",
                element_name=elem_name,
                file_a_value=str(val_a),
                file_b_value=str(val_b),
                difference_type=DifferenceType.VALUE_CHANGE,
                description=f"ISA header field '{field}' differs: '{val_a}' vs '{val_b}'.",
                suggested_resolution=_build_resolution("ISA", DifferenceType.VALUE_CHANGE),
            ))

    # --- Segment-level / element-level comparison ---------------------------
    segs_a = _collect_segments(tx_a)
    segs_b = _collect_segments(tx_b)
    _compare_segment_maps(segs_a, segs_b, differences)

    # --- Aligned side-by-side diff ------------------------------------------
    raw_a = _get_all_raw_segments(tx_a)
    raw_b = _get_all_raw_segments(tx_b)
    lines_a, lines_b, statuses = _compute_aligned_diff(raw_a, raw_b)

    # --- Summary statistics -------------------------------------------------
    total_segs = max(len(raw_a), len(raw_b))
    missing  = sum(1 for d in differences if d.difference_type == DifferenceType.MISSING)
    extra    = sum(1 for d in differences if d.difference_type == DifferenceType.EXTRA)
    modified = sum(1 for d in differences if d.difference_type in (
        DifferenceType.VALUE_CHANGE, DifferenceType.MISMATCH))

    # --- Business-record (claim / authorization) matching -------------------
    tx_type = (tx_a.transaction_type or tx_b.transaction_type or "").upper()
    record_level_used = False
    record_label = "Record"
    blocks_a: dict[str, list[str]] = {}
    blocks_b: dict[str, list[str]] = {}
    matching_key_used = ""

    if tx_type.startswith("837"):
        blocks_a = _extract_claim_blocks(tx_a)
        blocks_b = _extract_claim_blocks(tx_b)
        record_label = "Claim"
        record_level_used = bool(blocks_a or blocks_b)
        matching_key_used = "CLM01 (Claim Submitter ID)"
    elif tx_type.startswith("278"):
        blocks_a = _extract_auth_blocks(tx_a)
        blocks_b = _extract_auth_blocks(tx_b)
        record_label = "Authorization"
        record_level_used = bool(blocks_a or blocks_b)
        matching_key_used = "TRN02 / Authorization Reference Number"

    set_a = set(blocks_a.keys())
    set_b = set(blocks_b.keys())
    matched_keys = sorted(set_a & set_b)
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)

    # --- Per-record (claim / auth) detailed comparison ----------------------
    record_comparisons: dict[str, RecordComparisonSchema] = {}
    records_with_diffs = 0
    records_without_diffs = 0
    total_rec_diffs = 0

    for key in matched_keys:
        # Normalise service-line order by LX01 before comparison so that
        # re-ordered claim lines (e.g. LX*3, LX*1 vs LX*1, LX*3) are matched
        # by their logical sequence number rather than file position.
        block_a = _normalize_lx_blocks(blocks_a[key])
        block_b = _normalize_lx_blocks(blocks_b[key])
        la, lb, st = _compute_aligned_diff(block_a, block_b)

        # Build segment maps for element-level comparison within the record
        map_a_block: dict[str, list[str]] = {}
        map_b_block: dict[str, list[str]] = {}
        for raw in block_a:
            sid = raw.split("*")[0] if "*" in raw else raw[:3]
            map_a_block.setdefault(sid, []).append(raw)
        for raw in block_b:
            sid = raw.split("*")[0] if "*" in raw else raw[:3]
            map_b_block.setdefault(sid, []).append(raw)

        rec_diffs: list[ComparisonSchema] = []
        _compare_segment_maps(map_a_block, map_b_block, rec_diffs)

        mod_segs = sorted({d.segment for d in rec_diffs if d.segment})
        mod_elems = sorted({
            d.field for d in rec_diffs
            if d.difference_type == DifferenceType.VALUE_CHANGE
        })

        record_comparisons[key] = RecordComparisonSchema(
            record_id=key,
            lines_a=la,
            lines_b=lb,
            statuses=st,
            differences=rec_diffs,
            modified_segments=mod_segs,
            modified_elements=mod_elems,
            total_differences=len(rec_diffs),
        )

        if rec_diffs:
            records_with_diffs += 1
        else:
            records_without_diffs += 1
        total_rec_diffs += len(rec_diffs)

    return ComparisonResultSchema(
        file_a=name_a,
        file_b=name_b,
        total_differences=len(differences),
        differences=differences,
        lines_a=lines_a,
        lines_b=lines_b,
        statuses=statuses,
        total_segments_compared=total_segs,
        missing_segments_count=missing,
        extra_segments_count=extra,
        modified_values_count=modified,
        record_level_used=record_level_used,
        record_label=record_label,
        record_a_count=len(blocks_a),
        record_b_count=len(blocks_b),
        matched_records_count=len(matched_keys),
        only_in_a=only_a,
        only_in_b=only_b,
        matched_record_ids=matched_keys,
        record_comparisons=record_comparisons,
        records_with_differences=records_with_diffs,
        records_without_differences=records_without_diffs,
        total_record_differences=total_rec_diffs,
        matching_key_used=matching_key_used,
        transaction_type=tx_type,
    )


def _collect_segments(tx: EDITransactionSchema) -> dict[str, list[str]]:
    """Collect segments grouped by segment_id for map-based comparison."""
    result: dict[str, list[str]] = {}
    for group in tx.groups:
        for ts in group.transaction_sets:
            for seg in ts.segments:
                result.setdefault(seg.segment_id, []).append(seg.raw)
    return result


def _compare_segment_maps(
    segs_a: dict[str, list[str]],
    segs_b: dict[str, list[str]],
    differences: list[ComparisonSchema],
) -> None:
    """Append segment-level and element-level differences."""
    for key in sorted(set(segs_a.keys()) | set(segs_b.keys())):
        list_a = segs_a.get(key, [])
        list_b = segs_b.get(key, [])

        if not list_a:
            differences.append(ComparisonSchema(
                field=key, segment=key, element_name="Segment",
                file_a_value="", file_b_value="; ".join(list_b[:3]),
                difference_type=DifferenceType.MISSING,
                description=f"Segment '{key}' missing in File A but present in File B ({len(list_b)} occurrence(s)).",
                suggested_resolution=_build_resolution(key, DifferenceType.MISSING),
            ))
            continue

        if not list_b:
            differences.append(ComparisonSchema(
                field=key, segment=key, element_name="Segment",
                file_a_value="; ".join(list_a[:3]), file_b_value="",
                difference_type=DifferenceType.EXTRA,
                description=f"Segment '{key}' present in File A ({len(list_a)} occurrence(s)) but missing from File B.",
                suggested_resolution=_build_resolution(key, DifferenceType.EXTRA),
            ))
            continue

        # Element-by-element comparison for paired occurrences
        for idx, (raw_a, raw_b) in enumerate(zip(list_a, list_b)):
            elems_a = raw_a.split("*")
            elems_b = raw_b.split("*")
            for e_idx in range(1, max(len(elems_a), len(elems_b))):
                val_a = elems_a[e_idx].strip() if e_idx < len(elems_a) else ""
                val_b = elems_b[e_idx].strip() if e_idx < len(elems_b) else ""
                if val_a != val_b:
                    elem = _element_name(key, e_idx)
                    differences.append(ComparisonSchema(
                        field=f"{key}{e_idx:02d}", segment=key, element_name=elem,
                        file_a_value=val_a, file_b_value=val_b,
                        difference_type=DifferenceType.VALUE_CHANGE,
                        description=(
                            f"{elem} ({key}{e_idx:02d}, occurrence {idx + 1}) differs: "
                            f"'{val_a}' vs '{val_b}'."
                        ),
                        suggested_resolution=_build_resolution(key, DifferenceType.VALUE_CHANGE),
                    ))

        # Count mismatch
        if len(list_a) != len(list_b):
            differences.append(ComparisonSchema(
                field=f"{key}_COUNT", segment=key, element_name="Segment Count",
                file_a_value=str(len(list_a)), file_b_value=str(len(list_b)),
                difference_type=DifferenceType.MISMATCH,
                description=f"Segment '{key}' occurs {len(list_a)} time(s) in File A but {len(list_b)} time(s) in File B.",
                suggested_resolution=_build_resolution(key, DifferenceType.MISMATCH),
            ))


# ---------------------------------------------------------------------------
# Excel Comparison Report
# ---------------------------------------------------------------------------

def generate_comparison_excel(result: ComparisonResultSchema) -> bytes:
    """
    Generate a detailed Excel comparison report from a ComparisonResultSchema.
    Returns raw bytes of the .xlsx file.
    """
    from io import BytesIO
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()

    # ── Helpers ──────────────────────────────────────────────────────────
    def _hdr_font() -> Font:
        return Font(bold=True, color="FFFFFF", size=10)

    def _hdr_fill(hex_color: str = "1F4E79") -> PatternFill:
        return PatternFill("solid", fgColor=hex_color)

    def _thin_border() -> Border:
        side = Side(style="thin", color="D0D0D0")
        return Border(left=side, right=side, top=side, bottom=side)

    def _apply_headers(ws, headers: list[str], col_widths: list[int], fill_color: str = "1F4E79") -> None:
        for ci, (h, w) in enumerate(zip(headers, col_widths), start=1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = _hdr_font()
            cell.fill = _hdr_fill(fill_color)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = _thin_border()
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.row_dimensions[1].height = 28
        ws.freeze_panes = "A2"

    def _write_row(ws, row_idx: int, values: list, fill_hex: str | None = None) -> None:
        for ci, v in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=ci, value=v)
            cell.border = _thin_border()
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if fill_hex:
                cell.fill = PatternFill("solid", fgColor=fill_hex)

    ts_str = result.executed_at.strftime("%Y-%m-%d %H:%M:%S UTC") if result.executed_at else ""

    # ── Sheet 1: Dashboard ────────────────────────────────────────────────
    ws_dash = wb.active
    ws_dash.title = "Dashboard"
    ws_dash.column_dimensions["A"].width = 35
    ws_dash.column_dimensions["B"].width = 20

    dash_title = ws_dash.cell(row=1, column=1, value="EDI Comparison Report — Dashboard")
    dash_title.font = Font(bold=True, size=13, color="1F4E79")
    ws_dash.merge_cells("A1:B1")
    ws_dash.row_dimensions[1].height = 30

    dash_rows = [
        ("Report Generated", ts_str),
        ("Source File A", result.file_a),
        ("Source File B", result.file_b),
        ("Transaction Type", result.transaction_type or "—"),
        ("Matching Key Used", result.matching_key_used or "—"),
        ("", ""),
        ("--- Record / Business Level ---", ""),
        ("Total Records in File A", result.record_a_count),
        ("Total Records in File B", result.record_b_count),
        ("Matched Records", result.matched_records_count),
        ("Missing Records in File A (in B not A)", len(result.only_in_b)),
        ("Missing Records in File B (in A not B)", len(result.only_in_a)),
        ("Records With Differences", result.records_with_differences),
        ("Records Without Differences", result.records_without_differences),
        ("Total Record-Level Differences", result.total_record_differences),
        ("", ""),
        ("--- Segment / Element Level ---", ""),
        ("Total Segments Compared", result.total_segments_compared),
        ("Total Differences Found", result.total_differences),
        ("Missing Segments", result.missing_segments_count),
        ("Extra Segments", result.extra_segments_count),
        ("Modified Values", result.modified_values_count),
    ]
    for ri, (label, value) in enumerate(dash_rows, start=2):
        lbl_cell = ws_dash.cell(row=ri, column=1, value=label)
        val_cell = ws_dash.cell(row=ri, column=2, value=value)
        if label.startswith("---"):
            lbl_cell.font = Font(bold=True, color="1F4E79")
        if isinstance(value, int) and value > 0 and "Differences" in label:
            val_cell.font = Font(bold=True, color="C62828")
        lbl_cell.border = _thin_border()
        val_cell.border = _thin_border()

    # ── Sheet 2: All Differences ──────────────────────────────────────────
    ws_diffs = wb.create_sheet("All Differences")
    diff_headers = [
        "Reference ID", "Transaction Type", "Segment", "Element",
        "File A Value", "File B Value", "Difference Description",
        "Difference Type", "Source File A", "Source File B", "Timestamp",
    ]
    diff_widths = [18, 16, 12, 18, 22, 22, 45, 16, 30, 30, 22]
    _apply_headers(ws_diffs, diff_headers, diff_widths)

    diff_fill_map = {
        "MISSING": "FFEBEE", "EXTRA": "E8F5E9",
        "VALUE_CHANGE": "E3F0FA", "MISMATCH": "FFF8E1",
    }

    # Gather all differences: first from record comparisons (with record_id), then global
    all_diff_rows: list[tuple] = []

    if result.record_comparisons:
        for rec_id, rec in result.record_comparisons.items():
            for d in rec.differences:
                all_diff_rows.append((
                    rec_id, result.transaction_type or "—",
                    d.segment, d.field, d.file_a_value, d.file_b_value,
                    d.description, d.difference_type.value if hasattr(d.difference_type, "value") else str(d.difference_type),
                    result.file_a, result.file_b, ts_str,
                ))
    else:
        for d in result.differences:
            all_diff_rows.append((
                "N/A", result.transaction_type or "—",
                d.segment, d.field, d.file_a_value, d.file_b_value,
                d.description, d.difference_type.value if hasattr(d.difference_type, "value") else str(d.difference_type),
                result.file_a, result.file_b, ts_str,
            ))

    for ri, row_vals in enumerate(all_diff_rows, start=2):
        diff_type = row_vals[7]
        fill = diff_fill_map.get(diff_type, "FFFFFF")
        _write_row(ws_diffs, ri, list(row_vals), fill_hex=fill)

    ws_diffs.auto_filter.ref = f"A1:{get_column_letter(len(diff_headers))}1"

    # ── Sheet 3: Matched Records Summary ─────────────────────────────────
    ws_matched = wb.create_sheet("Matched Records")
    matched_headers = [result.record_label + " / Auth ID", "Differences Found", "Modified Segments", "Modified Elements", "Status"]
    matched_widths = [22, 18, 40, 45, 15]
    _apply_headers(ws_matched, matched_headers, matched_widths, fill_color="2366A8")

    for ri, rec_id in enumerate(result.matched_record_ids, start=2):
        rec = result.record_comparisons.get(rec_id)
        if rec:
            diffs = rec.total_differences
            segs = ", ".join(rec.modified_segments) or "—"
            elems = ", ".join(rec.modified_elements) or "—"
            status = "With Differences" if diffs > 0 else "Identical"
            fill = "FFF8E1" if diffs > 0 else "E8F5E9"
            _write_row(ws_matched, ri, [rec_id, diffs, segs, elems, status], fill_hex=fill)
        else:
            _write_row(ws_matched, ri, [rec_id, 0, "—", "—", "Identical"])

    ws_matched.auto_filter.ref = f"A1:{get_column_letter(len(matched_headers))}1"

    # ── Sheet 4: Missing Records ──────────────────────────────────────────
    ws_miss = wb.create_sheet("Missing Records")
    miss_headers = [result.record_label + " / Auth ID", "Present In", "Missing From"]
    miss_widths = [25, 15, 15]
    _apply_headers(ws_miss, miss_headers, miss_widths, fill_color="C62828")

    ri = 2
    for key in result.only_in_a:
        _write_row(ws_miss, ri, [key, "File A", "File B"], fill_hex="FFF8E1")
        ri += 1
    for key in result.only_in_b:
        _write_row(ws_miss, ri, [key, "File B", "File A"], fill_hex="FFEBEE")
        ri += 1

    # ── Serialize ─────────────────────────────────────────────────────────
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()

