# -*- coding: utf-8 -*-
"""Offline regression checks for the GPL Hongguo TVBox Python playback adapter.

This deliberately performs no network access and does not claim real playback.
"""
import base64
import gzip
import importlib.util
import io
import json
import struct
import subprocess
import requests
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "py" / "红果短剧.py"
spec = importlib.util.spec_from_file_location("hongguo_spider_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

VID = "7699003626647194649"
PAIR = {"device_id": "1905892595378490",
        "install_id": "1905892595382586",
        "cdid": "1d137b2b-2bc9-4cf0-b01f-f65c51e9ac86"}
MODEL = {"video_id": VID, "video_duration": 120,
         "video_list": {"hd": {"main_url": "https://example.test/video.mp4",
                               "quality_desc": "1080", "codec_type": "h264",
                               "spade_a": "example"}}}


class PlaybackContractTests(unittest.TestCase):
    def test_full_v5_signature_matches_reference_js(self):
        # The upstream GPL JS signer is used only as a test oracle; the Python
        # spider still runs without Node, Java, or a remote signing service.
        now = 1800000000123
        values = {
            "aid": "8662", "app_name": "novelread",
            "version_code": "74332", "version_name": "7.4.3.32",
            "channel": "vivo_8662_64", "device_platform": "android",
            "device_type": "PGT-AN10", "os_version": "12",
            "update_version_code": "74332",
            "iid": PAIR["install_id"], "cdid": PAIR["cdid"],
            "device_id": PAIR["device_id"],
        }
        body = gzip.compress(json.dumps({"dr_scene": "player"}).encode(), mtime=0)
        base = "https://api5-normal-sinfonlineb.fqnovel.com/novel/player/multi_video_model/player/v1"
        payload = json.dumps({
            "now": now, "base": base, "values": values,
            "body": base64.b64encode(body).decode("ascii"),
        })
        process = subprocess.run(
            ["node", str(SOURCE.parents[1] / "tests" / "v5_reference" / "reference.cjs")],
            input=payload, text=True, capture_output=True, check=True, timeout=20,
        )
        expected = json.loads(process.stdout)
        old_nonce = module._V5_PROCESS_NONCE
        old_started = module._V5_PROCESS_STARTED
        module._V5_PROCESS_NONCE = base64.urlsafe_b64encode(bytes([1]) * 18).decode().rstrip("=")
        module._V5_PROCESS_STARTED = now
        calls = [1]
        def deterministic(n):
            calls[0] += 1
            return bytes([calls[0]]) * n
        try:
            with patch.object(module.time, "time", return_value=now / 1000), \
                 patch.object(module.os, "urandom", side_effect=deterministic):
                url, headers = module._v5_sign(base, values, body)
        finally:
            module._V5_PROCESS_NONCE = old_nonce
            module._V5_PROCESS_STARTED = old_started
        self.assertEqual(url, expected["url"])
        self.assertEqual(headers, expected["headers"])

    def test_bodyless_v5_get_signature_matches_reference_js(self):
        now = 1800000000123
        pair = dict(PAIR)
        with patch.object(module, "_v5_sign") as signer:
            signer.return_value = ("https://example.test/test", {
                "x-khronos": "1800000000", "x-helios": "a", "x-medusa": "b",
            })
            endpoint, headers = module._v5_video_tab_request(VID, pair)
        base, values, body = signer.call_args.args
        self.assertIsNone(body)
        self.assertTrue(base.endswith("/reading/bookapi/video_tab/multi_video_model/v1/"))
        self.assertEqual(values["video_id"], VID)
        self.assertEqual(values["from_video_id"], "")
        self.assertEqual(values["aid"], "8662")
        self.assertFalse(any(k.lower() in ("x-ss-stub", "x-ss-req-ticket",
                                           "content-type", "content-encoding",
                                           "x-argus", "x-ladon") for k in headers))
        self.assertEqual(endpoint, "https://example.test/test")

        # Compare the same full signed empty-body request against the 7.7 JS.
        payload = json.dumps({
            "now": now, "base": base, "values": values, "body": None,
        })
        process = subprocess.run(
            ["node", str(SOURCE.parents[1] / "tests" / "v5_reference" / "reference.cjs")],
            input=payload, text=True, capture_output=True, check=True, timeout=20,
        )
        expected = json.loads(process.stdout)
        old_nonce, old_started = module._V5_PROCESS_NONCE, module._V5_PROCESS_STARTED
        module._V5_PROCESS_NONCE = base64.urlsafe_b64encode(bytes([1]) * 18).decode().rstrip("=")
        module._V5_PROCESS_STARTED = now
        calls = [1]
        def deterministic(n):
            calls[0] += 1
            return bytes([calls[0]]) * n
        try:
            with patch.object(module.time, "time", return_value=now / 1000), \
                 patch.object(module.os, "urandom", side_effect=deterministic):
                url, headers = module._v5_sign(base, values, None)
        finally:
            module._V5_PROCESS_NONCE = old_nonce
            module._V5_PROCESS_STARTED = old_started
        self.assertEqual(url, expected["url"])
        self.assertEqual(headers, expected["headers"])
        self.assertEqual(set(headers), {"x-khronos", "x-helios", "x-medusa"})

    # Public synthetic vectors from N3urda/hongguoTV (GPL-3.0), carried by
    # jackotom/hongguo-drama src/native/fixtures/playback-v5-vectors.
    def test_v5_f13_matches_32_independent_reference_vectors(self):
        data = json.loads((SOURCE.parents[1] / "tests" / "fixtures" /
                          "hongguo-signing-v5-f13.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data), 32)
        for row in data:
            with self.subTest(ts=row["ts"]):
                q, b = bytes.fromhex(row["query"]), bytes.fromhex(row["body"])
                self.assertEqual(module._v5_branch(q, b, row["ts"]), 12)
                digest = module._v5_hash_f13(q, b, row["ts"])
                self.assertEqual(digest[:16].hex(), row["digest"])
                self.assertEqual(len(digest), 20)

    def test_v5_carrier_matches_four_reference_ciphertexts(self):
        data = json.loads((SOURCE.parents[1] / "tests" / "fixtures" /
                          "hongguo-signing-v5-carrier.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data), 4)
        for row in data:
            with self.subTest(ts=row["ts"]):
                source = bytes.fromhex(row["source"])
                actual = module._V5Carrier(
                    bytes.fromhex(row["key"]), row["ts"]
                ).encrypt(source, bytes.fromhex(row["iv"]))
                self.assertEqual(actual.hex(), row["encrypted"])

    def test_v5_signer_generates_complete_gzip_post(self):
        url, headers, body = module._v5_playback_request(VID, PAIR)
        self.assertIn("/novel/player/multi_video_model/player/v1", url)
        self.assertIn("device_id=" + PAIR["device_id"], url)
        self.assertEqual(json.loads(gzip.decompress(body))
                         ["mixed_video_id_map"]["1004"], [VID])
        for name in ("x-khronos", "x-ss-stub", "x-helios", "x-medusa"):
            self.assertTrue(headers.get(name), name)
        self.assertNotIn("x-ss-req-ticket", headers)
        self.assertGreater(len(base64.b64decode(headers["x-medusa"])), 100)

    def test_exact_nested_1004_episode_selection(self):
        response = {"code": 0, "data": {"1004": {VID: {"video_model": MODEL},
                                                "999": {"video_model": {}}}}}
        self.assertEqual(module._model_from_response(response, VID), MODEL)
        with self.assertRaises(module._PlaybackModelError):
            module._model_from_response(response, "888")

    def test_v8_preload_request_matches_current_app_contract(self):
        with patch.object(module, "_v5_sign", return_value=("https://example.test/model", {})) as signer:
            url, headers, body = module._v8_preload_request(VID, PAIR)
        base, params, signed_body = signer.call_args.args
        self.assertTrue(base.endswith("/novel/player/multi_video_model/preload/v1"))
        self.assertEqual(params["version_code"], "74532")
        self.assertEqual(params["device_type"], "25053RT47C")
        self.assertEqual(signer.call_args.kwargs["field21"], 312)
        self.assertEqual(body, signed_body)
        payload = json.loads(gzip.decompress(body))
        self.assertEqual(payload["dr_scene"], "preload")
        self.assertEqual(payload["biz_param"]["device_level"], 2)
        self.assertEqual(payload["mixed_video_id_map"], {"1004": [VID]})
        self.assertEqual(headers["User-Agent"], "okhttp/4.12.0")
        self.assertEqual(headers["Content-Encoding"], "gzip")

    def test_v8_preload_signature_matches_82_reference_js(self):
        now = 1800000000123
        with patch.object(module, "_v5_sign", return_value=("https://example.test/model", {})) as mock:
            module._v8_preload_request(VID, PAIR)
        base, values, body = mock.call_args.args
        payload = json.dumps({"now": now, "base": base, "values": values,
                              "body": base64.b64encode(body).decode("ascii"), "field21": 312})
        process = subprocess.run(
            ["node", str(SOURCE.parents[1] / "tests" / "v5_reference" / "reference.cjs")],
            input=payload, text=True, capture_output=True, check=True, timeout=20,
        )
        expected = json.loads(process.stdout)
        old_nonce, old_started = module._V5_PROCESS_NONCE, module._V5_PROCESS_STARTED
        module._V5_PROCESS_NONCE = base64.urlsafe_b64encode(bytes([1]) * 18).decode().rstrip("=")
        module._V5_PROCESS_STARTED = now
        calls = [1]
        def deterministic(n):
            calls[0] += 1
            return bytes([calls[0]]) * n
        try:
            with patch.object(module.time, "time", return_value=now / 1000), \
                 patch.object(module.os, "urandom", side_effect=deterministic):
                url, headers = module._v5_sign(base, values, body, field21=312)
        finally:
            module._V5_PROCESS_NONCE, module._V5_PROCESS_STARTED = old_nonce, old_started
        self.assertEqual(url, expected["url"])
        self.assertEqual(headers, expected["headers"])

    def test_preload_is_first_and_identity_is_reused(self):
        with patch.object(module, "_playback_device", return_value=PAIR) as device, \
             patch.object(module, "_v8_preload_model", return_value=MODEL) as preload, \
             patch.object(module, "_v5_video_tab_model") as tab, \
             patch.object(module, "_v5_playback_model") as play:
            self.assertEqual(module._video_model(VID, {}), MODEL)
            device.assert_called_once_with(force=False)
            preload.assert_called_once()
            tab.assert_not_called()
            play.assert_not_called()

    def test_empty_preload_uses_video_tab_next(self):
        with patch.object(module, "_playback_device", return_value=PAIR), \
             patch.object(module, "_v8_preload_model", side_effect=module._PlaybackModelError("播放模型皆為空")), \
             patch.object(module, "_v5_video_tab_model", return_value=MODEL) as tab, \
             patch.object(module, "_v5_playback_model") as play:
            self.assertEqual(module._video_model(VID, {}), MODEL)
            tab.assert_called_once()
            play.assert_not_called()

    def test_empty_preload_and_tab_use_v5_hosts(self):
        empty = module._PlaybackModelError("播放模型皆為空")
        with patch.object(module, "_playback_device", return_value=PAIR), \
             patch.object(module, "_v8_preload_model", side_effect=empty), \
             patch.object(module, "_v5_video_tab_model", side_effect=empty), \
             patch.object(module, "_v5_playback_model", side_effect=[empty, MODEL]) as play:
            self.assertEqual(module._video_model(VID, {}), MODEL)
            self.assertEqual([x.kwargs["alternate"] for x in play.call_args_list], [False, True])

    def test_explicit_rejection_stops_before_other_routes(self):
        for message in ("上游拒絕播放請求（HTTP 403）", "上游拒絕播放請求（HTTP 429）",
                        "播放模型被上游拒絕（code=110001）"):
            with self.subTest(message=message), \
                 patch.object(module, "_playback_device", return_value=PAIR), \
                 patch.object(module, "_v8_preload_model", side_effect=module._PlaybackModelError(message)), \
                 patch.object(module, "_v5_video_tab_model") as tab, \
                 patch.object(module, "_v5_playback_model") as play:
                with self.assertRaises(module._PlaybackModelError):
                    module._video_model(VID, {})
                tab.assert_not_called()
                play.assert_not_called()

    def test_no_obsolete_playback_api_targets_remain(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("/novel/player/multi_video_model/preload/v1", source)
        self.assertIn("/reading/bookapi/video_tab/multi_video_model/v1", source)
        self.assertNotIn("/novel/player/multi_video_model/v1/", source)
        self.assertNotIn("/novel/player/video_model/v1/", source)
        self.assertNotIn("def _playback_request(", source)

    def test_public_web_360_direct_playback(self):
        from unittest.mock import Mock
        media = "https://v1.fqnovelvod.com/test.mp4"
        response = Mock(status_code=200, content=b"{}")
        response.json.return_value = {"code": 0, "main_url": media}
        with patch.object(module.requests, "post", return_value=response) as post, \
             patch.object(module, "_public_mp4_info", return_value={"quality": 360, "width": 360,
                          "height": 640, "codec": "avc1"}):
            result = module.Spider().playerContent(module._PUBLIC_LINE, module._PUBLIC_EPISODE_PREFIX + VID)
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

    def test_detail_only_advertises_full_episode_lines(self):
        sid = "123456789"
        payload = {"loaderData": {"detail_page": {"seriesDetail": {
            "series_id": sid, "series_name": "Test", "vid_list": [VID]}}}}
        with patch.object(module, "_data", return_value=payload), \
             patch.object(module, "_dm_series_load"), \
             patch.object(module, "_dm_remember_series"), \
             patch.object(module, "_dm_series_save"):
            detail = module.Spider().detailContent([sid])["list"][0]
        lines = detail["vod_play_from"].split("$$$")
        tokens = detail["vod_play_url"].split("$$$")
        self.assertEqual(lines, [name for _, name in module._HG_QUALITY_LINES])
        self.assertEqual(tokens, [
            "1$" + module.EPISODE_PREFIX + quality + ":" + VID
            for quality, _ in module._HG_QUALITY_LINES
        ])
        self.assertNotIn(module._PUBLIC_PAGE_PREFIX, detail["vod_play_url"])

    def test_public_player_page_requires_exact_episode_and_clear_full_video(self):
        from unittest.mock import Mock
        sid = "123456789"
        media = module.SITE + "/video/public/" + VID + "/movie.mp4"
        page = module.SITE + "/player/" + sid + "/" + VID
        data = {"isSuccess": True, "protectedPlayback": False, "vid": VID,
                "series_id": sid, "seriesDetail": {"series_id": sid},
                "publicVideoSeo": {"available": True, "itemId": VID, "seriesId": sid}}
        def response(protected=False, mismatch=False):
            row = dict(data, protectedPlayback=protected, vid="999" if mismatch else VID)
            html = "<script>window._ROUTER_DATA=" + json.dumps(
                {"loaderData": {"player_(series_id)/(vid)/page": row}}) + "</script>"
            html += '<script type="application/ld+json">' + json.dumps(
                {"@type": "VideoObject", "url": page, "contentUrl": media}) + "</script>"
            return Mock(status_code=200, text=html, content=html.encode())
        with patch.object(module.requests, "get", return_value=response()) as get, \
             patch.object(module, "_public_mp4_info", return_value={"quality": 1080, "width": 1080,
                          "height": 1920, "codec": "avc1"}):
            result = module.Spider().playerContent(module._PUBLIC_PAGE_LINE,
                                                    module._PUBLIC_PAGE_PREFIX + sid + ":" + VID)
            self.assertEqual(result["url"], media)
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
        for bad in (response(protected=True), response(mismatch=True)):
            with patch.object(module.requests, "get", return_value=bad):
                with self.assertRaises(module.HongguoPluginError):
                    module._public_page_media_url(sid, VID)

    def test_detail_does_not_expose_partial_episode_lines(self):
        sid = "123456789"
        for count in (0, 1):
            payload = {"loaderData": {"detail_page": {"seriesDetail": {
                "series_id": sid, "vid_list": [VID, "123456789"],
                "accessible_episode_cnt": count}}}}
            with patch.object(module, "_data", return_value=payload), \
                 patch.object(module, "_dm_series_load"), \
                 patch.object(module, "_dm_remember_series"), \
                 patch.object(module, "_dm_series_save"):
                detail = module.Spider().detailContent([sid])["list"][0]
            lines = detail["vod_play_from"].split("$$$")
            tokens = detail["vod_play_url"].split("$$$")
            self.assertEqual(len(lines), len(tokens))
            self.assertNotIn(module._PUBLIC_LINE, lines)
            self.assertTrue(all(len(line.split("#")) == 2 for line in tokens))

    def test_public_360_label_rejects_wrong_actual_resolution(self):
        with patch.object(module, "_public_web_media_url", return_value="https://v1.fqnovelvod.com/test.mp4"), \
             patch.object(module, "_public_mp4_info", return_value={"quality": 720, "width": 720,
                          "height": 1280, "codec": "avc1"}):
            result = module.Spider().playerContent(module._PUBLIC_LINE, module._PUBLIC_EPISODE_PREFIX + VID)
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

    def test_exact_quality_prefers_real_dimensions_and_never_downgrades(self):
        rows = [{"main_url": "https://example.test/video.mp4",
                 "video_meta": {"definition": "1080p", "vwidth": 360, "vheight": 640}}]
        self.assertEqual(module._select_quality(rows, "360", strict=True)[0], "360")
        with self.assertRaises(module._PlaybackModelError):
            module._select_quality(rows, "1080", strict=True)
        rows[0]["video_meta"].update(vwidth=1080, vheight=1920)
        self.assertEqual(module._select_quality(rows, "1080", strict=True)[0], "1080")

    def test_empty_response_does_not_rotate_registered_identity(self):
        with patch.object(module, "_video_model", side_effect=module._PlaybackModelError("播放模型皆為空")) as model:
            with self.assertRaises(module._PlaybackModelError):
                module._video_model_rotating(VID, {})
            model.assert_called_once()

    def test_legacy_play_url_leaf_is_not_dropped(self):
        name, item = module._select_quality(
            {"hd": {"play_url": "https://example.test/movie.mp4",
                    "quality_desc": "720", "codec_type": "h264"}}, "720")
        self.assertEqual(name, "720")
        self.assertIn("play_url", item)

    def test_tail_metadata_skips_large_mdat(self):
        ftyp = struct.pack(">I4s4s", 12, b"ftyp", b"isom")
        payload = bytes(196608)
        mdat = struct.pack(">I4sQ", 1, b"mdat", len(payload) + 16) + payload
        tail = b"moov payload" * 32
        moov = struct.pack(">I4s", 0, b"moov") + tail
        data = ftyp + mdat + moov
        offset = len(ftyp + mdat)
        def read(url, start, end, deadline):
            return data[start:end + 1], len(data)
        with patch.object(module, "_range_get", side_effect=read) as get:
            self.assertEqual(module._fetch_moov("fixture"), (len(data), offset, moov))
        self.assertLessEqual(get.call_count, 3)
        for call in get.call_args_list[1:]:
            self.assertGreaterEqual(call.args[1], offset)
            self.assertEqual(call.args[3], get.call_args_list[0].args[3])

    def test_metadata_detects_cdn_size_change(self):
        head = struct.pack(">I4s", 150000, b"mdat") + bytes(65528)
        header = struct.pack(">I4s8s", 16, b"moov", bytes(8))
        with patch.object(module, "_range_get", side_effect=[(head, 150016), (header, 150017)]):
            with self.assertRaisesRegex(module.HongguoPluginError, "長度已變更"):
                module._fetch_moov("fixture")

    def test_invalid_metadata_size_does_not_trigger_large_read(self):
        for header in (struct.pack(">I4s", 7, b"free"), struct.pack(">I4s", 400, b"moov"),
                       struct.pack(">I4s", 1, b"moov")):
            with self.subTest(header=header), patch.object(
                module, "_range_get", return_value=(header, len(header))
            ) as get:
                with self.assertRaises(module.HongguoPluginError):
                    module._fetch_moov("fixture")
                self.assertEqual(get.call_count, 1)

    def test_player_reports_empty_source_before_handing_out_loopback(self):
        spider = module.Spider()
        err = module._PlaybackModelError("播放模型皆為空（8.2 官方取源）")
        with patch.object(spider, "_adopt_working_pair"), \
             patch.object(spider, "_danmaku_payload", return_value={}), \
             patch.object(module, "_start_stream_server", return_value=10010), \
             patch.object(module, "_stream_session", side_effect=err) as prepare:
            with self.assertRaisesRegex(module.HongguoPluginError, "上游沒有回傳本集播放資料"):
                spider.playerContent("超清", module.EPISODE_PREFIX + "1080:" + VID)
            self.assertEqual(prepare.call_count, 1)

    def test_player_prepares_selected_episode_before_returning_loopback(self):
        spider = module.Spider()
        import threading
        order = []
        def ready(vid, config, quality):
            order.append((vid, quality, threading.get_ident()))
        with patch.object(spider, "_adopt_working_pair"), \
             patch.object(spider, "_danmaku_payload", return_value={}), \
             patch.object(module, "_start_stream_server", return_value=10010), \
             patch.object(module, "_stream_session", side_effect=ready):
            result = spider.playerContent("高清", module.EPISODE_PREFIX + "720:" + VID)
        self.assertEqual(order, [(VID, "720", threading.get_ident())])
        self.assertIn("/hg.mp4?vid=" + VID + "&q=720", result["url"])

    def test_local_http_prefetch_error_returns_502_not_truncated_206(self):
        class BrokenMedia:
            total = 10000
            def read_range(self, start, end):
                raise module.HongguoPluginError("simulated CDN failure")

        port = module._start_stream_server()
        self.assertGreater(port, 0)
        with patch.object(module, "_stream_session", return_value=BrokenMedia()):
            result = requests.get(
                "http://127.0.0.1:%d/hg.mp4?vid=%s&q=1080" % (port, VID),
                headers={"Range": "bytes=0-4095"}, timeout=5,
            )
        self.assertEqual(result.status_code, 502)
        self.assertNotIn("Content-Range", result.headers)

    def test_local_http_prefetch_valid_range_remains_206(self):
        class WorkingMedia:
            total = 10000
            def read_range(self, start, end):
                return bytes([42]) * (end - start + 1)
            def iter_range(self, start, end):
                yield bytes([42]) * (end - start + 1)

        port = module._start_stream_server()
        self.assertGreater(port, 0)
        with patch.object(module, "_stream_session", return_value=WorkingMedia()):
            result = requests.get(
                "http://127.0.0.1:%d/hg.mp4?vid=%s&q=1080" % (port, VID),
                headers={"Range": "bytes=0-4095"}, timeout=5,
            )
        self.assertEqual(result.status_code, 206)
        self.assertEqual(result.headers.get("Content-Range"), "bytes 0-4095/10000")
        self.assertEqual(result.content, bytes([42]) * 4096)

    def test_range_requires_exact_offset(self):
        good = self.media_response(206, {"Content-Range": "bytes 4-7/20"}, b"abcd")
        with patch.object(requests.Session, "get", return_value=good):
            self.assertEqual(module._range_get("https://example.test/movie.mp4", 4, 7),
                             (b"abcd", 20))
        bad = self.media_response(200, {"Content-Length": "20"}, b"x" * 20)
        with patch.object(requests.Session, "get", return_value=bad):
            with self.assertRaises(module.HongguoPluginError):
                module._range_get("https://example.test/movie.mp4", 4, 7)

    @staticmethod
    def media_response(status, headers, body=b""):
        response = requests.Response()
        response.status_code = status
        response.headers.update(headers)
        response.raw = io.BytesIO(body)
        return response

    def test_media_redirect_uses_location_with_proxy_and_preserves_range(self):
        first = "https://v1.fqnovelvod.com/first"
        final = "https://v2.qznovelvod.com/video?token=sample"
        redirects = [self.media_response(302, {"Location": "../second"}),
                     self.media_response(307, {"Location": final}),
                     self.media_response(206, {"Content-Range": "bytes 4-7/20"}, b"data")]
        with patch.dict("os.environ", {"https_proxy": "http://127.0.0.1:7890", "no_proxy": ""}), \
             patch.object(requests.adapters.HTTPAdapter, "send", side_effect=redirects) as send:
            self.assertEqual(module._range_get(first, 4, 7), (b"data", 20))
        self.assertEqual([c.args[0].url for c in send.call_args_list],
                         [first, "https://v1.fqnovelvod.com/second", final])
        for call in send.call_args_list:
            self.assertEqual(call.args[0].headers["Range"], "bytes=4-7")
            self.assertEqual(call.kwargs["proxies"]["https"], "http://127.0.0.1:7890")

    def test_media_redirect_rejected_before_contact(self):
        start = "https://v1.fqnovelvod.com/movie"
        for target in ("http://127.0.0.1/private", "//v2.fqnovelvod.com.example/test",
                       "https://u:p@v2.fqnovelvod.com/test", "https://v2.fqnovelvod.com:444/test",
                       start, "", "https://["):
            with self.subTest(target=target):
                redirect = self.media_response(302, {"Location": target})
                trap = self.media_response(206, {"Content-Range": "bytes 0-3/16"}, b"abcd")
                with patch.object(requests.adapters.HTTPAdapter, "send", side_effect=[redirect, trap]) as send:
                    with self.assertRaises(module.HongguoPluginError):
                        module._range_get(start, 0, 3)
                    self.assertEqual(send.call_count, 1)

    def test_media_retry_budget_expires_before_another_get(self):
        elapsed = [0.0]
        def stall(*args, **kwargs):
            elapsed[0] += 35
            raise requests.Timeout()
        with patch.object(module.time, "monotonic", side_effect=lambda: elapsed[0]), \
             patch.object(module.time, "sleep") as sleep, \
             patch.object(requests.Session, "get", side_effect=stall) as get:
            with self.assertRaises((module.HongguoPluginError, requests.Timeout)):
                module._range_get("https://v1.fqnovelvod.com/movie", 0, 3)
            self.assertEqual(get.call_count, 1)
            sleep.assert_not_called()

    def test_media_prefix_and_total_when_server_ignores_range(self):
        data = b"abcdefgh"
        for headers in ({}, {"Content-Length": "8"}):
            for end, expected in ((3, b"abcd"), (15, data)):
                with self.subTest(headers=headers, end=end):
                    response = self.media_response(200, headers, data)
                    with patch.object(requests.Session, "get", return_value=response):
                        self.assertEqual(module._range_get("https://v1.fqnovelvod.com/movie", 0, end),
                                         (expected, len(data)))

    def test_media_redirect_and_body_share_one_deadline(self):
        elapsed = [0.0]
        redirect = self.media_response(302, {"Location": "/video"})
        final = self.media_response(206, {"Content-Range": "bytes 0-3/12"}, b"test")
        def fetch(*args, **kwargs):
            if not elapsed[0]:
                elapsed[0] = 8.0
                return redirect
            self.assertLessEqual(kwargs["timeout"], 2.0)
            elapsed[0] = 10.1
            return final
        with patch.object(module.time, "monotonic", side_effect=lambda: elapsed[0]), \
             patch.object(requests.Session, "get", side_effect=fetch) as get:
            with self.assertRaises(module.HongguoPluginError):
                module._range_get("https://v1.fqnovelvod.com/movie", 0, 3, deadline=10.0)
            self.assertEqual(get.call_count, 2)
        self.assertTrue(final.raw.closed)

    def test_media_denial_is_terminal(self):
        for status in (401, 403, 429):
            with self.subTest(status=status), \
                 patch.object(module.time, "sleep"), \
                 patch.object(requests.Session, "get", return_value=self.media_response(status, {})) as get:
                with self.assertRaises(requests.HTTPError):
                    module._range_get("https://v1.fqnovelvod.com/movie", 0, 3)
                self.assertEqual(get.call_count, 1)



class StreamServerRecoveryTests(unittest.TestCase):
    """iOS 凍結暫停中的 App 時會關閉本機串流服務的監聽 socket。快取的連接埠若不再回應，
    播放網址就一直失效，只能重啟 App；所以回傳前必須確認它仍會回應，否則重新開啟。"""

    def tearDown(self):
        server = module._STREAM_STATE.get("server")
        module._STREAM_STATE["port"] = 0
        module._STREAM_STATE["server"] = None
        if server is not None:
            server.shutdown()
            server.server_close()

    def test_a_live_stream_server_keeps_its_port(self):
        port = module._start_stream_server()
        self.assertTrue(port)
        self.assertTrue(module._stream_server_answers(port))
        self.assertEqual(module._start_stream_server(), port)

    def test_a_closed_stream_server_is_opened_again(self):
        port = module._start_stream_server()
        closed = module._STREAM_STATE["server"]
        closed.shutdown()
        closed.server_close()
        # 狀態仍留著舊連接埠，正如 App 從凍結回來時。
        self.assertEqual(module._STREAM_STATE["port"], port)
        self.assertFalse(module._stream_server_answers(port))
        reopened = module._start_stream_server()
        self.assertTrue(module._stream_server_answers(reopened))
        self.assertIsNot(module._STREAM_STATE["server"], closed)


if __name__ == "__main__":
    unittest.main()
