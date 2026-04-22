import json
import os
import shutil
import tempfile
import unittest

from ai_news.data import evolve


class TestEvolveHelpers(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source_md_path = os.path.join(self.tmpdir, "source.md")
        self.log_path = os.path.join(self.tmpdir, "evolve-log.jsonl")
        with open(self.source_md_path, "w") as f:
            f.write("---\nevolve_count: 3\n---\nbody")
        self._orig = evolve.EVOLVE_LOG_PATH
        evolve.EVOLVE_LOG_PATH = self.log_path

    def tearDown(self):
        evolve.EVOLVE_LOG_PATH = self._orig
        shutil.rmtree(self.tmpdir)

    def test_backup_creates_versioned_copy(self):
        backup = evolve.backup_source(self.source_md_path, evolve_count=3)
        self.assertTrue(os.path.isfile(backup))
        self.assertTrue(backup.endswith(".v3"))
        with open(backup) as f:
            self.assertIn("evolve_count: 3", f.read())

    def test_load_frontmatter_parses_count(self):
        fm = evolve.load_frontmatter(self.source_md_path)
        self.assertEqual(fm.get("evolve_count"), 3)

    def test_write_evolve_log_appends_jsonl(self):
        evolve.write_evolve_log({"source": "hackernews", "from": 3, "to": 4, "diff": "..."})
        with open(self.log_path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        j = json.loads(lines[0])
        self.assertEqual(j["source"], "hackernews")
        self.assertIn("ts", j)


if __name__ == "__main__":
    unittest.main()
