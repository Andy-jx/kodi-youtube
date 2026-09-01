# -*- coding: utf-8 -*-
import importlib
import os

import xbmc
import xbmcgui
import xbmcplugin


def _setting_text(addon, key, default=''):
    """Read a Kodi setting as text without relying on typed getters.

    Some Kodi builds/settings schemas can raise TypeError('Invalid setting type')
    from getSettingString(). The legacy getSetting() API always returns text and is
    compatible with Kodi 19-21, so prefer it here.
    """
    try:
        value = addon.getSetting(key)
        return value if value not in (None, '') else default
    except Exception:
        return default


def _try_ytdlp(video_id, cookie_file=''):
    try:
        ytdlp = importlib.import_module('yt_dlp')
    except Exception:
        return None
    try:
        url = 'https://www.youtube.com/watch?v=%s' % video_id
        opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'format': 'best[ext=mp4]/best',
        }
        if cookie_file and os.path.exists(cookie_file):
            opts['cookiefile'] = cookie_file
        with ytdlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        direct = info.get('url')
        headers = info.get('http_headers') or {}
        if not direct:
            return None
        return direct, headers
    except Exception as exc:
        xbmc.log('[AndyYouTube] yt-dlp failed: %r' % exc, xbmc.LOGWARNING)
        return None


def _with_headers(url, headers):
    if not headers:
        return url
    from urllib.parse import quote
    pairs = []
    for key, value in headers.items():
        if key and value:
            pairs.append('%s=%s' % (quote(str(key)), quote(str(value))))
    return url + ('|' + '&'.join(pairs) if pairs else '')


def play_video(handle, video_id, addon, cookie_file=''):
    if not video_id:
        xbmcgui.Dialog().notification(addon.getAddonInfo('name'), '缺少视频 ID', xbmcgui.NOTIFICATION_ERROR, 3500)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    backend = _setting_text(addon, 'playback_backend', 'auto')
    if backend in ('auto', 'ytdlp'):
        result = _try_ytdlp(video_id, cookie_file)
        if result:
            direct, headers = result
            li = xbmcgui.ListItem(path=_with_headers(direct, headers))
            li.setProperty('IsPlayable', 'true')
            xbmcplugin.setResolvedUrl(handle, True, li)
            return
        if backend == 'ytdlp':
            xbmcgui.Dialog().notification(addon.getAddonInfo('name'), 'yt-dlp 无法解析此视频', xbmcgui.NOTIFICATION_ERROR, 3500)
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            return

    target = 'plugin://plugin.video.youtube/play/?video_id=%s' % video_id
    xbmc.Player().play(target)
    xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
