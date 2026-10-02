"""Offline regression checks; never load personal config or call an upstream."""

import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        with patch.dict(os.environ, {"OCS2API_DATA_DIR": str(cls.root)}, clear=True):
            with patch("dotenv.load_dotenv"):
                cls.config = importlib.import_module("config")
                cls.service = importlib.import_module("app")
        cls.client = cls.service.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.service.Config._settings = dict(self.config.DEFAULT_SETTINGS)
        for key, value in self.config.DEFAULT_SETTINGS.items():
            setattr(self.service.Config, key.upper(), value)
        self.service.initialize_runtime()
        self.service.question_bank.clear()
        self.service.qa_records.clear()

    def test_empty_key_still_allows_console_and_health(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("OCS2API", response.get_data(as_text=True))
        self.assertIn("runtime-log-output", response.get_data(as_text=True))
        self.assertEqual(self.client.get("/api/health").json["status"], "ok")
        self.assertFalse(self.client.get("/api/config").json["api_key_configured"])

    def test_import_search_export_and_reload_without_upstream(self):
        record = {"question": "1 + 1?", "type": "single", "options": "1\n2", "answer": "2"}
        self.assertTrue(self.client.post("/api/question-bank/import", json=[record]).json["success"])
        upstream = Mock()
        with patch.object(self.service, "client", upstream):
            response = self.client.get("/api/search", query_string={
                "title": record["question"], "type": record["type"], "options": record["options"]
            })
        upstream.chat.completions.create.assert_not_called()
        self.assertEqual(response.json, {"code": 1, "question": record["question"], "answer": "2"})
        self.assertEqual(json.loads(self.client.get("/api/question-bank/export").data), [record])
        restored = self.service.QuestionBank(self.config.QUESTION_BANK_PATH)
        self.assertEqual(restored.find("1 + 1?", "single", "1\n2"), "2")
        self.assertIsNone(restored.find("1 + 1?", "single", "2\n1"))

    def test_upstream_answer_is_persisted_for_next_search(self):
        upstream = Mock()
        upstream.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="2"))]
        )
        with patch.object(self.service, "client", upstream):
            self.assertEqual(self.client.post("/api/search", json={"title": "1+1?"}).json["answer"], "2")
        self.service.cache.clear()
        self.assertEqual(self.client.get("/api/search?title=1%2B1?").json["answer"], "2")
        upstream.chat.completions.create.assert_called_once()
        self.assertEqual(self.service.QuestionBank(self.config.QUESTION_BANK_PATH).find("1+1?"), "2")

    def test_search_access_token(self):
        self.service.Config.ACCESS_TOKEN = "example-token"
        self.assertEqual(self.client.get("/api/search?title=test").status_code, 403)
        self.assertEqual(self.client.get("/api/search?title=test", headers={"X-Access-Token": "example-token"}).status_code, 200)

    def test_config_save_masks_key_and_preserves_blank_input(self):
        response = self.client.put("/api/config", json={"port": 5019, "openai_api_key": "example-key-1234"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["restart_required"])
        self.assertNotIn("example-key-1234", response.get_data(as_text=True))
        self.assertEqual(self.client.put("/api/config", json={"openai_api_key": ""}).status_code, 200)
        settings = json.loads(self.config.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(settings["port"], 5019)
        self.assertEqual(settings["openai_api_key"], "example-key-1234")

    def test_invalid_config_does_not_replace_saved_values(self):
        self.client.put("/api/config", json={"port": 5018})
        before = self.config.CONFIG_PATH.read_bytes()
        self.assertEqual(self.client.put("/api/config", json={"port": 65536}).status_code, 400)
        self.assertEqual(self.config.CONFIG_PATH.read_bytes(), before)

    def test_ocs_config_uses_request_port_and_placeholders(self):
        entry = self.client.get("/api/ocs-config", base_url="http://localhost:5027").json[0]
        self.assertEqual(entry["name"], "OCS2API")
        self.assertEqual(entry["url"], "http://localhost:5027/api/search")
        self.assertEqual(entry["data"], {"title": "${title}", "type": "${type}", "options": "${options}"})

    def test_logs_are_bounded_and_can_be_cleared(self):
        self.client.post("/api/logs/clear")
        for index in range(350):
            self.service.append_runtime_log("test record %d" % index)
        logs = self.client.get("/api/logs?limit=999").json["logs"]
        self.assertEqual(len(logs), 300)
        self.assertEqual(logs[0]["message"], "test record 50")
        self.client.post("/api/logs/clear")
        self.assertEqual(len(self.client.get("/api/logs").json["logs"]), 1)

    def test_import_rejects_non_array(self):
        self.assertEqual(self.client.post("/api/question-bank/import", json="invalid").status_code, 400)

    def test_container_data_path_is_separate_from_resources(self):
        self.assertEqual(self.config.DATA_DIR, self.root)
        self.assertNotEqual(self.config.DATA_DIR, self.config.APP_DIR)


if __name__ == "__main__":
    unittest.main()
