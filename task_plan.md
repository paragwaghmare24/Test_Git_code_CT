# task_plan.md
# EDI Accelerator Platform — Task Plan

## Protocol 0: Initialization
- [x] Discovery questions answered (2026-08-07)
- [x] DataSchema.md confirmed (pre-existing)
- [ ] Blueprint approved by user
- [ ] Companion Guide requirements reviewed
- [ ] TP Mapping requirements reviewed (deferred — no files provided yet)
- [ ] LLM.md created and approved

## Phase 1: Blueprint
- [ ] Project folder structure scaffolded
- [ ] requirements.txt defined
- [ ] package.json (React) defined

## Phase 2: Link (Connectivity Verification)
- [ ] File system access verified
- [ ] Companion Guide loader utility built and tested
- [ ] Handshake tests pass

## Phase 3: Architect — Layer 1 (Docs)
- [ ] Architecture.md up to date
- [ ] LLM.md up to date before each code change

## Phase 3: Architect — Layer 2 (Navigation / Orchestrator)
- [ ] FastAPI main.py
- [ ] Route: /generate
- [ ] Route: /parse
- [ ] Route: /validate
- [ ] Route: /compare
- [ ] Route: /correct
- [ ] Route: /analyze/999
- [ ] Route: /analyze/277ca
- [ ] Route: /export
- [ ] Route: /audit
- [ ] Route: /batch
- [ ] AI consent gate middleware

## Phase 3: Architect — Layer 3 (Tools / Services)
- [ ] EDI Generator Service
- [ ] EDI Parser Service
- [ ] EDI Validator Service
- [ ] EDI Comparator Service
- [ ] Auto Correction Service
- [ ] EDI to Excel Service
- [ ] 999 Analyzer Service
- [ ] 277CA Analyzer Service
- [ ] Reporting Service
- [ ] Audit Service
- [ ] Batch Processing Service

## Rule Engines
- [ ] HIPAA Engine
- [ ] Companion Guide Engine (reads .docx / .pdf guides)
- [ ] TP Mapping Engine (deferred until user provides TP files)
- [ ] Business Rules Engine

## Phase 4: Stylize (React Frontend)
- [ ] Dashboard
- [ ] UploadPanel
- [ ] ValidationPanel
- [ ] ComparisonPanel
- [ ] ResponsePanel (999 / 277CA)
- [ ] ExportPanel
- [ ] CompanionGuidePanel
- [ ] TPMappingPanel
- [ ] AuditPanel
- [ ] AIConsentDialog

## Phase 5: Trigger (Deployment)
- [ ] start.bat / start.sh for local machine
- [ ] README with setup steps

## Discovered Inputs
- Input types: Excel (.xlsx), CSV, JSON, Raw EDI (.edi/.x12/.txt)
- Output: Local folder + downloadable Excel
- Transactions: 837P, 837I, 278, 834, 820, 999, 277CA
- Storage: File system only
- AI: Gated by explicit user consent per invocation
- Companion Guides: 7 files in /Companion_Guide/ folder
