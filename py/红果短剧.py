# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
"""Hongguo's public web catalog and playback for CatVod Python hosts.

Retains the public parsing and media inspection from recha's previous Spider.
Upstream notices and the GPL are in licenses/hongguo-jackotom/.
The public player model also follows THLRedGuo's assets/sources/hongguo.js.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import socket
import struct
import threading
import time
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests

try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    class _BaseSpider:
        pass

SITE = "https://hongguoduanju.com"


_MEDIA_CDN_DOMAINS = ("qznovelvod.com", "fqnovelvod.com", "douyinvod.com")


_PUBLIC_WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


_PUBLIC_GRADES = (1080, 720, 540, 480, 360)


_WEB_TOKEN = re.compile(r"v1_[A-Za-z0-9_-]{8,128}")


_CATALOG_EPISODE_PREFIX = "hg-catalog-v1:"


_PUBLIC_SLOT_PREFIX = "hg-web-slot-v1:"


_PUBLIC_HD_SLOT_PREFIX = "hg-web-1080-slot-v1:"


_NATIVE_SLOT_PREFIX = "hg-native-slot-v1:"


_PUBLIC_PAGE_PREFIX = "hg-public-page-v1:"


_PUBLIC_EPISODE_PREFIX = "hg-public-v1:"


EPISODE_PREFIX = "hg-episode-v1:"


_HG_CONTENT_TYPES = [
    ("real-drama", "真人剧", [
        ("", "全部"), ("romance", "爱情"), ("period", "年代"), ("comeback", "逆袭"),
        ("legend", "传奇"), ("growth", "成长"), ("family", "家庭"), ("clan", "家族"),
        ("cute-kids", "萌宝"), ("suspense", "悬疑"), ("thriller", "惊悚"), ("horror", "恐怖"),
        ("supernatural", "志怪"), ("costume", "古装"), ("fantasy", "玄幻"), ("wonder", "奇幻"),
        ("urban", "都市"), ("youth", "青春"), ("comedy", "喜剧"), ("sci-fi", "科幻"),
        ("disaster", "灾难"), ("action-adventure", "动作冒险"), ("war", "战争"),
        ("variety", "综艺"), ("drama", "剧情"),
    ]),
    ("comic-drama", "漫剧", [
        ("", "全部"), ("creative", "脑洞"), ("fantasy", "玄幻"), ("drama", "剧情"),
        ("apocalypse", "末世"), ("wealthy-family", "豪门"), ("wonder", "奇幻"),
        ("sci-fi", "科幻"), ("adventure", "冒险"),
    ]),
    ("ai-drama", "AI剧", [
        ("", "全部"), ("creative", "脑洞"), ("fantasy", "玄幻"), ("drama", "剧情"),
        ("apocalypse", "末世"), ("wealthy-family", "豪门"), ("wonder", "奇幻"),
        ("sci-fi", "科幻"), ("adventure", "冒险"),
    ]),
    ("comic", "漫画", [("", "全部")]),
]


_HG_ALIAS = {
    "all": "real-drama", "latest": "real-drama", "hot": "real-drama",
    "male": "real-drama", "female": "real-drama", "短剧": "real-drama",
    "ai_comic": "ai-drama", "ai_manju": "ai-drama", "AI漫剧": "ai-drama",
    "manju": "comic-drama", "漫剧": "comic-drama",
}


class HongguoPluginError(RuntimeError):
    pass


class _PublicAccessDenied(HongguoPluginError):
    pass


class _PublicEpisodeLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()
        self.episode_links = []
        self.anchor_path = None
        self.anchor_text = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        self.anchor_path = None
        self.anchor_text = []
        href = dict(attrs).get("href")
        if not href:
            return
        path = href.split("?", 1)[0].split("#", 1)[0]
        if path.startswith(SITE + "/"):
            path = path[len(SITE):]
        if path.startswith("/player/"):
            self.anchor_path = path.rstrip("/")
            self.paths.add(self.anchor_path)

    def handle_data(self, text):
        if self.anchor_path is not None:
            self.anchor_text.append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor_path is not None:
            match = re.fullmatch(r"\s*(?:第\s*)?([1-9][0-9]{0,3})(?:\s*集)?\s*",
                                 "".join(self.anchor_text))
            if match:
                self.episode_links.append((int(match[1]), self.anchor_path))
            self.anchor_path = None
            self.anchor_text = []


class _PlaybackMemo:
    """Keep bounded in-process results and coalesce concurrent requests for each key."""
    def __init__(self, capacity):
        self.capacity = capacity
        self.values = {}
        self.loading = {}
        self.lock = threading.Lock()

    def peek(self, key):
        with self.lock:
            record = self.values.get(key)
            return record[1] if record and record[0] > time.monotonic() else None

    def get(self, key, loader):
        with self.lock:
            record = self.values.get(key)
            if record and record[0] > time.monotonic():
                return record[1]
            future = self.loading.get(key)
            leader = future is None
            if leader:
                future = self.loading[key] = concurrent.futures.Future()
        if not leader:
            return future.result()
        try:
            value, lifetime = loader()
            with self.lock:
                self.values.pop(key, None)
                if lifetime > 0:
                    if len(self.values) >= self.capacity:
                        self.values.pop(next(iter(self.values)))
                    self.values[key] = (time.monotonic() + lifetime, value)
            future.set_result(value)
            return value
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.loading.pop(key, None)


def _episode_number(value):
    text = str(value or "")
    return int(text) if re.fullmatch(r"[1-9][0-9]{0,3}", text) else 0


def _series_count(detail):
    info = detail.get("series_episode_info")
    match = re.search(r"(?:全|共)\s*([1-9][0-9]{0,3})\s*集", str(detail.get("episode_right_text") or ""))
    return max(_episode_number(detail.get("episode_cnt")),
               _episode_number(detail.get("episode_total_cnt")),
               _episode_number(info.get("episode_total_cnt") or info.get("episode_cnt"))
               if isinstance(info, dict) else 0,
               int(match[1]) if match else 0)


def _catalog_video_ids(detail, sid):
    rows = detail.get("video_list")
    if not isinstance(rows, list):
        return {}
    catalog = {}
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or str(row.get("series_id") or sid) != sid:
            continue
        number = _episode_number(row.get("vid_index"))
        vid = str(row.get("vid") or row.get("video_id") or "")
        if not number or not re.fullmatch(r"[0-9]{1,30}", vid):
            continue
        if number in catalog or vid in ids:
            return {}
        ids.add(vid)
        catalog[number] = (vid, str(row.get("disable_play")).lower() in ("true", "1"))
    return catalog


def _decode_site_page(html, include_player_paths=False):
    m = re.search(r"(?:window\.)?_ROUTER_DATA\s*=\s*", html)
    if not m:
        return {}
    try:
        obj = json.JSONDecoder().raw_decode(html[m.end():])[0]
    except (ValueError, TypeError):
        return {}
    if not isinstance(obj, dict):
        return {}
    if include_player_paths:
        links = _PublicEpisodeLinks()
        links.feed(html)
        links.close()
        obj["_webhtv_player_paths"] = links.paths
        obj["_webhtv_episode_links"] = links.episode_links
    return obj


def _public_slots(payload, series_id):
    page = (payload.get("loaderData") or {}).get("detail_page") or {}
    detail = page.get("seriesDetail") or {}
    if page.get("isSuccess") is False or str(detail.get("series_id_str") or detail.get("series_id")) != series_id:
        return {}
    vids = detail.get("vid_list")
    paths = payload.get("_webhtv_player_paths") or set()
    if not paths:
        return {}
    if not isinstance(vids, list):
        vids = []
    limit = detail.get("accessible_episode_cnt")
    if limit is None:
        limit = max(len(vids), _series_count(detail), 1)
    elif not re.fullmatch(r"[0-9]{1,7}", str(limit)):
        return {}
    root = "/player/" + series_id
    slots = {}
    seen = set()
    for number, token in enumerate(vids[:int(limit)], 1):
        token = str(token)
        if not (_WEB_TOKEN.fullmatch(token) or re.fullmatch(r"[0-9]{1,30}", token)):
            continue
        if token in seen:
            return {}
        seen.add(token)
        if root + "/" + token in paths or (number == 1 and root in paths):
            slots[number] = token
    for number, path in payload.get("_webhtv_episode_links", ()):
        if number in slots or number > int(limit) or not path.startswith(root + "/"):
            continue
        token = path[len(root) + 1:]
        if token not in seen and (_WEB_TOKEN.fullmatch(token) or re.fullmatch(r"[0-9]{1,30}", token)):
            slots[number] = token
            seen.add(token)
    return dict(sorted(slots.items()))


def _public_headers():
    return {"User-Agent": _PUBLIC_WEB_UA, "Referer": SITE + "/"}


def _trusted_direct_url(raw, video_id=None):
    """Accept HTTPS media from this source's public CDN or its exact public-video path."""
    if not isinstance(raw, str) or not raw or len(raw) > 8192 or re.search(r"[\s\\]", raw):
        return False
    try:
        item = urlparse(raw)
        host = item.hostname or ""
        if (item.scheme != "https" or item.username is not None or item.password is not None
                or item.port not in (None, 443)):
            return False
        if host == "hongguoduanju.com":
            return bool(video_id and item.path.startswith("/video/public/%s/" % video_id))
        return any(host == d or host.endswith("." + d) for d in _MEDIA_CDN_DOMAINS)
    except ValueError:
        return False


def _public_mp4_boxes(blob: bytes):
    """Yield complete ISO BMFF children, rejecting invalid/truncated boxes."""
    at = 0
    while at < len(blob):
        if len(blob) - at < 8:
            raise HongguoPluginError("MP4 metadata truncated")
        size, kind = struct.unpack_from(">I4s", blob, at)
        header = 8
        if size == 1:
            if len(blob) - at < 16:
                raise HongguoPluginError("MP4 large box header truncated")
            size = struct.unpack_from(">Q", blob, at + 8)[0]
            header = 16
        elif size == 0:
            size = len(blob) - at
        if size < header or at + size > len(blob):
            raise HongguoPluginError("MP4 box outside metadata")
        yield kind, blob[at + header:at + size]
        at += size


def _public_clear_video_info(moov: bytes) -> dict:
    """Read coded dimensions and codec from an ordinary clear MP4; no decryption."""
    if any(marker in moov for marker in (b"pssh", b"encv", b"enca", b"sinf", b"tenc")):
        raise HongguoPluginError("公開片源不是可直接播放的未加密 MP4")
    tracks = []
    for kind, trak in _public_mp4_boxes(moov):
        if kind != b"trak":
            continue
        for media_kind, mdia in _public_mp4_boxes(trak):
            if media_kind != b"mdia":
                continue
            children = list(_public_mp4_boxes(mdia))
            if not any(k == b"hdlr" and len(v) >= 12 and v[8:12] == b"vide"
                       for k, v in children):
                continue
            for k, minf in children:
                if k != b"minf":
                    continue
                for table_kind, stbl in _public_mp4_boxes(minf):
                    if table_kind != b"stbl":
                        continue
                    for sample_kind, stsd in _public_mp4_boxes(stbl):
                        if sample_kind != b"stsd" or len(stsd) < 8:
                            continue
                        entries = list(_public_mp4_boxes(stsd[8:]))
                        if len(entries) != struct.unpack_from(">I", stsd, 4)[0]:
                            raise HongguoPluginError("MP4 sample descriptions invalid")
                        for codec, entry in entries:
                            if codec not in (b"avc1", b"avc3", b"hvc1", b"hev1") or len(entry) < 78:
                                continue
                            width, height = struct.unpack_from(">HH", entry, 24)
                            config_type = b"avcC" if codec in (b"avc1", b"avc3") else b"hvcC"
                            if not any(k == config_type and len(v) > 0
                                       for k, v in _public_mp4_boxes(entry[78:])):
                                continue
                            if 0 < width <= 7680 and 0 < height <= 7680:
                                tracks.append({"width": width, "height": height,
                                               "quality": min(width, height),
                                               "codec": codec.decode("ascii")})
    if not tracks:
        raise HongguoPluginError("公開 MP4 缺少可辨識的 H.264/HEVC 視訊軌")
    return max(tracks, key=lambda info: info["width"] * info["height"])


def _public_mp4_range(url: str, start: int, end: int, deadline: float):
    """Bounded, exact public CDN range read. A denial or redirect is terminal."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HongguoPluginError("公開片源驗證逾時")
    headers = {"User-Agent": _PUBLIC_WEB_UA, "Referer": SITE + "/",
               "Range": "bytes=%d-%d" % (start, end), "Accept-Encoding": "identity"}
    with requests.get(url, headers=headers, timeout=min(10, remaining),
                      stream=True, allow_redirects=False) as response:
        if response.status_code in _DENIED_STATUSES:
            raise _PublicAccessDenied("公開媒體拒絕播放（HTTP %d）" % response.status_code)
        if response.status_code != 206:
            raise HongguoPluginError("公開媒體不支援 Range 或拒絕播放（HTTP %d）" % response.status_code)
        match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
        if not match:
            raise HongguoPluginError("公開媒體 Content-Range 無效")
        first, last, total = map(int, match.groups())
        if first != start or total <= start or last != min(end, total - 1):
            raise HongguoPluginError("公開媒體 Range 偏移不符")
        expected = last - first + 1
        body = bytearray()
        for chunk in response.iter_content(16384):
            if time.monotonic() >= deadline or len(body) + len(chunk) > expected:
                raise HongguoPluginError("公開媒體 Range 回應過大或逾時")
            body.extend(chunk)
        if len(body) != expected:
            raise HongguoPluginError("公開媒體 Range 回應不完整")
        return bytes(body), total


def _public_mp4_info(url: str) -> dict:
    """Inspect actual coded size using bounded Range reads, including tail moov."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443)
            or not (host == "hongguoduanju.com" and parsed.path.startswith("/video/public/")
                    or any(host == d or host.endswith("." + d) for d in _MEDIA_CDN_DOMAINS))):
        raise HongguoPluginError("公開媒體主機不受信任")
    deadline = time.monotonic() + 12
    # The public 360p CDN can place an 80+ KiB moov at the start of the file.
    # Read 128 KiB first so these episodes need only one metadata request.
    head, total = _public_mp4_range(url, 0, 128 * 1024 - 1, deadline)
    if len(head) < 16 or head[4:8] != b"ftyp":
        raise HongguoPluginError("公開媒體不是 MP4")
    at = 0
    for _ in range(24):
        if at >= total:
            break
        if at + 16 <= len(head):
            prefix = head[at:at + 16]
        else:
            prefix, other_total = _public_mp4_range(url, at, min(total - 1, at + 15), deadline)
            if other_total != total:
                raise HongguoPluginError("公開媒體長度已變更")
        if len(prefix) < 8:
            break
        size, kind = struct.unpack_from(">I4s", prefix)
        header = 8
        if size == 1:
            if len(prefix) < 16:
                break
            size = struct.unpack_from(">Q", prefix, 8)[0]
            header = 16
        elif size == 0:
            size = total - at
        if size < header or at + size > total:
            raise HongguoPluginError("公開 MP4 box 越界")
        if kind == b"moov":
            if size > 2 * 1024 * 1024:
                raise HongguoPluginError("公開 MP4 metadata 過大")
            if at + size <= len(head):
                box = head[at:at + size]
            else:
                box, other_total = _public_mp4_range(url, at, at + size - 1, deadline)
                if other_total != total or len(box) != size:
                    raise HongguoPluginError("公開 MP4 metadata 不完整")
            return _public_clear_video_info(box[header:])
        at += size
    raise HongguoPluginError("公開 MP4 找不到可驗證的 moov")


def _public_web_media_url(video_id: str) -> str:
    """Resolve only the official web player's publicly supplied full 360p MP4.
    Adapted from jackotom/hongguo-drama 8.3 src/native/hongguo.js (GPL-3.0-only).
    Do not retry a refusal, scrape protected previews, or guess media URLs.
    """
    if not (re.fullmatch(r"[0-9]{1,30}", str(video_id)) or _WEB_TOKEN.fullmatch(str(video_id))):
        raise HongguoPluginError("公開分集識別無效")
    headers = {
        "User-Agent": _PUBLIC_WEB_UA, "Accept": "application/json",
        "Referer": SITE + "/", "Content-Type": "application/json",
    }
    response = requests.post(
        SITE + "/api/video/protected/fallback-play-info",
        json={"item_id": str(video_id)}, headers=headers,
        timeout=12, allow_redirects=False,
    )
    if response.status_code in _DENIED_STATUSES:
        raise _PublicAccessDenied("官網拒絕公開播放（HTTP %d）" % response.status_code)
    if response.status_code != 200:
        raise HongguoPluginError("官網公開播放暫時不可用（HTTP %d）" % response.status_code)
    if len(response.content) > 65536:
        raise HongguoPluginError("官網公開播放回應過大")
    try:
        data = response.json()
    except ValueError as error:
        raise HongguoPluginError("官網公開播放回應無效") from error
    if not isinstance(data, dict):
        raise HongguoPluginError("官網公開播放回應無效")
    base = data.get("base_resp")
    code = base.get("StatusCode", data.get("code", 0)) if isinstance(base, dict) else data.get("code", 0)
    if (any(data.get(flag) for flag in _PROTECTED_FIELDS)
            or str(code or 0) != "0" or data.get("error")):
        raise HongguoPluginError("官網未提供本集公開完整片源")
    raw = data.get("main_url")
    if not isinstance(raw, str) or not raw or len(raw) > 8192 or re.search(r"[\s\\]", raw):
        raise HongguoPluginError("官網公開媒體網址無效")
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)
                or not any(host == domain or host.endswith("." + domain) for domain in _MEDIA_CDN_DOMAINS)):
            raise ValueError("untrusted media URL")
        expires = data.get("url_expire")
        if expires not in (None, "", 0, "0") and float(expires) <= time.time() + 5:
            raise ValueError("expired media URL")
    except (TypeError, ValueError) as error:
        raise HongguoPluginError("官網公開媒體網址無效或已過期") from error
    return raw


def _clear_web_rows(player, video_id):
    """Read the clear URLs published for the currently selected episode."""
    if isinstance(player, str):
        try:
            player = json.loads(player)
        except ValueError:
            return []
    if not isinstance(player, dict):
        return []
    def restricted(row):
        return any(row.get(field) for field in _PROTECTED_FIELDS)
    if restricted(player):
        return []
    variants = player.get("video_list")
    if isinstance(variants, dict):
        variants = list(variants.values())
    rows = []
    for row in ([player] + variants if isinstance(variants, list) else [player]):
        if not isinstance(row, dict) or restricted(row):
            continue
        try:
            size = min(int(row.get("vwidth") or row.get("width") or 0),
                       int(row.get("vheight") or row.get("height") or 0))
        except (TypeError, ValueError):
            size = 0
        for field in ("main_url", "backup_url"):
            url = row.get(field)
            if _trusted_direct_url(url, video_id):
                rows.append((size, url))
    return rows


def _public_page_media_rows(series_id: str, video_id: str, first_episode=False):
    """Read the full media the exact public player page offers for this episode.
    Adapted from the public web route in hongguo-drama 8.3 (GPL-3.0-only).
    """
    if (not re.fullmatch(r"[0-9]{1,30}", str(series_id)) or not (
            re.fullmatch(r"[0-9]{1,30}", str(video_id)) or _WEB_TOKEN.fullmatch(str(video_id)))):
        raise HongguoPluginError("公開分集識別無效")
    path = "/player/" + series_id if first_episode else "/player/%s/%s" % (series_id, video_id)
    response = requests.get(SITE + path, headers={
        "User-Agent": _PUBLIC_WEB_UA, "Accept": "text/html",
        "Referer": SITE + "/",
    }, timeout=6, allow_redirects=False)
    if response.status_code in _DENIED_STATUSES:
        raise _PublicAccessDenied("官網暫未開放此播放頁（HTTP %d）" % response.status_code)
    if response.status_code != 200:
        raise HongguoPluginError("官網公開頁面不可用（HTTP %d）" % response.status_code)
    if len(response.content) > 2 * 1024 * 1024:
        raise HongguoPluginError("官網公開頁面回應過大")
    html = response.text
    router = _decode_site_page(html)
    loader = router.get("loaderData")
    data = (loader.get("player_(series_id)/(vid)/page") or loader.get("player_(series_id)/page")) if isinstance(loader, dict) else None
    if not isinstance(data, dict):
        raise HongguoPluginError("官網缺少目前分集資料")
    detail = data.get("seriesDetail")
    seo = data.get("publicVideoSeo")
    if (data.get("isSuccess") is False or str(data.get("vid")) != video_id
            or str(data.get("series_id")) != series_id
            or not isinstance(detail, dict) or str(detail.get("series_id")) != series_id):
        raise HongguoPluginError("本集未確認為公開完整影片")
    public = (isinstance(seo, dict) and seo.get("available") is True
              and str(seo.get("itemId")) == video_id and str(seo.get("seriesId")) == series_id)
    if data.get("protectedPlayback") is True:
        if not public:
            raise _PublicAccessDenied("本集未開放公開完整播放")
        try:
            return [(0, _public_web_media_url(video_id))]
        except HongguoPluginError as error:
            raise _PublicAccessDenied(str(error)) from error
    if data.get("protectedPlayback") is not False:
        raise HongguoPluginError("本集未確認為公開完整影片")
    rows = _clear_web_rows(data.get("video_player_info"), video_id)
    if not public:
        return rows
    for script in re.finditer(r"<script\b([^>]*)>([\s\S]*?)</script\s*>", html, re.I):
        if not re.search(r"""\btype\s*=\s*["']application/ld\+json["']""", script.group(1), re.I):
            continue
        try:
            obj = json.loads(script.group(2))
            if not isinstance(obj, dict) or obj.get("@type") != "VideoObject":
                continue
            media = obj.get("contentUrl")
            if not isinstance(media, str) or len(media) > 8192 or re.search(r"[\s\\]", media):
                continue
            target = urlparse(media)
            if (target.scheme != "https" or target.username is not None or target.password is not None
                    or target.port not in (None, 443)):
                continue
            # Restrict to the official episode-specific public media path.
            if target.hostname != "hongguoduanju.com" or not target.path.startswith("/video/public/%s/" % video_id):
                continue
            allowed_pages = {SITE + path, SITE + "/player/" + series_id}
            if obj.get("url") not in allowed_pages or (obj.get("@id") and obj["@id"] not in allowed_pages):
                continue
            rows.append((0, media))
        except (TypeError, ValueError):
            continue
    return rows


def _public_page_media_url(series_id: str, video_id: str) -> str:
    rows = _public_page_media_rows(series_id, video_id)
    for _, url in sorted(rows, key=lambda row: row[0], reverse=True):
        if not urlparse(url).path.lower().endswith(".m3u8"):
            return url
    raise HongguoPluginError("官網未提供匹配的公開完整片源")


def _hls_grade_urls(url, size_hint, video_id):
    with requests.get(url, headers=_public_headers(), stream=True, timeout=6,
                      allow_redirects=False) as response:
        if response.status_code in _DENIED_STATUSES:
            raise _PublicAccessDenied("官網暫未開放此播放清單")
        if response.status_code != 200:
            raise HongguoPluginError("HLS 播放清單不可用")
        body = bytearray()
        for chunk in response.iter_content(16384):
            body.extend(chunk)
            if len(body) > 256 * 1024:
                raise HongguoPluginError("HLS 播放清單過大")
    lines = [line.strip() for line in body.decode("utf-8-sig").splitlines() if line.strip()]
    if not lines or lines[0] != "#EXTM3U":
        raise HongguoPluginError("HLS 播放清單無效")
    variants = []
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        attrs = line.partition(":")[2]
        match = re.search(r"(?:^|,)RESOLUTION=(\d+)x(\d+)(?=,|$)", attrs, re.I)
        size = min(map(int, match.groups())) if match else 0
        uri = lines[i + 1] if i + 1 < len(lines) and not lines[i + 1].startswith("#") else ""
        variants.append((size, line, urljoin(url, uri) if uri else ""))
    if not variants:
        if size_hint in _PUBLIC_GRADES and any(line.startswith("#EXTINF:") for line in lines):
            return {size_hint: url}
        return {}
    sizes = {size for size, _, _ in variants}
    if len(sizes) == 1 and sizes.issubset(_PUBLIC_GRADES):
        return {sizes.pop(): url}
    choices = {}
    for size, tag, uri in variants:
        if size not in _PUBLIC_GRADES or size in choices or not _trusted_direct_url(uri, video_id):
            continue
        # Grouped playlists must keep their audio, captions and master-level attributes.
        if re.search(r"(?:[:,])(?:AUDIO|VIDEO|SUBTITLES|CLOSED-CAPTIONS)=", tag) or any(
                line.startswith(("#EXT-X-DEFINE:", "#EXT-X-SESSION-KEY:")) for line in lines):
            continue
        choices[size] = uri
    grouped = (sizes & set(_PUBLIC_GRADES)) - choices.keys()
    for size in grouped:
        uri = _local_hls_grade(lines, url, size, variants, video_id)
        if uri:
            choices[size] = uri
    return choices


def _local_hls_grade(lines, master, grade, variants, video_id):
    """Preserve rendition groups in a normal HLS master restricted to one resolution."""
    # Variable substitution depends on the original URL. A protected session cannot
    # be represented by this small clear-playlist adapter.
    if any(line.startswith(("#EXT-X-DEFINE:", "#EXT-X-SESSION-KEY:", "#EXT-X-CONTENT-STEERING:"))
           for line in lines) or any("{$" in line for line in lines):
        return None
    selected = [(tag, uri) for size, tag, uri in variants
                if size == grade and _trusted_direct_url(uri, video_id)]
    if not selected:
        return None
    output = ["#EXTM3U"]
    for line in lines:
        if line.startswith("#EXT-X-MEDIA:"):
            match = re.search(r'(?:[:,])URI="([^"]+)"', line)
            if match:
                target = urljoin(master, match[1])
                if not _trusted_direct_url(target, video_id):
                    return None
                line = line[:match.start(1)] + target + line[match.end(1):]
            output.append(line)
        elif line.startswith(("#EXT-X-VERSION:", "#EXT-X-INDEPENDENT-SEGMENTS", "#EXT-X-START:")):
            output.append(line)
    for tag, uri in selected:
        output.extend([tag, uri])
    data = ("\n".join(output) + "\n").encode("utf-8")
    key = hashlib.sha256(data).hexdigest()
    try:
        port = _start_stream_server()
    except (OSError, RuntimeError):
        return None
    if not port:
        return None
    _GRADE_PLAYLISTS.get(key, lambda: (data, 1800))
    return "http://127.0.0.1:%d/hg-quality/%s.m3u8" % (port, key)


def _hd_result_lifetime(url):
    expiries = []
    query = parse_qs(urlparse(url).query)
    for name, values in query.items():
        if name.lower() not in ("expire", "expires", "x-expires", "url_expire"):
            continue
        for value in values:
            if value.isascii() and value.isdigit() and len(value) in (10, 13):
                expiry = int(value) / (1000 if len(value) == 13 else 1)
                expiries.append(expiry - time.time() - 5)
    return max(0, min([300] + expiries)) if expiries else 90


def _public_choices(rows, vid):
    choices, seen = {}, set()
    errors = []
    for size, url in sorted(rows, key=lambda row: row[0], reverse=True):
        if not _trusted_direct_url(url, vid) or url in seen or _hd_result_lifetime(url) <= 0:
            continue
        seen.add(url)
        try:
            if urlparse(url).path.lower().endswith(".m3u8"):
                variants = _hls_grade_urls(url, size, vid)
            else:
                size = _public_mp4_info(url)["quality"]
                variants = {size: url} if size in _PUBLIC_GRADES else {}
            for grade, media in variants.items():
                if _hd_result_lifetime(url) > 0 and _hd_result_lifetime(media) > 0:
                    choices.setdefault(grade, media)
        except _PublicAccessDenied:
            raise
        except (HongguoPluginError, requests.RequestException, ValueError) as error:
            errors.append(error)
    if not choices and errors:
        raise errors[0]
    return choices


def _public_menu(choices, wanted=0):
    grades = [grade for grade in _PUBLIC_GRADES if grade in choices]
    if wanted:
        if wanted not in grades:
            raise HongguoPluginError("本集未提供可直放的 %dP" % wanted)
        grades = [wanted]
    if not grades:
        raise HongguoPluginError("本集暫無可用的分集畫質")
    values = []
    for grade in grades:
        values.extend(["%dP" % grade, choices[grade]])
    return {"parse": 0, "jx": 0, "playUrl": "", "url": values,
            "header": _public_headers(), "quality": values[0]}


_DENIED_STATUSES = (401, 403, 429, 451)
_PROTECTED_FIELDS = (
    "spade_a", "encrypt_info", "drm", "license_url", "protectedPlayback",
    "is_preview", "is_trial", "is_encrypted",
)
_SERIES_ID = re.compile(r"[0-9]{1,30}")
_CATEGORIES = {route: dict(categories) for route, _, categories in _HG_CONTENT_TYPES}
_DIRECTORY_MEMO = _PlaybackMemo(24)
_EPISODE_CHOICES = _PlaybackMemo(64)
_GRADE_PLAYLISTS = _PlaybackMemo(128)
_SERVER_LOCK = threading.Lock()
_SERVER = None


class _PlaylistHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self._serve(True)

    def do_HEAD(self):
        self._serve(False)

    def _serve(self, send_body):
        if self.path == "/health":
            self.send_response(204)
            self.end_headers()
            return
        match = re.fullmatch(r"/hg-quality/([a-f0-9]{64})\.m3u8", self.path)
        playlist = _GRADE_PLAYLISTS.peek(match[1]) if match else None
        if playlist is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(playlist)))
        self.end_headers()
        if send_body:
            try:
                self.wfile.write(playlist)
            except (BrokenPipeError, ConnectionResetError):
                pass


def _start_stream_server():
    global _SERVER
    with _SERVER_LOCK:
        if _SERVER:
            try:
                with socket.create_connection(_SERVER.server_address, timeout=0.5) as connection:
                    connection.sendall(b"HEAD /health HTTP/1.0\r\nHost: localhost\r\n\r\n")
                    if connection.recv(16).startswith(b"HTTP/1.0 204"):
                        return _SERVER.server_port
            except OSError:
                pass
            stale = _SERVER
            _SERVER = None
            stale.server_close()
            threading.Thread(target=stale.shutdown, daemon=True).start()

        server = ThreadingHTTPServer(("127.0.0.1", 0), _PlaylistHandler)
        try:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        except RuntimeError:
            server.server_close()
            raise
        _SERVER = server
        return server.server_port


def _site_request(session, path, *, params=None, accept="text/html", max_bytes=2 * 1024 * 1024):
    headers = dict(_public_headers(), Accept=accept)
    for attempt in range(2):
        try:
            with session.get(SITE + path, headers=headers, params=params, timeout=(6, 8),
                             stream=True, allow_redirects=False) as response:
                if response.status_code in _DENIED_STATUSES:
                    raise _PublicAccessDenied("紅果官網暫時限制請求（HTTP %d）" % response.status_code)
                if response.status_code in (502, 503, 504) and attempt == 0:
                    continue
                if response.status_code != 200:
                    raise HongguoPluginError("紅果官網回應 HTTP %d" % response.status_code)
                data = bytearray()
                for chunk in response.iter_content(16384):
                    if len(data) + len(chunk) > max_bytes:
                        raise HongguoPluginError("紅果官網回應超出大小限制")
                    data.extend(chunk)
                return data.decode("utf-8-sig", errors="replace")
        except (requests.Timeout, requests.ConnectionError):
            if attempt:
                raise


def _loader_page(payload, key):
    loader = payload.get("loaderData")
    page = loader.get(key) if isinstance(loader, dict) else None
    return page if isinstance(page, dict) else {}


def _series_item(row):
    if not isinstance(row, dict):
        return None
    data = row.get("video_data")
    if isinstance(data, dict):
        row = {**row, **data}
    sid = str(row.get("series_id_str") or row.get("series_id") or "")
    if not _SERIES_ID.fullmatch(sid):
        return None
    count = _series_count(row)
    return {
        "vod_id": sid,
        "vod_name": str(row.get("series_name") or row.get("series_title") or row.get("name") or ""),
        "vod_pic": str(row.get("series_cover") or row.get("cover_url") or ""),
        "vod_remarks": str(row.get("episode_right_text") or ("全%d集" % count if count else "")),
        "vod_content": str(row.get("series_intro") or ""),
    }


def _page_number(raw, default=1, minimum=1):
    try:
        return max(minimum, int(raw))
    except (ValueError, TypeError, OverflowError):
        return default


def _listing(rows, page, pages=1, total=0):
    seen = set()
    result = []
    for row in rows if isinstance(rows, list) else []:
        item = _series_item(row)
        if item and item["vod_id"] not in seen:
            seen.add(item["vod_id"])
            result.append(item)
    return {
        "page": page,
        "pagecount": _page_number(pages),
        "limit": len(result),
        "total": max(len(result), _page_number(total, default=0, minimum=0)),
        "list": result,
    }


def _load_series_directory(sid):
    html = _site_request(requests, "/detail", params={"series_id": sid})
    payload = _decode_site_page(html, include_player_paths=True)
    page = _loader_page(payload, "detail_page")
    detail = page.get("seriesDetail")
    if (page.get("isSuccess") is False or not isinstance(detail, dict)
            or str(detail.get("series_id_str") or detail.get("series_id")) != sid):
        raise HongguoPluginError("官網暫無此劇詳情")

    catalog = _catalog_video_ids(detail, sid)
    videos = detail.get("vid_list")
    if not isinstance(videos, list):
        videos = []
    numeric = {index: str(vid) for index, vid in enumerate(videos, start=1)
               if _SERIES_ID.fullmatch(str(vid))}
    slots = _public_slots(payload, sid)
    blocked = {number for number, (_, disabled) in catalog.items() if disabled}
    accessible = detail.get("accessible_episode_cnt")
    if accessible is not None:
        limit = _page_number(accessible, default=0, minimum=0)
        count = max(_series_count(detail), len(videos), max(slots, default=0), max(catalog, default=0))
        blocked.update(range(limit + 1, count + 1))

    media = {}
    rows = detail.get("video_list")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            number = _episode_number(row.get("vid_index"))
            entry = catalog.get(number)
            vid = str(row.get("vid") or row.get("video_id") or "")
            if (entry != (vid, False) or number in blocked
                    or str(row.get("series_id") or sid) != sid
                    or any(row.get(field) for field in _PROTECTED_FIELDS)):
                continue
            variants = _clear_web_rows(row.get("video_player_info") or row, vid)
            if variants:
                media[vid] = variants

    total = max(_series_count(detail), len(videos), max(slots, default=0), max(catalog, default=0))
    return {"detail": detail, "catalog": catalog, "numeric": numeric, "slots": slots,
            "total": min(total, 9999), "blocked": blocked, "media": media}, (20 if slots else 10)


def _series_directory(sid):
    return _DIRECTORY_MEMO.get(sid, lambda: _load_series_directory(sid))


def _category(route, option, page):
    path = "/category/" + route
    if option and option in _CATEGORIES[route]:
        path += "/" + option
    params = {"page": page} if page > 1 else None
    body = _site_request(requests, path, params=params)
    return _loader_page(_decode_site_page(body), "category_$")


def _browse_search(query, page):
    if page > 1:
        return _listing([], page, page)

    def browse(route):
        try:
            rows = _category(route, "", 1).get("recommendList")
            return rows if isinstance(rows, list) else []
        except (HongguoPluginError, requests.RequestException, ValueError):
            return []

    query = query.casefold()
    matches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for rows in executor.map(browse, _CATEGORIES):
            for row in rows:
                item = _series_item(row)
                if item and query in item["vod_name"].casefold():
                    matches.append(row)
    return _listing(matches, page)


def _numbered_choices(sid, number):
    def resolve():
        directory = _series_directory(sid)
        if number in directory["blocked"]:
            raise _PublicAccessDenied("第 %d 集未開放公開播放" % number)
        slot = directory["slots"].get(number)
        entry = directory["catalog"].get(number)
        vid = entry[0] if entry else directory["numeric"].get(number)
        choices = _public_choices(directory["media"].get(vid, []), vid)
        if slot:
            try:
                rows = _public_page_media_rows(sid, slot, first_episode=number == 1)
                choices.update(_public_choices(rows, slot))
            except _PublicAccessDenied:
                raise
            except (HongguoPluginError, requests.RequestException, ValueError):
                if not choices and number == 1:
                    # Some public first episodes link directly to their own ID.
                    try:
                        rows = _public_page_media_rows(sid, slot)
                        choices.update(_public_choices(rows, slot))
                    except _PublicAccessDenied:
                        raise
                    except (HongguoPluginError, requests.RequestException, ValueError):
                        pass
        if not choices:
            raise HongguoPluginError("第 %d 集目前無公開完整片源" % number)
        return choices, min(_hd_result_lifetime(url) for url in choices.values())

    return _EPISODE_CHOICES.get((sid, number), resolve)


def _direct_result(url, info):
    return {"parse": 0, "jx": 0, "playUrl": "", "url": url, "header": _public_headers(),
            "quality": "%dP" % info["quality"], "width": info["width"], "height": info["height"],
            "codec": info["codec"]}


def _legacy_episode(token):
    quality, sep, vid = token.partition(":")
    if not sep:
        quality, vid = "auto", quality
    if not (_SERIES_ID.fullmatch(vid) or _WEB_TOKEN.fullmatch(vid)):
        raise HongguoPluginError("舊分集識別碼已失效，請重新開啟詳情選集")
    url = _public_web_media_url(vid)
    info = _public_mp4_info(url)
    if info["quality"] not in _PUBLIC_GRADES or quality not in ("auto", str(info["quality"])):
        raise HongguoPluginError("此集目前沒有指定的公開畫質，請重新開啟詳情選集")
    return _direct_result(url, info)


def _playback(token):
    if token.startswith(_CATALOG_EPISODE_PREFIX):
        match = re.fullmatch(r"(auto|1080|720|540|480|360):([0-9]{1,30}):([1-9][0-9]{0,3}):(?:[0-9]{1,30}|pending|disabled|listed)",
                             token[len(_CATALOG_EPISODE_PREFIX):])
        if match:
            grade, sid, number = match.groups()
            if token.endswith(":disabled"):
                raise _PublicAccessDenied("此集未開放公開播放")
            return _public_menu(_numbered_choices(sid, int(number)), 0 if grade == "auto" else int(grade))

    for prefix, grade in ((_NATIVE_SLOT_PREFIX, 0), (_PUBLIC_SLOT_PREFIX, 360),
                          (_PUBLIC_HD_SLOT_PREFIX, 1080)):
        if token.startswith(prefix):
            match = re.fullmatch(r"([0-9]{1,30}):([1-9][0-9]{0,3})", token[len(prefix):])
            if match:
                return _public_menu(_numbered_choices(match[1], int(match[2])), grade)
            break

    if token.startswith(_PUBLIC_EPISODE_PREFIX):
        return _legacy_episode("360:" + token[len(_PUBLIC_EPISODE_PREFIX):])
    if token.startswith(EPISODE_PREFIX):
        return _legacy_episode(token[len(EPISODE_PREFIX):])

    if token.startswith(_PUBLIC_PAGE_PREFIX):
        match = re.fullmatch(r"([0-9]{1,30}):([0-9]{1,30}|v1_[A-Za-z0-9_-]{8,128})",
                             token[len(_PUBLIC_PAGE_PREFIX):])
        if match:
            url = _public_page_media_url(*match.groups())
            info = _public_mp4_info(url)
            if info["quality"] in _PUBLIC_GRADES:
                return _direct_result(url, info)

    if token.startswith("hongguo:"):
        token = token[len("hongguo:"):]
    if _trusted_direct_url(token) and urlparse(token).path.lower().endswith((".mp4", ".m3u8")):
        return _public_menu(_public_choices([(0, token)], None))

    exact = re.fullmatch(r"https://(?:www\.)?hongguoduanju\.com/player/([0-9]{1,30})(?:/([0-9]{1,30}|v1_[A-Za-z0-9_-]{8,128}))?/?",
                         token)
    if exact:
        sid, vid = exact.groups()
        if not vid:
            return _public_menu(_numbered_choices(sid, 1))
        directory = _series_directory(sid)
        for number, slot in directory["slots"].items():
            if slot == vid:
                return _public_menu(_numbered_choices(sid, number))
        raise _PublicAccessDenied("本集目前未開放網頁播放")

    numbered = re.fullmatch(r"([0-9]{1,30})[/_]([1-9][0-9]{0,3})", token)
    if numbered:
        return _public_menu(_numbered_choices(numbered[1], int(numbered[2])))
    identified = re.fullmatch(r"([0-9]{1,30})_([0-9]{10,30})", token)
    if identified:
        sid, vid = identified.groups()
        directory = _series_directory(sid)
        ids = {**directory["numeric"], **{n: v for n, (v, _) in directory["catalog"].items()}}
        for number, listed in ids.items():
            if listed == vid:
                return _public_menu(_numbered_choices(sid, number))
    raise HongguoPluginError("分集識別碼已失效，請重新開啟詳情選集")


class Spider(_BaseSpider):
    def getName(self):
        return "红果短剧"

    def init(self, extend=""):
        pass

    def getDependence(self):
        return []

    def homeContent(self, filter):
        return {
            "class": [{"type_id": route, "type_name": title} for route, title, _ in _HG_CONTENT_TYPES],
            "filters": {route: [{"key": "cat", "name": "分类", "value": [
                {"n": name, "v": value} for value, name in options.items()
            ]}] for route, options in _CATEGORIES.items() if len(options) > 1},
        }

    def homeVideoContent(self):
        return {"list": self.categoryContent("real-drama", 1)["list"]}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = _page_number(pg)
        tid = str(tid or "")
        route = tid if tid in _CATEGORIES else _HG_ALIAS.get(tid, "real-drama")
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except ValueError:
                extend = None
        option = ""
        for values in (extend, filter):
            if isinstance(values, dict):
                option = str(values.get("cat") or values.get("分类") or "")
                if option:
                    break
        try:
            category = _category(route, option, page)
            pagination = category.get("pagination") or {}
            if not isinstance(pagination, dict):
                pagination = {}
            return _listing(category.get("recommendList"), page, pagination.get("totalPages"),
                            pagination.get("total"))
        except (HongguoPluginError, requests.RequestException, ValueError):
            return _listing([], page)

    def searchContent(self, key, quick=False, pg="1"):
        page = _page_number(pg)
        query = str(key or "").strip()
        if not query:
            return _listing([], page)
        try:
            with requests.Session() as session:
                # Establish the same anonymous web session used by the public search form.
                _site_request(session, "/")
                raw = _site_request(session, "/api/search/result", accept="application/json",
                                    params={"aid": "8662", "query": query, "page": page})
                payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get("searchList"):
                pages = payload.get("totalPages") or (page + 1 if payload.get("hasMore") is True else page)
                return _listing(payload.get("searchList"), page, pages, payload.get("totalCount"))
        except (HongguoPluginError, requests.RequestException, ValueError):
            pass
        if page == 1:
            try:
                body = _site_request(requests, "/search/" + quote(query, safe=""))
                rows = _loader_page(_decode_site_page(body), "search_(keyword)/page").get("searchList")
                if rows:
                    return _listing(rows, page)
            except (HongguoPluginError, requests.RequestException, ValueError):
                pass
        return _browse_search(query, page)

    def detailContent(self, ids):
        value = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        sid = str(value or "")
        if sid.startswith("hg-series-v1:"):
            sid = sid[len("hg-series-v1:"):]
        if not _SERIES_ID.fullmatch(sid):
            return {"list": []}
        try:
            directory = _series_directory(sid)
        except (HongguoPluginError, requests.RequestException, ValueError):
            return {"list": []}
        row = directory["detail"]
        item = _series_item(row)
        if not item:
            return {"list": []}
        episodes = []
        for number in range(1, directory["total"] + 1):
            entry = directory["catalog"].get(number)
            vid = entry[0] if entry else directory["numeric"].get(number)
            title = "第%d集" % number
            if number in directory["blocked"]:
                title += "（未開放）"
                vid = "disabled"
            elif number in directory["slots"]:
                vid = "listed"
            elif vid not in directory["media"]:
                title += "（待取片源）"
            token = "%sauto:%s:%d:%s" % (_CATALOG_EPISODE_PREFIX, sid, number, vid or "pending")
            episodes.append(title + "$" + token)
        actors = row.get("celebrities")
        if not isinstance(actors, list):
            actors = []
        item.update(vod_actor=",".join(str(actor["nickname"]) for actor in actors
                                     if isinstance(actor, dict) and actor.get("nickname")),
                    vod_play_from="完整選集" if episodes else "",
                    vod_play_url="#".join(episodes))
        return {"list": [item]}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            return _playback(str(id or ""))
        except (HongguoPluginError, requests.RequestException, ValueError) as error:
            message = str(error) if isinstance(error, HongguoPluginError) else "官網公開播放暫時不可用"
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}, "msg": message}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(?:mp4|m3u8)(?:$|[?#])", str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [404, "text/plain", "Not found"]

    def proxy(self, param):
        return self.localProxy(param)

    def destroy(self):
        pass
