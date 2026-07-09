import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tg_notify
from tg_notify import build_daily_report_from_data


def _spec_data(github_items=None, warning=None, error=None):
    """§2.6 spec 合规形态: pipeline_metrics 键为 dedupe, 无 total_items/sources."""
    if github_items is None:
        github_items = [{"dimension": d} for d in ("daily", "weekly", "monthly", "total")]
    return {
        "stage_by_source": {"hackernews": "hot", "github_trending": "cold", "threads": "hot"},
        "pipeline_metrics": {
            "wall_time_sec": 100,
            "scorer": {"source_failures": []},
            "boundary_fetch": {},
            "dedupe": {"suppressed_total": 4},
        },
        "sources": [
            {"id": "hackernews", "items": [{}] * 5, "error": None, "warning": None},
            {"id": "github_trending", "items": github_items, "error": error, "warning": warning},
            {"id": "threads", "items": [{}] * 2, "error": None, "warning": None},
        ],
    }


class TestBuildDailyReport(unittest.TestCase):
    """报文构建对 spec 合规 / 异形 / 残缺 JSON 的行为."""

    def test_spec_shape_all_normal_no_alerts(self):
        text = build_daily_report_from_data(_spec_data(), [])
        lines = text.splitlines()
        self.assertEqual(lines[0], "[ai-news] 已刷新 11 则 · 去重 4 条")
        self.assertEqual(lines[1], "HN 5 · GitHub 4 · Threads 2")
        self.assertEqual(lines[2], "阶段: HN hot · GitHub cold · Threads hot")
        self.assertEqual(lines[3], "dashboard: http://localhost:38080/#news")
        self.assertNotIn("⚠️", text)

    def test_malformed_0709_shape_compat(self):
        # 07-09 云端 agent 自由发挥的异形: dedup/total_items/sources, 缺 github_dims
        data = {
            "stage_by_source": {"hackernews": "hot", "github_trending": "cold", "threads": "hot"},
            "pipeline_metrics": {
                "total_items": 53,
                "dedup": {"suppressed_total": 6},
                "sources": {"hackernews": 5, "github_trending": 27, "threads": 21},
            },
            "sources": [
                {"id": "github_trending", "error": None,
                 "warning": "部分维度抓取失败: daily: 所有实例无数据",
                 "items": [{"dimension": "weekly"}] * 8 + [{"dimension": "monthly"}] * 5
                          + [{"dimension": "total"}] * 14},
            ],
        }
        text = build_daily_report_from_data(data, [])
        self.assertIn("已刷新 53 则 · 去重 6 条", text)
        self.assertIn("HN 5 · GitHub 27 · Threads 21", text)
        self.assertIn("⚠️ GitHub 维度空: daily", text)
        self.assertIn("⚠️ GitHub 部分维度抓取失败: daily", text)

    def test_github_source_total_failure(self):
        text = build_daily_report_from_data(
            _spec_data(github_items=[], error="RSSHubTimeout: all instances dead"), [])
        self.assertIn("⚠️ GitHub 维度空: daily · weekly · monthly · total", text)
        self.assertIn("⚠️ GitHub 抓取错误: RSSHubTimeout", text)

    def test_empty_data_does_not_crash(self):
        text = build_daily_report_from_data({}, [])
        self.assertIn("已刷新 0 则 · 去重 0 条", text)
        self.assertIn("HN 0 · GitHub 0 · Threads 0", text)
        self.assertIn("⚠️ GitHub 维度空: daily · weekly · monthly · total", text)
        self.assertTrue(text.splitlines()[-1].startswith("dashboard:"))

    def test_extra_lines_order_after_alerts_before_dashboard(self):
        data = _spec_data(warning="部分维度抓取失败: weekly: x")
        text = build_daily_report_from_data(data, ["EXTRA-A", "EXTRA-B"])
        lines = text.splitlines()
        self.assertEqual(lines[-1], "dashboard: http://localhost:38080/#news")
        self.assertEqual(lines[-3:-1], ["EXTRA-A", "EXTRA-B"])
        self.assertLess(lines.index("⚠️ GitHub 部分维度抓取失败: weekly: x"),
                        lines.index("EXTRA-A"))

    def test_error_and_warning_truncated(self):
        data = _spec_data(error="E" * 300, warning="W" * 300)
        text = build_daily_report_from_data(data, [])
        self.assertIn("⚠️ GitHub 抓取错误: " + "E" * 120 + "\n", text + "\n")
        self.assertIn("⚠️ GitHub " + "W" * 120 + "\n", text + "\n")
        self.assertNotIn("E" * 121, text)


class TestDailyReportCli(unittest.TestCase):
    """--daily-report 的 --extra / --extra-file 参数行为 (stub 发送)."""

    def setUp(self):
        self._send = tg_notify.send_message
        self._argv = sys.argv
        self.sent = []
        tg_notify.send_message = lambda t: self.sent.append(t)
        self.json_path = tempfile.mktemp(suffix=".json")
        import json
        with open(self.json_path, "w") as f:
            json.dump(_spec_data(), f)

    def tearDown(self):
        tg_notify.send_message = self._send
        sys.argv = self._argv
        os.unlink(self.json_path)

    def test_extra_file_lines_appended_and_file_kept(self):
        alert = tempfile.mktemp(suffix=".txt")
        with open(alert, "w") as f:
            f.write("⚠️ 数据未上 main, 滞留分支: claude/epic-x\n\n  \n")
        try:
            sys.argv = ["tg_notify.py", "--daily-report", self.json_path,
                        "--extra", "A行", "--extra-file", alert]
            self.assertEqual(tg_notify.main(), 0)
            self.assertIn("A行", self.sent[0])
            self.assertIn("⚠️ 数据未上 main, 滞留分支: claude/epic-x", self.sent[0])
            self.assertNotIn("\n\n", self.sent[0])  # 空行被剔除
            self.assertTrue(os.path.exists(alert))  # 脚本不删告警文件
        finally:
            os.unlink(alert)

    def test_extra_file_missing_silently_skipped(self):
        sys.argv = ["tg_notify.py", "--daily-report", self.json_path,
                    "--extra-file", "/no/such/alert.txt"]
        self.assertEqual(tg_notify.main(), 0)
        self.assertNotIn("⚠️", self.sent[0])


if __name__ == "__main__":
    unittest.main()
