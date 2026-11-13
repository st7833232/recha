# -*- coding: utf-8 -*-
"""黃果短劇 / TVBox + WebHTV compatible Python spider (2026-11).

Public catalog and freely reachable HLS only. No account or DRM bypass.
Fixes encrypted CDN thumbnails and offers a local HLS proxy for players whose
network/header handling cannot fetch upstream playlist, segments, and keys.
"""
import re
import sys
import os
import base64
import threading
import secrets
import json
import time
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urljoin, urlparse, urlsplit, parse_qs

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
        ('全部作品', 'all'),
        ('AI 成人短劇', 'ai-duanju'),
        ('AI 成人漫劇', 'ai-manju'),
        ('AI 換臉', 'ai-huanlian'),
        ('AI 魔改', 'ai-mogai'),
    )
    VERSION = '2026-11-13-v6-tags'
    # The site's JSON category endpoint ignores sort/year/finished parameters.
    # Alternative filters operate over a disclosed, bounded recent-content window.
    FILTER_SCAN_PAGES = 12
    FILTER_CACHE_SECONDS = 180
    _HLS_TAG_URI = re.compile(r'(URI\s*=\s*)(["\'])(.*?)(\2)', re.I)

    def getName(self):
        return '黃果短劇（雙平台 v4）'

    def init(self, extend=''):
        # `proxy_mode`: auto = Android native CatVod proxy, iOS independent loopback.
        # Explicit `{"proxy_mode":"android"}` or `{"proxy_mode":"self"}` is supported
        # for shells that misreport the platform. No other files need changing.
        opts = {}
        if isinstance(extend, dict):
            opts = extend
        elif isinstance(extend, str) and extend.strip().startswith('{'):
            try:
                opts = json.loads(extend)
            except (ValueError, TypeError):
                pass
        mode = str(opts.get('proxy_mode', 'auto')).lower() if isinstance(opts, dict) else 'auto'
        if mode not in ('auto', 'android', 'self'):
            mode = 'auto'
        if mode == 'auto':
            mode = ('android' if (sys.platform.startswith('android') or
                    hasattr(sys, 'getandroidapilevel') or
                    (sys.platform.startswith('linux') and
                     any(os.environ.get(k) for k in ('ANDROID_ROOT', 'ANDROID_ARGUMENT'))))
                    else 'self')
        self._proxy_mode = mode
        self._last_error = ''
        self._cdn_headers = {}
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
        self._filter_cache = {}
        self._tag_cache = {}

    def _ready(self):
        if not hasattr(self, 'session'):
            self.init('')

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(?:m3u8|mp4)(?:\?|$)', str(url or ''), re.I))

    def manualVideoCheck(self):
        return False

    def _local_server_url(self):
        """Create a loopback HTTP server on the first poster request.

        This avoids Android's `9978` getProxyUrl entirely for thumbnails and HLS.
        WebHTV iOS only rewrites Android proxy URLs on playback, not in `vod_pic`.
        Only allowed upstream CDN hosts can be fetched; the listener binds to loopback.
        """
        self._ready()
        with self._lock:
            if getattr(self, '_http_server', None):
                return 'http://127.0.0.1:%d' % self._http_server.server_address[1]
            if getattr(self, '_http_server_failed', False):
                return ''
            owner = self
            token = secrets.token_urlsafe(24)

            class Handler(BaseHTTPRequestHandler):
                protocol_version = 'HTTP/1.1'

                def log_message(self, format, *args):
                    # Never log CDN signed URLs or the loopback access token.
                    pass

                def do_HEAD(self):
                    self._serve(True)

                def do_GET(self):
                    self._serve(False)

                def _serve(self, head_only):
                    path = urlsplit(self.path)
                    if path.path != '/hg':
                        self.send_error(404)
                        return
                    p = parse_qs(path.query, keep_blank_values=True)
                    if p.get('token', [''])[0] != token:
                        self.send_error(403)
                        return
                    action = p.get('hg_action', [''])[0]
                    upstream = p.get('hg_url', [''])[0]
                    code, content_type, payload, extra = owner._proxy_fetch(
                        action, upstream, range_header=self.headers.get('Range', ''))
                    self.send_response(code)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Cache-Control', 'no-store' if action != 'image' else 'private, max-age=300')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    for key, val in extra.items():
                        self.send_header(key, val)
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    if not head_only:
                        try:
                            self.wfile.write(payload)
                        except (BrokenPipeError, ConnectionResetError):
                            pass

            try:
                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                server.daemon_threads = True
                thread = threading.Thread(target=server.serve_forever, name='hg-loopback', daemon=True)
                thread.start()
                self._http_server = server
                self._server_token = token
                return 'http://127.0.0.1:%d' % server.server_address[1]
            except (OSError, RuntimeError):
                self._http_server_failed = True
                return ''

    def _proxy_base(self):
        return self._local_server_url()

    def _native_proxy_url(self, action, upstream):
        try:
            native = str(self.getProxyUrl() or '').strip()
        except Exception:
            native = ''
        if not native.startswith(('http://127.0.0.1:', 'http://localhost:')):
            return ''
        return native + ('&' if '?' in native else '?') + urlencode({
            'hg_action': action, 'hg_url': upstream})

    def _proxy_url(self, action, upstream):
        # Avoid starting a Python HTTP listener in Android (Chaquopy): the
        # Android shell already has a CatVod localProxy service and owns its
        # lifecycle. On iOS, WebHTV's Android-compat service only serves playback
        # URLs, so images must use an independent loopback server.
        if getattr(self, '_proxy_mode', 'self') == 'android':
            native = self._native_proxy_url(action, upstream)
            if native:
                return native
        base = self._local_server_url()
        if base:
            return base + '/hg?' + urlencode({
                'token': self._server_token, 'hg_action': action, 'hg_url': upstream})
        return ''

    def _proxy_fetch(self, action, url, range_header=''):
        """Response as (status, mime, bytes, extra HTTP headers)."""
        if action not in ('image', 'hls', 'asset'):
            return 400, 'text/plain', b'unknown action', {}
        if not self._valid_url(url, image=(action == 'image')):
            return 403, 'text/plain', b'blocked URL', {}
        if action == 'image':
            with self._lock:
                cached = self._img_cache.get(url)
            if cached:
                return 200, _image_kind(cached), cached, {}
        request_url = url
        headers = {'User-Agent': self.UA, 'Accept': '*/*', 'Referer': self.SITE + '/'}
        if action != 'image':
            headers.update(getattr(self, '_cdn_headers', {}))
        if range_header and action == 'asset' and re.fullmatch(r'bytes=\d+-\d*', range_header):
            headers['Range'] = range_header
        try:
            for _ in range(4):
                resp = requests.get(url, headers=headers, allow_redirects=False, timeout=20)
                if resp.status_code not in (301, 302, 303, 307, 308):
                    break
                target = urljoin(url, resp.headers.get('Location') or '')
                if target == url or not self._valid_url(target, image=(action == 'image')):
                    return 502, 'text/plain', b'invalid redirect', {}
                url = target
            else:
                return 502, 'text/plain', b'too many redirects', {}
            resp.raise_for_status()
            body = resp.content
            if action == 'image':
                if len(body) > 6 * 1024 * 1024:
                    return 413, 'text/plain', b'cover too large', {}
                decoded = _decode_image(body)
                if not decoded:
                    return 502, 'text/plain', b'image decrypt failed', {}
                with self._lock:
                    if len(self._img_cache) >= 40:
                        self._img_cache.pop(next(iter(self._img_cache)))
                    self._img_cache[request_url] = decoded
                return 200, _image_kind(decoded), decoded, {}
            if action == 'hls':
                if not body.lstrip().startswith(b'#EXTM3U'):
                    return 502, 'text/plain', b'not a HLS playlist', {}
                return (200, 'application/vnd.apple.mpegurl',
                        self._rewrite_hls(body, url, self._proxy_url), {})
            content_type = resp.headers.get('Content-Type', 'application/octet-stream').split(';')[0]
            extra = {}
            if resp.status_code == 206:
                for field in ('Content-Range', 'Accept-Ranges'):
                    if resp.headers.get(field):
                        extra[field] = resp.headers[field]
            return resp.status_code, content_type, body, extra
        except (requests.RequestException, ValueError, TypeError):
            # Avoid leaking signed tokens in URLs to UI logs.
            return 502, 'text/plain', b'upstream request failed', {}

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
                                'new2.drleao.cn', 'image.drleao.cn',
                                'pic.eanfog.cn', 'pic.zdmhyg.cn', 'pic.tuafjz.cn')
            return (host in ('yd-hls.hzjvlo.cn', 'yd-lphu-hls.hzjvlo.cn',
                             'tp3.drleao.cn') or host.endswith('.hzjvlo.cn')
                    or host.endswith('.drleao.cn'))
        except ValueError:
            return False

    def _api_call(self, method, path, data=None):
        self._ready()
        if not path.startswith('/api/') or '://' in path or path.startswith('//'):
            return {}
        method = method.upper()
        if method not in ('GET', 'POST'):
            return {}
        payload = (json.dumps(data if data is not None else {}, ensure_ascii=False,
                              separators=(',', ':')).encode('utf-8') if method == 'POST'
                   else b'')
        envelope = {'method': method, 'path': path,
                    'body': base64.b64encode(payload).decode('ascii') if payload else '',
                    'content_type': 'application/json' if method == 'POST' else ''}
        errors = []
        # Edge gateway is the documented API contract. Direct request is a
        # compatibility fallback for deployments exposing the actual endpoint.
        for edge in (True, False):
            try:
                headers = dict(self.headers)
                if not edge and method == 'POST':
                    headers.update({'Content-Type': 'application/json', 'Origin': self.SITE})
                if edge:
                    response = self.session.post(self.SITE + '/api/edge/request',
                                                 json=envelope, headers=headers, timeout=16)
                elif method == 'GET':
                    response = self.session.get(self.SITE + path,
                                                headers=headers, timeout=16)
                else:
                    response = self.session.post(self.SITE + path, data=payload,
                                                 headers=headers, timeout=16)
                response.raise_for_status()
                obj = response.json()
                if not isinstance(obj, dict):
                    continue
                if str(obj.get('status', '1')) == '0':
                    errors.append(str(obj.get('msg') or 'upstream API status 0'))
                    continue
                data_obj = obj.get('data', obj)
                if isinstance(data_obj, dict) and data_obj:
                    self._last_error = ''
                    return data_obj
                if isinstance(data_obj, list):
                    self._last_error = ''
                    return {'items': data_obj}
            except (requests.RequestException, ValueError, TypeError) as exc:
                errors.append(type(exc).__name__)
        self._last_error = '/'.join(errors)[:120] or 'API returned no data'
        return {}

    def _get_json(self, path):
        return self._api_call('GET', path)

    def _post_json(self, path, data=None):
        return self._api_call('POST', path, data)

    @staticmethod
    def _public_media_url(url):
        # Direct player URLs need not belong to our proxy allowlist. The
        # upstream may rotate CDN domains without updating the script.
        try:
            p = urlparse(url)
            host = (p.hostname or '').lower()
            if p.scheme != 'https' or not host or p.username or p.password or p.port not in (None, 443):
                return False
            if host in ('localhost', 'localhost.localdomain') or host.endswith('.local'):
                return False
            import ipaddress
            try:
                return ipaddress.ip_address(host).is_global
            except ValueError:
                return '.' in host and not host.endswith('.')
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _play_url_from(data):
        if not isinstance(data, dict):
            return '', {}
        headers = {}
        cdn = data.get('cdn')
        if isinstance(cdn, dict):
            name, value = cdn.get('authKey'), cdn.get('authValue')
            if (isinstance(name, str) and isinstance(value, str) and
                    re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,63}', name) and
                    name.lower() not in ('host', 'cookie', 'authorization',
                                         'connection', 'transfer-encoding',
                                         'content-length', 'referer', 'origin')):
                headers[name] = value
        candidates = [data.get('video_url'), data.get('url'), data.get('play_url')]
        streams = data.get('streams')
        if isinstance(streams, dict):
            candidates.extend(streams.get(key) for key in ('main', 'avc', 'hevc', 'preview'))
        if isinstance(data.get('videos'), list):
            candidates.extend(x.get('url') if isinstance(x, dict) else x
                              for x in data['videos'])
        candidates.append(data.get('video_url_hevc'))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.startswith('https://'):
                return candidate, headers
        return '', headers


    def homeContent(self, filter=False):
        """CatVod/TVBox filters, shared by Android and WebHTV iOS."""
        year_now = datetime.now().year
        common = [
            {'key': 'sort', 'name': '排序', 'value': [
                {'n': '最新', 'v': 'latest'},
                {'n': '最熱（近期）', 'v': 'hot'},
                {'n': '評分最高（近期）', 'v': 'score'}]},
            {'key': 'year', 'name': '年份', 'value':
                [{'n': '全部', 'v': 'all'}] +
                [{'n': str(y), 'v': str(y)}
                 for y in range(year_now, max(2020, year_now - 6), -1)]},
            {'key': 'finished', 'name': '是否完結', 'value': [
                {'n': '全部', 'v': 'all'},
                {'n': '已完結', 'v': 'yes'},
                {'n': '連載中', 'v': 'no'}]},
            {'key': 'original', 'name': '是否原創', 'value': [
                {'n': '全部', 'v': 'all'},
                {'n': '黃果原創', 'v': 'yes'},
                {'n': '非原創', 'v': 'no'}]},
        ]
        # The public catalog exposes tags per video, but no server-side tag
        # predicate. Discover real recent labels once per cache window, with a
        # documented fallback when the catalog is temporarily unreachable.
        tag_options = self._tag_filter_options()
        return {
            'class': [{'type_id': slug, 'type_name': name}
                      for name, slug in self.CATEGORIES],
            'filters': {
                slug: common + [{'key': 'tag', 'name': '題材標籤（近期）',
                                  'value': [{'n': '全部', 'v': 'all'}] +
                                           [{'n': tag, 'v': tag}
                                            for tag in tag_options.get(slug, [])]}]
                for _, slug in self.CATEGORIES
            },
        }

    @staticmethod
    def _clean_tags(item):
        raw = item.get('tags') if isinstance(item, dict) else None
        if not isinstance(raw, (list, tuple)):
            return []
        found = []
        for value in raw:
            if not isinstance(value, str):
                continue
            tag = value.strip()
            if not tag or len(tag) > 36 or any(ord(ch) < 32 for ch in tag):
                continue
            if tag not in found:
                found.append(tag)
        return found

    def _tag_filter_options(self):
        self._ready()
        now = time.monotonic()
        with self._lock:
            saved = self._tag_cache.get('options')
            if saved and now - saved['at'] < self.FILTER_CACHE_SECONDS:
                return {k: list(v) for k, v in saved['values'].items()}

        # One page per channel, not a 12-page crawl just to render filter UI.
        # Labels are observed tags, not an invented or exhaustive tag taxonomy.
        counts = {}
        all_tags = Counter()
        for _, slug in self.CATEGORIES:
            if slug == 'all':
                continue
            data = self._get_json(self._catalog_path(slug, 1))
            entries = data.get('items') if isinstance(data, dict) else None
            count = Counter()
            for item in (entries if isinstance(entries, list) else []):
                count.update(self._clean_tags(item))
            counts[slug] = count
            all_tags.update(count)
        counts['all'] = all_tags

        # Fallback labels are verified examples from the public API schema,
        # and keep the control usable even when discovery requests fail.
        fallback = ['現代', '都市', '大男主', '熟女', '綠帽']
        options = {}
        for _, slug in self.CATEGORIES:
            count = counts.get(slug, Counter())
            observed = sorted(count, key=lambda tag: (-count[tag], tag))
            options[slug] = observed[:30] if observed else list(fallback)
        with self._lock:
            self._tag_cache['options'] = {'at': time.monotonic(), 'values': options}
        return options

    @staticmethod
    def _flag(value):
        """Unknown values remain unknown: never treat a missing flag as False."""
        if isinstance(value, bool):
            return value
        if value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            value = value.strip().lower()
            if value in ('1', 'true', 'yes'):
                return True
            if value in ('0', 'false', 'no'):
                return False
        return None

    @staticmethod
    def _metric(item, name):
        try:
            return float(item.get(name) or 0)
        except (TypeError, ValueError, OverflowError):
            return 0.0

    @staticmethod
    def _catalog_path(tid, page):
        params = urlencode({'page': page, 'size': 20})
        if tid == 'all':
            return '/api/videos?' + params
        return '/api/videos/category/%s?%s' % (tid, params)

    def _recent_catalog(self, tid):
        """A stable, bounded sample; do not pretend it covers the whole site."""
        self._ready()
        now = time.monotonic()
        with self._lock:
            saved = self._filter_cache.get(tid)
            if saved and now - saved['at'] < self.FILTER_CACHE_SECONDS:
                return list(saved['items']), saved['scanned'], saved['complete']

        all_items, ids = [], set()
        complete = False
        scanned = 0
        for source_page in range(1, self.FILTER_SCAN_PAGES + 1):
            data = self._get_json(self._catalog_path(tid, source_page))
            entries = data.get('items') if isinstance(data, dict) else None
            if not isinstance(entries, list):
                break  # transient API failure; do not cache a false empty catalog
            scanned += 1
            for item in entries:
                if not isinstance(item, dict) or item.get('id') is None:
                    continue
                video_id = str(item['id'])
                if video_id not in ids:
                    ids.add(video_id)
                    all_items.append(item)
            p = data.get('pagination') or {}
            try:
                page_count = int(p.get('pages') or 0)
            except (ValueError, TypeError):
                page_count = 0
            if not entries or (page_count and source_page >= page_count) or len(entries) < 20:
                complete = True
                break

        if scanned:
            with self._lock:
                self._filter_cache[tid] = {
                    'at': time.monotonic(), 'items': all_items,
                    'scanned': scanned, 'complete': complete,
                }
                # A bounded cache per source keeps memory use low on mobile.
                if len(self._filter_cache) > len(self.CATEGORIES):
                    self._filter_cache.pop(next(iter(self._filter_cache)))
        return all_items, scanned, complete

    def _cover_url(self, value):
        if not isinstance(value, str) or not self._valid_url(value, image=True):
            return value if isinstance(value, str) and value.startswith('https://') else ''
        # IMPORTANT: upstream URL yields AES ciphertext, not a displayable JPEG.
        # Our own loopback server can answer before a video starts playing.
        # Fail closed instead of showing encrypted bytes as a broken JPEG.
        return self._proxy_url('image', value) or '' 

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
        try:
            page = max(1, int(pg or 1))
        except (ValueError, TypeError):
            page = 1
        if isinstance(extend, dict):
            selected = dict(extend)
        elif isinstance(extend, str):
            try:
                obj = json.loads(extend)
                selected = obj if isinstance(obj, dict) else {}
            except (ValueError, TypeError):
                selected = {}
        else:
            selected = {}
        if isinstance(filter, dict):
            for key, value in filter.items():
                selected.setdefault(key, value)
        sort = str(selected.get('sort') or 'latest').strip().lower()
        year = str(selected.get('year') or 'all').strip()
        finished = str(selected.get('finished') or 'all').strip().lower()
        original = str(selected.get('original') or 'all').strip().lower()
        tag = str(selected.get('tag') or 'all').strip()
        if sort not in ('latest', 'hot', 'score'):
            sort = 'latest'
        if not (year == 'all' or (len(year) == 4 and year.isdigit())):
            year = 'all'
        if finished not in ('all', 'yes', 'no'):
            finished = 'all'
        if original not in ('all', 'yes', 'no'):
            original = 'all'
        if not tag or len(tag) > 36 or any(ord(ch) < 32 for ch in tag):
            tag = 'all'

        # Default listing uses upstream pagination: no unnecessary extra requests.
        if (sort == 'latest' and year == 'all' and
                finished == 'all' and original == 'all' and tag == 'all'):
            return self._list(self._get_json(self._catalog_path(tid, page)))

        # The API ignores query-string sort/filter parameters. We really filter
        # metadata, across a cached window of recent source pages, instead of
        # sending unsupported parameters that silently return unfiltered data.
        items, scanned, complete = self._recent_catalog(tid)
        filtered = []
        for item in items:
            if year != 'all' and str(item.get('created_at') or '')[:4] != year:
                continue
            if finished != 'all':
                actual = self._flag(item.get('is_finished'))
                if actual is None or actual != (finished == 'yes'):
                    continue
            if original != 'all':
                actual = self._flag(item.get('is_original'))
                if actual is None or actual != (original == 'yes'):
                    continue
            if tag != 'all' and tag not in self._clean_tags(item):
                continue
            filtered.append(item)

        if sort == 'hot':
            filtered.sort(key=lambda item: (
                self._metric(item, 'hot'),
                str(item.get('created_at') or ''),
                self._metric(item, 'score')), reverse=True)
        elif sort == 'score':
            filtered.sort(key=lambda item: (
                self._metric(item, 'score'),
                self._metric(item, 'hot'),
                str(item.get('created_at') or '')), reverse=True)
        else:
            filtered.sort(key=lambda item: str(item.get('created_at') or ''),
                          reverse=True)

        size = 20
        start = (page - 1) * size
        result = {
            'list': [self._video_item(item) for item in filtered[start:start + size]],
            'page': page,
            'pagecount': max(1, (len(filtered) + size - 1) // size),
            'limit': size,
            'total': len(filtered),
            # Diagnostic fields: these counts cover the sampled window only.
            'filter_scope': 'all' if complete else 'recent',
            'filter_scanned_pages': scanned,
        }
        return result

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
        can_proxy = bool(self._proxy_url('hls', 'https://yd-hls.hzjvlo.cn/test.m3u8'))
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
        # The public player endpoint differs between site generations.
        # Refetch per play; HLS auth_key expires, so no URL cache.
        paths = (
            ('POST', '/api/videos/%s/episodes/%s/playback' % (vid, ep)),
            ('GET', '/api/videos/%s/play?%s' % (
                vid, urlencode({'ep': ep, 'page_texts': 0}))),
            ('POST', '/api/videos/%s/playback' % vid),
        )
        url = ''
        extra = {}
        for method, path in paths:
            data = self._post_json(path, {}) if method == 'POST' else self._get_json(path)
            url, extra = self._play_url_from(data)
            if url and self._public_media_url(url):
                break
            url = ''
        if not url:
            return {'parse': 0, 'jx': 0, 'url': ''}
        self._cdn_headers = extra
        use_proxy = '代理' in str(flag or '')
        if use_proxy and self._valid_url(url):
            proxied = self._proxy_url('hls' if '.m3u8' in urlparse(url).path.lower() else 'asset', url)
            if proxied:
                return {'parse': 0, 'jx': 0, 'url': proxied,
                        'header': {'User-Agent': self.UA}}
        return {'parse': 0, 'jx': 0, 'url': url,
                'header': dict({'User-Agent': self.UA, 'Referer': self.SITE + '/'}, **extra)}


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
        params = params or {}
        action = str(params.get('hg_action') or '')
        url = str(params.get('hg_url') or '')
        code, content_type, body, headers = self._proxy_fetch(action, url,
            range_header=str(params.get('range') or ''))
        return [code, content_type, body, headers]

    def action(self, action):
        if action == 'diagnostics':
            return {'version': self.VERSION,
                    'proxy_mode': getattr(self, '_proxy_mode', 'uninitialized'),
                    'proxy_alive': bool(getattr(self, '_http_server', None)),
                    'last_api_error': getattr(self, '_last_error', '')}
        return {}

    def destroy(self):
        server = getattr(self, '_http_server', None)
        if server is not None:
            server.shutdown()
            server.server_close()
            self._http_server = None
        if hasattr(self, 'session'):
            self.session.close()
        return 'ok'
