# -*- coding: utf-8 -*-
"""Offline regression checks for the GPL Hongguo TVBox Python playback adapter.

This deliberately performs no network access and does not claim real playback.
"""
import base64
import gzip
import importlib.util
import json
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

    def test_only_v5_primary_is_used_on_success(self):
        with patch.object(module, "_playback_device", return_value=PAIR) as profile, \
             patch.object(module, "_v5_playback_model", return_value=MODEL) as play:
            self.assertEqual(module._video_model(VID, {}), MODEL)
            profile.assert_called_once_with(force=True)
            play.assert_called_once()
            self.assertFalse(play.call_args.kwargs["alternate"])

    def test_v5_backup_host_only_on_empty_model(self):
        side_effect = [module._PlaybackModelError("播放模型皆為空"), MODEL]
        with patch.object(module, "_playback_device", return_value=PAIR), \
             patch.object(module, "_v5_playback_model", side_effect=side_effect) as play:
            self.assertEqual(module._video_model(VID, {}), MODEL)
            self.assertEqual([v.kwargs["alternate"] for v in play.call_args_list],
                             [False, True])

    def test_business_rejection_has_no_fallback(self):
        with patch.object(module, "_playback_device", return_value=PAIR), \
             patch.object(module, "_v5_playback_model",
                          side_effect=module._PlaybackModelError("上游拒絕播放請求（HTTP 403）")) as play:
            with self.assertRaises(module._PlaybackModelError):
                module._video_model(VID, {})
            play.assert_called_once()

    def test_no_obsolete_playback_api_targets_remain(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("/reading/bookapi/video_tab/multi_video_model/v1", source)
        self.assertNotIn("/novel/player/multi_video_model/v1/", source)
        self.assertNotIn("/novel/player/video_model/v1/", source)
        self.assertNotIn("def _playback_request(", source)
        self.assertIn('for alternate in (False, True):', source)

    def test_empty_post_resolves_via_v5_video_tab(self):
        with patch.object(module, "_playback_device", return_value=PAIR), \
             patch.object(module, "_v5_playback_model",
                          side_effect=module._PlaybackModelError("播放模型皆為空")) as post, \
             patch.object(module, "_v5_video_tab_model", return_value=MODEL) as tab:
            self.assertEqual(module._video_model(VID, {}), MODEL)
            self.assertEqual([x.kwargs["alternate"] for x in post.call_args_list],
                             [False, True])
            tab.assert_called_once()

    def test_upstream_110001_allows_video_tab_without_old_endpoint(self):
        with patch.object(module, "_playback_device", return_value=PAIR), \
             patch.object(module, "_v5_playback_model",
                          side_effect=module._PlaybackModelError("播放模型被上游拒絕（code=110001）")) as post, \
             patch.object(module, "_v5_video_tab_model", return_value=MODEL) as tab:
            self.assertEqual(module._video_model(VID, {}), MODEL)
            self.assertEqual(post.call_count, 2)
            tab.assert_called_once()

    def test_explicit_rejection_stops_before_tab(self):
        with patch.object(module, "_playback_device", return_value=PAIR), \
             patch.object(module, "_v5_playback_model",
                          side_effect=module._PlaybackModelError("上游拒絕播放請求（HTTP 403）")), \
             patch.object(module, "_v5_video_tab_model") as tab:
            with self.assertRaises(module._PlaybackModelError):
                module._video_model(VID, {})
            tab.assert_not_called()

    def test_legacy_play_url_leaf_is_not_dropped(self):
        name, item = module._select_quality(
            {"hd": {"play_url": "https://example.test/movie.mp4",
                    "quality_desc": "720", "codec_type": "h264"}}, "720")
        self.assertEqual(name, "720")
        self.assertIn("play_url", item)

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
        class MockResponse:
            def __init__(self, status, headers, body):
                self.status_code, self.headers, self.content = status, headers, body
            def raise_for_status(self):
                return None
        good = MockResponse(206, {"Content-Range": "bytes 4-7/20"}, b"abcd")
        with patch.object(module.requests, "get", return_value=good):
            self.assertEqual(module._range_get("https://example.test/movie.mp4", 4, 7),
                             (b"abcd", 20))
        bad = MockResponse(200, {"Content-Length": "20"}, b"x" * 20)
        with patch.object(module.requests, "get", return_value=bad):
            with self.assertRaises(module.HongguoPluginError):
                module._range_get("https://example.test/movie.mp4", 4, 7)


if __name__ == "__main__":
    unittest.main()
