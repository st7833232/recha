# -*- coding: utf-8 -*-
import re
import time
import urllib.parse
import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass

class Spider(BaseSpider):
    # Tried in order when the current one fails; the first that answers serves every later page, detail and play.
    MIRRORS = ["https://jable.sbs", "https://jable.my", "https://jable01.net", "https://jable666.net"]
    BASE_URL = MIRRORS[0]
    TIMEOUT = 8   # one request
    BUDGET = 25   # one page across every mirror
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": BASE_URL + "/",
    }

    def __init__(self):
        super().__init__()
        self.name = "JableTV"
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.base = self.BASE_URL
        self._class_cache = None

    def init(self, extend="{}"):
        return None

    def getName(self):
        return self.name

    def homeContent(self, filter):
        html = self._get(self.base + "/latest-updates/")
        return {"class": self._classes(), "filters": {}, "list": self._parse_list(html), "parse": 0, "jx": 0}

    def homeVideoContent(self):
        return {"list": self._parse_list(self._get(self.base + "/latest-updates/"))}

    def categoryContent(self, tid, pg, filter, extend):
        page = self._to_int(pg, 1)
        path = str(tid or "latest-updates").strip("/")
        url = self.base + "/" + path + "/" if page <= 1 else self.base + "/" + path + "/" + str(page) + "/"
        data = self._parse_list(self._get(url))
        return {"page": page, "pagecount": page if len(data) < 10 else page + 1, "limit": 24, "total": 99999, "list": data, "parse": 0, "jx": 0}

    def detailContent(self, ids):
        result = {"list": [], "parse": 0, "jx": 0}
        if not ids:
            return result
        url = self._fix_url(ids[0] if str(ids[0]).startswith("http") else self.base + "/videos/" + str(ids[0]).strip("/") + "/")
        html = self._get(url)
        name = self._clean(self._match(html, r'<h4[^>]*>(.*?)</h4>') or self._match(html, r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)') or self._match(html, r'<title>(.*?)</title>').split("-")[0])
        pic = self._match(html, r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)') or self._match(html, r'<video[^>]+poster=["\']([^"\']+)') or self._match(html, r'<img[^>]+(?:data-src|src)=["\']([^"\']+)')
        tags = ",".join([self._clean(x) for x in re.findall(r'<a[^>]+href=["\'][^"\']*/tags/[^"\']+["\'][^>]*>(.*?)</a>', html, re.S)])
        remarks = self._clean(" ".join(re.findall(r'<h6[^>]*>(.*?)</h6>', html, re.S)[:3]))
        content = self._clean(self._match(html, r'<div[^>]+class=["\'][^"\']*(?:description|info|text)[^"\']*["\'][^>]*>(.*?)</div>') or remarks or name)
        m3u8 = self._m3u8(html)
        result["list"].append({"vod_id": url, "vod_name": name, "vod_pic": urllib.parse.urljoin(self.base, pic), "type_name": tags, "vod_year": "", "vod_area": "", "vod_remarks": remarks, "vod_actor": tags, "vod_director": "", "vod_content": content, "vod_play_from": "Jable", "vod_play_url": "正片$" + (m3u8 or url)})
        return result

    def searchContent(self, key, quick, pg="1"):
        page = self._to_int(pg, 1)
        q = urllib.parse.quote(str(key))
        url = self.base + "/search/" + q + "/" if page <= 1 else self.base + "/search/" + q + "/" + str(page) + "/"
        data = self._parse_list(self._get(url))
        return {"page": page, "pagecount": page if len(data) < 10 else page + 1, "limit": 24, "total": 99999, "list": data, "parse": 0, "jx": 0}

    def playerContent(self, flag, id, vipFlags):
        result = {"parse": 0, "playUrl": "", "url": id or "", "jx": 0, "header": {"User-Agent": self.HEADERS["User-Agent"], "Referer": self.base + "/"}}
        if not id:
            return result
        if ".m3u8" in id or ".mp4" in id:
            return result
        play_page = self._fix_url(id if str(id).startswith("http") else self.base + "/videos/" + str(id).strip("/") + "/")
        html = self._get(play_page)
        m3u8 = self._m3u8(html)
        if m3u8:
            result["url"] = m3u8
            result["header"] = {"User-Agent": self.HEADERS["User-Agent"], "Referer": play_page, "Origin": self.base}
        else:
            result["url"] = play_page
            result["parse"] = 1
        return result

    def _classes(self, html=None):
        if self._class_cache:
            return self._class_cache
        self._class_cache = [
            {"type_id": "latest-updates", "type_name": "最近更新"},
            {"type_id": "hot", "type_name": "热门影片"},
            {"type_id": "new-release", "type_name": "全新上市"},
            {"type_id": "tags/chinese-subtitle", "type_name": "中文字幕"},
            {"type_id": "tags/drama", "type_name": "剧情"},
            {"type_id": "tags/cosplay", "type_name": "角色扮演"},
        ]
        return self._class_cache

    def _parse_list(self, html):
        data, seen = [], set()
        cards = re.findall(r'(<div[^>]+class=["\'][^"\']*video-img-box[^"\']*["\'][\s\S]*?</h6>[\s\S]*?</div>\s*</div>)', html or "", re.S | re.I)
        if not cards:
            cards = re.findall(r'(<a[^>]+href=["\'][^"\']*/videos/[^"\']+["\'][\s\S]*?</a>)', html or "", re.S | re.I)
        for item in cards:
            href = self._match(item, r'href=["\']([^"\']*/videos/[^"\']+)["\']')
            if not href:
                continue
            name = self._clean(self._match(item, r'<h6[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>\s*<a[^>]*>(.*?)</a>') or self._match(item, r'title=["\']([^"\']+)') or self._match(item, r'alt=["\']([^"\']+)'))
            pic = self._match(item, r'(?:data-src|data-original|data-lazy-src|data-lazyload)=["\']([^"\']+)') or self._match(item, r'<img[^>]+src=["\']([^"\']+)')
            remarks = self._clean(self._match(item, r'<span[^>]+class=["\'][^"\']*(?:duration|label|badge)[^"\']*["\'][^>]*>(.*?)</span>') or self._match(item, r'(\d{1,2}:\d{2}(?::\d{2})?)'))
            full = self._fix_url(urllib.parse.urljoin(self.base, href))
            if full not in seen and name and not re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', name):
                seen.add(full)
                data.append({"vod_id": full, "vod_name": name, "vod_pic": urllib.parse.urljoin(self.base, pic), "vod_remarks": remarks})
        return data

    def _get(self, url, headers=None):
        p = urllib.parse.urlsplit(self._fix_url(url))
        tail = p.path + ("?" + p.query if p.query else "")
        # Each mirror once, the working one first, all within BUDGET so a host app's 30 s call limit (FongMi) is not hit.
        # shortcut: requests' read timeout is per socket read, so a host trickling bytes can outlast it; a hard total needs a thread.
        deadline = time.time() + self.BUDGET
        failed = set()  # hosts that failed in this call: jable.sbs and jable.my both redirect to jable01.net
        for base in [self.base] + [m for m in self.MIRRORS if m != self.base]:
            h = dict(self.HEADERS)
            h["Referer"] = base + "/"
            if headers:
                h.update(headers)
            r = self._follow(base + tail, h, deadline, failed)
            if r is None:
                continue
            r.encoding = "utf-8"
            if r.status_code < 400 and "Just a moment" not in r.text and "cf-browser-verification" not in r.text:
                # Land on where the redirects end when it is a known mirror, so later requests skip the hops.
                final = "https://" + urllib.parse.urlsplit(r.url).netloc
                self.base = final if final in self.MIRRORS else base
                return r.text
            failed.add(urllib.parse.urlsplit(r.url).netloc)
        return ""

    def _follow(self, url, h, deadline, failed):
        # Redirects by hand, so a mirror that leads into a host already failed in this call is dropped at once.
        for _ in range(5):
            host = urllib.parse.urlsplit(url).netloc
            left = deadline - time.time()
            if host in failed or left < 1:
                return None
            t = min(self.TIMEOUT, left)
            try:
                r = self.session.get(url, headers=h, timeout=(min(5, t), t), verify=False, allow_redirects=False)
            except Exception:
                failed.add(host)
                return None
            if not r.is_redirect:
                return r
            url = urllib.parse.urljoin(url, r.headers["Location"])
        return None

    def _fix_url(self, url):
        # Any Jable host, old (jable.tv) or a mirror, moves to the one that works now.
        return re.sub(r'^https?://(?:www\.)?jable\d*\.(?:tv|sbs|my|net)(?=[/:?#]|$)', self.base, str(url or ""), flags=re.I)

    def _m3u8(self, html):
        return self._match(html, r'var\s+hlsUrl\s*=\s*["\']([^"\']+\.m3u8[^"\']*)') or self._match(html, r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']')

    def _match(self, text, pattern):
        m = re.search(pattern, text or "", re.S | re.I)
        return m.group(1).strip() if m else ""

    def _clean(self, text):
        text = re.sub(r'<.*?>', '', text or '')
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#038;', '&').replace('&quot;', '"')
        return re.sub(r'\s+', ' ', text).strip()

    def _to_int(self, value, default=0):
        try:
            return int(value)
        except Exception:
            return default