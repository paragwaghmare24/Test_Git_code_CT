# Architecture.md

# EDI Accelerator Platform Architecture

## Vision
Build an enterprise-grade healthcare EDI platform that generates, validates, compares, corrects, analyzes and exports EDI transactions using a deterministic Python engine. AI assistance is optional and uses GitHub Copilot (GHCP) models only after explicit user approval.

## Core Principles
1. Python first.
2. No assumptions.
3. Companion Guide is source of truth.
4. Trading Partner mapping can override generic rules.
5. Every action must be auditable.
6. AI never runs automatically.

## High Level Architecture
React UI
↓
FastAPI Orchestrator
↓
Processing Services
↓
Rule Engines
↓
Reports / Exports

## Processing Services
- EDI Generator Service
- EDI Parser Service
- EDI Validator Service
- EDI Compare Service
- Auto Correction Service
- EDI To Excel Service
- 999 Analyzer Service
- 277CA Analyzer Service
- Reporting Service
- Audit Service
- Batch Processing Service

## Rule Engines
### HIPAA Engine
Standard X12 validation.

### Companion Guide Engine
Reads payer guide.
Maintains version history.
Provides rule references.

### Trading Partner Mapping Engine
User uploads TP mappings.
Used during generation, validation and export.

### Business Rules Engine
Project specific rules.

## React Components
Dashboard
UploadPanel
CompanionGuidePanel
TPMappingPanel
ValidationPanel
ErrorPanel
CorrectionPanel
SegmentPanel
ComparePanel
Response999Panel
Response277CAPanel
ExportPanel
AuditPanel
AIConsentDialog

## Validation Workspace
Left: EDI Viewer
Center: Error Grid
Right: Error Details
Bottom: Segment Explanation

## Companion Guide Engine
Functions:
- Upload Guide
- Version Control
- Rule Extraction
- Rule Search
- Rule Traceability
- Difference Analysis

## Trading Partner Mapping Engine
Functions:
- Upload Mapping
- Mapping Validation
- Field Transformations
- Segment Mapping
- Value Mapping
- Rule Overrides

## Learning Repository
Store:
- Common Errors
- Approved Corrections
- Historical Outcomes
- Reusable Templates

## Batch Processing
Upload Folder.
Process hundreds of files.
Generate consolidated report.

## QA Evidence Package
Validation Report
Error Report
Comparison Report
Corrected File
Excel Output
Execution Summary
Audit Log

## AI Governance
User Requests AI
→ Approval Dialog
→ GHCP Invocation
→ Audit Entry
→ Response

Allowed AI Functions:
- Requirement to EDI
- Error Explanation
- Companion Guide Q&A
- Correction Suggestions

Not Allowed:
- Silent Validation Overrides
- Automatic File Changes
- Assumptions
