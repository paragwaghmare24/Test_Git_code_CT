import React, { useState, useRef } from 'react'
import { generateEDI, generateEDIFromFile } from '../api'
import AIAssistBar, { AITabAction } from './AIAssistBar'

const GENERATE_AI_ACTIONS: AITabAction[] = [
  { label: 'Map to EDI Segments', icon: '⊕', description: 'Help map business requirements to EDI segments', promptHint: 'Map these business requirements to EDI segments:' },
  { label: 'Validate Structure', icon: '✓', description: 'Review generated EDI for structural correctness', promptHint: 'Review this generated EDI for correctness:' },
  { label: 'Explain Segments', icon: '🔍', description: 'Explain what each segment in the output means', promptHint: 'Explain the segments in this generated EDI:' },
]

const TRANSACTION_TYPES = ['837P', '837I', '278', '834']

const FIELD_DEFS: Record<string, { label: string; required: boolean; hint?: string }[]> = {
  /* ─── 837P — Professional Claim ──────────────────────────────────────────
     Fields ordered by EDI loop / segment sequence.
     All "required" fields must be present for a valid X12 5010 837P claim.   */
  '837P': [
    // ── ISA/GS Envelope ────────────────────────────────────────────────────
    { label: 'sender_id',                  required: true,  hint: 'ISA06 — Interchange Sender ID (up to 15 chars)' },
    { label: 'receiver_id',                required: true,  hint: 'ISA08 — Interchange Receiver ID (up to 15 chars)' },
    // ── Loop 1000A / 2010AA — Billing Provider ─────────────────────────────
    { label: 'billing_provider_name',      required: true,  hint: 'NM1*85*03 — Billing Provider Organization Name' },
    { label: 'billing_provider_npi',       required: true,  hint: 'NM1*85*09 — Billing Provider 10-digit NPI' },
    { label: 'billing_provider_taxonomy',  required: true,  hint: 'PRV03 — NUCC Provider Taxonomy Code (e.g. 207Q00000X)' },
    { label: 'billing_provider_address',   required: true,  hint: 'N3*01 — Billing Provider Street Address' },
    { label: 'billing_provider_city',      required: true,  hint: 'N4*01 — Billing Provider City' },
    { label: 'billing_provider_state',     required: true,  hint: 'N4*02 — Billing Provider State (2-char)' },
    { label: 'billing_provider_zip',       required: true,  hint: 'N4*03 — Billing Provider ZIP Code' },
    // ── Loop 2010BB — Payer (CRITICAL — required for every 837) ─────────────
    { label: 'payer_id',                   required: true,  hint: 'NM1*PR*09 — Payer Identification Number (from trading partner agreement)' },
    { label: 'payer_name',                 required: true,  hint: 'NM1*PR*03 — Payer Name (insurance company name)' },
    // ── Loop 2010BA — Subscriber / Insured ─────────────────────────────────
    { label: 'subscriber_last_name',       required: true,  hint: 'NM1*IL*03 — Subscriber Last Name' },
    { label: 'subscriber_first_name',      required: true,  hint: 'NM1*IL*04 — Subscriber First Name' },
    { label: 'subscriber_id',              required: true,  hint: 'NM1*IL*09 — Subscriber Member ID (insurance card ID)' },
    { label: 'dob',                        required: true,  hint: 'DMG02 — Date of Birth YYYYMMDD (subscriber / patient)' },
    { label: 'gender',                     required: true,  hint: 'DMG03 — Gender: M=Male, F=Female, U=Unknown' },
    // ── Loop 2300 — Claim ──────────────────────────────────────────────────
    { label: 'claim_number',               required: true,  hint: 'CLM01 — Unique Claim Submitter ID (alphanumeric, ≤38 chars)' },
    { label: 'claim_amount',               required: true,  hint: 'CLM02 — Total Claim Charge Amount (e.g. 150.00)' },
    { label: 'diagnosis_code',             required: true,  hint: 'HI*ABK — Primary ICD-10-CM Diagnosis Code (no dots, e.g. Z0000)' },
    // ── Loop 2400 — Service Line ───────────────────────────────────────────
    { label: 'procedure_code',             required: true,  hint: 'SV1 — CPT/HCPCS Procedure Code (e.g. 99213)' },
    { label: 'service_date',               required: true,  hint: 'DTP*472 — Date of Service YYYYMMDD; use YYYYMMDD-YYYYMMDD for date range' },
    // ── Optional / Situational Fields ─────────────────────────────────────
    { label: 'member_id',                  required: false, hint: 'NM1*QC*09 — Patient Member ID if patient differs from subscriber' },
    { label: 'place_of_service',           required: false, hint: 'CLM05-1 — Place of Service Code (default 11=Office; 21=Inpatient; 22=Outpatient; 23=ER)' },
    { label: 'claim_frequency',            required: false, hint: 'CLM05-3 — Claim Frequency: 1=Original, 7=Replacement, 8=Void (default: 1)' },
    { label: 'insurance_type_code',        required: false, hint: 'SBR09 — Claim Filing Indicator: CI=Commercial, MB=Medicare Part B, MC=Medicaid, CH=CHAMPUS, OF=Other' },
    { label: 'group_number',               required: false, hint: 'SBR03 — Insurance Group or Policy Number' },
    { label: 'subscriber_address',         required: false, hint: 'N3*01 — Subscriber Street Address' },
    { label: 'subscriber_city',            required: false, hint: 'N4*01 — Subscriber City' },
    { label: 'subscriber_state',           required: false, hint: 'N4*02 — Subscriber State (2-char)' },
    { label: 'subscriber_zip',             required: false, hint: 'N4*03 — Subscriber ZIP Code' },
    { label: 'diagnosis_code_2',           required: false, hint: 'HI*ABF — Secondary ICD-10-CM Diagnosis Code (no dots)' },
    { label: 'diagnosis_code_3',           required: false, hint: 'HI*ABF — Tertiary ICD-10-CM Diagnosis Code (no dots)' },
    { label: 'diagnosis_code_4',           required: false, hint: 'HI*ABF — Additional ICD-10-CM Diagnosis Code (no dots)' },
    { label: 'service_line_amount',        required: false, hint: 'SV102 — Service Line Charge Amount (defaults to claim_amount)' },
    { label: 'units',                      required: false, hint: 'SV104 — Units of Service (default: 1)' },
    { label: 'modifier',                   required: false, hint: 'SV1 — Procedure Code Modifier (e.g. 25, 59, GT, 95)' },
    { label: 'diagnosis_pointer',          required: false, hint: 'SV107 — Diagnosis Code Pointer (default: 1; use 1:2 for multiple)' },
    { label: 'rendering_provider_npi',     required: false, hint: 'NM1*82*09 — Rendering Provider 10-digit NPI (if different from billing)' },
    { label: 'rendering_provider_last_name', required: false, hint: 'NM1*82*03 — Rendering Provider Last Name' },
    { label: 'authorization_number',       required: false, hint: 'REF*G1 — Prior Authorization Number' },
    { label: 'submitter_phone',            required: false, hint: 'PER*IC — Submitter Contact Phone (digits only, e.g. 5555551234)' },
  ],

  /* ─── 837I — Institutional Claim ─────────────────────────────────────────
     837I covers hospital/facility claims (UB-04 equivalent).               */
  '837I': [
    // ── ISA/GS Envelope ────────────────────────────────────────────────────
    { label: 'sender_id',                  required: true,  hint: 'ISA06 — Interchange Sender ID' },
    { label: 'receiver_id',                required: true,  hint: 'ISA08 — Interchange Receiver ID' },
    // ── Billing Provider ───────────────────────────────────────────────────
    { label: 'billing_provider_name',      required: true,  hint: 'NM1*85*03 — Billing Provider / Facility Name' },
    { label: 'billing_provider_npi',       required: true,  hint: 'NM1*85*09 — Billing Provider 10-digit NPI' },
    { label: 'billing_provider_taxonomy',  required: true,  hint: 'PRV03 — NUCC Taxonomy Code (e.g. 282N00000X=General Acute Care Hospital)' },
    { label: 'billing_provider_address',   required: true,  hint: 'N3*01 — Billing Provider Street Address' },
    { label: 'billing_provider_city',      required: true,  hint: 'N4*01 — Billing Provider City' },
    { label: 'billing_provider_state',     required: true,  hint: 'N4*02 — Billing Provider State (2-char)' },
    { label: 'billing_provider_zip',       required: true,  hint: 'N4*03 — Billing Provider ZIP Code' },
    // ── Payer ──────────────────────────────────────────────────────────────
    { label: 'payer_id',                   required: true,  hint: 'NM1*PR*09 — Payer Identification Number' },
    { label: 'payer_name',                 required: true,  hint: 'NM1*PR*03 — Payer Name' },
    // ── Subscriber ─────────────────────────────────────────────────────────
    { label: 'subscriber_last_name',       required: true,  hint: 'NM1*IL*03 — Subscriber Last Name' },
    { label: 'subscriber_first_name',      required: true,  hint: 'NM1*IL*04 — Subscriber First Name' },
    { label: 'subscriber_id',             required: true,  hint: 'NM1*IL*09 — Subscriber Member ID' },
    { label: 'dob',                        required: true,  hint: 'DMG02 — Date of Birth YYYYMMDD' },
    { label: 'gender',                     required: true,  hint: 'DMG03 — M=Male, F=Female, U=Unknown' },
    // ── Claim ──────────────────────────────────────────────────────────────
    { label: 'claim_number',               required: true,  hint: 'CLM01 — Unique Claim / Medical Record Number' },
    { label: 'claim_amount',               required: true,  hint: 'CLM02 — Total Claim Charge Amount (e.g. 5000.00)' },
    { label: 'type_of_bill',               required: true,  hint: 'CLM05-1 — UB-04 Type of Bill (3 chars: e.g. 111=Inpatient, 131=Outpatient, 141=Other)' },
    { label: 'diagnosis_code',             required: true,  hint: 'HI*ABK — Principal ICD-10-CM Diagnosis Code (no dots)' },
    { label: 'revenue_code',               required: true,  hint: 'SV201 — UB-04 Revenue Code (4 digits, e.g. 0120=Room/Board, 0450=ER, 0270=Medical/Surgical)' },
    { label: 'service_date',               required: true,  hint: 'DTP*472 — Service From Date YYYYMMDD' },
    { label: 'admission_date',             required: true,  hint: 'DTP*435 — Admission Date YYYYMMDD (required for inpatient)' },
    // ── Optional ───────────────────────────────────────────────────────────
    { label: 'member_id',                  required: false, hint: 'NM1*QC*09 — Patient Member ID if different from subscriber' },
    { label: 'admission_time',             required: false, hint: 'DTP*435 — Admission Hour HHMM, 24-hr (default: 0000 if left blank)' },
    { label: 'discharge_date',             required: false, hint: 'DTP*096 — Discharge Date YYYYMMDD (presence triggers the Discharge Hour segment)' },
    { label: 'discharge_time',             required: false, hint: 'DTP*096 — Discharge Hour HHMM, 24-hr (default: 0000 if left blank)' },
    { label: 'claim_frequency',            required: false, hint: 'CLM05-3 — 1=Admit-Discharge, 2=Interim First, 3=Interim Continuing, 4=Interim Last, 7=Replacement, 8=Void (default: 1)' },
    { label: 'insurance_type_code',        required: false, hint: 'SBR09 — Claim Filing Indicator: CI=Commercial, MB=Medicare Part B, MC=Medicaid' },
    { label: 'group_number',               required: false, hint: 'SBR03 — Insurance Group Number' },
    { label: 'subscriber_address',         required: false, hint: 'N3*01 — Subscriber Street Address' },
    { label: 'subscriber_city',            required: false, hint: 'N4*01 — Subscriber City' },
    { label: 'subscriber_state',           required: false, hint: 'N4*02 — Subscriber State (2-char)' },
    { label: 'subscriber_zip',             required: false, hint: 'N4*03 — Subscriber ZIP Code' },
    { label: 'admitting_diagnosis_code',   required: false, hint: 'HI*ABJ — Admitting ICD-10-CM Diagnosis Code (no dots)' },
    { label: 'diagnosis_code_2',           required: false, hint: 'HI*ABF — Secondary ICD-10-CM Diagnosis Code' },
    { label: 'diagnosis_code_3',           required: false, hint: 'HI*ABF — Tertiary ICD-10-CM Diagnosis Code' },
    { label: 'procedure_code',             required: false, hint: 'SV202 — ICD-10-PCS or CPT Procedure Code for service line' },
    { label: 'units',                      required: false, hint: 'SV205 — Units of Service (default: 1)' },
    { label: 'patient_status',             required: false, hint: 'CL1*01 — Discharge Status Code (e.g. 01=Home, 02=Transfer, 30=Still Patient, 20=Expired)' },
    { label: 'attending_provider_npi',     required: false, hint: 'NM1*71*09 — Attending Physician 10-digit NPI' },
    { label: 'attending_provider_last_name', required: false, hint: 'NM1*71*03 — Attending Physician Last Name' },
    { label: 'authorization_number',       required: false, hint: 'REF*G1 — Prior Authorization Number' },
    { label: 'submitter_phone',            required: false, hint: 'PER*IC — Submitter Contact Phone (digits only)' },
  ],

  /* ─── 278 — Health Care Services Review (Prior Authorization) ────────────
     278 Request is submitted by a provider to a payer for prior auth.      */
  '278': [
    // ── ISA/GS Envelope ────────────────────────────────────────────────────
    { label: 'sender_id',                  required: true,  hint: 'ISA06 — Interchange Sender ID' },
    { label: 'receiver_id',                required: true,  hint: 'ISA08 — Interchange Receiver ID' },
    // ── Loop 2010A — Utilization Management Organization (Payer) ───────────
    { label: 'payer_id',                   required: true,  hint: 'NM1*X3*09 — Utilization Management Organization / Payer ID' },
    { label: 'payer_name',                 required: true,  hint: 'NM1*X3*03 — Payer / UMO Name' },
    // ── Loop 2010B — Requestor (a person per the guide's sample) ───────────
    { label: 'requestor_last_name',         required: true,  hint: 'NM1*1P*03 — Requestor Last Name' },
    { label: 'requestor_first_name',        required: true,  hint: 'NM1*1P*04 — Requestor First Name' },
    { label: 'requestor_npi',               required: true,  hint: 'NM1*1P*09 — Requestor 10-digit NPI' },
    // ── Loop 2010C — Subscriber ────────────────────────────────────────────
    { label: 'subscriber_last_name',       required: true,  hint: 'NM1*IL*03 — Subscriber Last Name' },
    { label: 'subscriber_first_name',      required: true,  hint: 'NM1*IL*04 — Subscriber First Name' },
    { label: 'member_id',                  required: true,  hint: 'NM1*IL*09 — Subscriber Member ID' },
    // ── Loop 2000E / UM — Patient Event / Service Request ──────────────────
    { label: 'service_type',               required: true,  hint: 'UM03 — Service Type Code (e.g. 1=Medical Care, 2=Surgical, 3=Consultation, 73=Diagnostic Imaging)' },
    { label: 'service_date',               required: true,  hint: 'DTP*472 — Requested Service Date YYYYMMDD or YYYYMMDD-YYYYMMDD range (Loop 2000F)' },
    // ── Optional ───────────────────────────────────────────────────────────
    { label: 'requestor_taxonomy',          required: false, hint: 'PRV03 — Requestor NUCC Taxonomy Code' },
    { label: 'requestor_tax_id',            required: false, hint: 'REF*EI — Requestor Tax ID / EIN' },
    { label: 'subscriber_dob',             required: false, hint: 'DMG02 — Subscriber Date of Birth YYYYMMDD' },
    { label: 'subscriber_gender',          required: false, hint: 'DMG03 — Subscriber Gender: M=Male, F=Female, U=Unknown' },
    { label: 'dependent_first_name',        required: false, hint: 'NM1*QC*04 — Dependent First Name (only if patient is not the subscriber; adds Loop 2000D)' },
    { label: 'dependent_last_name',         required: false, hint: 'NM1*QC*03 — Dependent Last Name' },
    { label: 'dependent_dob',               required: false, hint: 'DMG02 — Dependent Date of Birth YYYYMMDD' },
    { label: 'dependent_gender',            required: false, hint: 'DMG03 — Dependent Gender: M=Male, F=Female, U=Unknown' },
    { label: 'request_category_code',       required: false, hint: 'UM01 — HS=Health Services Review, SC=Specialty Care Review (default: HS)' },
    { label: 'certification_type_code',     required: false, hint: 'UM02 — I=Initial, R=Renewal, S=Revised, 3=Appeal (default: I)' },
    { label: 'facility_type_code',          required: false, hint: 'UM04-1 — Place of Service Code (e.g. 11=Office, 21=Inpatient Hospital)' },
    { label: 'facility_code_qualifier',     required: false, hint: 'UM04-2 — Facility Code Qualifier (default: B)' },
    { label: 'level_of_service_code',       required: false, hint: 'UM06 — E=Emergency, U=Urgent, 03=Routine' },
    { label: 'certification_effective_date', required: false, hint: 'DTP*007 — Certification Effective Date YYYYMMDD (Loop 2000E, if distinct from service_date)' },
    { label: 'diagnosis_code',             required: false, hint: 'HI*ABF — Primary ICD-10-CM Diagnosis Code supporting the request (no dots)' },
    { label: 'procedure_code',             required: false, hint: 'SV1 — Procedure / service code being requested for authorization (CPT or HCPCS)' },
    { label: 'quantity',                   required: false, hint: 'HSD02 — Number of services / units requested (e.g. 5)' },
    { label: 'quantity_type',              required: false, hint: 'HSD03 — Unit type: DA=Days, VS=Visits, UN=Units (default: VS)' },
    { label: 'rendering_provider_npi',     required: false, hint: 'NM1*SJ*09 — Service Provider / Rendering Provider 10-digit NPI (Loop 2000E)' },
    { label: 'rendering_provider_last_name', required: false, hint: 'NM1*SJ*03 — Service Provider Last Name' },
    { label: 'authorization_number',       required: false, hint: 'REF*BB — Existing Authorization Number (for concurrent, retrospective, or appeal reviews)' },
    { label: 'action_code',                 required: false, hint: 'HCR01 — Prior decision Action Code, only for reconsideration/appeal requests referencing a known review outcome (e.g. A1=Certified, A3=Not Certified)' },
    { label: 'action_reason_code',          required: false, hint: 'HCR03 — Reason Code for the referenced action_code' },
  ],

  /* ─── 834 — Benefit Enrollment and Maintenance ───────────────────────────
     One member enrollment/maintenance record (with one health coverage)
     per generated transaction; batch multiple rows via the file-upload mode.
     NOTE: this guide has no worked EDI sample, unlike the other 3 — the
     834-specific segment layout below follows the guide's table spec plus
     well-established real-world X12 5010 834 conventions.                  */
  '834': [
    // ── ISA/GS Envelope ────────────────────────────────────────────────────
    { label: 'sender_id',                  required: true,  hint: 'ISA06 — Interchange Sender ID' },
    { label: 'receiver_id',                required: true,  hint: 'ISA08 — Interchange Receiver ID' },
    // ── Loop 1000A — Plan Sponsor ───────────────────────────────────────────
    { label: 'sponsor_name',                required: true,  hint: 'N1*P5*02 — Plan Sponsor (employer/group) Name' },
    { label: 'sponsor_ein',                 required: true,  hint: 'N1*P5*04 — Plan Sponsor Federal Tax ID / EIN' },
    // ── Loop 1000B — Payer / Insurer ────────────────────────────────────────
    { label: 'payer_name',                  required: true,  hint: 'N1*IN*02 — Payer / Insurer Name' },
    { label: 'payer_id',                    required: true,  hint: 'N1*IN*04 — Payer Federal Tax ID' },
    // ── Loop 2000 / 2100A — Member ──────────────────────────────────────────
    { label: 'subscriber_last_name',        required: true,  hint: 'NM1*IL*03 — Member Last Name' },
    { label: 'subscriber_first_name',       required: true,  hint: 'NM1*IL*04 — Member First Name' },
    { label: 'subscriber_id',               required: true,  hint: 'NM1*IL*09 / REF*0F — Member Identifier (payer-assigned ID; not necessarily an SSN)' },
    { label: 'dob',                         required: true,  hint: 'DMG02 — Member Date of Birth YYYYMMDD' },
    { label: 'gender',                      required: true,  hint: 'DMG03 — Gender: F=Female, M=Male, U=Unknown, X=Unspecified' },
    { label: 'relationship_code',           required: true,  hint: 'INS02 — Individual Relationship Code (18=Self, 01=Spouse, 19=Child, etc.)' },
    { label: 'maintenance_type_code',        required: true,  hint: 'INS03 — 001=Change, 021=Addition, 024=Termination, 025=Reinstatement, 030=Audit' },
    // ── Loop 2300 — Health Coverage ─────────────────────────────────────────
    { label: 'benefit_begin_date',          required: true,  hint: 'DTP*348 — Health Coverage Benefit Begin Date YYYYMMDD (at least one of begin/end is required)' },
    // ── Optional ─────────────────────────────────────────────────────────────
    { label: 'benefit_end_date',             required: false, hint: 'DTP*349 — Health Coverage Benefit End Date YYYYMMDD (required instead of begin date for terminations)' },
    { label: 'maintenance_reason_code',      required: false, hint: 'INS04 — Reason for the maintenance action (e.g. 01=Divorce, 02=Birth, 03=Death)' },
    { label: 'benefit_status_code',          required: false, hint: 'INS05 — A=Active, C=COBRA, S=Surviving Insured, T=TEFRA' },
    { label: 'employment_status_code',       required: false, hint: 'INS08 — FT=Full-time, PT=Part-time, AC=Active, RT=Retired, TE=Terminated' },
    { label: 'student_status_code',          required: false, hint: 'INS09 — F=Full-time Student, P=Part-time, N=Not a Student' },
    { label: 'group_number',                 required: false, hint: 'REF*1L — Group or Policy Number (member level)' },
    { label: 'enrollment_signature_date',    required: false, hint: 'DTP*300 — Enrollment Signature Date YYYYMMDD' },
    { label: 'subscriber_middle_name',       required: false, hint: 'NM1*IL*05 — Member Middle Name' },
    { label: 'member_phone',                 required: false, hint: 'PER*IP*TE — Member Telephone Number (digits only)' },
    { label: 'member_address',               required: false, hint: 'N3 — Member Street Address' },
    { label: 'member_city',                  required: false, hint: 'N4*01 — Member City' },
    { label: 'member_state',                 required: false, hint: 'N4*02 — Member State (2-char)' },
    { label: 'member_zip',                   required: false, hint: 'N4*03 — Member ZIP Code' },
    { label: 'insurance_line_code',          required: false, hint: 'HD03 — HMO, POS, or PPO' },
    { label: 'coverage_level_code',          required: false, hint: 'HD05 — EMP=Employee Only, FAM=Family, IND=Individual, ESP=Employee+Spouse, ECH=Employee+Children, etc.' },
    { label: 'plan_coverage_description',    required: false, hint: 'HD04 — Free-text Plan/Coverage Description (as directed by payer)' },
    { label: 'hd_maintenance_type_code',     required: false, hint: 'HD01 — Coverage-level maintenance code (defaults to maintenance_type_code if left blank)' },
    { label: 'health_coverage_policy_number', required: false, hint: 'REF*1L — Health Coverage Policy Number (Loop 2300)' },
    { label: 'bgn_purpose_code',             required: false, hint: 'BGN01 — 00=Original, 15=Re-Submission, 22=Information Copy (default: 00)' },
    { label: 'bgn_action_code',              required: false, hint: 'BGN08 — 2=Change, 4=Verify, RX=Replace (default: 2)' },
  ],
}

type InputMode = 'manual' | 'file'

const s: Record<string, React.CSSProperties> = {
  container: { padding: 24 },
  title: { fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#1F4E79' },
  hint: { fontSize: 11, color: '#888', marginBottom: 6 },
  card: { background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16 },
  label: { display: 'block', marginBottom: 4, fontWeight: 600, color: '#444', fontSize: 13 },
  input: { width: '100%', padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 13, marginBottom: 10, boxSizing: 'border-box' as const },
  inputError: { borderColor: '#c62828', background: '#fff8f8' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0 16px' },
  btn: { padding: '10px 28px', background: '#1F4E79', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  btnOutline: { padding: '10px 20px', background: '#fff', color: '#1F4E79', border: '2px solid #1F4E79', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 13 },
  select: { padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginBottom: 16, width: '100%' },
  pre: { background: '#1e1e1e', color: '#d4d4d4', padding: 16, borderRadius: 8, fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-all' as const, maxHeight: 400, overflow: 'auto' },
  error: { color: '#c62828', background: '#ffebee', padding: '10px 14px', borderRadius: 6, marginBottom: 8, fontSize: 13 },
  modeBar: { display: 'flex', gap: 8, marginBottom: 20 },
  modeBtn: { padding: '8px 20px', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 13, border: '2px solid #1F4E79' },
  dropZone: { border: '2px dashed #1F4E79', borderRadius: 8, padding: 32, textAlign: 'center' as const, cursor: 'pointer', color: '#555', background: '#f8fafc', marginBottom: 12 },
  dropZoneActive: { background: '#e3f0fa', borderColor: '#0d47a1' },
  fieldMissing: { display: 'inline-block', background: '#ffebee', color: '#c62828', borderRadius: 4, padding: '2px 8px', marginRight: 4, marginBottom: 4, fontSize: 12, fontWeight: 600 },
  parsedGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, marginTop: 12 },
  parsedField: { fontSize: 12, background: '#f5f5f5', padding: '6px 10px', borderRadius: 4 },
}

export default function GeneratePanel() {
  const [txType, setTxType] = useState('837P')
  const [mode, setMode] = useState<InputMode>('manual')
  const [formData, setFormData] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState('')
  const [err, setErr] = useState('')
  const [generatedResponse, setGeneratedResponse] = useState<unknown>(null)
  const [missingFields, setMissingFields] = useState<string[]>([])
  const [parsedData, setParsedData] = useState<Record<string, string> | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [batchSummary, setBatchSummary] = useState<{ total: number; generated: number; skipped: number; errors: any[] } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fields = FIELD_DEFS[txType] || []
  const requiredFields = fields.filter(f => f.required).map(f => f.label)
  const missingManual = requiredFields.filter(f => !formData[f]?.trim())

  const reset = () => { setErr(''); setResult(''); setGeneratedResponse(null); setMissingFields([]); setParsedData(null); setBatchSummary(null) }

  const runManual = async () => {
    if (missingManual.length > 0) {
      setErr(`Missing required fields: ${missingManual.join(', ')}`)
      return
    }
    setLoading(true); reset()
    try {
      const res = await generateEDI(txType, formData)
      setResult(res.data.edi); setGeneratedResponse(res.data)
    } catch (e: any) {
      setErr(e.response?.data?.detail || e.message)
    } finally { setLoading(false) }
  }

  const runFile = async () => {
    if (!uploadFile) { setErr('Please select a file first.'); return }
    setLoading(true); reset()
    try {
      const res = await generateEDIFromFile(uploadFile, txType)
      const d = res.data
      setGeneratedResponse(d)
      setParsedData(d.parsed_data || null)

      // ── Single-row missing-field error ──────────────────────────────────
      if (d.missing_fields?.length > 0 && d.total_rows === 1) {
        setMissingFields(d.missing_fields)
        setErr(d.error || 'Missing required fields.')
        return
      }

      // ── Batch result ────────────────────────────────────────────────────
      if (d.edi) {
        setResult(d.edi)
        // Store batch summary whenever the API returns count fields
        if (d.total_rows !== undefined) {
          setBatchSummary({
            total:     d.total_rows,
            generated: d.generated_count,
            skipped:   d.skipped_count ?? 0,
            errors:    d.skipped_rows  ?? [],
          })
        }
      }
    } catch (e: any) {
      setErr(e.response?.data?.detail || e.message)
    } finally { setLoading(false) }
  }

  const downloadEDI = () => {
    const blob = new Blob([result], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${txType}_generated.edi`; a.click()
    URL.revokeObjectURL(url)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) setUploadFile(f)
  }

  const downloadTemplate = () => {
    const headers = fields.map(f => f.label).join(',')
    const hints = fields.map(f => f.required ? `required${f.hint ? ' - ' + f.hint : ''}` : `optional${f.hint ? ' - ' + f.hint : ''}`).join(',')
    const blob = new Blob([headers + '\n' + hints], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${txType}_template.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={s.container}>
      <h1 style={s.title}>EDI Generation</h1>

      {/* Mode selector */}
      <div style={s.modeBar}>
        {(['manual', 'file'] as InputMode[]).map(m => (
          <button key={m}
            style={{ ...s.modeBtn, background: mode === m ? '#1F4E79' : '#fff', color: mode === m ? '#fff' : '#1F4E79' }}
            onClick={() => { setMode(m); reset() }}
          >
            {m === 'manual' ? '✎ Manual Form' : '📂 Upload Excel / JSON'}
          </button>
        ))}
      </div>

      <div style={s.card}>
        <label style={{ ...s.label, marginBottom: 8 }}>Transaction Type</label>
        <select value={txType} onChange={e => { setTxType(e.target.value); setFormData({}); reset() }} style={s.select}>
          {TRANSACTION_TYPES.map(t => <option key={t}>{t}</option>)}
        </select>

        {mode === 'manual' && (
          <>
            <div style={s.grid}>
              {fields.map(f => (
                <div key={f.label}>
                  <label style={s.label}>
                    {f.label.replace(/_/g, ' ').toUpperCase()}
                    {f.required && <span style={{ color: '#c62828' }}> *</span>}
                  </label>
                  {f.hint && <div style={s.hint}>{f.hint}</div>}
                  <input
                    value={formData[f.label] || ''}
                    onChange={e => setFormData(prev => ({ ...prev, [f.label]: e.target.value }))}
                    placeholder={f.required ? 'Required' : 'Optional'}
                    style={{ ...s.input, ...(missingManual.includes(f.label) && err ? s.inputError : {}) }}
                  />
                </div>
              ))}
            </div>
            <button style={{ ...s.btn, opacity: loading ? 0.7 : 1 }} disabled={loading} onClick={runManual}>
              {loading ? 'Generating…' : 'Generate EDI'}
            </button>
          </>
        )}

        {mode === 'file' && (
          <>
            <div
              style={{ ...s.dropZone, ...(dragOver ? s.dropZoneActive : {}) }}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <div style={{ fontSize: 28, marginBottom: 6 }}>📂</div>
              {uploadFile
                ? <><strong>{uploadFile.name}</strong><br /><span style={{ fontSize: 12, color: '#888' }}>Click or drag to replace</span></>
                : <>Drop your <strong>.xlsx</strong> or <strong>.json</strong> here, or click to browse</>
              }
            </div>
            <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.json"
              style={{ display: 'none' }}
              onChange={e => setUploadFile(e.target.files?.[0] || null)} />

            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
              <button style={{ ...s.btn, opacity: loading || !uploadFile ? 0.6 : 1 }}
                disabled={loading || !uploadFile} onClick={runFile}>
                {loading ? 'Processing…' : 'Generate EDI from File'}
              </button>
              <button style={s.btnOutline} onClick={downloadTemplate}>
                Download Template CSV
              </button>
            </div>

            <div style={{ fontSize: 12, color: '#666', background: '#f8fafc', padding: '10px 14px', borderRadius: 6 }}>
              <strong>File format:</strong><br />
              • <strong>Excel (.xlsx) — single claim:</strong> Row 1 = column headers, Row 2 = field values.<br />
              • <strong>Excel (.xlsx) — batch (multiple claims):</strong> Row 1 = column headers, Rows 2…N = one claim per row.
                All valid rows are included in a single batch EDI file. Rows with missing required fields are skipped and reported.<br />
              • <strong>JSON:</strong> Single flat object <code>{'{'}field: value{'}'}</code> or an array <code>[{'{'}...{'}'}, {'{'}...{'}'}]</code> for batch.
            </div>
          </>
        )}
      </div>

      {err && (
        <div style={s.error}>
          <strong>Error:</strong> {err}
          {missingFields.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <strong>Missing required fields:</strong><br />
              {missingFields.map(f => (
                <span key={f} style={s.fieldMissing}>{f}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {parsedData && Object.keys(parsedData).length > 0 && (
        <div style={s.card}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: '#444', marginBottom: 10 }}>Parsed Fields from File</h2>
          <div style={s.parsedGrid}>
            {Object.entries(parsedData).map(([k, v]) => (
              <div key={k} style={{ ...s.parsedField, borderLeft: `3px solid ${missingFields.includes(k) ? '#c62828' : v ? '#1F4E79' : '#bbb'}` }}>
                <strong style={{ color: '#333' }}>{k}: </strong>
                <span style={{ color: v ? '#1F4E79' : '#bbb' }}>{v || '(empty)'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Batch generation summary ── */}
      {batchSummary && (
        <div style={{ marginBottom: 12 }}>
          <div style={{
            display: 'flex', gap: 12, flexWrap: 'wrap' as const,
            background: batchSummary.skipped > 0 ? '#fff8e1' : '#e8f5e9',
            border: `1px solid ${batchSummary.skipped > 0 ? '#ffe082' : '#a5d6a7'}`,
            borderRadius: 8, padding: '10px 16px', alignItems: 'center',
          }}>
            <span style={{ fontWeight: 700, fontSize: 14, color: batchSummary.skipped > 0 ? '#e65100' : '#1b5e20' }}>
              {batchSummary.skipped > 0 ? '⚠' : '✓'} Batch Generation Complete
            </span>
            <span style={{ fontSize: 13, color: '#333' }}>
              <strong>{batchSummary.generated}</strong> of <strong>{batchSummary.total}</strong> claim{batchSummary.total !== 1 ? 's' : ''} generated
              {batchSummary.skipped > 0 && <span style={{ color: '#c62828', marginLeft: 8 }}>· {batchSummary.skipped} row{batchSummary.skipped !== 1 ? 's' : ''} skipped</span>}
            </span>
          </div>
          {batchSummary.errors.length > 0 && (
            <div style={{ background: '#ffebee', border: '1px solid #ef9a9a', borderRadius: 8, padding: '10px 14px', marginTop: 8 }}>
              <strong style={{ fontSize: 12, color: '#c62828' }}>Skipped rows — missing required fields:</strong>
              <ul style={{ margin: '6px 0 0 16px', padding: 0, fontSize: 12, color: '#b71c1c' }}>
                {batchSummary.errors.map((e: any, i: number) => (
                  <li key={i}>{e.reason}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {result && (
        <div style={s.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: '#333' }}>
            Generated EDI — deterministic result
          </h2>
            <button onClick={downloadEDI} style={{ ...s.btn, padding: '6px 16px', fontSize: 13 }}>
              Download .edi
            </button>
          </div>
          <pre style={s.pre}>{result}</pre>
        </div>
      )}

      {/* AI Assist Bar */}
      <AIAssistBar
        tabName="EDI Generation"
        sources={mode === 'file' && uploadFile ? [uploadFile] : []}
        context={JSON.stringify({ transaction_type: txType, mode, formData, parsedData, generated_edi: result, deterministic_result: generatedResponse, batchSummary, missingFields, error: err })}
        actions={GENERATE_AI_ACTIONS}
      />
    </div>
  )
}
