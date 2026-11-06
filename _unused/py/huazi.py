# coding=utf-8
import sys
import os
import json
import time
import base64
import random
import hashlib
import hmac
import requests
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA1, SHA256

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def __init__(self):
        self.name = "花子动漫"
        self.base = 'https://www.huazidm.com'
        self.ua = 'okhttp/5.3.2'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.ua
        })
        self.aes_key = None
        self.client_id = None
        self.session_id = None
        self.types = {}
        self._home_cache = None
        self._home_cache_time = 0
        # 不在__init__里握手，延迟到第一次请求时

    def getName(self):
        return self.name

    def init(self, extend=''):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    # ==================== 加密通信 ====================
    def _b64u_encode(self, data):
        return base64.urlsafe_b64encode(data).decode().rstrip('=')

    def _b64u_decode(self, s):
        padding = 4 - len(s) % 4
        if padding != 4:
            s += '=' * padding
        return base64.urlsafe_b64decode(s)

    def _aes_gcm_encrypt(self, key, plaintext):
        iv = os.urandom(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
        return {
            'iv': self._b64u_encode(iv),
            'data': self._b64u_encode(ciphertext),
            'tag': self._b64u_encode(tag)
        }

    def _aes_gcm_decrypt(self, key, data):
        iv = self._b64u_decode(data['iv'])
        ciphertext = self._b64u_decode(data['data'])
        tag = self._b64u_decode(data['tag'])
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()

    def _init_api(self):
        try:
            r = self.session.get(self.base + '/api/public/config', timeout=15)
            config = r.json()['data']
            pub_key = config['public_key']

            self.aes_key = os.urandom(32)
            self.client_id = os.urandom(16).hex()

            rsa_key = RSA.import_key(pub_key)
            cipher_rsa = PKCS1_OAEP.new(rsa_key, hashAlgo=SHA1)
            encrypted_key = base64.b64encode(cipher_rsa.encrypt(self.aes_key)).decode()

            handshake_data = {
                'client_id': self.client_id,
                'encrypted_key': encrypted_key,
                'fingerprint': self.session.headers.get('User-Agent', '')
            }
            r2 = self.session.post(
                self.base + '/api/public/handshake',
                headers={'Content-Type': 'application/json'},
                json=handshake_data,
                timeout=15
            )
            result = r2.json()
            if result.get('code') == 1:
                self.session_id = result['data']['session_id']
            else:
                raise Exception('handshake failed: ' + result.get('msg', ''))
        except Exception as e:
            print(f'_init_api error: {e}')

    def _req(self, path, data=None, retry=True):
        if data is None:
            data = {}
        if not self.aes_key or not self.session_id:
            self._init_api()
            if not self.aes_key or not self.session_id:
                return None
        try:
            payload = self._aes_gcm_encrypt(self.aes_key, json.dumps(data, ensure_ascii=False))
            ts = str(int(time.time()))
            nonce = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=20))
            sign = hmac.new(
                self.aes_key,
                f'{payload["data"]}|{ts}|{nonce}'.encode(),
                SHA256
            ).hexdigest()
            body = {
                'client_id': self.client_id,
                'session_id': self.session_id,
                'ts': ts,
                'nonce': nonce,
                'sign': sign,
                'payload': payload
            }
            headers = {
                'Content-Type': 'application/json',
                'X-Client-Id': self.client_id,
                'X-Session-Id': self.session_id
            }
            r = self.session.post(self.base + path, headers=headers, json=body, timeout=15)
            rd = r.json()
            if rd.get('code') != 1:
                # session失效时重新握手
                if retry and ('失效' in str(rd.get('msg', '')) or '过期' in str(rd.get('msg', '')) or rd.get('code') == 401):
                    self._init_api()
                    return self._req(path, data, retry=False)
                return None
            pd = rd['data']['payload']
            decrypted = self._aes_gcm_decrypt(self.aes_key, pd)
            return json.loads(decrypted)
        except Exception as e:
            print(f'_req {path} error: {e}')
            return None

    # ==================== TVBox 接口 ====================
    def _get_home(self):
        # 缓存home数据5分钟，避免重复请求
        now = time.time()
        if self._home_cache and now - self._home_cache_time < 300:
            return self._home_cache
        data = self._req('/api/site/home')
        if data:
            self._home_cache = data
            self._home_cache_time = now
        return data

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': [], 'parse': 0, 'jx': 0}
        try:
            data = self._get_home()
            if not data:
                return result
            types = data.get('types', [])
            for t in types:
                tid = str(t['type_id'])
                name = t['type_name']
                result['class'].append({'type_id': tid, 'type_name': name})
                self.types[tid] = t
                # 精简筛选 - 只保留排序，减少初始化时间
                result['filters'][tid] = [{
                    'key': 'sort', 'name': '排序', 'value': [
                        {'n': '最新', 'v': 'latest'},
                        {'n': '最热', 'v': 'hits'},
                        {'n': '评分', 'v': 'score'},
                    ]
                }]

            # 首页推荐
            for item in data.get('recommend', []):
                result['list'].append({
                    'vod_id': str(item['id']),
                    'vod_name': item.get('name', ''),
                    'vod_pic': item.get('poster', ''),
                    'vod_remarks': item.get('remark', '')
                })
        except Exception as e:
            print(f'homeContent error: {e}')
        return result

    def homeVideoContent(self):
        videos = []
        try:
            data = self._req('/api/site/home')
            if data:
                for item in data.get('latest', []):
                    videos.append({
                        'vod_id': str(item['id']),
                        'vod_name': item.get('name', ''),
                        'vod_pic': item.get('poster', ''),
                        'vod_remarks': item.get('remark', '')
                    })
        except Exception as e:
            print(f'homeVideoContent error: {e}')
        return {'list': videos, 'parse': 0, 'jx': 0}

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'parse': 0, 'jx': 0}
        page = int(pg) if pg else 1
        try:
            params = {'keyword': '', 'category_id': int(tid), 'page': page, 'limit': 20}
            if extend:
                if extend.get('class'):
                    params['genre'] = extend['class']
                if extend.get('year'):
                    params['year'] = extend['year']
                if extend.get('area'):
                    params['area'] = extend['area']
                if extend.get('sort'):
                    sort_map = {'latest': 'updated_at', 'hits': 'hits', 'score': 'score'}
                    params['sort'] = sort_map.get(extend['sort'], extend['sort'])
            data = self._req('/api/site/search', params)
            if data:
                for item in data.get('list', []):
                    result['list'].append({
                        'vod_id': str(item['id']),
                        'vod_name': item.get('name', ''),
                        'vod_pic': item.get('poster', ''),
                        'vod_remarks': item.get('remark', '')
                    })
                total = int(data.get('total', 0))
                result['page'] = page
                result['pagecount'] = (total + 19) // 20 if total > 0 else page
                result['limit'] = 20
                result['total'] = total
        except Exception as e:
            print(f'categoryContent error: {e}')
        return result

    def detailContent(self, ids):
        result = {'list': [], 'parse': 0, 'jx': 0}
        vid = str(ids[0]) if ids else ''
        if not vid:
            return result
        try:
            data = self._req('/api/site/detail', {'id': int(vid)})
            if not data or 'detail' not in data:
                return result
            detail = data['detail']
            play_sources = detail.get('play_sources', [])
            play_from = []
            play_urls = []
            for src in play_sources:
                src_code = src.get('code', '')
                src_name = src.get('name', '')
                if not src_code or not src_name:
                    continue
                episodes = src.get('episodes', [])
                ep_list = []
                for idx, ep in enumerate(episodes):
                    ep_name = ep.get('name', f'第{idx+1}集')
                    # 用base64编码避免特殊字符问题
                    play_data = f'{vid}|{src_code}|{idx}'
                    play_id = base64.b64encode(play_data.encode()).decode()
                    ep_list.append(f'{ep_name}${play_id}')
                if ep_list:
                    play_from.append(src_name)
                    play_urls.append('#'.join(ep_list))
            vod = {
                'vod_id': vid,
                'vod_name': detail.get('name', ''),
                'vod_pic': detail.get('poster', ''),
                'type_name': detail.get('genre', ''),
                'vod_year': str(detail.get('year', '')),
                'vod_area': detail.get('area', ''),
                'vod_remarks': detail.get('remark', ''),
                'vod_actor': detail.get('actor', ''),
                'vod_director': detail.get('director', ''),
                'vod_content': detail.get('content_text', ''),
                'vod_play_from': '$$$'.join(play_from),
                'vod_play_url': '$$$'.join(play_urls)
            }
            result['list'].append(vod)
        except Exception as e:
            print(f'detailContent error: {e}')
        return result

    def searchContent(self, key, quick, pg='1'):
        result = {'list': [], 'parse': 0, 'jx': 0}
        page = int(pg) if pg else 1
        try:
            data = self._req('/api/site/search', {
                'keyword': key,
                'page': page,
                'limit': 20
            })
            if data:
                for item in data.get('list', []):
                    result['list'].append({
                        'vod_id': str(item['id']),
                        'vod_name': item.get('name', ''),
                        'vod_pic': item.get('poster', ''),
                        'vod_remarks': item.get('remark', '')
                    })
                total = int(data.get('total', 0))
                result['page'] = page
                result['pagecount'] = (total + 19) // 20 if total > 0 else page
                result['limit'] = 20
                result['total'] = total
        except Exception as e:
            print(f'searchContent error: {e}')
        return result

    def playerContent(self, flag, id, vipFlags):
        try:
            # id 是 base64 编码的 vod_id|source_code|episode_index
            try:
                decoded = base64.b64decode(id).decode()
            except:
                decoded = id
            parts = decoded.split('|')
            if len(parts) < 3:
                return {'parse': 0, 'jx': 0, 'url': ''}
            vod_id = int(parts[0])
            source_code = parts[1]
            episode_index = int(parts[2])

            data = self._req('/api/site/play-resolve', {
                'id': vod_id,
                'source': source_code,
                'episode': episode_index
            })
            if data and data.get('play_url'):
                url = data['play_url']
                headers = {'User-Agent': self.ua}
                ua = data.get('user_agent', '')
                if ua:
                    headers['User-Agent'] = ua
                return {
                    'parse': 0,
                    'jx': 0,
                    'url': url,
                    'header': headers,
                    'danmaku': 'http://127.0.0.1:9978/proxy?do=diydanmu'
                }
        except Exception as e:
            print(f'playerContent error: {e}')
        return {'parse': 0, 'jx': 0, 'url': ''}

    def localProxy(self, params):
        return [200, "video/MP2T", {}, ""]