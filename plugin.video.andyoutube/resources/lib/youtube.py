# -*- coding: utf-8 -*-
import hashlib
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urlparse
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
        self.user_agent = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/152.0.0.0 Safari/537.36'
        )
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
        return bool(
            self.cookies.get('SAPISID')
            or self.cookies.get('__Secure-3PAPISID')
            or self.cookies.get('__Secure-1PAPISID')
        )

    def _cookie_header(self):
        if not self.cookies:
            return ''
        return '; '.join('%s=%s' % (k, v) for k, v in self.cookies.items())

    def _auth_header(self):
        sid = (
            self.cookies.get('SAPISID')
            or self.cookies.get('__Secure-3PAPISID')
            or self.cookies.get('__Secure-1PAPISID')
        )
        if not sid:
            return ''
        ts = str(int(time.time()))
        digest = hashlib.sha1(
            ('%s %s %s' % (ts, sid, self.ORIGIN)).encode('utf-8')
        ).hexdigest()
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
            with urlopen(req, timeout=20) as response:
                return response.read().decode('utf-8', 'replace')
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
        markers = (
            'var ytInitialData =',
            'window["ytInitialData"] =',
            "window['ytInitialData'] =",
            'ytInitialData =',
            '"ytInitialData":',
        )
        for marker in markers:
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
            'api_key': [
                r'"INNERTUBE_API_KEY":"([^"]+)"',
                r'INNERTUBE_API_KEY\\?":\\?"([^"]+)"',
            ],
            'client_version': [r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"'],
            'visitor_data': [r'"VISITOR_DATA":"([^"]+)"'],
        }
        for name, regexes in patterns.items():
            for regex in regexes:
                match = re.search(regex, html)
                if match:
                    setattr(self, name, match.group(1))
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
        url = (
            'https://www.youtube.com/youtubei/v1/%s?key=%s&prettyPrint=false'
            % (endpoint, self.api_key)
        )
        req = Request(
            url,
            data=json.dumps(body).encode('utf-8'),
            headers=self._headers(True, self.HOME),
        )
        try:
            with urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode('utf-8', 'replace'))
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
        return ''.join(
            item.get('text', '')
            for item in obj.get('runs', [])
            if isinstance(item, dict)
        )

    @staticmethod
    def _duration_seconds(text):
        try:
            total = 0
            for part in [int(x) for x in (text or '').split(':')]:
                total = total * 60 + part
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
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            for key in keys:
                candidate = value.get(key)
                if candidate is not None and (
                    validator is None or validator(candidate)
                ):
                    found.append(candidate)
                    return
            for child in value.values():
                walk(child)

        walk(node)
        return found[0] if found else ''

    @classmethod
    def _video_id_from_node(cls, node):
        return cls._find_value(
            node,
            ('videoId', 'contentId'),
            lambda value: isinstance(value, str)
            and bool(re.fullmatch(r'[A-Za-z0-9_-]{11}', value)),
        )

    @classmethod
    def _channel_id_from_node(cls, node):
        return cls._find_value(
            node,
            ('browseId', 'channelId'),
            lambda value: isinstance(value, str) and value.startswith('UC'),
        )

    @classmethod
    def _image_url(cls, node):
        urls = []

        def walk(value):
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            url = value.get('url')
            if isinstance(url, str) and (
                'ytimg.com' in url or 'googleusercontent.com' in url
            ):
                urls.append(url)
            for child in value.values():
                walk(child)

        walk(node)
        return urls[-1] if urls else ''

    def _video_from_any(self, renderer):
        if not isinstance(renderer, dict):
            return None
        video_id = self._video_id_from_node(renderer)
        if not video_id:
            return None

        title = self._text(renderer.get('title') or renderer.get('headline'))
        if not title:
            metadata = renderer.get('metadata', {}).get('lockupMetadataViewModel', {})
            title = self._text(metadata.get('title'))
        if not title:
            label = self._find_value(
                renderer,
                ('label',),
                lambda value: isinstance(value, str) and len(value.strip()) > 2,
            )
            if label:
                title = label.split('\n')[0].strip()
        if not title:
            title = 'YouTube 视频'

        channel = self._text(
            renderer.get('ownerText')
            or renderer.get('shortBylineText')
            or renderer.get('longBylineText')
        )
        if not channel:
            metadata = renderer.get('metadata', {}).get('lockupMetadataViewModel', {})
            rows = (
                metadata.get('metadata', {})
                .get('contentMetadataViewModel', {})
                .get('metadataRows', [])
            )
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
            'video_id': video_id,
            'title': title,
            'channel': channel,
            'channel_id': self._channel_id_from_node(renderer),
            'thumbnail': self._image_url(renderer),
            'description': self._text(renderer.get('descriptionSnippet')),
            'duration': self._duration_seconds(
                self._text(renderer.get('lengthText'))
            ),
        }

    def _channel_from_renderer(self, renderer):
        if not isinstance(renderer, dict):
            return None
        channel_id = renderer.get('channelId') or self._channel_id_from_node(renderer)
        if not channel_id:
            return None
        return {
            'type': 'channel',
            'channel_id': channel_id,
            'title': self._text(renderer.get('title')) or 'YouTube 频道',
            'thumbnail': self._image_url(renderer),
        }

    def _collect(self, node, out, continuations):
        if isinstance(node, list):
            for item in node:
                self._collect(item, out, continuations)
            return
        if not isinstance(node, dict):
            return

        video_keys = (
            'videoRenderer',
            'gridVideoRenderer',
            'compactVideoRenderer',
            'playlistVideoRenderer',
            'richItemRenderer',
            'videoCardRenderer',
            'compactVideoCardRenderer',
            'videoCardViewModel',
            'compactVideoViewModel',
            'lockupViewModel',
            'shortsLockupViewModel',
            'reelItemRenderer',
        )
        for key in video_keys:
            if key in node:
                item = self._video_from_any(node[key])
                if item:
                    out.append(item)

        if (
            ('videoId' in node or 'contentId' in node)
            and any(
                key in node
                for key in (
                    'title',
                    'headline',
                    'metadata',
                    'thumbnail',
                    'navigationEndpoint',
                )
            )
        ):
            item = self._video_from_any(node)
            if item:
                out.append(item)

        for key in ('channelRenderer', 'compactChannelRenderer'):
            if key in node:
                item = self._channel_from_renderer(node[key])
                if item:
                    out.append(item)

        if 'continuationItemRenderer' in node:
            endpoint = node['continuationItemRenderer'].get('continuationEndpoint', {})
            token = endpoint.get('continuationCommand', {}).get('token')
            if token:
                continuations.append(token)

        for child in node.values():
            self._collect(child, out, continuations)

    def _parse(self, data):
        items = []
        continuations = []
        self._collect(data, items, continuations)

        unique = []
        seen = set()
        for item in items:
            key = (
                item.get('type'),
                item.get('video_id') or item.get('channel_id'),
            )
            if not key[1] or key in seen:
                continue
            seen.add(key)
            unique.append(item)

        return {
            'items': unique,
            'continuation': continuations[-1] if continuations else '',
        }

    @staticmethod
    def _ensure_nonempty(result, label):
        if result.get('items'):
            return result
        raise YouTubeError(
            '%s暂时没有解析到视频，请打开“诊断信息”查看详情' % label
        )

    def search(self, query, continuation=None):
        query = (query or '').strip()
        if not query:
            raise YouTubeError('请输入搜索内容')

        if continuation:
            result = self._parse(self._post('search', {'continuation': continuation}))
            return result

        # Primary path: Innertube search gives clean continuation tokens.
        try:
            result = self._parse(self._post('search', {'query': query}))
            if result.get('items'):
                return result
        except YouTubeError:
            pass

        # Fallback path: parse the same public search result page a browser sees.
        # This keeps search usable when YouTube changes the Innertube search
        # response while the normal web UI is still working.
        try:
            url = 'https://www.youtube.com/results?search_query=%s' % quote_plus(query)
            result = self._parse(self._page_data(url))
            if result.get('items'):
                return result
        except YouTubeError:
            pass

        raise YouTubeError('搜索暂时没有返回可用结果，请稍后重试或查看“诊断信息”')

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
            result = self._parse(
                self._page_data('https://www.youtube.com/feed/subscriptions')
            )
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
            if (
                'accounts.google.com/ServiceLogin' in html
                or 'Sign in to YouTube' in html
            ):
                return False
            data = self._extract_initial_data(html)
            return isinstance(data, dict)
        except Exception:
            return False

    def channel_videos(self, channel_id, continuation=None):
        if continuation:
            data = self._post('browse', {'continuation': continuation})
        else:
            data = self._post(
                'browse',
                {
                    'browseId': channel_id,
                    'params': 'EgZ2aWRlb3PyBgQKAjoA',
                },
            )
        return self._parse(data)

    @staticmethod
    def extract_video_id(value):
        value = (value or '').strip()
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
            return value
        try:
            parsed = urlparse(value)
            host = (parsed.hostname or '').lower()
            if host in ('youtu.be', 'www.youtu.be'):
                video_id = parsed.path.strip('/').split('/')[0]
                return (
                    video_id
                    if re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id or '')
                    else ''
                )
            if 'youtube.com' in host:
                if parsed.path == '/watch':
                    video_id = parse_qs(parsed.query).get('v', [''])[0]
                    return (
                        video_id
                        if re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id or '')
                        else ''
                    )
                parts = [part for part in parsed.path.split('/') if part]
                if len(parts) >= 2 and parts[0] in ('shorts', 'embed', 'live'):
                    video_id = parts[1]
                    return (
                        video_id
                        if re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id or '')
                        else ''
                    )
        except Exception:
            pass
        return ''
