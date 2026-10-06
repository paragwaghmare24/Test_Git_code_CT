"""Opt-in Gemini protocol check using synthetic data only.

Run explicitly after user permission. Does not use workspace uploads/guides,
publish artifacts, or approve external retrieval. All local state is temporary.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.services import ai_tasks
from backend.utils import ai_gate, gemini_client


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for sub in ("tasks", "approvals", "guides"):
            (root / sub).mkdir()
        with patch.object(ai_tasks, "TASK_DIR", root / "tasks"), \
             patch.object(ai_tasks, "COMPANION_GUIDE_DIR", root / "guides"), \
             patch.object(ai_gate, "_PENDING_DIR", root / "approvals"), \
             patch.object(ai_tasks.audit, "record"):
            rid = ai_gate.request_ai_approval("User-approved synthetic-only live protocol check")
            ai_gate.approve_ai_request(rid)
            task = ai_tasks.create(rid, "Synthetic protocol check",
                "Explain whether deterministic rule 'one SE per CLM' is reliable. "
                "Read both supplied excerpts. Discuss transaction sets versus claims and HL. "
                "These are incomplete, artificial structure excerpts, NOT complete real claims. "
                "Do not certify them valid, generate files or request external references. "
                "Return an answer with concise evidence and limitations.",
                json.dumps({"deterministic_result": {"status": "FAIL", "rule": "One SE required per CLM"},
                            "note": "Synthetic intentionally incorrect rule for review testing"}),
                [("synthetic_structures.txt", b"Layout A (excerpt):\nST*837*0001~HL*1**20*1~HL*2*1*22*0~CLM*TEST001*10~CLM*TEST002*20~SE*6*0001~\n"
                  b"Layout B (excerpt):\nST*837*0001~CLM*TEST001*10~SE*3*0001~ST*837*0002~CLM*TEST002*20~SE*3*0002~")])
            print(json.dumps({"model": gemini_client._MODEL_NAME, "state": task["state"],
                              "message": task.get("message"), "error": task.get("error"),
                              "coverage": task.get("coverage_summary"),
                              "artifact_count": len(task["artifacts"])}, indent=2))
            if task["state"] != "answered" or task["artifacts"]:
                raise SystemExit(1)


if __name__ == "__main__":
    main()