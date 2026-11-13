# -*- coding: utf-8 -*-
"""黃果短劇（huangguoai.com）— TVBox / FongMi Python Spider.

Uses publicly available browse/search/detail/play endpoints, not login bypass.
Source API is subject to change. Only publicly accessible episodes are returned.
"""
import sys
import re
from urllib.parse import urlencode, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    sys.path.append('..')
    from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    SITE = 'https://huangguoai.com'
    CATEGORIES = (
        ('AI 成人短劇', 'ai-duanju'),
        ('AI 成人漫劇', 'ai-manju'),
        ('AI 換臉', 'ai-huanlian'),
        ('AI 魔改', 'ai-mogai'),
    )

    def getName(self):
        return '黃果短劇（Python）'

    def init(self, extend=''):
        self.headers = {
            'User-Agent': ('Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36'),
            'Accept': 'application/json',
            'Referer': self.SITE + '/',
        }
        self.s = requests.Session()
        retry = Retry(total=2, backoff_factor=0.4, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=frozenset(['GET', 'POST']))
        self.s.mount('https://', HTTPAdapter(max_retries=retry))
        self.s.mount('http://', HTTPAdapter(max_retries=retry))

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|m4v)(?:\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def _get_json(self, path):
        """Try site's API edge route; fallback to direct public GET.

        No authentication, member-unlocking, or DRM bypass is attempted.
        """
        if not path.startswith('/api/') or '://' in path or path.startswith('//'):
            return {}
        envelope = {'method': 'GET', 'path': path, 'body': '', 'content_type': ''}
        for via_edge in (True, False):
            try:
                if via_edge:
                    response = self.s.post(
                        self.SITE + '/api/edge/request', json=envelope,
                        headers=self.headers, timeout=15)
                else:
                    response = self.s.get(self.SITE + path, headers=self.headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                if data.get('status') == 1:
                    return data.get('data') or {}
                if data.get('status') == 0:
                    # An application-level rejection shouldn't be retried via a different route.
                    return {}
            except (requests.RequestException, ValueError, TypeError, AttributeError):
                continue
        return {}

    def _list_result(self, data):
        if not isinstance(data, dict):
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 20, 'total': 0}
        p = data.get('pagination') or {}
        return {
            'list': [self._video_item(item) for item in data.get('items', []) if isinstance(item, dict) and item.get('id')],
            'page': int(p.get('page') or 1),
            'pagecount': int(p.get('pages') or 1),
            'limit': int(p.get('size') or 20),
            'total': int(p.get('total') or 0),
        }

    def _video_item(self, item):
        num = item.get('episode_count') or 0
        is_finished = bool(item.get('is_finished'))
        remark = f'{num} 集' if num else ''
        if is_finished:
            remark = '完結' + (f' · {remark}' if remark else '')
        return {
            'vod_id': str(item['id']),
            'vod_name': item.get('title') or '未命名',
            # NOTE: some upstream images are AES-CBC encrypted; stock TVBox won't display them.
            'vod_pic': self._cover_url(item.get('cover') or ''),
            'vod_remarks': remark,
            'vod_content': item.get('description') or '',
            'style': {'type': 'rect', 'ratio': 0.68},
        }

    @staticmethod
    def _img_crypto_available():
        try:
            from Crypto.Cipher import AES  # noqa: F401
            return True
        except ImportError:
            try:
                from cryptography.hazmat.primitives.ciphers import Cipher  # noqa: F401
                return True
            except ImportError:
                return False

    def _cover_url(self, raw):
        """Use TVBox local proxy to decode encrypted CDN covers when supported."""
        if not raw or not isinstance(raw, str):
            return ''
        if not self._img_crypto_available():
            return raw
        try:
            proxy = self.getProxyUrl() if hasattr(self, 'getProxyUrl') else ''
            if proxy:
                sep = '&' if '?' in proxy else '?'
                return proxy + sep + urlencode({'hg_action': 'image', 'hg_img': raw})
        except Exception:
            pass
        return raw

    @staticmethod
    def _decode_image(content):
        """Decrypt publicly served picture bytes, or return an ordinary JPEG/PNG unchanged."""
        if content[:3] == b'\xff\xd8\xff' or content[:8] == b'\x89PNG\r\n\x1a\n' or content[:4] in (b'RIFF', b'GIF8'):
            return content
        if not content or len(content) % 16:
            return b''
        key, iv = b'f5d965df75336270', b'97b60394abc2fbe1'
        try:
            try:
                from Crypto.Cipher import AES
                data = AES.new(key, AES.MODE_CBC, iv).decrypt(content)
            except ImportError:
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
                data = dec.update(content) + dec.finalize()
            pad = data[-1]
            if 1 <= pad <= 16 and data[-pad:] == bytes([pad]) * pad:
                data = data[:-pad]
            return data if (data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG') or data.startswith(b'GIF8') or data.startswith(b'RIFF')) else b''
        except Exception:
            return b''

    def homeContent(self, filter=False):
        return {'class': [{'type_name': name, 'type_id': cate}
                          for name, cate in self.CATEGORIES]}

    def homeVideoContent(self):
        return self._list_result(self._get_json('/api/videos?page=1&size=20'))

    def categoryContent(self, tid, pg, filter=False, extend=None):
        allowed = {cate for _, cate in self.CATEGORIES}
        if tid not in allowed:
            return self._list_result({})
        page = max(1, int(pg or 1))
        path = '/api/videos/category/%s?%s' % (tid, urlencode({'page': page, 'size': 20}))
        return self._list_result(self._get_json(path))

    def detailContent(self, array):
        if not array:
            return {'list': []}
        vid = str(array[0]).strip()
        if not vid.isdecimal():
            return {'list': []}
        item = self._get_json('/api/videos/' + vid)
        if not item or not isinstance(item, dict):
            return {'list': []}
        episodes = item.get('episodes') or []
        episode_numbers = []
        for entry in episodes:
            if isinstance(entry, dict):
                ep = entry.get('ep_num')
                if ep is not None and str(ep).isdigit():
                    # Skip episodes explicitly marked unavailable.
                    if str(entry.get('status', '')).lower() in ('unavailable', 'locked', 'disabled'):
                        continue
                    episode_numbers.append(int(ep))
        if not episode_numbers:
            # Detail may have episode_count but omit a standalone episodes list.
            count = min(max(int(item.get('episode_count') or 0), 0), 300)
            episode_numbers = list(range(1, count + 1))
        if not episode_numbers and item.get('video_url'):
            episode_numbers = [1]
        ep_list = []
        for ep in sorted(set(episode_numbers)):
            ep_list.append('第%d集$%s:%d' % (ep, vid, ep))
        v = self._video_item(item)
        v.update({
            'type_name': '短劇',
            'vod_year': str(item.get('created_at') or '')[:4],
            'vod_actor': (item.get('author') or {}).get('name', '') if isinstance(item.get('author'), dict) else '',
            'vod_tag': ','.join(item.get('tags') or []),
            'vod_play_from': '黃果HLS',
            'vod_play_url': '#'.join(ep_list),
        })
        return {'list': [v]}

    def searchContent(self, key, quick=False, pg='1'):
        if not str(key).strip():
            return self._list_result({})
        page = max(1, int(pg or 1))
        path = '/api/search?' + urlencode({'q': str(key).strip(), 'page': page, 'size': 20})
        return self._list_result(self._get_json(path))

    def playerContent(self, flag, pid, vipFlags=None):
        if not re.fullmatch(r'\d+:\d+', str(pid or '')):
            return {'parse': 0, 'jx': 0, 'url': ''}
        vid, ep = str(pid).split(':', 1)
        data = self._get_json('/api/videos/%s/play?%s' % (
            vid, urlencode({'ep': ep, 'page_texts': 0})))
        url = data.get('video_url') if isinstance(data, dict) else None
        if not isinstance(url, str) or not url.startswith('https://'):
            return {'parse': 0, 'jx': 0, 'url': ''}
        return {
            'parse': 0, 'jx': 0, 'url': url,
            'header': {'User-Agent': self.headers['User-Agent'], 'Referer': self.SITE + '/'},
        }

    def proxy(self, params):
        return self.localProxy(params)

    def localProxy(self, params):
        params = params or {}
        if params.get('hg_action') != 'image':
            return [404, 'text/plain', b'not found']
        url = str(params.get('hg_img') or '')
        parsed = urlparse(url)
        allowed = {'pic.drleao.cn', 'new2.drleao.cn', 'new.drleao.cn', 'image.drleao.cn'}
        if parsed.scheme != 'https' or parsed.hostname not in allowed:
            return [400, 'text/plain', b'invalid image host']
        try:
            response = self.s.get(url, headers={'User-Agent': self.headers['User-Agent'],
                                                'Referer': self.SITE + '/'}, timeout=15)
            response.raise_for_status()
            data = self._decode_image(response.content)
            if not data:
                return [502, 'text/plain', b'image decode failed']
            mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/gif' if data.startswith(b'GIF8') else 'image/webp' if data.startswith(b'RIFF') else 'image/jpeg'
            return [200, mime, data]
        except requests.RequestException:
            return [502, 'text/plain', b'upstream image unavailable']

    def destroy(self):
        if hasattr(self, 's'):
            self.s.close()
        return 'ok'
