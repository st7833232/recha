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
import threading
import time
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit

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


# ----------------------------------------------------------------------
# 片中廣告去除。W-233：幾條線路的 CDN 在片中固定時間插廣告，播放器原生規則認不出。
# 自成一段、只用標準庫，其他 PY 站可以整段複製。判不準一律原樣回傳：
# 寧可播廣告，不可刪正片。只處理 _AD_LINES 裡線路名與網域都對得上的清單。
# ----------------------------------------------------------------------

# 線路名 → 該線路實測過的 CDN 網域關鍵字。站方改名或換網域就不代理，原樣播放。
_AD_LINES = {
    "FF线路": ("ffzy",),
    "蓝光": ("dytt", "phimgood"),
    "蓝光1": ("fengbao",),
    "蓝光3": ("yzzy", "vvvip-plays"),
    "LZ线路": ("lzcdn", "lfthirtytwo"),
}
_AD_FPS = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0)
_AD_FRAME_TOL = 0.03          # EXTINF 只有 3 位小數：60fps 下最多差 0.03 幀
_AD_SHORT_RATIO = 0.75        # 少於平常區塊 3/4 段數的算短區塊（同 Android 比例）
_AD_REGULAR_MIN_BLOCKS = 10   # 「規則排法」至少要有這麼多個同大小區塊，免得把廣告當成正片節奏
_AD_MAX_SECONDS = 60.0        # 一次廣告（相鄰短區塊合計）最長秒數
_AD_MAX_REMOVED_RATIO = 0.05  # 要刪的超過片長 5% 就不像廣告，放棄
# 2026-11 實測的廣告：整段的段長序列（0.01 秒），每串都在 11–12 部不同影片出現。換素材時更新這裡。
_AD_KNOWN = {
    (4.87, 3.33, 6.37, 2.1, 2.97), (6.96, 4.0, 2.56, 3.84),        # FF（ffzy）
    (5.57, 2.93, 5.7, 3.33, 1.53), (6.67, 2.13, 3.23, 3.73),       # 蓝光
    (6.63, 3.33, 4.8, 1.7), (5.93, 3.33, 2.8, 5.3, 0.3),           # 蓝光3
}


def _ad_host_allowed(url):
    host = urlsplit(url).netloc.lower()
    return any(key in host for hosts in _AD_LINES.values() for key in hosts)


def _ad_line_allowed(flag, url):
    hosts = _AD_LINES.get(str(flag or "").strip())
    host = urlsplit(url).netloc.lower()
    return bool(hosts) and any(key in host for key in hosts) and ".m3u8" in url.lower()


def _ad_blocks(lines):
    """[(DISCONTINUITY 行號, [(EXTINF 行號, 網址行號, 秒數)])]；EXTINF 讀不懂回 None。"""
    blocks, cur, dur, extinf = [], None, 0.0, None
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line == "#EXT-X-DISCONTINUITY":
            cur = (index, [])
            blocks.append(cur)
        elif line.startswith("#EXTINF:"):
            extinf = index
            try:
                dur = float(line[8:].split(",")[0])
            except ValueError:
                return None
        elif line and not line.startswith("#"):
            if cur is None:
                cur = (None, [])
                blocks.append(cur)
            cur[1].append((extinf, index, dur))
    return blocks


def _ad_fits(seconds, fps):
    frames = seconds * fps
    return abs(frames - round(frames)) <= _AD_FRAME_TOL


def _ad_film_fps(durations):
    best, score = None, 0.0
    for fps in _AD_FPS:
        value = sum(_ad_fits(d, fps) for d in durations) / float(len(durations) or 1)
        if value > score:
            best, score = fps, value
    return best if score >= 0.9 else None


def _ad_seconds(block):
    return sum(segment[2] for segment in block[1])


def _ad_dir(uri):
    uri = uri.strip()
    return uri.rsplit("/", 1)[0] if "/" in uri else ""


def hls_ad_lines(text):
    """要刪的行號（廣告段與它們的 DISCONTINUITY）；不確定時回空集合。段網址要先改成絕對位址。"""
    if "#EXT-X-ENDLIST" not in text:
        return set()
    lines = text.splitlines()
    blocks = _ad_blocks(lines)
    if not blocks or len(blocks) < 3:
        return set()
    judged = blocks[:-1]  # 最後一塊一律不判（同 Android）
    sizes = {}
    for block in judged:
        sizes[len(block[1])] = sizes.get(len(block[1]), 0) + 1
    mode, freq = max(sizes.items(), key=lambda kv: (kv[1], kv[0]))
    runs = []
    if mode >= 4 and freq >= 0.5 * len(judged) and freq >= _AD_REGULAR_MIN_BLOCKS:
        # 規則排法：正片每 mode 段切一次；相鄰的短區塊合併成一次廣告。
        run = []
        for block in judged:
            if len(block[1]) < mode * _AD_SHORT_RATIO:
                run.append(block)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
    else:
        # 長區塊排法：夾在兩個超過一分鐘的區塊之間的短區塊。
        for k in range(1, len(blocks) - 1):
            if _ad_seconds(blocks[k]) <= _AD_MAX_SECONDS \
                    and _ad_seconds(blocks[k - 1]) > _AD_MAX_SECONDS \
                    and _ad_seconds(blocks[k + 1]) > _AD_MAX_SECONDS:
                runs.append([blocks[k]])
    if not runs:
        return set()
    in_runs = set(id(block) for run in runs for block in run)
    film = [s for b in judged if id(b) not in in_runs for s in b[1]]
    fps = _ad_film_fps([s[2] for s in film])
    film_dirs = set(_ad_dir(lines[s[1]]) for b in blocks if id(b) not in in_runs for s in b[1])
    signatures = {}
    for run in runs:
        key = tuple(round(s[2], 3) for b in run for s in b[1])
        signatures[key] = signatures.get(key, 0) + 1
    total = sum(_ad_seconds(block) for block in blocks)
    drop, removed = set(), 0.0
    for run in runs:
        segments = [s for b in run for s in b[1]]
        seconds = sum(s[2] for s in segments)
        known = tuple(round(s[2], 2) for s in segments) in _AD_KNOWN
        repeated = signatures[tuple(round(s[2], 3) for s in segments)] >= 2
        off_fps = fps is not None and sum(_ad_fits(s[2], fps) for s in segments) * 2 < len(segments)
        other_path = all(_ad_dir(lines[s[1]]) not in film_dirs for s in segments)
        # K，或 R 且 F，或 P 且（R 或 F）（W-233 審查 #5601、#5661）；單一證據一律保留。
        if seconds <= _AD_MAX_SECONDS and (known or (repeated and off_fps) or (other_path and (repeated or off_fps))):
            removed += seconds
            for s in segments:
                drop.update(i for i in (s[0], s[1]) if i is not None)
            drop.update(b[0] for b in run if b[0] is not None)
    if removed > _AD_MAX_REMOVED_RATIO * total:
        return set()
    return drop


def strip_hls_ads(text):
    """刪掉廣告的清單；沒有可確定的廣告時原樣回傳。"""
    drop = hls_ad_lines(text)
    if not drop:
        return text
    return "\n".join(l for i, l in enumerate(text.splitlines()) if i not in drop) + "\n"


def _ad_absolute_uris(text, base, wrap=None):
    """清單裡的網址改成絕對位址（清單改從本機代理送出，相對路徑會失效）。
    wrap：master 的 variant 網址再包一層代理。"""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            out.append(re.sub(r'URI="([^"]+)"', lambda m: 'URI="%s"' % urljoin(base, m.group(1)), raw))
        elif line:
            url = urljoin(base, line)
            out.append(wrap(url) if wrap else url)
        else:
            out.append(raw)
    return "\n".join(out) + "\n"


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
        self._ad_cache = {}  # 網址 → (時間, 處理好的清單)
        self._ad_lock = threading.Lock()
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
            # W-234：卡片本身就是 <a href="/detail/…">，先看自己的 href。
            href = node.attr("href") if "/detail/" in node.attr("href") else ""
            for candidate in [] if href else _find_all(node, tag="a", attr_name="href"):
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

            # W-234：類型與年份不再混進片名，改放備註。
            header = _first(_find_all(node, cls="search-result-item-header"))
            tags = _first(_find_all(node, cls="tags"))
            year = _first(_find_all(tags, tag="span")) if tags else None
            remarks = " · ".join(v for v in (header.text() if header else "", year.text() if year else "") if v)

            result.append({
                "vod_id": detail_url,
                "vod_name": title,
                "vod_pic": picture,
                "vod_remarks": remarks,
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

        # KKYS may include repeated slash separators before/inside cast text.
        # Remove only runs of 3+ separators so normal name separators remain intact.
        vod_director = re.sub(r"(?:\s*[/／|｜]\s*){3,}", " ", vod_director).strip(" /／|｜")
        vod_actor = re.sub(r"(?:\s*[/／|｜]\s*){3,}", " ", vod_actor).strip(" /／|｜")

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
            url = _absolute(media, play_page)
            # W-233：白名單線路先在這裡抓好、刪完廣告存快取，再回代理位址；
            # 抓不到就回原位址照播。其他線路不變。
            if _ad_line_allowed(flag, url):
                url = self._ad_play_url(url)
            return {
                "parse": 0,
                "url": url,
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

    _AD_CACHE_SECONDS = 600
    _AD_CACHE_SIZE = 8
    _AD_PREFETCH_TIMEOUT = 5

    def _ad_proxy_url(self, url):
        return self.getProxyUrl() + "&type=adm3u8&url=" + quote(url, safe="")

    def _ad_answer(self, url, timeout=10):
        """處理好的清單（先查快取）：master 把 variant 包成代理位址，variant 刪廣告。抓不到回 None。"""
        with self._ad_lock:
            hit = self._ad_cache.get(url)
        if hit and time.time() - hit[0] < self._AD_CACHE_SECONDS:
            return hit[1]
        response = self._get_response(url, self.site + "/", timeout=timeout)
        text = (getattr(response, "text", "") or "") if response is not None else ""
        if "#EXTM3U" not in text:
            return None
        # CDN 可能轉址：段網址要以實際送出清單的位址為基底。
        base = str(getattr(response, "url", "") or url)
        if "#EXT-X-STREAM-INF" in text:
            # 只包白名單網域的 variant；轉址到別的網域就直連（代理會拒絕那個網域）。
            text = _ad_absolute_uris(text, base, lambda u: self._ad_proxy_url(u) if _ad_host_allowed(u) else u)
        else:
            text = strip_hls_ads(_ad_absolute_uris(text, base))
        with self._ad_lock:  # 逾時後留下的預抓執行緒也只會走到這裡
            self._ad_cache[url] = (time.time(), text)
            while len(self._ad_cache) > self._AD_CACHE_SIZE:
                self._ad_cache.pop(min(self._ad_cache, key=lambda key: self._ad_cache[key][0]), None)
        return text

    def _ad_play_url(self, url):
        """在 playerContent 裡把 master 和它的 variant 都抓好，播放器來要時直接從快取回；
        起播 15 秒逾時（FongMi 會換線）就不含這段時間。抓不到回原位址，含廣告照播。"""
        done = []

        def prefetch():
            try:
                master = self._ad_answer(url, self._AD_PREFETCH_TIMEOUT)
                if master is None:
                    return
                for line in master.splitlines():
                    if line and not line.startswith("#") and "url=" in line:
                        if self._ad_answer(unquote(line.split("url=", 1)[1]), self._AD_PREFETCH_TIMEOUT) is None:
                            return
                done.append(True)
            except Exception as error:
                self.log("KKYS ad prefetch failed: %s" % error)

        # 主機有多個 IP 時，Python 會逐一連線、每個都等滿逾時（5 個 IP＝25 秒）：
        # 用 join 卡住總時間。逾時就回原位址；留下的執行緒最多晚一點寫進快取。
        worker = threading.Thread(target=prefetch, daemon=True)
        worker.start()
        worker.join(self._AD_PREFETCH_TIMEOUT)
        return self._ad_proxy_url(url) if done else url

    def localProxy(self, param):
        """W-233：回白名單線路處理好的 master／variant（通常已在快取）。抓不到就 302 回原位址。"""
        param = param or {}
        url = param.get("url", "")
        if param.get("type") != "adm3u8" or not url.startswith("http") or not _ad_host_allowed(url):
            return [404, "text/plain", ""]
        try:
            text = self._ad_answer(url)
        except Exception as error:
            self.log("KKYS ad proxy failed: %s" % error)
            text = None
        if text is None:
            self.log("KKYS ad proxy fallback: %s" % url)
            return [302, "text/plain", "", {"Location": url}]
        return [200, "application/vnd.apple.mpegurl", text]

    def isVideoFormat(self, url):
        value = (url or "").lower().split("?", 1)[0]
        return value.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".webm", ".ts"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ""

    def destroy(self):
        with self._ad_lock:
            self._ad_cache.clear()
        try:
            if self.session is not None:
                self.session.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# W-233 自我檢查：python3 kkys.py [固定清單資料夾]
# 合成清單測邊界；資料夾給了就再跑實際清單（只有段長與匿名路徑，沒有真實網址）。
# ----------------------------------------------------------------------

# 每份固定清單要刪的段數。00–14：FF 線路（00 是回報的那部）；其餘是新開線路各一部。
_AD_FIXTURES = dict([("%02d" % i, n) for i, n in enumerate([18, 18, 18, 18, 18, 9, 9, 9, 9, 5, 5, 5, 5, 14, 9])]
                    + [("lan", 18), ("lan1", 27), ("lan3", 18), ("lz", 21)])


def _ad_synthetic(ads, film_blocks=60, vod=True, ad_dir=""):
    """29.97fps 正片每 5 段一塊；ads 是 {插在第幾塊之後: [段長]}；ad_dir 讓廣告段走別的路徑。"""
    lines = ["#EXTM3U", "#EXT-X-PLAYLIST-TYPE:VOD"]
    n = 0
    for k in range(film_blocks):
        lines.append("#EXT-X-DISCONTINUITY")
        for _ in range(5):
            lines += ["#EXTINF:3.337,", "film/s%d.ts" % n]
            n += 1
        for half in ads.get(k, []):
            lines.append("#EXT-X-DISCONTINUITY")
            for d in half:
                lines += ["#EXTINF:%.3f," % d, "%sa%d.ts" % (ad_dir or "film/", n)]
                n += 1
    if vod:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def _ad_removed(text):
    return sum(1 for l in text.splitlines() if l and not l.startswith("#")) - \
        sum(1 for l in strip_hls_ads(text).splitlines() if l and not l.startswith("#"))


def _ad_self_check(fixture_dir=None):
    ad_a = [[4.867, 3.333, 6.367], [2.1, 2.967]]          # 已知廣告 A，切成兩塊
    unknown = [[3.0, 2.5], [4.5]]                           # 30fps、不在已知清單
    film_like = [[3.337, 6.673], [3.337]]                   # 29.97fps，像正片
    too_long = [[25.01, 25.01], [25.01]]                    # 不像正片也重複，但一次超過 60 秒
    assert _ad_removed(_ad_synthetic({5: ad_a})) == 5, "K"
    assert _ad_removed(_ad_synthetic({5: unknown})) == 0, "only F"
    assert _ad_removed(_ad_synthetic({5: unknown, 20: unknown})) == 6, "R and F"
    assert _ad_removed(_ad_synthetic({5: film_like, 20: film_like})) == 0, "only R"
    assert _ad_removed(_ad_synthetic({5: film_like}, ad_dir="ad/")) == 0, "only P"
    assert _ad_removed(_ad_synthetic({5: film_like, 20: film_like}, ad_dir="ad/")) == 6, "P and R"
    assert _ad_removed(_ad_synthetic({5: unknown}, ad_dir="ad/")) == 3, "P and F"
    assert _ad_removed(_ad_synthetic({5: too_long, 40: too_long}, film_blocks=200)) == 0, "over 60 s"
    assert _ad_removed(_ad_synthetic({5: ad_a}, vod=False)) == 0, "not VOD"
    assert _ad_removed(_ad_synthetic({59: ad_a})) == 0, "last block is never judged"
    over = _ad_synthetic({k: ad_a for k in range(0, 57, 4)}, film_blocks=60)  # 15 次廣告約佔 29%
    assert len(hls_ad_lines(over.replace("#EXT-X-ENDLIST", ""))) == 0 and _ad_removed(over) == 0, "over 5%"
    clean = strip_hls_ads(_ad_synthetic({5: ad_a}))
    assert strip_hls_ads(clean) == clean, "idempotent"
    assert "/a" not in "".join(l for l in clean.splitlines() if l and not l.startswith("#")), "ad left"
    for flag, url, allowed in (("FF线路", "https://vip.ffzy-plays.com/a/index.m3u8", True),
                               ("FF线路", "https://other-cdn.com/a/index.m3u8", False),   # 換網域
                               ("FF线路2", "https://vip.ffzy-plays.com/a/index.m3u8", False),  # 改名
                               ("JY线路", "https://hd.kuktxu.com/a/index.m3u8", False),   # 不在白名單
                               ("蓝光1", "https://v.fengbao14.com/a/index.mp4", False)):  # 不是 m3u8
        assert _ad_line_allowed(flag, url) == allowed, "whitelist %s %s" % (flag, url)
    assert _ad_host_allowed("https://cdn.yzzy30-play.com/a/b.m3u8") and not _ad_host_allowed("https://evil.example/a.m3u8"), "host"

    class _Answer(object):
        def __init__(self, url, text):
            self.url, self.text = url, text

    class _Probe(Spider):
        """playerContent 的預抓與 localProxy 的快取，不連網：_get_response 換成固定回答。"""
        def __init__(self, answers):
            self._ad_cache, self.site, self.calls, self.answers = {}, SITE, [], answers
            self._ad_lock, self.delay = threading.Lock(), 0

        def getProxyUrl(self, local=True):
            return "http://127.0.0.1:9978/proxy?do=py"

        def log(self, *args):
            pass

        def _get_response(self, url, referer=None, timeout=10):
            self.calls.append(url)
            time.sleep(self.delay)
            text = self.answers.get(url)
            return _Answer(url, text) if text is not None else None

    master_url = "https://vip.ffzy-plays.com/a/index.m3u8"
    variant_url = "https://vip.ffzy-plays.com/a/3000k/hls/mixed.m3u8"
    probe = _Probe({master_url: "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\n3000k/hls/mixed.m3u8\n",
                    variant_url: _ad_synthetic({5: ad_a})})
    played = probe._ad_play_url(master_url)
    assert played.startswith("http://127.0.0.1:9978/proxy") and probe.calls == [master_url, variant_url], "prefetch"
    variant = probe.localProxy({"type": "adm3u8", "url": variant_url})
    assert variant[0] == 200 and probe.calls == [master_url, variant_url], "cache hit"
    assert "film/a" not in variant[2] and variant[2].count("film/s") == 300, "cached variant clean"
    down = _Probe({})
    assert down._ad_play_url(master_url) == master_url, "prefetch failure plays the original"
    assert down.localProxy({"type": "adm3u8", "url": master_url})[0] == 302, "302"
    assert down.localProxy({"type": "adm3u8", "url": "https://evil.example/a.m3u8"})[0] == 404, "foreign host"
    foreign = _Probe({master_url: "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nhttps://other-cdn.example/v.m3u8\n"})
    assert foreign._ad_answer(master_url).splitlines()[-1] == "https://other-cdn.example/v.m3u8", "foreign variant stays direct"
    slow = _Probe(dict(probe.answers))
    slow._AD_PREFETCH_TIMEOUT, slow.delay = 0.3, 1.0  # 每個 IP 都等滿逾時的情形
    started = time.time()
    assert slow._ad_play_url(master_url) == master_url, "slow CDN plays the original"
    assert time.time() - started < 0.6, "prefetch is bounded by its timeout in total"
    checked = 25
    if fixture_dir:
        import os
        for name, expected in sorted(_AD_FIXTURES.items()):
            path = os.path.join(fixture_dir, name + ".m3u8")
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            got = _ad_removed(text)
            assert got == expected, "%s: removed %d, expected %d" % (path, got, expected)
            assert strip_hls_ads(strip_hls_ads(text)) == strip_hls_ads(text), path
            checked += 1
    return checked


if __name__ == "__main__":
    import sys
    print("ad self-check passed: %d cases" % _ad_self_check(sys.argv[1] if len(sys.argv) > 1 else None))
