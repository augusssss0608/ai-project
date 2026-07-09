import os
import unittest
import ai_news.data.fetchers as F
from ai_news.data.fetchers import _TrendingParser


class TestTodayStarsInt(unittest.TestCase):
    def test_parses_today_stars_as_int(self):
        html = """
        <article class="Box-row">
          <h2><a href="/owner/repo">owner/repo</a></h2>
          <p class="col-9">desc</p>
          <a class="Link--muted" href="/owner/repo/stargazers">1,234</a>
          <span class="d-inline-block float-sm-right">123 stars today</span>
        </article>
        <article class="Box-row">
          <h2><a href="/a/b">a/b</a></h2>
          <p class="col-9">desc</p>
          <a class="Link--muted" href="/a/b/stargazers">9</a>
          <span class="d-inline-block float-sm-right">9 stars today</span>
        </article>
        """
        p = _TrendingParser()
        p.feed(html)
        self.assertEqual(p.items[0]["today_stars_int"], 123)
        self.assertEqual(p.items[1]["today_stars_int"], 9)
        # 排序 (123 > 9) 不出现字典序 bug
        p.items.sort(key=lambda x: x["today_stars_int"], reverse=True)
        self.assertEqual(p.items[0]["today_stars_int"], 123)


def _rss_xml(full_names):
    """构造 RSSHub trending RSS. full_names 空 -> 空 feed (0 item)."""
    items = "".join(
        f"<item><title>{n}</title><link>https://github.com/{n}</link>"
        f"<description>Stars: 1,234 Language: Go</description></item>"
        for n in full_names
    )
    return f"<rss><channel>{items}</channel></rss>".encode()


class TestTrendingRssEmptyFeedRetry(unittest.TestCase):
    """RSSHub '200 但空 feed' 必须换实例重试, 全空才抛出 (带原因), 不静默返回空."""

    def setUp(self):
        self._fetch = F._fetch
        self._inst = F.RSSHUB_INSTANCES
        self._pause = F.TRENDING_RETRY_PAUSE
        F.TRENDING_RETRY_PAUSE = 0

    def tearDown(self):
        F._fetch, F.RSSHUB_INSTANCES = self._fetch, self._inst
        F.TRENDING_RETRY_PAUSE = self._pause

    def test_empty_first_instance_falls_through_to_second(self):
        F.RSSHUB_INSTANCES = ("https://a", "https://b")
        calls = []

        def fake(url, headers=None, timeout=None):
            calls.append(url)
            return _rss_xml([]) if url.startswith("https://a") else _rss_xml(["a/b"])
        F._fetch = fake
        out = F.fetch_github_trending_rss("weekly")
        self.assertEqual([x["url"] for x in out], ["https://github.com/a/b"])
        self.assertEqual(len(calls), 2)  # 空的第一个后继续试第二个

    def test_all_empty_raises_with_reason(self):
        F.RSSHUB_INSTANCES = ("https://a", "https://b")
        F._fetch = lambda url, headers=None, timeout=None: _rss_xml([])
        with self.assertRaises(RuntimeError) as ctx:
            F.fetch_github_trending_rss("weekly")
        self.assertIn("空 feed", str(ctx.exception))


class TestFetchOnePartialWarning(unittest.TestCase):
    """部分维度失败时, fetch_one 应把原因写进 source.warning 而非静默丢弃."""

    def setUp(self):
        self._rss, self._search = F.fetch_github_trending_rss, F.fetch_github_search

    def tearDown(self):
        F.fetch_github_trending_rss, F.fetch_github_search = self._rss, self._search

    def test_partial_dim_failure_sets_warning(self):
        def rss(since, limit=25):
            if since == "weekly":
                raise RuntimeError("RSSHub trending [weekly] 所有实例无数据: 空 feed")
            return [{"url": f"u-{since}", "title": "a/b", "total_stars_int": 5}]
        F.fetch_github_trending_rss = rss
        F.fetch_github_search = lambda params: []
        res = F.fetch_one("github", {"type": "github_trending_multi", "params": {}})
        self.assertIsNone(res["error"])
        self.assertTrue(res["items"])
        self.assertIn("weekly", res["warning"])


class TestGithubTrendingMultiFailure(unittest.TestCase):
    """fetch_github_trending_multi 的失败暴露 / 降级不误报行为."""

    def setUp(self):
        self._rss, self._search = F.fetch_github_trending_rss, F.fetch_github_search

    def tearDown(self):
        F.fetch_github_trending_rss, F.fetch_github_search = self._rss, self._search

    def test_all_empty_no_exception_raises(self):
        # 关键盲区: 各源 HTTP 200 但返回空、都不抛异常时, 仍应 raise 暴露失败
        F.fetch_github_trending_rss = lambda since, limit=25: []
        F.fetch_github_search = lambda params: []
        with self.assertRaises(RuntimeError):
            F.fetch_github_trending_multi({})

    def test_all_exception_raises(self):
        def boom(*a, **k):
            raise RuntimeError("HTTP 403")
        F.fetch_github_trending_rss = boom
        F.fetch_github_search = boom
        with self.assertRaises(RuntimeError):
            F.fetch_github_trending_multi({})

    def test_partial_success_no_raise(self):
        # RSS 全挂但 total 正常 = 成功降级, 不得误报
        def boom(*a, **k):
            raise RuntimeError("HTTP 403")
        F.fetch_github_trending_rss = boom
        F.fetch_github_search = lambda params: [{
            "title": "a/b", "url": "u", "total_stars_int": 9,
            "daily_stars": 0, "weekly_stars": 0, "monthly_stars": 0,
        }]
        out = F.fetch_github_trending_multi({})
        self.assertTrue(out)
        self.assertEqual({x["dimension"] for x in out}, {"total"})

    def test_search_empty_total_falls_back_to_pool(self):
        # Jina 搜索空 (云端封 github 全局端点) 时, total 回退到 trending 池按总 star 排
        rss = [
            {"url": "u1", "title": "big/repo", "total_stars_int": 500,
             "daily_stars": 0, "weekly_stars": 0, "monthly_stars": 0},
            {"url": "u2", "title": "small/repo", "total_stars_int": 20,
             "daily_stars": 0, "weekly_stars": 0, "monthly_stars": 0},
        ]
        F.fetch_github_trending_rss = lambda since, limit=25: rss
        F.fetch_github_search = lambda params: []
        out = F.fetch_github_trending_multi({})
        total = [x for x in out if x["dimension"] == "total"]
        self.assertEqual([x["url"] for x in total], ["u1", "u2"])  # 按总 star 降序


class TestGithubSearch(unittest.TestCase):
    """fetch_github_search 走 Jina 代理: 解析 stargazers 锚点 + 描述, 失败返 []."""

    _SAMPLE = (
        "### ![Image 1](https://github.com/owner1.png?size=40)\n\n"
        "[owner1/claude-tool](https://github.com/owner1/claude-tool)\n\n"
        "A Claude helper tool.\n\n"
        "[topic](https://github.com/topics/x)\n\n"
        "*    Python\n"
        "·*   [12k](https://github.com/owner1/claude-tool/stargazers)\n"
        "·*   Updated 1 day ago\n\n"
        "### ![Image 2](https://github.com/owner2.png?size=40)\n\n"
        "[owner2/mcp-server](https://github.com/owner2/mcp-server)\n\n"
        "An MCP server.\n\n"
        "*    Go\n"
        "·*   [3,400](https://github.com/owner2/mcp-server/stargazers)\n"
    )

    def setUp(self):
        self._fetch = F._fetch

    def tearDown(self):
        F._fetch = self._fetch

    def test_parses_full_name_stars_desc(self):
        F._fetch = lambda url, headers=None, timeout=25: self._SAMPLE.encode()
        out = F.fetch_github_search({"queries": ["claude"], "pages": 1, "min_stars": 30})
        by = {it["title"]: it for it in out}
        self.assertEqual(by["owner1/claude-tool"]["total_stars_int"], 12000)
        self.assertEqual(by["owner1/claude-tool"]["desc"], "A Claude helper tool.")
        self.assertEqual(by["owner1/claude-tool"]["url"],
                         "https://github.com/owner1/claude-tool")
        self.assertEqual(by["owner2/mcp-server"]["total_stars_int"], 3400)

    def test_dedups_across_pages_and_queries(self):
        F._fetch = lambda url, headers=None, timeout=25: self._SAMPLE.encode()
        out = F.fetch_github_search({"queries": ["claude", "topic:mcp"], "pages": 2})
        self.assertEqual(sorted(it["title"] for it in out),
                         ["owner1/claude-tool", "owner2/mcp-server"])

    def test_fetch_failure_returns_empty(self):
        def boom(*a, **k):
            raise RuntimeError("network down")
        F._fetch = boom
        self.assertEqual(
            F.fetch_github_search({"queries": ["claude"], "pages": 1}), [])

    def test_no_stargazers_returns_empty(self):
        F._fetch = lambda url, headers=None, timeout=25: b"no results here"
        self.assertEqual(
            F.fetch_github_search({"queries": ["claude"], "pages": 1}), [])


class TestTrendingRetryAndJinaFallback(unittest.TestCase):
    """主源抖动按轮重试, RSSHub 全失败时走 Jina 兜底, 兜底也挂才抛错."""

    # 按 Jina 真实渲染形状 (2026-07-09 实测): 标题链接文本带空格, lang 紧贴 stargazers 链接行首
    _TRENDING_MD = (
        "## [owner1 / hot-repo](https://github.com/owner1/hot-repo)\n\n"
        "Hottest repo today.\n\n"
        "Python[1.2k](https://github.com/owner1/hot-repo/stargazers)"
        "[33](https://github.com/owner1/hot-repo/forks) Built by\n\n"
        "## [owner2 / cool-repo](https://github.com/owner2/cool-repo)\n\n"
        "[3,400](https://github.com/owner2/cool-repo/stargazers)\n"
    )

    def setUp(self):
        self._fetch = F._fetch
        self._inst = F.RSSHUB_INSTANCES
        self._pause = F.TRENDING_RETRY_PAUSE
        F.RSSHUB_INSTANCES = ("https://a",)
        F.TRENDING_RETRY_PAUSE = 0

    def tearDown(self):
        F._fetch = self._fetch
        F.RSSHUB_INSTANCES = self._inst
        F.TRENDING_RETRY_PAUSE = self._pause

    def test_timeout_then_retry_succeeds(self):
        calls = []

        def fake(url, headers=None, timeout=None):
            calls.append(url)
            if len(calls) < 3:
                raise TimeoutError("The read operation timed out")
            return _rss_xml(["a/b"])
        F._fetch = fake
        out = F.fetch_github_trending_rss("daily")
        self.assertEqual(out[0]["title"], "a/b")
        self.assertEqual(len(calls), 3)  # 前两轮超时, 第三轮成功

    def test_rsshub_dead_falls_back_to_jina(self):
        def fake(url, headers=None, timeout=None):
            if url.startswith("https://a"):
                raise TimeoutError("The read operation timed out")
            return self._TRENDING_MD.encode()
        F._fetch = fake
        out = F.fetch_github_trending_rss("daily")
        # 页面出现顺序即榜单名次
        self.assertEqual([it["title"] for it in out],
                         ["owner1/hot-repo", "owner2/cool-repo"])
        self.assertEqual(out[0]["total_stars_int"], 1200)
        self.assertEqual(out[0]["desc"], "Hottest repo today.")
        self.assertEqual(out[0]["lang"], "Python")
        self.assertEqual(out[1]["total_stars_int"], 3400)
        self.assertEqual(out[1]["desc"], "")   # 无描述仓库不误吞后续行
        self.assertEqual(out[1]["lang"], "")

    def test_rsshub_and_jina_all_dead_raises_with_reasons(self):
        def fake(url, headers=None, timeout=None):
            raise TimeoutError("The read operation timed out")
        F._fetch = fake
        with self.assertRaises(RuntimeError) as ctx:
            F.fetch_github_trending_rss("daily")
        self.assertIn("jina兜底", str(ctx.exception))
        self.assertIn("TimeoutError", str(ctx.exception))


class TestJinaKeyHeader(unittest.TestCase):
    """JINA_API_KEY 存在时带 Bearer 头 (专属配额), 不存在时匿名."""

    def setUp(self):
        self._fetch = F._fetch
        self._key = os.environ.pop("JINA_API_KEY", None)

    def tearDown(self):
        F._fetch = self._fetch
        if self._key is not None:
            os.environ["JINA_API_KEY"] = self._key
        else:
            os.environ.pop("JINA_API_KEY", None)

    def _capture(self):
        seen = {}

        def fake(url, headers=None, timeout=None):
            seen["url"] = url
            seen["headers"] = dict(headers or {})
            return b"x"
        F._fetch = fake
        return seen

    def test_with_key_sends_bearer(self):
        seen = self._capture()
        os.environ["JINA_API_KEY"] = "jina_test123"
        F._fetch_jina("https://github.com/trending?since=daily")
        self.assertEqual(seen["headers"].get("Authorization"), "Bearer jina_test123")
        self.assertTrue(seen["url"].startswith("https://r.jina.ai/"))

    def test_without_key_anonymous(self):
        seen = self._capture()
        F._fetch_jina("https://github.com/trending?since=daily")
        self.assertNotIn("Authorization", seen["headers"])


if __name__ == "__main__":
    unittest.main()
