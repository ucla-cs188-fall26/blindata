"""Run after copying interactive_agent.py into the repo: python3 -m unittest -v test_interactive_agent"""
import unittest
import os
from unittest.mock import patch
from types import SimpleNamespace
import tempfile
from pathlib import Path
import sys
from interactive_agent import EvidenceAgent


class EvidenceAgentTests(unittest.TestCase):
    def setUp(self):
        mode = patch.dict(os.environ, {"BLINDATA_AGENT_MODE": "rules"})
        mode.start()
        self.addCleanup(mode.stop)
        self.agent = EvidenceAgent(
            labels=["Jan", "Feb", "Mar", "Apr"],
            series={"sales": [100, 120, 90, 150]},
            unit="USD thousands",
            description="Sales rise continuously and peak in March.",
            buckets={
                "verified": [],
                "contradicted": [
                    "Trend: the description says sales go up, but the data falls.",
                    "Peak: the description puts the sales peak in Mar, but the real maximum is 150 in Apr."
                ],
                "missing": [], "unverifiable": [],
            },
        )

    def test_summary_reuses_existing_findings(self):
        out = self.agent.ask("summary")
        self.assertIn("2 contradicted", out["answer"])
        self.assertIn("1. [contradicted]", out["answer"])

    def test_inspect_has_source_rows(self):
        out = self.agent.ask("why 1")
        self.assertEqual(out["finding"]["status"], "contradicted")
        self.assertEqual(len(out["evidence"]), 4)
        self.assertIn("Feb 120", out["answer"])

    def test_comparison_uses_original_data(self):
        out = self.agent.ask("compare February and March")
        self.assertIn("-25.0%", out["answer"])
        self.assertEqual(len(out["evidence"]), 2)

    def test_rewrite_is_labeled_suggestion(self):
        out = self.agent.ask("corrected description")
        self.assertIn("Suggested data-grounded summary", out["answer"])
        self.assertIn("150 at Apr", out["answer"])

    def test_from_files_delegates_to_existing_checker(self):
        observed = {}
        def fake_load(path):
            observed["loaded_path"] = str(path)
            return ["Jan", "Feb"], {"sales": [2, 1]}, None
        def fake_facts(labels, series):
            return {"from_core_facts": True}
        def fake_check(description, labels, series, computed_facts, unit):
            observed["facts"] = computed_facts
            observed["unit"] = unit
            return {"contradicted": ["Trend: sales decreased."], "verified": [], "missing": [], "unverifiable": []}
        fake_checker = SimpleNamespace(load=fake_load, facts=fake_facts,
                                       check=fake_check, DEFAULT_UNIT="units")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "description.txt"
            p.write_text("sales increased", encoding="utf-8")
            with patch.dict(sys.modules, {"checker": fake_checker}):
                agent = EvidenceAgent.from_files(Path(d) / "data.csv", p)
        self.assertIn("data.csv", observed["loaded_path"])
        self.assertEqual(observed["unit"], "units")
        self.assertEqual(observed["facts"], {"from_core_facts": True})
        self.assertEqual(len(agent.findings), 1)

    def test_invalid_finding_does_not_fabricate(self):
        out = self.agent.ask("why 99")
        self.assertIn("does not exist", out["answer"])


if __name__ == "__main__":
    unittest.main()
