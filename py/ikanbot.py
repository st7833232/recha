# -*- coding: utf-8 -*-
"""
愛看機器人 / Ikanbot CatVod Python Spider (W-200)
- Android: FongMi 影視 PyLoader；iOS: WebHTV PythonSpiderRuntime
- Port of WebHTV ios/Spiders/Ikanbot.js (itself a port of com.github.catvod.spider.Ikanbot).
- 回傳 dict（FongMi 的 app.py 會自己 json.dumps；回傳字串會被編碼兩次而變空站），iOS 也接受 dict。
- 只用 base.spider、requests、lxml（含 cssselect）與 Python 標準庫；兩端都內建。
ext: site host, e.g. "https://www1.aikanbot.com", optionally followed by "[排序:k1,k2]".
"""

import json
import re
from urllib.parse import quote

import requests
from lxml import html as lxml_html

from base.spider import Spider as BaseSpider

HOST = "https://www1.ikanbot.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/151.0.0.0 Safari/537.36")
CLASSES = [("hot/index-movie-热门", "电影"), ("hot/index-tv-热门", "剧集"), ("billboard", "榜单"), ("kanlist/全部", "片单")]
MAX = 2147483647


def _f(prefix, names):
    return [{"v": "", "n": "全部"}] + [{"v": prefix + v, "n": n} for v, n in names]


# Ikanbot.java:313, verbatim (its stray spaces included).
FILTERS = {
    "kanlist/全部": [{"name": "分类", "key": "cateId", "value": _f("kanlist/", [
        ("剧情", "剧情"), ("情感", "情感"), ("治愈", "治愈"), ("爱情", "爱情"), ("颁奖", "颁奖"), ("喜剧", "喜剧"),
        ("获奖", "获奖"), (" 科幻", "科幻"), ("漫威", "漫威"), ("甜蜜", "甜蜜"), ("悬疑", "悬疑"), ("励志", "励志"),
        ("烧脑", "烧脑"), ("友情", "友情")])}],
    "billboard": [],
    "hot/index-movie-热门": [{"name": "分类", "key": "cateId", "value": _f("hot/index-movie-", [
        ("最新", "最新"), ("经典", "经典"), ("豆瓣高 分", "豆瓣高分"), ("冷门佳片", "冷 门佳片"), ("华语", "华语"),
        ("欧美", "欧美"), ("韩国", "韩国"), ("日本", "日本"), ("动作", "动作"), ("喜剧", "喜剧"), ("爱情", "爱情"),
        ("科幻", "科幻"), ("悬疑", "悬疑"), ("恐怖", "恐怖"), ("成长", "成长"), ("豆瓣top250", "豆瓣top250")])}],
    "hot/index-tv-热门": [{"name": "分类", "key": "cateId", "value": _f("hot/index-tv-", [
        ("美剧", "美剧"), ("英剧", "英剧"), ("韩剧", "韩剧"), ("日剧", "日剧"), ("国产剧", "国产剧"), ("港剧", "港剧"),
        ("日本动画", "日本动画"), ("综艺", "综艺"), ("纪录片", "纪录片")])}],
}


def _text(value):
    return "" if value is None else str(value)


def _page_number(pg):
    try:
        n = int(_text(pg).strip())
    except ValueError:
        return 1
    return n if n > 1 else 1


def _douban(pic):
    """A douban poster needs this Referer (a bare request answers 418)."""
    if not pic:
        return ""
    return pic + "@Headers=" + json.dumps({"User-Agent": UA, "Referer": "https://www.douban.com"}, separators=(",", ":"))


def _first(node, selector):
    found = node.cssselect(selector)
    return found[0] if found else None


def _attr(node, selector, name):
    el = _first(node, selector)
    return (el.get(name) or "").strip() if el is not None else ""


def _txt(node, selector):
    el = _first(node, selector)
    return " ".join(el.text_content().split()) if el is not None else ""


def _tks(video_id, token):
    """Ikanbot.java:42–62. '' on a short or non-numeric id or a short token."""
    video_id, token = _text(video_id), _text(token)
    tail = video_id[-4:]
    if len(video_id) < 4 or not re.match(r"^\d{4}$", tail):
        return ""
    out = ""
    for ch in tail:
        i = int(ch) % 3
        if len(token) < i + 9:
            return ""
        out += token[i + 1:i + 9]
        token = token[i + 9:]
    return out


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.site = HOST
        self.order = ""

    def getName(self):
        return "愛看機器人"

    # `$$$` starts TVBox add-on flags; they are dropped.
    def init(self, extend=""):
        ext = _text(extend).split("$$$")[0]
        self.site, self.order = HOST, ""
        if ext.startswith("http"):
            self.site = ext.split("[")[0].rstrip("/")
        if "[排序:" in ext:
            self.order = "[" + ext.split("[", 1)[1]

    def _headers(self):
        return {"User-Agent": UA, "Referer": self.site}

    def _page(self, url):
        try:
            response = requests.get(url, headers=self._headers(), timeout=15)
            response.encoding = "utf-8"
            return response.text if response.status_code == 200 else ""
        except Exception as error:
            self.log("Ikanbot request failed: %s | %s" % (url, error))
            return ""

    def _video(self, node, name_selector):
        return {"vod_id": _attr(node, "a", "href"), "vod_name": _txt(node, name_selector),
                "vod_pic": _douban(_attr(node, "img", "data-src")), "vod_remarks": ""}

    def _sorted(self, names, urls):
        """[排序:k1,k2]: lines whose name contains k1, then k2, ahead of the rest, each moved once."""
        if "[排序:" not in self.order:
            return names, urls
        keys = self.order.split("[排序:")[1].split("]")[0].split(",")
        rest, front = list(range(len(names))), []
        for key in keys:
            front += [i for i in rest if key in names[i]]
            rest = [i for i in rest if key not in names[i]]
        order = front + rest
        return [names[i] for i in order], [urls[i] for i in order]

    def homeContent(self, filter):
        return {"class": [{"type_id": tid, "type_name": name} for tid, name in CLASSES], "filters": FILTERS}

    # Every div.v-list on the home page (it has two).
    def homeVideoContent(self):
        source = self._page(self.site)
        items = []
        if source:
            doc = lxml_html.fromstring(source)
            for block in doc.cssselect("body div.v-list"):
                items += [self._video(node, "p") for node in block.cssselect("div.item")]
        return {"list": items}

    def categoryContent(self, tid, pg, filter, extend):
        cid, n = _text(tid), _page_number(pg)
        kanlist, article, billboard = "kanlist" in cid, "article" in cid, "billboard" in cid
        empty = {"list": [], "page": n, "pagecount": n, "limit": 0, "total": 0}
        template = self.site + "/{cateId}.html"
        if kanlist:
            template = self.site + "/{cateId}-p-" + str(n) + ".html"
        if article:
            template = self.site + cid
        if n != 1:
            if billboard or article:
                return empty
            template = self.site + "/{cateId}-p-" + str(n) + ".html"
        for key, value in (extend if isinstance(extend, dict) else {}).items():
            if _text(value):
                template = template.replace("{" + key + "}", _text(value))
        source = self._page(template.replace("{cateId}", cid))
        if not source:
            return empty
        doc = lxml_html.fromstring(source)
        if kanlist:
            items = [{"vod_id": _attr(node, "a", "href"), "vod_name": _txt(node, "h5"),
                      "vod_pic": _attr(node, "img", "data-src"), "vod_remarks": "", "vod_tag": "folder"}
                     for node in doc.cssselect("div.reslut-list div.media")]
        else:
            rule = ("div#video-list div.item", ".title") if billboard or article else ("div.v-list div.item", "p")
            items = []
            for node in doc.cssselect(rule[0]):
                item = self._video(node, rule[1])
                item["vod_tag"] = "file"
                items.append(item)
        if not items:
            return empty
        return {"list": items, "page": n, "pagecount": MAX, "limit": len(items), "total": MAX}

    def detailContent(self, ids):
        vid = _text(ids[0] if ids else "").split("$$$")[0]
        none = {"list": []}
        if not vid.startswith("/"):
            return none
        source = self._page(self.site + vid)

        def field(name):
            m = re.search('id="' + name + '" value="([^"]*)"', source)
            return m.group(1) if m else ""

        video_id, mtype = field("current_id"), field("mtype")
        token = _tks(video_id, field("e_token"))
        if not source or not token:
            return none
        try:
            response = requests.get(
                self.site + "/api/getResN?videoId=" + video_id + "&mtype=" + mtype + "&token=" + token,
                headers={"User-Agent": UA, "Referer": self.site + vid, "Accept": "*/*",
                         "X-Requested-With": "XMLHttpRequest"}, timeout=15)
            data = response.json() if response.status_code == 200 else None
        except Exception as error:
            self.log("Ikanbot getResN failed: %s | %s" % (vid, error))
            data = None
        rows = data.get("data", {}).get("list") if isinstance(data, dict) and isinstance(data.get("data"), dict) else None
        if not isinstance(rows, list):
            return none
        names, urls = [], []
        for row in rows:
            raw = _text(row.get("resData")) if isinstance(row, dict) else ""
            try:
                episodes = json.loads(raw) if raw else None
            except ValueError:
                continue
            if not isinstance(episodes, list) or not episodes or not isinstance(episodes[0], dict):
                continue
            flag = _text(episodes[0].get("flag"))
            names.append(flag.replace("m3u8", "线路"))
            line = []
            for ep in episodes:
                url = _text(ep.get("url") if isinstance(ep, dict) else "")
                line.append(url.replace("$" + flag + "#", "").replace("$" + flag, "") if flag else url)
            urls.append("#".join(line))
        names, urls = self._sorted(names, urls)
        doc = lxml_html.fromstring(source)
        return {"list": [{
            "vod_id": vid,
            "vod_name": _txt(doc, "h1"),
            "vod_pic": _douban(_attr(doc, "img.cover", "data-src")),
            "vod_year": _txt(doc, "div.detail > .year"),
            "vod_area": _txt(doc, "div.detail > .country"),
            "vod_actor": _txt(doc, "div.detail > .celebrity"),
            "vod_content": "",
            "vod_play_from": "$$$".join(names),
            "vod_play_url": "$$$".join(urls),
        }]}

    def searchContent(self, key, quick, pg="1"):
        wd, n = _text(key).strip(), _page_number(pg)
        if not wd:
            return {"list": []}
        source = self._page(self.site + "/search?q=" + quote(wd, safe="-_.!~*'()") + ("&p=" + str(n) if n > 1 else ""))
        if not source:
            return {"list": []}
        items = []
        for node in lxml_html.fromstring(source).cssselect("body .media"):
            item = self._video(node, ".title-text")
            item["vod_name"] = re.sub(r"\s\d{4}$", "", item["vod_name"]).strip()
            item["vod_remarks"] = _txt(node, "span.label")
            items.append(item)
        return {"list": items}

    # Direct play with the desktop user agent, and only that header.
    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "url": _text(id), "header": {"User-Agent": UA}}

    def destroy(self):
        pass
