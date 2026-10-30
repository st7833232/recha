# -*- coding: utf-8 -*-
# @Author  : 星河
# @Time    : 2026.03.17 18:34
# @file    : symx.py
# 山有木兮 (symx.club) 爬虫 - OK影视/TVBox Python版本

import json
import re
import sys
import time
import hmac
import hashlib
import urllib.parse

sys.path.append('..')

from base.spider import Spider as BaseSpider

class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.name = "山有木兮"
        self.host = "https://film.symx.club"
        # XOR解密密钥(用于解密system/config中的安全参数)
        self.xor_key = "0x1A2B3C4D5E6F7A8B9C"
        # 签名消息前缀
        self.sign_prefix = "symx_"
        # 签名参数（从config解密得到，默认值）
        self.sign_header_name = "X-Sign"
        self.sign_order = "pts"  # 默认顺序: path+timestamp+secret
        self.sign_key = "symx"

    def getName(self):
        return self.name

    def init(self, extend='{}'):
        try:
            ext = json.loads(extend)
            if 'host' in ext:
                self.host = ext['host'].rstrip('/')
        except:
            pass
        # 获取安全配置
        self.fetch_security_config()



    def xor_decode(self, hex_str):
        """XOR解密hex编码的字符串"""
        if not hex_str:
            return ""
        result = []
        for i in range(0, len(hex_str), 2):
            val = int(hex_str[i:i + 2], 16)
            val ^= ord(self.xor_key[(i // 2) % len(self.xor_key)])
            result.append(chr(val))
        return ''.join(result)

    def generate_timestamp(self):
        """生成带校验位的时间戳"""
        ts = str(int(time.time() * 1000))
        prefix = ts[:-1]
        total = sum(int(c) for c in prefix)
        return prefix + str(total % 10)

    def generate_sign(self, api_path, timestamp):
        """生成HMAC-SHA256签名 - 核心算法"""
        try:
            secret = self.sign_prefix + self.sign_key
            parts = {
                'p': api_path,
                't': timestamp,
                's': secret
            }
            # 按sign_order顺序拼接
            raw = ''.join(parts.get(c, '') for c in self.sign_order)
            # 字符替换: 1->i, 0->o, 5->s
            msg = raw.replace('1', 'i').replace('0', 'o').replace('5', 's')
            # HMAC-SHA256
            mac = hmac.new(self.sign_key.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256)
            return mac.hexdigest()
        except:
            return ""

    def get_headers(self):
        """获取基础请求头"""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "application/json, text/plain, */*",
            "X-Platform": "web"
        }

    def get_signed_headers(self, api_path):
        """获取带签名的请求头(用于需要鉴权的API)"""
        headers = self.get_headers()
        ts = self.generate_timestamp()
        headers["X-Timestamp"] = ts
        headers[self.sign_header_name] = self.generate_sign(api_path, ts)
        return headers

    def fetch_security_config(self):
        """从/api/system/config获取并解密安全参数"""
        try:
            import requests
            resp = requests.get(self.host + "/api/system/config", headers=self.get_headers(), timeout=10)
            data = resp.json()
            if 'data' in data:
                cfg = data['data']
                raw_report_id = cfg.get('reportId', '')
                raw_trace_id = cfg.get('traceId', '')
                raw_session = cfg.get('session', '')
                if raw_report_id:
                    self.sign_header_name = self.xor_decode(raw_report_id)
                if raw_trace_id:
                    self.sign_order = self.xor_decode(raw_trace_id)
                if raw_session:
                    self.sign_key = self.xor_decode(raw_session)

            requests.get(self.host + "/api/stats/init", headers= self.get_signed_headers("/stats/init"), timeout=10)
        except Exception as e:
            print(f"[Symx] 获取安全配置失败: {e}")

    def homeContent(self, filter):
        import requests
        result = {
            'class': [],
            'filters': {},
            'list': [],
            'parse': 0,
            'jx': 0
        }

        try:
            # 获取分类
            cat_url = self.host + "/api/category/top"

            # print(self.get_headers())

            cat_resp = requests.get(cat_url, headers=self.get_headers(), timeout=10).json()

            if 'data' in cat_resp:
                for item in cat_resp['data']:
                    result['class'].append({
                        'type_id': str(item['id']),
                        'type_name': item['name']
                    })

            # 获取首页推荐
            film_url = self.host + "/api/film/category"
            film_resp = requests.get(film_url, headers=self.get_headers(), timeout=10).json()

            if 'data' in film_resp:
                count = 0
                for category in film_resp['data']:
                    if count >= 30:
                        break
                    if 'filmList' in category:
                        for film in category['filmList']:
                            if count >= 30:
                                break
                            result['list'].append({
                                'vod_id': str(film['id']),
                                'vod_name': film.get('name', ''),
                                'vod_pic': film.get('cover', ''),
                                'vod_remarks': film.get('doubanScore', '')
                            })
                            count += 1
        except Exception as e:
            print(f"[Symx] homeContent error: {e}")

        return result

    def categoryContent(self, cid, page, filter, ext):
        import requests
        result = {
            'list': [],
            'parse': 0,
            'jx': 0
        }

        try:
            url = f"{self.host}/api/film/category/list?area=&categoryId={cid}&language=&pageNum={page}&pageSize=15&sort=updateTime&year="
            resp = requests.get(url, headers=self.get_headers(), timeout=10).json()

            total = 0
            if 'data' in resp:
                data = resp['data']
                total = data.get('total', 0)
                if 'list' in data:
                    for item in data['list']:
                        result['list'].append({
                            'vod_id': str(item['id']),
                            'vod_name': item.get('name', ''),
                            'vod_pic': item.get('cover', ''),
                            'vod_remarks': item.get('updateStatus', '')
                        })

            page_count = (total + 14) // 15
            result['page'] = page
            result['pagecount'] = page_count
            result['limit'] = 15
            result['total'] = total
        except Exception as e:
            print(f"[Symx] categoryContent error: {e}")

        return result

    def detailContent(self, did):
        import requests
        result = {
            'list': [],
            'parse': 0,
            'jx': 0
        }

        if not did:
            return result

        vod_id = did[0]

        try:
            url = self.host + "/api/film/detail?id=" + urllib.parse.quote(vod_id)
            resp = requests.get(url, headers=self.get_signed_headers("/film/detail"), timeout=10).json()

            if 'data' not in resp:
                return result

            info = resp['data']
            vod_name = info.get('name', '')

            vod = {
                'vod_id': vod_id,
                'vod_name': vod_name,
                'vod_pic': info.get('cover', ''),
                'vod_year': info.get('year', ''),
                'vod_area': info.get('other', ''),
                'vod_actor': info.get('actor', ''),
                'vod_director': info.get('director', ''),
                'vod_content': info.get('blurb', ''),
                'vod_remarks': f"豆瓣: {info.get('doubanScore', '')}" if info.get('doubanScore') else '',
                'vod_play_from': '',
                'vod_play_url': ''
            }

            # 解析播放列表
            play_froms = []
            play_urls = []

            if 'playLineList' in info:
                for line in info['playLineList']:
                    player_name = line.get('playerName', '')
                    play_froms.append(player_name)

                    episodes = []
                    if 'lines' in line:
                        for ep in line['lines']:
                            ep_name = ep.get('name', '')
                            ep_id = str(ep['id'])
                            episodes.append(f"{ep_name}${ep_id}")
                    play_urls.append('#'.join(episodes))

            vod['vod_play_from'] = '$$$'.join(play_froms)
            vod['vod_play_url'] = '$$$'.join(play_urls)

            result['list'].append(vod)
        except Exception as e:
            print(f"[Symx] detailContent error: {e}")

        return result

    def playerContent(self, flag, pid, vipFlags):
        import requests
        result = {
            'parse': 0,
            'jx': 0,
            'url': '',
            'header': self.get_headers()
        }

        try:
            url = self.host + "/api/line/play/parse?lineId=" + urllib.parse.quote(pid)
            resp = requests.get(url, headers=self.get_signed_headers("/line/play/parse"), timeout=10).json()

            play_url = resp.get('data', '')
            if play_url:
                result['url'] = play_url
            else:
                result['parse'] = 1
                result['jx'] = 1
        except Exception as e:
            print(f"[Symx] playerContent error: {e}")
            result['parse'] = 1
            result['jx'] = 1

        return result

    def searchContent(self, key, quick, page='1'):
        import requests
        result = {
            'list': [],
            'parse': 0,
            'jx': 0
        }

        try:
            url = f"{self.host}/api/film/search?keyword={urllib.parse.quote(key)}&pageNum={page}&pageSize=10"
            resp = requests.get(url, headers=self.get_signed_headers("/film/search"), timeout=10).json()

            if 'data' in resp:
                data = resp['data']
                if 'list' in data:
                    for item in data['list']:
                        result['list'].append({
                            'vod_id': str(item['id']),
                            'vod_name': item.get('name', ''),
                            'vod_pic': item.get('cover', ''),
                            'vod_remarks': item.get('updateStatus', ''),
                            'vod_year': item.get('year', '')
                        })
        except Exception as e:
            print(f"[Symx] searchContent error: {e}")

        return result

    def localProxy(self, params):
        return None


if __name__ == '__main__':
    spider = Spider()
    spider.init('{}')
    print(json.dumps(spider.homeContent(True), ensure_ascii=False, indent=2))