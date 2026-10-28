# -*- coding: utf-8 -*-
"""
搜TV啦 / SOTVLA CatVod Python Spider（W-195）
- Android: FongMi PyLoader（需安裝 Python 模組）；iOS: WebHTV PythonSpiderRuntime
- 只用兩端共同能力：base.spider + Python 標準庫（requests 可用時用它保留 cookie）
- 網站只有搜尋入口，沒有分類列表，所以首頁與分類為空
- 只播放公開頁面列出的直接媒體（m3u8／mp4）；平台會員解析線路明確拒絕
"""

import html as html_lib
import json
import re
from urllib.parse import quote, unquote

try:
    import requests as _requests
except Exception:
    _requests = None

from base.spider import Spider as BaseSpider


SITE = "https://www.sotvla.cc"
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)


def _text(value):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]*>", "", value or ""))).strip()


def _label(value):
    return re.sub(r"[$#]", " ", _text(value))


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.headers = {"User-Agent": UA, "Referer": SITE + "/"}
        self.session = _requests.Session() if _requests is not None else None

    def getName(self):
        return "搜TV啦"

    def init(self, extend=""):
        pass

    def _get(self, path):
        url = path if path.startswith("http") else SITE + path
        try:
            if self.session is not None:
                response = self.session.get(url, headers=self.headers, timeout=15)
            else:
                response = self.fetch(url, headers=self.headers, timeout=15)
            response.encoding = "utf-8"
            if response.status_code != 200:
                raise Exception("HTTP %s" % response.status_code)
            return response.text
        except Exception as error:
            self.log("SOTVLA request failed: %s | %s" % (url, error))
            raise Exception("搜TV啦：公開頁面讀取失敗")

    def homeContent(self, filter):
        return {"class": []}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def searchContent(self, key, quick, pg="1"):
        if int(pg or 1) > 1:
            return {"list": []}
        source = self._get("/search.php?q=" + quote(key))
        videos = []
        for block in source.split('<article class="search-result-item"')[1:]:
            href = re.search(r'href="(/detail\.php\?[^"]+)"', block)
            if not href:
                continue
            title = re.search(r'class="sr-title"[^>]*>([\s\S]*?)</a>', block)
            pic = re.search(r'<img[^>]*\ssrc="([^"]+)"', block)
            videos.append({
                "vod_id": html_lib.unescape(href.group(1)),
                "vod_name": _text(title.group(1) if title else ""),
                "vod_pic": pic.group(1) if pic else "",
                "vod_remarks": "",
            })
        return {"list": videos}

    def detailContent(self, ids):
        vid = str(ids[0])
        if not re.match(r"^/detail\.php\?api_id=\d+&vod_id=\d+$", vid):
            raise Exception("搜TV啦：無效詳情 ID")
        source = self._get(vid)
        names = [_label(n) for n in re.findall(r'class="play-source-tab[^"]*"[^>]*>([\s\S]*?)</', source)]
        lines = []
        for panel in source.split('class="play-ep-panel"')[1:]:
            episodes = re.findall(r'<a class="play-ep-pill[^"]*" href="([^"]+)"[^>]*>([\s\S]*?)</a>', panel)
            lines.append("#".join("%s$%s" % (_label(n), SITE + html_lib.unescape(h)) for h, n in episodes))
        title = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", source)
        pic = re.search(r'detail-poster[\s\S]*?<img[^>]*\ssrc="([^"]+)"', source)
        return {"list": [{
            "vod_id": vid,
            "vod_name": _text(title.group(1) if title else ""),
            "vod_pic": pic.group(1) if pic else "",
            "vod_play_from": "$$$".join(names[:len(lines)]),
            "vod_play_url": "$$$".join(lines),
        }]}

    def playerContent(self, flag, id, vipFlags):
        if not re.match(r"^https://www\.sotvla\.cc/play\.php\?", id):
            raise Exception("搜TV啦：無效播放頁")
        frame = re.search(r'<iframe[^>]*id="play-player-iframe"[^>]*src="([^"]+)"', self._get(id))
        query = html_lib.unescape(frame.group(1)) if frame else ""
        for value in re.findall(r"[?&]url=([^&]*)", query):
            media = unquote(value)
            if re.match(r"^https?://", media) and re.search(r"\.(m3u8|mp4)(\?|$)", media, re.I):
                return {"parse": 0, "url": media, "header": {"Referer": SITE + "/", "User-Agent": UA}}
        raise Exception("搜TV啦：未公開直接媒體；平台會員解析不納入")

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def destroy(self):
        pass
