"""Dateibasierter JSON-Store mit plattformübergreifendem Lock.

Scheduler-Loop und Webserver sind zwei getrennte Prozesse, die sich
dieselben JSON-Dateien (jobs.json, settings.json) teilen. JsonFileStore
serialisiert Zugriffe über einen Datei-Lock, damit read-modify-write nie
Updates verliert.

Zielplattform ist Linux (siehe README/Dockerfile), daher fcntl.flock. Für
lokale Entwicklung/Tests unter Windows gibt es einen msvcrt-Fallback.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from typing import Any, Callable

try:
    import fcntl

    def _lock(fh, exclusive: bool) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)

    def _unlock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

except ImportError:  # pragma: no cover - Windows-Entwicklungsfallback
    import msvcrt

    def _lock(fh, exclusive: bool) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


class JsonFileStore:
    """Generischer JSON-Store mit Cross-Prozess-Lock über eine .lock-Datei.

    Ein zusätzlicher In-Prozess-Lock (threading.Lock) sichert zusätzlich
    gegen Races zwischen Threads desselben Prozesses ab (z. B. mehrere
    Gunicorn-Threads), da flock innerhalb eines Prozesses reentrant ist und
    sich Threads sonst gegenseitig nicht blockieren würden.
    """

    def __init__(self, path: str, default: Any = None) -> None:
        self.path = path
        self._default = default if default is not None else {}
        self._thread_lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        if not os.path.exists(path):
            self._write_atomic(self._default)

    def _lock_path(self) -> str:
        return self.path + ".lock"

    @contextmanager
    def _locked(self, exclusive: bool):
        with open(self._lock_path(), "a+") as lock_fh:
            if lock_fh.tell() == 0:
                lock_fh.write(" ")
                lock_fh.flush()
            _lock(lock_fh, exclusive)
            try:
                yield
            finally:
                _unlock(lock_fh)

    def _read_unlocked(self) -> Any:
        if not os.path.exists(self.path):
            return self._default
        with open(self.path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
            if not content:
                return self._default
            return json.loads(content)

    def _write_atomic(self, data: Any) -> None:
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def read(self) -> Any:
        with self._thread_lock, self._locked(exclusive=False):
            return self._read_unlocked()

    def modify(self, fn: Callable[[Any], Any]) -> Any:
        """Liest, wendet fn(data) -> data an und schreibt atomar zurück.

        fn darf die übergebene Struktur in-place verändern und/oder ein
        neues Objekt zurückgeben; der Rückgabewert wird persistiert.
        Gibt die gespeicherte Struktur zurück.
        """
        with self._thread_lock, self._locked(exclusive=True):
            data = self._read_unlocked()
            result = fn(data)
            if result is None:
                result = data
            self._write_atomic(result)
            return result
