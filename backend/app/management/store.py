"""Durable single-master management state. No credentials enter audit records."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from ..core.config import settings
from ..core.exceptions import AppError

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
 id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, secret_hash TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', room_id TEXT NOT NULL DEFAULT '',
 config TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 reported_revision INTEGER NOT NULL DEFAULT 0, metadata TEXT NOT NULL DEFAULT '{}',
 last_seen INTEGER NOT NULL, created_at INTEGER NOT NULL, error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS history (
 device_id TEXT NOT NULL, revision INTEGER NOT NULL, value TEXT NOT NULL,
 PRIMARY KEY(device_id, revision));
CREATE TABLE IF NOT EXISTS users (
 subject TEXT PRIMARY KEY, tenant TEXT NOT NULL, name TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
 digest TEXT PRIMARY KEY, subject TEXT NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS oauth (
 state TEXT PRIMARY KEY, verifier TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, time INTEGER NOT NULL, actor TEXT NOT NULL,
 action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS templates (id TEXT PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL);
"""
DEFAULT_CONFIG = {'version': 'v6', 'portrait': False, 'room_light': True, 'node_id': 'central', 'reload': 0,
                  'theme_mode': 'auto', 'language': 'zh-CN', 'device_profile': 'auto'}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def database():
    if not settings.ROOM_DISPLAY_V6_DB:
        raise AppError(503, 'V6 管理服务尚未配置', 503)
    path = Path(settings.ROOM_DISPLAY_V6_DB)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=5000')
        db.executescript(SCHEMA)
        db.execute("INSERT OR IGNORE INTO meta VALUES ('signing_key', ?)", (secrets.token_hex(32),))
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except sqlite3.Error as exc:
        db.rollback()
        raise AppError(503, '设备管理存储暂不可用', 503) from exc
    finally:
        db.close()


def audit(db, actor, action, target, detail=None):
    db.execute('INSERT INTO audit(time,actor,action,target,detail) VALUES (?,?,?,?,?)',
               (int(time.time()), actor, action, target, json.dumps(detail or {}, ensure_ascii=False)))


def rate_limit(key, maximum=30, window=60):
    now = int(time.time())
    with database() as db:
        db.execute('DELETE FROM limits WHERE expires < ?', (now,))
        row = db.execute('SELECT count FROM limits WHERE key=?', (key,)).fetchone()
        if row and row['count'] >= maximum:
            raise AppError(429, '请求过于频繁，请稍后重试', 429)
        db.execute('INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',
                   (key, now + window))


def device_view(row):
    value = dict(row)
    value.pop('secret_hash', None)
    value['metadata'] = json.loads(value['metadata'])
    value['config'] = DEFAULT_CONFIG | json.loads(value['config'])
    value['online'] = time.time() - value['last_seen'] < 60
    return value


def save_history(db, row):
    value = {'config': json.loads(row['config']), 'room_id': row['room_id'], 'status': row['status']}
    db.execute('INSERT INTO history VALUES (?,?,?)', (row['id'], row['revision'], json.dumps(value)))
