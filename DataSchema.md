# DataSchema.md

# CompanionGuideSchema
GuideId
GuideName
Version
TransactionType
Rules
UploadDate

# TPMappingSchema
PartnerName
Version
TransactionType
SourceSegment
SourceElement
TargetField
Mandatory

# EDITransactionSchema
TransactionType
InterchangeControlNumber
Groups
Transactions

# SegmentSchema
SegmentId
Name
Loop
Elements

# ElementSchema
ElementId
Description
Value
Required

# ValidationResultSchema
Status
ErrorCount
WarningCount
Errors
Warnings

# ErrorSchema
ErrorId
Severity
Segment
Element
Description
Source
RuleReference
SuggestedCorrection

# CorrectionSchema
ErrorId
BeforeValue
AfterValue
RequiresApproval
ApprovedBy

# ComparisonSchema
Field
ExpectedValue
ActualValue
DifferenceType

# AIApprovalSchema
RequestId
Requested
Approved
Timestamp
Model

# AuditSchema
Timestamp
User
Action
Module
Result
AIUsed

# BatchExecutionSchema
ExecutionId
FileCount
PassCount
FailCount

# ReportSchema
Summary
Errors
Warnings
Corrections
Statistics
