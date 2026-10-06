"""
models/schemas.py
EDI Accelerator Platform — Pydantic Data Models
Source of Truth: DataSchema.md + LLM.md
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class DifferenceType(str, Enum):
    MISSING = "MISSING"
    EXTRA = "EXTRA"
    MISMATCH = "MISMATCH"
    VALUE_CHANGE = "VALUE_CHANGE"


class RuleSource(str, Enum):
    HIPAA = "HIPAA"
    COMPANION_GUIDE = "COMPANION_GUIDE"
    TP_MAPPING = "TP_MAPPING"
    BUSINESS = "BUSINESS"
    SYNTAX = "SYNTAX"


class TransactionType(str, Enum):
    T837P = "837P"
    T837I = "837I"
    T278 = "278"
    T834 = "834"
    T820 = "820"
    T999 = "999"
    T277CA = "277CA"


# ---------------------------------------------------------------------------
# Core EDI Models
# ---------------------------------------------------------------------------

class ElementSchema(BaseModel):
    element_id: str = Field(..., description="Element reference, e.g. CLM01")
    description: str = Field(default="", description="Human-readable element name")
    value: str = Field(default="", description="Parsed element value")
    required: bool = Field(default=False)


class SegmentSchema(BaseModel):
    segment_id: str = Field(..., description="Segment identifier, e.g. CLM, NM1, SV1")
    name: str = Field(default="", description="Human-readable segment name")
    loop: str = Field(default="", description="Loop identifier the segment belongs to")
    position: int = Field(default=0, description="Ordinal position in transaction set")
    raw: str = Field(default="", description="Raw segment string")
    elements: list[ElementSchema] = Field(default_factory=list)


class FunctionalGroup(BaseModel):
    gs_segment: Optional[SegmentSchema] = None
    ge_segment: Optional[SegmentSchema] = None
    group_control_number: str = Field(default="")
    functional_identifier: str = Field(default="")
    transaction_sets: list["TransactionSet"] = Field(default_factory=list)


class TransactionSet(BaseModel):
    st_segment: Optional[SegmentSchema] = None
    se_segment: Optional[SegmentSchema] = None
    transaction_set_control_number: str = Field(default="")
    transaction_type: str = Field(default="")
    segments: list[SegmentSchema] = Field(default_factory=list)


class EDITransactionSchema(BaseModel):
    transaction_type: str = Field(default="")
    interchange_control_number: str = Field(default="")
    sender_id: str = Field(default="")
    receiver_id: str = Field(default="")
    interchange_date: str = Field(default="")
    interchange_time: str = Field(default="")
    isa_segment: Optional[SegmentSchema] = None
    iea_segment: Optional[SegmentSchema] = None
    groups: list[FunctionalGroup] = Field(default_factory=list)
    raw_content: str = Field(default="", description="Full raw EDI file content")
    source_file: str = Field(default="")


# ---------------------------------------------------------------------------
# Validation Models
# ---------------------------------------------------------------------------

class ErrorSchema(BaseModel):
    error_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    severity: Severity = Severity.ERROR
    segment: str = Field(default="")
    element: str = Field(default="")
    description: str = Field(...)
    source: RuleSource = RuleSource.SYNTAX
    rule_reference: str = Field(default="")
    suggested_correction: str = Field(default="")
    loop: str = Field(default="")
    position: int = Field(default=0)


class ValidationResultSchema(BaseModel):
    status: ValidationStatus = ValidationStatus.PASS
    error_count: int = 0
    warning_count: int = 0
    errors: list[ErrorSchema] = Field(default_factory=list)
    warnings: list[ErrorSchema] = Field(default_factory=list)
    source_file: str = Field(default="")
    transaction_type: str = Field(default="")
    executed_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Correction Models
# ---------------------------------------------------------------------------

class CorrectionSchema(BaseModel):
    correction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    error_id: str = Field(...)
    segment: str = Field(default="")
    element: str = Field(default="")
    before_value: str = Field(default="")
    after_value: str = Field(...)
    requires_approval: bool = Field(default=True)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    ai_suggested: bool = Field(default=False)


class CorrectionResponseSchema(BaseModel):
    corrections: list[CorrectionSchema] = Field(default_factory=list)
    corrected_edi: Optional[str] = None
    requires_approval: bool = True
    approval_token: str = Field(default_factory=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Comparison Models
# ---------------------------------------------------------------------------

class ComparisonSchema(BaseModel):
    field: str = Field(...)
    segment: str = Field(default="")
    loop: str = Field(default="")
    element_name: str = Field(default="")
    file_a_value: str = Field(default="")
    file_b_value: str = Field(default="")
    difference_type: DifferenceType = DifferenceType.VALUE_CHANGE
    description: str = Field(default="")
    suggested_resolution: str = Field(default="")


class RecordComparisonSchema(BaseModel):
    """Per-record (claim / authorization) comparison result."""
    record_id: str = Field(...)
    lines_a: list[str] = Field(default_factory=list)
    lines_b: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    differences: list[ComparisonSchema] = Field(default_factory=list)
    modified_segments: list[str] = Field(default_factory=list)
    modified_elements: list[str] = Field(default_factory=list)
    total_differences: int = 0


class ComparisonResultSchema(BaseModel):
    file_a: str = Field(default="")
    file_b: str = Field(default="")
    total_differences: int = 0
    differences: list[ComparisonSchema] = Field(default_factory=list)
    # Aligned side-by-side diff (all three lists share the same length)
    lines_a: list[str] = Field(default_factory=list)
    lines_b: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)   # 'same'|'modified'|'removed'|'added'
    # Segment-level summary statistics
    total_segments_compared: int = 0
    missing_segments_count: int = 0
    extra_segments_count: int = 0
    modified_values_count: int = 0
    # Business-record (claim / authorization) matching
    record_level_used: bool = False          # True when smart claim/auth matching was applied
    record_label: str = "Record"             # "Claim" for 837, "Authorization" for 278
    record_a_count: int = 0                  # Total business records in File A
    record_b_count: int = 0                  # Total business records in File B
    matched_records_count: int = 0           # Records present in both files
    only_in_a: list[str] = Field(default_factory=list)   # Record keys only in File A
    only_in_b: list[str] = Field(default_factory=list)   # Record keys only in File B
    # Per-record (claim/auth) detailed comparison
    matched_record_ids: list[str] = Field(default_factory=list)
    record_comparisons: dict[str, RecordComparisonSchema] = Field(default_factory=dict)
    records_with_differences: int = 0
    records_without_differences: int = 0
    total_record_differences: int = 0
    matching_key_used: str = ""
    transaction_type: str = ""
    executed_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Companion Guide Models
# ---------------------------------------------------------------------------

class CompanionGuideRuleSchema(BaseModel):
    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    segment: str = Field(default="")
    element: str = Field(default="")
    loop: str = Field(default="")
    rule_text: str = Field(...)
    mandatory: bool = Field(default=False)
    condition: str = Field(default="")
    page_reference: str = Field(default="")


class CompanionGuideSchema(BaseModel):
    guide_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    guide_name: str = Field(...)
    version: str = Field(default="")
    transaction_type: str = Field(...)
    rules: list[CompanionGuideRuleSchema] = Field(default_factory=list)
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    source_file: str = Field(default="")


# ---------------------------------------------------------------------------
# TP Mapping Models
# ---------------------------------------------------------------------------

class TPMappingEntrySchema(BaseModel):
    source_segment: str = Field(...)
    source_element: str = Field(...)
    target_field: str = Field(...)
    mandatory: bool = Field(default=False)
    value_map: dict[str, str] = Field(default_factory=dict)
    condition: str = Field(default="")


class TPMappingSchema(BaseModel):
    mapping_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    partner_name: str = Field(...)
    version: str = Field(default="")
    transaction_type: str = Field(...)
    entries: list[TPMappingEntrySchema] = Field(default_factory=list)
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    source_file: str = Field(default="")


# ---------------------------------------------------------------------------
# AI Approval Models
# ---------------------------------------------------------------------------

class AIApprovalSchema(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    requested_action: str = Field(...)
    context: str = Field(default="")
    approved: bool = Field(default=False)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model: str = Field(default="GHCP")
    result: Optional[str] = None


# ---------------------------------------------------------------------------
# Audit Models
# ---------------------------------------------------------------------------

class AuditSchema(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user: str = Field(default="SYSTEM")
    action: str = Field(...)
    module: str = Field(...)
    input_summary: str = Field(default="")
    result: str = Field(default="")
    ai_used: bool = Field(default=False)
    ai_request_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Batch Models
# ---------------------------------------------------------------------------

class BatchExecutionSchema(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    file_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    warning_count: int = 0
    results: list[ValidationResultSchema] = Field(default_factory=list)
    report_path: str = Field(default="")


# ---------------------------------------------------------------------------
# Reporting Models
# ---------------------------------------------------------------------------

class ReportSchema(BaseModel):
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[ErrorSchema] = Field(default_factory=list)
    warnings: list[ErrorSchema] = Field(default_factory=list)
    corrections: list[CorrectionSchema] = Field(default_factory=list)
    statistics: dict[str, Any] = Field(default_factory=dict)
    source_files: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 999 / 277CA Models
# ---------------------------------------------------------------------------

class AK5StatusSchema(BaseModel):
    ak5_01: str = Field(default="", description="Transaction Set Acknowledgment Code")
    ak5_02: Optional[str] = Field(default=None, description="Implementation Transaction Set Syntax Error Code 1")
    ak5_03: Optional[str] = Field(default=None, description="Error Code 2")
    human_readable: str = Field(default="")


class Analysis999Schema(BaseModel):
    transaction_set_id: str = Field(default="")
    status: str = Field(default="")
    ak5_status: Optional[AK5StatusSchema] = None
    errors: list[ErrorSchema] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    human_readable_summary: str = Field(default="")


class Analysis999ResultSchema(BaseModel):
    source_file: str = Field(default="")
    overall_status: str = Field(default="")
    transaction_analyses: list[Analysis999Schema] = Field(default_factory=list)
    executed_at: datetime = Field(default_factory=datetime.utcnow)


class STCStatusSchema(BaseModel):
    stc_01: str = Field(default="", description="Health Care Claim Status Category Code")
    stc_02: str = Field(default="", description="Status Code")
    stc_03: Optional[str] = Field(default=None)
    category_description: str = Field(default="")
    status_description: str = Field(default="")


class Analysis277CAClaimSchema(BaseModel):
    claim_number: str = Field(default="")
    member_id: str = Field(default="")
    provider_npi: str = Field(default="")
    status: str = Field(default="")
    stc_status: Optional[STCStatusSchema] = None
    human_readable_summary: str = Field(default="")


class Analysis277CAResultSchema(BaseModel):
    source_file: str = Field(default="")
    claim_analyses: list[Analysis277CAClaimSchema] = Field(default_factory=list)
    executed_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Excel Export Model
# ---------------------------------------------------------------------------

class ExcelExportRowSchema(BaseModel):
    file_name: str = Field(default="")
    transaction_type: str = Field(default="")
    sender_id: str = Field(default="")
    receiver_id: str = Field(default="")
    interchange_control_number: str = Field(default="")
    group_control_number: str = Field(default="")
    transaction_control_number: str = Field(default="")
    subscriber_id: str = Field(default="")
    subscriber_first_name: str = Field(default="")
    subscriber_last_name: str = Field(default="")
    member_id: str = Field(default="")
    dob: str = Field(default="")
    gender: str = Field(default="")
    billing_provider_name: str = Field(default="")
    billing_provider_npi: str = Field(default="")
    rendering_provider_name: str = Field(default="")
    rendering_provider_npi: str = Field(default="")
    referring_provider_name: str = Field(default="")
    referring_provider_npi: str = Field(default="")
    claim_number: str = Field(default="")
    claim_amount: str = Field(default="")
    authorization_number: str = Field(default="")
    service_type: str = Field(default="")
    diagnosis_code: str = Field(default="")
    procedure_code: str = Field(default="")
    revenue_code: str = Field(default="")
    service_date: str = Field(default="")
    claim_status: str = Field(default="")
    validation_status: str = Field(default="")
    error_count: int = 0
    warning_count: int = 0
    companion_guide_reference: str = Field(default="")
    tp_mapping_reference: str = Field(default="")
    dynamic_fields: dict[str, str] = Field(default_factory=dict)


# Update forward references
FunctionalGroup.model_rebuild()
TransactionSet.model_rebuild()
