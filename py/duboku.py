# -*- coding: utf-8 -*-
"""
獨播影視 / Duboku CatVod Python Spider (W-200)
- Android: FongMi 影視 PyLoader；iOS: WebHTV PythonSpiderRuntime
- Port of WebHTV ios/Spiders/Duboku.js (itself a port of com.github.catvod.spider.Duboku).
- 回傳 dict（FongMi 的 app.py 會自己 json.dumps；回傳字串會被編碼兩次而變空站），iOS 也接受 dict。
- 只用 base.spider、requests 與 Python 標準庫。
Source host: https://api.dbokutv.com (signed JSON GET); media is HLS on vid.dbokutv.com.
"""

import base64
import re
import time
from urllib.parse import quote

import requests

from base.spider import Spider as BaseSpider

API = "https://api.dbokutv.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/151.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://www.duboku.tv/"}
CLASSES = [("1", "电影"), ("2", "电视剧"), ("3", "综艺"), ("4", "动漫"), ("21", "短剧"),
           ("20", "港剧"), ("13", "陆剧"), ("15", "日韩剧"), ("14", "台泰剧")]
ALPHA_SIGN = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALPHA_TOKEN = "XYZ0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVW"


def _row(key, names):
    return {"key": key, "name": key, "value": [{"n": n, "v": "" if n == "时间" else n} for n in names.split(" ")]}


_LETTER = _row("letter", "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z 0~9")
_BY = _row("by", "时间 人气 评分")
_MOVIE = [_row("class", "喜剧 爱情 恐怖 动作 科幻 剧情 警匪 战争 犯罪 动画 奇幻 武侠 冒险 悬疑 惊悚 古装 同性"),
          _row("area", "大陆 香港 台湾 韩国 英国 法国 加拿大 澳大利亚"), _row("year", "2026 2025 2024 2023 2022 2020 2019"),
          _row("lang", "国语 粤语 韩语 英语 法语"), _LETTER, _BY]
_SERIES = [_row("class", "悬疑 武侠 科幻 都市 爱情 古装 战争 青春 偶像 喜剧 家庭 奇幻 剧情 乡村 年代 警匪 谍战 历险 罪案 宫廷 经典 动作 惊悚 历史 穿越 同性"),
           _row("area", "大陆 香港 台湾 韩国 日本 新加坡 泰国"), _row("year", "2026 2025 2024 2023 2022 2021 2020 2019 2018 2017 更早"),
           _row("lang", "国语 粤语 韩语 泰语 日语"), _LETTER, _BY]
_VARIETY = [_row("class", "真人秀 选秀 竞演 情感 旅游 音乐 美食 纪实 生活 游戏互动 竞技 搞笑 脱口秀"),
            _row("area", "大陆 韩国"), _row("year", "2026 2025 2024 2023 2022 2021 2020 2019 更早"),
            _row("lang", "国语 韩语"), _LETTER, _BY]
FILTERS = {"1": _MOVIE, "2": _SERIES, "3": _VARIETY, "4": _SERIES, "13": _SERIES, "14": _SERIES,
           "15": _SERIES, "20": _SERIES, "21": _SERIES}


class JavaRandom:
    """java.util.Random, whose sequence the server checks."""
    MULTIPLIER = 0x5DEECE66D
    MASK = (1 << 48) - 1

    def __init__(self, seed):
        self.seed = (seed ^ self.MULTIPLIER) & self.MASK

    def next(self, bits):
        self.seed = (self.seed * self.MULTIPLIER + 0xB) & self.MASK
        value = (self.seed >> (48 - bits)) & 0xFFFFFFFF
        return value - (1 << 32) if value >= (1 << 31) else value

    # shortcut: no power-of-two branch; the only bounds here are 62 and 800000000. Add Java's branch before using a power of two.
    def nextInt(self, bound):
        u = self.next(31)
        r = u % bound
        while u - r + bound - 1 > 0x7FFFFFFF:  # Java's int-overflow test
            u = self.next(31)
            r = u % bound
        return r


def _pick(length, seed, alphabet):
    random = JavaRandom(seed)
    return "".join(alphabet[random.nextInt(len(alphabet))] for _ in range(length))


def _sign(ms=None):
    ms = int(time.time() * 1000) if ms is None else ms
    t = ms // 1000
    r = JavaRandom(t).nextInt(800000000)
    a, b = str(100000000 + r) + str(900000000 - r), str(ms)
    n = min(len(a), len(b))
    mixed = "".join(a[i] + b[i] for i in range(n)) + a[n:] + b[n:]
    ssid = base64.b64encode(mixed.encode()).decode().replace("=", ".")
    return "?sign=" + _pick(60, 2 * t + 60, ALPHA_SIGN) + "&ssid=" + ssid + "&token=" + _pick(38, 2 * t + 38, ALPHA_TOKEN)


def _text(value):
    return "" if value is None else str(value)


def _decode(value):
    """Reverse every 10 characters, '.' back to '=', base64. '' when it does not decode."""
    s = _text(value)
    flipped = "".join(s[i:i + 10][::-1] for i in range(0, len(s), 10)).replace(".", "=")
    try:
        return base64.b64decode(flipped, validate=True).decode("utf-8")
    except Exception:
        return ""


def _enc(value):
    return quote(_text(value), safe="-_.!~*'()")


def _page_number(pg):
    s = _text(pg).strip()
    return max(1, int(s)) if re.match(r"^[+-]?\d+$", s) else 1


def _remarks(item):
    tag, rating = item.get("Tag"), item.get("Rating")
    if isinstance(tag, str):
        return tag
    if isinstance(rating, (int, float)) and not isinstance(rating, bool):
        return ("%.1f" % rating if float(rating).is_integer() else str(rating)) + "分"
    return ""


def _vods(items):
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        vid = _decode(item.get("DId"))
        if not vid.startswith("/voddetail/"):
            continue
        out.append({"vod_id": vid, "vod_name": _text(item.get("Name")), "vod_pic": _decode(item.get("TnId")),
                    "vod_remarks": _remarks(item)})
    return out


class Spider(BaseSpider):
    def getName(self):
        return "獨播影視"

    def _api(self, path, query=""):
        try:
            response = requests.get(API + path + _sign() + query, headers=HEADERS, timeout=15)
            return response.json() if response.status_code == 200 else None
        except Exception as error:
            self.log("Duboku request failed: %s | %s" % (path, error))
            return None

    def homeContent(self, filter):
        return {"class": [{"type_id": tid, "type_name": name} for tid, name in CLASSES], "filters": FILTERS}

    def homeVideoContent(self):
        items = []
        sections = self._api("/home")
        for section in sections if isinstance(sections, list) else []:
            if isinstance(section, dict):
                items += _vods(section.get("VodList"))
        return {"list": items}

    # /vodshow/{cateId}-{area}-{by}-{class}-{lang}----{pg}---{year}, each part URL-encoded.
    def categoryContent(self, tid, pg, filter, extend):
        ext = extend if isinstance(extend, dict) else {}
        page = _page_number(pg)

        def part(key, fallback=""):
            return _enc(ext.get(key, fallback))

        path = ("/vodshow/" + part("cateId", tid) + "-" + part("area") + "-" + part("by") + "-" + part("class")
                + "-" + part("lang") + "----" + str(page) + "---" + part("year"))
        data = self._api(path)
        # Upstream's paging, unbounded: 48 a page.
        return {"list": _vods(data.get("VodList") if isinstance(data, dict) else None), "page": page,
                "pagecount": 44739243, "limit": 48, "total": 2147483647}

    def detailContent(self, ids):
        vid = _text(ids[0] if ids else "")
        if not vid.startswith("/voddetail/"):
            return {"list": []}
        d = self._api(vid)
        if not isinstance(d, dict) or not isinstance(d.get("Playlist"), list):
            return {"list": []}
        episodes = []
        for ep in d["Playlist"]:
            path = _decode(ep.get("VId")) if isinstance(ep, dict) else ""
            if re.match(r"^/vodplay/[^$#]*$", path):
                episodes.append(re.sub(r"[$#]", " ", _text(ep.get("EpisodeName"))) + "$" + path)
        actors = d.get("Actor")
        return {"list": [{
            "vod_id": vid,
            "vod_name": _text(d.get("Name")),
            "vod_pic": _decode(d.get("TnId")),
            "vod_year": _text(d.get("ReleaseYear")),
            "vod_content": _text(d.get("Description")),
            "vod_actor": ",".join(a for a in actors if isinstance(a, str)) if isinstance(actors, list) else "",
            "vod_director": _text(d.get("Director")),
            "vod_play_from": "独播库" if episodes else "",
            "vod_play_url": "#".join(episodes),
        }]}

    # Upstream asks once and ignores the page.
    def searchContent(self, key, quick, pg="1"):
        wd = _text(key).strip()
        if not wd:
            return {"list": []}
        return {"list": _vods(self._api("/vodsearch", "&wd=" + _enc(wd)))}

    # Accepts upstream's older "path|episode|title" ids too.
    def playerContent(self, flag, id, vipFlags):
        path = _text(id).split("|")[0]
        d = self._api(path) if path.startswith("/vodplay/") else None
        url = _decode(d.get("HId")) if isinstance(d, dict) else ""
        if not re.match(r"^https?://", url):
            return {"parse": 0, "url": ""}
        return {"parse": 0, "url": url,
                "header": {"User-Agent": UA, "Origin": "https://w.duboku.io", "Referer": "https://w.duboku.io/"}}
