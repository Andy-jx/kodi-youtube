# -*- coding: utf-8 -*-
import datetime
import os
import traceback

_LOG_PATH = ''
_MAX_BYTES = 1024 * 1024


def configure(path):
    global _LOG_PATH
    _LOG_PATH = path or ''


def path():
    return _LOG_PATH


def _rotate_if_needed():
    if not _LOG_PATH or not os.path.exists(_LOG_PATH):
        return
    try:
        if os.path.getsize(_LOG_PATH) <= _MAX_BYTES:
            return
        old = _LOG_PATH + '.old'
        if os.path.exists(old):
            os.remove(old)
        os.replace(_LOG_PATH, old)
    except Exception:
        pass


def write(event, detail=''):
    if not _LOG_PATH:
        return
    try:
        folder = os.path.dirname(_LOG_PATH)
        if folder:
            os.makedirs(folder, exist_ok=True)
        _rotate_if_needed()
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = '[%s] %s' % (stamp, event)
        if detail:
            line += ' | ' + str(detail)
        with open(_LOG_PATH, 'a', encoding='utf-8', errors='replace') as fh:
            fh.write(line + '\n')
    except Exception:
        pass


def exception(event, exc):
    detail = '%r\n%s' % (exc, traceback.format_exc())
    write(event, detail)


def read_text():
    if not _LOG_PATH or not os.path.exists(_LOG_PATH):
        return ''
    try:
        with open(_LOG_PATH, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except Exception as exc:
        return '无法读取诊断日志: %r' % exc


def clear():
    if not _LOG_PATH:
        return
    try:
        with open(_LOG_PATH, 'w', encoding='utf-8') as fh:
            fh.write('')
    except Exception:
        pass
