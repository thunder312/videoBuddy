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
    assert not file_path.exists()


def test_process_uploading_failure_keeps_file_and_marks_failed(make_config, tmp_path, monkeypatch):
    config = make_config()
    job = scheduler.create_job(config, "ard.de", "Tatort", START, END, 3, 12)
    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    job = scheduler.update_job(
        config, job["id"], status="uploading", file_path=str(file_path)
    )

    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(main.dropbox_upload, "upload_file", _boom)

    main._process_uploading(config, job)

    updated = scheduler.get_job(config, job["id"])
    assert updated["status"] == "failed"
    assert "network down" in updated["error"]
    assert file_path.exists()
