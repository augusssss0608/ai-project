import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ai_news import history


class TestHistoryAppendAndAggregate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        self.tmp.close()
        self.path = self.tmp.name
        self._orig_path = history.HISTORY_PATH
        history.HISTORY_PATH = self.path

    def tearDown(self):
        history.HISTORY_PATH = self._orig_path
        os.unlink(self.path)

    def test_append_items_creates_jsonl_lines(self):
        items = [
            {"source": "hackernews", "url": "u1", "title": "A", "desc": "d1"},
            {"source": "hackernews", "url": "u2", "title": "B", "desc": "d2"},
        ]
        history.append_items(items)
        with open(self.path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        j = json.loads(lines[0])
        self.assertEqual(j["source"], "hackernews")
        self.assertEqual(j["url"], "u1")
        self.assertIn("ts", j)

    def test_aggregate_groups_by_url(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        past_iso = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        with open(self.path, "w") as f:
            f.write(json.dumps({"ts": past_iso, "source": "hackernews", "url": "u1", "title": "A"}) + "\n")
            f.write(json.dumps({"ts": now_iso, "source": "hackernews", "url": "u1", "title": "A"}) + "\n")
            f.write(json.dumps({"ts": now_iso, "source": "hackernews", "url": "u2", "title": "B"}) + "\n")
        agg = history.aggregate_by_url(source_id="hackernews")
        self.assertEqual(len(agg), 2)
        u1 = next(a for a in agg if a["url"] == "u1")
        u2 = next(a for a in agg if a["url"] == "u2")
        self.assertEqual(u1["count"], 2)
        self.assertEqual(u2["count"], 1)
        self.assertEqual(u1["first_ts"], past_iso)
        self.assertEqual(u1["last_ts"], now_iso)

    def test_get_negatives_excludes_voted_and_recent(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        past_iso = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        recent_iso = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with open(self.path, "w") as f:
            f.write(json.dumps({"ts": past_iso, "source": "hackernews", "url": "voted", "title": "v"}) + "\n")
            f.write(json.dumps({"ts": recent_iso, "source": "hackernews", "url": "recent", "title": "r"}) + "\n")
            f.write(json.dumps({"ts": past_iso, "source": "hackernews", "url": "neg1", "title": "n1"}) + "\n")
            f.write(json.dumps({"ts": past_iso, "source": "hackernews", "url": "neg1", "title": "n1"}) + "\n")

        feedback = {"votes": {"voted": {"source": "hackernews"}}}
        negs = history.get_negatives("hackernews", feedback, days=7, limit=10)
        self.assertEqual(len(negs), 1)
        self.assertEqual(negs[0]["url"], "neg1")
        self.assertEqual(negs[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
