"""test_offline_sync.py - Unit test suite for jarvis_offline_sync.py

Verifies:
- Idempotent processing of offline turns and memories.
- Handling of sensitive memories according to Five Rules.
- Sync status reporting.
"""
import json
import tempfile
import unittest
from pathlib import Path

import jarvis_offline_sync as sync


class TestOfflineSync(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_sync.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_batch(self):
        res = sync.handle_offline_batch({}, db_path=self.db_path)
        self.assertTrue(res["ok"])
        self.assertEqual(res["accepted_turns"], [])
        self.assertEqual(res["accepted_memories"], [])

    def test_turn_ingestion_and_idempotency(self):
        payload = {
            "device_id": "pixel9_test",
            "turns": [
                {
                    "turn_id": "turn-101",
                    "conversation_id": "chat-a",
                    "timestamp": 1731375000000,
                    "user_query": "What is the capital of Italy?",
                    "model_response": "The capital of Italy is Rome.",
                    "model_name": "ondevice:qwen2.5"
                }
            ]
        }
        # First sync
        res1 = sync.handle_offline_batch(payload, db_path=self.db_path)
        self.assertTrue(res1["ok"])
        self.assertEqual(res1["accepted_turns"], ["turn-101"])

        # Second sync with same turn (idempotency check)
        res2 = sync.handle_offline_batch(payload, db_path=self.db_path)
        self.assertTrue(res2["ok"])
        self.assertEqual(res2["accepted_turns"], ["turn-101"])

        conn = sync._init_sync_db(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM synced_records WHERE item_id = 'turn-101'")
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1, "Turn must only be recorded once in synced_records")

    def test_memory_ingestion_and_status(self):
        payload = {
            "device_id": "pixel9_test",
            "memories": [
                {
                    "memory_id": "mem-201",
                    "timestamp": 1731375000000,
                    "fact_text": "Prefers espresso over drip coffee",
                    "category": "preferences",
                    "sensitive": False
                },
                {
                    "memory_id": "mem-202",
                    "timestamp": 1731375000000,
                    "fact_text": "Doctor visit scheduled on Tuesday",
                    "category": "health",
                    "sensitive": True
                }
            ]
        }
        res = sync.handle_offline_batch(payload, db_path=self.db_path)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["accepted_memories"]), 2)

        # Check sync status
        status = sync.sync_status(db_path=self.db_path)
        self.assertTrue(status["ok"])
        self.assertEqual(status["total_synced_memories"], 2)
        self.assertIsNotNone(status["last_sync"])
        self.assertEqual(status["last_sync"]["device"], "pixel9_test")

    def test_mobile_lane_registration_and_status(self):
        reg_payload = {
            "device_id": "pixel-9-owner",
            "model_name": "qwen2.5-1.5b",
            "vulkan": True,
            "context_size": 2048
        }
        res = sync.register_mobile_lane(reg_payload)
        self.assertTrue(res["ok"])
        self.assertEqual(res["lane"], "mobile-edge")
        self.assertEqual(res["device_id"], "pixel-9-owner")

        status = sync.mobile_lane_status()
        self.assertTrue(status["available"])
        self.assertTrue(status["active"])
        self.assertEqual(status["info"]["model_name"], "qwen2.5-1.5b")
        self.assertTrue(status["info"]["vulkan"])

    def test_available_transfer_models(self):
        models_data = sync.available_transfer_models()
        self.assertIn("models", models_data)
        self.assertGreaterEqual(len(models_data["models"]), 1)
        first = models_data["models"][0]
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertIn("filename", first)
        self.assertIn("size_bytes", first)
        self.assertTrue(first["recommended"])


if __name__ == "__main__":
    unittest.main()
