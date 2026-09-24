"""SQLite's first WAL transition can fail before its busy timeout is used."""
import sqlite3
from unittest.mock import Mock

import pytest

from app.management import store


def failure(code):
    error = sqlite3.OperationalError('simulated initialization error')
    error.sqlite_errorcode = code
    return error


def test_concurrent_wal_transition_retries_only_busy(monkeypatch):
    db = Mock()
    journal = Mock()
    journal.fetchone.return_value = ('delete',)
    db.execute.side_effect = [journal, failure(sqlite3.SQLITE_BUSY), journal, Mock()]
    sleep = Mock()
    monkeypatch.setattr(store.time, 'sleep', sleep)
    store.enable_wal(db)
    assert db.execute.call_count == 4
    sleep.assert_called_once_with(0.02)


def test_storage_errors_are_not_silently_retried(monkeypatch):
    db, sleep = Mock(), Mock()
    db.execute.side_effect = failure(sqlite3.SQLITE_IOERR)
    monkeypatch.setattr(store.time, 'sleep', sleep)
    with pytest.raises(sqlite3.OperationalError):
        store.enable_wal(db)
    sleep.assert_not_called()


def test_busy_retry_has_a_deadline(monkeypatch):
    db = Mock()
    db.execute.side_effect = failure(sqlite3.SQLITE_BUSY)
    monkeypatch.setattr(store.time, 'monotonic', Mock(side_effect=[10, 11, 16]))
    monkeypatch.setattr(store.time, 'sleep', Mock())
    with pytest.raises(sqlite3.OperationalError):
        store.enable_wal(db)
    assert db.execute.call_count == 2
