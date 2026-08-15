from videobuddy import dropbox_upload
from videobuddy.config import DropboxConfig


class _FakeSessionStart:
    session_id = "sess-1"


class _FakeClient:
    def __init__(self, **kwargs):
        pass

    def files_upload(self, data, path, mode):
        pass

    def files_upload_session_start(self, data):
        return _FakeSessionStart()

    def files_upload_session_append_v2(self, data, cursor):
        pass

    def files_upload_session_finish(self, data, cursor, commit):
        pass


def test_upload_file_small_reports_start_and_end(tmp_path, monkeypatch):
    """Datei <= CHUNK_SIZE geht über den files_upload-Einzelrequest - kein
    Zwischenfortschritt möglich, aber on_progress meldet zumindest 0% und 100%."""
    monkeypatch.setattr(dropbox_upload.dropbox, "Dropbox", lambda **kwargs: _FakeClient())
    path = tmp_path / "small.ts"
    path.write_bytes(b"x" * 100)
    calls = []

    dropbox_upload.upload_file(
        str(path),
        DropboxConfig(refresh_token="t", app_key="k", app_secret="s"),
        on_progress=lambda uploaded, total: calls.append((uploaded, total)),
    )

    assert calls == [(0, 100), (100, 100)]


def test_upload_file_chunked_reports_progress_per_chunk(tmp_path, monkeypatch):
    monkeypatch.setattr(dropbox_upload.dropbox, "Dropbox", lambda **kwargs: _FakeClient())
    monkeypatch.setattr(dropbox_upload, "CHUNK_SIZE", 10)
    path = tmp_path / "big.ts"
    path.write_bytes(b"x" * 35)
    calls = []

    dropbox_upload.upload_file(
        str(path),
        DropboxConfig(refresh_token="t", app_key="k", app_secret="s"),
        on_progress=lambda uploaded, total: calls.append((uploaded, total)),
    )

    assert calls == [(0, 35), (10, 35), (20, 35), (30, 35), (35, 35)]


def test_upload_file_without_on_progress_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(dropbox_upload.dropbox, "Dropbox", lambda **kwargs: _FakeClient())
    monkeypatch.setattr(dropbox_upload, "CHUNK_SIZE", 10)
    path = tmp_path / "big.ts"
    path.write_bytes(b"x" * 35)

    remote_path = dropbox_upload.upload_file(
        str(path), DropboxConfig(refresh_token="t", app_key="k", app_secret="s")
    )

    assert remote_path == "/PVR-OeRR/big.ts"
