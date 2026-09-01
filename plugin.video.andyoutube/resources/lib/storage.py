# -*- coding: utf-8 -*-
import json
import os

import xbmcvfs
import xbmcaddon

ADDON = xbmcaddon.Addon()
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
FAVORITES = os.path.join(PROFILE, 'favorites.json')
HISTORY = os.path.join(PROFILE, 'history.json')
SEARCHES = os.path.join(PROFILE, 'searches.json')


def _ensure():
    if not xbmcvfs.exists(PROFILE):
        xbmcvfs.mkdirs(PROFILE)


def _load(path, default):
    _ensure()
    if not xbmcvfs.exists(path):
        return default
    try:
        f = xbmcvfs.File(path)
        data = f.read()
        f.close()
        return json.loads(data) if data else default
    except Exception:
        return default


def _save(path, data):
    _ensure()
    f = xbmcvfs.File(path, 'w')
    f.write(json.dumps(data, ensure_ascii=False, indent=2))
    f.close()


def _item(raw):
    return {
        'video_id': raw.get('video_id', ''),
        'title': raw.get('title', ''),
        'channel': raw.get('channel', ''),
        'channel_id': raw.get('channel_id', ''),
        'thumbnail': raw.get('thumbnail', ''),
        'description': raw.get('description', ''),
        'type': 'video',
    }


def get_favorites():
    return _load(FAVORITES, [])


def is_favorite(video_id):
    return any(x.get('video_id') == video_id for x in get_favorites())


def add_favorite(raw):
    item = _item(raw)
    if not item['video_id']:
        return
    items = [x for x in get_favorites() if x.get('video_id') != item['video_id']]
    items.insert(0, item)
    _save(FAVORITES, items[:500])


def remove_favorite(video_id):
    _save(FAVORITES, [x for x in get_favorites() if x.get('video_id') != video_id])


def get_history():
    return _load(HISTORY, [])


def add_history(raw):
    item = _item(raw)
    if not item['video_id']:
        return
    items = [x for x in get_history() if x.get('video_id') != item['video_id']]
    items.insert(0, item)
    _save(HISTORY, items[:200])


def get_searches():
    return _load(SEARCHES, [])


def add_search(q):
    q = (q or '').strip()
    if not q:
        return
    items = [x for x in get_searches() if x != q]
    items.insert(0, q)
    _save(SEARCHES, items[:50])


def remove_search(q):
    _save(SEARCHES, [x for x in get_searches() if x != q])
