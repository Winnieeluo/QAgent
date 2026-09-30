import unittest
from pathlib import Path
from unittest.mock import patch

from create_demo_repo import create_repository
from web.app import DEMO, MEMORY_REPORTS, ROOT, build_review, check_repo, repository_info


class WebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DEMO / ".git").exists():
            create_repository(DEMO)

    def test_demo_repository_metadata(self):
        info = repository_info(check_repo(str(DEMO)))
        self.assertIn("main", info["branches"])
        self.assertEqual(info["currentBranch"], "feature/risky-transfer")

    def test_path_outside_documents_is_rejected(self):
        with self.assertRaises(ValueError):
            check_repo(str(Path.home()))

    def test_web_review_writes_exportable_evidence(self):
        result = build_review(DEMO, "main")
        self.assertEqual(len(result["findings"]), 3)
        self.assertEqual(len(result["files"]), 3)
        report = ROOT / "runs" / result["runId"] / "review.md"
        self.assertTrue(report.is_file())
        self.assertIn("IBMI-001", report.read_text(encoding="utf-8"))
        self.assertEqual(result["checks"][1]["status"], "not_run")

    def test_optional_integrations_are_separate_from_rules(self):
        ai = {"model": "test-model", "summary": "人工复核", "findings": [],
              "verification": "待人工复核"}
        ibmi = {"status": "not_run", "detail": "测试桥接未连接", "evidence": []}
        with patch("web.app.llm_available", return_value=True), \
                patch("web.app.ibmi_available", return_value=True), \
                patch("web.app.run_llm_review", return_value=ai), \
                patch("web.app.run_ibmi_adapter", return_value=ibmi):
            result = build_review(DEMO, "main", persist=False, run_ai=True, run_ibmi=True)
        self.assertEqual(len(result["findings"]), 3)
        self.assertEqual(result["checks"][1]["status"], "passed")
        self.assertEqual(result["checks"][2]["status"], "not_run")
        self.assertIn(result["runId"], MEMORY_REPORTS)
        MEMORY_REPORTS.pop(result["runId"])


if __name__ == "__main__":
    unittest.main()
