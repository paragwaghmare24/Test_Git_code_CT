"""
utils/file_handler.py
Safe file I/O utilities with path validation.
Security: SR-02, SR-03 — validate paths, restrict to controlled directories.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

# Controlled data directory — all file operations are restricted here
_ROOT = Path(__file__).resolve().parent.parent.parent  # EDI_TOOL root
DATA_DIR = _ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
AUDIT_LOG_DIR = DATA_DIR / "audit_log"
TEMPLATES_DIR = DATA_DIR / "templates"
COMPANION_GUIDE_DIR = _ROOT / "Companion_Guide"

# Ensure directories exist at import time
for _d in [UPLOADS_DIR, OUTPUTS_DIR, AUDIT_LOG_DIR, TEMPLATES_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


def _safe_path(base: Path, filename: str) -> Path:
    """Resolve path and ensure it does not escape the base directory."""
    resolved = (base / filename).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(f"Path traversal attempt detected: {filename}")
    return resolved


def save_upload(filename: str, content: bytes) -> Path:
    """Save an uploaded file to the uploads directory."""
    safe_name = f"{uuid.uuid4()}_{Path(filename).name}"
    dest = _safe_path(UPLOADS_DIR, safe_name)
    dest.write_bytes(content)
    return dest


def save_output(filename: str, content: str | bytes, binary: bool = False) -> Path:
    """Save a generated output file."""
    dest = _safe_path(OUTPUTS_DIR, filename)
    if binary:
        dest.write_bytes(content if isinstance(content, bytes) else content.encode())
    else:
        dest.write_text(content if isinstance(content, str) else content.decode(), encoding="utf-8")
    return dest


def read_upload(file_path: str | Path) -> str:
    """Read a text file from the uploads or companion guide directory safely."""
    p = Path(file_path).resolve()
    allowed_bases = [UPLOADS_DIR.resolve(), COMPANION_GUIDE_DIR.resolve(), TEMPLATES_DIR.resolve()]
    if not any(str(p).startswith(str(b)) for b in allowed_bases):
        raise ValueError(f"Access denied: {file_path}")
    return p.read_text(encoding="utf-8", errors="replace")


def read_upload_bytes(file_path: str | Path) -> bytes:
    """Read a binary file safely."""
    p = Path(file_path).resolve()
    allowed_bases = [UPLOADS_DIR.resolve(), COMPANION_GUIDE_DIR.resolve(), TEMPLATES_DIR.resolve()]
    if not any(str(p).startswith(str(b)) for b in allowed_bases):
        raise ValueError(f"Access denied: {file_path}")
    return p.read_bytes()


def write_audit_entry(entry: dict) -> Path:
    """Append a JSON audit entry to the daily audit log file."""
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = AUDIT_LOG_DIR / f"audit_{date_str}.jsonl"
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return log_file


def read_audit_log(date_str: str | None = None) -> list[dict]:
    """Read audit log entries for a given date (defaults to today)."""
    if date_str is None:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = AUDIT_LOG_DIR / f"audit_{date_str}.jsonl"
    if not log_file.exists():
        return []
    entries = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def list_companion_guides() -> list[dict]:
    """List all companion guide files with metadata."""
    guides = []
    for f in COMPANION_GUIDE_DIR.iterdir():
        if f.suffix.lower() in {".docx", ".pdf"}:
            guides.append({
                "file_name": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
                "extension": f.suffix.lower(),
            })
    return guides


def list_outputs() -> list[dict]:
    """List all generated output files."""
    outputs = []
    for f in OUTPUTS_DIR.iterdir():
        if f.is_file():
            outputs.append({
                "file_name": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
                "created_at": datetime.utcfromtimestamp(f.stat().st_ctime).isoformat(),
            })
    return sorted(outputs, key=lambda x: x["created_at"], reverse=True)
