import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qa_agent
from create_demo_repo import create_repository


class RuleTests(unittest.TestCase):
    def test_synthetic_branch_has_three_findings_and_self_diff_has_none(self):
        repo = Path(__file__).resolve().parents[1] / "demo-repo"
        if not (repo / ".git").exists():
            create_repository(repo)
        self.assertEqual([x.rule for x in qa_agent.review(repo, "main")],
                         ["IBMI-002", "IBMI-003", "IBMI-001"])
        self.assertEqual(qa_agent.review(repo, "HEAD"), [])

    def test_dds_precision_parser(self):
        self.assertEqual(qa_agent.dds_fields("A          BALANCE       15P 2\n"), {"BALANCE": (15, 2)})

    def test_changed_update_requires_sql_check(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "transfer.sqlrpgle").write_text(
                "exec sql update DEMO.ACCOUNT_BALANCE set BALANCE = BALANCE + :amount;\n"
                "exec sql commit;\n", encoding="utf-8"
            )
            with patch.object(qa_agent, "git", return_value=""), \
                 patch.object(qa_agent, "changed_lines", return_value={"transfer.sqlrpgle": {1}}):
                found = qa_agent.review(repo, "main")
            self.assertEqual([item.rule for item in found], ["IBMI-001"])

    def test_checked_update_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "transfer.sqlrpgle").write_text(
                "exec sql update DEMO.ACCOUNT_BALANCE set BALANCE = BALANCE + :amount;\n"
                "if sqlcode <> 0;\n  return;\nendif;\n", encoding="utf-8"
            )
            with patch.object(qa_agent, "git", return_value=""), \
                 patch.object(qa_agent, "changed_lines", return_value={"transfer.sqlrpgle": {1}}):
                found = qa_agent.review(repo, "main")
            self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
