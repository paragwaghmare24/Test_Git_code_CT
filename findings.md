# findings.md
# EDI Accelerator Platform — Findings Log

## 2026-08-07 — Initial Discovery

### Confirmed Facts
- Project Root: c:\Users\ParagW4.MUMBAI1\Documents\EDI FILE Generator\EDI_TOOL
- Companion Guides present (7 files):
  - 278_Companion_Guide.docx
  - 820_Version_218_Companion_Guide.docx
  - 837I_Companion_Guide.docx
  - 837P_Companion_Guide.docx
  - EDI_834_Companion_Guide.docx
  - X12 HIPAA 277 Claim Acknowledgement (X214).pdf
  - X12 HIPAA 999 Implementation Acknowledgment (X231).pdf
- DataSchema.md pre-defined (all schemas confirmed)
- ExcelTemplateSchema.md pre-defined (Master Output Template confirmed)
- No Trading Partner mapping files provided yet (TP Mapping Engine will be built, but deferred until user provides files)
- No database required — file system only

### Open Questions
- None at this stage. All discovery questions answered.
- Companion Guide rule extraction will be handled programmatically via the Companion Guide Engine (docx/pdf reader).

### Risks
- .docx and .pdf companion guides require parsing libraries (python-docx, pdfplumber) — must be verified in Phase 2 Link.
- React frontend requires Node.js installed on local machine — must verify during Phase 5.

### Decisions Made
- AI mode: both Mode 1 and Mode 2 supported; AI requires explicit per-invocation user approval.
- Storage: file system only (JSON/Excel output files, no SQLite or database).
- All 7 transaction types are equal priority.

## 2026-09-30 — Full Companion Guide vs. Codebase Audit

Trigger: user reported generated 837P missing BHT segment. Root cause fixed, then a full
text-verified audit of all 7 Companion Guides against generator/validator/analyzer code was
performed per user request. Guide text was extracted verbatim using the app's own
python-docx/pdfplumber code (not simulated) into plain text for line-by-line comparison.

### Fixed this session (approved, low-risk, already applied)
1. **BHT segment was completely missing from 837P and 837I generation.**
   `_build_837p_body()` / `_build_837i_body()` in `backend/services/edi_generator.py` never
   emitted a BHT segment. Guide sample data for both transactions confirms the correct form:
   `BHT*0019*00*<ref>*<date>*<time>*CH` (837P) / `...*RP` (837I, response context).
   Fix: added BHT construction as the first statement of both body builders, auto-generating
   BHT03 the same way other control numbers are auto-generated (no new required user field).
2. **Dead/duplicate code removed** from `generate_837p()` — a full manual segment list (Loop
   1000A/1000B/2000A/2000B) was built and then immediately discarded/overwritten by
   `segments = _build_837p_body(data)` on the next line. Removed; a duplicated banner comment
   above `_build_837p_body()` was also cleaned up.
   Verified: `get_errors` clean, and a full manual generation run for both 837P/837I confirms
   BHT now appears correctly right after ST, with correct auto-computed SE counts.

### 837P — new confirmed issue (NOT fixed — awaiting confirmation)
- **NM1\*40 (Receiver) qualifier is hardcoded `46`, but the 837P guide requires `PR`.**
  Guide table: "1000B NM108 Identification Code Qualifier — PR" (accept only PR for 837P).
  Current generator emits `NM1*40*2*<name>****46*<id>` for BOTH 837P and 837I (same
  hardcoded line reused). It happens to be correct for 837I (which really does require `46`)
  but wrong for 837P. Confirmed via generated output and guide text side by side.
  Impact: every generated 837P file fails this element under the codebase's own
  `_NM1_RULES_BY_TX["837P"]["40"]` validation rule (which is already correctly set to `{"PR"}`)
  — i.e. the tool's own validator would flag the tool's own generator output.

### 837P / 837I — informational (guide self-contradiction, not blocking)
- Guide's descriptive table lists BHT01 = `0022`, but the guide's own worked sample for both
  837P and 837I shows `BHT*0019*...`. `0022` is not a valid X12 hierarchical-structure code for
  837 at all (external code list only defines `0019` for this transaction), so this looks like
  a typo in the guide's table. Implemented value (`0019`) matches the guide's own sample,
  `smoke_test.py`'s fixture, and `ai_operations.py`'s reference data — convergent evidence.
  Flagging for awareness only.

### 837I — new confirmed issue (NOT fixed — needs a decision)
- **Version identifier mismatch:** generator uses `005010X223A2` for GS08/ST03, but this
  guide's own sample explicitly shows `005010X223A1` (`ST*837*0001*005010X223A1~`, and the
  guide's table also states `005010X223A1`). X223A2 is the modern HIPAA-mandated production
  version (X223A1 was superseded industry-wide); the guide itself may simply be outdated.
  Need a decision: follow this guide's literal text, or keep the current
  production-standard value. Not changed pending your answer.

### 278 — extensive confirmed issues (NOT fixed — substantial scope, awaiting direction)
Guide text reveals `_build_278_body()` diverges from the real 278 companion guide far beyond
the BHT06/HL03 items flagged previously:
1. `GS01` = `"HS"` in code; guide sample shows `"HI"` (Health Care Services Review Information).
2. `BHT06` = `"RQ"` in code (previous guess was "RU" — also wrong); guide's worked sample
   actually uses `"18"`. The guide's own BHT table oddly has no row for BHT06 at all.
3. `NM1*X3` (UMO/Payer) — code always emits qualifier `PI`; guide table says `PI` too, but the
   guide's own sample shows qualifier `24` with a **blank** NM109. Likely the sample is a
   redacted placeholder rather than a real contradiction, but flagging since it's ambiguous.
4. `NM1*1P` (Requestor) — code always emits entity type `2` (organization) using a single
   `billing_provider_name` field. Guide's sample models the requestor as a **person**
   (entity type `1`) with separate last/first name (`NM1*1P*1*Lastname*Firstname****XX*id`).
   This is a data-model gap, not just a value fix — there is no first/last name field for the
   278 requestor today.
5. `PRV` segment (billing provider taxonomy) emitted by code — does not appear anywhere in the
   278 guide's segment table at all; looks like it may not belong in this transaction/guide.
6. `HL*4` (Patient Event level) — code emits `HL03="PT"`, which never appears in the guide.
   Guide's sample clearly uses `HL03="EV"`. Also code emits `HL04="0"` (no children) but the
   guide's hierarchy has a child loop beneath this level, so `HL04` should be `"1"`.
7. **Entire 2000F "Service Level" HL loop is missing.** The real 278 structure has TWO
   service-related hierarchy levels — 2000E (Patient Event, `HL03=EV`) and a child 2000F
   (Service Level, `HL03=SS`) — each with its own `TRN`, `UM`, `HCR`, `DTP`, and (at 2000F)
   `SV1`/`SV2`/`HSD`. The current generator conflates everything into a single HL and never
   emits `TRN` or `HCR` at all.
8. `UM` segment construction looks malformed — a raw service date string is concatenated into
   what should be a Facility Type Code composite position (`UM*SC*I*{type}***{date}:*1`),
   which does not match the guide's `UM01/UM02/UM03/UM04/UM06` layout.
9. `DTP*435` (used by code for "admission date") does not appear anywhere in the 278 guide;
   the guide instead documents `DTP*007` (certification/effective date, 2000E) and `DTP*472`
   (service date, 2000F). `DTP*435` appears to be an unrelated carryover from 837I.
10. `REF*BB` (authorization number) — `BB` is not a documented REF qualifier anywhere in this
    guide (guide only documents `EI`, `ZH` at 2010B/2010EA and `EJ` at 2010C). The guide's
    sample instead carries a trace/authorization number in `TRN02`, which the generator never
    emits at all (see item 7).
11. `HI*BF:{code}` (diagnosis) — guide's HI01-1 qualifier list for this transaction is
    `ABF`/`ABJ`/`ABK`, not `BF`. The guide's sample also shows a 4-part composite
    (`HI*ABK:R51.9:D8:20220815~` — qualifier:code:date-qualifier:decision-date), which is more
    complex than the current 2-part `HI*BF:{dx}`.

Given the number and nature of these gaps (missing loops/segments, wrong qualifiers throughout,
a data-model change needed for requestor name), fixing 278 properly is a **redesign**, not a
patch. Not touched pending your direction on scope/priority.

### 834 — confirmed issues in the validation rule table (no generator exists for 834)
`_DTP_RULES_BY_TX["834"]` in `companion_guide_engine.py` has several qualifier descriptions
that don't match the actual guide text:
- `300` labeled "Enrollment / Benefit Date" — guide says "Enrollment **Signature** Date".
- `336` labeled "Benefit Begin Date" — guide says "**Employment** Begin" (nothing to do with
  benefits).
- `348` labeled "Maintenance Effective Date" — guide says `348` = "**Benefit Begin**";
  "Maintenance Effective" is actually qualifier `303` (not present in our table at all).
- `357` labeled "Benefit End Date" — guide says "**Eligibility** End"; the real "Benefit End" is
  qualifier `349` (also not present in our table).
- Loop id `"2700"` used for several entries does not appear anywhere in the extracted guide
  text (the guide only shows loops `2000` and `2300` for these qualifiers).
- Several guide-documented qualifiers are simply missing from the table (`301`, `303`, `338`,
  `339`, `349`, `356`, `385`, `386`, `473`, `474`, etc.)
Impact: validating an uploaded 834 file against these qualifiers produces mislabeled
descriptions in error/inspector output. Moderate impact (no generator exists yet, so this only
affects the "validate an uploaded 834" path).

### 820 — structural note + guide self-contradiction (no generator exists for 820)
- The guide's prose says control values include "ISA-IEA, GS-GE, **BHT**, and ST-SE" — but the
  guide's own worked sample shows **no BHT segment at all**; ST is immediately followed by
  `BPR` (Financial Information). If an 820 generator is ever built, it must **not** include a
  BHT segment.
- The guide's own GS01 table says `"RA"` (Payment Order/Remittance Advice), but the guide's own
  sample shows `GS*HS*...` (`"HS"`) — another internal table-vs-sample contradiction.
- `_DTP_RULES_BY_TX["820"]` is currently an empty dict with a note that 820 has minimal DTP use
  — this is appropriately conservative, not a bug.

### 999 — confirmed code-table bug in `analyzer_999.py`
- `_AK5_ERROR_CODES` (used for the AK502/IK502 "Transaction Set Syntax Error Code", X12 code
  list 618) has incorrect descriptions for codes `15`, `16`, `18`, `19` (confirmed by direct
  comparison with the guide's own text and a full worked AK9/IK5/IK3/IK4 sample). Guide-real
  values: `15`=Unknown Security Originator, `16`=Syntax Error in Decrypted Text,
  `18`=Transaction Set not in Functional Group, `19`=Invalid Transaction Set Implementation
  Convention Reference. Codes `20`–`22` and `28`–`30` in our table do not correspond to code
  list 618 at all per the guide (that list has no entries in those ranges) and appear to have
  been sourced from a different/unrelated list. Guide-documented codes `23`–`27` (S3E/S3S/S4E/
  S4S security-segment errors) are missing from our table entirely (would show as "Unknown
  code" today).
  Codes `1`–`13` and `17` were verified correct.
- Separately (not a bug, a completeness gap): IK502 can repeat up to `IK506` (5 possible error
  codes per transaction set per spec), but the analyzer only reads the first occurrence
  (`parts[2]`).
- AK3/AK4/IK4/AK9 segment **position parsing** was independently verified correct against a
  full worked example from the guide (`AK3*CLM*22**8~` / `IK4*2*782*1~` / `AK9*P*3*3*1~` all
  decode exactly as expected). Only the AK502 code-value table itself needs correction.

### 277CA — flagged for independent verification (lower confidence)
- `_STC_CATEGORY_CODES` (`A0`–`A8`) values look shifted relative to the standard published X12
  "Code Source 507" list based on general X12 domain knowledge — e.g. this codebase's `A0` =
  "Received, but not in process" and `A2` = "Forwarded to third party", whereas the standard
  507 list defines `A0` = "Forwarded" and `A2` = "Accepted into adjudication system", etc.
  **This could not be verified directly against the extracted guide text** — the Stedi guide
  only references "Code Source 507" / "Code Source 508" by name and does not reproduce the
  actual code values inline. Recommend checking against the official Washington Publishing
  Company code list before treating this as confirmed; flagged here as a probable issue, not a
  certainty.
- `STC03` (transmission-level Accept/Reject action code, `U`/`WQ`) and the optional `STC10`/
  `STC11` supplementary status composites are not parsed by `analyzer_277ca.py` at all
  (completeness gap, not necessarily wrong — `STC10`/`STC11` are explicitly optional per guide).

### Cross-cutting findings
1. **VR-06 ("all mandatory loops/segments per guide must be present") is not actually enforced.**
   The heuristic mandatory-segment extraction (`_extract_rules_from_text` / Pass 1 of
   `validate_against_guide()` in `companion_guide_engine.py`) cannot produce usable rules from
   these guides' tabular (Loop | Segment | Name | Values | Notes) format — matches on
   MUST/REQUIRED keywords exist but the segment code lives in a different table cell, so
   extracted rules end up with an empty `segment` field. This affects validation for all 7
   transaction types, not just one.
2. **docx table extraction does not preserve row/column structure for merged cells.** Plain
   `cell.text` concatenation can misattribute a "Loop ID" to the wrong following segment rows
   (observed while cross-checking the 834 guide). This affects confidence in any rule
   hand-transcribed from these docx tables, including some existing hand-curated ones.
3. **Several guide source documents self-contradict** between their descriptive tables and
   their own worked sample data (837P/837I BHT01: `0022` vs `0019`; 820 GS01: `RA` vs `HS`;
   278 several table-vs-sample gaps). "Companion Guide is primary source of truth" (AR-09) is
   ambiguous when a single document disagrees with itself. No blanket rule was applied without
   asking — see open questions below.
4. **PDF extraction quality issue specific to the two Stedi PDF guides (999, 277CA):**
   pdfplumber systematically drops most instances of the letter "l" in these two documents
   (e.g. "Faied" for "Failed", "impementation" for "implementation") — a font/ligature decoding
   quirk specific to these PDFs. Values were still identifiable from context, but any future
   automated keyword-based extraction from these two PDFs specifically would see corrupted
   text. The five .docx guides did not have this problem.
5. **834 and 820 are listed as "Supported Transactions" in `LLM.md` but have no generator at
   all** — `_GENERATORS`/`_BATCH_CONFIG` in `edi_generator.py` only implement 837P/837I/278.
   Only partial validation-side rule tables exist for 834/820. Needs a scope decision.

### Open Questions (please advise before further implementation)
1. **BHT01 (837P/837I):** guide table says `0022`, sample says `0019`; I implemented `0019`
   (matches sample + existing codebase convention). Confirm this is acceptable.
2. **837I version identifier:** guide literally says `005010X223A1`; code currently uses the
   modern production-mandated `005010X223A2`. Which should the tool follow?
3. **278 generator:** given the scope (missing 2000F loop, missing TRN/HCR, wrong qualifiers
   throughout, new required data field for requestor first/last name), do you want a full
   redesign now, and if so, what priority relative to other work?
4. **834 / 820 generators:** currently not implemented at all. In scope for this cycle, or
   intentionally validation-only?
5. **278 NM1\*X3 qualifier:** guide table says `PI`; guide's own sample shows `24` with blank
   NM109 (likely a redacted placeholder). Treat the table (`PI`) as authoritative?
6. ~~**Immediate low-risk fixes**~~ — **superseded, see 2026-09-30 update below: all
   narrowly-scoped, well-evidenced, no-new-fields corrections have now been implemented.**
   (Note: this item as originally worded said "837P `NM1*40` qualifier `46`→`PR`", which had the
   direction backwards — see correction below: the fix applied was the opposite, `PR`→`46`.)

---

## 2026-09-30 — Deep Segment-Level Audit (837P/837I/278) + Fixes Applied

Per your instruction to check for further mismatches and proceed with unambiguous fixes, I did
a full segment-by-segment re-read of the 837P and 837I guides (tables **and** worked samples,
start to finish) against the exact current generator code. This surfaced **8 additional
confirmed issues** beyond the original list above, plus **one correction to an earlier
finding**. All unambiguous items have been fixed and verified (see "Fixes applied" below);
genuinely ambiguous ones are listed as new open questions.

### Correction to an earlier finding
**837P `NM1*40` (Receiver) qualifier — direction reversed.** The original report above said the
generator's `46` was wrong and should be `PR`. Having now read the guide's full worked sample
(not just its descriptive table), the sample itself uses `NM1*40*2*PLAN*****46*77048~` — i.e.
`46`, not `PR`. Additionally, `PR` is not a valid X12 ID Code Qualifier (Code List 66) at all —
it is normally an *Entity Identifier Code* (used in `NM101`, e.g. `NM1*PR` = Payer), so its
appearance in the guide's `NM108` table row looks like a transcription slip. The 837I guide's
own validator rule already correctly uses `46` for the same loop, which corroborates this.
**Conclusion: the generator (`46`) was already correct; the bug was in the validator's 837P
rule (`PR`), which has now been fixed to `46`.**

### New confirmed issues found (all now fixed)
1. **`PER02` (Submitter contact name) incorrectly repeated the billing-provider name** —
   `PER*IC*<name>*TE*<phone>` — instead of being left blank as the guide's own sample shows
   (`PER*IC**TE*5556009932~`). Fixed in both 837P and 837I.
2. **Missing `REF*EI` (Billing Provider Tax ID)** in Loop 2010AA — documented in both the
   guide's table and its sample (`REF*EI*050505050~`) immediately after the billing provider
   `N4`, but never emitted. Added as an optional segment (new optional field
   `billing_provider_tax_id`) to both 837P and 837I.
3. **837P `SV1` diagnosis-code-pointer landed in the wrong element.** The code emitted
   `SV1*...*UN*<units>**<pointer>` (one blank element), placing the pointer in `SV106`. The
   guide explicitly documents the pointer as composite `SV107`/`C004`, which needs **two** blank
   elements after quantity, confirmed against the sample's `SV1*HC:99214*70*UN*1***1~` (three
   `*` between quantity and pointer). Fixed by adding the missing blank element. This is a
   structural bug that affected every 837P service line generated.
4. **837I `CL1` (Institutional Claim Code) had the patient-status value in the wrong element.**
   Code emitted `CL1*<patient_status>*1*01`, putting the caller's `patient_status` value in
   `CL101` (which is actually *Admission Type Code*) and fabricating `1`/`01` placeholders with
   no basis. Guide confirms `CL103` is *Patient Status Code*. Fixed to
   `CL1**<admission_source_if_any>*<patient_status>` — `patient_status` now lands correctly in
   `CL103`; `CL101`/`CL102` are left blank rather than fabricated (no field collects them today).
5. **837I unconditionally generated Loop 2000C (Patient), always using the subscriber's own
   data as a fake "patient" with a hardcoded `PAT*19` (Child) relationship.** Per X12 rules,
   Loop 2000C only exists when the patient is a *dependent* distinct from the subscriber — which
   this data model has never actually collected (no separate patient name/relationship fields
   exist). The guide's own worked sample also has no Loop 2000C at all; it goes straight from
   the subscriber's `NM1*PR` (Payer) to `CLM`. Removed the loop entirely (also corrected the
   preceding `HL*2` segment's HL04 from `1`→`0` since it no longer has a child level), bringing
   837I's structure in line with 837P's (which never had this bug) and with the guide's sample.
6. **Missing `DTP*434` (Statement From/To Dates)** — guide-documented (`RD8` format,
   `CCYYMMDD-CCYYMMDD`) but never emitted by 837I. Added as optional (new optional fields
   `statement_from_date` / `statement_to_date`).
7. **278: `GS01` was `HS`, guide's own sample uses `HI`.** Fixed (also fixed in `_BATCH_CONFIG`).
8. **278: `BHT06` was `RQ`, which appears nowhere in the guide; the guide's sample uses `18`.**
   Fixed. **278: `HL03`/`HL04` for the service-level HL was `PT*0`; guide's hierarchy uses
   `EV*1`** (Patient Event level, with a child — the 2000F Service loop — that is not yet
   implemented; see open question below). Fixed the level code/child-indicator; the missing
   2000F loop itself remains part of the larger 278 redesign question. **278: `HI*BF:<code>`
   qualifier `BF` isn't a valid HI01-1 code; guide's list is `ABF`/`ABJ`/`ABK`.** Fixed to `ABF`.
9. **834 DTP qualifier table (`companion_guide_engine.py`) was substantially wrong** — I
   re-verified every qualifier directly against the guide's four DTP tables (loops 2000E, 2000,
   2200, 2300, 2750) rather than relying on the earlier summary. Corrected descriptions for
   `300`, `336`, `348`, `357` (as previously reported) **and** added 15 previously-missing but
   guide-documented qualifiers (`301`, `303`, `337`, `338`, `339`, `340`, `341`, `356`, `360`,
   `361`, `385`, `386`, `473`, `474`, `343`, `543`, `695`), replacing the incorrect `"2700"` loop
   ID with the guide-confirmed `2000`/`2200`/`2300`/`2000E` loop IDs.
10. **999 AK502 error-code table (`analyzer_999.py`) fully corrected** against the guide's
    Code List 618: removed 8 fabricated entries (`14` never existed; `20`–`22`, `28`–`30` had
    invented descriptions), corrected `15`/`16`/`18`/`19` (were shifted/wrong), and added the
    real `23`–`27` and `I5`/`I6` codes.

### Fixes applied (summary)
- [backend/services/edi_generator.py](backend/services/edi_generator.py) — items 1–8 above.
- [backend/engines/companion_guide_engine.py](backend/engines/companion_guide_engine.py) — 837P
  `NM1*40` correction, 834 DTP table (item 9).
- [backend/services/analyzer_999.py](backend/services/analyzer_999.py) — AK502 table (item 10).
- Verified: `get_errors` clean on all 3 files; manual generation smoke test for 837P/837I/278
  confirms correct segment content/positions (blank `PER02`, `REF*EI` present, `SV1` pointer in
  `SV107`, `CL1` patient-status in `CL103`, no Loop 2000C in 837I, 278 `GS*HI*`/`BHT*...*18`/
  `HL*4*3*EV*1`).

### New open questions (genuinely ambiguous — not assumed, need your direction)
1. **837I `DTP*435` (Admission Date/Hour) and `DTP*096` (Discharge Hour) format mismatch.** The
   validator already correctly documents these as `DT` (`CCYYMMDDHHMM`) and `TM` (`HHMM`)
   respectively (someone had already researched this), but the **generator** emits both with
   `D8` (date-only) using the existing `admission_date`/`discharge_date` fields, which only ever
   hold an 8-digit date, not a date+time or time-only value. I did not change the generator's
   format here because doing so would either (a) require collecting real admission/discharge
   *time* values (new fields, not currently gathered anywhere), or (b) silently pad a fake
   `0000` time onto real dates, which conflicts with the No-Assumption-Rule (PR-01). How would
   you like this handled — add `admission_time`/`discharge_time` fields, pad with `0000`, or
   leave as `D8` and accept the compliance gap for now?
2. **277CA STC category/status codes** — I flagged specific STC values as possibly wrong in the
   original report, but I could not verify this because the guide document itself only
   references external Code Sources 507/508 rather than reproducing the actual values. My
   proposed corrections are based on general X12 domain knowledge, not this specific guide's
   text. Do you want me to apply them on that basis, or leave as-is until a source that actually
   lists the codes can be verified?
3. **837I guide's worked sample appears to be a mislabeled copy of the 837P sample** (it uses
   `SV1` instead of `SV2`, has no revenue code, no type-of-bill, no Loop 2000C or 2310 A–F
   institutional provider loops). This means everywhere I relied on "the guide's sample" for
   837I-specific structure, I was actually only able to cross-check against the *table* section,
   not a genuine institutional example. Flagging this so you're aware the 837I sample section of
   this guide should not be trusted as authoritative — worth requesting a corrected guide from
   the source if possible.
4. Still open from the original list: BHT01 `0022` vs `0019` (informational only, no action
   needed), 837I version identifier (`005010X223A1` vs `005010X223A2`), full 278 redesign scope,
   834/820 generator scope, 278 `NM1*X3` qualifier.

---

## 2026-09-30 — Open Questions 1 & 2 Resolved + Real-World 837I Sample Cross-Check

### 1. 837I `DTP*435`/`DTP*096` format — resolved
Decision: add optional `admission_time`/`discharge_time` fields (HHMM) rather than leave the
`D8` compliance gap. Implemented in
[backend/services/edi_generator.py](backend/services/edi_generator.py) `_build_837i_body()`:
`DTP*435*DT*{admission_date}{admission_time or "0000"}` (12-digit `CCYYMMDDHHMM`) and, when
`discharge_date` or `discharge_time` is present, `DTP*096*TM*{discharge_time or "0000"}`
(4-digit `HHMM`). Both new fields are optional and default to `"0000"` — no new required input,
no compliance gap, and no fabricated *business* data (the padding is a formatting convention for
an unknown hour, not an invented date/value). Added both fields to the frontend 837I form
([frontend/src/components/GeneratePanel.tsx](frontend/src/components/GeneratePanel.tsx)) so
users can supply a real hour when known. Verified with a smoke test (default-padding case and
explicit-time case both produce correctly formatted segments).

### 2. 277CA STC codes — resolved, verified against the official X12 source
Rather than rely purely on memory, the actual current **X12 External Code Lists** were fetched
from x12.org (successor to the Washington Publishing Company lists) — Code Source 507 (Claim
Status Category Codes) and Code Source 508 (Claim Status Codes). This confirmed the original
finding: the codebase's tables were **not a shifted/approximate version of the real list, but
almost entirely fabricated** (e.g. old `"19": "Claim adjusted"` vs. the real, official
`"19": "Entity acknowledges receipt of claim/encounter"` — unrelated meanings).
`_STC_CATEGORY_CODES` was fully replaced with the verified Code Source 507 list (A0–A8, P0–P5,
F0–F4/F3F/F3N, R0–R8, E0–E3, D0). `_STC_STATUS_CODES` was replaced with a verified ~45-entry
subset of Code Source 508 (which has 400+ total entries) covering the codes most relevant to
claim-acknowledgment scenarios (entity acknowledgment chain, duplicates, timely filing, missing/

---

## 2026-09-30 — 278 Full Redesign + New 834 Generator

User resolved the 4 remaining open questions from the prior section: BHT01 → **keep `0019`**
(no code change — the codebase's existing value already matched the real production 837I file
checked last round), 837I version → **keep `005010X223A2`** (same reasoning), 278 → **full
redesign now**, 834/820 → **build 834 only** (820 explicitly out of scope this round).

### 278 — full redesign
Re-read the entire `278.txt` companion guide (1012 lines), including all 3 worked samples
(Request / Request-for-Review / Response — nearly identical structure). The guide's own sample
proved the existing generator had the Requestor entity type wrong, and revealed an entire missing
loop. Rewrote `_build_278_body()` in
[backend/services/edi_generator.py](backend/services/edi_generator.py):

- **`NM1*1P` (Requestor) fixed**: was entity-type `2` (non-person) reusing a single
  `billing_provider_name` field; the guide's sample shows `NM1*1P*1*Lastname*Firstname` — a
  **person** with separate last/first names. New required fields `requestor_last_name` /
  `requestor_first_name` / `requestor_npi` replace `billing_provider_name` /
  `billing_provider_npi` for this transaction type (deliberate breaking rename — the old fields
  were provably wrong, not merely incomplete).
- **Loop 2000F (Service) added** — was entirely missing. Now includes its own `HL`, `TRN`, `UM`,
  optional `HCR`, `DTP*472`, optional `HSD`, optional `REF*BB`, and `SV1`. This also activates the
  `procedure_code` field, which already existed in the frontend form but the old generator never
  emitted it.
- **`TRN` (trace number)** added at both 2000E and 2000F — previously absent everywhere.
- **Optional Loop 2000D (Dependent)** added — only appears if `dependent_first_name` /
  `dependent_last_name` is supplied. HL segment numbering is now tracked dynamically (not
  hardcoded) since inserting 2000D shifts every subsequent HL id.
- **`BHT05` (time) fixed** from `HHMM` to `HHMMSS` — the 278 guide explicitly specifies a 6-digit
  time, unlike the other guides which use 4-digit `HHMM`.
- **`UM` rebuilt as a proper composite**: `UM01` request category (default `HS`), `UM02`
  certification type (default `I`), `UM03` service type (existing field), `UM04` facility
  composite `type:qualifier` (default qualifier `B`), `UM06` level of service — the old code had a
  single malformed one-line `UM` segment.
- **`HCR` (action code) kept optional/conditional** — only emitted if the caller explicitly
  supplies `action_code`, even though all 3 guide samples include it. Reasoning: for a genuine new
  request the submitter cannot know the payer's decision yet (the guide's own samples including it
  is most plausibly a copy/paste artifact); this also supports the real reconsideration/appeal
  workflow, where a known prior decision *is* legitimately referenced.
- **`NM1*X3` (payer) qualifier** — confirmed **keep `PI`** (resolves a previously open question).
  The validator already accepts both `PI`/`24`; the guide's table says `PI` and the sample's
  blank-name-associated `24` isn't reliable contrary evidence this time (different from the
  `NM1*40` case from the prior round, where the table's value failed a basic code-validity check).

`_REQUIRED_FIELDS["278"]`, `generate_278()`, and the frontend `GeneratePanel.tsx` '278' field
list were all updated to match. Verified with `get_errors` (clean) and terminal smoke tests
(basic case; and a second case exercising date-range, dependent loop, facility composite, and
action_code together) — segment element positions double-checked via a `split('*')` index dump.

### 834 — new generator
Guide (`834.txt`, 1875 lines) researched via a dedicated research pass given its size.
**Critical finding: unlike the other 4 guides used in this project, this one has table
specifications only — no worked EDI sample anywhere in the text.** `generate_834()` /
`_build_834_body()` were implemented from the table spec plus well-established real-world X12
5010 834 conventions — `GS01="BE"` and `GS08`/`ST03="005010X220A1"` are **not literally confirmed
by this guide's own text** (flagged in code comments), applying the "X12 general knowledge, if
trustworthy" latitude the user granted this round.

Scope: **one member enrollment/maintenance record with one health-coverage (`HD`) segment per
call** — the same single-record-per-call pattern already used by 837P/837I/278 (batch multiple
records via `generate_batch()`). Loops deliberately **not** modeled, since the guide marks them
optional/situational and this data model doesn't collect the fields they'd need: Loop 1000C
(TPA/Broker) + 1100C, Loop 2100C (mailing address) + 2200 (disability), Loop 2310 (provider), Loop
2100F/2100G (custodial parent / responsible person), and multiple simultaneous coverages
(medical+dental+vision) per member.

Notable design decisions:
- `INS01` (subscriber Y/N) is **derived** from `relationship_code == "18"` rather than a separate
  field that could contradict it.
- `NM108` (member ID qualifier) defaults to `ZZ` (Mutually Defined / payer-assigned ID), not `34`
  (SSN) — a safer default that doesn't presume the caller is submitting a Social Security Number.
- `HD01` (coverage-level maintenance code) defaults to the member's own `maintenance_type_code`
  rather than a hardcoded guess — adding a member typically means adding their coverage too.
- Enforced "at least one of `benefit_begin_date` / `benefit_end_date` required" (guide: `DTP*348`
  or `DTP*349`) as a custom check inside `generate_834()`. (Batch mode only hard-requires
  `benefit_begin_date` via the flat `_REQUIRED_FIELDS` list — consistent with how batch mode
  already only validates that flat list, not any custom in-function logic, for every other
  transaction type too; not a new gap introduced here.)
- Used `"*".join([...])` list construction instead of hand-counted f-string asterisks for
  segments with 3+ blank elements (`BGN`, `INS`, `NM1`, `HD`) — specifically to avoid the
  off-by-one blank-element bugs found earlier this session in `SV1`/`CL1`.

Registered in `_GENERATORS` / `_REQUIRED_FIELDS` / `_BATCH_CONFIG`; added `'834'` to the frontend
`TRANSACTION_TYPES` array plus a full `FIELD_DEFS['834']` entry. No backend API route changes were
needed — the routes pass `transaction_type` through generically with no hardcoded whitelist.
Verified with `get_errors` (clean) and a terminal smoke test, including a `split('*')` index dump
confirming exact segment element positions.

**820 was explicitly declared out of scope by the user this round — not touched.**
invalid info, eligibility, format/version errors). Codes outside this curated subset still fall
back gracefully to `"Status '<code>'"` (unchanged existing behavior in `_parse_stc`) rather than
showing a wrong guess — this was deemed safer than fabricating coverage for all 400+ codes.
Verified with a smoke test confirming correct lookups.

### Real-world 837I sample cross-check (`Input/837I.txt`, user-supplied production file)
Used to empirically settle two of the remaining open questions and surfaced a few new
observations:
- **Confirms `BHT01=0019`** (`BHT*0019*00*...*CH`) — matches the codebase's existing choice over
  the guide table's `0022`.
- **Confirms version `005010X223A2`** in both `GS08` and `ST03` — matches the codebase's current
  default over the guide's literal `005010X223A1`.
- **Confirms the `CL1` fix**: real file uses `CL1*9*9*01` — patient status `01` in `CL103`,
  consistent with the fix applied earlier this cycle.
- **Confirms `REF*EI`** (billing provider tax ID) and **`DTP*434`** (statement dates) are both
  present in the real file, consistent with fixes already applied.
- **New observation (not yet acted on):** the real file has no `DTP*435`/`DTP*096` at all,
  suggesting admission/discharge date-hour is situational in practice for this trading partner,
  not universal — worth keeping in mind if `admission_date` is ever revisited as a required
  field.
- **New observation (not yet acted on):** the real file includes `REF*D9` (claim-level, Claim
  Identifier for transmission intermediaries) and `REF*6R` (service-line-level, Line Item
  Control Number) — both currently absent from the generator. Also `PRV*AT` (attending provider
  taxonomy) and `REF*EA` (medical record number) at the claim level, also currently absent. None
  of these are implemented yet; flagging as candidates for a future completeness pass, not acted
  on this cycle (out of scope for the current open questions).
- **New observation (not yet acted on):** `PER02` in the real file is *not* blank — it holds a
  distinct contact name (`PER*IC*EDI SERVICES*TE*...`), different from the submitter org name.
  The current fix (always blank) remains the safer default given no dedicated "submitter contact
  name" field exists in the data model, but a future optional field could let callers populate
  this more fully.

