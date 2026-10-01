# -*- coding: utf-8 -*-
"""可可影視 / kkys20 TVBox-FongMi Spider

重點：
1. 保留 TVBox/FongMi 常用欄位：vod_year / vod_area / vod_type /
   vod_actor / vod_director / vod_content / vod_remarks。
2. 為了相容不會單獨顯示上述欄位的 App，將年代、地區、類型、導演、演員
   同步寫入 vod_content；年代/地區/類型也會組成 vod_remarks。
3. 不改變播放欄位格式：vod_play_from / vod_play_url。
"""

import json
import re
import sys
from urllib.parse import quote

from lxml import etree

sys.path.append("..")
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def getName(self):
        return "可可影视-WebHTV資訊版"

    def init(self, extend=""):
        self.host = "https://www.kkys20.com"
        self.image_host = "https://vres.cyscyy.com"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            "Referer": self.host + "/",
        }
        self.categories = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "连续剧"},
            {"type_id": "3", "type_name": "动漫"},
            {"type_id": "4", "type_name": "综艺"},
            {"type_id": "6", "type_name": "短剧"},
        ]

    # ---------- HTTP / HTML ----------
    def _get(self, url):
        try:
            response = self.fetch(url, headers=self.headers, timeout=15, verify=False)
            response.encoding = "utf-8"
            return response.text
        except Exception:
            return ""

    def _tree(self, html):
        if not html:
            return None
        try:
            return etree.HTML(html.encode("utf-8", "ignore"))
        except Exception:
            return None

    def _absolute(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        return url

    def _picture(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.image_host + url
        return url

    @staticmethod
    def _clean(value):
        return re.sub(r"\s+", " ", value or "").strip()

    @staticmethod
    def _first(values, default=""):
        return values[0] if values else default

    # ---------- Lists ----------
    def _parse_cards(self, html):
        tree = self._tree(html)
        if tree is None:
            return []

        items = []
        seen = set()
        nodes = tree.xpath('//div[contains(@class,"module-item")]//a[contains(@class,"v-item")]')
        for node in nodes:
            href = node.get("href", "")
            match = re.search(r"/detail/(\d+)\.html", href)
            if not match:
                continue
            vod_id = match.group(1)
            if vod_id in seen:
                continue

            title = self._clean("".join(node.xpath('.//div[contains(@class,"v-item-title")]//text()')))
            if not title:
                continue

            pic = self._first(
                node.xpath('.//img[not(contains(@data-original,"logo_placeholder"))]/@data-original')
            )
            remarks = self._clean("".join(node.xpath('.//div[contains(@class,"v-item-bottom")]//text()')))

            items.append(
                {
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": self._picture(pic),
                    "vod_remarks": remarks,
                }
            )
            seen.add(vod_id)
        return items

    def homeContent(self, filter):
        return {
            "class": self.categories,
            "list": self._parse_cards(self._get(self.host + "/")),
        }

    def homeVideoContent(self):
        return {"list": self._parse_cards(self._get(self.host + "/"))}

    def categoryContent(self, tid, pg, filter, extend):
        extend = extend or {}
        page = int(pg or 1)
        media_type = quote(str(extend.get("type", "")))
        area = quote(str(extend.get("area", "")))
        lang = quote(str(extend.get("lang", "")))
        year = quote(str(extend.get("year", "")))
        sort = str(extend.get("sort", "3") or "3")
        url = f"{self.host}/show/{tid}-{media_type}-{area}-{lang}-{year}-{sort}-{page}.html"
        html = self._get(url)
        items = self._parse_cards(html)
        has_next = bool(html and "page-item-next" in html)
        return {
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": len(items),
            "total": len(items),
            "list": items,
        }

    # ---------- Detail metadata ----------
    def _detail_rows(self, tree):
        """把站上『導演 / 演員 / 首映 / 備註 …』的 key-value 列轉成 dict。"""
        rows = {}
        for row in tree.xpath('//div[contains(@class,"detail-info-row")]'):
            key = self._clean(
                "".join(row.xpath('.//*[contains(@class,"detail-info-row-side")]//text()'))
            ).rstrip(":：")
            value = self._clean(
                "".join(row.xpath('.//*[contains(@class,"detail-info-row-main")]//text()'))
            )
            if key and value:
                rows[key] = value
        return rows

    @staticmethod
    def _pick_row(rows, *names):
        for name in names:
            value = rows.get(name)
            if value:
                return value
        return ""

    def _detail_tags(self, tree):
        tags = []
        for node in tree.xpath('//a[contains(@class,"detail-tags-item")]'):
            text = self._clean("".join(node.xpath('.//text()')))
            if text:
                tags.append(text)
        return tags

    def _play_lines(self, tree):
        source_names = []
        for node in tree.xpath('//div[contains(@class,"source-list-box-main")]//a[contains(@class,"source-item")]'):
            name = self._clean("".join(node.xpath('.//span[contains(@class,"source-item-label")]//text()')))
            if name:
                source_names.append(name)

        groups = []
        for group in tree.xpath('//div[contains(@class,"episode-list-box-main")]/div[contains(@class,"episode-list")]'):
            episodes = []
            for anchor in group.xpath('.//a[contains(@href,"/play/")]'):
                label = self._clean("".join(anchor.xpath('.//text()'))) or "播放"
                href = self._absolute(anchor.get("href", ""))
                if href:
                    episodes.append(f"{label}${href}")
            if episodes:
                groups.append(episodes)

        while len(source_names) < len(groups):
            source_names.append(f"线路{len(source_names) + 1}")

        result = []
        for index, episodes in enumerate(groups):
            name = source_names[index] if index < len(source_names) else f"线路{index + 1}"
            if "4k" in name.lower():
                continue
            result.append((name, episodes))
        return result

    def detailContent(self, ids):
        vod_id = str(ids[0])
        html = self._get(f"{self.host}/detail/{vod_id}.html")
        tree = self._tree(html)
        if tree is None:
            return {"list": []}

        # 可可頁面可能存在隱藏/水印 strong，因此先找可見位置，再 fallback。
        title = self._clean(
            "".join(tree.xpath('//div[contains(@class,"detail-title")]//strong[position() mod 2 = 0]/text()'))
        )
        if not title:
            title = self._clean(
                "".join(tree.xpath('//div[contains(@class,"detail-title")]//strong[1]/text()'))
            )

        picture = self._first(
            tree.xpath('//div[contains(@class,"detail-pic")]//img[not(contains(@data-original,"logo_placeholder"))]/@data-original')
        )
        original_desc = self._clean("".join(tree.xpath('//div[contains(@class,"detail-desc")]//text()')))

        rows = self._detail_rows(tree)
        tags = self._detail_tags(tree)

        director = self._pick_row(rows, "导演", "導演")
        actor = self._pick_row(rows, "演员", "演員", "主演")
        premiere = self._pick_row(rows, "首映", "上映", "上映时间", "上映時間", "年份", "年代")
        site_remarks = self._pick_row(rows, "备注", "備註", "更新")

        year = ""
        year_match = re.search(r"(?:19|20)\d{2}", premiere)
        if year_match:
            year = year_match.group(0)

        # tags 常見順序：年份 / 地區 / 類型...
        if not year and tags:
            tag_year = re.search(r"(?:19|20)\d{2}", tags[0])
            if tag_year:
                year = tag_year.group(0)

        area = tags[1] if len(tags) >= 2 else self._pick_row(rows, "地区", "地區", "国家", "國家")
        media_type = "/".join(tags[2:]) if len(tags) >= 3 else self._pick_row(rows, "类型", "類型")

        vod = {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": self._picture(picture),
        }

        # TVBox / FongMi 標準 metadata 欄位。
        if year:
            vod["vod_year"] = year
        if area:
            vod["vod_area"] = area
        if media_type:
            vod["vod_type"] = media_type
        if director:
            vod["vod_director"] = director
        if actor:
            vod["vod_actor"] = actor

        # WebHTV 相容補強：即使 App 沒渲染上述獨立欄位，也會在內容區看到。
        metadata_lines = []
        compact = []
        if year:
            compact.append(year)
        if area:
            compact.append(area)
        if media_type:
            compact.append(media_type)
        if compact:
            metadata_lines.append(" · ".join(compact))
        if director:
            metadata_lines.append(f"導演：{director}")
        if actor:
            metadata_lines.append(f"演員：{actor}")

        content_parts = metadata_lines[:]
        if original_desc:
            content_parts.append("")
            content_parts.append(original_desc)
        vod["vod_content"] = "\n".join(content_parts).strip()

        # vod_remarks 通常會直接出現在標題附近，僅放短資訊避免 UI 過長。
        remarks_parts = []
        if year:
            remarks_parts.append(year)
        if area:
            remarks_parts.append(area)
        if media_type:
            remarks_parts.append(media_type)
        if site_remarks:
            remarks_parts.append(site_remarks)
        vod["vod_remarks"] = " · ".join(remarks_parts) or site_remarks

        play_lines = self._play_lines(tree)
        if play_lines:
            vod["vod_play_from"] = "$$$".join(name for name, _ in play_lines)
            vod["vod_play_url"] = "$$$".join("#".join(episodes) for _, episodes in play_lines)

        return {"list": [vod]}

    # ---------- Search ----------
    def searchContent(self, key, quick, pg="1"):
        page = int(pg or 1)
        encoded = quote(str(key))
        html = self._get(f"{self.host}/search?k={encoded}")

        token_match = re.search(r'name=["\']t["\']\s+value=["\']([^"\']+)', html or "")
        if token_match:
            url = f"{self.host}/search?k={encoded}&t={quote(token_match.group(1))}"
            if page > 1:
                url += f"&page={page}"
            html = self._get(url)

        tree = self._tree(html)
        if tree is None:
            return {"list": [], "page": page}

        items = []
        for anchor in tree.xpath('//a[contains(@class,"search-result-item")]'):
            match = re.search(r"/detail/(\d+)\.html", anchor.get("href", ""))
            if not match:
                continue
            name = self._clean("".join(anchor.xpath('.//*[contains(@class,"title")]//text()')))
            if not name:
                continue
            pic = self._first(
                anchor.xpath('.//img[not(contains(@data-original,"logo_placeholder"))]/@data-original')
            )
            items.append(
                {
                    "vod_id": match.group(1),
                    "vod_name": name,
                    "vod_pic": self._picture(pic),
                }
            )
        return {"list": items, "page": page}

    # ---------- Playback ----------
    def _referer_for_media(self, url):
        playlist = re.match(r"(https?://[^/]+/[^?\s]+\.m3u8)", url or "")
        if playlist:
            return playlist.group(1)
        origin = re.match(r"(https?://[^/]+)", url or "")
        return origin.group(1) + "/" if origin else self.host + "/"

    def playerContent(self, flag, id, vipFlags):
        page_url = self._absolute(id)
        html = self._get(page_url)
        media_url = ""

        patterns = [
            r'playSource\s*=\s*\{[^}]*?src:\s*["\']([^"\']+)',
            r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
            r'(https?://[^\s"\'<>]+\.(?:mp4|flv|mkv|webm)[^\s"\'<>]*)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html or "", re.I)
            if match:
                media_url = self._absolute(match.group(1))
                break

        if not media_url:
            return {
                "parse": 1,
                "url": page_url,
                "header": json.dumps(self.headers, ensure_ascii=False),
            }

        headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self._referer_for_media(media_url),
        }
        return {
            "parse": 0,
            "url": media_url,
            "header": json.dumps(headers, ensure_ascii=False),
        }

    def isVideoFormat(self, url):
        value = (url or "").lower()
        return ".m3u8" in value or ".mp4" in value

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def destroy(self):
        return None
