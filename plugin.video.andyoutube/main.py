# -*- coding: utf-8 -*-
import os
import sys
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import storage, debuglog
from resources.lib.youtube import YouTubeClient, YouTubeError
from resources.lib.player import play_video

ADDON = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
COOKIE_FILE = os.path.join(PROFILE, 'cookies.txt')
DEBUG_LOG_FILE = os.path.join(PROFILE, 'AndyYouTube-debug.log')
debuglog.configure(DEBUG_LOG_FILE)
debuglog.write('plugin start', 'version=%s' % ADDON.getAddonInfo('version'))


def plugin_url(**params):
    return BASE_URL + '?' + urlencode({k: v for k, v in params.items() if v is not None})


def add_folder(label, action, art=None, context=None, **params):
    li = xbmcgui.ListItem(label=label)
    if art:
        li.setArt(art)
    li.setInfo('video', {'title': label})
    if context:
        li.addContextMenuItems(context)
    xbmcplugin.addDirectoryItem(HANDLE, plugin_url(action=action, **params), li, True)


def add_video(item):
    title = item.get('title') or 'Untitled'
    video_id = item.get('video_id') or ''
    channel_id = item.get('channel_id') or ''
    channel = item.get('channel') or ''
    thumb = item.get('thumbnail') or ''
    li = xbmcgui.ListItem(label=title)
    li.setProperty('IsPlayable', 'true')
    li.setInfo('video', {
        'title': title,
        'plot': item.get('description', ''),
        'studio': channel,
        'duration': item.get('duration', 0) or 0,
    })
    if thumb:
        li.setArt({'thumb': thumb, 'icon': thumb, 'fanart': thumb})
    fav = storage.is_favorite(video_id)
    fav_label = '移出我喜欢' if fav else '加入我喜欢'
    fav_action = 'remove_favorite' if fav else 'add_favorite'
    ctx = [(fav_label, 'RunPlugin(%s)' % plugin_url(action=fav_action, video_id=video_id, title=title, channel=channel, channel_id=channel_id, thumbnail=thumb))]
    if channel_id:
        ctx.append(('进入作者频道', 'Container.Update(%s)' % plugin_url(action='channel', channel_id=channel_id, title=channel)))
    ctx.append(('刷新本页', 'Container.Refresh'))
    li.addContextMenuItems(ctx)
    xbmcplugin.addDirectoryItem(HANDLE, plugin_url(action='play', video_id=video_id, title=title, channel=channel, thumbnail=thumb), li, False)


def finish(content='videos'):
    xbmcplugin.setContent(HANDLE, content)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def notify(msg, icon=xbmcgui.NOTIFICATION_INFO):
    xbmcgui.Dialog().notification(ADDON.getAddonInfo('name'), msg, icon, 5000)


def log_error(prefix, exc):
    xbmc.log('[AndyYouTube] %s: %r' % (prefix, exc), xbmc.LOGERROR)
    debuglog.exception(prefix, exc)


def setting_text(key, default=''):
    """Read settings as text using Kodi's compatibility getter.

    On some Kodi 21 builds getSettingString() can raise
    TypeError('Invalid setting type') even for a string-backed setting.
    getSetting() is compatible with both legacy and current settings schemas.
    """
    try:
        value = ADDON.getSetting(key)
        return value if value not in (None, '') else default
    except Exception as exc:
        log_error('setting read failed: %s' % key, exc)
        return default


def client():
    return YouTubeClient(
        hl=setting_text('language', 'zh-CN'),
        gl=setting_text('region', 'SG'),
        cookie_file=COOKIE_FILE,
    )


def cookie_exists():
    try:
        return xbmcvfs.exists(COOKIE_FILE)
    except Exception:
        return os.path.exists(COOKIE_FILE)


def remove_cookie_file():
    try:
        if xbmcvfs.exists(COOKIE_FILE):
            xbmcvfs.delete(COOKIE_FILE)
            return
    except Exception:
        pass
    try:
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
    except Exception:
        pass


def account_ready():
    if not cookie_exists():
        return False
    try:
        return client().has_account_cookies()
    except Exception as exc:
        log_error('cookie local check failed', exc)
        return False


def show_home():
    if account_ready():
        add_folder('我的订阅', 'subscriptions')
        add_folder('YouTube 账号：已连接', 'account_status')
    else:
        add_folder('连接我的 YouTube 账号', 'import_cookies')
    add_folder('搜索 YouTube', 'search_prompt')
    add_folder('热门 / 推荐', 'trending')
    add_folder('我喜欢的视频（本地）', 'favorites')
    add_folder('观看历史', 'history')
    add_folder('搜索历史', 'search_history')
    add_folder('打开 YouTube 链接', 'open_url_prompt')
    add_folder('插件设置', 'settings')
    add_folder('诊断信息', 'diagnostics')
    finish('files')


def render_result(result, continuation_action=None, continuation_params=None):
    for item in result.get('items', []):
        if item.get('type') == 'video' and item.get('video_id'):
            add_video(item)
        elif item.get('type') == 'channel' and item.get('channel_id'):
            add_folder('[频道] ' + item.get('title', '频道'), 'channel', channel_id=item['channel_id'], title=item.get('title', ''))
    token = result.get('continuation')
    if token and continuation_action:
        params = dict(continuation_params or {})
        params['continuation'] = token
        add_folder('下一页 ▶', continuation_action, **params)
    finish()


def import_cookies():
    try:
        source = xbmcgui.Dialog().browse(1, '选择 YouTube cookies.txt', 'files', '.txt')
    except Exception as exc:
        log_error('cookie picker failed', exc)
        notify('无法打开文件选择器，请打开“诊断信息”查看详情', xbmcgui.NOTIFICATION_ERROR)
        finish('files')
        return

    if not source:
        finish('files')
        return

    debuglog.write('cookie import', 'file selected')

    try:
        xbmcvfs.mkdirs(PROFILE)
    except Exception:
        try:
            os.makedirs(PROFILE, exist_ok=True)
        except Exception as exc:
            log_error('profile create failed', exc)
            notify('无法创建插件数据目录', xbmcgui.NOTIFICATION_ERROR)
            finish('files')
            return

    remove_cookie_file()

    try:
        copied = xbmcvfs.copy(source, COOKIE_FILE)
        if not copied or not cookie_exists():
            raise IOError('Kodi VFS copy returned false')
    except Exception as exc:
        log_error('cookie VFS copy failed', exc)
        try:
            local_source = xbmcvfs.translatePath(source)
            src = xbmcvfs.File(local_source, 'rb')
            data = src.readBytes()
            src.close()
            dst = xbmcvfs.File(COOKIE_FILE, 'wb')
            dst.write(data)
            dst.close()
        except Exception as fallback_exc:
            log_error('cookie fallback copy failed', fallback_exc)
            remove_cookie_file()
            notify('Cookie 文件导入失败，请确认文件可读取', xbmcgui.NOTIFICATION_ERROR)
            finish('files')
            return

    debuglog.write('cookie import', 'copy completed')

    try:
        cookie_client = client()
        if not cookie_client.has_account_cookies():
            remove_cookie_file()
            debuglog.write('cookie validation', 'required YouTube account cookies not found')
            notify('不是有效的 YouTube cookies.txt，请重新导出当前 youtube.com Cookie', xbmcgui.NOTIFICATION_ERROR)
            finish('files')
            return

        debuglog.write('cookie validation', 'local format accepted; starting online test')
        if cookie_client.account_test():
            try:
                os.chmod(COOKIE_FILE, 0o600)
            except Exception:
                pass
            debuglog.write('cookie validation', 'online test passed')
            notify('YouTube 账号连接成功')
            xbmc.executebuiltin('Container.Refresh')
        else:
            debuglog.write('cookie validation', 'online test returned false')
            remove_cookie_file()
            notify('Cookie 已导入，但 YouTube 登录验证失败；请重新导出后再试', xbmcgui.NOTIFICATION_ERROR)
    except Exception as exc:
        log_error('cookie validation failed', exc)
        remove_cookie_file()
        notify('Cookie 验证发生错误，请打开“诊断信息”查看详情', xbmcgui.NOTIFICATION_ERROR)

    finish('files')


def account_status():
    if not account_ready():
        notify('当前没有可用的 YouTube 登录', xbmcgui.NOTIFICATION_WARNING)
        finish('files')
        return

    valid = False
    try:
        valid = client().account_test()
    except Exception as exc:
        log_error('account status check failed', exc)

    status = '当前 Cookie 登录验证有效。' if valid else '已找到 Cookie，但在线验证暂未通过。'
    choice = xbmcgui.Dialog().yesno('YouTube 账号', status + '\n\n是否移除当前账号？', yeslabel='移除账号', nolabel='保留')
    if choice:
        remove_cookie_file()
        notify('已移除 YouTube 登录')
        xbmc.executebuiltin('Container.Refresh')
    finish('files')


def show_diagnostics():
    text = debuglog.read_text()
    if not text:
        text = '暂无诊断记录。'
    body = '诊断日志路径：\n%s\n\n%s' % (DEBUG_LOG_FILE, text)
    xbmcgui.Dialog().textviewer('Andy YouTube 诊断信息', body)
    finish('files')


def search_prompt():
    q = xbmcgui.Dialog().input('搜索 YouTube', type=xbmcgui.INPUT_ALPHANUM)
    if not q:
        finish()
        return
    storage.add_search(q)
    xbmc.executebuiltin('Container.Update(%s)' % plugin_url(action='search', q=q))


def do_search(params):
    q = params.get('q', '')
    if not q:
        return search_prompt()
    render_result(client().search(q, continuation=params.get('continuation')), 'search', {'q': q})


def do_trending(params):
    render_result(client().trending(continuation=params.get('continuation')), 'trending', {})


def do_subscriptions(params):
    result = client().subscriptions(continuation=params.get('continuation'))
    render_result(result, 'subscriptions', {})


def do_channel(params):
    cid = params.get('channel_id', '')
    if not cid:
        notify('缺少频道 ID', xbmcgui.NOTIFICATION_ERROR)
        finish()
        return
    result = client().channel_videos(cid, continuation=params.get('continuation'))
    render_result(result, 'channel', {'channel_id': cid, 'title': params.get('title', '')})


def show_favorites():
    for item in storage.get_favorites():
        add_video(item)
    finish()


def show_history():
    for item in storage.get_history():
        add_video(item)
    finish()


def show_search_history():
    for q in storage.get_searches():
        add_folder(q, 'search', q=q, context=[('删除这条记录', 'RunPlugin(%s)' % plugin_url(action='remove_search', q=q))])
    finish('files')


def open_url_prompt():
    value = xbmcgui.Dialog().input('粘贴 YouTube 视频或 Shorts 链接', type=xbmcgui.INPUT_ALPHANUM)
    if not value:
        finish()
        return
    vid = YouTubeClient.extract_video_id(value)
    if not vid:
        notify('没有识别到 YouTube 视频 ID', xbmcgui.NOTIFICATION_ERROR)
        finish()
        return
    xbmc.executebuiltin('PlayMedia(%s)' % plugin_url(action='play', video_id=vid, title='YouTube'))
    finish()


def route():
    params = dict(parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 else {}
    action = params.get('action', 'home')
    try:
        if action == 'home':
            show_home()
        elif action == 'import_cookies':
            import_cookies()
        elif action == 'account_status':
            account_status()
        elif action == 'diagnostics':
            show_diagnostics()
        elif action == 'subscriptions':
            do_subscriptions(params)
        elif action == 'search_prompt':
            search_prompt()
        elif action == 'search':
            do_search(params)
        elif action == 'trending':
            do_trending(params)
        elif action == 'channel':
            do_channel(params)
        elif action == 'favorites':
            show_favorites()
        elif action == 'history':
            show_history()
        elif action == 'search_history':
            show_search_history()
        elif action == 'open_url_prompt':
            open_url_prompt()
        elif action == 'play':
            item = {'video_id': params.get('video_id', ''), 'title': params.get('title', ''), 'channel': params.get('channel', ''), 'thumbnail': params.get('thumbnail', '')}
            storage.add_history(item)
            play_video(HANDLE, item['video_id'], ADDON, COOKIE_FILE)
        elif action == 'add_favorite':
            storage.add_favorite(params)
            notify('已加入我喜欢')
            xbmc.executebuiltin('Container.Refresh')
        elif action == 'remove_favorite':
            storage.remove_favorite(params.get('video_id', ''))
            notify('已移出我喜欢')
            xbmc.executebuiltin('Container.Refresh')
        elif action == 'remove_search':
            storage.remove_search(params.get('q', ''))
            xbmc.executebuiltin('Container.Refresh')
        elif action == 'settings':
            ADDON.openSettings()
            finish('files')
        else:
            show_home()
    except YouTubeError as exc:
        log_error('YouTube error', exc)
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        finish()
    except Exception as exc:
        log_error('unexpected', exc)
        notify('发生错误，请打开“诊断信息”查看详情', xbmcgui.NOTIFICATION_ERROR)
        finish()


if __name__ == '__main__':
    route()
