# -*- coding: utf-8 -*-
import json
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class YouTubeError(Exception):
    pass


class YouTubeClient:
    HOME = 'https://www.youtube.com/'

    def __init__(self, hl='zh-CN', gl='SG'):
        self.hl = hl
        self.gl = gl
        self.api_key = None
        self.client_version = None
        self.visitor_data = ''
        self.user_agent = 'Mozilla/5.0 (Linux; Android 10; TV) AppleWebKit/537.36 Chrome/124 Safari/537.36'

    def _request_text(self, url):
        req = Request(url, headers={
            'User-Agent': self.user_agent,
            'Accept-Language': self.hl + ',en;q=0.8',
        })
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
        data = json.dumps(body).encode('utf-8')
        req = Request(url, data=data, headers={
            'User-Agent': self.user_agent,
            'Content-Type': 'application/json',
            'Origin': 'https://www.youtube.com',
            'Referer': 'https://www.youtube.com/',
            'Accept-Language': self.hl + ',en;q=0.8',
        })
        try:
            with urlopen(req, timeout=20) as r:
                raw = r.read().decode('utf-8', 'replace')
            return json.loads(raw)
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
        if obj.get('simpleText'):
            return obj['simpleText']
        return ''.join(x.get('text', '') for x in obj.get('runs', []))

    @staticmethod
    def _thumb(obj):
        thumbs = ((obj or {}).get('thumbnails') or [])
        if not thumbs:
            return ''
        return thumbs[-1].get('url', '')

    @staticmethod
    def _duration_seconds(text):
        try:
            parts = [int(x) for x in (text or '').split(':')]
            total = 0
            for p in parts:
                total = total * 60 + p
            return total
        except Exception:
            return 0

    def _video_from_renderer(self, r):
        vid = r.get('videoId')
        if not vid:
            return None
        channel_id = ''
        channel = self._text(r.get('ownerText') or r.get('shortBylineText'))
        runs = (r.get('ownerText') or r.get('shortBylineText') or {}).get('runs', [])
        if runs:
            ep = runs[0].get('navigationEndpoint', {})
            channel_id = ep.get('browseEndpoint', {}).get('browseId', '')
        duration_text = self._text(r.get('lengthText'))
        return {
            'type': 'video',
            'video_id': vid,
            'title': self._text(r.get('title')),
            'channel': channel,
            'channel_id': channel_id,
            'thumbnail': self._thumb(r.get('thumbnail')),
            'description': self._text(r.get('descriptionSnippet')),
            'duration': self._duration_seconds(duration_text),
        }

    def _channel_from_renderer(self, r):
        cid = r.get('channelId')
        if not cid:
            return None
        return {
            'type': 'channel',
            'channel_id': cid,
            'title': self._text(r.get('title')),
            'thumbnail': self._thumb(r.get('thumbnail')),
        }

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
        unique = []
        seen = set()
        for x in items:
            key = (x.get('type'), x.get('video_id') or x.get('channel_id'))
            if key in seen or not key[1]:
                continue
            seen.add(key)
            unique.append(x)
        return {'items': unique, 'continuation': cont[-1] if cont else ''}

    def search(self, query, continuation=None):
        if continuation:
            data = self._post('search', {'continuation': continuation})
        else:
            data = self._post('search', {'query': query})
        return self._parse(data)

    def trending(self, continuation=None):
        if continuation:
            data = self._post('browse', {'continuation': continuation})
        else:
            data = self._post('browse', {'browseId': 'FEtrending'})
        return self._parse(data)

    def channel_videos(self, channel_id, continuation=None):
        if continuation:
            data = self._post('browse', {'continuation': continuation})
        else:
            # YouTube channel "Videos" tab params. If YouTube changes this value,
            # browse still fails cleanly rather than sending user credentials anywhere.
            data = self._post('browse', {
                'browseId': channel_id,
                'params': 'EgZ2aWRlb3PyBgQKAjoA',
            })
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
