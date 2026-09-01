# -*- coding: utf-8 -*-
import hashlib
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


class YouTubeError(Exception):
    pass


class YouTubeClient:
    HOME = 'https://www.youtube.com/'
    ORIGIN = 'https://www.youtube.com'

    def __init__(self, hl='zh-CN', gl='SG', cookie_file=''):
        self.hl = hl
        self.gl = gl
        self.cookie_file = cookie_file or ''
        self.api_key = None
        self.client_version = None
        self.visitor_data = ''
        self.user_agent = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/152.0.0.0 Safari/537.36')
        self.cookies = self._load_netscape_cookies(self.cookie_file)

    @staticmethod
    def _load_netscape_cookies(path):
        cookies = {}
        if not path or not os.path.exists(path):
            return cookies
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) < 7:
                        continue
                    domain, _, _, _, _, name, value = parts[:7]
                    if 'youtube.com' in domain or 'google.com' in domain:
                        cookies[name] = value
        except Exception:
            return {}
        return cookies

    def has_account_cookies(self):
        return bool(self.cookies.get('SAPISID') or self.cookies.get('__Secure-3PAPISID') or self.cookies.get('__Secure-1PAPISID'))

    def _cookie_header(self):
        return '; '.join('%s=%s' % (k, v) for k, v in self.cookies.items()) if self.cookies else ''

    def _auth_header(self):
        sid = self.cookies.get('SAPISID') or self.cookies.get('__Secure-3PAPISID') or self.cookies.get('__Secure-1PAPISID')
        if not sid:
            return ''
        ts = str(int(time.time()))
        digest = hashlib.sha1(('%s %s %s' % (ts, sid, self.ORIGIN)).encode('utf-8')).hexdigest()
        return 'SAPISIDHASH %s_%s' % (ts, digest)

    def _headers(self, json_request=False, referer=None):
        headers = {
            'User-Agent': self.user_agent,
            'Accept-Language': self.hl + ',en;q=0.8',
        }
        cookie = self._cookie_header()
        if cookie:
            headers['Cookie'] = cookie
        auth = self._auth_header()
        if auth:
            headers['Authorization'] = auth
            headers['X-Origin'] = self.ORIGIN
            headers['X-Goog-AuthUser'] = '0'
        if referer:
            headers['Referer'] = referer
        if json_request:
            headers.update({
                'Content-Type': 'application/json',
                'Origin': self.ORIGIN,
                'Referer': referer or self.HOME,
            })
        return headers

    def _request_text(self, url):
        req = Request(url, headers=self._headers(False, url))
        try:
            with urlopen(req, timeout=20) as r:
                return r.read().decode('utf-8', 'replace')
        except (HTTPError, URLError, TimeoutError) as exc:
            raise YouTubeError('YouTube 网络请求失败: %s' % exc)

    @staticmethod
    def _json_after_marker(text, marker):
        pos = text.find(marker)
        if pos < 0:
            return None
        start = text.find('{', pos + len(marker))
        if start < 0:
            return None
        try:
            data, _ = json.JSONDecoder().raw_decode(text[start:])
            return data
        except Exception:
            return None

    def _extract_initial_data(self, html):
        for marker in ('var ytInitialData =', 'window["ytInitialData"] =', "window['ytInitialData'] =", 'ytInitialData =', '"ytInitialData":'):
            data = self._json_after_marker(html, marker)
            if isinstance(data, dict):
                return data
        raise YouTubeError('无法解析 YouTube 页面数据，页面结构可能已变化')

    def _page_data(self, url):
        return self._extract_initial_data(self._request_text(url))

    def _bootstrap(self):
        if self.api_key and self.client_version:
            return
        html = self._request_text(self.HOME)
        patterns = {
            'api_key': [r'"INNERTUBE_API_KEY":"([^"]+)"', r'INNERTUBE_API_KEY\\?":\\?"([^"]+)"'],
            'client_version': [r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"'],
            'visitor_data': [r'"VISITOR_DATA":"([^"]+)"'],
        }
        for name, regs in patterns.items():
            for rgx in regs:
                m = re.search(rgx, html)
                if m:
                    setattr(self, name, m.group(1))
                    break
        if not self.api_key or not self.client_version:
            raise YouTubeError('无法读取 YouTube 页面配置，可能是网络或页面结构已变化')

    def _context(self):
        self._bootstrap()
        client = {
            'clientName': 'WEB',
            'clientVersion': self.client_version,
            'hl': self.hl,
            'gl': self.gl,
        }
        if self.visitor_data:
            client['visitorData'] = self.visitor_data
        return {'client': client}

    def _post(self, endpoint, payload):
        self._bootstrap()
        body = dict(payload)
        body.setdefault('context', self._context())
        url = 'https://www.youtube.com/youtubei/v1/%s?key=%s&prettyPrint=false' % (endpoint, self.api_key)
        req = Request(url, data=json.dumps(body).encode('utf-8'), headers=self._headers(True, self.HOME))
        try:
            with urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except HTTPError as exc:
            try:
                detail = exc.read().decode('utf-8', 'replace')[:300]
            except Exception:
                detail = str(exc)
            raise YouTubeError('YouTube HTTP %s: %s' % (exc.code, detail))
        except (URLError, TimeoutError, ValueError) as exc:
            raise YouTubeError('YouTube 请求失败: %s' % exc)

    @staticmethod
    def _text(obj):
        if not obj:
            return ''
        if isinstance(obj, str):
            return obj
        if not isinstance(obj, dict):
            return ''
        if obj.get('simpleText'):
            return obj['simpleText']
        if obj.get('content'):
            return obj['content']
        return ''.join(x.get('text', '') for x in obj.get('runs', []) if isinstance(x, dict))

    @staticmethod
    def _duration_seconds(text):
        try:
            total = 0
            for p in [int(x) for x in (text or '').split(':')]:
                total = total * 60 + p
            return total
        except Exception:
            return 0

    @classmethod
    def _find_value(cls, node, keys, validator=None):
        found = []
        def walk(value):
            if found:
                return
            if isinstance(value, list):
                for x in value:
                    walk(x)
                return
            if not isinstance(value, dict):
                return
            for key in keys:
                v = value.get(key)
                if v is not None and (validator is None or validator(v)):
                    found.append(v)
                    return
            for v in value.values():
                walk(v)
        walk(node)
        return found[0] if found else ''

    @classmethod
    def _video_id_from_node(cls, node):
        return cls._find_value(node, ('videoId', 'contentId'), lambda v: isinstance(v, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{11}', v)))

    @classmethod
    def _channel_id_from_node(cls, node):
        return cls._find_value(node, ('browseId', 'channelId'), lambda v: isinstance(v, str) and v.startswith('UC'))

    @classmethod
    def _image_url(cls, node):
        urls = []
        def walk(value):
            if isinstance(value, list):
                for x in value:
                    walk(x)
                return
            if not isinstance(value, dict):
                return
            url = value.get('url')
            if isinstance(url, str) and ('ytimg.com' in url or 'googleusercontent.com' in url):
                urls.append(url)
            for v in value.values():
                walk(v)
        walk(node)
        return urls[-1] if urls else ''

    def _video_from_any(self, r):
        if not isinstance(r, dict):
            return None
        vid = self._video_id_from_node(r)
        if not vid:
            return None
        title = self._text(r.get('title') or r.get('headline'))
        if not title:
            meta = r.get('metadata', {}).get('lockupMetadataViewModel', {})
            title = self._text(meta.get('title'))
        if not title:
            label = self._find_value(r, ('label',), lambda v: isinstance(v, str) and len(v.strip()) > 2)
            if label:
                title = label.split('\n')[0].strip()
        if not title:
            title = 'YouTube 视频'
        channel = self._text(r.get('ownerText') or r.get('shortBylineText') or r.get('longBylineText'))
        if not channel:
            meta = r.get('metadata', {}).get('lockupMetadataViewModel', {})
            rows = meta.get('metadata', {}).get('contentMetadataViewModel', {}).get('metadataRows', [])
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for part in row.get('metadataParts', []):
                    if not isinstance(part, dict):
                        continue
                    text = self._text(part.get('text'))
                    if text:
                        channel = text
                        break
                if channel:
                    break
        return {
            'type': 'video',
            'video_id': vid,
            'title': title,
            'channel': channel,
            'channel_id': self._channel_id_from_node(r),
            'thumbnail': self._image_url(r),
            'description': self._text(r.get('descriptionSnippet')),
            'duration': self._duration_seconds(self._text(r.get('lengthText'))),
        }

    def _channel_from_renderer(self, r):
        if not isinstance(r, dict):
            return None
        cid = r.get('channelId') or self._channel_id_from_node(r)
        if not cid:
            return None
        return {
            'type': 'channel',
            'channel_id': cid,
            'title': self._text(r.get('title')) or 'YouTube 频道',
            'thumbnail': self._image_url(r),
        }

    def _collect(self, node, out, continuations):
        if isinstance(node, list):
            for x in node:
                self._collect(x, out, continuations)
            return
        if not isinstance(node, dict):
            return
        video_keys = ('videoRenderer', 'gridVideoRenderer', 'compactVideoRenderer', 'playlistVideoRenderer', 'richItemRenderer', 'videoCardRenderer', 'compactVideoCardRenderer', 'videoCardViewModel', 'compactVideoViewModel', 'lockupViewModel', 'shortsLockupViewModel', 'reelItemRenderer')
        for key in video_keys:
            if key in node:
                item = self._video_from_any(node[key])
                if item:
                    out.append(item)
        if (('videoId' in node or 'contentId' in node) and any(k in node for k in ('title', 'headline', 'metadata', 'thumbnail', 'navigationEndpoint'))):
            item = self._video_from_any(node)
            if item:
                out.append(item)
        for key in ('channelRenderer', 'compactChannelRenderer'):
            if key in node:
                item = self._channel_from_renderer(node[key])
                if item:
                    out.append(item)
        if 'continuationItemRenderer' in node:
            ep = node['continuationItemRenderer'].get('continuationEndpoint', {})
            token = ep.get('continuationCommand', {}).get('token')
            if token:
                continuations.append(token)
        for value in node.values():
            self._collect(value, out, continuations)

    def _parse(self, data):
        items, continuations = [], []
        self._collect(data, items, continuations)
        unique, seen = [], set()
        for item in items:
            key = (item.get('type'), item.get('video_id') or item.get('channel_id'))
            if not key[1] or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return {'items': unique, 'continuation': continuations[-1] if continuations else ''}

    @staticmethod
    def _ensure_nonempty(result, label):
        if result.get('items'):
            return result
        raise YouTubeError('%s暂时没有解析到视频，请打开“诊断信息”查看详情' % label)

    def search(self, query, continuation=None):
        data = self._post('search', {'continuation': continuation} if continuation else {'query': query})
        return self._parse(data)

    def trending(self, continuation=None):
        if continuation:
            return self._parse(self._post('browse', {'continuation': continuation}))
        try:
            result = self._parse(self._page_data(self.HOME))
            if result.get('items'):
                return result
        except YouTubeError:
            pass
        result = self._parse(self._post('browse', {'browseId': 'FEwhat_to_watch'}))
        return self._ensure_nonempty(result, '热门 / 推荐')

    def subscriptions(self, continuation=None):
        if not self.has_account_cookies():
            raise YouTubeError('尚未导入有效的 YouTube 登录 cookies.txt')
        if continuation:
            return self._parse(self._post('browse', {'continuation': continuation}))
        try:
            result = self._parse(self._page_data('https://www.youtube.com/feed/subscriptions'))
            if result.get('items'):
                return result
        except YouTubeError:
            pass
        result = self._parse(self._post('browse', {'browseId': 'FEsubscriptions'}))
        return self._ensure_nonempty(result, '我的订阅')

    def account_test(self):
        if not self.has_account_cookies():
            return False
        try:
            html = self._request_text('https://www.youtube.com/feed/subscriptions')
            if 'accounts.google.com/ServiceLogin' in html or 'Sign in to YouTube' in html:
                return False
            data = self._extract_initial_data(html)
            return isinstance(data, dict)
        except Exception:
            return False

    def channel_videos(self, channel_id, continuation=None):
        if continuation:
            data = self._post('browse', {'continuation': continuation})
        else:
            data = self._post('browse', {'browseId': channel_id, 'params': 'EgZ2aWRlb3PyBgQKAjoA'})
        return self._parse(data)

    @staticmethod
    def extract_video_id(value):
        value = (value or '').strip()
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
            return value
        try:
            u = urlparse(value)
            host = (u.hostname or '').lower()
            if host in ('youtu.be', 'www.youtu.be'):
                vid = u.path.strip('/').split('/')[0]
                return vid if re.fullmatch(r'[A-Za-z0-9_-]{11}', vid or '') else ''
            if 'youtube.com' in host:
                if u.path == '/watch':
                    vid = parse_qs(u.query).get('v', [''])[0]
                    return vid if re.fullmatch(r'[A-Za-z0-9_-]{11}', vid or '') else ''
                parts = [x for x in u.path.split('/') if x]
                if len(parts) >= 2 and parts[0] in ('shorts', 'embed', 'live'):
                    vid = parts[1]
                    return vid if re.fullmatch(r'[A-Za-z0-9_-]{11}', vid or '') else ''
        except Exception:
            pass
        return ''
