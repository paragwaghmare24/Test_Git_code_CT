# LLM.md — EDI Accelerator Platform Project Constitution
# Version: 1.0
# Date: 2026-08-07
# Status: DRAFT — Awaiting Blueprint Approval

---

## 1. Project Identity

| Property | Value |
|---|---|
| Project Name | EDI Accelerator Platform |
| Version | 1.0 |
| Owner | EDI_TOOL Workspace |
| Deployment | Local Machine |
| Storage | File System Only |

---

## 2. Data Schemas (Source of Truth: DataSchema.md)

### CompanionGuideSchema
| Field | Type | Notes |
|---|---|---|
| GuideId | string | UUID generated on upload |
| GuideName | string | File name |
| Version | string | User-provided or extracted |
| TransactionType | string | 837P, 837I, 278, 834, 820, 999, 277CA |
| Rules | list[dict] | Extracted rules from guide |
| UploadDate | datetime | ISO 8601 |

### TPMappingSchema
| Field | Type | Notes |
|---|---|---|
| PartnerName | string | Trading partner name |
| Version | string | Mapping version |
| TransactionType | string | |
| SourceSegment | string | X12 segment |
| SourceElement | string | X12 element reference |
| TargetField | string | Output field name |
| Mandatory | boolean | |

### EDITransactionSchema
| Field | Type | Notes |
|---|---|---|
| TransactionType | string | |
| InterchangeControlNumber | string | ISA13 |
| Groups | list[FunctionalGroup] | GS/GE wrapper |
| Transactions | list[TransactionSet] | ST/SE wrapper |

### SegmentSchema
| Field | Type | Notes |
|---|---|---|
| SegmentId | string | e.g. CLM, NM1, SV1 |
| Name | string | Human-readable name |
| Loop | string | Loop identifier |
| Elements | list[ElementSchema] | |

### ElementSchema
| Field | Type | Notes |
|---|---|---|
| ElementId | string | e.g. CLM01 |
| Description | string | |
| Value | string | |
| Required | boolean | |

### ValidationResultSchema
| Field | Type | Notes |
|---|---|---|
| Status | string | PASS / FAIL / WARNING |
| ErrorCount | int | |
| WarningCount | int | |
| Errors | list[ErrorSchema] | |
| Warnings | list[ErrorSchema] | |

### ErrorSchema
| Field | Type | Notes |
|---|---|---|
| ErrorId | string | UUID |
| Severity | string | ERROR / WARNING |
| Segment | string | Segment identifier |
| Element | string | Element reference |
| Description | string | Human-readable description |
| Source | string | HIPAA / COMPANION_GUIDE / TP_MAPPING / BUSINESS |
| RuleReference | string | Rule ID from source document |
| SuggestedCorrection | string | |

### CorrectionSchema
| Field | Type | Notes |
|---|---|---|
| ErrorId | string | Reference to ErrorSchema |
| BeforeValue | string | |
| AfterValue | string | |
| RequiresApproval | boolean | Always true for AI-suggested corrections |
| ApprovedBy | string | User ID or "USER" |

### ComparisonSchema
| Field | Type | Notes |
|---|---|---|
| Field | string | |
| ExpectedValue | string | |
| ActualValue | string | |
| DifferenceType | string | MISSING / EXTRA / MISMATCH / VALUE_CHANGE |

### AIApprovalSchema
| Field | Type | Notes |
|---|---|---|
| RequestId | string | UUID |
| Requested | string | What AI was asked to do |
| Approved | boolean | |
| Timestamp | datetime | |
| Model | string | GHCP model name only |

### AuditSchema
| Field | Type | Notes |
|---|---|---|
| Timestamp | datetime | |
| User | string | |
| Action | string | |
| Module | string | |
| Result | string | |
| AIUsed | boolean | |

### BatchExecutionSchema
| Field | Type | Notes |
|---|---|---|
| ExecutionId | string | UUID |
| FileCount | int | |
| PassCount | int | |
| FailCount | int | |

### ReportSchema
| Field | Type | Notes |
|---|---|---|
| Summary | dict | Aggregated stats |
| Errors | list[ErrorSchema] | |
| Warnings | list[ErrorSchema] | |
| Corrections | list[CorrectionSchema] | |
| Statistics | dict | |

---

## 3. Architectural Rules

| # | Rule | Enforcement |
|---|---|---|
| AR-01 | Python is the primary processing language | Hard |
| AR-02 | React + TypeScript is the UI layer | Hard |
| AR-03 | FastAPI is the orchestration layer | Hard |
| AR-04 | File system is the only storage backend | Hard |
| AR-05 | All services are deterministic (no AI) by default | Hard |
| AR-06 | AI (GHCP only) requires explicit user approval per invocation | Hard |
| AR-07 | Documentation must be updated before code | Hard |
| AR-08 | No OpenAI API, Azure OpenAI, Gemini, Anthropic, or any external LLM | Hard |
| AR-09 | Companion Guide is primary source of truth for validation rules | Hard |
| AR-10 | TP Mapping overrides Companion Guide where explicitly mapped | Hard |

---

## 4. Processing Rules

| # | Rule |
|---|---|
| PR-01 | EDI generation requires all mandatory fields from Companion Guide; missing fields halt generation |
| PR-02 | Validation runs in order: Syntax → HIPAA → Companion Guide → TP Mapping → Business Rules |
| PR-03 | Comparison produces field-level diff for every segment and element |
| PR-04 | Auto-correction only proposes changes; user must approve before file is written |
| PR-05 | Batch processing generates one consolidated report per batch run |
| PR-06 | 999 analysis maps AK5/IK5 codes to human-readable descriptions |
| PR-07 | 277CA analysis maps STC codes to claim status descriptions |
| PR-08 | Excel export maps all fields from ExcelTemplateSchema.md |
| PR-09 | Audit log entry created for every API call |
| PR-10 | AI invocation creates AIApprovalSchema record before AI is called |

---

## 5. Validation Rules

| # | Rule |
|---|---|
| VR-01 | ISA segment must have exactly 16 elements |
| VR-02 | Interchange Control Numbers (ISA13/IEA02) must match |
| VR-03 | Group Control Numbers (GS06/GE02) must match |
| VR-04 | Transaction Set Control Numbers (ST02/SE02) must match |
| VR-05 | Segment count in SE01 must match actual segment count |
| VR-06 | All mandatory loops and segments per Companion Guide must be present |
| VR-07 | Element data types (AN, DT, TM, N, R, ID) must be valid |
| VR-08 | Code values must be from X12 or Companion Guide approved code lists |
| VR-09 | Date format: CCYYMMDD |
| VR-10 | Time format: HHMM or HHMMSS |
| VR-11 | NPI must be 10-digit numeric |
| VR-12 | Qualifier codes must match X12 or Companion Guide specification |

---

## 6. Security Rules

| # | Rule |
|---|---|
| SR-01 | No PHI/PII logged to console or log files in plain text |
| SR-02 | File paths must be validated before any read/write operation |
| SR-03 | Uploaded files stored in controlled /data/ directory only |
| SR-04 | No external API calls except GHCP (gated by AI consent) |
| SR-05 | No hardcoded credentials anywhere in codebase |

---

## 7. Behavioral Rules

| # | Rule |
|---|---|
| BR-01 | Never assume a value; always ask if required data is missing |
| BR-02 | Every error must include a RuleReference to its source |
| BR-03 | Every correction must be traceable to an error |
| BR-04 | AI suggestions are marked as AI_SUGGESTED and require user approval |
| BR-05 | All outputs include execution timestamp and source file reference |

---

## 8. Project Invariants

1. The Companion Guide is ALWAYS the primary rule source.
2. AI NEVER runs without explicit user approval.
3. Data is NEVER assumed or fabricated.
4. Every action is auditable.
5. Corrections are NEVER applied without user approval.
6. Only GHCP models are permitted for AI functions.
7. File system is the only persistence mechanism.

---

## 9. Companion Guide Files (Available)

| Transaction | File |
|---|---|
| 837P | 837P_Companion_Guide.docx |
| 837I | 837I_Companion_Guide.docx |
| 278 | 278_Companion_Guide.docx |
| 834 | EDI_834_Companion_Guide.docx |
| 820 | 820_Version_218_Companion_Guide.docx |
| 277CA | X12 HIPAA 277 Claim Acknowledgement (X214).pdf |
| 999 | X12 HIPAA 999 Implementation Acknowledgment (X231).pdf |

---

## 10. Supported Transactions

837P, 837I, 278, 834, 820, 999, 277CA

---

## Change Log

| Date | Version | Change | Author |
|---|---|---|---|
| 2026-08-07 | 1.0 | Initial draft from discovery | System Pilot |
