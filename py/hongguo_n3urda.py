"""TVBox Python Spider for N3urda/hongguoTV's content service API v1."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object


_ID = re.compile(r"[0-9]{1,30}")
_STREAM_PATH = re.compile(r"/api/episodes/[0-9]{1,30}/stream")
_MAX_JSON_BYTES = 4 * 1024 * 1024


class BridgeError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _identifier(value):
    if isinstance(value, str) and _ID.fullmatch(value):
        return value
    raise BridgeError("內容服務提供的劇集 ID 無效")


def _card(series):
    if not isinstance(series, dict) or not isinstance(series.get("title"), str) or not series["title"].strip():
        raise BridgeError("內容服務的劇集資料格式不符")
    return {
        "vod_id": _identifier(series.get("id")),
        "vod_name": series["title"],
        "vod_pic": series.get("cover") or "",
        "vod_remarks": series.get("badge") or "",
        "vod_content": series.get("description") or "",
    }


class Spider(BaseSpider):
    def init(self, extend=""):
        if isinstance(extend, str):
            try:
                extend = json.loads(extend or "{}")
            except ValueError as error:
                raise BridgeError("站台 ext 必須是 JSON，內含 baseUrl") from error
        if not isinstance(extend, dict):
            raise BridgeError("站台 ext 必須是 JSON，內含 baseUrl")

        url = str(extend.get("baseUrl") or "").strip().rstrip("/")
        try:
            parts = urlsplit(url)
            valid_url = (
                parts.scheme in ("http", "https") and parts.hostname
                and parts.username is None and not parts.query and not parts.fragment
            )
            port = parts.port
        except ValueError:
            valid_url, port = False, None
        if not valid_url or port == 0 or any(character.isspace() for character in url):
            raise BridgeError("請在站台 ext.baseUrl 設定 N3urda 內容服務的 HTTP(S) 位址")

        token = extend.get("token") or ""
        if not isinstance(token, str) or any(not 33 <= ord(char) <= 126 for char in token):
            raise BridgeError("內容服務口令含有不支援的字元")
        self.base_url = url
        self.headers = {"Authorization": "Bearer " + token} if token else {}
        self.opener = build_opener(_NoRedirect())

    def getName(self):
        return "紅果短劇（N3urda 內容服務）"

    def _request(self, path, params=None):
        if not getattr(self, "base_url", None):
            raise BridgeError("尚未設定 N3urda 內容服務位址")
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={**self.headers, "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(_MAX_JSON_BYTES + 1)
            if len(raw) > _MAX_JSON_BYTES:
                raise BridgeError("內容服務回應過大")
            data = json.loads(raw)
        except HTTPError as error:
            error.close()
            if error.code in (401, 403):
                raise BridgeError("內容服務拒絕存取，請確認服務口令及權限") from None
            raise BridgeError(f"內容服務回傳 HTTP {error.code}") from None
        except (URLError, OSError):
            raise BridgeError("無法連線至 N3urda 內容服務") from None
        except ValueError:
            raise BridgeError("內容服務回傳無效的 JSON") from None
        if not isinstance(data, dict) or "error" in data:
            raise BridgeError("內容服務回應格式不符")
        return data

    def _list(self, path, page, **params):
        try:
            page = min(100, max(1, int(page)))
        except (ValueError, TypeError):
            page = 1
        items = self._request(path, {"page": page, **params}).get("items")
        if not isinstance(items, list):
            raise BridgeError("內容服務回傳無效的列表")
        cards = [_card(item) for item in items]
        page_count = page + 1 if cards and page < 100 else page
        return {"list": cards, "page": page, "pagecount": page_count}

    def homeContent(self, filter):
        return {"class": [{"type_id": "recommended", "type_name": "推薦"}]}

    def homeVideoContent(self):
        return self._list("/api/home", 1)

    def categoryContent(self, tid, pg, filter, extend):
        if tid != "recommended":
            return {"list": []}
        return self._list("/api/home", pg)

    def searchContent(self, key, quick=False, pg="1"):
        keyword = str(key or "").strip()
        if not keyword:
            return {"list": []}
        return self._list("/api/search", pg, q=keyword)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        series_id = _identifier(ids[0])
        data = self._request("/api/series/" + series_id)
        if data.get("id") != series_id or not isinstance(data.get("episodes"), list):
            raise BridgeError("內容服務回傳的劇集詳情不符")
        item = _card(data)
        episodes = []
        seen = set()
        for episode in data["episodes"]:
            if not isinstance(episode, dict):
                raise BridgeError("內容服務回傳無效的分集")
            episode_id = _identifier(episode.get("id"))
            if episode_id in seen:
                continue
            seen.add(episode_id)
            title = str(episode.get("title") or f"第 {episode.get('number') or len(episodes) + 1} 集")
            title = title.replace("#", "＃").replace("$", "＄")
            episodes.append(title + "$" + episode_id)
        item["vod_play_from"] = "N3urda" if episodes else ""
        item["vod_play_url"] = "#".join(episodes)
        return {"list": [item]}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            episode_path = "/api/episodes/" + _identifier(id)
            play = self._request(episode_path + "/play", {"fresh": 1})
            if play.get("path") != episode_path + "/stream" or play.get("contentType") != "video/mp4":
                raise BridgeError("內容服務回傳的播放路徑不符")
            return {"parse": 0, "jx": 0, "url": self.base_url + play["path"], "header": self.headers}
        except BridgeError as error:
            return {"parse": 0, "jx": 0, "url": "", "msg": str(error)}

    def isVideoFormat(self, url):
        return bool(_STREAM_PATH.search(urlsplit(url).path))

    def manualVideoCheck(self):
        return False
