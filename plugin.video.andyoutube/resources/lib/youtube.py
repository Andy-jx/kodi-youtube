# -*- coding: utf-8 -*-
import hashlib
import json
import os
import re
import time
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


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
        self.user_agent = 'Mozilla/5.0 (Linux; Android 10; TV) AppleWebKit/537.36 Chrome/124 Safari/537.36'
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
                    if len(parts) >= 7:
                        domain, _, _, _, _, name, value = parts[:7]
                        if 'youtube.com' in domain or 'google.com' in domain:
                            cookies[name] = value
        except Exception:
            return {}
        return cookies

    def has_account_cookies(self):
        return bool(self.cookies.get('SAPISID') or self.cookies.get('__Secure-3PAPISID'))

    def _cookie_header(self):
        if not self.cookies:
            return ''
        return '; '.join('%s=%s' % (k, v) for k, v in self.cookies.items())

    def _auth_header(self):
        sid = self.cookies.get('SAPISID') or self.cookies.get('__Secure-3PAPISID')
        if not sid:
            return ''
        ts = str(int(time.time()))
        digest = hashlib.sha1(('%s %s %s' % (ts, sid, self.ORIGIN)).encode('utf-8')).hexdigest()
        return 'SAPISIDHASH %s_%s' % (ts, digest)

    def _headers(self, json_request=False):
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
        if json_request:
            headers.update({
                'Content-Type': 'application/json',
                'Origin': self.ORIGIN,
                'Referer': self.HOME,
            })
        return headers

    def _request_text(self, url):
        req = Request(url, headers=self._headers(False))
        try:
            with urlopen(req, timeout=15) as r:
                return r.read().decode('utf-8', 'replace')
        except (HTTPError, URLError, TimeoutError) as exc:
            raise YouTubeError('YouTube 网络请求失败: %s' % exc)

    def _bootstrap(self):
        if self.api_key and self.client_version:
            return
        html = self._request_text(self.HOME)
        patterns = {
            'api_key': [r'"INNERTUBE_API_KEY":"([^"]+)"', r'INNERTUBE_API_KEY":"([^"]+)"'],
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
        req = Request(url, data=json.dumps(body).encode('utf-8'), headers=self._headers(True))
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
    def _thumb(obj):
        thumbs = ((obj or {}).get('thumbnails') or [])
        return thumbs[-1].get('url', '') if thumbs else ''

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

    @classmethod
    def _channel_id_from_node(cls, node):
        found = []

        def walk(value):
            if isinstance(value, list):
                for x in value:
                    walk(x)
                return
            if not isinstance(value, dict):
                return
            browse = value.get('browseEndpoint')
            if isinstance(browse, dict):
                bid = browse.get('browseId', '')
                if isinstance(bid, str) and bid.startswith('UC'):
                    found.append(bid)
            for v in value.values():
                walk(v)

        walk(node)
        return found[0] if found else ''

    @staticmethod
    def _duration_seconds(text):
        try:
            total = 0
            for p in [int(x) for x in (text or '').split(':')]:
                total = total * 60 + p
            return total
        except Exception:
            return 0

    def _video_from_renderer(self, r):
        if not isinstance(r, dict):
            return None
        vid = r.get('videoId')
        if not vid:
            return None
        channel_id = ''
        channel = self._text(r.get('ownerText') or r.get('shortBylineText') or r.get('longBylineText'))
        runs = (r.get('ownerText') or r.get('shortBylineText') or r.get('longBylineText') or {}).get('runs', [])
        if runs:
            channel_id = runs[0].get('navigationEndpoint', {}).get('browseEndpoint', {}).get('browseId', '')
        duration_text = self._text(r.get('lengthText'))
        title = self._text(r.get('title') or r.get('headline'))
        if not title:
            return None
        return {
            'type': 'video', 'video_id': vid,
            'title': title, 'channel': channel, 'channel_id': channel_id,
            'thumbnail': self._thumb(r.get('thumbnail')) or self._image_url(r),
            'description': self._text(r.get('descriptionSnippet')),
            'duration': self._duration_seconds(duration_text),
        }

    def _video_from_lockup(self, r):
        if not isinstance(r, dict):
            return None
        content_type = r.get('contentType', '')
        if content_type and content_type not in ('LOCKUP_CONTENT_TYPE_VIDEO', 'LOCKUP_CONTENT_TYPE_SHORTS'):
            return None
        vid = r.get('contentId') or r.get('videoId')
        if not isinstance(vid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            return None
        meta = r.get('metadata', {}).get('lockupMetadataViewModel', {})
        title = self._text(meta.get('title'))
        if not title:
            label = r.get('rendererContext', {}).get('accessibilityContext', {}).get('label', '')
            if isinstance(label, str) and label:
                title = label.split('\n')[0].strip()
        if not title:
            title = 'YouTube 视频'

        channel = ''
        rows = meta.get('metadata', {}).get('contentMetadataViewModel', {}).get('metadataRows', [])
        for row in rows:
            for part in row.get('metadataParts', []) if isinstance(row, dict) else []:
                text = self._text(part.get('text'))
                if text and not channel:
                    channel = text
                    break
            if channel:
                break

        return {
            'type': 'video', 'video_id': vid,
            'title': title,
            'channel': channel,
            'channel_id': self._channel_id_from_node(meta) or self._channel_id_from_node(r),
            'thumbnail': self._image_url(r),
            'description': '',
            'duration': 0,
        }

    def _video_from_card(self, r):
        if not isinstance(r, dict):
            return None
        vid = r.get('videoId') or r.get('contentId')
        if not isinstance(vid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            return None
        title = self._text(r.get('title') or r.get('headline'))
        if not title:
            title = self._text(r.get('metadata', {}).get('lockupMetadataViewModel', {}).get('title'))
        if not title:
            return None
        return {
            'type': 'video', 'video_id': vid,
            'title': title,
            'channel': self._text(r.get('ownerText') or r.get('shortBylineText') or r.get('longBylineText')),
            'channel_id': self._channel_id_from_node(r),
            'thumbnail': self._thumb(r.get('thumbnail')) or self._image_url(r),
            'description': self._text(r.get('descriptionSnippet')),
            'duration': self._duration_seconds(self._text(r.get('lengthText'))),
        }

    def _channel_from_renderer(self, r):
        cid = r.get('channelId') or r.get('channelId', '')
        if not cid:
            return None
        return {'type': 'channel', 'channel_id': cid, 'title': self._text(r.get('title')), 'thumbnail': self._thumb(r.get('thumbnail'))}

    def _collect(self, node, out, continuations):
        if isinstance(node, list):
            for x in node:
                self._collect(x, out, continuations)
            return
        if not isinstance(node, dict):
            return

        for key in ('videoRenderer', 'gridVideoRenderer', 'compactVideoRenderer', 'playlistVideoRenderer'):
            if key in node:
                item = self._video_from_renderer(node[key])
                if item:
                    out.append(item)

        for key in ('videoCardRenderer', 'compactVideoCardRenderer'):
            if key in node:
                item = self._video_from_card(node[key])
                if item:
                    out.append(item)

        if 'lockupViewModel' in node:
            item = self._video_from_lockup(node['lockupViewModel'])
            if item:
                out.append(item)

        if 'shortsLockupViewModel' in node:
            item = self._video_from_lockup(node['shortsLockupViewModel'])
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
        items, cont = [], []
        self._collect(data, items, cont)
        unique, seen = [], set()
        for x in items:
            key = (x.get('type'), x.get('video_id') or x.get('channel_id'))
            if key in seen or not key[1]:
                continue
            seen.add(key)
            unique.append(x)
        return {'items': unique, 'continuation': cont[-1] if cont else ''}

    def search(self, query, continuation=None):
        return self._parse(self._post('search', {'continuation': continuation} if continuation else {'query': query}))

    def trending(self, continuation=None):
        # YouTube retired the old FEtrending feed. FEwhat_to_watch is the
        # current Home/Recommended feed and works for both signed-in and
        # signed-out sessions.
        payload = {'continuation': continuation} if continuation else {'browseId': 'FEwhat_to_watch'}
        return self._parse(self._post('browse', payload))

    def subscriptions(self, continuation=None):
        if not self.has_account_cookies():
            raise YouTubeError('尚未导入有效的 YouTube 登录 cookies.txt')
        payload = {'continuation': continuation} if continuation else {'browseId': 'FEsubscriptions'}
        return self._parse(self._post('browse', payload))

    def account_test(self):
        if not self.has_account_cookies():
            return False
        try:
            data = self._post('browse', {'browseId': 'FEsubscriptions'})
            return isinstance(data, dict) and not data.get('error')
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
