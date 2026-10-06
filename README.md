# EDI Accelerator Platform — README

## Overview
Healthcare EDI Accelerator built following the **B.L.A.S.T. protocol** and **A.N.T. 3-layer architecture**.

| Component | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite |
| Backend | Python 3.14 + FastAPI |
| EDI Processing | Pure Python (deterministic) |
| AI (optional) | GitHub Copilot (GHCP) — gated |
| Storage | File system only |

---

## Quick Start

### One-Click Launch (Windows)
```
Double-click: start.bat
```

### Manual Launch

**Backend:**
```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

**Frontend:**
```powershell
cd frontend
npm run dev
```

**Access:**
- UI: http://localhost:5173
- API Docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

---

## Supported Transactions
| Code | Name |
|---|---|
| 837P | Professional Claims |
| 837I | Institutional Claims |
| 278 | Prior Authorization |
| 834 | Enrollment |
| 820 | Premium Payment |
| 999 | Implementation Acknowledgment |
| 277CA | Claim Acknowledgment |

---

## Capabilities
- **Generate EDI** — 837P, 837I, 278 from structured input
- **Parse EDI** — all transaction types → structured JSON
- **Validate** — Syntax → HIPAA → Companion Guide → TP Mapping → Business Rules
- **Compare** — file-to-file field-level diff
- **Auto Correct** — propose fixes (user approval required before applying)
- **999 Analysis** — AK5/IK5 code translation
- **277CA Analysis** — STC claim status translation
- **Excel Export** — full ExcelTemplateSchema output
- **Batch Processing** — multiple files + consolidated report
- **Companion Guide Browser** — search rules from 7 loaded guides
- **TP Mapping** — upload JSON/CSV overrides
- **Audit Trail** — every action logged
- **AI Governance** — GHCP only, explicit approval per invocation

---

## Project Structure
```
EDI_TOOL/
├── backend/                  ← Python FastAPI
│   ├── main.py               ← Entry point
│   ├── api/routes/           ← API endpoints
│   ├── services/             ← Processing logic
│   ├── engines/              ← Rule engines
│   ├── models/schemas.py     ← Pydantic models
│   └── utils/                ← File handler, AI gate
├── frontend/                 ← React + TypeScript
│   └── src/components/       ← UI panels
├── Companion_Guide/          ← 7 guide files
├── data/                     ← Uploads, outputs, audit logs
├── LLM.md                    ← Project constitution
├── DataSchema.md             ← Data schemas
├── task_plan.md              ← Build plan
├── progress.md               ← Status tracker
└── start.bat                 ← One-click launcher
```

---

## AI Rules
- AI is **disabled by default**
- Only **GitHub Copilot (GHCP)** models are permitted
- Every AI invocation requires **explicit per-action user approval**
- OpenAI API, Azure OpenAI, Gemini, Anthropic — **strictly prohibited**
- All AI actions are **logged in the audit trail**

---

## Companion Guides
Located in `Companion_Guide/`:
- 837P_Companion_Guide.docx
- 837I_Companion_Guide.docx
- 278_Companion_Guide.docx
- EDI_834_Companion_Guide.docx
- 820_Version_ 218_Companion_Guide.docx
- X12 HIPAA 277CA (PDF)
- X12 HIPAA 999 (PDF)

---

## Invariants (LLM.md)
1. Companion Guide is ALWAYS the primary rule source
2. AI NEVER runs without explicit user approval
3. Data is NEVER assumed or fabricated
4. Every action is auditable
5. Corrections are NEVER applied without user approval
6. Only GHCP models are permitted
7. File system is the only persistence mechanism
