# -*- coding: utf-8 -*-
"""
洛雪TV / LXYY CatVod Python Spider（W-195，邏輯沿用 W-191 已審的 Lxyy.js）
- Android: FongMi PyLoader（需安裝 Python 模組）；iOS: WebHTV PythonSpiderRuntime
- 只用兩端共同能力：base.spider + Python 標準庫（requests 可用時用 Session 保留播放授權 cookie）
- 站方公開介面只有搜尋與詳情，沒有分類列表，所以首頁與分類為空
- 照網站自己的流程：詳情前先 POST playback-session；need_captcha 就停，不取題、不解題、不重試
- 只列直接媒體（m3u8／mp4）；fy、qilin 是平台頁要會員解析，不收；成人分類以完整名稱排除
"""

import html as html_lib
import json
import re
from urllib.parse import quote

try:
    import requests as _requests
except Exception:
    _requests = None

from base.spider import Spider as BaseSpider


SITE = "https://tv.lxyy.club"
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
SOURCES = ["md", "mj", "jl", "360zy", "dytt", "ik"]
# 完整名稱比對（Reviewer #3734：不用會誤擋的模糊比對）
ADULT = {"伦理片", "倫理片", "伦理", "倫理", "里番", "里番动漫", "裏番", "福利", "福利片", "三级片", "三級片",
         "写真", "寫真", "情色", "情色片", "成人", "两性", "兩性"}
DIRECT = re.compile(r"^https?://\S+\.(m3u8|mp4)(\?|$)", re.I)


def _adult(kind):
    return str(kind or "").strip() in ADULT


def _label(value):
    return re.sub(r"[$#]", " ", str(value or "")).strip()


def _strip(value):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]*>", "", value or ""))).strip()


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.headers = {"User-Agent": UA, "Referer": SITE + "/"}
        self.session = _requests.Session() if _requests is not None else None

    def getName(self):
        return "洛雪TV"

    def init(self, extend=""):
        pass

    def _request(self, method, path, body=None):
        url = SITE + path
        try:
            if self.session is not None:
                if method == "POST":
                    response = self.session.post(url, data=body or "", headers=self.headers, timeout=15)
                else:
                    response = self.session.get(url, headers=self.headers, timeout=15)
            elif method == "POST":
                response = self.post(url, data=body or "", headers=self.headers, timeout=15)
            else:
                response = self.fetch(url, headers=self.headers, timeout=15)
            response.encoding = "utf-8"
            return response.status_code, response.text
        except Exception as error:
            self.log("LXYY request failed: %s | %s" % (url, error))
            return 0, ""

    def _proxy(self, query):
        status, text = self._request("GET", "/api/proxy.php?" + query)
        try:
            data = json.loads(text)
        except Exception:
            data = None
        if isinstance(data, dict) and data.get("need_captcha"):
            raise Exception("洛雪：網站要求人工驗證，請稍後再試")
        if status != 200 or not isinstance(data, dict) or not data.get("success"):
            raise Exception("洛雪：公開介面沒有回應（HTTP %s）" % status)
        return data

    def homeContent(self, filter):
        return {"class": []}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def searchContent(self, key, quick, pg="1"):
        page = max(int(pg or 1), 1)
        data = self._proxy("action=search&wd=%s&page=%d" % (quote(key), page))
        videos = []
        for item in data.get("results") or []:
            if item.get("source") not in SOURCES or _adult(item.get("type")):
                continue
            videos.append({
                "vod_id": "%s|%s" % (item.get("source"), item.get("id")),
                "vod_name": item.get("name") or "",
                "vod_pic": item.get("pic") or "",
                "vod_remarks": item.get("remarks") or item.get("type") or "",
            })
        return {"list": videos}

    def detailContent(self, ids):
        vid = str(ids[0])
        parts = vid.split("|")
        if len(parts) != 2 or parts[0] not in SOURCES or not parts[1].isdigit():
            raise Exception("洛雪：無效的影片 ID")
        status, text = self._request("POST", "/api/playback-session.php")
        try:
            grant = json.loads(text)
        except Exception:
            grant = None
        if status != 200 or not isinstance(grant, dict) or not grant.get("success"):
            raise Exception("洛雪：網站沒有給播放授權")
        data = self._proxy("action=detail&source=%s&id=%s" % (quote(parts[0]), quote(parts[1])))
        details = data.get("details") or []
        if not details:
            raise Exception("洛雪：找不到這部影片")
        d = details[0]
        if _adult(d.get("type")):
            raise Exception("洛雪：這個分類不提供")
        froms, urls = [], []
        for group in d.get("episodes") or []:
            episodes = ["%s$%s" % (_label(e.get("name")) or "播放", e.get("url"))
                        for e in group.get("episodes") or [] if DIRECT.match(str(e.get("url") or ""))]
            if episodes:
                froms.append(_label(group.get("group")) or parts[0])
                urls.append("#".join(episodes))
        if not urls:
            raise Exception("洛雪：這部影片沒有可直接播放的線路")
        return {"list": [{
            "vod_id": vid,
            "vod_name": d.get("name") or "",
            "vod_pic": d.get("pic") or "",
            "vod_remarks": d.get("remarks") or "",
            "type_name": d.get("type") or "",
            "vod_year": str(d.get("year") or ""),
            "vod_area": d.get("area") or "",
            "vod_actor": d.get("actor") or "",
            "vod_director": d.get("director") or "",
            "vod_content": _strip(d.get("content") or ""),
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }]}

    def playerContent(self, flag, id, vipFlags):
        if not DIRECT.match(str(id)):
            raise Exception("洛雪：不是可直接播放的網址")
        return {"parse": 0, "url": id, "header": {"Referer": SITE + "/", "User-Agent": UA}}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def destroy(self):
        pass
