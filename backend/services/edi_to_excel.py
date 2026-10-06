"""
services/edi_to_excel.py
EDI to Excel Export Service.
Maps parsed EDI data to ExcelTemplateSchema and writes .xlsx output.
Processing Rule PR-08.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from backend.models.schemas import (
    EDITransactionSchema,
    ErrorSchema,
    ExcelExportRowSchema,
    ValidationResultSchema,
)
from backend.utils.file_handler import OUTPUTS_DIR


# ---------------------------------------------------------------------------
# Field Extraction Helpers
# ---------------------------------------------------------------------------

def _get_element(parts: list[str], idx: int) -> str:
    """Safely get an element value by index."""
    return parts[idx].strip() if idx < len(parts) else ""


def _find_segment(segments: list[str], seg_id: str, element_sep: str,
                   qualifier_idx: Optional[int] = None,
                   qualifier_val: Optional[str] = None) -> Optional[list[str]]:
    """Find FIRST matching segment by ID and optional qualifier."""
    for seg in segments:
        parts = seg.split(element_sep)
        if parts[0].strip() != seg_id:
            continue
        if qualifier_idx is not None and qualifier_val is not None:
            if len(parts) <= qualifier_idx or parts[qualifier_idx].strip() != qualifier_val:
                continue
        return parts
    return None


def _find_last_segment(segments: list[str], seg_id: str, element_sep: str,
                        qualifier_idx: Optional[int] = None,
                        qualifier_val: Optional[str] = None) -> Optional[list[str]]:
    """Find LAST matching segment by ID and optional qualifier (used for context lookback)."""
    result = None
    for seg in segments:
        parts = seg.split(element_sep)
        if parts[0].strip() != seg_id:
            continue
        if qualifier_idx is not None and qualifier_val is not None:
            if len(parts) <= qualifier_idx or parts[qualifier_idx].strip() != qualifier_val:
                continue
        result = parts
    return result


def _build_provider_name(parts: list[str]) -> str:
    """Build a provider name from NM1 parts (last/org name + first name)."""
    last = _get_element(parts, 3)
    first = _get_element(parts, 4)
    names = [p for p in [last, first] if p]
    return " ".join(names) if names else last


def _extract_sv_procedure(segments: list[str], element_sep: str,
                           component_sep: str) -> tuple[str, str, str, str]:
    """
    Extract service type, procedure code, revenue code from SV1/SV2/SV3 segments.
    Returns (service_type, procedure_code, revenue_code, claim_amount_override).
    """
    service_type = procedure_code = revenue_code = amount_override = ""

    # SV1 — Professional
    sv1 = _find_segment(segments, "SV1", element_sep)
    if sv1:
        sv1_01 = _get_element(sv1, 1)
        comp = sv1_01.split(component_sep)
        service_type = comp[0] if comp else ""
        procedure_code = comp[1] if len(comp) > 1 else ""
        amount_override = _get_element(sv1, 2)

    # SV2 — Institutional (revenue code)
    sv2 = _find_segment(segments, "SV2", element_sep)
    if sv2:
        revenue_code = _get_element(sv2, 1)
        if not procedure_code:
            sv2_02 = _get_element(sv2, 2)
            comp = sv2_02.split(component_sep) if sv2_02 else []
            procedure_code = comp[1] if len(comp) > 1 else sv2_02
        if not amount_override:
            amount_override = _get_element(sv2, 3)

    # SV3 — Dental (tooth procedure code)
    # SV3*qualifier:procedure_code:tooth_info*amount**units
    # May appear multiple times per claim — collect all codes
    proc_codes: list[str] = []
    for seg in segments:
        parts = seg.split(element_sep)
        if parts[0].strip() != "SV3":
            continue
        sv3_01 = _get_element(parts, 1)
        comp = sv3_01.split(component_sep)
        svc_type = comp[0] if comp else ""
        proc = comp[1] if len(comp) > 1 else ""
        if proc:
            proc_codes.append(proc)
        if not service_type:
            service_type = svc_type
        if not amount_override:
            amount_override = _get_element(parts, 2)

    if proc_codes and not procedure_code:
        procedure_code = ", ".join(proc_codes)

    return service_type, procedure_code, revenue_code, amount_override


# ---------------------------------------------------------------------------
# Per-Claim Multi-Row Extraction (handles multiple CLM per transaction set)
# ---------------------------------------------------------------------------

def _extract_all_claims(
    segments: list[str],
    element_sep: str,
    component_sep: str,
    transaction: EDITransactionSchema,
    validation_result: Optional[ValidationResultSchema] = None,
) -> list[ExcelExportRowSchema]:
    """
    Extract one ExcelExportRowSchema per CLM segment found in the transaction set.
    For each CLM, performs a backwards-scan to find the relevant billing provider
    and subscriber context, and a forward-scan for service line data.
    Handles 837P, 837I, 837D (dental), and any transaction with no CLM segments.
    """
    # Locate all CLM segment indices
    clm_indices = [
        i for i, seg in enumerate(segments)
        if seg.split(element_sep)[0].strip() == "CLM"
    ]

    # Header fields common to all rows
    def _base_row(group_ctrl: str = "", tx_ctrl: str = "") -> ExcelExportRowSchema:
        r = ExcelExportRowSchema()
        r.transaction_type = transaction.transaction_type
        r.sender_id = transaction.sender_id
        r.receiver_id = transaction.receiver_id
        r.interchange_control_number = transaction.interchange_control_number
        r.group_control_number = group_ctrl
        r.transaction_control_number = tx_ctrl
        if validation_result:
            r.validation_status = validation_result.status.value
            r.error_count = validation_result.error_count
            r.warning_count = validation_result.warning_count
        return r

    # Extract header control numbers from GS/ST segments
    gs = _find_segment(segments, "GS", element_sep)
    group_ctrl = _get_element(gs, 6) if gs else ""
    st = _find_segment(segments, "ST", element_sep)
    tx_ctrl = _get_element(st, 2) if st else ""

    if not clm_indices:
        # No CLM — one row with whatever can be found (e.g. 278, 835)
        row = _base_row(group_ctrl, tx_ctrl)
        _fill_context_from_segments(row, segments, element_sep, component_sep)
        _fill_service_from_segments(row, segments, element_sep, component_sep)
        return [row]

    rows: list[ExcelExportRowSchema] = []

    for clm_pos, clm_idx in enumerate(clm_indices):
        row = _base_row(group_ctrl, tx_ctrl)

        # --- Backward context: look before this CLM for billing provider / subscriber ---
        pre_segs = segments[:clm_idx]

        # Billing Provider — last NM1*85 before this CLM
        nm1_85 = _find_last_segment(pre_segs, "NM1", element_sep, 1, "85")
        if nm1_85:
            row.billing_provider_name = _build_provider_name(nm1_85)
            row.billing_provider_npi = _get_element(nm1_85, 9)

        # Subscriber — last NM1*IL before this CLM
        nm1_il = _find_last_segment(pre_segs, "NM1", element_sep, 1, "IL")
        if nm1_il:
            row.subscriber_last_name = _get_element(nm1_il, 3)
            row.subscriber_first_name = _get_element(nm1_il, 4)
            row.member_id = _get_element(nm1_il, 9)

        # Subscriber ID from REF — check pre-CLM segments, then also within claim
        for ref_qual in ["SY", "1W", "HJ", "1L", "6P", "F6", "EJ", "1J"]:
            ref = _find_last_segment(pre_segs, "REF", element_sep, 1, ref_qual)
            if ref:
                row.subscriber_id = _get_element(ref, 2)
                break
        if not row.subscriber_id and nm1_il:
            row.subscriber_id = _get_element(nm1_il, 9)

        # Demographics — last DMG before this CLM
        dmg = _find_last_segment(pre_segs, "DMG", element_sep)
        if dmg:
            row.dob = _get_element(dmg, 2)
            row.gender = _get_element(dmg, 3)

        # Patient (when patient != subscriber) — last NM1*QC before CLM
        nm1_qc = _find_last_segment(pre_segs, "NM1", element_sep, 1, "QC")
        if nm1_qc:
            row.member_id = _get_element(nm1_qc, 9)

        # --- Forward context: from CLM to the next CLM (or end) ---
        next_clm_idx = clm_indices[clm_pos + 1] if clm_pos + 1 < len(clm_indices) else len(segments)
        claim_segs = segments[clm_idx:next_clm_idx]

        # CLM segment itself
        clm_parts = claim_segs[0].split(element_sep)
        row.claim_number = _get_element(clm_parts, 1)
        row.claim_amount = _get_element(clm_parts, 2)

        # Rendering Provider within claim
        nm1_82 = _find_segment(claim_segs, "NM1", element_sep, 1, "82")
        if nm1_82:
            row.rendering_provider_name = _build_provider_name(nm1_82)
            row.rendering_provider_npi = _get_element(nm1_82, 9)

        # Referring Provider within claim
        nm1_dn = _find_segment(claim_segs, "NM1", element_sep, 1, "DN")
        if nm1_dn:
            row.referring_provider_name = _build_provider_name(nm1_dn)
            row.referring_provider_npi = _get_element(nm1_dn, 9)

        # Authorization number
        ref_g1 = _find_segment(claim_segs, "REF", element_sep, 1, "G1")
        if ref_g1:
            row.authorization_number = _get_element(ref_g1, 2)

        # Service date DTP*472
        dtp_472 = _find_segment(claim_segs, "DTP", element_sep, 1, "472")
        if dtp_472:
            row.service_date = _get_element(dtp_472, 3)

        # Service lines (SV1 / SV2 / SV3)
        svc_type, proc_code, rev_code, _amt = _extract_sv_procedure(
            claim_segs, element_sep, component_sep
        )
        row.service_type = svc_type
        row.procedure_code = proc_code
        row.revenue_code = rev_code

        # Diagnosis codes HI
        hi = _find_segment(claim_segs, "HI", element_sep)
        if hi:
            diag_codes: list[str] = []
            for idx in range(1, len(hi)):
                hi_elem = _get_element(hi, idx)
                if hi_elem:
                    comp = hi_elem.split(component_sep)
                    code = comp[1] if len(comp) > 1 else comp[0]
                    if code:
                        diag_codes.append(code)
            row.diagnosis_code = ", ".join(diag_codes)

        # Claim status from validation
        if validation_result:
            row.claim_status = "REJECTED" if validation_result.error_count > 0 else "ACCEPTED"

        rows.append(row)

    return rows


def _fill_context_from_segments(row: ExcelExportRowSchema, segments: list[str],
                                 element_sep: str, component_sep: str) -> None:
    """Fill subscriber/provider fields for non-CLM transactions (278, 835, etc.)."""
    nm1_il = _find_segment(segments, "NM1", element_sep, 1, "IL")
    if nm1_il:
        row.subscriber_last_name = _get_element(nm1_il, 3)
        row.subscriber_first_name = _get_element(nm1_il, 4)
        row.member_id = _get_element(nm1_il, 9)
    for ref_qual in ["SY", "1W", "HJ", "1L", "6P", "F6", "EJ", "1J"]:
        ref = _find_segment(segments, "REF", element_sep, 1, ref_qual)
        if ref:
            row.subscriber_id = _get_element(ref, 2)
            break
    if not row.subscriber_id and nm1_il:
        row.subscriber_id = _get_element(nm1_il, 9)
    nm1_qc = _find_segment(segments, "NM1", element_sep, 1, "QC")
    if nm1_qc:
        row.member_id = _get_element(nm1_qc, 9)
    dmg = _find_segment(segments, "DMG", element_sep)
    if dmg:
        row.dob = _get_element(dmg, 2)
        row.gender = _get_element(dmg, 3)
    nm1_85 = _find_segment(segments, "NM1", element_sep, 1, "85")
    if nm1_85:
        row.billing_provider_name = _build_provider_name(nm1_85)
        row.billing_provider_npi = _get_element(nm1_85, 9)
    nm1_82 = _find_segment(segments, "NM1", element_sep, 1, "82")
    if nm1_82:
        row.rendering_provider_name = _build_provider_name(nm1_82)
        row.rendering_provider_npi = _get_element(nm1_82, 9)


def _fill_service_from_segments(row: ExcelExportRowSchema, segments: list[str],
                                  element_sep: str, component_sep: str) -> None:
    """Fill service-line and date fields for non-CLM transactions."""
    dtp_472 = _find_segment(segments, "DTP", element_sep, 1, "472")
    if dtp_472:
        row.service_date = _get_element(dtp_472, 3)
    ref_g1 = _find_segment(segments, "REF", element_sep, 1, "G1")
    if ref_g1:
        row.authorization_number = _get_element(ref_g1, 2)
    svc_type, proc_code, rev_code, _ = _extract_sv_procedure(segments, element_sep, component_sep)
    row.service_type = svc_type
    row.procedure_code = proc_code
    row.revenue_code = rev_code
    hi = _find_segment(segments, "HI", element_sep)
    if hi:
        diag_codes: list[str] = []
        for idx in range(1, len(hi)):
            hi_elem = _get_element(hi, idx)
            if hi_elem:
                comp = hi_elem.split(component_sep)
                code = comp[1] if len(comp) > 1 else comp[0]
                if code:
                    diag_codes.append(code)
        row.diagnosis_code = ", ".join(diag_codes)


# ---------------------------------------------------------------------------
# Legacy single-row extractor (kept for backward compatibility)
# ---------------------------------------------------------------------------

def _extract_row(
    segments: list[str],
    element_sep: str,
    component_sep: str,
    transaction: EDITransactionSchema,
    validation_result: Optional[ValidationResultSchema] = None,
) -> ExcelExportRowSchema:
    """Extract one ExcelExportRowSchema — delegates to multi-row extractor, returns first row."""
    rows = _extract_all_claims(segments, element_sep, component_sep, transaction, validation_result)
    return rows[0] if rows else ExcelExportRowSchema()


# ---------------------------------------------------------------------------
# Excel Writer
# ---------------------------------------------------------------------------

_HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_ERROR_FILL = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
_WARNING_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
_PASS_FILL = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")


def _write_master_sheet(ws, rows: list[ExcelExportRowSchema]) -> None:
    """Write Master Output sheet."""
    headers = [
        "File Name", "Transaction Type", "Sender ID", "Receiver ID",
        "Interchange Control Number", "Group Control Number", "Transaction Control Number",
        "Subscriber ID", "Subscriber First Name", "Subscriber Last Name",
        "Member ID", "DOB", "Gender",
        "Billing Provider Name", "Billing Provider NPI",
        "Rendering Provider Name", "Rendering Provider NPI",
        "Referring Provider Name", "Referring Provider NPI",
        "Claim Number", "Claim Amount", "Authorization Number",
        "Service Type", "Diagnosis Code", "Procedure Code", "Revenue Code",
        "Service Date", "Claim Status", "Validation Status",
        "Error Count", "Warning Count",
        "Companion Guide Reference", "TP Mapping Reference",
    ]
    ws.title = "Master Output"
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    for row in rows:
        data = [
            row.file_name, row.transaction_type, row.sender_id, row.receiver_id,
            row.interchange_control_number, row.group_control_number,
            row.transaction_control_number,
            row.subscriber_id, row.subscriber_first_name, row.subscriber_last_name,
            row.member_id, row.dob, row.gender,
            row.billing_provider_name, row.billing_provider_npi,
            row.rendering_provider_name, row.rendering_provider_npi,
            row.referring_provider_name, row.referring_provider_npi,
            row.claim_number, row.claim_amount, row.authorization_number,
            row.service_type, row.diagnosis_code, row.procedure_code, row.revenue_code,
            row.service_date, row.claim_status, row.validation_status,
            row.error_count, row.warning_count,
            row.companion_guide_reference, row.tp_mapping_reference,
        ]
        ws.append(data)
        # Color by validation status
        row_idx = ws.max_row
        fill = None
        if row.validation_status == "FAIL":
            fill = _ERROR_FILL
        elif row.validation_status == "WARNING":
            fill = _WARNING_FILL
        elif row.validation_status == "PASS":
            fill = _PASS_FILL
        if fill:
            for col in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=col).fill = fill

    _auto_width(ws)


def _write_validation_sheet(
    ws, errors: list[ErrorSchema], title: str = "Validation Report"
) -> None:
    ws.title = title
    headers = ["Error ID", "Severity", "Segment", "Element",
                "Description", "Rule Source", "Rule Reference", "Suggested Fix"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
    for e in errors:
        ws.append([
            e.error_id, e.severity.value, e.segment, e.element,
            e.description, e.source.value, e.rule_reference, e.suggested_correction,
        ])
    _auto_width(ws)


def _write_comparison_sheet(ws, differences: list) -> None:
    ws.title = "Comparison Report"
    headers = ["Field", "Segment", "File A Value", "File B Value",
                "Difference Type", "Description"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
    for d in differences:
        ws.append([
            d.field, d.segment,
            d.file_a_value, d.file_b_value,
            d.difference_type.value, d.description,
        ])
    _auto_width(ws)


def _auto_width(ws) -> None:
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 4, 60)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_to_excel(
    transactions: list[tuple[EDITransactionSchema, Optional[ValidationResultSchema]]],
    output_filename: Optional[str] = None,
    comparison_result=None,
) -> Path:
    """
    Export one or more parsed transactions to Excel.
    Each tuple is (transaction, optional_validation_result).
    Returns path to the written .xlsx file.
    """
    wb = openpyxl.Workbook()
    master_ws = wb.active

    rows: list[ExcelExportRowSchema] = []
    all_errors: list[ErrorSchema] = []
    all_warnings: list[ErrorSchema] = []

    for transaction, val_result in transactions:
        element_sep = (
            transaction.isa_segment.raw[3]
            if transaction.isa_segment and len(transaction.isa_segment.raw) > 3
            else "*"
        )
        component_sep = ":"

        for group in transaction.groups:
            for ts in group.transaction_sets:
                # Include GS and ST/SE segments so _extract_row can find them
                seg_raws: list[str] = []
                if group.gs_segment:
                    seg_raws.append(group.gs_segment.raw)
                if ts.st_segment:
                    seg_raws.append(ts.st_segment.raw)
                seg_raws.extend([s.raw for s in ts.segments])
                if ts.se_segment:
                    seg_raws.append(ts.se_segment.raw)

                # Use multi-claim extractor — produces one row per CLM segment
                claim_rows = _extract_all_claims(
                    seg_raws, element_sep, component_sep, transaction, val_result
                )
                for row in claim_rows:
                    row.file_name = transaction.source_file
                    # Prefer direct group/ts metadata when segment lookup missed them
                    if not row.group_control_number:
                        row.group_control_number = group.group_control_number
                    if not row.transaction_control_number:
                        row.transaction_control_number = ts.transaction_set_control_number
                    row.companion_guide_reference = transaction.transaction_type
                    rows.append(row)

        if val_result:
            all_errors.extend(val_result.errors)
            all_warnings.extend(val_result.warnings)

    _write_master_sheet(master_ws, rows)

    if all_errors or all_warnings:
        val_ws = wb.create_sheet()
        _write_validation_sheet(val_ws, all_errors + all_warnings)

    if comparison_result and comparison_result.differences:
        comp_ws = wb.create_sheet()
        _write_comparison_sheet(comp_ws, comparison_result.differences)

    filename = output_filename or f"edi_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.xlsx"
    out_path = OUTPUTS_DIR / filename
    wb.save(str(out_path))
    return out_path
