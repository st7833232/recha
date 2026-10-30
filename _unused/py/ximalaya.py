# -*- coding: utf-8 -*-
# @Author: 竹佀
# @Date: 2026-03-28
# @Description: 喜马拉雅音频爬虫

import json
import re
import sys
sys.path.append('../../')
from base.spider import Spider

class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.AUDIO_API_BASE = "https://api-v2.cenguigui.cn/api/music/ximalaya.php"
        self.XIMALAYA_API = "https://www.ximalaya.com/revision"
        self.MOBILE_API = "http://mobile.ximalaya.com/mobile"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
        }

    def getName(self):
        return "喜马拉雅"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter):
        """首页推荐分类"""
        result = {}
        classes = [
            {"type_id": "3", "type_name": "有声书"},
            {"type_id": "15", "type_name": "广播剧"},
            {"type_id": "2", "type_name": "音乐"},
            {"type_id": "5", "type_name": "儿童"},
            {"type_id": "9", "type_name": "人文"},
            {"type_id": "8", "type_name": "娱乐"}
        ]
        result['class'] = classes
        
        # 筛选器配置
        if filter:
            result['filters'] = {
                "3": [{"key": "tag", "name": "标签", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "玄幻", "v": "玄幻"},
                    {"n": "穿越", "v": "穿越"},                 
                    {"n": "重生", "v": "重生"},
                    {"n": "系统流", "v": "系统流"},
                    {"n": "脑洞", "v": "脑洞"},
                    {"n": "穿书", "v": "穿书"},
                    {"n": "虐渣", "v": "虐渣"},
                    {"n": "异能", "v": "异能"},
                    {"n": "网游", "v": "网游"},
                    {"n": "下山", "v": "下山"},
                    {"n": "黑科技", "v": "黑科技"},
                    {"n": "囤物资", "v": "囤物资"},
                    {"n": "机甲", "v": "机甲"},
                    {"n": "美食", "v": "美食"},
                    {"n": "基建", "v": "基建"},
                    {"n": "群穿", "v": "群穿"},
                    {"n": "逃荒", "v": "逃荒"},
                    {"n": "废材流", "v": "废材流"},
                    {"n": "无女主", "v": "无女主"},
                    {"n": "多女主", "v": "多女主"},
                    {"n": "单女主", "v": "单女主"},                    
                    {"n": "仙侠", "v": "仙侠"},
                    {"n": "都市", "v": "都市"},
                    {"n": "历史", "v": "历史"},
                    {"n": "现代言情", "v": "现代言情"},
                    {"n": "古代言情", "v": "古代言情"}
                ]}],
                "15": [{"key": "tag", "name": "标签", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "言情", "v": "言情"},
                    {"n": "纯爱", "v": "纯爱"},
                    {"n": "悬疑", "v": "悬疑"},
                    {"n": "搞笑", "v": "搞笑"}
                ]}],
                "2": [{"key": "tag", "name": "标签", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "华语流行", "v": "华语流行"},
                    {"n": "欧美金曲", "v": "欧美金曲"}
                ]}],
                "5": [{"key": "tag", "name": "标签", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "儿童故事", "v": "儿童故事"},
                    {"n": "儿歌", "v": "儿歌"},
                    {"n": "启蒙教育", "v": "启蒙教育"}
                ]}],
                "9": [{"key": "tag", "name": "标签", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "历史人文", "v": "历史人文"},
                    {"n": "哲学", "v": "哲学"},
                    {"n": "国学", "v": "国学"}
                ]}],
                "8": [{"key": "tag", "name": "标签", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "相声", "v": "相声"},
                    {"n": "脱口秀", "v": "脱口秀"},
                    {"n": "搞笑", "v": "搞笑"}
                ]}]
            }
        
        # 获取热门推荐
        videos = []
        try:
            url = f"{self.XIMALAYA_API}/category/v2/albums"
            params = {"pageNum": 1, "pageSize": 20, "sort": 2, "categoryId": 3}
            response = self.fetch(url, params=params, headers=self.headers)
            if response and response.text:
                data = json.loads(response.text)
                if data.get('data'):
                    albums = data['data'].get('albums', []) or data['data'].get('list', [])
                    for album in albums[:12]:
                        videos.append({
                            "vod_id": str(album.get('albumId') or album.get('id')),
                            "vod_name": album.get('albumTitle') or album.get('title', ''),
                            "vod_pic": self.fixImageUrl(album.get('coverPath') or album.get('cover_path') or album.get('albumCoverPath', '')),
                            "vod_remarks": f"{album.get('playCount', 0)}播放"
                        })
        except Exception as e:
            print(f"[喜马拉雅] 首页获取失败: {e}")
            
        result['list'] = videos
        return result

    def homeVideoContent(self):
        """首页视频内容"""
        result = {'list': []}
        try:
            url = f"{self.XIMALAYA_API}/category/v2/albums"
            params = {"pageNum": 1, "pageSize": 20, "sort": 2, "categoryId": 3}
            response = self.fetch(url, params=params, headers=self.headers)
            if response and response.text:
                data = json.loads(response.text)
                if data.get('data'):
                    albums = data['data'].get('albums', []) or data['data'].get('list', [])
                    for album in albums[:12]:
                        result['list'].append({
                            "vod_id": str(album.get('albumId') or album.get('id')),
                            "vod_name": album.get('albumTitle') or album.get('title', ''),
                            "vod_pic": self.fixImageUrl(album.get('coverPath') or album.get('cover_path') or album.get('albumCoverPath', '')),
                            "vod_remarks": f"{album.get('playCount', 0)}播放"
                        })
        except Exception as e:
            print(f"[喜马拉雅] homeVideoContent失败: {e}")
        return result

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容"""
        result = {}
        videos = []
        try:
            tag = extend.get('tag', '') if extend else ''
            url = f"{self.XIMALAYA_API}/category/v2/albums"
            params = {
                "pageNum": int(pg),
                "pageSize": 20,
                "sort": 2,
                "categoryId": int(tid)
            }
            if tag:
                params['metadataValues'] = tag
                
            response = self.fetch(url, params=params, headers=self.headers)
            if response and response.text:
                data = json.loads(response.text)
                if data.get('data'):
                    albums = data['data'].get('albums', []) or data['data'].get('list', [])
                    total = data['data'].get('total', 0)
                    for album in albums:
                        videos.append({
                            "vod_id": str(album.get('albumId') or album.get('id')),
                            "vod_name": album.get('albumTitle') or album.get('title', ''),
                            "vod_pic": self.fixImageUrl(album.get('coverPath') or album.get('cover_path') or album.get('albumCoverPath', '')),
                            "vod_remarks": f"{album.get('trackCount', album.get('tracksCount', 0))}集"
                        })
                    result['pagecount'] = (total // 20) + (1 if total % 20 > 0 else 0) if total > 0 else 1
                    result['total'] = total
                else:
                    result['pagecount'] = 1
                    result['total'] = len(videos)
            else:
                result['pagecount'] = 1
                result['total'] = 0
        except Exception as e:
            print(f"[喜马拉雅] 分类获取失败: {e}")
            result['pagecount'] = 1
            result['total'] = 0
            
        result['list'] = videos
        result['page'] = pg
        result['limit'] = 20
        return result

    def detailContent(self, ids):
        """详情页"""
        result = {}
        try:
            album_id = ids[0]
            # 获取专辑详情和曲目列表
            url = f"{self.MOBILE_API}/others/ca/album/track/{album_id}/true/1/30"
            response = self.fetch(url, headers=self.headers)
            
            if response and response.text:
                data = json.loads(response.text)
                if data.get('tracks'):
                    tracks = data['tracks'].get('list', [])
                    album_info = data.get('albumInfo', {})
                    
                    # 从第一个 track 中提取专辑信息（如果 albumInfo 为空）
                    first_track = tracks[0] if tracks else {}
                    
                    # 专辑名称：优先使用 albumInfo，否则从 track 中提取
                    album_title = (album_info.get('title') or 
                                  album_info.get('albumTitle') or 
                                  first_track.get('albumTitle') or 
                                  first_track.get('album_title') or 
                                  '未知专辑')
                    
                    # 主播名称：优先使用 albumInfo，否则从 track 中提取
                    anchor_name = (album_info.get('anchorName') or 
                                  album_info.get('nickname') or 
                                  first_track.get('anchorName') or 
                                  first_track.get('nickname') or 
                                  '未知主播')
                    
                    # 封面图：优先使用 albumInfo，否则从 track 中提取
                    artwork = (album_info.get('coverPath') or 
                              album_info.get('cover_path') or 
                              album_info.get('coverLarge') or 
                              first_track.get('albumCoverPath') or 
                              first_track.get('coverPath') or 
                              first_track.get('coverLarge') or 
                              first_track.get('cover') or 
                              '')
                    
                    # 简介
                    intro = (album_info.get('intro') or 
                            album_info.get('albumIntro') or 
                            first_track.get('albumIntro') or 
                            '暂无简介')
                    
                    # 构建播放列表
                    play_urls = []
                    for track in tracks:
                        track_id = track.get('trackId') or track.get('id')
                        title = track.get('title', '')
                        if track_id and title:
                            play_urls.append(f"{title}${track_id}")
                    
                    vod = {
                        "vod_id": album_id,
                        "vod_name": album_title,
                        "vod_pic": self.fixImageUrl(artwork),
                        "vod_actor": anchor_name,
                        "vod_content": self.cleanHtml(intro),
                        "vod_play_from": "喜马拉雅",
                        "vod_play_url": "#".join(play_urls) if play_urls else ""
                    }
                    result['list'] = [vod]
                else:
                    result['list'] = []
            else:
                result['list'] = []
        except Exception as e:
            print(f"[喜马拉雅] 详情获取失败: {e}")
            result['list'] = []
        return result

    def searchContent(self, key, quick, pg=1):
        """搜索内容"""
        result = {}
        videos = []
        try:
            url = f"{self.XIMALAYA_API}/search"
            params = {
                "kw": key,
                "page": pg,
                "spellchecker": "true",
                "condition": "relation",
                "rows": 20,
                "device": "iPhone",
                "core": "album",
                "paidFilter": "false"
            }
            response = self.fetch(url, params=params, headers=self.headers)
            if response and response.text:
                data = json.loads(response.text)
                if data.get('data') and data['data'].get('result') and data['data']['result'].get('response'):
                    albums = data['data']['result']['response'].get('docs', [])
                    for album in albums:
                        # 搜索API返回的集数字段是 tracks，不是 trackCount
                        track_count = album.get('tracks', 0)
                        videos.append({
                            "vod_id": str(album.get('albumId') or album.get('id')),
                            "vod_name": album.get('title') or album.get('albumTitle', ''),
                            "vod_pic": self.fixImageUrl(album.get('coverPath') or album.get('cover_path') or album.get('albumCoverPath', '')),
                            "vod_remarks": f"{track_count}集"
                        })
            result['list'] = videos
            result['page'] = pg
            result['pagecount'] = 9999 if len(videos) >= 20 else pg
        except Exception as e:
            print(f"[喜马拉雅] 搜索失败: {e}")
            result['list'] = []
            result['page'] = pg
            result['pagecount'] = pg
        return result

    def playerContent(self, flag, id, vipFlags):
        """获取播放地址"""
        result = {}
        try:
            # 解析真实ID（处理 $ 分隔符）
            real_id = id
            if '$' in str(id):
                real_id = str(id).split('$')[-1]
            
            url = f"{self.AUDIO_API_BASE}?trackId={real_id}"
            response = self.fetch(url, headers=self.headers)
            
            if response and response.text:
                data = json.loads(response.text)
                if data.get('url'):
                    result = {
                        "parse": 0,
                        "url": data['url'],
                        "header": json.dumps(self.headers)
                    }
                else:
                    result = {"parse": 0, "url": "", "header": "{}"}
            else:
                result = {"parse": 0, "url": "", "header": "{}"}
        except Exception as e:
            print(f"[喜马拉雅] 获取播放地址失败: {e}")
            result = {"parse": 0, "url": "", "header": "{}"}
        return result

    def fixImageUrl(self, url):
        """修复图片URL"""
        if not url:
            return ''
        if url.startswith('http://') or url.startswith('https://'):
            if '!op_type=' in url:
                url = url.split('!op_type=')[0]
            return url
        if url.startswith('//'):
            return f"https:{url}"
        if url.startswith('storages/'):
            return f"https://imagev2.xmcdn.com/{url}"
        if url.startswith('/'):
            return f"https://imagev2.xmcdn.com{url}"
        return f"https://imagev2.xmcdn.com/{url}"

    def cleanHtml(self, text):
        """清理HTML标签"""
        if not text:
            return "暂无简介"
        clean = re.sub('<[^<]+?>', '', text)
        return clean.strip()[:200] + '...' if len(clean) > 200 else clean.strip()

    def localProxy(self, param):
        return {"action": ""}
