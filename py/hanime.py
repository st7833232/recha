# -*- coding: utf-8 -*-
# by @嗷呜 & Perplexity (Updated 2025-12-04 修復解析問題)
import json
import sys
import threading
import requests
import re
import time
import random
import html as html_parser
from urllib.parse import quote, unquote

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):

    def init(self, extend=""):
        self.host = "https://hanime1.me"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'{self.host}/',
            'Origin': self.host,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive'
        }

    def getName(self):
        return "Hanime"

    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4', '.ts'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter):
        classes = [
            {'type_name': '最新上市', 'type_id': 'latest'},
            {'type_name': '裏番', 'type_id': '裏番'},
            {'type_name': '泡麵番', 'type_id': '泡麵番'},
            {'type_name': 'Motion Anime', 'type_id': 'Motion Anime'},
            {'type_name': '3D動畫', 'type_id': '3D動畫'},
            {'type_name': '同人作品', 'type_id': '同人作品'},
            {'type_name': 'MMD', 'type_id': 'MMD'},
            {'type_name': 'Cosplay', 'type_id': 'Cosplay'},
            {'type_name': '本日排行', 'type_id': 'daily_rank'},
            {'type_name': '本週排行', 'type_id': 'weekly_rank'},
            {'type_name': '本月排行', 'type_id': 'monthly_rank'}
        ]
        sort_filters = [
            {"n": "最新上市", "v": "最新上市"},
            {"n": "本日排行", "v": "本日排行"},
            {"n": "本週排行", "v": "本週排行"},
            {"n": "本月排行", "v": "本月排行"},
            {"n": "人氣爆棚", "v": "人氣爆棚"}
        ]
        date_filters = [
            {"n": "全部時間", "v": ""},
            {"n": "24小時", "v": "24"},
            {"n": "2天", "v": "2"},
            {"n": "1週", "v": "7"},
            {"n": "1月", "v": "30"},
            {"n": "3月", "v": "90"}
        ]
        duration_filters = [
            {"n": "全部時長", "v": ""},
            {"n": "1分鐘", "v": "1"},
            {"n": "5分鐘", "v": "5"},
            {"n": "10分鐘", "v": "10"},
            {"n": "20分鐘", "v": "20"},
            {"n": "30分鐘", "v": "30"},
            {"n": "60+分鐘", "v": "60"},
            {"n": "0-10分鐘", "v": "0-10"},
            {"n": "0-20分鐘", "v": "0-20"}
        ]
        filters = {}
        for item in classes:
            filters[item['type_id']] = [
                {"key": "sort", "name": "排序", "value": sort_filters},
                {"key": "date", "name": "時間", "value": date_filters},
                {"key": "duration", "name": "時長", "value": duration_filters}
            ]
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        try:
            url = f"{self.host}/search?sort=最新上市"
            content = self.fetch(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(content)
            return {'list': vods}
        except Exception as e:
            print(f"homeVideoContent error: {e}")
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg)
        sort = extend.get('sort', '')
        date = extend.get('date', '')
        duration = extend.get('duration', '')

        # 參數映射
        valid_dates = {"": "", "24": "24", "2": "2", "7": "7", "30": "30", "90": "90"}
        valid_durations = {"": "", "1": "1", "5": "5", "10": "10", "20": "20", "30": "30", "60": "60", "0-10": "0-10", "0-20": "0-20"}

        date = valid_dates.get(date, "")
        duration = valid_durations.get(duration, "")

        # 構建URL
        if tid == 'latest':
            sort = '最新上市'
            url = f"{self.host}/search?sort={quote(sort)}&page={page}"
        elif tid == 'daily_rank':
            sort = '本日排行'
            url = f"{self.host}/search?sort={quote(sort)}&page={page}"
        elif tid == 'weekly_rank':
            sort = '本週排行'
            url = f"{self.host}/search?sort={quote(sort)}&page={page}"
        elif tid == 'monthly_rank':
            sort = '本月排行'
            url = f"{self.host}/search?sort={quote(sort)}&page={page}"
        else:
            # 普通分類搜索
            url = f"{self.host}/search?query={quote(tid)}&page={page}"
            if sort:
                url += f"&sort={quote(sort)}"
            if date:
                url += f"&date={quote(date)}"
            if duration:
                url += f"&duration={quote(duration)}"

        try:
            print(f"categoryContent url: {url}")
            content = self.fetch(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(content)
            
            # 判斷是否有下一頁
            has_next = '下一頁' in content or '下一頁' in content
            
            return {
                'list': vods,
                'page': page,
                'pagecount': page + 1 if has_next else page,
                'limit': 30,
                'total': 9999
            }
        except Exception as e:
            print(f"categoryContent error: {e}")
            return {'list': [], 'page': page, 'pagecount': page}

    def detailContent(self, ids):
        vid = ids[0]
        url = f"{self.host}/watch?v={vid}"

        try:
            print(f"detailContent url: {url}")
            html = self.fetch(url, headers=self.getheaders()).text

            # 提取標題
            title_match = re.search(r'<meta property="og:title" content="(.*?)"', html)
            title = title_match.group(1) if title_match else vid

            # 提取圖片
            pic_match = re.search(r'<meta property="og:image" content="(.*?)"', html)
            pic = pic_match.group(1) if pic_match else ""

            # 提取描述
            desc_match = re.search(r'<meta property="og:description" content="(.*?)"', html)
            desc = desc_match.group(1) if desc_match else ""

            # 提取標籤
            vod_tag_list = []
            rich_tags = []

            # 從meta關鍵詞提取
            keywords_match = re.search(r'<meta name="keywords" content="(.*?)"', html)
            if keywords_match:
                keywords = keywords_match.group(1).split(',')
                for keyword in keywords[:10]:
                    keyword = keyword.strip()
                    if keyword and len(keyword) < 30:
                        vod_tag_list.append(keyword)
                        target = json.dumps({'id': keyword, 'name': keyword}, ensure_ascii=False)
                        rich_tags.append(f'[a=cr:{target}/]{keyword}[/a]')

            # 從頁面提取視頻源
            play_parts = []
            
            # 方法1: 查找video標籤中的source
            sources = re.findall(r'<source[^>]+src="([^"]+)"', html)
            
            # 方法2: 查找mp4鏈接
            if not sources:
                sources = re.findall(r'src="([^"]+\.mp4[^"]*)"', html)
            
            # 方法3: 查找m3u8鏈接
            if not sources:
                sources = re.findall(r'(https?://[^\'"]+\.m3u8[^\'"]*)', html)
            
            # 方法4: 查找data-src屬性
            if not sources:
                sources = re.findall(r'data-src="([^"]+)"', html)

            if sources:
                # 解碼並清理URL
                decoded_sources = []
                for s in sources:
                    s = html_parser.unescape(s).replace('&amp;', '&')
                    if s.startswith('//'):
                        s = 'https:' + s
                    decoded_sources.append(s)

                # 按質量分組
                quality_map = {}
                for s in decoded_sources:
                    s_lower = s.lower()
                    if '4k' in s_lower or '2160' in s_lower:
                        quality_map.setdefault('4K', []).append(s)
                    elif '2k' in s_lower or '1440' in s_lower:
                        quality_map.setdefault('2K', []).append(s)
                    elif '1080' in s_lower:
                        quality_map.setdefault('1080p', []).append(s)
                    elif '720' in s_lower:
                        quality_map.setdefault('720p', []).append(s)
                    elif '480' in s_lower:
                        quality_map.setdefault('480p', []).append(s)
                    else:
                        quality_map.setdefault('標清', []).append(s)

                # 按質量順序添加播放鏈接
                quality_order = ['4K', '2K', '1080p', '720p', '480p', '標清']
                for q in quality_order:
                    if q in quality_map and quality_map[q]:
                        best_url = quality_map[q][0]
                        play_url_with_dm = f"{vid}_dm_{best_url}"
                        play_parts.append(f"{q}${play_url_with_dm}")

            # 如果沒有找到視頻源，使用頁面URL作為備用
            if not play_parts:
                play_parts.append(f"網頁播放${url}")

            # 構建播放字符串
            line_name = "Hanime1"
            vod_play_url = f"{line_name}$" + "#".join(play_parts)

            # 構建vod_content
            vod_tag_str = ",".join(vod_tag_list)
            vod_content = f"{desc}\n\n🏷️ 標籤: {' '.join(rich_tags)}" if rich_tags else desc

            vod = {
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": vod_content,
                "vod_tag": vod_tag_str,
                "vod_play_from": line_name,
                "vod_play_url": vod_play_url
            }
            return {'list': [vod]}
            
        except Exception as e:
            print(f"detailContent error: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg="1", extend=None):
        page = int(pg)
        
        # 構建搜索URL
        url = f"{self.host}/search?query={quote(key)}&page={page}"
        
        if extend:
            sort = extend.get("sort", "")
            if sort:
                url += f"&sort={quote(sort)}"
            date = extend.get("date", "")
            if date:
                url += f"&date={quote(date)}"
            duration = extend.get("duration", "")
            if duration:
                url += f"&duration={quote(duration)}"

        try:
            print(f"searchContent url: {url}")
            html = self.fetch(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(html)
            return {'list': vods, 'page': page}
        except Exception as e:
            print(f"searchContent error: {e}")
            return {'list': [], 'page': page}

    def playerContent(self, flag, id, vipFlags):
        header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://hanime1.me/',
            'Origin': 'https://hanime1.me'
        }
        
        if '_dm_' in id:
            vid, url = id.split('_dm_', 1)
            threading.Thread(target=self._preload_danmaku, args=(vid, url)).start()
        else:
            url = id

        # 處理相對路徑
        if url.startswith('//'):
            url = 'https:' + url
        elif url.startswith('/'):
            url = self.host + url

        if '.mp4' in url or '.m3u8' in url:
            return {'parse': 0, 'url': url, 'header': header}
        return {'parse': 1, 'url': url, 'header': header}

    def parse_vod_list(self, html):
        vods = []
        seen = set()
        
        try:
            # 方法1: 查找視頻卡片
            # 使用更靈活的匹配方式
            card_pattern = r'<div[^>]*class="[^"]*col-xs-[^"]*"[^>]*>.*?<a[^>]*href="([^"]+watch\?v=(\d+))"[^>]*>.*?<img[^>]*src="([^"]+)".*?<div[^>]*class="[^"]*card-mobile-title[^"]*"[^>]*>(.*?)</div>.*?<div[^>]*class="[^"]*duration[^"]*"[^>]*>(.*?)</div>'
            
            matches = re.findall(card_pattern, html, re.S | re.I)
            
            for match in matches:
                try:
                    if len(match) >= 5:
                        url, vid, pic, title, duration = match[0], match[1], match[2], match[3], match[4]
                    else:
                        continue
                        
                    if vid in seen:
                        continue
                    seen.add(vid)
                    
                    # 清理標題
                    title = re.sub(r'<[^>]+>', '', title).strip()
                    title = html_parser.unescape(title)
                    
                    # 清理圖片URL
                    pic = pic.strip()
                    if pic.startswith('//'):
                        pic = 'https:' + pic
                    
                    # 清理時長
                    duration = re.sub(r'<[^>]+>', '', duration).strip()
                    
                    vods.append({
                        "vod_id": vid,
                        "vod_name": title[:100],  # 限制標題長度
                        "vod_pic": pic,
                        "vod_remarks": duration
                    })
                except Exception as e:
                    print(f"parse_vod_list item error: {e}")
                    continue
            
            # 方法2: 如果方法1沒找到，使用更簡單的匹配
            if not vods:
                # 查找所有watch鏈接
                watch_links = re.findall(r'<a[^>]*href="([^"]*watch\?v=(\d+))"[^>]*>', html)
                for link, vid in watch_links:
                    if vid in seen:
                        continue
                    seen.add(vid)
                    
                    # 查找對應的圖片
                    pic = ""
                    img_pattern = f'<img[^>]*src="([^"]+)"[^>]*>.*?{vid}'
                    img_match = re.search(img_pattern, html, re.S)
                    if img_match:
                        pic = img_match.group(1)
                        if pic.startswith('//'):
                            pic = 'https:' + pic
                    
                    # 查找標題
                    title = f"視頻 {vid}"
                    title_pattern = f'<div[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</div>.*?{vid}'
                    title_match = re.search(title_pattern, html, re.S)
                    if title_match:
                        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                    
                    vods.append({
                        "vod_id": vid,
                        "vod_name": html_parser.unescape(title[:100]),
                        "vod_pic": pic,
                        "vod_remarks": ""
                    })
            
        except Exception as e:
            print(f"parse_vod_list error: {e}")
        
        return vods[:50]  # 限制返回數量

    def localProxy(self, param):
        try:
            xtype = param.get('type', '')
            if xtype == 'hlxdm':
                vid = param.get('path', '')
                times = int(param.get('times', 0))
                comments = self._fetch_comments(vid)
                return self._generate_danmaku_xml(comments, times)
            return [404, 'text/plain', b'']
        except Exception as e:
            print(f"localProxy error: {e}")
            return [500, 'text/plain', b'']

    def _fetch_comments(self, vid):
        comments = []
        try:
            url = f"{self.host}/loadComment?id={vid}&type=video&content=comment-tablink"
            res = requests.get(url, headers=self.getheaders(), timeout=5)
            data = res.json()
            comments_html = data.get('comments', '')
            if not comments_html:
                return ["歡迎觀看", "Hanime1"]

            comment_blocks = re.findall(
                r'<div[^>]*class="comment-index-text"[^>]*>(.*?)</div>',
                comments_html, re.S
            )
            for block in comment_blocks:
                text = re.sub(r'<[^>]+>', '', block).strip()
                if len(text) > 2 and len(text) < 100 and not any(x in text for x in ['加載中', '查看', '回覆', '登錄', '發表']):
                    comments.append(text)
            
            # 去重並限制數量
            seen = set()
            clean_comments = []
            for c in comments:
                if c not in seen and len(clean_comments) < 60:
                    seen.add(c)
                    clean_comments.append(c)
            return clean_comments if clean_comments else ["歡迎觀看", "精彩內容"]
        except Exception as e:
            print(f"_fetch_comments error: {e}")
            return ["歡迎觀看", "Hanime1"]

    def _generate_danmaku_xml(self, comments, duration):
        if duration <= 0:
            duration = 600
        xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<i>']
        xml.append('<d p="0,5,25,16711680,0">彈幕加載成功</d>')
        if not comments:
            xml.extend([
                '<d p="5,1,25,16777215,0">暫無評論，歡迎補充~</d>',
                '<d p="15,1,25,16777215,0">Hanime1 高清無碼</d>'
            ])
        else:
            for i, c in enumerate(comments):
                progress = i / len(comments)
                base_time = progress * duration
                t = round(max(1, min(base_time + random.uniform(-5, 5), duration - 1)), 1)
                color = 16777215
                if random.random() < 0.15:
                    color = random.randint(0x666666, 0xFFFFFF)
                safe_text = html_parser.escape(c)
                xml.append(f'<d p="{t},1,25,{color},0">{safe_text}</d>')
        xml.append('</i>')
        return [200, 'text/xml', '\n'.join(xml).encode('utf-8')]

    def _preload_danmaku(self, vid, url):
        try:
            time.sleep(1)
            dm_url = f"{self.getProxyUrl()}&path={vid}&times=600&type=hlxdm"
            requests.get(f"http://127.0.0.1:9978/action?do=refresh&type=danmaku&path={quote(dm_url)}", timeout=2)
        except:
            pass

    def getheaders(self, param=None):
        return self.headers.copy()