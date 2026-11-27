# -*- coding: utf-8 -*-
"""Offline checks for the shared Hongguo Python Spider."""
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "py" / "红果短剧.py"
spec = importlib.util.spec_from_file_location("hongguo_spider_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

VID = "7699003626647194649"


class PublicPlaybackTests(unittest.TestCase):
    def test_public_web_360_direct_playback(self):
        from unittest.mock import Mock
        media = "https://v1.fqnovelvod.com/test.mp4"
        response = Mock(status_code=200, content=b"{}")
        response.json.return_value = {"code": 0, "main_url": media}
        with patch.object(module.requests, "post", return_value=response) as post, \
             patch.object(module, "_public_mp4_info", return_value={"quality": 360, "width": 360,
                          "height": 640, "codec": "avc1"}):
            result = module.Spider().playerContent("官網公開 360P", module._PUBLIC_EPISODE_PREFIX + VID)
        self.assertEqual(result["url"], media)
        self.assertEqual(result["parse"], 0)
        self.assertEqual(post.call_args.kwargs["json"], {"item_id": VID})
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_public_web_stops_on_denial_or_invalid_media(self):
        from unittest.mock import Mock
        for status, payload in (
            (403, {}), (429, {}),
            (200, {"error": "public_fallback_unavailable"}),
            (200, {"code": 0, "main_url": "https://evil.fqnovelvod.com.example/test.mp4"}),
            (200, {"code": 0, "main_url": "https://v1.fqnovelvod.com:8443/test.mp4"}),
            (200, {"code": 0, "main_url": "https://v1.fqnovelvod.com/test.mp4", "url_expire": 1}),
        ):
            with self.subTest(status=status, payload=payload):
                response = Mock(status_code=status, content=b"{}")
                response.json.return_value = payload
                with patch.object(module.requests, "post", return_value=response) as post:
                    with self.assertRaises(module.HongguoPluginError):
                        module._public_web_media_url(VID)
                    post.assert_called_once()

    def test_public_web_validates_episode_before_network(self):
        with patch.object(module.requests, "post") as post:
            with self.assertRaises(module.HongguoPluginError):
                module._public_web_media_url("not-an-episode")
            post.assert_not_called()

    def test_hls_menu_uses_actual_portrait_and_landscape_renditions(self):
        from unittest.mock import MagicMock
        master = "https://v1.fqnovelvod.com/media/master.m3u8"
        data = (b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=8,RESOLUTION=720x1280\n720.m3u8\n"
                b"#EXT-X-STREAM-INF:BANDWIDTH=9,RESOLUTION=1920x1080\n1080.m3u8\n"
                b"#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=320x240\n240.m3u8\n")
        response = MagicMock(status_code=200)
        response.__enter__.return_value = response
        response.iter_content.return_value = [data]
        with patch.object(module.requests, "get", return_value=response):
            result = module._public_menu(module._public_choices([(0, master)], VID))
        self.assertEqual(result["url"], ["1080P", master.replace("master", "1080"),
                                        "720P", master.replace("master", "720")])

    def test_grouped_hls_preserves_external_audio_in_fixed_grade(self):
        master = "https://v1.fqnovelvod.com/media/master.m3u8"
        tags = ['#EXTM3U', '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="Main",URI="a.m3u8"']
        variants = [(g, '#EXT-X-STREAM-INF:RESOLUTION=%dx1920,AUDIO="a"' % g,
                     master.replace("master", str(g))) for g in (1080, 720)]
        with patch.object(module, "_GRADE_PLAYLISTS", module._PlaybackMemo(3)), \
             patch.object(module, "_start_stream_server", return_value=4321):
            local = module._local_hls_grade(tags, master, 720, variants, VID)
            key = local.rsplit("/", 1)[1].split(".")[0]
            playlist = module._GRADE_PLAYLISTS.peek(key).decode()
        self.assertIn(master.replace("master", "a"), playlist)
        self.assertIn(master.replace("master", "720"), playlist)
        self.assertNotIn("1080", playlist)

    def test_public_player_page_requires_exact_episode_and_clear_full_video(self):
        from unittest.mock import Mock
        sid = "123456789"
        media = module.SITE + "/video/public/" + VID + "/movie.mp4"
        page = module.SITE + "/player/" + sid + "/" + VID
        data = {"isSuccess": True, "protectedPlayback": False, "vid": VID,
                "series_id": sid, "seriesDetail": {"series_id": sid},
                "publicVideoSeo": {"available": True, "itemId": VID, "seriesId": sid}}
        def response(protected=False, mismatch=False, public=True, published_url=True):
            row = dict(data, protectedPlayback=protected, vid="999" if mismatch else VID)
            if not public:
                row["publicVideoSeo"] = {"available": False}
            html = "<script>window._ROUTER_DATA=" + json.dumps(
                {"loaderData": {"player_(series_id)/(vid)/page": row}}) + "</script>"
            if published_url:
                html += '<script type="application/ld+json">' + json.dumps(
                    {"@type": "VideoObject", "url": page, "@id": page + "#video",
                     "contentUrl": media}) + "</script>"
            return Mock(status_code=200, text=html, content=html.encode())
        with patch.object(module.requests, "get", return_value=response()) as get, \
             patch.object(module, "_public_mp4_info", return_value={"quality": 1080, "width": 1080,
                          "height": 1920, "codec": "avc1"}):
            result = module.Spider().playerContent("官網公開原始畫質",
                                                    module._PUBLIC_PAGE_PREFIX + sid + ":" + VID)
            self.assertEqual(result["url"], media)
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
        for bad in (response(protected=True, public=False), response(mismatch=True)):
            with patch.object(module.requests, "get", return_value=bad):
                with self.assertRaises(module.HongguoPluginError):
                    module._public_page_media_url(sid, VID)
        with patch.object(module.requests, "get", return_value=response(protected=True)) as get, \
             patch.object(module, "_public_web_media_url", return_value=media) as fallback:
            self.assertEqual(module._public_page_media_rows(sid, VID, first_episode=True), [(0, media)])
            self.assertEqual(get.call_args.args[0], module.SITE + "/player/" + sid)
            fallback.assert_not_called()
        with patch.object(module.requests, "get", return_value=response(protected=True, published_url=False)), \
             patch.object(module, "_public_web_media_url", return_value=media) as fallback:
            self.assertEqual(module._public_page_media_rows(sid, VID), [(0, media)])
            fallback.assert_called_once_with(VID)

    def test_public_360_label_rejects_wrong_actual_resolution(self):
        with patch.object(module, "_public_web_media_url", return_value="https://v1.fqnovelvod.com/test.mp4"), \
             patch.object(module, "_public_mp4_info", return_value={"quality": 720, "width": 720,
                          "height": 1280, "codec": "avc1"}):
            result = module.Spider().playerContent("官網公開 360P", module._PUBLIC_EPISODE_PREFIX + VID)
        self.assertEqual(result["url"], "")

    def test_clear_mp4_inspector_rejects_protection_or_missing_video(self):
        for body in (b"pssh", b"encv", b"", b"\x00\x00\x00\x08free"):
            with self.subTest(body=body), self.assertRaises(module.HongguoPluginError):
                module._public_clear_video_info(body)

    def test_public_mp4_range_rejects_http_denial_and_wrong_offsets(self):
        import time
        from unittest.mock import MagicMock
        for status, headers in ((403, {}), (302, {}), (200, {}),
                                (206, {"Content-Range": "bytes 1-4/100"})):
            response = MagicMock(status_code=status, headers=headers)
            response.__enter__.return_value = response
            with patch.object(module.requests, "get", return_value=response) as get:
                with self.assertRaises(module.HongguoPluginError):
                    module._public_mp4_range("https://v1.fqnovelvod.com/test.mp4", 0, 3, time.monotonic() + 3)
                self.assertFalse(get.call_args.kwargs["allow_redirects"])
                response.iter_content.assert_not_called()

    def test_public_mp4_actual_720_and_1080_fixture(self):
        # Generate ordinary clear MP4s locally, not an upstream playback claim.
        import shutil
        import tempfile
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg unavailable")
        with tempfile.TemporaryDirectory() as directory:
            for quality, width, height, faststart in ((720, 720, 1280, False),
                                                      (1080, 1080, 1920, True)):
                path = Path(directory) / ("%d.mp4" % quality)
                cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                       "-f", "lavfi", "-i", "color=c=blue:s=%dx%d:r=10" % (width, height),
                       "-t", "0.3", "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p"]
                if faststart:
                    cmd += ["-movflags", "+faststart"]
                subprocess.run(cmd + [str(path)], check=True, timeout=30)
                data = path.read_bytes()
                def fetch(url, start, end, deadline):
                    return data[start:end + 1], len(data)
                with patch.object(module, "_public_mp4_range", side_effect=fetch):
                    result = module._public_mp4_info("https://v1.fqnovelvod.com/test.mp4")
                self.assertEqual((result["width"], result["height"], result["quality"], result["codec"]),
                                 (width, height, quality, "avc1"))
                subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                                "-i", str(path), "-f", "null", "-"], check=True, timeout=30)


class SpiderContractTests(unittest.TestCase):
    def test_invalid_catalog_media_can_use_the_same_episodes_public_player_page(self):
        sid = "123"
        stale = "https://v1.fqnovelvod.com/stale.mp4"
        public = module.SITE + "/video/public/" + VID + "/movie.mp4"
        directory = {"blocked": set(), "slots": {2: VID}, "catalog": {},
                     "numeric": {2: VID}, "media": {VID: [(360, stale)]}}
        with patch.object(module, "_series_directory", return_value=directory), \
             patch.object(module, "_EPISODE_CHOICES", module._PlaybackMemo(4)), \
             patch.object(module, "_public_mp4_info",
                          side_effect=[module.HongguoPluginError("無效媒體"), {"quality": 360}]), \
             patch.object(module, "_public_page_media_rows", return_value=[(360, public)]) as page:
            result = module.Spider().playerContent("", "hg-catalog-v1:auto:%s:2:listed" % sid)
        self.assertEqual(result["url"], ["360P", public])
        page.assert_called_once_with(sid, VID, first_episode=False)

    def test_page_one_uses_canonical_category_and_filters_are_whitelisted(self):
        category = {"recommendList": [{"series_id": "123", "series_name": "Example",
                                      "series_cover": "https://images.example/cover.jpg"}],
                    "pagination": {"totalPages": 3, "total": 25}}
        html = "<script>window._ROUTER_DATA=" + json.dumps(
            {"loaderData": {"category_$": category}}) + "</script>"
        spider = module.Spider()
        with patch.object(module, "_site_request", return_value=html) as get:
            first = spider.categoryContent("real-drama", "1", True, '{"cat":"../other"}')
            second = spider.categoryContent("ai-drama", "2", True, {"cat": "sci-fi"})
        self.assertEqual([call.args[1] for call in get.call_args_list],
                         ["/category/real-drama", "/category/ai-drama/sci-fi"])
        self.assertIsNone(get.call_args_list[0].kwargs["params"])
        self.assertEqual(get.call_args_list[1].kwargs["params"], {"page": 2})
        self.assertEqual(first["list"][0]["vod_pic"], "https://images.example/cover.jpg")
        self.assertEqual(second["pagecount"], 3)

    def test_catalog_preserves_episode_count_and_quality_is_bound_to_the_episode(self):
        sid = "123456789"
        first, second = "101", "102"
        cdn = "https://v1.fqnovelvod.com/"

        def row(vid, number, grades):
            return {"vid": vid, "vid_index": number, "video_player_info": {"video_list": [
                {"width": grade, "height": grade * 2, "main_url": cdn + vid + "-" + str(grade) + ".mp4"}
                for grade in grades]}}

        detail = {"series_id": sid, "series_name": "Example", "episode_cnt": 4,
                  "series_intro": "Synopsis", "accessible_episode_cnt": 3,
                  "video_list": [row(first, 1, [360, 1080]), row(second, 2, [480, 720]),
                                 {"vid": "103", "vid_index": 3, "disable_play": True}]}
        html = "<script>window._ROUTER_DATA=" + json.dumps(
            {"loaderData": {"detail_page": {"seriesDetail": detail}}}) + "</script>"
        spider = module.Spider()
        with patch.object(module, "_DIRECTORY_MEMO", module._PlaybackMemo(4)), \
             patch.object(module, "_EPISODE_CHOICES", module._PlaybackMemo(8)), \
             patch.object(module, "_site_request", return_value=html) as get, \
             patch.object(module, "_public_mp4_info", side_effect=lambda url: {
                 "quality": int(url.rsplit("-", 1)[1].split(".")[0])
             }):
            item = spider.detailContent([sid])["list"][0]
            episodes = item["vod_play_url"].split("#")
            tokens = [episode.split("$", 1)[1] for episode in episodes]
            one = spider.playerContent("完整選集", tokens[0])
            two = spider.playerContent("完整選集", tokens[1])
            missing_grade = spider.playerContent("", tokens[1].replace("auto:", "1080:"))
            blocked = spider.playerContent("", tokens[3])
        self.assertEqual(len(episodes), 4)
        self.assertEqual(item["vod_content"], "Synopsis")
        self.assertEqual(one["url"], ["1080P", cdn + "101-1080.mp4", "360P", cdn + "101-360.mp4"])
        self.assertEqual(two["url"][::2], ["720P", "480P"])
        self.assertEqual(missing_grade["url"], "")
        self.assertIn("未開放", blocked["msg"])
        get.assert_called_once()

    def test_deny_does_not_fall_through_to_fallback_playback(self):
        sid = "123"
        directory = {"blocked": set(), "slots": {1: VID}, "catalog": {}, "numeric": {}, "media": {}}
        with patch.object(module, "_series_directory", return_value=directory), \
             patch.object(module, "_EPISODE_CHOICES", module._PlaybackMemo(4)), \
             patch.object(module, "_public_page_media_rows",
                          side_effect=module._PublicAccessDenied("HTTP 403")), \
             patch.object(module, "_public_web_media_url") as fallback:
            result = module.Spider().playerContent("", "hg-catalog-v1:auto:%s:1:listed" % sid)
        self.assertEqual(result["url"], "")
        self.assertIn("403", result["msg"])
        fallback.assert_not_called()

    def test_search_uses_pagination_and_keeps_poster_and_intro(self):
        payload = {"searchList": [{"video_data": {"series_id": "123", "series_title": "Example",
                                               "series_cover": "https://images.example/cover.jpg",
                                               "series_intro": "Synopsis"}}],
                   "totalCount": 30, "totalPages": 3}
        with patch.object(module, "_site_request", side_effect=["", json.dumps(payload)]) as get:
            result = module.Spider().searchContent("Example", False, "2")
        self.assertEqual(result["list"][0]["vod_content"], "Synopsis")
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["pagecount"], 3)
        self.assertEqual(get.call_args.kwargs["params"]["query"], "Example")


class ShareLinkTests(unittest.TestCase):
    SID = "7710503618658454553"
    REF = "https://novelquickapp.com/s/Example/"
    PREVIEW = "https://v3-share.qznovel.com/trial.mp4?start=0&end=30"
    MEDIA = "https://v3-hgweb.qznovelvod.com/public.mp4"

    def setUp(self):
        self.spider = module.Spider()
        self.info = {
            "item": {"vod_id": self.SID, "vod_name": "溫夜潮濕", "vod_pic": ""},
            "vid": VID, "preview": self.PREVIEW, "referer": "https://novelquickapp.com/",
        }

    def test_pasted_share_text_selects_the_exact_public_episode(self):
        directory = {"slots": {2: VID}, "catalog": {}, "numeric": {}, "blocked": set()}
        with patch.object(module, "_share_info", return_value=self.info) as resolve, \
             patch.object(module, "_series_directory", return_value=directory), \
             patch.object(module, "_EPISODE_CHOICES", module._PlaybackMemo(4)), \
             patch.object(module, "_numbered_choices", return_value={360: self.MEDIA}) as play:
            hits = self.spider.searchContent("來看紅果短劇！" + self.REF + "】", False, "1")
            self.assertEqual(hits["total"], 1)
            resolve.assert_called_once_with(self.REF)
            item = self.spider.detailContent([hits["list"][0]["vod_id"]])["list"][0]
            self.assertIn("公開完整版", item["vod_remarks"])
            title, token = item["vod_play_url"].split("$", 1)
            result = self.spider.playerContent(title, token)
            self.assertEqual(result["url"], ["360P", self.MEDIA])
            self.assertEqual(result["parse"], 0)
            play.assert_called_once_with(self.SID, 2)

    def test_explicit_preview_is_labeled_and_preserves_its_original_url(self):
        with patch.object(module, "_share_info", return_value=self.info), \
             patch.object(module, "_share_public_choices",
                          side_effect=module._PublicAccessDenied("未開放")):
            hit = self.spider.searchContent(self.REF)["list"][0]
            item = self.spider.detailContent([hit["vod_id"]])["list"][0]
            self.assertIn("試看", item["vod_remarks"])
            label, token = item["vod_play_url"].split("$", 1)
            self.assertIn("試看", label)
            self.assertEqual(self.spider.playerContent(label, token)["url"], self.PREVIEW)
            full = token.replace("hg-share-v1:preview:", "hg-share-v1:full:", 1)
            self.assertEqual(self.spider.playerContent("", full)["url"], "")

    def test_unbounded_share_media_is_not_presented_as_a_preview(self):
        raw = self.PREVIEW.split("?")[0]
        self.assertEqual(module._share_preview(raw), "")
        self.assertEqual(module._share_preview(self.PREVIEW.replace("end=30", "end=0")), "")
        self.assertEqual(module._share_preview(self.PREVIEW.replace("qznovel.com", "example.com")), "")

    def test_share_landing_page_extracts_consistent_public_metadata(self):
        from unittest.mock import MagicMock
        payload = {"loaderData": {"video-animation-share_page": {
            "linkParams": {"schemeParams": {"video_id": self.SID, "vid": VID}},
            "pageData": {"used_chapter_id": VID, "series_data": {
                "title": "溫夜潮濕", "play_url": self.PREVIEW,
                "cover_url": "https://p3-novel.byteimg.com/share.jpg",
            }},
        }}}
        redirect = MagicMock(status_code=302, headers={"Location": "/ug/pages/video-animation-share?v=1"})
        redirect.__enter__.return_value = redirect
        page = MagicMock(status_code=200)
        page.__enter__.return_value = page
        page.iter_content.return_value = [("window._ROUTER_DATA = " + json.dumps(payload)).encode()]
        with patch.object(module.requests, "get", side_effect=[redirect, page]) as get:
            info, lifetime = module._load_share(self.REF)
        self.assertEqual(info["item"]["vod_id"], self.SID)
        self.assertEqual(info["item"]["vod_name"], "溫夜潮濕")
        self.assertEqual(info["vid"], VID)
        self.assertEqual(info["preview"], self.PREVIEW)
        self.assertGreater(lifetime, 0)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_share_redirect_cannot_send_a_request_to_another_host(self):
        from unittest.mock import MagicMock
        redirect = MagicMock(status_code=302, headers={"Location": "https://example.test/s/Elsewhere"})
        redirect.__enter__.return_value = redirect
        with patch.object(module.requests, "get", return_value=redirect) as get:
            with self.assertRaises(module.HongguoPluginError):
                module._load_share(self.REF)
        self.assertEqual(get.call_count, 1)

    def test_series_only_public_link_uses_the_original_catalog_identity(self):
        sid = self.SID
        directory = {"detail": {"series_id": sid, "series_name": "溫夜潮濕", "episode_cnt": 78}}
        with patch.object(module, "_series_directory", return_value=directory), \
             patch.object(module, "_SHARE_MEMO", module._PlaybackMemo(4)):
            hit = self.spider.searchContent("https://hongguoduanju.com/player/" + sid)["list"][0]
        self.assertEqual(hit["vod_id"], sid)
        self.assertEqual(hit["vod_remarks"], "全78集")

    def test_unavailable_numbered_episode_stops_before_public_page_probe(self):
        directory = {"slots": {}, "catalog": {}, "numeric": {6: VID}, "blocked": {6}}
        with patch.object(module, "_series_directory", return_value=directory), \
             patch.object(module, "_public_page_media_rows") as resolve, \
             patch.object(module, "_EPISODE_CHOICES", module._PlaybackMemo(4)):
            with self.assertRaises(module._PublicAccessDenied):
                module._share_public_choices(self.info)
        resolve.assert_not_called()

