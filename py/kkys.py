# -*- coding: utf-8 -*-
"""
可可影視 / KKYS CatVod Python Spider
- Android: WebHTV Chaquopy / PyLoader
- iOS: WebHTV PythonSpiderRuntime
- 僅使用目前兩端共同可用能力：base.spider + Python 標準庫
- 不依賴 lxml / BeautifulSoup / loadSpider / loadModule
"""

import html as html_lib
import json
import re
from html.parser import HTMLParser
from urllib.parse import quote, urljoin

from base.spider import Spider as BaseSpider


SITE = "https://www.kkys20.com"
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
    "Mobile/15E148 Safari/604.1"
)


def _clean(value):
    if value is None:
        return ""
    value = html_lib.unescape(str(value))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


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

    def has_class(self, name):
        return name in self.classes()

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
        if cls and not item.has_class(cls):
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


def _absolute(value, base=SITE + "/"):
    value = _clean(value)
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    return urljoin(base, value)


def _media_decode(value):
    return (
        _clean(value)
        .replace("\\/", "/")
        .replace("\\u0026", "&")
        .replace("\\u0026".upper(), "&")
        .replace("&amp;", "&")
    )


def _filter_values(values):
    return [{"n": name, "v": value} for name, value in values]


COMMON_AREA = _filter_values([
    ("全部", ""),
    ("大陆", "中国大陆"),
    ("香港", "香港"),
    ("台湾", "台湾"),
    ("美国", "美国"),
    ("日本", "日本"),
    ("韩国", "韩国"),
    ("英国", "英国"),
    ("法国", "法国"),
    ("德国", "德国"),
    ("印度", "印度"),
    ("泰国", "泰国"),
    ("加拿大", "加拿大"),
    ("俄罗斯", "俄罗斯"),
    ("意大利", "意大利"),
    ("西班牙", "西班牙"),
    ("澳大利亚", "澳大利亚"),
    ("其他", "其他"),
])

COMMON_LANG = _filter_values([
    ("全部", ""),
    ("国语", "国语"),
    ("粤语", "粤语"),
    ("英语", "英语"),
    ("日语", "日语"),
    ("韩语", "韩语"),
    ("法语", "法语"),
    ("其他", "其他"),
])

COMMON_YEAR = _filter_values([
    ("全部", ""),
    ("2026", "2026"),
    ("2025", "2025"),
    ("2024", "2024"),
    ("2023", "2023"),
    ("2022", "2022"),
    ("2021", "2021"),
    ("2020", "2020"),
    ("10年代", "2010_2019"),
    ("00年代", "2000_2009"),
    ("90年代", "1990_1999"),
    ("80年代", "1980_1989"),
    ("更早", "0_1979"),
])

COMMON_SORT = _filter_values([
    ("综合", "1"),
    ("最新", "2"),
    ("最热", "3"),
    ("评分", "4"),
])

MOVIE_TYPES = _filter_values([
    ("全部", ""),
    ("剧情", "剧情"),
    ("喜剧", "喜剧"),
    ("动作", "动作"),
    ("爱情", "爱情"),
    ("恐怖", "恐怖"),
    ("惊悚", "惊悚"),
    ("犯罪", "犯罪"),
    ("科幻", "科幻"),
    ("悬疑", "悬疑"),
    ("奇幻", "奇幻"),
    ("冒险", "冒险"),
    ("战争", "战争"),
    ("历史", "历史"),
    ("古装", "古装"),
    ("家庭", "家庭"),
    ("传记", "传记"),
    ("武侠", "武侠"),
    ("歌舞", "歌舞"),
    ("短片", "短片"),
    ("动画", "动画"),
    ("儿童", "儿童"),
    ("职场", "职场"),
])

SERIES_TYPES = _filter_values([
    ("全部", ""),
    ("剧情", "剧情"),
    ("爱情", "爱情"),
    ("喜剧", "喜剧"),
    ("犯罪", "犯罪"),
    ("悬疑", "悬疑"),
    ("古装", "古装"),
    ("动作", "动作"),
    ("家庭", "家庭"),
    ("惊悚", "惊悚"),
    ("奇幻", "奇幻"),
    ("美剧", "美剧"),
    ("科幻", "科幻"),
    ("历史", "历史"),
    ("战争", "战争"),
    ("韩剧", "韩剧"),
    ("武侠", "武侠"),
    ("言情", "言情"),
    ("恐怖", "恐怖"),
    ("冒险", "冒险"),
    ("都市", "都市"),
    ("职场", "职场"),
])


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.site = SITE
        self.headers = {
            "User-Agent": UA,
            "Referer": SITE + "/",
        }

    def getName(self):
        return "可可影視"

    def init(self, extend=""):
        self.extend = extend or ""
        if isinstance(extend, str) and extend.startswith("http"):
            self.site = extend.rstrip("/")

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

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
            self.log("KKYS request failed: %s | %s" % (target, error))
            return ""

    # ------------------------------------------------------------------
    # Shared parsing
    # ------------------------------------------------------------------

    def _poster(self, node, base_url):
        image = _first(_find_all(node, tag="img"))
        if not image:
            return ""
        value = (
            image.attr("data-original")
            or image.attr("data-src")
            or image.attr("data-lazy-src")
            or image.attr("src")
        )
        return _absolute(value, base_url)

    def _detail_anchor(self, node):
        for anchor in _find_all(node, tag="a", attr_name="href"):
            if "/detail/" in anchor.attr("href"):
                return anchor
        return None

    def _item_title(self, node, anchor=None):
        titles = _find_all(node, cls="v-item-title")
        if len(titles) > 1:
            title = titles[1].text()
            if title:
                return title
        if titles:
            title = titles[0].text()
            if title:
                return title
        if anchor:
            title = _clean(anchor.attr("title"))
            if title:
                return title
            return anchor.text()
        return ""

    def _item_remark(self, node):
        for cls in (
            "v-item-note",
            "module-item-note",
            "module-item-text",
            "module-item-caption",
        ):
            found = _first(_find_all(node, cls=cls))
            if found:
                text = found.text()
                if text:
                    return text
        return ""

    def _item_from_node(self, node, base_url):
        anchor = self._detail_anchor(node)
        if not anchor:
            return None
        href = _absolute(anchor.attr("href"), base_url)
        title = self._item_title(node, anchor)
        if not href or not title:
            return None
        item = {
            "vod_id": href,
            "vod_name": title,
            "vod_pic": self._poster(node, base_url),
        }
        remark = self._item_remark(node)
        if remark:
            item["vod_remarks"] = remark
        return item

    def _parse_list(self, source, base_url):
        root = _parse_dom(source)
        candidates = _find_all(root, cls="module-item")
        if not candidates:
            candidates = _find_all(root, cls="search-result-item")

        result = []
        seen = set()
        for node in candidates:
            item = self._item_from_node(node, base_url)
            if not item:
                continue
            key = item["vod_id"]
            if key in seen:
                continue
            seen.add(key)
            result.append(item)

        # Site templates occasionally change wrapper class while keeping /detail/ links.
        # Use anchors as a conservative fallback only when the normal list selectors found nothing.
        if not result:
            for anchor in _find_all(root, tag="a", attr_name="href"):
                href = anchor.attr("href")
                if "/detail/" not in href:
                    continue
                title = _clean(anchor.attr("title")) or anchor.text()
                if not title:
                    continue
                absolute = _absolute(href, base_url)
                if absolute in seen:
                    continue
                seen.add(absolute)
                result.append({
                    "vod_id": absolute,
                    "vod_name": title,
                    "vod_pic": "",
                })
        return result

    def _filters_for(self, tid):
        filters = []
        if str(tid) == "1":
            filters.append({"key": "type", "name": "類型", "value": MOVIE_TYPES})
        elif str(tid) == "2":
            filters.append({"key": "type", "name": "類型", "value": SERIES_TYPES})

        # These four dimensions are shared by the current KKYS show route.
        filters.extend([
            {"key": "area", "name": "地區", "value": COMMON_AREA},
            {"key": "lang", "name": "語言", "value": COMMON_LANG},
            {"key": "year", "name": "年份", "value": COMMON_YEAR},
            {"key": "sort", "name": "排序", "value": COMMON_SORT},
        ])
        return filters

    # ------------------------------------------------------------------
    # CatVod API
    # ------------------------------------------------------------------

    def homeContent(self, filter):
        classes = [
            {"type_id": "1", "type_name": "電影"},
            {"type_id": "2", "type_name": "連續劇"},
            {"type_id": "3", "type_name": "動漫"},
            {"type_id": "4", "type_name": "綜藝紀錄"},
            {"type_id": "6", "type_name": "短剧"},
        ]
        result = {"class": classes}
        if filter:
            result["filters"] = {
                item["type_id"]: self._filters_for(item["type_id"])
                for item in classes
            }
        return result

    def homeVideoContent(self):
        source = self._get(self.site + "/", self.site + "/")
        items = self._parse_list(source, self.site + "/")
        return {"list": items[:30]}

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg))
        except Exception:
            pass

        extend = extend or {}
        kind = _clean(extend.get("type", ""))
        area = _clean(extend.get("area", ""))
        lang = _clean(extend.get("lang", ""))
        year = _clean(extend.get("year", ""))
        sort = _clean(extend.get("sort", "")) or "3"

        def seg(value):
            return quote(value, safe="") if value else ""

        url = (
            self.site
            + "/show/"
            + "%s-%s-%s-%s-%s-%s-%s.html"
            % (
                str(tid),
                seg(kind),
                seg(area),
                seg(lang),
                seg(year),
                seg(sort),
                str(page),
            )
        )

        source = self._get(url, self.site + "/")
        items = self._parse_list(source, url)
        root = _parse_dom(source)
        has_next = any(
            "下一页" in anchor.text() or "下一頁" in anchor.text()
            for anchor in _find_all(root, tag="a", attr_name="href")
        )

        return {
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": len(items),
            "total": (page * len(items) + (1 if has_next else 0)),
            "list": items,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}

        detail_url = _absolute(ids[0], self.site + "/")
        source = self._get(detail_url, self.site + "/")
        root = _parse_dom(source)

        title = ""
        title_box = _first(_find_all(root, cls="detail-title"))
        if title_box:
            strongs = _find_all(title_box, tag="strong")
            if len(strongs) > 1:
                title = strongs[1].text()
            elif strongs:
                title = strongs[0].text()
            if not title:
                title = title_box.text()

        if not title:
            meta_title = _first([
                node for node in _find_all(root, tag="meta")
                if node.attr("property") == "og:title"
            ])
            if meta_title:
                title = _clean(meta_title.attr("content"))

        pic = ""
        pic_box = _first(_find_all(root, cls="detail-pic"))
        if pic_box:
            pic = self._poster(pic_box, detail_url)

        content = ""
        for meta in _find_all(root, tag="meta"):
            if meta.attr("name") == "description" or meta.attr("property") == "og:description":
                content = _clean(meta.attr("content"))
                if content:
                    break

        source_container = _first(_find_all(root, cls="source-list-box-main"))
        episode_container = _first(_find_all(root, cls="episode-list-box-main"))
        source_items = _find_all(source_container or root, tag="a", cls="source-item")
        episode_boxes = _find_all(episode_container or root, cls="episode-list")

        play_from = []
        play_urls = []

        # Pair by the original DOM index first. Do not re-index after filtering:
        # each source button corresponds to the episode box at the same position.
        pair_count = min(len(source_items), len(episode_boxes))
        for index in range(pair_count):
            source_item = source_items[index]
            episode_box = episode_boxes[index]

            label_node = _first(_find_all(source_item, cls="source-item-label"))
            source_name = (label_node.text() if label_node else source_item.text()) or ("线路%d" % (index + 1))
            source_name = _clean(source_name)

            # The dedicated "4K" source is intentionally excluded; "超清2" remains.
            if re.search(r"4k", source_name, re.I):
                continue

            episodes = []
            for anchor in _find_all(episode_box, tag="a", attr_name="href"):
                href = anchor.attr("href")
                if "/play/" not in href:
                    continue
                name = anchor.text() or _clean(anchor.attr("title")) or ("第%d集" % (len(episodes) + 1))
                episode_url = _absolute(href, detail_url)
                if episode_url:
                    episodes.append("%s$%s" % (name, episode_url))

            if episodes:
                play_from.append(source_name)
                play_urls.append("#".join(episodes))

        # Fallback for a template change: keep the source usable even if the paired wrappers change.
        if not play_urls:
            episodes = []
            for anchor in _find_all(root, tag="a", attr_name="href"):
                href = anchor.attr("href")
                if "/play/" not in href:
                    continue
                name = anchor.text() or ("第%d集" % (len(episodes) + 1))
                episode_url = _absolute(href, detail_url)
                if episode_url:
                    episodes.append("%s$%s" % (name, episode_url))
            if episodes:
                play_from = ["可可影視"]
                play_urls = ["#".join(episodes)]

        vod = {
            "vod_id": detail_url,
            "vod_name": title or detail_url,
            "vod_pic": pic,
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_urls),
        }
        return {"list": [vod]}

    def _extract_player_url(self, source):
        text = source or ""

        # Current KKYS page embeds: playSource = { ..., src: "https://..." }
        match = re.search(
            r"playSource\s*=\s*\{[^}]*?\bsrc\s*:\s*[\"']([^\"']+)[\"']",
            text,
            re.I | re.S,
        )
        if match:
            return _media_decode(match.group(1))

        # Conservative media fallbacks.
        match = re.search(r"(https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*)", text, re.I)
        if match:
            return _media_decode(match.group(1))

        match = re.search(
            r"(https?://[^\s\"'<>]+\.(?:mp4|flv|mkv|webm)[^\s\"'<>]*)",
            text,
            re.I,
        )
        if match:
            return _media_decode(match.group(1))

        return ""

    def playerContent(self, flag, id, vipFlags):
        play_page = _absolute(id, self.site + "/")
        source = self._get(play_page, self.site + "/")
        media = self._extract_player_url(source)

        header = {
            "User-Agent": UA,
            "Referer": self.site + "/",
        }

        if media:
            return {
                "parse": 0,
                "url": _absolute(media, play_page),
                "header": header,
            }

        # Let WebHTV's normal sniffer handle the play page if the direct URL is not exposed.
        return {
            "parse": 1,
            "url": play_page,
            "header": header,
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            if int(pg) > 1:
                return {"list": []}
        except Exception:
            pass

        home = self._get(self.site + "/", self.site + "/")
        root = _parse_dom(home)

        token = ""
        for node in _find_all(root, tag="input"):
            if node.attr("name") == "t":
                token = _clean(node.attr("value"))
                if token:
                    break

        params = "k=" + quote(str(key), safe="")
        if token:
            params += "&t=" + quote(token, safe="")
        url = self.site + "/search?" + params

        source = self._get(url, self.site + "/")
        items = self._parse_list(source, url)
        return {"list": items}

    def isVideoFormat(self, url):
        value = (url or "").lower().split("?", 1)[0]
        return value.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".webm", ".ts"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ""

    def destroy(self):
        pass
