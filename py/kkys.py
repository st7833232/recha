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

try:
    import requests as _requests
except Exception:
    _requests = None

from base.spider import Spider as BaseSpider


SITE = "https://www.kkys20.com"
IMG_HOST = "https://vres.esadj.com"
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
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


def _origin_of(value):
    match = re.match(r"^(https?://[^/]+)", str(value or ""), re.I)
    return match.group(1) if match else ""


def _rewrite_image(value):
    raw = _clean(value)
    if not raw:
        return ""

    raw = raw.replace("\\/", "/")

    # Do not return KKYS lazy-loading placeholders as posters.
    if re.search(r"logo_placeholder|placeholder_vertical", raw, re.I):
        return ""

    if re.match(r"^https?://", raw, re.I):
        image_origin = _origin_of(raw)

        # Already on the image CDN (or an explicit host:port image endpoint).
        if re.search(r"vres\.", image_origin, re.I) or re.search(r":\d+$", image_origin):
            return raw

        # KKYS sometimes emits its image path on the website origin even though
        # the asset is actually served from the dedicated image host.
        if image_origin == _origin_of(SITE):
            return re.sub(r"^https?://[^/]+", IMG_HOST, raw, flags=re.I)

        return raw

    if raw.startswith("//"):
        return "https:" + raw

    if raw.startswith("/"):
        return IMG_HOST + raw

    return IMG_HOST + "/" + raw.lstrip("/")


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
    ("香港", "中国香港"),
    ("台湾", "中国台湾"),
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
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Accept": "*/*",
        }
        self.session = _requests.Session() if _requests is not None else None
        if self.session is not None:
            self.session.headers.update(self.headers)

    def getName(self):
        return "可可影視"

    def init(self, extend=""):
        self.extend = extend or ""
        if isinstance(extend, str) and extend.startswith("http"):
            self.site = extend.rstrip("/")

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get_response(self, url, referer=None, timeout=10):
        target = _absolute(url, self.site + "/")
        headers = dict(self.headers)
        headers["Referer"] = referer or (self.site + "/")

        try:
            if self.session is not None:
                response = self.session.get(
                    target,
                    headers=headers,
                    timeout=timeout,
                    verify=True,
                    allow_redirects=True,
                )
            else:
                response = self.fetch(
                    target,
                    headers=headers,
                    timeout=timeout,
                    verify=True,
                    allow_redirects=True,
                )

            if hasattr(response, "encoding"):
                response.encoding = "utf-8"
            return response
        except Exception as error:
            self.log("KKYS request failed: %s | %s" % (target, error))
            return None

    def _get(self, url, referer=None, timeout=10):
        response = self._get_response(url, referer, timeout)
        if response is None:
            return ""
        return getattr(response, "text", "") or ""

    # ------------------------------------------------------------------
    # Shared parsing
    # ------------------------------------------------------------------

    def _poster(self, node, base_url):
        images = _find_all(node, tag="img")
        if not images:
            return ""

        candidates = []

        # The working JS spider deliberately checks img:eq(-1) first because
        # KKYS cards may contain an earlier placeholder/decorative image.
        last = images[-1]
        candidates.extend([
            last.attr("data-original"),
            last.attr("data-src"),
        ])

        first = images[0]
        candidates.extend([
            first.attr("data-original"),
            first.attr("data-src"),
            first.attr("src"),
        ])

        # Extra robustness for template changes without changing the proven
        # priority above.
        for image in reversed(images):
            candidates.extend([
                image.attr("data-original"),
                image.attr("data-src"),
                image.attr("data-lazy-src"),
                image.attr("src"),
            ])

        for value in candidates:
            image_url = _rewrite_image(value)
            if image_url:
                return image_url

        return ""

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

    def _search_token(self, source):
        root = _parse_dom(source)
        for node in _find_all(root, tag="input"):
            if node.attr("name") == "t":
                value = _clean(node.attr("value"))
                if value:
                    return value

        # Conservative fallback in case the input is emitted in a form the
        # lightweight parser does not preserve exactly.
        match = re.search(
            r'<input[^>]*\bname=["\']t["\'][^>]*\bvalue=["\']([^"\']+)["\']',
            source or "",
            re.I | re.S,
        )
        if match:
            return _clean(match.group(1))

        match = re.search(
            r'<input[^>]*\bvalue=["\']([^"\']+)["\'][^>]*\bname=["\']t["\']',
            source or "",
            re.I | re.S,
        )
        return _clean(match.group(1)) if match else ""

    def _image_from_raw_fragment(self, fragment):
        if not fragment:
            return ""

        img_tags = list(re.finditer(r"<img\b[^>]*>", fragment, re.I | re.S))
        if not img_tags:
            return ""

        # Match the proven JS priority as closely as possible:
        # last image lazy attrs first, then first image lazy attrs/src.
        ordered = []
        if img_tags:
            ordered.append(img_tags[-1].group(0))
            if len(img_tags) > 1:
                ordered.append(img_tags[0].group(0))

        for match in reversed(img_tags):
            tag = match.group(0)
            if tag not in ordered:
                ordered.append(tag)

        for tag in ordered:
            for attr in ("data-original", "data-src", "data-lazy-src", "src"):
                found = re.search(
                    r'\b' + re.escape(attr) + r'\s*=\s*["\']([^"\']+)["\']',
                    tag,
                    re.I | re.S,
                )
                if not found:
                    continue
                picture = _rewrite_image(found.group(1))
                if picture:
                    return picture

        return ""

    def _search_picture_from_raw_html(self, source, detail_id):
        if not source or not detail_id:
            return ""

        pattern = re.compile(
            r"/detail/" + re.escape(str(detail_id)) + r"\.html(?:[?#][^\"'<>\s]*)?",
            re.I,
        )
        hit = pattern.search(source)
        if not hit:
            return ""

        # Search around the matching detail link. This avoids relying on the
        # lightweight HTMLParser to perfectly reconstruct malformed site HTML.
        left = max(0, hit.start() - 2600)
        right = min(len(source), hit.end() + 4200)
        fragment = source[left:right]

        # Prefer the nearest <img> tag to this detail link.
        relative_hit = hit.start() - left
        candidates = []
        for img in re.finditer(r"<img\b[^>]*>", fragment, re.I | re.S):
            distance = min(abs(img.start() - relative_hit), abs(img.end() - relative_hit))
            candidates.append((distance, img.group(0)))

        candidates.sort(key=lambda item: item[0])

        for _, tag in candidates:
            for attr in ("data-original", "data-src", "data-lazy-src", "src"):
                found = re.search(
                    r'\b' + re.escape(attr) + r'\s*=\s*["\']([^"\']+)["\']',
                    tag,
                    re.I | re.S,
                )
                if not found:
                    continue
                picture = _rewrite_image(found.group(1))
                if picture:
                    return picture

        return self._image_from_raw_fragment(fragment)

    def _parse_search_list(self, source, base_url):
        root = _parse_dom(source)
        nodes = _find_all(root, cls="search-result-item")

        result = []
        seen = set()

        for node in nodes:
            href = ""
            for candidate in _find_all(node, tag="a", attr_name="href"):
                if "/detail/" in candidate.attr("href"):
                    href = candidate.attr("href")
                    break

            if not href:
                continue

            detail_url = _absolute(href, base_url)
            match = re.search(r"/detail/(\d+)\.html(?:[?#].*)?$", detail_url, re.I)
            detail_id = match.group(1) if match else ""
            if not detail_id or detail_id in seen:
                continue

            title = ""
            title_node = _first(_find_all(node, cls="title"))
            if title_node:
                title = title_node.text()

            images = _find_all(node, tag="img")
            image_alt = _clean(images[0].attr("alt")) if images else ""
            title = _clean(title or image_alt)
            if not title:
                continue

            picture = ""
            if images:
                candidates = [
                    images[-1].attr("data-original"),
                    images[-1].attr("data-src"),
                    images[-1].attr("data-lazy-src"),
                    images[0].attr("data-original"),
                    images[0].attr("data-src"),
                    images[0].attr("data-lazy-src"),
                    images[0].attr("src"),
                ]
                for value in candidates:
                    picture = _rewrite_image(value)
                    if picture:
                        break

            # KKYS search HTML is less structurally consistent than category
            # pages. If HTMLParser loses the <img> from the card tree, recover
            # it directly from the raw HTML around /detail/{id}.html.
            if not picture:
                picture = self._search_picture_from_raw_html(source, detail_id)

            result.append({
                "vod_id": detail_url,
                "vod_name": title,
                "vod_pic": picture,
                "vod_remarks": "",
            })
            seen.add(detail_id)

        if not result:
            result = self._parse_list(source, base_url)

        for item in result:
            if item.get("vod_pic"):
                continue
            value = str(item.get("vod_id", ""))
            match = re.search(r"/detail/(\d+)\.html(?:[?#].*)?$", value, re.I)
            detail_id = match.group(1) if match else ""
            if detail_id:
                item["vod_pic"] = self._search_picture_from_raw_html(source, detail_id)

        return result

    def _has_next_page(self, source):
        if "page-item-next" in str(source or ""):
            return True

        root = _parse_dom(source)
        for anchor in _find_all(root, tag="a"):
            text = _clean(anchor.text())
            if text in ("下一页", "下一頁"):
                return True
        return False

    def _search_request(self, keyword, page):
        encoded = quote(keyword, safe="")
        seed_url = self.site + "/search?k=" + encoded

        seed_response = self._get_response(seed_url, self.site + "/", timeout=7)
        seed_source = ""
        if seed_response is not None:
            seed_source = getattr(seed_response, "text", "") or ""

        token = self._search_token(seed_source)

        if not token:
            return seed_source, seed_url, seed_source

        url = (
            self.site
            + "/search?k="
            + encoded
            + "&t="
            + quote(token, safe="")
        )

        if page > 1:
            url += "&page=" + str(page)

        result_response = self._get_response(url, seed_url, timeout=7)
        result_source = ""
        if result_response is not None:
            result_source = getattr(result_response, "text", "") or ""

        return result_source, url, seed_source

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
        # Keep startup instant. The Android flow asks homeContent() and
        # homeVideoContent() before publishing the result; category loading
        # will fetch the real list afterwards.
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg))
        except Exception:
            pass

        extend = extend or {}
        kind = _clean(extend.get("type", ""))
        area = _clean(extend.get("area", ""))
        # Match the site's actual category values, including values persisted
        # by earlier Python configs. UI label and request value are distinct.
        area = {
            "台湾": "中国台湾",
            "台灣": "中国台湾",
            "香港": "中国香港",
        }.get(area, area)
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

        # Detail metadata exposed by KKYS. Keep these as standard TVBox/FongMi
        # fields so WebHTV can render them without changing playback behavior.
        detail_rows = {}
        for row in _find_all(root, cls="detail-info-row"):
            side = _first(_find_all(row, cls="detail-info-row-side"))
            main = _first(_find_all(row, cls="detail-info-row-main"))
            key = _clean(side.text() if side else "").rstrip(":：")
            value = _clean(main.text() if main else "")
            if key and value:
                detail_rows[key] = value

        vod_director = detail_rows.get("导演", "") or detail_rows.get("導演", "")
        vod_actor = detail_rows.get("演员", "") or detail_rows.get("演員", "")
        vod_area = detail_rows.get("地区", "") or detail_rows.get("地區", "")
        vod_type = detail_rows.get("类型", "") or detail_rows.get("類型", "")
        vod_lang = detail_rows.get("语言", "") or detail_rows.get("語言", "")
        vod_remarks = detail_rows.get("备注", "") or detail_rows.get("備註", "")

        vod_year = ""
        premiere = detail_rows.get("首映", "") or detail_rows.get("上映", "")
        year_match = re.search(r"(?:19|20)\d{2}", premiere)
        if year_match:
            vod_year = year_match.group(0)

        # KKYS also exposes year / area / genre as detail tags on some pages.
        # Use them only as fallbacks when the labelled rows did not provide data.
        detail_tags = [
            _clean(node.text())
            for node in _find_all(root, tag="a", cls="detail-tags-item")
            if _clean(node.text())
        ]
        if detail_tags:
            if not vod_year:
                for tag in detail_tags:
                    year_match = re.search(r"(?:19|20)\d{2}", tag)
                    if year_match:
                        vod_year = year_match.group(0)
                        break
            if not vod_area and len(detail_tags) > 1:
                vod_area = detail_tags[1]
            if not vod_type and len(detail_tags) > 2:
                vod_type = "/".join(detail_tags[2:])

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

            # Hide 4K and the "超清2" playback source. Filter the source and
            # its episode box together so later sources keep their own episodes.
            normalized_name = re.sub(r"\s+", "", source_name)
            if re.search(r"4k", normalized_name, re.I) or re.fullmatch(
                r"超清[2２](?:線路|线路)?", normalized_name
            ):
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

        # Only use the generic fallback if source/episode wrappers were absent.
        # Otherwise it could silently reintroduce a deliberately hidden line.
        if not play_urls and pair_count == 0:
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
        if vod_year:
            vod["vod_year"] = vod_year
        if vod_area:
            vod["vod_area"] = vod_area
        if vod_type:
            vod["vod_type"] = vod_type
        if vod_lang:
            vod["vod_lang"] = vod_lang
        if vod_director:
            vod["vod_director"] = vod_director
        if vod_actor:
            vod["vod_actor"] = vod_actor
        if vod_remarks:
            vod["vod_remarks"] = vod_remarks
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
        keyword = _clean(key)
        if not keyword:
            return {
                "list": [],
                "page": 1,
                "pagecount": 1,
                "limit": 20,
                "total": 0,
            }

        try:
            page = max(1, int(pg or "1"))
        except Exception:
            page = 1

        try:
            source, request_url, seed_source = self._search_request(keyword, page)
        except Exception as error:
            self.log("KKYS search failed: %s" % error)
            source, request_url, seed_source = "", self.site + "/search", ""

        items = self._parse_search_list(source, request_url) if source else []

        if not items and seed_source:
            items = self._parse_search_list(
                seed_source,
                self.site + "/search?k=" + quote(keyword, safe=""),
            )

        has_next = self._has_next_page(source or seed_source)

        return {
            "list": items,
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": len(items) or 20,
            "total": len(items),
        }

    def isVideoFormat(self, url):
        value = (url or "").lower().split("?", 1)[0]
        return value.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".webm", ".ts"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ""

    def destroy(self):
        try:
            if self.session is not None:
                self.session.close()
        except Exception:
            pass
