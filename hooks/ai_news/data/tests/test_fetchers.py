import unittest
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


if __name__ == "__main__":
    unittest.main()
