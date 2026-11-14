"""Exercise the real local HTTP server without calling an external API."""
import http.client
import json
from pathlib import Path
import os
import threading
import unittest
from unittest.mock import patch

from agent_web import Handler, SESSIONS, ThreadingHTTPServer


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class WebIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        mode = patch.dict(os.environ, {"BLINDATA_AGENT_MODE": "rules"})
        mode.start()
        self.addCleanup(mode.stop)
        SESSIONS.clear()

    def request(self, path, payload=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            body = json.dumps(payload) if payload is not None else None
            connection.request("POST" if payload is not None else "GET", path,
                               body=body, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read().decode("utf-8")
            if response.getheader("Content-Type", "").startswith("application/json"):
                data = json.loads(data)
            return response.status, data
        finally:
            connection.close()

    def start_example(self, filename="chart1_data.csv"):
        examples = Path(__file__).parent / "examples"
        path = examples / filename
        return self.request("/api/start", {
            "format": path.suffix[1:],
            "data": path.read_text(),
            "description": (examples / "chart1_description_wrong.txt").read_text(),
        })

    def test_serves_html_and_javascript(self):
        status, page = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn('id="verify-form"', page)
        status, script = self.request("/static/agent_ui.js")
        self.assertEqual(status, 200)
        self.assertIn("/api/start", script)

    def test_verifies_every_example_format(self):
        for filename in ("chart1_data.csv", "chart1_data.tsv", "chart1_data_labels.json",
                         "chart1_data_rows.json", "chart1_vegalite.json",
                         "chart1_data_pasted_tabs.txt", "chart1_data_pasted_aligned.txt"):
            with self.subTest(filename=filename):
                status, result = self.start_example(filename)
                self.assertEqual(status, 200, result)
                self.assertEqual(result["agent_mode"], "rules")
                self.assertIn("4 contradicted", result["result"]["answer"])
                self.assertEqual(len(result["findings"]), 8)

    def test_follow_up_returns_original_evidence(self):
        status, session = self.start_example()
        self.assertEqual(status, 200)
        status, result = self.request("/api/ask", {
            "session_id": session["session_id"],
            "question": "compare apples February and March",
        })
        self.assertEqual(status, 200)
        self.assertEqual([r["value"] for r in result["result"]["evidence"]], [14, 18])
        self.assertIn("28.6%", result["result"]["answer"])

    def test_invalid_data_is_rejected(self):
        status, result = self.request("/api/start", {
            "format": "csv", "data": "month,sales\nJan,invalid", "description": "Sales rise.",
        })
        self.assertEqual(status, 400)
        self.assertIn("error", result)

    def test_unknown_session_is_reported(self):
        status, result = self.request("/api/ask", {"session_id": "unknown", "question": "summary"})
        self.assertEqual(status, 404)
        self.assertIn("Session expired", result["error"])


if __name__ == "__main__":
    unittest.main()
