import json
import os
import tempfile
import unittest

from ai_news.data import io as ainews_io


class TestAiNewsJsonIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.tmp.close()
        self.path = self.tmp.name
        self._orig = ainews_io.AI_NEWS_PATH
        ainews_io.AI_NEWS_PATH = self.path

    def tearDown(self):
        ainews_io.AI_NEWS_PATH = self._orig
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_write_and_read_roundtrip(self):
        payload = {"updated_at": "2026-04-20T10:00:00Z", "sources": [{"id": "hackernews"}]}
        ainews_io.write_ai_news_atomic(payload)
        got = ainews_io.read_ai_news()
        self.assertEqual(got["updated_at"], payload["updated_at"])
        self.assertEqual(got["sources"][0]["id"], "hackernews")

    def test_read_missing_returns_none(self):
        os.unlink(self.path)
        self.assertIsNone(ainews_io.read_ai_news())

    def test_atomic_write_no_tmp_leftover(self):
        ainews_io.write_ai_news_atomic({"version": 2})
        self.assertFalse(os.path.exists(self.path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
