import json
import os
import types
import unittest
from unittest.mock import patch

from web.extensions import _new_side_lines, run_ibmi_adapter, run_llm_review


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return types.SimpleNamespace(status="completed", output_text=json.dumps(self.output))


class ExtensionTests(unittest.TestCase):
    def test_diff_line_validation(self):
        diff = "@@ -2,2 +2,3 @@\n old\n-removed\n+added\n+next\n"
        self.assertEqual(_new_side_lines(diff), {2, 3, 4})

    def test_model_request_is_opt_in_structured_and_stateless(self):
        output = {"summary": "需要复核", "findings": [{"file": "src/X.RPGLE", "line": 3,
                  "severity": "medium", "title": "检查状态", "evidence": "+added",
                  "impact": "可能跳过错误", "action": "添加校验"}]}
        fake = FakeResponses(output)
        context = {"sourceMode": "local", "repository": "demo", "baseSha": "base", "headSha": "head",
                   "files": [{"path": "src/X.RPGLE", "diff": "@@ -2,2 +2,3 @@\n old\n-removed\n+added\n+next\n",
                              "diffTruncated": False}], "ruleFindings": []}
        with patch.dict(os.environ, {"QAAGENT_LLM_ENABLED": "1", "QAAGENT_LLM_MODEL": "approved-model",
                                  "QAAGENT_LLM_API_KEY": "fake-test-key"}):
            result = run_llm_review(context, client=types.SimpleNamespace(responses=fake))
        self.assertEqual(result["findings"][0]["line"], 3)
        self.assertFalse(fake.kwargs["store"])
        self.assertEqual(fake.kwargs["text"]["format"]["type"], "json_schema")
        self.assertNotIn("fake-test-key", fake.kwargs["input"])

    def test_ibmi_adapter_contract(self):
        fake_module = types.SimpleNamespace(run_checks=lambda context: {
            "status": "not_run", "detail": "测试适配器未连接", "evidence": []})
        with patch.dict(os.environ, {"QAAGENT_IBMI_ADAPTER": "fake_ibmi_adapter"}), \
                patch.dict("sys.modules", {"fake_ibmi_adapter": fake_module}):
            result = run_ibmi_adapter({"files": []})
        self.assertEqual(result["status"], "not_run")


if __name__ == "__main__":
    unittest.main()
