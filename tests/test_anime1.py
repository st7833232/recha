# -*- coding: utf-8 -*-
"""Network-free regression checks for the Anime1 CatVod source."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

if "base.spider" not in sys.modules:
    base = types.ModuleType("base")
    spider_base = types.ModuleType("base.spider")
    spider_base.Spider = type("Spider", (), {})
    base.spider = spider_base
    sys.modules["base"] = base
    sys.modules["base.spider"] = spider_base

spec = importlib.util.spec_from_file_location(
    "anime1_source", Path(__file__).resolve().parents[1] / "py" / "anime1.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Response:
    def __init__(self, payload=None, text="", cookies=None, headers=None):
        self.payload = payload or {}
        self.text = text
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.status_code = 200
        self.raw = None

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class Anime1Tests(unittest.TestCase):
    def setUp(self):
        self.spider = module.Spider()
        self.rows = module._parse_catalog([
            [1910, "某動畫 第二季", "連載中(08)", 2026, "秋", "字幕組A"],
            [1900, "劇場版：動畫", "1-1", 2026, "夏", "字幕組B"],
            [1800, "校園日常", "1-12", 2025, "春", ""],
            [0, "<a href='https://anime1.pw/123'>外站</a>", "1", 2025, "夏", ""],
            ["broken"],
        ])
        self.rows[0]["cover"] = "https://image.tmdb.org/t/p/w500/abc.jpg"
        self.rows[0]["alias"] = "某动画 第二季"
        self.rows[0]["index"] = "1001:1,1002:2"

    def test_official_catalog_parsing_and_external_exclusion(self):
        self.assertEqual(len(self.rows), 3)
        self.assertEqual(self.rows[0]["season"], "秋")
        self.assertEqual(self.rows[0]["subtitle"], "字幕組A")

    def test_enriched_tmdb_poster_path_is_checked(self):
        self.assertEqual(module._poster("/abc123.jpg"),
                         "https://image.tmdb.org/t/p/w500/abc123.jpg")
        self.assertEqual(module._poster("//evil.example/a.jpg"), "")
        self.assertEqual(module._poster("http://unsafe/x.png"), "")

    def test_category_filters_compose(self):
        with patch.object(self.spider, "_catalog", return_value=self.rows):
            found = self.spider._selected("all", {"year": "2026", "season": "秋",
                                                   "status": "ongoing"})
            self.assertEqual([x["id"] for x in found], [1910])
            self.assertEqual(len(self.spider._selected("complete")), 2)
            self.assertEqual(len(self.spider._selected("special")), 1)

    def test_season_year_search_and_pages(self):
        with patch.object(self.spider, "_catalog", return_value=self.rows):
            search = self.spider.searchContent("某动画", False, "1")
            self.assertEqual(search["total"], 1)
            listed = self.spider.categoryContent("all", "2", True, {"year": "2026"})
            self.assertEqual(listed["list"], [])
            self.assertEqual(listed["page"], 2)

    def test_home_includes_catvod_filter_contract(self):
        with patch.object(self.spider, "_catalog", return_value=self.rows):
            home = self.spider.homeContent(True)
            self.assertEqual(home["class"][1]["type_id"], "current")
            self.assertEqual(home["filters"]["all"][0]["key"], "year")
            self.assertEqual(home["filters"]["all"][1]["key"], "season")
            self.assertEqual(home["list"][0]["vod_pic"], self.rows[0]["cover"])

    def test_episode_index_and_url_guards(self):
        self.assertEqual(module._episodes_from_index("1001:1,1002:,bad:2"), [
            ("第1集", "https://anime1.me/1001"),
            ("特別篇", "https://anime1.me/1002"),
        ])
        self.assertFalse(module._safe_episode("https://evil.example/1001"))
        self.assertFalse(module._safe_episode("https://anime1.me/?cat=99"))
        self.assertTrue(module._safe_episode("https://anime1.me/1001"))

    def test_html_pages_episode_order_and_pagination(self):
        page1 = """<article><h2 class="entry-title">
            <a rel="bookmark" href="https://anime1.me/1002">第2集</a></h2></article>
            <div class="nav-previous"><a href="/?cat=1910&paged=2">上一頁</a></div>"""
        page2 = """<article><h2 class="entry-title">
            <a rel="bookmark" href="https://anime1.me/1001">第1集</a></h2></article>"""
        with patch.object(self.spider, "_page_html", side_effect=[page1, page2]):
            self.assertEqual(self.spider._episodes(self.rows[0]), [
                ("第1集", "https://anime1.me/1001"),
                ("第2集", "https://anime1.me/1002"),
            ])

    def test_detail_synopsis_and_play_items(self):
        with patch.object(self.spider, "_catalog", return_value=self.rows), \
             patch.object(self.spider, "_metadata",
                          return_value={"pic": self.rows[0]["cover"], "summary": "作品的真正劇情摘要"}), \
             patch.object(self.spider, "_episodes",
                          return_value=[("第1集", "https://anime1.me/1001")]):
            detail = self.spider.detailContent(["1910"])["list"][0]
            self.assertIn("作品的真正劇情摘要", detail["vod_content"])
            self.assertEqual(detail["vod_play_from"], "Anime1")
            self.assertEqual(detail["vod_play_url"], "第1集$https://anime1.me/1001")

    def test_video_api_cookies_and_player_header(self):
        html = '<video class="video-js" data-apireq="signed%2Fpayload"></video>'
        response = Response(
            payload={"s": [{"src": "//v.anime1.me/media/1001.mp4"}]},
            cookies={"e": "e1", "p": "p1", "h": "h1"})
        with patch.object(self.spider, "_page_html", return_value=html), \
             patch.object(module.requests, "post", return_value=response) as post:
            play = self.spider.playerContent("Anime1", "https://anime1.me/1001")
            self.assertEqual(play["parse"], 0)
            self.assertEqual(play["url"], "https://v.anime1.me/media/1001.mp4")
            self.assertIn("e=e1", play["header"]["Cookie"])
            self.assertIn("p=p1", play["header"]["Cookie"])
            self.assertIn("h=h1", play["header"]["Cookie"])
            self.assertEqual(post.call_args.kwargs["data"], "d=signed%2Fpayload")

    def test_no_cookie_fails_closed(self):
        html = '<video class="video-js" data-apireq="abc"></video>'
        with patch.object(self.spider, "_page_html", return_value=html), \
             patch.object(module.requests, "post",
                          return_value=Response(payload={"s": [{"src": "/foo.mp4"}]})):
            self.assertEqual(self.spider.playerContent("Anime1", "https://anime1.me/1001")["url"], "")

    def test_bangumi_returns_description_on_verified_match(self):
        row = self.rows[0]
        bgm = Response({"data": [{"id": 12, "name": "某動畫 第二季", "date": "2026-10-01"}]})
        details = Response({"summary": "官方提供的劇情摘要", "images": {"large": "https://lain.bgm.tv/abc.jpg"}})
        with patch.object(module.requests, "post", return_value=bgm), \
             patch.object(module.requests, "get", return_value=details):
            meta = self.spider._metadata(row)
        self.assertEqual(meta["summary"], "官方提供的劇情摘要")
        self.assertEqual(meta["pic"], row["cover"])


if __name__ == "__main__":
    unittest.main()
