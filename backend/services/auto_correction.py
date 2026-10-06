"""
services/auto_correction.py
Auto Correction Service — propose fixes for validation errors.
All corrections require user approval before writing (PR-04, BR-04).
No silent changes. AI suggestions are flagged separately.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from backend.models.schemas import (
    CorrectionResponseSchema,
    CorrectionSchema,
    ErrorSchema,
    RuleSource,
    ValidationResultSchema,
)


# ---------------------------------------------------------------------------
# Deterministic Correction Rules
# ---------------------------------------------------------------------------

def _try_fix_date_format(value: str) -> Optional[str]:
    """Attempt to reformat a date to CCYYMMDD."""
    import re
    # MM/DD/YYYY → CCYYMMDD
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
    if m:
        return f"{m.group(3)}{int(m.group(1)):02d}{int(m.group(2)):02d}"
    # YYYY-MM-DD → CCYYMMDD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return None


def _generate_correction_for_error(error: ErrorSchema) -> Optional[CorrectionSchema]:
    """
    Generate a deterministic correction proposal for a known error type.
    Returns None if no automatic fix is available.
    """
    desc = error.description.lower()

    # Date format errors
    if "date format" in desc or "ccyymmdd" in desc:
        import re
        # Extract the bad value from description
        m = re.search(r"'([^']+)'", error.description)
        if m:
            bad_value = m.group(1)
            fixed = _try_fix_date_format(bad_value)
            if fixed:
                return CorrectionSchema(
                    error_id=error.error_id,
                    segment=error.segment,
                    element=error.element,
                    before_value=bad_value,
                    after_value=fixed,
                    requires_approval=True,
                    ai_suggested=False,
                )

    # NPI format — can only suggest format, not fabricate a value
    if "npi" in desc and "10 digit" in desc:
        return CorrectionSchema(
            error_id=error.error_id,
            segment=error.segment,
            element=error.element,
            before_value=error.element,
            after_value="[PROVIDE VALID 10-DIGIT NPI]",
            requires_approval=True,
            ai_suggested=False,
        )

    # Segment count mismatch — recalculate SE01
    if "segment count mismatch" in desc and error.segment == "SE":
        import re
        m = re.search(r"actual='(\d+)'", error.description)
        if m:
            correct_count = m.group(1)
            return CorrectionSchema(
                error_id=error.error_id,
                segment="SE",
                element="SE01",
                before_value="",
                after_value=correct_count,
                requires_approval=True,
                ai_suggested=False,
            )

    # Control number mismatch
    if "interchange control number mismatch" in desc:
        import re
        m = re.search(r"ISA13='([^']+)'", error.description)
        if m:
            isa13 = m.group(1)
            return CorrectionSchema(
                error_id=error.error_id,
                segment="IEA",
                element="IEA02",
                before_value="",
                after_value=isa13,
                requires_approval=True,
                ai_suggested=False,
            )

    if "group control number mismatch" in desc:
        import re
        m = re.search(r"GS06='([^']+)'", error.description)
        if m:
            gs06 = m.group(1)
            return CorrectionSchema(
                error_id=error.error_id,
                segment="GE",
                element="GE02",
                before_value="",
                after_value=gs06,
                requires_approval=True,
                ai_suggested=False,
            )

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def propose_corrections(
    validation_result: ValidationResultSchema,
    raw_edi: str,
) -> CorrectionResponseSchema:
    """
    Propose corrections for all errors in a ValidationResultSchema.
    Does NOT apply any changes. User must approve (PR-04).
    Returns CorrectionResponseSchema with proposals and approval token.
    """
    corrections: list[CorrectionSchema] = []

    for error in validation_result.errors:
        correction = _generate_correction_for_error(error)
        if correction:
            corrections.append(correction)

    return CorrectionResponseSchema(
        corrections=corrections,
        corrected_edi=None,  # Not applied until approved
        requires_approval=True,
        approval_token=str(uuid.uuid4()),
    )


def apply_corrections(
    raw_edi: str,
    corrections: list[CorrectionSchema],
    approval_token: str,
) -> str:
    """
    Apply approved corrections to the raw EDI string.
    All corrections must be explicitly approved (requires_approval=True, approved_by set).
    Returns the corrected EDI string.
    """
    # Verify all corrections are approved
    unapproved = [c for c in corrections if not c.approved_by]
    if unapproved:
        raise ValueError(
            f"{len(unapproved)} correction(s) have not been approved. "
            "All corrections require explicit user approval before applying."
        )

    corrected = raw_edi

    # Detect element separator and segment terminator from the ISA envelope.
    # ISA is fixed-width: position 3 = element separator, position 105 = segment
    # terminator (before any newline).  Using hardcoded '~' caused corrections to
    # silently fail on newline-terminated EDI files.
    raw_strip = corrected.strip()
    if len(raw_strip) > 3 and raw_strip.startswith("ISA"):
        element_sep = raw_strip[3]
        candidate = raw_strip[105] if len(raw_strip) > 105 else "~"
        if candidate in ("\n", "\r"):
            seg_term = "\n"
        elif candidate not in (" ", element_sep):
            seg_term = candidate
        else:
            seg_term = "~"
    else:
        element_sep = "*"
        seg_term = "~"

    if seg_term == "\n":
        segments = [s.strip() for s in re.split(r"\r?\n", corrected.strip()) if s.strip()]
    else:
        flat = re.sub(r"[\r\n]+", "", corrected)
        segments = [s.strip() for s in flat.split(seg_term) if s.strip()]

    for correction in corrections:
        seg_id = correction.segment
        element_ref = correction.element
        if not seg_id or not element_ref:
            continue

        # Determine element index
        try:
            elem_idx = int(element_ref[len(seg_id):])
        except (ValueError, IndexError):
            continue

        for i, seg in enumerate(segments):
            parts = seg.split(element_sep)
            if not parts or parts[0].strip() != seg_id:
                continue
            if elem_idx >= len(parts):
                continue
            if correction.before_value and parts[elem_idx].strip() != correction.before_value:
                continue
            parts[elem_idx] = correction.after_value
            segments[i] = element_sep.join(parts)
            break  # Apply to first matching segment only

    return "~\n".join(s for s in segments if s.strip()) + "~"
