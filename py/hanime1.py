#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Author  : Doubebly 
# @Time    : 2026/3/3
# @file    : py_hanime.min.py

import sys
import urllib.request
import re
import html as html_parser
from urllib.parse import quote
from pyquery import PyQuery as G
from urllib import parse

sys.path.append('..')
from base.spider import Spider as M

class Spider(M):
    def __init__(self):
        super().__init__()
        self.debug = False
        self.name = 'hanime'
        self.error_play_url = 'https://kjjsaas-sh.oss-cn-shanghai.aliyuncs.com/u/3401405881/20240818-936952-fc31b16575e80a7562cdb1f81a39c6b0.mp4'
        self.home_url = 'https://hanime1.me'
        self.proxy = "http://127.0.0.1:2525?single=true&url="  # 如果需要代理可以启用
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36',
            'Referer': f'{self.home_url}/',
        }

    def getName(self):
        return self.name

    def init(self, extend='{}'):
        self.extend = extend

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        # 合并第二个 spider 的完整分类
        classes = [
            {'type_id': '裏番', 'type_name': '裏番'},
            {'type_id': '泡麵番', 'type_name': '泡麵番'},
            {'type_id': 'latest_rank', 'type_name': '最新上市'},
            {'type_id': 'Motion Anime', 'type_name': 'Motion Anime'},
            {'type_id': '3DCG', 'type_name': '3DCG'},
            {'type_id': '2D動畫', 'type_name': '2D動畫'},
            {'type_id': 'AI生成', 'type_name': 'AI生成'},
            {'type_id': 'MMD', 'type_name': 'MMD'},
            {'type_id': 'Cosplay', 'type_name': 'Cosplay'},
            {'type_id': 'daily_rank', 'type_name': '本日排行'},
            {'type_id': 'weekly_rank', 'type_name': '本週排行'},
            {'type_id': 'monthly_rank', 'type_name': '本月排行'}
        ]
        
        # 添加第二个 spider 的筛选选项
        sort_options = [
            {"n": "最新上市", "v": "最新上市"},
            {"n": "最新上傳", "v": "最新上傳"},
            {"n": "本日排行", "v": "本日排行"},
            {"n": "本週排行", "v": "本週排行"},
            {"n": "本月排行", "v": "本月排行"},
            {"n": "觀看次數", "v": "觀看次數"}
        ]
        
        filters = {}
        for item in classes:
            filters[item['type_id']] = [{"key": "sort", "name": "排序", "value": sort_options}]
            
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        # 获取首页内容（最新视频）
        try:
            content = self.get(self.home_url)
            vods = self.parse_vod_list(content)
            return {'list': vods, 'page': 1, 'pagecount': 1}
        except:
            return {'list': [], 'page': 1, 'pagecount': 1}

    def categoryContent(self, cid, page, filter, ext):
        sort = ext.get('sort', '最新上市') if ext else '最新上市'
        
        # 根据分类类型构建不同的URL
        if 'rank' in cid or cid == 'latest_rank':
            rank_map = {'latest_rank': '最新上市', 'daily_rank': '本日排行', 'weekly_rank': '本週排行', 'monthly_rank': '本月排行'}
            url = f"{self.home_url}/search?sort={quote(rank_map.get(cid, '最新上市'))}&page={page}"
        else:
            url = f"{self.home_url}/search?genre={quote(cid)}&sort={quote(sort)}&page={page}"
        
        content = self.get(url)
        if content:
            vods = self.parse_vod_list(content)
            # 尝试获取总页数
            pagecount = page + 1  # 默认值
            pc_match = re.search(r'\/ (\d+)', content)
            if pc_match:
                pagecount = int(pc_match.group(1))
            
            return {'list': vods, 'page': page, 'pagecount': pagecount}
        
        return {'list': [], 'page': page, 'pagecount': 0}

    def parse_vod_list(self, html):
        """统一的视频列表解析函数"""
        vods = []
        seen = set()
        
        # 使用PyQuery解析
        doc = G(html)
        
        # 方法1: 从video-item-container中提取
        for item in doc('div.video-item-container').items():
            link = item('a[href*="watch?v="]')
            if not link:
                continue
                
            href = link.attr('href')
            vid = href.split('watch?v=')[-1] if 'watch?v=' in href else None
            
            if vid and vid not in seen:
                seen.add(vid)
                
                # 提取图片
                img = item('img')
                pic = img.attr('src') or img.attr('data-src') or ''
                
                # 提取时长
                duration = item('div.duration').text()
                
                # 提取标题
                title_elem = item('div.title') or item('div.video-title')
                title = title_elem.text() or link.text()
                
                vods.append({
                    'vod_id': vid,
                    'vod_name': html_parser.unescape(title).strip(),
                    'vod_pic': pic,
                    'vod_remarks': duration.strip()
                })
        
        # 方法2: 如果没有找到，尝试从home-rows-videos-wrapper中提取
        if not vods:
            for item in doc('div.home-rows-videos-wrapper a').items():
                href = item.attr('href')
                if not href or 'watch?v=' not in href:
                    continue
                    
                vid = href.split('watch?v=')[-1]
                if vid in seen:
                    continue
                    
                seen.add(vid)
                
                # 提取图片
                img = item('img')
                pic = img.attr('src') or img.attr('data-src') or ''
                
                # 提取标题
                title = item('div.home-rows-videos-title').text()
                
                vods.append({
                    'vod_id': vid,
                    'vod_name': html_parser.unescape(title).strip(),
                    'vod_pic': pic,
                    'vod_remarks': ''
                })
        
        return vods

    def detailContent(self, did):
        vid = did[0]
        url = f"{self.home_url}/watch?v={vid}"
        
        content = self.get(url)
        if not content:
            return {'list': []}
        
        doc = G(content)
        
        # 提取标题和图片
        title = doc('meta[property="og:title"]').attr('content') or ''
        pic = doc('meta[property="og:image"]').attr('content') or ''
        
        if not title:
            title = doc('h1.video-title').text() or vid
            
        # 提取视频源
        sources = []
        for source in doc('video source').items():
            src = source.attr('src')
            if src:
                size = source.attr('size') or '标清'
                if '1080' in src or size == '1080':
                    tag = "1080P"
                elif '720' in src or size == '720':
                    tag = "720P"
                else:
                    tag = "标清"
                sources.append(f"{tag}${src}")
        
        # 如果没找到video source，尝试直接匹配mp4链接
        if not sources:
            mp4_links = re.findall(r'https?://[^\s"\'<>]+?\.mp4[^\s"\'<>]*', content)
            seen_urls = set()
            for s_url in mp4_links:
                s_url = html_parser.unescape(s_url).replace('&amp;', '&')
                if s_url in seen_urls:
                    continue
                seen_urls.add(s_url)
                
                if '1080' in s_url:
                    tag = "1080P"
                elif '720' in s_url:
                    tag = "720P"
                else:
                    tag = "标清"
                sources.append(f"{tag}${s_url}")
        
        # 排序
        sources.sort(key=lambda x: 0 if "1080P" in x else (1 if "720P" in x else 2))
        
        return {'list': [{
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': pic,
            'vod_year': '',
            'vod_area': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': '',
            'vod_play_from': self.name,
            'vod_play_url': '#'.join(sources)
        }]}

    def searchContent(self, key, quick, page='1'):
        url = f"{self.home_url}/search?query={quote(key)}&page={page}"
        content = self.get(url)
        if content:
            vods = self.parse_vod_list(content)
            return {'list': vods, 'page': int(page)}
        return {'list': [], 'page': int(page)}

    def playerContent(self, flag, pid, vipFlags):
        return {
            'parse': 0,
            'url': pid,
            'header': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36',
                'Referer': f'{self.home_url}/',
                'Connection': 'keep-alive'
            }
        }

    def localProxy(self, params):
        return None

    def destroy(self):
        return '正在Destroy'

    def get(self, url):
        """增强的GET请求方法"""
        try:
            req = urllib.request.Request(url, headers=self.headers, method='GET')
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"Error in get: {e}")
            return None


if __name__ == '__main__':
    pass