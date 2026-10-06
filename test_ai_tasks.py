"""Offline regression tests. All model/retrieval responses and storage are isolated."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.main import app
from backend.services import ai_tasks as tasks
from backend.utils import ai_gate, gemini_client


def step(action, **arguments):
    return {"action": action, "arguments": arguments}


class AITaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ["tasks", "approvals", "guides"]:
            (self.root / folder).mkdir()
        self.patches = [
            patch.object(tasks, "TASK_DIR", self.root / "tasks"),
            patch.object(tasks, "COMPANION_GUIDE_DIR", self.root / "guides"),
            patch.object(ai_gate, "_PENDING_DIR", self.root / "approvals"),
            patch.object(tasks.audit, "record"),
            patch.object(gemini_client, "task_step"),
            patch.object(tasks, "_retrieve"),
        ]
        self.mocks = [p.start() for p in self.patches]
        self.model, self.retrieve = self.mocks[-2:]
        self.client = TestClient(app)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def approval(self):
        response = self.client.post("/api/ai/request", json={"action": "test review"})
        self.assertEqual(response.status_code, 200)
        rid = response.json()["request_id"]
        self.assertEqual(self.client.post(f"/api/ai/approve/{rid}").status_code, 200)
        return rid

    def create(self, policy="undecided", context="deterministic result", raw=b"bad ISA input"):
        response = self.client.post("/api/ai/tasks", data={
            "request_id": self.approval(), "panel": "Validation", "instruction": "Review source independently",
            "context": context, "data_policy": policy,
        }, files={"files": ("source.edi", raw, "text/plain")})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def act(self, task, action, **kwargs):
        response = self.client.post(f"/api/ai/tasks/{task['id']}/actions", json={
            "revision": task["revision"], "action": action, **kwargs,
        })
        return response

    def plan(self, policy="supplied", count=None, fmt="txt"):
        return step("plan", summary="Create a new output", changes=["Create output; preserve original"],
                    assumptions=[], data_policy=policy, outputs=[{
                        "name": "result." + fmt, "format": fmt, "description": "Requested copy",
                        "record_count": count, "record_segment": "CLM"}])

    def test_unapproved_call_never_reaches_model(self):
        rid = ai_gate.request_ai_approval("test")
        response = self.client.post("/api/ai/tasks", data={"request_id": rid,
            "panel": "test", "instruction": "review"})
        self.assertEqual(response.status_code, 403)
        self.model.assert_not_called()

    def test_approval_cannot_be_reused(self):
        self.model.return_value = step("answer", message="Reviewed")
        rid = self.approval()
        data = {"request_id": rid, "panel": "test", "instruction": "review"}
        self.assertEqual(self.client.post("/api/ai/tasks", data=data).status_code, 200)
        self.assertEqual(self.client.post("/api/ai/tasks", data=data).status_code, 422)
        self.assertEqual(self.model.call_count, 1)

    def test_source_read_despite_parse_failure_and_full_context(self):
        raw = b"ISA malformed\nST*837\nCLM*ABC\nCLM*DEF\nSE*5"
        self.model.side_effect = [step("read", document_id="doc2", offset=0, length=16000),
                                 step("read", document_id="doc1", offset=0, length=16000),
                                 step("answer", message="Two CLMs, same ST/SE; ISA remains malformed.")]
        task = self.create(context="x" * 8000, raw=raw)
        self.assertEqual(task["state"], "answered")
        saved = tasks.load(task["id"])
        self.assertEqual(saved["documents"][0]["text"], raw.decode())
        self.assertEqual(len(saved["documents"][1]["text"]), 8000)
        self.assertTrue(all(c["complete"] for c in task["coverage_summary"]))

    def test_assessment_requires_explicit_adoption(self):
        assessment = dict(message="Rule may be a false positive", verdict="REVIEW", findings=[{
            "classification": "false_positive", "description": "ST/SE is transaction-level",
            "evidence": ["doc1: CLM structure"]}], limitations=["Guide not available"])
        self.model.return_value = step("assess", **assessment)
        task = self.create()
        self.assertEqual(task["state"], "assessment_pending")
        self.assertNotIn("adopted_assessment", task)
        adopted = self.act(task, "adopt").json()
        self.assertEqual(adopted["state"], "adopted")
        self.assertEqual(adopted["adopted_assessment"], assessment)
        self.assertEqual(self.model.call_count, 1)
        self.assertEqual(tasks.load(task["id"])["documents"][1]["text"], "deterministic result")

    def test_pass_with_unread_source_is_not_accepted(self):
        self.model.side_effect = [step("assess", message="PASS", verdict="PASS", findings=[], limitations=[]),
                                 step("assess", message="Incomplete review", verdict="REVIEW", findings=[],
                                      limitations=["Unread input"])]
        task = self.create()
        self.assertEqual(task["assessment"]["verdict"], "REVIEW")

    def test_file_tools_cannot_bypass_approval(self):
        self.model.side_effect = [step("write", name="result.txt", text="unauthorized"), self.plan()]
        task = self.create("supplied")
        self.assertEqual(task["state"], "plan_pending")
        self.assertEqual(task["artifacts"], [])
        self.assertEqual(tasks.load(task["id"])["drafts"], {})
        self.assertEqual(self.act(task, "execute").status_code, 422)

    def test_approved_copy_checked_and_downloadable(self):
        self.model.return_value = self.plan()
        task = self.create("supplied", raw=b"original unchanged")
        self.model.side_effect = [step("copy", name="result.txt", document_id="doc1"),
                                 step("check"), step("read", document_id="doc3"),
                                 step("finish", message="Created verified copy")]
        result = self.act(task, "execute", request_id=self.approval()).json()
        self.assertEqual(result["state"], "completed", result)
        artifact = result["artifacts"][0]
        response = self.client.get(artifact["url"])
        self.assertEqual(response.content, b"original unchanged")
        self.assertEqual(tasks.load(task["id"])["documents"][0]["text"], "original unchanged")
        self.assertEqual(self.act(task, "execute", request_id=self.approval()).status_code, 422)

    def test_missing_data_policy_asks_instead_of_synthesizing(self):
        self.model.side_effect = [self.plan("synthetic", count=1000),
            step("clarify", message="Choose record policy", questions=["Use supplied, duplicate, or synthetic records?"])]
        task = self.create()
        self.assertEqual(task["state"], "clarification")
        self.assertNotIn("plan", task)
        self.assertEqual(task["artifacts"], [])

    def test_policy_cannot_change_at_execution(self):
        self.model.return_value = self.plan("supplied")
        task = self.create("supplied")
        response = self.act(task, "execute", request_id=self.approval(), data_policy="synthetic")
        self.assertEqual(response.status_code, 422)

    def test_reply_can_explicitly_choose_synthetic_then_plan(self):
        self.model.return_value = step("clarify", message="Choose", questions=["Record policy?"])
        task = self.create()
        self.model.return_value = self.plan("synthetic", count=2, fmt="csv")
        response = self.act(task, "reply", request_id=self.approval(), message="Use synthetic test records", data_policy="synthetic")
        self.assertEqual(response.json()["state"], "plan_pending")
        self.assertEqual(response.json()["data_policy"], "synthetic")

    def test_bulk_template_and_count_verification(self):
        self.model.return_value = self.plan("synthetic", count=1000, fmt="csv")
        task = self.create("synthetic")
        self.model.side_effect = [step("write", name="result.csv", text="claim_id,amount\n"),
            step("repeat", name="result.csv", template="TEST{index:09d},1\n", count=1000, start=1, append=True),
            step("check"), step("read", document_id="doc3"), step("finish", message="1000 synthetic test records")]
        result = self.act(task, "execute", request_id=self.approval()).json()
        self.assertEqual(result["state"], "completed", result)
        self.assertEqual(result["artifacts"][0]["checks"]["record_count"], 1000)

    def test_incomplete_output_cannot_publish(self):
        self.model.return_value = self.plan("synthetic", count=1000, fmt="csv")
        task = self.create("synthetic")
        self.model.side_effect = [step("write", name="result.csv", text="id\nTEST1\n"), step("check"),
            step("finish", message="Claiming success too soon"),
            step("clarify", message="Need more records", questions=["Continue generation?"])]
        result = self.act(task, "execute", request_id=self.approval()).json()
        self.assertEqual(result["artifacts"], [])
        self.assertEqual(result["state"], "clarification")

    def test_draft_change_invalidates_checks(self):
        self.model.return_value = self.plan()
        task = self.create("supplied")
        self.model.side_effect = [step("copy", name="result.txt", document_id="doc1"), step("check"),
            step("read", document_id="doc3"), step("write", name="result.txt", text="changed"),
            step("finish", message="done"), step("clarify", message="Must check again", questions=["Continue?"])]
        result = self.act(task, "execute", request_id=self.approval()).json()
        self.assertEqual(result["artifacts"], [])

    def test_path_traversal_and_expression_templates_blocked(self):
        for name in ["../file.txt", "C:\\file.txt", "/tmp/f.txt", "sub/file.txt"]:
            with self.assertRaises(ValueError):
                tasks._safe_name(name)
        task = {"execution_revision": 1, "plan": {"data_policy": "synthetic", "outputs": [{"name": "result.txt"}]}, "drafts": {}}
        with self.assertRaises(ValueError):
            tasks._tool(task, "repeat", {"name": "result.txt", "template": "{index.__class__}", "count": 1})

    def test_external_retrieval_requires_new_permission_each_time(self):
        url = "https://x12.org/codes/claim-status-category-codes"
        self.model.return_value = step("external", url=url, reason="Configured guide lacks this code")
        task = self.create()
        self.retrieve.assert_not_called()
        self.assertEqual(task["state"], "external_pending")
        self.retrieve.return_value = "Reference content"
        self.model.return_value = step("external", url="https://x12.org/codes/claim-status-codes", reason="Second distinct reference needed")
        approved = self.act(task, "retrieve", request_id=self.approval()).json()
        self.assertEqual(approved["state"], "external_pending")
        self.retrieve.assert_called_once_with(url)
        rejected = self.act(approved, "reject").json()
        self.assertEqual(rejected["state"], "rejected")
        self.assertEqual(self.retrieve.call_count, 1)

    def test_private_urls_and_query_exfiltration_blocked(self):
        for url in ["http://x12.org/", "https://127.0.0.1/", "https://x12.org.evil.test/",
                    "https://x12.org/?patient=123", "https://user@x12.org/", "https://x12.org:444/"]:
            with self.assertRaises(ValueError):
                tasks._validate_url(url)

    def test_legacy_ai_routes_fail_closed(self):
        response = self.client.post("/api/ai/op/ask", data={"request_id": self.approval(),
            "panel": "test", "user_instruction": "Generate without approval"})
        self.assertEqual(response.status_code, 410)
        self.model.assert_not_called()

    def test_provider_failure_is_not_faked_success(self):
        self.model.side_effect = RuntimeError("Provider unavailable")
        task = self.create()
        self.assertEqual(task["state"], "failed")
        self.assertIn("Provider unavailable", task["error"])
        self.assertEqual(task["artifacts"], [])

    def test_xlsx_model_cells_not_executable(self):
        from openpyxl import load_workbook
        content, checks = tasks._serialize({"format": "xlsx", "name": "book.xlsx", "record_count": 1},
            json.dumps({"sheets": [{"name": "Claims", "rows": [["name"], ["=HYPERLINK(\"https://evil.test\")"]]}]}))
        wb = load_workbook(io.BytesIO(content))
        self.assertEqual(wb.active["A2"].data_type, "s")
        self.assertEqual(checks["record_count"], 1)
        wb.close()

    def test_837_multiple_claim_layouts_not_confused_with_transactions(self):
        isa = "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *261001*1200*^*00501*000000001*0*T*:~"
        gs = "GS*HC*SENDER*RECEIVER*20261001*1200*1*X*005010X222A1~"
        variants = [
            "ST*837*1~HL*1**20*1~HL*2*1*22*0~CLM*A*10~CLM*B*20~SE*6*1~GE*1*1~",
            "ST*837*1~HL*1**20*1~HL*2*1*22*0~CLM*A*10~SE*5*1~ST*837*2~HL*1**20*1~HL*2*1*22*0~CLM*B*20~SE*5*2~GE*2*1~",
        ]
        for body in variants:
            rows = tasks._segments(isa + gs + body + "IEA*1*000000001~")
            self.assertEqual(sum(r[0] == "CLM" for r in rows), 2)
            self.assertEqual(tasks._envelope_checks(rows), [])


if __name__ == "__main__":
    unittest.main()