"""
engines/tp_mapping_engine.py
Trading Partner Mapping Engine.
TP Mapping overrides Companion Guide rules where explicitly mapped (AR-10).
Users upload TP mapping files (JSON or CSV).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from backend.models.schemas import (
    ErrorSchema,
    RuleSource,
    Severity,
    TPMappingEntrySchema,
    TPMappingSchema,
)
from backend.utils.file_handler import UPLOADS_DIR

# Cache keyed by (partner_name, transaction_type)
_mapping_cache: dict[str, TPMappingSchema] = {}


def _cache_key(partner_name: str, transaction_type: str) -> str:
    return f"{partner_name.lower()}::{transaction_type}"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_json_mapping(data: dict) -> TPMappingSchema:
    """Parse a TP mapping from a JSON structure."""
    entries = []
    for item in data.get("entries", []):
        entries.append(TPMappingEntrySchema(
            source_segment=item.get("source_segment", ""),
            source_element=item.get("source_element", ""),
            target_field=item.get("target_field", ""),
            mandatory=item.get("mandatory", False),
            value_map=item.get("value_map", {}),
            condition=item.get("condition", ""),
        ))
    return TPMappingSchema(
        partner_name=data.get("partner_name", "Unknown"),
        version=data.get("version", ""),
        transaction_type=data.get("transaction_type", ""),
        entries=entries,
        source_file=data.get("source_file", ""),
    )


def _load_csv_mapping(content: str, partner_name: str, transaction_type: str,
                       source_file: str) -> TPMappingSchema:
    """
    Parse a TP mapping from CSV.
    Expected columns: source_segment, source_element, target_field, mandatory,
                      value_map_key, value_map_value, condition
    """
    entries = []
    reader = csv.DictReader(content.splitlines())
    for row in reader:
        value_map = {}
        key = row.get("value_map_key", "").strip()
        val = row.get("value_map_value", "").strip()
        if key and val:
            value_map[key] = val
        entries.append(TPMappingEntrySchema(
            source_segment=row.get("source_segment", "").strip(),
            source_element=row.get("source_element", "").strip(),
            target_field=row.get("target_field", "").strip(),
            mandatory=row.get("mandatory", "false").strip().lower() in {"true", "1", "yes"},
            value_map=value_map,
            condition=row.get("condition", "").strip(),
        ))
    return TPMappingSchema(
        partner_name=partner_name,
        transaction_type=transaction_type,
        entries=entries,
        source_file=source_file,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_mapping_from_file(file_path: str | Path, partner_name: str,
                            transaction_type: str) -> TPMappingSchema:
    """
    Load a TP mapping from an uploaded file (JSON or CSV).
    Stores in cache for subsequent validation/generation calls.
    """
    p = Path(file_path).resolve()
    if not str(p).startswith(str(UPLOADS_DIR.resolve())):
        raise ValueError(f"TP mapping file must be in uploads directory: {p}")

    content = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() == ".json":
        data = json.loads(content)
        data["source_file"] = str(p)
        mapping = _load_json_mapping(data)
    elif p.suffix.lower() == ".csv":
        mapping = _load_csv_mapping(content, partner_name, transaction_type, str(p))
    else:
        raise ValueError(f"Unsupported TP mapping file format: {p.suffix}")

    key = _cache_key(mapping.partner_name, mapping.transaction_type)
    _mapping_cache[key] = mapping
    return mapping


def load_mapping_from_dict(data: dict) -> TPMappingSchema:
    """Load a TP mapping from a dictionary (e.g. API payload)."""
    mapping = _load_json_mapping(data)
    key = _cache_key(mapping.partner_name, mapping.transaction_type)
    _mapping_cache[key] = mapping
    return mapping


def get_mapping(partner_name: str, transaction_type: str) -> Optional[TPMappingSchema]:
    """Retrieve a cached TP mapping. Returns None if not loaded."""
    return _mapping_cache.get(_cache_key(partner_name, transaction_type))


def list_loaded_mappings() -> list[dict]:
    """List all currently loaded TP mappings."""
    return [
        {
            "partner_name": m.partner_name,
            "transaction_type": m.transaction_type,
            "version": m.version,
            "entry_count": len(m.entries),
            "source_file": m.source_file,
        }
        for m in _mapping_cache.values()
    ]


def apply_tp_overrides(
    segments: list[str],
    mapping: TPMappingSchema,
    element_sep: str = "*",
) -> tuple[list[str], list[dict]]:
    """
    Apply TP mapping value overrides to parsed segments.
    Returns (modified_segments, list_of_applied_overrides).
    Only applies where value_map is defined.
    """
    modified = list(segments)
    applied: list[dict] = []

    for entry in mapping.entries:
        if not entry.value_map or not entry.source_segment or not entry.source_element:
            continue

        # Determine element index from element reference (e.g. CLM05 → index 5)
        element_ref = entry.source_element
        seg_id = entry.source_segment
        try:
            elem_idx = int(element_ref[len(seg_id):])
        except (ValueError, IndexError):
            continue

        for i, seg in enumerate(modified):
            parts = seg.split(element_sep)
            if parts[0].strip() != seg_id:
                continue
            if elem_idx >= len(parts):
                continue
            original_val = parts[elem_idx].strip()
            if original_val in entry.value_map:
                new_val = entry.value_map[original_val]
                parts[elem_idx] = new_val
                modified[i] = element_sep.join(parts)
                applied.append({
                    "segment": seg_id,
                    "element": element_ref,
                    "before": original_val,
                    "after": new_val,
                    "rule": "TP_MAPPING_VALUE_OVERRIDE",
                })

    return modified, applied


def validate_against_mapping(
    segments: list[str],
    mapping: TPMappingSchema,
    element_sep: str = "*",
) -> list[ErrorSchema]:
    """
    Validate segments against mandatory TP mapping rules.
    Returns list of ErrorSchema violations.
    """
    errors: list[ErrorSchema] = []
    present_segments: set[str] = {s.split(element_sep)[0].strip() for s in segments}

    for entry in mapping.entries:
        if not entry.mandatory or not entry.source_segment:
            continue
        if entry.source_segment not in present_segments:
            errors.append(ErrorSchema(
                severity=Severity.ERROR,
                segment=entry.source_segment,
                element=entry.source_element,
                description=(
                    f"Mandatory segment '{entry.source_segment}' missing per "
                    f"TP Mapping for partner '{mapping.partner_name}'."
                ),
                source=RuleSource.TP_MAPPING,
                rule_reference=f"TP:{mapping.partner_name}:{entry.source_element}",
                suggested_correction=f"Add required segment '{entry.source_segment}'.",
            ))

    return errors
