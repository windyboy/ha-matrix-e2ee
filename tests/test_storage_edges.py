"""Storage error-path tests."""

from __future__ import annotations

import json
import os

import pytest

from custom_components.matrix_e2ee.storage import (
    MatrixSession,
    SessionError,
    atomic_save_session,
    load_session,
    quarantine_session,
    quarantine_store,
    session_path,
    store_path,
)


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2, 3],
        {"version": 999},
        {"version": 1, "user_id": "@bot:example.org"},
    ],
)
def test_load_session_rejects_invalid_session_schema(tmp_path, payload) -> None:
    """Session files must be objects with a supported, complete schema."""
    path = session_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SessionError):
        load_session(tmp_path)


def test_atomic_save_session_removes_temporary_file_on_write_error(
    tmp_path, monkeypatch
) -> None:
    """A failed atomic write must not leave its temporary file behind."""
    session = MatrixSession(1, "@bot:example.org", "DEVICE", "token", "pickle")

    def raise_os_error(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fdopen", raise_os_error)

    with pytest.raises(OSError, match="disk full"):
        atomic_save_session(tmp_path, session)

    assert list(session_path(tmp_path).parent.glob("session.*.tmp")) == []


def test_quarantine_missing_paths_are_noops(tmp_path) -> None:
    """Quarantine operations do nothing when their source artifact is absent."""
    quarantine_session(tmp_path)
    quarantine_store(tmp_path)
    assert not session_path(tmp_path).exists()
    assert not store_path(tmp_path).exists()
