# coding=utf-8
import sys
import os
import re
import json
import urllib.parse
from base.spider import Spider
from bs4 import BeautifulSoup

class Spider(Spider):
    """西瓜卡通 - https://www.xgcartoon.com/"""
    def __init__(self):
        super(Spider, self).__init__()
        self.host = "https://www.xgcartoon.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': self.host,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        # 只保留首页实际显示的大分类
        self.type_map = {
            '%2a': '全部',
            'chuanyue': '穿越',
            'kehuan': '科幻',
            'rexue': '热血',
            'dianjing': '电竞',
            'zhanzheng': '战争',
            'dongzuo': '动作',
            'jingsong': '惊悚',
            'zainan': '灾难',
            'yiliao': '医疗',
        }

    def getName(self):
        return "西瓜卡通"

    def init(self, extend=""):
        pass

    def getDependence(self):
        return ["bs4"]

    def header(self):
        return self.headers

    def build_full_url(self, url):
        if not url or not isinstance(url, str):
            return ''
        url = url.strip().replace('&amp;', '&')
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.host + url
        return self.host + '/' + url

    # ==================== 首页功能 ====================
    def homeContent(self, filter):
        result = {}
        classes = []
        for type_id, type_name in self.type_map.items():
            classes.append({"type_id": type_id, "type_name": type_name})
        result["class"] = classes
        result["filters"] = {}
        res = self.categoryContent("%2a", "1", None, None)
        result["list"] = res.get("list", [])
        return result

    def homeVideoContent(self):
        return self.homeContent(False)

    # ==================== 分类页功能 ====================
    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        try:
            if tid == '%2a' or not tid:
                url = f"{self.host}/classify?region=%2A&state=%2A&filter=%2A&page={pg}"
            else:
                url = f"{self.host}/classify?type={tid}&region=%2A&state=%2A&filter=%2A&page={pg}"

            rsp = self.fetch(url, headers=self.header())
            if not rsp or rsp.status_code != 200:
                return {"list": [], "pagecount": 1, "page": pg, "limit": 0, "total": 0}

            html = rsp.text.replace('&amp;', '&')
            videos = []

            pattern = r'<div class="topic-list-box"[^>]*>.*?<a\s+href="([^"]+)"[^>]*>.*?<amp-img\s+src="([^"]+)"[^>]*>.*?<div class="h3[^"]*"[^>]*>\s*([^<]+)\s*</div>.*?</div>'
            matches = re.findall(pattern, html, re.S)

            if not matches:
                pattern = r'<a\s+href="(/detail/[^"]+)"[^>]*>.*?<amp-img\s+src="([^"]+)"[^>]*>.*?<div class="h3[^"]*"[^>]*>\s*([^<]+)\s*</div>'
                matches = re.findall(pattern, html, re.S)

            for item in matches:
                url_path, pic, name = item
                name = name.strip()

                if '{{' in name or '{{' in url_path or '{{' in pic:
                    continue
                if not name or name in ['name', 'author', '']:
                    continue

                vod_id = url_path.split('/')[-1].split('?')[0].replace('.html', '')
                pic = self.build_full_url(pic)

                videos.append({
                    "vod_id": vod_id,
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": ""
                })

            result["list"] = videos
            result["pagecount"] = 99
            result["page"] = pg
            result["limit"] = len(videos)
            result["total"] = 1980
        except Exception as e:
            print(f"categoryContent error: {e}")
            result = {"list": [], "pagecount": 1, "page": pg, "limit": 0, "total": 0}
        return result

    # ==================== 详情页功能 ====================
    def detailContent(self, ids):
        result = {}
        try:
            vid = ids[0] if isinstance(ids, list) else ids
            url = f"{self.host}/detail/{vid}"
            rsp = self.fetch(url, headers=self.header())
            if not rsp or rsp.status_code != 200:
                return {"list": []}

            html = rsp.text.replace('&amp;', '&')
            soup = BeautifulSoup(html, 'html.parser')

            vod = {
                "vod_id": vid,
                "vod_name": "",
                "vod_pic": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": "",
                "vod_area": "",
                "vod_year": "",
                "vod_remarks": "",
                "vod_play_from": "西瓜专线",
                "vod_play_url": ""
            }

            title_tag = soup.find('h1') or soup.find(class_='detail-right__title')
            if title_tag:
                vod["vod_name"] = title_tag.text.strip()

            pic_tag = soup.select_one('.detail-sider amp-img') or soup.find('amp-img')
            if pic_tag:
                vod["vod_pic"] = self.build_full_url(pic_tag.get('src', ''))

            desc_tag = soup.select_one('.detail-right__desc p')
            if desc_tag:
                vod["vod_content"] = desc_tag.text.strip()

            tags = []
            for tag in soup.select('.detail-right__tags .tag'):
                tags.append(tag.text.strip())
            if tags:
                vod["vod_remarks"] = ' '.join(tags)

            episodes = []
            seen_chapters = set()

            ep_links = soup.select('a.goto-chapter.chapter-box, a.chapter-box')
            if not ep_links:
                ep_links = soup.find_all('a', href=re.compile(r'(/user/page_direct\?|/video/)'))

            for ep in ep_links:
                ep_name = ep.text.strip().replace('\n', ' ').replace('\t', ' ')
                href = ep.get('href', '')

                if not ep_name or not href:
                    continue

                skip_keywords = ['下一集', '上一集', '播放', '全部', '分类', '更多', '展开', '收起']
                if any(kw in ep_name for kw in skip_keywords):
                    continue

                if '/user/page_direct' in href:
                    match = re.search(r'cartoon_id=([^&]+)&chapter_id=([^&]+)', href)
                    if match:
                        cartoon_id = match.group(1)
                        chapter_id = match.group(2)
                        if chapter_id in seen_chapters:
                            continue
                        seen_chapters.add(chapter_id)
                        play_url = f"/video/{cartoon_id}/{chapter_id}.html"
                        episodes.append({"name": ep_name, "url": play_url, "sort": self._extract_episode_num(ep_name)})
                elif '/video/' in href:
                    chapter_id = href.split('/')[-1].replace('.html', '')
                    if chapter_id in seen_chapters:
                        continue
                    seen_chapters.add(chapter_id)
                    episodes.append({"name": ep_name, "url": href, "sort": self._extract_episode_num(ep_name)})

            episodes.sort(key=lambda x: x["sort"])

            ep_list = []
            for ep in episodes:
                ep_list.append(f"{ep['name']}${ep['url']}")

            if not ep_list:
                ep_list.append(f"正片$/video/{vid}/1.html")

            vod["vod_play_url"] = "#".join(ep_list)
            result["list"] = [vod]
        except Exception as e:
            print(f"detailContent error: {e}")
            import traceback
            traceback.print_exc()
            result["list"] = []
        return result

    def _extract_episode_num(self, name):
        match = re.search(r'第?\s*(\d+)\s*集', name)
        if match:
            return int(match.group(1))
        match = re.search(r'(\d+)', name)
        if match:
            return int(match.group(1))
        return 0

    # ==================== 搜索功能 ====================
    def searchContent(self, key, quick, pg=1):
        result = {}
        try:
            url = f"{self.host}/search?keyword={urllib.parse.quote(key)}&page={pg}"
            rsp = self.fetch(url, headers=self.header())
            if not rsp or rsp.status_code != 200:
                return {"list": []}

            html = rsp.text.replace('&amp;', '&')
            videos = []

            pattern = r'<div class="topic-list-box"[^>]*>.*?<a\s+href="([^"]+)"[^>]*>.*?<amp-img\s+src="([^"]+)"[^>]*>.*?<div class="h3[^"]*"[^>]*>\s*([^<]+)\s*</div>.*?</div>'
            matches = re.findall(pattern, html, re.S)

            if not matches:
                pattern = r'<a\s+href="(/detail/[^"]+)"[^>]*>.*?<amp-img\s+src="([^"]+)"[^>]*>.*?<div class="h3[^"]*"[^>]*>\s*([^<]+)\s*</div>'
                matches = re.findall(pattern, html, re.S)

            for item in matches:
                url_path, pic, name = item
                name = name.strip()

                if '{{' in name or '{{' in url_path or '{{' in pic:
                    continue
                if not name or name in ['name', 'author', '']:
                    continue

                vod_id = url_path.split('/')[-1].split('?')[0].replace('.html', '')
                videos.append({
                    "vod_id": vod_id,
                    "vod_name": name,
                    "vod_pic": self.build_full_url(pic),
                    "vod_remarks": "搜索结果"
                })
            result["list"] = videos
        except Exception as e:
            print(f"searchContent error: {e}")
            result["list"] = []
        return result

    # ==================== 播放功能 ====================
    def playerContent(self, flag, ids, ext):
        result = {"parse": 0, "playUrl": "", "url": "", "header": json.dumps(self.header())}
        try:
            play_url = self.build_full_url(ids)
            print(f"【播放请求】flag={flag}, ids={ids}, play_url={play_url}")

            rsp = self.fetch(play_url, headers=self.header())
            if not rsp or rsp.status_code != 200:
                print(f"【播放页请求失败】status={rsp.status_code if rsp else 'None'}")
                result["parse"] = 1
                result["url"] = play_url
                return result

            html = rsp.text

            iframe_match = re.search(r'<iframe[^>]+src="[^"]*vid=([0-9a-fA-F-]{36})"', html)
            if iframe_match:
                video_uuid = iframe_match.group(1)
                target_m3u8 = f"https://xgct-video.bzcdn.net/{video_uuid}/playlist.m3u8"
                result["parse"] = 0
                result["url"] = target_m3u8
                print(f"【iframe提取成功】UUID={video_uuid}, M3U8={target_m3u8}")
                return result

            uuid_match = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', html)
            if uuid_match:
                video_uuid = uuid_match.group(1)
                target_m3u8 = f"https://xgct-video.bzcdn.net/{video_uuid}/playlist.m3u8"
                result["parse"] = 0
                result["url"] = target_m3u8
                print(f"【UUID提取成功】UUID={video_uuid}, M3U8={target_m3u8}")
                return result

            m3u8_match = re.search(r'(https?://[^"\'\s]+\.m3u8[^"\'\s]*)', html)
            if m3u8_match:
                video_url = m3u8_match.group(1).replace('\\/', '/')
                result["parse"] = 0
                result["url"] = video_url
                print(f"【M3U8直链提取成功】{video_url}")
                return result

            player_match = re.search(r'(https?://[^"\'\s]*player[^"\'\s]*\.htm[^"\'\s]*)', html)
            if player_match:
                player_url = player_match.group(1).replace('\\/', '/').replace('&amp;', '&')
                print(f"【发现player.htm】{player_url}")
                player_rsp = self.fetch(player_url, headers=self.header())
                if player_rsp and player_rsp.status_code == 200:
                    player_html = player_rsp.text
                    uuid_match = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', player_html)
                    if uuid_match:
                        video_uuid = uuid_match.group(1)
                        target_m3u8 = f"https://xgct-video.bzcdn.net/{video_uuid}/playlist.m3u8"
                        result["parse"] = 0
                        result["url"] = target_m3u8
                        print(f"【player.htm提取成功】UUID={video_uuid}")
                        return result

            print(f"【所有提取方式失败，使用嗅探】play_url={play_url}")
            result["parse"] = 1
            result["url"] = play_url

        except Exception as e:
            print(f"playerContent error: {e}")
            import traceback
            traceback.print_exc()
            result["parse"] = 1
            result["url"] = self.build_full_url(ids)
        return result

    def isVideoFormat(self, url):
        if not url:
            return False
        return any(ext in url.lower() for ext in ['.mp4', '.m3u8', '.flv', '.mkv'])

    def manualVideoCheck(self):
        pass

    def localProxy(self, param):
        return None

    def destroy(self):
        pass
