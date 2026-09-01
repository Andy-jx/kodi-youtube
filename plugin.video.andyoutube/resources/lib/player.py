# -*- coding: utf-8 -*-
import importlib
import os
import sys

import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs

try:
    from resources.lib import debuglog
except Exception:
    debuglog = None


_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/152.0.0.0 Safari/537.36'
)


class _KodiLogger(object):
    def debug(self, msg):
        if str(msg).startswith('[debug]'):
            xbmc.log('[AndyYouTube][yt-dlp] %s' % msg, xbmc.LOGDEBUG)

    def info(self, msg):
        xbmc.log('[AndyYouTube][yt-dlp] %s' % msg, xbmc.LOGINFO)

    def warning(self, msg):
        xbmc.log('[AndyYouTube][yt-dlp] %s' % msg, xbmc.LOGWARNING)

    def error(self, msg):
        xbmc.log('[AndyYouTube][yt-dlp] %s' % msg, xbmc.LOGERROR)


def _debug(event, detail=''):
    try:
        if debuglog:
            debuglog.write(event, detail)
    except Exception:
        pass


def _setting_text(addon, key, default=''):
    """Read a Kodi setting as text without relying on typed getters."""
    try:
        value = addon.getSetting(key)
        return value if value not in (None, '') else default
    except Exception:
        return default


def _addon_fs_path(addon, *parts):
    try:
        root = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    except Exception:
        root = addon.getAddonInfo('path')
    return os.path.join(root, *parts)


def _prepare_vendored_runtime(addon):
    """Make the release-bundled yt-dlp package visible to Kodi Python.

    Release ZIPs built by GitHub Actions contain a pure-Python yt-dlp + EJS
    package under resources/lib/vendor. Windows builds additionally contain an
    official Deno runtime so YouTube's 2026 JavaScript challenges can be solved
    without requiring the user to install anything separately.
    """
    vendor = _addon_fs_path(addon, 'resources', 'lib', 'vendor')
    if os.path.isdir(vendor) and vendor not in sys.path:
        sys.path.insert(0, vendor)

    deno = ''
    if sys.platform.startswith('win'):
        candidate = _addon_fs_path(addon, 'resources', 'bin', 'win64', 'deno.exe')
        if os.path.isfile(candidate):
            deno = candidate
    return vendor, deno


def _best_single_stream(info):
    """Return a directly playable A/V stream when top-level url is absent."""
    direct = info.get('url') if isinstance(info, dict) else None
    headers = info.get('http_headers') or {} if isinstance(info, dict) else {}
    if direct:
        return direct, headers

    formats = info.get('formats') or [] if isinstance(info, dict) else []
    candidates = []
    for fmt in formats:
        if not isinstance(fmt, dict) or not fmt.get('url'):
            continue
        if fmt.get('vcodec') in (None, 'none') or fmt.get('acodec') in (None, 'none'):
            continue
        candidates.append(fmt)
    if not candidates:
        return None

    candidates.sort(
        key=lambda f: (
            int(f.get('height') or 0),
            float(f.get('fps') or 0),
            float(f.get('tbr') or 0),
        ),
        reverse=True,
    )
    chosen = candidates[0]
    return chosen.get('url'), chosen.get('http_headers') or headers


def _try_ytdlp(video_id, addon, cookie_file=''):
    _, deno_path = _prepare_vendored_runtime(addon)
    try:
        ytdlp = importlib.import_module('yt_dlp')
    except Exception as exc:
        detail = 'yt_dlp import failed: %r' % exc
        xbmc.log('[AndyYouTube] %s' % detail, xbmc.LOGWARNING)
        _debug('playback resolver unavailable', detail)
        return None, detail

    try:
        url = 'https://www.youtube.com/watch?v=%s' % video_id
        opts = {
            'quiet': True,
            'no_warnings': False,
            'skip_download': True,
            'noplaylist': True,
            'cachedir': False,
            # A single A/V stream is preferable for direct Kodi playback. This
            # intentionally favors reliable playback over 4K DASH merging.
            'format': 'best[ext=mp4]/best',
            'logger': _KodiLogger(),
            'http_headers': {
                'User-Agent': _BROWSER_UA,
                'Referer': 'https://www.youtube.com/',
            },
        }
        if cookie_file and os.path.exists(cookie_file):
            opts['cookiefile'] = cookie_file
        if deno_path:
            opts['js_runtimes'] = {'deno': {'path': deno_path}}

        version = getattr(getattr(ytdlp, 'version', None), '__version__', '')
        _debug(
            'playback resolver start',
            'video=%s; yt-dlp=%s; cookies=%s; deno=%s' % (
                video_id,
                version or 'bundled',
                'yes' if cookie_file and os.path.exists(cookie_file) else 'no',
                'yes' if deno_path else 'no',
            ),
        )

        with ytdlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        selected = _best_single_stream(info)
        if not selected:
            detail = 'yt-dlp returned no directly playable A/V stream'
            _debug('playback resolver failed', detail)
            return None, detail
        _debug('playback resolver success', 'video=%s' % video_id)
        return selected, ''
    except Exception as exc:
        # Do not log cookie contents. yt-dlp exception text contains the video
        # URL / extraction reason but not the Netscape cookie values.
        detail = str(exc) or repr(exc)
        xbmc.log('[AndyYouTube] yt-dlp failed: %r' % exc, xbmc.LOGWARNING)
        _debug('playback resolver failed', detail[:1500])
        return None, detail


def _try_legacy_youtubedl(video_id, cookie_file=''):
    """Optional final extractor fallback when Kodi's youtube-dl module exists."""
    try:
        ytdl = importlib.import_module('youtube_dl')
    except Exception:
        return None
    try:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'format': 'best[ext=mp4]/best',
        }
        if cookie_file and os.path.exists(cookie_file):
            opts['cookiefile'] = cookie_file
        with ytdl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info('https://www.youtube.com/watch?v=%s' % video_id, download=False)
        selected = _best_single_stream(info)
        return selected
    except Exception:
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
        result, error_text = _try_ytdlp(video_id, addon, cookie_file)
        if result:
            direct, headers = result
            li = xbmcgui.ListItem(path=_with_headers(direct, headers))
            li.setProperty('IsPlayable', 'true')
            xbmcplugin.setResolvedUrl(handle, True, li)
            return

        legacy = _try_legacy_youtubedl(video_id, cookie_file)
        if legacy:
            direct, headers = legacy
            li = xbmcgui.ListItem(path=_with_headers(direct, headers))
            li.setProperty('IsPlayable', 'true')
            xbmcplugin.setResolvedUrl(handle, True, li)
            return

        if backend == 'ytdlp':
            msg = '账号视频解析失败，请查看“诊断信息”'
            xbmcgui.Dialog().notification(addon.getAddonInfo('name'), msg, xbmcgui.NOTIFICATION_ERROR, 5000)
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            return

        if cookie_file and os.path.exists(cookie_file):
            # Auto mode can still try the official add-on for public videos, but
            # account/age-restricted videos normally need our cookie-aware path.
            _debug('playback fallback', 'cookie-aware resolver failed; official add-on fallback; reason=%s' % error_text[:500])

    target = 'plugin://plugin.video.youtube/play/?video_id=%s' % video_id
    xbmc.Player().play(target)
    xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
