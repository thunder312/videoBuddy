"""Lädt eine Aufnahme zu Dropbox hoch, wenn sie nicht in der Mediathek
gefunden wurde (siehe README-Architekturdiagramm).

Chunked Upload-Session statt files_upload() in einem Rutsch, weil Aufnahmen
laut README ("Speicherbedarf im Blick behalten") leicht mehrere GB groß sind
- deutlich über dem 150-MB-Limit für Dropbox-Einzelrequests. Nicht gegen
einen echten Account getestet (siehe README "Offene Punkte" Punkt 4 /
"Nicht getestet")."""

from __future__ import annotations

import os
from typing import Callable

import dropbox
from dropbox.files import CommitInfo, UploadSessionCursor, WriteMode

from .config import DropboxConfig

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def upload_file(
    local_path: str,
    dropbox_config: DropboxConfig,
    remote_filename: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> str:
    """Lädt local_path per Chunked-Upload hoch, gibt den Dropbox-Zielpfad
    zurück. on_progress(bytes_uploaded, total_bytes) wird nach jedem Chunk
    aufgerufen - erlaubt dem Aufrufer (main.py), den Fortschritt in
    jobs.json mitzuschreiben, damit die Weboberfläche ihn anzeigen kann."""
    remote_filename = remote_filename or os.path.basename(local_path)
    remote_path = f"{dropbox_config.upload_folder.rstrip('/')}/{remote_filename}"

    client = dropbox.Dropbox(
        oauth2_refresh_token=dropbox_config.refresh_token,
        app_key=dropbox_config.app_key,
        app_secret=dropbox_config.app_secret,
    )

    file_size = os.path.getsize(local_path)

    def _report(uploaded: int) -> None:
        if on_progress is not None:
            on_progress(uploaded, file_size)

    with open(local_path, "rb") as fh:
        if file_size <= CHUNK_SIZE:
            _report(0)
            client.files_upload(fh.read(), remote_path, mode=WriteMode.overwrite)
            _report(file_size)
            return remote_path

        _report(0)
        session_start = client.files_upload_session_start(fh.read(CHUNK_SIZE))
        cursor = UploadSessionCursor(
            session_id=session_start.session_id, offset=fh.tell()
        )
        _report(fh.tell())

        while file_size - fh.tell() > CHUNK_SIZE:
            client.files_upload_session_append_v2(fh.read(CHUNK_SIZE), cursor)
            cursor.offset = fh.tell()
            _report(fh.tell())

        commit = CommitInfo(path=remote_path, mode=WriteMode.overwrite)
        client.files_upload_session_finish(fh.read(), cursor, commit)
        _report(file_size)

    return remote_path
