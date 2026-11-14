"""Offline tests for the LLM tool-calling orchestration; no network key is needed."""
import json
import os
import unittest
from unittest.mock import patch

from interactive_agent import EvidenceAgent
from llm_agent import LLMEvidenceAgent, LLMServiceError, _unbacked_numbers


def call_response(name, args, call_id="call_1"):
    return {"output": [{"type": "function_call", "name": name,
                        "arguments": json.dumps(args), "call_id": call_id}]}


def message_response(text):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


class FakeTransport:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def create(self, **payload):
        self.requests.append(payload)
        if not self.answers:
            raise AssertionError("Unexpected model call")
        return self.answers.pop(0)


class LLMAgentTests(unittest.TestCase):
    def setUp(self):
        self.base = EvidenceAgent(
            labels=["Jan", "Feb", "Mar", "Apr"],
            series={"sales": [100, 120, 90, 150]},
            unit="USD thousands",
            description="Sales increased continuously and peaked in March.",
            buckets={
                "contradicted": ["Trend: Sales rose continuously, but some intervals fell.",
                                 "Peak: sales maximum is not in March."],
                "missing": [], "unverifiable": [], "verified": [],
            },
        )

    def test_llm_calls_readonly_comparison_and_returns_grounded_rows(self):
        transport = FakeTransport([
            call_response("compare_points", {"series": "sales", "first_label": "February", "second_label": "March"}),
            message_response("Sales decreased by 25% from February (120) to March (90)."),
        ])
        agent = LLMEvidenceAgent(self.base, transport=transport)
        result = agent.ask("Was there a drop from February to March?")
        self.assertEqual(result["mode"], "llm")
        self.assertEqual(result["tools_used"], ["compare_points"])
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["evidence"][1]["row_index"], 3)
        self.assertEqual(result["evidence"][1]["value"], 90)
        self.assertEqual(transport.requests[0]["tool_choice"], "required")
        self.assertFalse(transport.requests[0]["store"])
        self.assertEqual(transport.requests[1]["input"][-1]["type"], "function_call_output")
        self.assertIn("-25.0", transport.requests[1]["input"][-1]["output"])

    def test_follow_up_uses_previous_conversation_and_active_finding(self):
        transport = FakeTransport([
            call_response("inspect_finding", {"finding_id": 2}),
            message_response("Finding 2 concerns the peak. The source maximum is 150 at Apr."),
            call_response("inspect_finding", {"finding_id": None}, call_id="call_2"),
            message_response("The selected finding is 2. Maximum is 150 at Apr."),
        ])
        agent = LLMEvidenceAgent(self.base, transport=transport)
        a = agent.ask("Explain finding 2")
        b = agent.ask("Show evidence for that")
        self.assertEqual(a["finding"]["id"], 2)
        self.assertEqual(b["finding"]["id"], 2)
        self.assertEqual(self.base.active_id, 2)
        self.assertIn("Explain finding 2", str(transport.requests[2]["input"]))

    def test_hallucinated_number_replaced_by_tool_evidence(self):
        transport = FakeTransport([
            call_response("compare_points", {"series": "sales", "first_label": "Feb", "second_label": "Mar"}),
            message_response("Sales fell 99.9% to 999 units."),
        ])
        result = LLMEvidenceAgent(self.base, transport=transport).ask("Compare Feb and Mar")
        self.assertNotIn("999", result["answer"])
        self.assertIn("-25.0%", result["answer"])

    def test_monotonicity_is_checked_against_adjacent_values(self):
        transport = FakeTransport([
            call_response("get_trend", {"series": "sales"}),
            message_response("The series rose overall from 100 to 150, but was not continuously increasing."),
        ])
        result = LLMEvidenceAgent(self.base, transport=transport).ask("Did sales increase continuously?")
        self.assertFalse(_unbacked_numbers(result["answer"], [{"answer": "100 to 150"}]))
        self.assertIn("not continuously", result["answer"])
        tool_result = json.loads(transport.requests[1]["input"][-1]["output"])
        self.assertFalse(tool_result["all_intervals_increasing"])
        self.assertEqual(tool_result["nonincreasing_intervals"][0]["to"], "Mar")

    def test_invalid_model_series_is_rejected_by_tool(self):
        transport = FakeTransport([
            call_response("get_extrema", {"series": "invented"}),
            message_response("I can't find that series. Please choose sales."),
        ])
        result = LLMEvidenceAgent(self.base, transport=transport).ask("Find maximum of invented")
        self.assertEqual(result["evidence"], [])
        self.assertIn("Unknown series", result["answer"])
        self.assertIn("Unknown series", transport.requests[1]["input"][-1]["output"])

    def test_model_text_without_tool_is_not_treated_as_verification(self):
        transport = FakeTransport([message_response("Your chart is definitely correct.")])
        result = LLMEvidenceAgent(self.base, transport=transport).ask("Is the chart correct?")
        self.assertIn("No reference-data tool", result["answer"])
        self.assertNotIn("definitely correct", result["answer"])

    def test_missing_api_key_keeps_old_rules(self):
        with patch.dict(os.environ, {"BLINDATA_AGENT_MODE": "auto"}, clear=True):
            self.assertIn("contradicted", self.base.ask("summary")["answer"])
        with patch.dict(os.environ, {"BLINDATA_AGENT_MODE": "llm"}, clear=True):
            self.assertIn("requires OPENAI_API_KEY", self.base.ask("summary")["answer"])

    def test_llm_error_returns_user_safe_message(self):
        class BrokenTransport:
            def create(self, **payload):
                raise LLMServiceError("Could not reach the LLM service.")
        with patch.dict(os.environ, {"BLINDATA_AGENT_MODE": "llm", "OPENAI_API_KEY": "fake"}):
            with patch("llm_agent.LLMEvidenceAgent", return_value=LLMEvidenceAgent(self.base, transport=BrokenTransport())):
                out = self.base.ask("Why 1?")
        self.assertIn("LLM unavailable", out["answer"])


if __name__ == "__main__":
    unittest.main()
