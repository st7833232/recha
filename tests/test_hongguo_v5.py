# -*- coding: utf-8 -*-
"""Offline regression checks for the GPL Hongguo TVBox Python playback adapter.

This deliberately performs no network access and does not claim real playback.
"""
import base64
import gzip
import importlib.util
import json
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
    def test_v5_signer_generates_complete_gzip_post(self):
        url, headers, body = module._v5_playback_request(VID, PAIR)
        self.assertIn("/novel/player/multi_video_model/player/v1", url)
        self.assertIn("device_id=" + PAIR["device_id"], url)
        self.assertEqual(json.loads(gzip.decompress(body))
                         ["mixed_video_id_map"]["1004"], [VID])
        for name in ("x-khronos", "x-ss-stub", "x-helios",
                     "x-medusa", "x-ss-req-ticket"):
            self.assertTrue(headers.get(name), name)
        self.assertGreater(len(base64.b64decode(headers["x-medusa"])), 100)

    def test_exact_nested_1004_episode_selection(self):
        response = {"code": 0, "data": {"1004": {VID: {"video_model": MODEL},
                                                "999": {"video_model": {}}}}}
        self.assertEqual(module._model_from_response(response, VID), MODEL)
        with self.assertRaises(module._PlaybackModelError):
            module._model_from_response(response, "888")

    def test_v5_is_first_model_request(self):
        with patch.object(module, "_playback_device", return_value=PAIR) as profile, \
             patch.object(module, "_v5_playback_model", return_value=MODEL) as play, \
             patch.object(module, "_video_tab_model") as obsolete:
            self.assertEqual(module._video_model(VID, {}), MODEL)
            profile.assert_called_once_with(force=True)
            play.assert_called_once()
            obsolete.assert_not_called()

    def test_legacy_play_url_leaf_is_not_dropped(self):
        name, item = module._select_quality(
            {"hd": {"play_url": "https://example.test/movie.mp4",
                    "quality_desc": "720", "codec_type": "h264"}}, "720")
        self.assertEqual(name, "720")
        self.assertIn("play_url", item)

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
