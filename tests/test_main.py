from datetime import datetime, timedelta, timezone

from videobuddy import main, scheduler

START = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
END = START + timedelta(minutes=90)


def _make_recorded_job(make_config, tmp_path, mediathek_check_due):
    config = make_config()
    job = scheduler.create_job(config, "ard.de", "Tatort", START, END, 3, 12)
    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    job = scheduler.update_job(
        config,
        job["id"],
        status="recorded",
        file_path=str(file_path),
        recorded_at=START.isoformat(),
        mediathek_check_due=mediathek_check_due.isoformat(),
    )
    return config, job, file_path


def test_process_recorded_marks_ready_and_flags_when_found_in_mediathek(
    make_config, tmp_path, monkeypatch
):
    """Kein Automatismus mehr - ein Mediathek-Fund loescht die Datei nicht,
    sondern setzt nur den found_in_mediathek-Marker fuer die Weboberflaeche.
    Die Entscheidung (Hochladen/Loeschen) bleibt beim Nutzer."""
    config, job, file_path = _make_recorded_job(
        make_config, tmp_path, datetime.now(timezone.utc) - timedelta(hours=1)
    )
    monkeypatch.setattr(main.mediathek, "is_in_mediathek", lambda *a, **k: True)

    main._process_recorded(config, job, datetime.now(timezone.utc))

    updated = scheduler.get_job(config, job["id"])
    assert updated["status"] == "ready"
    assert updated["found_in_mediathek"] is True
    assert file_path.exists()


def test_process_recorded_marks_ready_when_not_found(make_config, tmp_path, monkeypatch):
    """Kein Automatismus mehr - eine nicht in der Mediathek gefundene
    Aufnahme wartet auf eine manuelle Hochladen/Löschen-Entscheidung."""
    config, job, file_path = _make_recorded_job(
        make_config, tmp_path, datetime.now(timezone.utc) - timedelta(hours=1)
    )
    monkeypatch.setattr(main.mediathek, "is_in_mediathek", lambda *a, **k: False)

    main._process_recorded(config, job, datetime.now(timezone.utc))

    updated = scheduler.get_job(config, job["id"])
    assert updated["status"] == "ready"
    assert updated["found_in_mediathek"] is False
    assert file_path.exists()


def test_process_recorded_noop_before_check_due(make_config, tmp_path):
    config, job, file_path = _make_recorded_job(
        make_config, tmp_path, datetime.now(timezone.utc) + timedelta(hours=1)
    )

    main._process_recorded(config, job, datetime.now(timezone.utc))

    updated = scheduler.get_job(config, job["id"])
    assert updated["status"] == "recorded"
    assert file_path.exists()


def test_process_uploading_success(make_config, tmp_path, monkeypatch):
    config = make_config()
    job = scheduler.create_job(config, "ard.de", "Tatort", START, END, 3, 12)
    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    job = scheduler.update_job(
        config, job["id"], status="uploading", file_path=str(file_path)
    )
    monkeypatch.setattr(
        main.dropbox_upload, "upload_file", lambda *a, **k: "/PVR-OeRR/recording.mkv"
    )

    main._process_uploading(config, job)

    updated = scheduler.get_job(config, job["id"])
    assert updated["status"] == "uploaded"
    # Datei bleibt nach dem Upload bewusst erhalten (manuelles Loeschen ueber
    # die Weboberflaeche), damit "Direkt" auch nach dem Dropbox-Upload noch
    # verfuegbar ist.
    assert file_path.exists()


def test_process_uploading_persists_progress_and_clears_it_on_success(
    make_config, tmp_path, monkeypatch
):
    config = make_config()
    job = scheduler.create_job(config, "ard.de", "Tatort", START, END, 3, 12)
    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    job = scheduler.update_job(
        config, job["id"], status="uploading", file_path=str(file_path)
    )

    seen_mid_upload = {}

    def fake_upload(path, dropbox_config, on_progress=None, **kwargs):
        on_progress(500, 1000)
        seen_mid_upload.update(scheduler.get_job(config, job["id"]))
        return "/PVR-OeRR/recording.mkv"

    monkeypatch.setattr(main.dropbox_upload, "upload_file", fake_upload)

    main._process_uploading(config, job)

    assert seen_mid_upload["upload_progress"] == 500
    assert seen_mid_upload["upload_total"] == 1000

    updated = scheduler.get_job(config, job["id"])
    assert updated["status"] == "uploaded"
    assert updated["upload_progress"] is None
    assert updated["upload_total"] is None


def test_process_uploading_failure_keeps_file_and_marks_failed(make_config, tmp_path, monkeypatch):
    config = make_config()
    job = scheduler.create_job(config, "ard.de", "Tatort", START, END, 3, 12)
    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    job = scheduler.update_job(
        config, job["id"], status="uploading", file_path=str(file_path)
    )

    def _boom(*a, on_progress=None, **k):
        if on_progress is not None:
            on_progress(500, 1000)
        raise RuntimeError("network down")

    monkeypatch.setattr(main.dropbox_upload, "upload_file", _boom)

    main._process_uploading(config, job)

    updated = scheduler.get_job(config, job["id"])
    assert updated["status"] == "failed"
    assert "network down" in updated["error"]
    assert file_path.exists()
    assert updated["upload_progress"] is None
    assert updated["upload_total"] is None
