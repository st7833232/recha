# -*- coding: utf-8 -*-
"""Anime1.me CatVod Python spider for WebHTV (iOS/Android).

Catalog: Anime1 official animelist.json (authoritative year/season/subtitles).
Artwork/episode-index fallback: zjjscwt/anime1-enhanced (cat ID based, TMDB art).
Synopsis: Bangumi v0 (high-confidence match only; no invented descriptions).

No global HTTP calls during import. Returns dictionaries for Android and iOS.
"""
import datetime
import html
import json
import re
import time
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from base.spider import Spider as BaseSpider

HOST = "https://anime1.me"
CATALOG_URL = HOST + "/animelist.json"
ENRICHED_URL = ("https://raw.githubusercontent.com/zjjscwt/anime1-enhanced/"
                "main/animelist-enhanced.json")
BGM_SEARCH = "https://api.bgm.tv/v0/search/subjects?limit=6"
BGM_SUBJECT = "https://api.bgm.tv/v0/subjects/"
API_URL = "https://v.anime1.me/api"
ART_ROOT = "https://image.tmdb.org/t/p/w500"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"}
BGM_HEADERS = {"User-Agent": "WebHTV-Anime1/1.0 (https://github.com/st7833232/recha)",
               "Accept": "application/json", "Content-Type": "application/json"}
CATEGORIES = [
    ("latest", "最新更新"), ("current", "當季新番"),
    ("ongoing", "連載中"), ("complete", "已完結"),
    ("all", "動畫總覽"), ("special", "劇場版／OVA")
]
PER_PAGE = 24
MAX_EPISODE_PAGES = 30


def _clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", str(value or "")))).strip()


def _norm(value):
    return re.sub(r"[^\w]+", "", _clean(value).lower(), flags=re.UNICODE)


def _is_special(title):
    return bool(re.search(r"劇場版|剧场版|電影版|电影版|OVA|OAD|SP\b|Movie\b",
                          title or "", re.IGNORECASE))


def _quarter():
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    return str(today.year), ("冬" if today.month in (12, 1, 2) else
                             "春" if today.month in (3, 4, 5) else
                             "夏" if today.month in (6, 7, 8) else "秋")


def _status(episode_text):
    return "ongoing" if "連載中" in episode_text or "连载中" in episode_text else "complete"


def _poster(path):
    if isinstance(path, str) and re.match(r"^/[A-Za-z0-9_-]+\.(jpg|jpeg|png|webp)$", path, re.I):
        return ART_ROOT + path
    return ""


def _safe_episode(url):
    p = urlparse(url)
    return (p.scheme == "https" and p.hostname == "anime1.me" and
            re.fullmatch(r"/\d+/?", p.path or "") is not None)


def _opts(values):
    return [{"n": "全部", "v": ""}] + [{"n": str(x), "v": str(x)} for x in values]


def _filters():
    year, _ = _quarter()
    years = [str(y) for y in range(int(year), 2011, -1)]
    rows = [
        {"key": "year", "name": "年份", "value": _opts(years)},
        {"key": "season", "name": "季度", "value": _opts(["冬", "春", "夏", "秋"])},
        {"key": "status", "name": "狀態",
         "value": [{"n": "全部", "v": ""}, {"n": "連載中", "v": "ongoing"},
                   {"n": "已完結", "v": "complete"}]},
        {"key": "subtitle", "name": "字幕組", "value": [{"n": "全部", "v": ""}]},
        {"key": "by", "name": "排序",
         "value": [{"n": "最新收錄", "v": ""}, {"n": "年份新到舊", "v": "year"},
                   {"n": "名稱", "v": "title"}]},
    ]
    return {key: [dict(row) for row in rows] for key, _ in CATEGORIES}


def _parse_catalog(rows):
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, list) or len(row) < 6:
            continue
        try:
            cat_id = int(row[0])
        except (TypeError, ValueError):
            continue
        # ID=0 entries on anime1.pw are not supported by this site.
        if cat_id <= 0:
            continue
        result.append({"id": cat_id, "title": _clean(row[1]),
                       "episodes": str(row[2] or ""), "year": str(row[3] or ""),
                       "season": str(row[4] or ""), "subtitle": _clean(row[5]),
                       "cover": "", "alias": "", "index": ""})
    return result


def _parse_enriched(rows):
    result = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            cat_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if cat_id > 0:
            result[cat_id] = row
    return result


def _episodes_from_index(value):
    episodes = []
    for item in (value or "").split(","):
        bits = item.split(":", 1)
        if len(bits) != 2 or not bits[0].isdigit():
            continue
        episode_id = str(int(bits[0]))
        label = "第%s集" % bits[1] if bits[1] else "特別篇"
        episodes.append((label, HOST + "/" + episode_id))
    return episodes


def _episode_posts(markup, base=HOST):
    soup = BeautifulSoup(markup, "html.parser")
    episodes = []
    for link in soup.select("h2.entry-title a[href], h1.entry-title a[href]"):
        episode_url = urljoin(base, link.get("href", ""))
        if _safe_episode(episode_url):
            episodes.append((_clean(link.get_text(" ", strip=True)), episode_url))
    next_link = soup.select_one(".nav-previous a[href]")
    next_url = urljoin(base, next_link.get("href", "")) if next_link else ""
    if next_url and urlparse(next_url).hostname != "anime1.me":
        next_url = ""
    return episodes, next_url


def _stream_payload(data):
    if not isinstance(data, dict):
        return ""
    streams = data.get("s")
    if isinstance(streams, dict):
        streams = [streams]
    for stream in streams if isinstance(streams, list) else []:
        if isinstance(stream, dict) and isinstance(stream.get("src"), str):
            value = urljoin(API_URL, stream["src"])
            if urlparse(value).scheme == "https":
                return value
    return ""


def _api_cookies(response):
    cookies = {}
    for name in ("e", "p", "h"):
        value = response.cookies.get(name)
        if value:
            cookies[name] = value
    # Some HTTP wrappers combine Set-Cookie. Read all raw headers when available.
    raw = getattr(getattr(response, "raw", None), "headers", None)
    pieces = raw.getlist("Set-Cookie") if raw is not None and hasattr(raw, "getlist") else []
    if not pieces:
        pieces = [response.headers.get("Set-Cookie", "")]
    for piece in pieces:
        for key, value in re.findall(r"(?:^|[,;]\s*)([eph])=([^;,\s]+)", piece or ""):
            cookies.setdefault(key, value)
    return "; ".join("%s=%s" % (key, cookies[key]) for key in ("e", "p", "h") if key in cookies)


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.catalog_cache = (0, [])
        self.enriched_cache = (0, {})
        self.details_cache = {}

    def getName(self):
        return "Anime1 動畫"

    def init(self, extend=""):
        pass

    def _json(self, url, **kwargs):
        response = requests.get(url, headers=HEADERS, timeout=14, **kwargs)
        response.raise_for_status()
        return response.json()

    def _enriched(self):
        at, rows = self.enriched_cache
        if rows and time.time() - at < 6 * 3600:
            return rows
        try:
            rows = _parse_enriched(self._json(ENRICHED_URL))
            self.enriched_cache = (time.time(), rows)
            return rows
        except Exception:
            return rows or {}

    def _catalog(self):
        at, rows = self.catalog_cache
        if rows and time.time() - at < 20 * 60:
            return rows
        try:
            raw = _parse_catalog(self._json(CATALOG_URL))
        except Exception:
            raw = []
        enriched = self._enriched()
        if not raw:
            # Degraded mode: enhanced index has no season/subtitle information.
            raw = [{"id": cat_id, "title": _clean(x.get("n")),
                    "episodes": str(x.get("t") or ""),
                    "year": str(x.get("y") or ""), "season": "", "subtitle": "",
                    "cover": "", "alias": "", "index": ""}
                   for cat_id, x in enriched.items()]
        for item in raw:
            e = enriched.get(item["id"], {})
            item["cover"] = _poster(e.get("c"))
            item["alias"] = _clean(e.get("z"))
            item["index"] = e.get("l") if isinstance(e.get("l"), str) else ""
        if raw:
            self.catalog_cache = (time.time(), raw)
        return raw

    def _row(self, item):
        return {"vod_id": str(item["id"]), "vod_name": item["title"],
                "vod_pic": item["cover"],
                "vod_remarks": item["episodes"],
                "vod_year": item["year"],
                "type_name": item["season"] + "季" if item["season"] else "動畫"}

    def _selected(self, mode, extend=None):
        extend = extend if isinstance(extend, dict) else {}
        year_now, season_now = _quarter()
        year = str(extend.get("year") or "")
        season = str(extend.get("season") or "")
        status = str(extend.get("status") or "")
        subtitle = str(extend.get("subtitle") or "")
        items = self._catalog()
        if mode == "current":
            year = year or year_now
            season = season or season_now
        selected = []
        for item in items:
            if year and item["year"] != year:
                continue
            if season and item["season"] != season:
                continue
            if subtitle and item["subtitle"] != subtitle:
                continue
            if status and _status(item["episodes"]) != status:
                continue
            if mode == "ongoing" and _status(item["episodes"]) != "ongoing":
                continue
            if mode == "complete" and _status(item["episodes"]) != "complete":
                continue
            if mode == "special" and not _is_special(item["title"]):
                continue
            selected.append(item)
        order = str(extend.get("by") or "")
        if order == "year":
            selected.sort(key=lambda x: (x["year"], x["id"]), reverse=True)
        elif order == "title":
            selected.sort(key=lambda x: x["title"].casefold())
        # Default is the ordering of the upstream catalog, not an invented update timestamp.
        return selected

    def homeContent(self, filter=False):
        items = self._selected("latest")[:PER_PAGE]
        filters = _filters()
        # Derive subtitle choices from the catalog instead of hard-coding fan groups.
        subtitles = sorted({x["subtitle"] for x in self._catalog() if x["subtitle"]})
        subtitle_row = {"key": "subtitle", "name": "字幕組",
                        "value": _opts(subtitles[:90])}
        for group in filters.values():
            group[3] = subtitle_row
        return {"class": [{"type_id": key, "type_name": name}
                          for key, name in CATEGORIES],
                "filters": filters, "list": [self._row(x) for x in items]}

    def homeVideoContent(self):
        return {"list": [self._row(x) for x in self._selected("latest")[:PER_PAGE]]}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        mode = str(tid or "latest")
        if mode not in dict(CATEGORIES):
            mode = "all"
        selected = self._selected(mode, extend)
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        start = (page - 1) * PER_PAGE
        return {"list": [self._row(x) for x in selected[start:start + PER_PAGE]],
                "page": page, "pagecount": max(1, (len(selected) + PER_PAGE - 1) // PER_PAGE),
                "limit": PER_PAGE, "total": len(selected)}

    def searchContent(self, key, quick=False, pg="1"):
        keyword = _norm(key)
        matching = [x for x in self._catalog()
                    if keyword and (keyword in _norm(x["title"]) or
                                    keyword in _norm(x["alias"]))]
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        offset = (page - 1) * PER_PAGE
        return {"list": [self._row(x) for x in matching[offset:offset + PER_PAGE]],
                "page": page, "pagecount": max(1, (len(matching) + PER_PAGE - 1) // PER_PAGE),
                "limit": PER_PAGE, "total": len(matching)}

    def _metadata(self, item):
        identifier = item["id"]
        if identifier in self.details_cache:
            return self.details_cache[identifier]
        result = {"pic": item.get("cover", ""), "summary": ""}
        title = item["title"]
        try:
            response = requests.post(
                BGM_SEARCH, headers=BGM_HEADERS, timeout=12,
                json={"keyword": title, "sort": "match",
                      "filter": {"type": [2], "nsfw": False}})
            response.raise_for_status()
            data = response.json()
            candidates = data.get("data", []) if isinstance(data, dict) else []
            best, highest = None, 0
            target = _norm(title)
            for candidate in candidates[:6]:
                if not isinstance(candidate, dict):
                    continue
                aliases = [candidate.get("name"), candidate.get("name_cn")]
                score = max((SequenceMatcher(None, target, _norm(x)).ratio()
                             for x in aliases if x), default=0)
                date = str(candidate.get("date") or "")
                if item["year"] and date.startswith(item["year"]):
                    score += .07
                if score > highest:
                    best, highest = candidate, score
            # Avoid wrong posters/synopses for similar names or different seasons.
            if best and highest >= .76:
                sid = best.get("id")
                # GET the full summary: search only returns short metadata in some versions.
                response = requests.get(BGM_SUBJECT + str(int(sid)),
                                        headers=BGM_HEADERS, timeout=12)
                response.raise_for_status()
                detail = response.json()
                if isinstance(detail, dict):
                    result["summary"] = _clean(detail.get("summary"))
                    images = detail.get("images") or {}
                    if not result["pic"] and isinstance(images, dict):
                        url = images.get("large") or images.get("common")
                        if isinstance(url, str) and url.startswith("https://"):
                            result["pic"] = url
        except (requests.RequestException, TypeError, ValueError):
            pass
        # Retry failures after the spider session restarts, never fabricate summaries.
        self.details_cache[identifier] = result
        return result

    def _page_html(self, url):
        # Anime1 supports POST for HTML pages; a GET is a fallback for edge/CDN differences.
        for method in ("post", "get"):
            try:
                response = getattr(requests, method)(
                    url, headers={**HEADERS, "Referer": HOST + "/"}, timeout=15)
                response.raise_for_status()
                return response.text
            except requests.RequestException:
                continue
        return ""

    def _episodes(self, item):
        current = HOST + "/?cat=%s" % item["id"]
        seen_pages, seen_episode, found = set(), set(), []
        for _ in range(MAX_EPISODE_PAGES):
            if current in seen_pages:
                break
            seen_pages.add(current)
            markup = self._page_html(current)
            if not markup:
                break
            rows, next_url = _episode_posts(markup, current)
            for title, url in rows:
                if url not in seen_episode:
                    seen_episode.add(url)
                    found.append((title, url))
            if not next_url:
                break
            current = next_url
        if found:
            return list(reversed(found))  # Anime1 archive is newest first.
        # Fallback when archive HTML is unavailable.
        return _episodes_from_index(item.get("index", ""))

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            identifier = str(ids[0]) if ids else ""
        else:
            identifier = str(ids or "")
        item = next((x for x in self._catalog() if str(x["id"]) == identifier), None)
        if not item:
            return {"list": []}
        meta = self._metadata(item)
        episodes = self._episodes(item)
        play_url = "#".join(("%s$%s" % (title.replace("$", "＄").replace("#", "＃"),
                                        url)) for title, url in episodes)
        intro = meta["summary"] or "目前尚無經核實的作品劇情簡介。"
        info = ("年份：%s｜季度：%s｜更新：%s｜字幕組：%s" %
                (item["year"] or "未知", item["season"] or "未知",
                 item["episodes"] or "未知", item["subtitle"] or "未標示"))
        return {"list": [{"vod_id": identifier, "vod_name": item["title"],
                          "vod_pic": meta["pic"], "vod_year": item["year"],
                          "vod_remarks": item["episodes"], "vod_content": intro + "\n" + info,
                          "vod_play_from": "Anime1", "vod_play_url": play_url}]}

    def playerContent(self, flag, id, vipFlags=None):
        episode_url = str(id or "").strip()
        if not _safe_episode(episode_url):
            return {"parse": 1, "url": ""}  # Fail closed; do not expose foreign URLs.
        markup = self._page_html(episode_url)
        if not markup:
            return {"parse": 1, "url": ""}
        soup = BeautifulSoup(markup, "html.parser")
        video = soup.select_one("video.video-js[data-apireq]")
        if not video:
            # Some pages may supply an explicit MP4 file in a source element.
            source = soup.select_one("video.video-js source[src]")
            if source:
                url = urljoin(episode_url, source.get("src", ""))
                if url.startswith("https://") and urlparse(url).path.lower().endswith(".mp4"):
                    return {"parse": 0, "url": url,
                            "header": {"User-Agent": UA, "Referer": episode_url}}
            return {"parse": 1, "url": ""}
        token = video.get("data-apireq", "")
        if not token:
            return {"parse": 1, "url": ""}
        try:
            response = requests.post(
                API_URL, data="d=" + token,
                headers={**HEADERS, "Referer": episode_url,
                         "Content-Type": "application/x-www-form-urlencoded"},
                timeout=15)
            response.raise_for_status()
            url = _stream_payload(response.json())
            if not url:
                return {"parse": 1, "url": ""}
            cookie = _api_cookies(response)
            if not cookie:
                # The CDN normally requires access cookies; don't claim success.
                return {"parse": 1, "url": ""}
            headers = {"User-Agent": UA, "Referer": HOST + "/", "Cookie": cookie}
            return {"parse": 0, "url": url, "header": headers}
        except (requests.RequestException, ValueError, TypeError):
            return {"parse": 1, "url": ""}

    def isVideoFormat(self, url):
        return urlparse(str(url or "")).path.lower().endswith((".mp4", ".m3u8"))

    def manualVideoCheck(self):
        return False
