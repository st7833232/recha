# -*- coding: utf-8 -*-
"""
8Movie CatVod Python Spider
- Android: WebHTV Chaquopy / PyLoader
- iOS: WebHTV PythonSpiderRuntime
- 僅使用目前兩端共同可用能力：base.spider + Python 標準庫
- 不依賴 lxml / BeautifulSoup / loadSpider / loadModule
"""

import html as html_lib
import re
import time
from html.parser import HTMLParser
from urllib.parse import quote, urljoin

from base.spider import Spider as BaseSpider


SITE = "https://www.8movie.com"
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
    "Mobile/15E148 Safari/604.1"
)


def _clean(value):
    if value is None:
        return ""
    text = html_lib.unescape(str(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _absolute(value, base=SITE + "/"):
    value = _clean(value)
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    return urljoin(base, value)


def _movie_id(value):
    match = re.search(r"/movies/(\d+)/?(?:[?#].*)?$", value or "", re.I)
    return match.group(1) if match else ""


def _play_info(value):
    match = re.search(r"/play/(\d+)/(\d+)/?(?:[?#].*)?$", value or "", re.I)
    return (match.group(1), match.group(2)) if match else ("", "")


def _normalize_title(value):
    value = _clean(value)
    value = re.sub(r"^\s*\d+\s*集\s*", "", value)
    value = re.sub(r"^\s*立即觀看\s*", "", value)
    value = re.sub(r"^\s*立即观看\s*", "", value)
    return _clean(value)


class _Node:
    __slots__ = ("tag", "attrs", "parent", "children", "texts")

    def __init__(self, tag="", attrs=None, parent=None):
        self.tag = (tag or "").lower()
        self.attrs = dict(attrs or [])
        self.parent = parent
        self.children = []
        self.texts = []

    def attr(self, name, default=""):
        return self.attrs.get(name, default) or default

    def classes(self):
        return set(self.attr("class").split())

    def text(self):
        parts = list(self.texts)
        for child in self.children:
            parts.append(child.text())
        return _clean(" ".join(parts))


class _DOM(HTMLParser):
    VOID = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if data:
            self.stack[-1].texts.append(data)


def _parse_dom(source):
    parser = _DOM()
    try:
        parser.feed(source or "")
    except Exception:
        pass
    return parser.root


def _walk(node):
    for child in node.children:
        yield child
        yield from _walk(child)


def _find_all(node, tag=None, cls=None, attr_name=None, attr_contains=None):
    result = []
    tag = tag.lower() if tag else None
    for item in _walk(node):
        if tag and item.tag != tag:
            continue
        if cls and cls not in item.classes():
            continue
        if attr_name:
            value = item.attr(attr_name)
            if not value:
                continue
            if attr_contains is not None and attr_contains not in value:
                continue
        result.append(item)
    return result


def _first(items):
    return items[0] if items else None


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.site = SITE
        self.headers = {
            "User-Agent": UA,
            "Referer": SITE + "/",
        }

    def getName(self):
        return "8Movie"

    def init(self, extend=""):
        self.extend = extend or ""
        if isinstance(extend, str) and extend.startswith("http"):
            self.site = extend.rstrip("/")

    def _get(self, url, referer=None, timeout=10):
        target = _absolute(url, self.site + "/")
        headers = dict(self.headers)
        headers["Referer"] = referer or (self.site + "/")
        try:
            response = self.fetch(
                target,
                headers=headers,
                timeout=timeout,
                verify=True,
                allow_redirects=True,
            )
            if hasattr(response, "encoding"):
                response.encoding = "utf-8"
            return getattr(response, "text", "") or ""
        except Exception as error:
            self.log("8Movie request failed: %s | %s" % (target, error))
            return ""

    def _anchor_title(self, anchor):
        title = _normalize_title(anchor.attr("title"))
        if title:
            return title

        for image in _find_all(anchor, tag="img"):
            title = _normalize_title(image.attr("alt"))
            if title:
                return title

        title = _normalize_title(anchor.text())
        if title:
            return title

        parent = anchor.parent
        if parent:
            return _normalize_title(parent.text())

        return ""

    def _parse_movie_list(self, source, base_url):
        root = _parse_dom(source)
        result = []
        seen = set()

        for anchor in _find_all(root, tag="a", attr_name="href"):
            href = anchor.attr("href")
            if "/movies/" not in href:
                continue

            absolute = _absolute(href, base_url)
            mid = _movie_id(absolute)
            if not mid or mid in {"1", "2", "3", "4", "5", "6"}:
                continue
            if mid in seen:
                continue

            title = self._anchor_title(anchor)
            if not title:
                continue

            seen.add(mid)
            result.append({
                "vod_id": mid,
                "vod_name": title,
                # 8Movie 列表頁目前常出現共用宣傳圖，因此刻意不放 poster。
                "vod_pic": "",
            })

        return result

    def _category_url(self, tid):
        value = str(tid or "").strip()
        if value == "update":
            return self.site + "/movies/update/"
        if value == "rank":
            return self.site + "/movies/rank/"
        if re.fullmatch(r"[1-6]", value):
            return self.site + "/movies/" + value + "/"
        return self.site + "/movies/update/"

    def homeContent(self, filter):
        return {
            "class": [
                {"type_id": "update", "type_name": "最新更新"},
                {"type_id": "rank", "type_name": "熱門排行"},
                {"type_id": "1", "type_name": "穿越古代"},
                {"type_id": "2", "type_name": "都市情愛"},
                {"type_id": "3", "type_name": "復仇爽劇"},
                {"type_id": "4", "type_name": "玄幻武俠"},
                {"type_id": "5", "type_name": "奇幻懸疑"},
                {"type_id": "6", "type_name": "其他短劇"},
            ]
        }

    def homeVideoContent(self):
        # Android waits for homeContent() AND homeVideoContent() before the
        # home result is published. Do not block its cold-start UI on HTTP.
        # Both Android variants load the first category after an empty home
        # video list; this mirrors the previously working JS startup flow.
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg))
        except Exception:
            pass

        # 目前站點的穩定路徑未確認分頁格式；避免猜 URL。
        if page > 1:
            return {
                "page": page,
                "pagecount": page,
                "limit": 0,
                "total": 0,
                "list": [],
            }

        url = self._category_url(tid)
        items = []

        # A cold-start category request can race network readiness. Retry only
        # an empty/failed result, never an already parsed list. Bounded waits
        # keep the request inside Android's 30-second VOD task timeout even
        # when remote Python-script initialisation also needs time.
        for attempt, timeout in enumerate((4, 6)):
            source = self._get(url, self.site + "/", timeout=timeout)
            if source:
                items = self._parse_movie_list(source, url)
                if items:
                    break
            if attempt == 0:
                time.sleep(0.4)

        if not items:
            self.log("8Movie category returned no parsed items: tid=%s" % tid)

        return {
            "page": 1,
            "pagecount": 1,
            "limit": len(items) or 30,
            "total": len(items),
            "list": items,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}

        raw_id = str(ids[0])
        mid = _movie_id(raw_id) or raw_id.strip()
        if not re.fullmatch(r"\d+", mid):
            return {"list": []}

        url = self.site + "/movies/" + mid + "/"
        source = self._get(url, self.site + "/")
        root = _parse_dom(source)

        title = ""
        h1 = _first(_find_all(root, tag="h1"))
        if h1:
            title = _normalize_title(h1.text())

        if not title:
            for meta in _find_all(root, tag="meta"):
                if meta.attr("property") == "og:title":
                    title = _normalize_title(meta.attr("content"))
                    if title:
                        break

        if not title:
            title_node = _first(_find_all(root, tag="title"))
            if title_node:
                title = _normalize_title(title_node.text())

        content = ""
        for meta in _find_all(root, tag="meta"):
            if meta.attr("property") == "og:description" or meta.attr("name") == "description":
                content = _clean(meta.attr("content"))
                if content:
                    break

        if not content:
            h6 = _first(_find_all(root, tag="h6"))
            if h6:
                content = h6.text()

        episodes = []
        seen = set()
        for anchor in _find_all(root, tag="a", attr_name="href"):
            href = anchor.attr("href")
            if "/play/" not in href:
                continue

            play_url = _absolute(href, url)
            movie_id, episode_id = _play_info(play_url)
            if movie_id != mid or not episode_id:
                continue
            if play_url in seen:
                continue

            seen.add(play_url)
            name = _normalize_title(anchor.text()) or _normalize_title(anchor.attr("title"))
            if not name:
                name = "第%s集" % episode_id

            episodes.append("%s$%s" % (name, play_url))

        vod = {
            "vod_id": mid,
            "vod_name": title or ("8Movie " + mid),
            "vod_pic": "",
            "vod_content": content,
            "vod_play_from": "8Movie",
            "vod_play_url": "#".join(episodes),
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_url = _absolute(id, self.site + "/")
        return {
            "parse": 1,
            "url": play_url,
            "header": {
                "User-Agent": UA,
                "Referer": self.site + "/",
            },
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            if int(pg) > 1:
                return {"list": []}
        except Exception:
            pass

        keyword = quote(str(key), safe="")
        candidates = [
            self.site + "/?s=" + keyword,
            self.site + "/search/?q=" + keyword,
            self.site + "/movies/search/?q=" + keyword,
        ]

        merged = []
        seen = set()

        for url in candidates:
            source = self._get(url, self.site + "/")
            for item in self._parse_movie_list(source, url):
                if item["vod_id"] in seen:
                    continue
                seen.add(item["vod_id"])
                merged.append(item)
            if merged:
                return {"list": merged}

        # 搜尋頁失效時，用首頁分類做小範圍 fallback。
        lowered = _clean(key).lower()
        for tid in ("update", "rank", "1", "2", "3", "4", "5", "6"):
            url = self._category_url(tid)
            source = self._get(url, self.site + "/")
            for item in self._parse_movie_list(source, url):
                if lowered and lowered not in item["vod_name"].lower():
                    continue
                if item["vod_id"] in seen:
                    continue
                seen.add(item["vod_id"])
                merged.append(item)

        return {"list": merged}

    def isVideoFormat(self, url):
        value = (url or "").lower().split("?", 1)[0]
        return value.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".webm", ".ts"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ""

    def destroy(self):
        pass
