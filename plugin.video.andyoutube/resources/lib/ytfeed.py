# -*- coding: utf-8 -*-
"""Lightweight list provider backed by yt-dlp's maintained YouTube extractors.

Do not import yt_dlp at module import time. Kodi starts this module for every
navigation action, so the heavy dependency is loaded only when an online feed
is actually opened.
"""
import hashlib
import importlib
import json
import os
import re
import sys
import time

import xbmcvfs

from resources.lib import debuglog


class FeedError(Exception):
    pass


def _addon_fs_path(addon, *parts):
    try:
        root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    except Exception:
        root = addon.getAddonInfo('path')
    return os.path.join(root, *parts)


def _prepare_vendor(addon):
    vendor = _addon_fs_path(addon, 'resources', 'lib', 'vendor')
    if os.path.isdir(vendor) and vendor not in sys.path:
        sys.path.insert(0, vendor)
    return vendor


def _load_ytdlp(addon):
    _prepare_vendor(addon)
    try:
        return importlib.import_module('yt_dlp')
    except Exception as exc:
        debuglog.write('feed resolver unavailable', 'yt_dlp import failed: %r' % exc)
        raise FeedError('列表引擎没有正确加载，请重新安装插件')


def _cache_path(profile, key):
    cache_dir = os.path.join(profile, 'feed_cache')
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        pass
    name = hashlib.sha1(key.encode('utf-8', 'replace')).hexdigest() + '.json'
    return os.path.join(cache_dir, name)


def _load_cache(profile, key, max_age):
    path = _cache_path(profile, key)
    try:
        if not os.path.isfile(path) or time.time() - os.path.getmtime(path) > max_age:
            return None
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get('items'):
            return data
    except Exception:
        return None
    return None


def _save_cache(profile, key, data):
    path = _cache_path(profile, key)
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False)
    except Exception:
        pass


def _video_id(entry):
    if not isinstance(entry, dict):
        return ''
    for value in (entry.get('id'), entry.get('url'), entry.get('webpage_url')):
        if isinstance(value, str):
            m = re.search(r'(?:v=|youtu\.be/|shorts/)?([A-Za-z0-9_-]{11})(?:$|[?&#/])?', value)
            if m:
                return m.group(1)
    return ''


def _thumbnail(entry, vid):
    value = entry.get('thumbnail') if isinstance(entry, dict) else ''
    if value:
        return value
    thumbs = entry.get('thumbnails') or [] if isinstance(entry, dict) else []
    for item in reversed(thumbs):
        if isinstance(item, dict) and item.get('url'):
            return item['url']
    return 'https://i.ytimg.com/vi/%s/hqdefault.jpg' % vid if vid else ''


def _convert(info):
    entries = info.get('entries') if isinstance(info, dict) else None
    if entries is None and isinstance(info, dict):
        entries = [info]
    items, seen = [], set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        vid = _video_id(entry)
        if not vid or vid in seen:
            continue
        seen.add(vid)
        title = entry.get('title') or entry.get('fulltitle') or 'YouTube 视频'
        channel = entry.get('channel') or entry.get('uploader') or entry.get('uploader_id') or ''
        channel_id = entry.get('channel_id') or ''
        items.append({
            'type': 'video',
            'video_id': vid,
            'title': title,
            'channel': channel,
            'channel_id': channel_id,
            'thumbnail': _thumbnail(entry, vid),
            'description': entry.get('description') or '',
            'duration': int(entry.get('duration') or 0),
        })
    return {'items': items, 'continuation': ''}


def _extract(addon, profile, target, cookie_file='', cache_key='', max_age=180, limit=30):
    cookie_stamp = ''
    if cookie_file and os.path.isfile(cookie_file):
        try:
            cookie_stamp = str(int(os.path.getmtime(cookie_file)))
        except Exception:
            cookie_stamp = 'cookie'
    key = '%s|%s' % (cache_key or target, cookie_stamp)
    cached = _load_cache(profile, key, max_age)
    if cached:
        debuglog.write('feed cache hit', cache_key or target)
        return cached

    ytdlp = _load_ytdlp(addon)
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',
        'lazy_playlist': True,
        'playlistend': limit,
        'cachedir': False,
        'ignoreerrors': True,
        'noplaylist': False,
    }
    if cookie_file and os.path.isfile(cookie_file):
        opts['cookiefile'] = cookie_file

    debuglog.write('feed resolver start', '%s; cookies=%s' % (cache_key or target, 'yes' if 'cookiefile' in opts else 'no'))
    try:
        with ytdlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
        result = _convert(info or {})
    except Exception as exc:
        debuglog.write('feed resolver failed', '%s: %s' % (cache_key or target, str(exc)[:1200]))
        raise FeedError('YouTube 列表加载失败，请打开“诊断信息”查看原因')

    if not result.get('items'):
        debuglog.write('feed resolver empty', cache_key or target)
        raise FeedError('YouTube 没有返回可显示的视频，请打开“诊断信息”查看原因')

    _save_cache(profile, key, result)
    debuglog.write('feed resolver success', '%s; items=%d' % (cache_key or target, len(result['items'])))
    return result


def recommended(addon, profile, cookie_file=''):
    # yt-dlp has a dedicated maintained extractor for YouTube recommendations.
    return _extract(addon, profile, ':ytrec', cookie_file, 'recommended', max_age=180, limit=30)


def subscriptions(addon, profile, cookie_file=''):
    if not cookie_file or not os.path.isfile(cookie_file):
        raise FeedError('请先导入 YouTube cookies.txt')
    # Dedicated subscriptions extractor. It uses the account cookie itself and
    # is more robust than recursively walking YouTube's constantly changing UI JSON.
    return _extract(addon, profile, ':ytsubs', cookie_file, 'subscriptions', max_age=120, limit=40)


def search(addon, profile, query, cookie_file=''):
    q = (query or '').strip()
    if not q:
        raise FeedError('请输入搜索关键词')
    # ytsearch is maintained by yt-dlp and avoids our own renderer parser.
    return _extract(addon, profile, 'ytsearch25:%s' % q, cookie_file, 'search:' + q, max_age=900, limit=25)
