# -*- coding: utf-8 -*-
"""黃果短劇 / TVBox Python spider (2026-11 hotfix).

Public catalog and freely reachable HLS only. No account or DRM bypass.
Fixes encrypted CDN thumbnails and offers a local HLS proxy for players whose
network/header handling cannot fetch upstream playlist, segments, and keys.
"""
import re
import sys
import threading
from urllib.parse import urlencode, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    sys.path.append('..')
    from base.spider import Spider as BaseSpider


# Pure Python AES-128-CBC fallback for Chaquopy installs without Crypto.
# Encryption keys below are for publicly served thumbnails, NOT HLS DRM keys.
_IMG_KEY = b'f5d965df75336270'
_IMG_IV = b'97b60394abc2fbe1'


def _gf_mul(a, b):
    out = 0
    for _ in range(8):
        if b & 1:
            out ^= a
        a = ((a << 1) ^ (0x1b if a & 128 else 0)) & 255
        b >>= 1
    return out


def _make_sboxes():
    sb = []
    for v in range(256):
        inverse = next((w for w in range(1, 256) if _gf_mul(v, w) == 1), 0) if v else 0
        t = inverse
        t ^= ((inverse << 1) | (inverse >> 7)) & 255
        t ^= ((inverse << 2) | (inverse >> 6)) & 255
        t ^= ((inverse << 3) | (inverse >> 5)) & 255
        t ^= ((inverse << 4) | (inverse >> 4)) & 255
        sb.append(t ^ 0x63)
    inv = [0] * 256
    for i, x in enumerate(sb):
        inv[x] = i
    return tuple(sb), tuple(inv)


_SBOX, _INVSBOX = _make_sboxes()
_MUL = {k: bytes(_gf_mul(x, k) for x in range(256)) for k in (9, 11, 13, 14)}


def _expand_key(key):
    words = list(key)
    rcon = 1
    while len(words) < 176:
        t = words[-4:]
        if len(words) % 16 == 0:
            t = [_SBOX[t[1]] ^ rcon, _SBOX[t[2]], _SBOX[t[3]], _SBOX[t[0]]]
            rcon = _gf_mul(rcon, 2)
        base = words[-16:-12]
        words.extend(base[i] ^ t[i] for i in range(4))
    return [words[i:i + 16] for i in range(0, 176, 16)]


_AES_ROUNDS = _expand_key(_IMG_KEY)


def _inv_shift(s):
    # AES uses column-major order. Row r shifts right r places.
    for row in range(1, 4):
        old = [s[row + 4 * col] for col in range(4)]
        for col in range(4):
            s[row + 4 * col] = old[(col - row) % 4]


def _aes_decrypt_block(block):
    state = list(block)
    keys = _AES_ROUNDS
    for i in range(16):
        state[i] ^= keys[10][i]
    for rnd in range(9, -1, -1):
        _inv_shift(state)
        state = [_INVSBOX[v] for v in state]
        for i in range(16):
            state[i] ^= keys[rnd][i]
        if rnd != 0:
            m9, m11, m13, m14 = (_MUL[i] for i in (9, 11, 13, 14))
            for col in range(0, 16, 4):
                a, b, c, d = state[col:col + 4]
                state[col:col + 4] = [
                    m14[a] ^ m11[b] ^ m13[c] ^ m9[d],
                    m9[a] ^ m14[b] ^ m11[c] ^ m13[d],
                    m13[a] ^ m9[b] ^ m14[c] ^ m11[d],
                    m11[a] ^ m13[b] ^ m9[c] ^ m14[d],
                ]
    return bytes(state)


def _pure_cbc_decrypt(body):
    if len(body) % 16:
        return b''
    result = bytearray()
    previous = _IMG_IV
    for off in range(0, len(body), 16):
        cipherblock = body[off:off + 16]
        plain = _aes_decrypt_block(cipherblock)
        result.extend(a ^ b for a, b in zip(plain, previous))
        previous = cipherblock
    return bytes(result)


def _image_kind(data):
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'GIF8'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return ''


def _decode_image(data):
    if _image_kind(data):
        return data
    if not data or len(data) % 16:
        return b''
    try:
        try:
            from Crypto.Cipher import AES
            result = AES.new(_IMG_KEY, AES.MODE_CBC, _IMG_IV).decrypt(data)
        except ImportError:
            try:
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                ctx = Cipher(algorithms.AES(_IMG_KEY), modes.CBC(_IMG_IV)).decryptor()
                result = ctx.update(data) + ctx.finalize()
            except ImportError:
                result = _pure_cbc_decrypt(data)
    except (ValueError, TypeError):
        return b''
    pad = result[-1]
    if 1 <= pad <= 16 and result[-pad:] == bytes([pad]) * pad:
        result = result[:-pad]
    if result.startswith(b'\xff\xd8\xff'):
        # Some CDN images append alignment zeros after the JPEG trailer.
        eoi = result.rfind(b'\xff\xd9')
        if eoi >= 0:
            result = result[:eoi + 2]
    return result if _image_kind(result) else b''


class Spider(BaseSpider):
    SITE = 'https://huangguoai.com'
    UA = ('Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36')
    CATEGORIES = (
        ('AI 成人短劇', 'ai-duanju'),
        ('AI 成人漫劇', 'ai-manju'),
        ('AI 換臉', 'ai-huanlian'),
        ('AI 魔改', 'ai-mogai'),
    )
    _HLS_TAG_URI = re.compile(r'(URI\s*=\s*)(["\'])(.*?)(\2)', re.I)

    def getName(self):
        return '黃果短劇（Python）'

    def init(self, extend=''):
        self.headers = {'User-Agent': self.UA, 'Accept': 'application/json',
                        'Referer': self.SITE + '/'}
        self.session = requests.Session()
        retry = Retry(total=2, backoff_factor=.4,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=frozenset(('GET', 'POST')))
        self.session.mount('https://', HTTPAdapter(max_retries=retry))
        self.session.mount('http://', HTTPAdapter(max_retries=retry))
        self._img_cache = {}
        self._lock = threading.RLock()

    def _ready(self):
        if not hasattr(self, 'session'):
            self.init('')

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(?:m3u8|mp4)(?:\?|$)', str(url or ''), re.I))

    def manualVideoCheck(self):
        return False

    def _proxy_base(self):
        try:
            result = str(self.getProxyUrl() or '').strip()
            return result if result.startswith(('http://', 'https://')) else ''
        except Exception:
            return ''

    def _proxy_url(self, action, upstream):
        base = self._proxy_base()
        if not base:
            return ''
        return base + ('&' if '?' in base else '?') + urlencode(
            {'hg_action': action, 'hg_url': upstream})

    @staticmethod
    def _valid_url(url, image=False):
        """Explicit domain scope prevents arbitrary local proxy SSRF requests."""
        try:
            p = urlparse(url)
            host = (p.hostname or '').lower()
            if p.scheme != 'https' or p.username or p.password or not host:
                return False
            if p.port not in (None, 443):
                return False
            if image:
                return host in ('pic.drleao.cn', 'new.drleao.cn',
                                'new2.drleao.cn', 'image.drleao.cn')
            return (host in ('yd-hls.hzjvlo.cn', 'yd-lphu-hls.hzjvlo.cn',
                             'tp3.drleao.cn') or host.endswith('.hzjvlo.cn')
                    or host.endswith('.drleao.cn'))
        except ValueError:
            return False

    def _get_json(self, path):
        self._ready()
        if not path.startswith('/api/') or '://' in path or path.startswith('//'):
            return {}
        envelope = {'method': 'GET', 'path': path, 'body': '', 'content_type': ''}
        for edge in (True, False):
            try:
                if edge:
                    r = self.session.post(self.SITE + '/api/edge/request',
                                          json=envelope, headers=self.headers, timeout=16)
                else:
                    r = self.session.get(self.SITE + path,
                                         headers=self.headers, timeout=16)
                r.raise_for_status()
                body = r.json()
                if not isinstance(body, dict):
                    continue
                if str(body.get('status')) == '1':
                    return body.get('data') or {}
                if str(body.get('status')) == '0':
                    # Business error may be edge-specific; direct call can still work.
                    continue
                if 'items' in body or 'episodes' in body or 'video_url' in body:
                    return body
            except (requests.RequestException, ValueError, TypeError):
                continue
        return {}

    def homeContent(self, filter=False):
        return {'class': [{'type_id': slug, 'type_name': name}
                          for name, slug in self.CATEGORIES]}

    def _cover_url(self, value):
        if not isinstance(value, str) or not self._valid_url(value, image=True):
            return value if isinstance(value, str) and value.startswith('https://') else ''
        # IMPORTANT: upstream URL yields AES ciphertext, not a displayable JPEG.
        # Proxy even when Crypto isn't installed; _decode_image has pure Python fallback.
        return self._proxy_url('image', value) or value

    def _video_item(self, item):
        n = int(item.get('episode_count') or 0)
        rem = ('已完結 · ' if item.get('is_finished') else '') + ('%d 集' % n if n else '')
        return {
            'vod_id': str(item['id']),
            'vod_name': item.get('title') or '未命名',
            'vod_pic': self._cover_url(item.get('cover') or ''),
            'vod_remarks': rem,
            'vod_content': item.get('description') or '',
            'style': {'type': 'rect', 'ratio': 0.68},
        }

    def _list(self, data):
        if not isinstance(data, dict):
            data = {}
        p = data.get('pagination') or {}
        return {'list': [self._video_item(x) for x in (data.get('items') or [])
                         if isinstance(x, dict) and x.get('id')],
                'page': int(p.get('page') or 1),
                'pagecount': int(p.get('pages') or 1),
                'limit': int(p.get('size') or 20),
                'total': int(p.get('total') or 0)}

    def homeVideoContent(self):
        return self._list(self._get_json('/api/videos?page=1&size=20'))

    def categoryContent(self, tid, pg, filter=False, extend=None):
        if tid not in {slug for _, slug in self.CATEGORIES}:
            return self._list({})
        pg = max(1, int(pg or 1))
        return self._list(self._get_json('/api/videos/category/%s?%s' %
                                         (tid, urlencode({'page': pg, 'size': 20}))))

    def searchContent(self, key, quick=False, pg='1'):
        if not str(key or '').strip():
            return self._list({})
        return self._list(self._get_json('/api/search?' + urlencode({
            'q': str(key).strip(), 'page': max(1, int(pg or 1)), 'size': 20})))

    def detailContent(self, array):
        vid = str(array[0]).strip() if array else ''
        if not vid.isdecimal():
            return {'list': []}
        item = self._get_json('/api/videos/' + vid)
        if not isinstance(item, dict) or not item:
            return {'list': []}
        eps = []
        for x in item.get('episodes') or []:
            if not isinstance(x, dict) or not str(x.get('ep_num', '')).isdigit():
                continue
            if str(x.get('status') or '').lower() in ('locked', 'disabled', 'unavailable'):
                continue
            eps.append(int(x['ep_num']))
        if not eps:
            eps = list(range(1, min(int(item.get('episode_count') or 0), 500) + 1))
        if not eps and item.get('video_url'):
            eps = [1]
        one = '#'.join('第%d集$%s:%d' % (ep, vid, ep) for ep in sorted(set(eps)))
        # Direct and proxy are deliberately separate lines for renderer compatibility.
        can_proxy = bool(self._proxy_base())
        detail = self._video_item(item)
        detail.update({
            'vod_year': str(item.get('created_at') or '')[:4],
            'vod_actor': (item.get('author') or {}).get('name', '')
                if isinstance(item.get('author'), dict) else '',
            'vod_tag': ','.join(item.get('tags') or []),
            'vod_play_from': '黃果直連' + ('$$$黃果代理' if can_proxy else ''),
            'vod_play_url': one + ('$$$' + one if can_proxy else ''),
        })
        return {'list': [detail]}

    def playerContent(self, flag, pid, vipFlags=None):
        value = str(pid or '')
        if not re.fullmatch(r'[0-9]+:[0-9]+', value):
            return {'parse': 0, 'jx': 0, 'url': ''}
        vid, ep = value.split(':', 1)
        data = self._get_json('/api/videos/%s/play?%s' % (
            vid, urlencode({'ep': ep, 'page_texts': 0})))
        # Prefer AVC/H.264 default to HEVC which may not be supported on older TV boxes.
        url = data.get('video_url') if isinstance(data, dict) else ''
        if not url and isinstance(data, dict):
            url = data.get('video_url_hevc')
        if not isinstance(url, str) or not self._valid_url(url):
            return {'parse': 0, 'jx': 0, 'url': ''}
        use_proxy = '代理' in str(flag or '')
        if use_proxy:
            proxied = self._proxy_url('hls' if '.m3u8' in url else 'asset', url)
            if proxied:
                return {'parse': 0, 'jx': 0, 'url': proxied,
                        'header': {'User-Agent': self.UA}}
        return {'parse': 0, 'jx': 0, 'url': url,
                'header': {'User-Agent': self.UA, 'Referer': self.SITE + '/'}}

    @classmethod
    def _rewrite_hls(cls, data, origin, proxify):
        # Handles master playlists, media playlists, key URI and EXT-X-MAP.
        # No decryption of HLS content by the Python spider is necessary.
        lines = []
        for line in data.decode('utf-8-sig', errors='replace').splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append(line)
                continue
            if stripped.startswith('#'):
                def replace(match):
                    if not match.group(3).strip():
                        return match.group(0)
                    candidate = urljoin(origin, match.group(3))
                    if not cls._valid_url(candidate):
                        return match.group(0)
                    kind = 'hls' if '.m3u8' in urlparse(candidate).path.lower() else 'asset'
                    new_url = proxify(kind, candidate)
                    return match.group(1) + match.group(2) + (new_url or candidate) + match.group(4)
                lines.append(cls._HLS_TAG_URI.sub(replace, line))
            else:
                candidate = urljoin(origin, stripped)
                if cls._valid_url(candidate):
                    kind = 'hls' if '.m3u8' in urlparse(candidate).path.lower() else 'asset'
                    lines.append(proxify(kind, candidate) or candidate)
                else:
                    lines.append(line)
        return ('\n'.join(lines) + '\n').encode('utf-8')

    def proxy(self, params):
        return self.localProxy(params)

    def localProxy(self, params):
        self._ready()
        params = params or {}
        action = str(params.get('hg_action') or '')
        url = str(params.get('hg_url') or '')
        request_url = url
        if action not in ('image', 'hls', 'asset'):
            return [400, 'text/plain; charset=utf-8', b'unknown action']
        if not self._valid_url(url, image=(action == 'image')):
            return [400, 'text/plain; charset=utf-8', b'blocked URL']
        if action == 'image':
            with self._lock:
                cached = self._img_cache.get(request_url)
            if cached:
                return [200, _image_kind(cached), cached]
        try:
            headers = {'User-Agent': self.UA,
                       'Referer': self.SITE + '/',
                       'Accept': '*/*'}
            # Preserve signing parameters while following only trusted CDN redirects.
            for _redirect in range(4):
                r = self.session.get(url, headers=headers, timeout=25,
                                     allow_redirects=False)
                if r.status_code not in (301, 302, 303, 307, 308):
                    break
                next_url = urljoin(url, r.headers.get('Location') or '')
                if next_url == url or not self._valid_url(next_url, image=(action == 'image')):
                    return [502, 'text/plain', b'blocked CDN redirect']
                url = next_url
            else:
                return [502, 'text/plain', b'too many CDN redirects']
            r.raise_for_status()
            binary = r.content
            if action == 'image':
                if len(binary) > 6 * 1024 * 1024:
                    return [413, 'text/plain', b'cover too large']
                picture = _decode_image(binary)
                if not picture:
                    return [502, 'text/plain', b'cover decrypt failed']
                with self._lock:
                    if len(self._img_cache) >= 25:
                        self._img_cache.pop(next(iter(self._img_cache)))
                    self._img_cache[request_url] = picture
                return [200, _image_kind(picture), picture]
            if action == 'hls':
                # An upstream 403/HTML/JSON response must never be passed as m3u8.
                if not binary.lstrip().startswith(b'#EXTM3U'):
                    return [502, 'text/plain', b'upstream is not a playlist']
                converted = self._rewrite_hls(binary, url, self._proxy_url)
                return [200, 'application/vnd.apple.mpegurl', converted]
            mimetype = r.headers.get('Content-Type', '').split(';')[0].strip().lower()
            if not mimetype or mimetype in ('application/octet-stream', 'binary/octet-stream'):
                mimetype = ('application/octet-stream' if '.key' in urlparse(url).path
                            else 'video/mp2t')
            return [200, mimetype, binary]
        except (requests.RequestException, ValueError, TypeError) as err:
            # Do not leak signed CDN auth tokens in logs or errors.
            return [502, 'text/plain; charset=utf-8',
                    ('upstream error: ' + type(err).__name__).encode('ascii')]

    def destroy(self):
        if hasattr(self, 'session'):
            self.session.close()
        return 'ok'
