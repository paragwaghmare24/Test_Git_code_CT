"""
engines/business_rules_engine.py
Project-specific business rule validation.
All rules are deterministic — no AI.
"""

from __future__ import annotations

from backend.models.schemas import (
    EDITransactionSchema,
    ErrorSchema,
    RuleSource,
    Severity,
)


# ---------------------------------------------------------------------------
# Business Rule Definitions
# ---------------------------------------------------------------------------

def _check_claim_amount(segments: list[str], element_sep: str,
                         errors: list[ErrorSchema]) -> None:
    """BR: CLM02 (Total Claim Charge Amount) must be a positive number."""
    for seg in segments:
        parts = seg.split(element_sep)
        if parts[0].strip() == "CLM" and len(parts) > 2:
            clm02 = parts[2].strip()
            try:
                amount = float(clm02)
                if amount <= 0:
                    errors.append(ErrorSchema(
                        severity=Severity.ERROR,
                        segment="CLM",
                        element="CLM02",
                        description=f"Claim amount '{clm02}' must be greater than zero.",
                        source=RuleSource.BUSINESS,
                        rule_reference="BRE-001",
                        suggested_correction="Provide a positive claim charge amount in CLM02."
                    ))
            except ValueError:
                errors.append(ErrorSchema(
                    severity=Severity.ERROR,
                    segment="CLM",
                    element="CLM02",
                    description=f"Claim amount '{clm02}' is not a valid number.",
                    source=RuleSource.BUSINESS,
                    rule_reference="BRE-001",
                    suggested_correction="CLM02 must be a numeric value."
                ))


def _check_service_line_amount(segments: list[str], element_sep: str,
                                errors: list[ErrorSchema]) -> None:
    """BR: SV102 (Line Item Charge Amount) must be numeric and positive."""
    for seg in segments:
        parts = seg.split(element_sep)
        if parts[0].strip() == "SV1" and len(parts) > 2:
            sv102 = parts[2].strip()
            try:
                amount = float(sv102)
                if amount <= 0:
                    errors.append(ErrorSchema(
                        severity=Severity.WARNING,
                        segment="SV1",
                        element="SV102",
                        description=f"Service line amount '{sv102}' should be greater than zero.",
                        source=RuleSource.BUSINESS,
                        rule_reference="BRE-002",
                    ))
            except ValueError:
                errors.append(ErrorSchema(
                    severity=Severity.ERROR,
                    segment="SV1",
                    element="SV102",
                    description=f"Service line amount '{sv102}' is not a valid number.",
                    source=RuleSource.BUSINESS,
                    rule_reference="BRE-002",
                ))


def _check_diagnosis_codes(segments: list[str], element_sep: str,
                            errors: list[ErrorSchema]) -> None:
    """BR: HI segment must have at least one diagnosis code for 837 claims."""
    hi_segs = [s for s in segments if s.split(element_sep)[0].strip() == "HI"]
    if not hi_segs:
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="HI",
            description="At least one HI (diagnosis) segment is required for claims.",
            source=RuleSource.BUSINESS,
            rule_reference="BRE-003",
            suggested_correction=(
                "Add an HI segment with at least one ICD-10-CM diagnosis code. "
                "Example (principal diagnosis): HI*ABK:Z7389 "
                "or with qualifier ABF: HI*ABF:J189"
            )
        ))


def _check_provider_info(segments: list[str], element_sep: str,
                          errors: list[ErrorSchema]) -> None:
    """BR: Billing provider NM1 segment with qualifier '85' must be present."""
    nm1_85_present = False
    for seg in segments:
        parts = seg.split(element_sep)
        if parts[0].strip() == "NM1" and len(parts) > 1 and parts[1].strip() == "85":
            nm1_85_present = True
            break
    if not nm1_85_present:
        # Use qualifier-encoded segment label so this error does NOT bleed onto
        # other NM1 occurrences (IL, PR, 82, etc.) in the validation inspector.
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="NM1-85",
            element="NM101",
            description="Billing Provider NM1 segment (NM1*85) is missing from the transaction.",
            source=RuleSource.BUSINESS,
            rule_reference="BRE-004",
            suggested_correction=(
                "Add an NM1*85 segment for the Billing Provider in Loop 2010AA. "
                "Example: NM1*85*2*BILLING PROVIDER NAME***XX*<10-digit NPI>"
            )
        ))


def _check_subscriber_info(segments: list[str], element_sep: str,
                            errors: list[ErrorSchema]) -> None:
    """BR: NM1 segment with qualifier 'IL' (Insured/Subscriber) must be present."""
    nm1_il_present = False
    for seg in segments:
        parts = seg.split(element_sep)
        if parts[0].strip() == "NM1" and len(parts) > 1 and parts[1].strip() == "IL":
            nm1_il_present = True
            break
    if not nm1_il_present:
        # Qualifier-encoded label keeps this error scoped to NM1*IL absence
        # and prevents it from appearing on NM1*85, NM1*PR, etc.
        errors.append(ErrorSchema(
            severity=Severity.WARNING,
            segment="NM1-IL",
            element="NM101",
            description="Subscriber NM1 segment (NM1*IL) not found in the transaction.",
            source=RuleSource.BUSINESS,
            rule_reference="BRE-005",
            suggested_correction=(
                "Add an NM1*IL segment for the Subscriber/Insured in Loop 2010BA. "
                "Example: NM1*IL*1*LAST NAME*FIRST NAME***MI*<MEMBER ID>"
            )
        ))


def _check_service_dates(segments: list[str], element_sep: str,
                          errors: list[ErrorSchema]) -> None:
    """BR: DTP segments with qualifier 472 (Service Date) must be present for 837."""
    dtp_segs = [s for s in segments if s.split(element_sep)[0].strip() == "DTP"]
    has_service_date = any(
        s.split(element_sep)[1].strip() == "472"
        for s in dtp_segs
        if len(s.split(element_sep)) > 1
    )
    if not has_service_date:
        # Qualifier-encoded label prevents this from appearing on DTP*435, DTP*096, etc.
        errors.append(ErrorSchema(
            severity=Severity.ERROR,
            segment="DTP-472",
            element="DTP01",
            description="Service Date DTP segment (DTP*472) is missing from the transaction.",
            source=RuleSource.BUSINESS,
            rule_reference="BRE-006",
            suggested_correction=(
                "Add a DTP*472 segment in Loop 2400 with the service date. "
                "Single date example: DTP*472*D8*CCYYMMDD. "
                "Date-range example: DTP*472*RD8*CCYYMMDD-CCYYMMDD"
            )
        ))


# ---------------------------------------------------------------------------
# Transaction-specific rule sets
# ---------------------------------------------------------------------------

_RULES_837P = [
    _check_claim_amount,
    _check_service_line_amount,
    _check_diagnosis_codes,
    _check_provider_info,
    _check_subscriber_info,
    _check_service_dates,
]

_RULES_837I = [
    _check_claim_amount,
    _check_diagnosis_codes,
    _check_provider_info,
    _check_subscriber_info,
    _check_service_dates,
]

_RULES_GENERIC = [
    _check_provider_info,
    _check_subscriber_info,
]

# 278 (Health Care Services Review) has no Billing Provider (NM1*85) segment at
# all — it uses NM1*X3 (UMO/Payer) and NM1*1P (Requestor) instead. Reusing
# _RULES_GENERIC (which checks for NM1*85) always false-fired "Billing Provider
# missing" on every valid 278 transaction.
_RULES_278 = [
    _check_subscriber_info,
]

_RULES_BY_TYPE: dict[str, list] = {
    "837P": _RULES_837P,
    "837I": _RULES_837I,
    "278": _RULES_278,
    "834": [],
    "820": [],
    "999": [],
    "277CA": [],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(transaction: EDITransactionSchema, element_sep: str = "*") -> list[ErrorSchema]:
    """
    Run business rules for the given transaction type.
    Returns list of ErrorSchema violations.
    """
    errors: list[ErrorSchema] = []

    tx_type = transaction.transaction_type
    rules = _RULES_BY_TYPE.get(tx_type, _RULES_GENERIC)

    # Build a flat list of raw segment strings from the already-parsed transaction
    # schema.  Re-parsing raw_content with a hardcoded "~" terminator would silently
    # fail for newline-terminated EDI files, causing every presence-check rule to
    # fire a false positive even when the segment exists.
    segments: list[str] = []
    for group in transaction.groups:
        for ts in group.transaction_sets:
            if ts.st_segment:
                segments.append(ts.st_segment.raw)
            for seg in ts.segments:
                segments.append(seg.raw)
            if ts.se_segment:
                segments.append(ts.se_segment.raw)

    if not segments:
        return errors

    for rule_fn in rules:
        rule_fn(segments, element_sep, errors)

    return errors
