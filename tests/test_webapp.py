import os
from datetime import datetime, timedelta, timezone

import pytest

from videobuddy import epg
from videobuddy.epg import EpgEntry
from videobuddy.webapp import create_app


@pytest.fixture
def client(make_config, monkeypatch):
    config = make_config()

    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    fake_entries = [
        EpgEntry(
            channel="ard.de",
            title="Der Blaue Planet",
            start=future_start,
            stop=future_start + timedelta(minutes=90),
            categories=["Spielfilm"],
            description="",
        )
    ]
    monkeypatch.setattr(epg, "fetch_epg", lambda urls: fake_entries)

    app = create_app(config)
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        test_client.app_config = config
        yield test_client


def test_dashboard_empty(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Noch keine Aufnahmen geplant" in response.get_data(as_text=True)


def test_dashboard_shows_compact_time_range_even_across_midnight(client):
    """Sendezeit zeigt das Datum nur einmal (erste Zeile), Uhrzeiten in der
    zweiten Zeile - auch wenn die Sendung ueber Mitternacht laeuft."""
    from videobuddy import scheduler

    config = client.app_config
    start = datetime(2026, 8, 15, 21, 0, tzinfo=timezone.utc)  # 23:00 Berlin (15.08.)
    end = datetime(2026, 8, 15, 23, 0, tzinfo=timezone.utc)  # 01:00 Berlin (16.08.!)
    scheduler.create_job(config, "ard.de", "Nachtfilm", start, end, 3, 12)

    body = client.get("/").get_data(as_text=True)
    # Nur das Start-Datum (15.08.), obwohl die Sendung nach Berliner Zeit
    # erst am 16.08. endet.
    assert "15.08.2026<br>23:00 - 01:00" in body


def test_sendungen_shows_suggestion(client):
    response = client.get("/sendungen")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Der Blaue Planet" in body
    assert "Vorschlag" in body


def test_sendungen_titel_expands_epg_description(client, monkeypatch):
    """Der Titel wird zu einem <details>/<summary> statt einem Mouseover-
    Tooltip verpackt, wenn der EPG-Feed eine Beschreibung liefert - das
    funktioniert per Tap genauso wie per Klick, ganz ohne JavaScript."""
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    entries = [
        EpgEntry(
            channel="ard.de",
            title="Der talentierte Mr. Ripley",
            start=future_start,
            stop=future_start + timedelta(minutes=90),
            categories=["Spielfilm"],
            description="Ein Hochstapler gibt sich als reicher Erbe aus.",
        )
    ]
    monkeypatch.setattr(epg, "fetch_epg", lambda urls: entries)

    body = client.get("/sendungen").get_data(as_text=True)

    assert "<summary>Der talentierte Mr. Ripley</summary>" in body
    assert "Ein Hochstapler gibt sich als reicher Erbe aus." in body


def test_sendungen_titel_plain_without_epg_description(client):
    # Der Fixture-Eintrag hat description="" - siehe client-Fixture oben.
    # <summary> kommt trotzdem vor (einklappbarer Filterblock), nur nicht
    # als <details class="plot"> fuer den Titel.
    body = client.get("/sendungen").get_data(as_text=True)
    assert '<details class="plot">' not in body
    assert "Der Blaue Planet" in body


def test_sendungen_zeit_filter(client, monkeypatch):
    """Tageszeit-Filter ist datumsunabhaengig - filtert nach der Uhrzeit in
    Berliner Zeit, nicht nach absoluten Zeitstempeln."""
    day = datetime(2026, 8, 20, tzinfo=timezone.utc)
    morning = day.replace(hour=6, minute=0)  # 08:00 Berlin (CEST, +2h)
    evening = day.replace(hour=19, minute=0)  # 21:00 Berlin
    entries = [
        EpgEntry(
            channel="ard.de", title="Morgenmagazin", start=morning,
            stop=morning + timedelta(minutes=30), categories=[], description="",
        ),
        EpgEntry(
            channel="ard.de", title="Spaetfilm", start=evening,
            stop=evening + timedelta(minutes=90), categories=[], description="",
        ),
    ]
    monkeypatch.setattr(epg, "fetch_epg", lambda urls: entries)

    body = client.get("/sendungen?zeit_von=20:00&zeit_bis=23:00").get_data(as_text=True)
    assert "Spaetfilm" in body
    assert "Morgenmagazin" not in body


def test_sendungen_textsuche(client, monkeypatch):
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    entries = [
        EpgEntry(
            channel="ard.de", title="Tatort", start=future_start,
            stop=future_start + timedelta(minutes=90), categories=[], description="",
        ),
        EpgEntry(
            channel="zdf.de", title="Der Alte", start=future_start,
            stop=future_start + timedelta(minutes=90), categories=[], description="",
        ),
    ]
    monkeypatch.setattr(epg, "fetch_epg", lambda urls: entries)

    body = client.get("/sendungen?suche=tatort").get_data(as_text=True)  # klein geschrieben
    assert "Tatort" in body
    assert "Der Alte" not in body


def test_sendungen_shows_eingeplant_for_already_scheduled_candidate(client, monkeypatch):
    """Nach dem Einplanen zeigt "Sendungen wählen" fuer diese Sendung
    "Eingeplant" statt "Aufnehmen" - auch nach einem echten Reload, nicht
    nur direkt nach dem JS-Klick."""
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    entries = [
        EpgEntry(
            channel="ard.de", title="Der Blaue Planet", start=start, stop=end,
            categories=[], description="",
        )
    ]
    monkeypatch.setattr(epg, "fetch_epg", lambda urls: entries)

    scheduler.create_job(config, "ard.de", "Der Blaue Planet", start, end, 3, 12)

    body = client.get("/sendungen").get_data(as_text=True)
    assert "Eingeplant" in body
    assert ">Aufnehmen<" not in body


def test_aufnehmen_via_fetch_returns_204_without_redirect(client):
    """Der JS-Klick-Handler schickt den Request mit diesem Header - die
    Route soll dann nur 204 liefern, ohne Flash/Redirect, damit die Seite
    nicht neu laedt und die Scrollposition erhalten bleibt."""
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    future_end = future_start + timedelta(minutes=90)

    response = client.post(
        "/sendungen/aufnehmen",
        data={
            "channel": "ard.de",
            "title": "Der Blaue Planet",
            "epg_start": future_start.isoformat(),
            "epg_end": future_end.isoformat(),
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 204
    assert response.get_data() == b""

    dashboard = client.get("/")
    assert "Der Blaue Planet" in dashboard.get_data(as_text=True)


def test_aufnehmen_then_dashboard_shows_job(client):
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    future_end = future_start + timedelta(minutes=90)

    response = client.post(
        "/sendungen/aufnehmen",
        data={
            "channel": "ard.de",
            "title": "Der Blaue Planet",
            "epg_start": future_start.isoformat(),
            "epg_end": future_end.isoformat(),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    dashboard = client.get("/")
    assert "Der Blaue Planet" in dashboard.get_data(as_text=True)
    assert "geplant" in dashboard.get_data(as_text=True)


def test_cancel_job(client):
    import re

    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    future_end = future_start + timedelta(minutes=90)
    client.post(
        "/sendungen/aufnehmen",
        data={
            "channel": "ard.de",
            "title": "Der Blaue Planet",
            "epg_start": future_start.isoformat(),
            "epg_end": future_end.isoformat(),
        },
    )

    dashboard = client.get("/").get_data(as_text=True)
    match = re.search(r"/jobs/([0-9a-f]+)/cancel", dashboard)
    assert match, "Stornieren-Formular nicht im Dashboard gefunden"
    job_id = match.group(1)

    response = client.post(f"/jobs/{job_id}/cancel", follow_redirects=True)
    assert response.status_code == 200
    assert "storniert" in response.get_data(as_text=True)


def test_einstellungen_get_shows_channels(client):
    response = client.get("/einstellungen")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ard.de" in body
    assert "zdf.de" in body


def test_einstellungen_genre_dropdown_lists_epg_categories(client):
    """Genres fuer das Dropdown kommen direkt aus den EPG-Daten (siehe
    client-Fixture: categories=["Spielfilm"]), nicht aus einer fest
    hinterlegten Liste."""
    body = client.get("/einstellungen").get_data(as_text=True)
    assert '<option value="Spielfilm">Spielfilm</option>' in body


def test_einstellungen_genre_group_dropdown_lists_curated_groups(client):
    """Zweites Dropdown zeigt die kuratierten Genre-Gruppen aus
    genre_groups.py (z. B. "Sci-Fi"), unabhaengig von den aktuell im EPG
    vorkommenden Rohdaten-Tags."""
    body = client.get("/einstellungen").get_data(as_text=True)
    assert '<option value="Sci-Fi">Sci-Fi</option>' in body
    assert 'id="genre-group-picker"' in body


def test_upload_and_delete_only_offered_for_ready_or_failed(client, tmp_path):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)

    # Frisch angelegt (status="scheduled") -> keine Hochladen/Löschen-Buttons
    dashboard = client.get("/").get_data(as_text=True)
    assert "Hochladen" not in dashboard
    assert "Löschen" not in dashboard

    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    scheduler.update_job(config, job["id"], status="ready", file_path=str(file_path))

    dashboard = client.get("/").get_data(as_text=True)
    assert "Hochladen" in dashboard
    assert "Löschen" in dashboard


def test_dashboard_status_filter(client):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    scheduled_job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    canceled_job = scheduler.create_job(
        config, "zdf.de", "Aktenzeichen XY", start + timedelta(hours=1), end + timedelta(hours=1), 3, 12
    )
    scheduler.cancel_job(config, canceled_job["id"])

    only_scheduled = client.get("/?status=scheduled").get_data(as_text=True)
    assert "Tatort" in only_scheduled
    assert "Aktenzeichen XY" not in only_scheduled

    only_canceled = client.get("/?status=canceled").get_data(as_text=True)
    assert "Aktenzeichen XY" in only_canceled
    assert "Tatort" not in only_canceled


def test_dashboard_hides_canceled_and_deleted_by_default(client, tmp_path):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)

    active_job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    canceled_job = scheduler.create_job(
        config, "zdf.de", "Aktenzeichen XY", start + timedelta(hours=1), end + timedelta(hours=1), 3, 12
    )
    scheduler.cancel_job(config, canceled_job["id"])

    deleted_job = scheduler.create_job(
        config, "zdf.de", "Geloeschte Show", start + timedelta(hours=2), end + timedelta(hours=2), 3, 12
    )
    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    scheduler.update_job(config, deleted_job["id"], status="ready", file_path=str(file_path))
    scheduler.update_job(config, deleted_job["id"], status="deleted")

    default_view = client.get("/").get_data(as_text=True)
    assert "Tatort" in default_view
    assert "Aktenzeichen XY" not in default_view
    assert "Geloeschte Show" not in default_view

    with_hidden = client.get("/?alle_status=1").get_data(as_text=True)
    assert "Tatort" in with_hidden
    assert "Aktenzeichen XY" in with_hidden
    assert "Geloeschte Show" in with_hidden

    # Gezielter Status-Filter zeigt storniert/gelöscht trotzdem, auch ohne Haken.
    explicit_status = client.get("/?status=canceled").get_data(as_text=True)
    assert "Aktenzeichen XY" in explicit_status


def test_dashboard_sort_by_titel_and_sender(client):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    scheduler.create_job(config, "zdf.de", "Zebra-Doku", start, end, 3, 12)
    scheduler.create_job(config, "ard.de", "Achterbahn", start, end, 3, 12)

    by_title = client.get("/?sortierung=titel").get_data(as_text=True)
    assert by_title.index("Achterbahn") < by_title.index("Zebra-Doku")

    by_sender = client.get("/?sortierung=sender").get_data(as_text=True)
    assert by_sender.index("ARD") < by_sender.index("ZDF")


def test_dashboard_default_sort_is_next_recording_first(client):
    """Standard-Sortierung zeigt die naechste anstehende Aufnahme zuerst -
    also aufsteigend nach Sendezeit, nicht mehr "neueste zuerst"."""
    from videobuddy import scheduler

    config = client.app_config
    soon = datetime.now(timezone.utc) + timedelta(hours=2)
    later = datetime.now(timezone.utc) + timedelta(days=3)
    scheduler.create_job(config, "ard.de", "Bald dran", soon, soon + timedelta(minutes=90), 3, 12)
    scheduler.create_job(config, "zdf.de", "Erst spaeter", later, later + timedelta(minutes=90), 3, 12)

    default_view = client.get("/").get_data(as_text=True)
    assert default_view.index("Bald dran") < default_view.index("Erst spaeter")


def test_upload_offered_and_works_for_recorded_status(client, tmp_path):
    """"Hochladen" soll nicht auf den (bis zu tagelangen) Mediathek-Check
    warten - die Datei ist direkt nach der Aufnahme schon vollstaendig."""
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    file_path = tmp_path / "recording.ts"
    file_path.write_text("fake video content")
    scheduler.update_job(config, job["id"], status="recorded", file_path=str(file_path))

    dashboard = client.get("/").get_data(as_text=True)
    assert f"/jobs/{job['id']}/upload" in dashboard

    response = client.post(f"/jobs/{job['id']}/upload", follow_redirects=True)
    assert response.status_code == 200
    assert scheduler.get_job(config, job["id"])["status"] == "uploading"


def test_upload_route_sets_uploading_status(client, tmp_path):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    scheduler.update_job(config, job["id"], status="ready", file_path=str(file_path))

    response = client.post(f"/jobs/{job['id']}/upload", follow_redirects=True)

    assert response.status_code == 200
    assert scheduler.get_job(config, job["id"])["status"] == "uploading"
    assert file_path.exists()  # Upload selbst laeuft im Scheduler-Loop, nicht hier


def test_delete_route_removes_file_and_marks_deleted(client, tmp_path):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    file_path = tmp_path / "recording.mkv"
    file_path.write_text("fake video content")
    scheduler.update_job(config, job["id"], status="ready", file_path=str(file_path))

    response = client.post(f"/jobs/{job['id']}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert scheduler.get_job(config, job["id"])["status"] == "deleted"
    assert not file_path.exists()


def test_direkt_and_delete_stay_available_after_upload(client, tmp_path):
    """"Direkt" und "Loeschen" bleiben verfuegbar, solange die Datei noch auf
    dem Server liegt - auch nach erfolgreichem Dropbox-Upload. "Hochladen"
    macht dagegen nur noch vor dem Upload Sinn."""
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    file_path = tmp_path / "recording.ts"
    file_path.write_text("fake video content")
    scheduler.update_job(config, job["id"], status="uploaded", file_path=str(file_path))

    body = client.get("/").get_data(as_text=True)
    assert f"/jobs/{job['id']}/direkt" in body
    assert f"/jobs/{job['id']}/delete" in body
    assert f"/jobs/{job['id']}/upload" not in body

    direkt_response = client.get(f"/jobs/{job['id']}/direkt")
    assert direkt_response.status_code == 200
    assert direkt_response.get_data() == b"fake video content"
    direkt_response.close()  # Dateihandle freigeben, bevor gleich geloescht wird

    delete_response = client.post(f"/jobs/{job['id']}/delete", follow_redirects=True)
    assert delete_response.status_code == 200
    assert scheduler.get_job(config, job["id"])["status"] == "deleted"
    assert not file_path.exists()


def test_dashboard_shows_file_size(client, tmp_path):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    file_path = tmp_path / "recording.ts"
    file_path.write_bytes(b"x" * 2_000_000)  # ~2 MB
    scheduler.update_job(config, job["id"], status="ready", file_path=str(file_path))

    body = client.get("/").get_data(as_text=True)
    assert "1.9 MiB" in body or "2.0 MB" in body or "MiB" in body


def test_dashboard_no_upload_estimate_without_known_speed(client, tmp_path):
    """Ohne jemals einen erfolgreichen Upload gemessen zu haben, gibt es
    keine Zeitschaetzung - genau wie gewuenscht "dann lass die Zeit weg"."""
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    file_path = tmp_path / "recording.ts"
    file_path.write_bytes(b"x" * 2_000_000)
    scheduler.update_job(config, job["id"], status="ready", file_path=str(file_path))

    body = client.get("/").get_data(as_text=True)
    assert "<br><small>~" not in body


def test_dashboard_shows_estimated_upload_time_once_speed_known(client, tmp_path):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)

    # Ein bereits erfolgreich hochgeladener Job liefert die gemessene
    # Geschwindigkeit (500 KB/s), die fuer die Schaetzung genutzt wird.
    done_job = scheduler.create_job(config, "ard.de", "Schon hoch", start, end, 3, 12)
    scheduler.update_job(
        config,
        done_job["id"],
        status="uploaded",
        file_path=str(tmp_path / "done.ts"),
        upload_speed_bps=500_000,
        upload_speed_measured_at=datetime.now(timezone.utc).isoformat(),
    )

    pending_job = scheduler.create_job(config, "zdf.de", "Wartet noch", start, end, 3, 12)
    file_path = tmp_path / "pending.ts"
    file_path.write_bytes(b"x" * 1_000_000)  # 1 MB -> bei 500 KB/s ~2 Sek
    scheduler.update_job(config, pending_job["id"], status="ready", file_path=str(file_path))

    body = client.get("/").get_data(as_text=True)
    assert "~2 Sek" in body


def test_dashboard_shows_upload_progress_and_autorefresh(client, tmp_path):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    file_path = tmp_path / "recording.ts"
    file_path.write_text("fake video content")
    scheduler.update_job(
        config,
        job["id"],
        status="uploading",
        file_path=str(file_path),
        upload_progress=500_000,
        upload_total=1_000_000,
    )

    body = client.get("/").get_data(as_text=True)

    assert "50%" in body
    assert '<meta http-equiv="refresh" content="10">' in body


def test_dashboard_no_autorefresh_without_active_upload(client):
    body = client.get("/").get_data(as_text=True)
    assert "http-equiv=\"refresh\"" not in body


def test_direkt_route_streams_file_as_attachment(client, tmp_path):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)
    file_path = tmp_path / "recording.ts"
    file_path.write_text("fake video content")
    scheduler.update_job(config, job["id"], status="ready", file_path=str(file_path))

    response = client.get(f"/jobs/{job['id']}/direkt")

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment")
    assert "recording.ts" in response.headers["Content-Disposition"]
    assert response.get_data() == b"fake video content"


def test_direkt_route_resolves_relative_file_path_against_cwd(client):
    """Regression: mit einem relativen file_path (config.recording_dir z.B.
    "./recordings") loeste Flasks send_file() den Pfad faelschlich gegen
    current_app.root_path (das videobuddy-Paketverzeichnis) statt gegen das
    Arbeitsverzeichnis auf und warf FileNotFoundError - obwohl
    os.path.exists() denselben Pfad zuvor noch als vorhanden gemeldet
    hatte, weil os.path.exists() (anders als send_file) korrekt gegen das
    Arbeitsverzeichnis aufloest. Live auf Athene aufgetreten.

    Der Temp-Ordner wird bewusst direkt unters aktuelle Arbeitsverzeichnis
    gelegt (statt der tmp_path-Fixture) - nur so laesst sich ueberhaupt ein
    relativer Pfad dazu bilden (tmp_path kann auf einem anderen Laufwerk
    liegen als das Repo, das schlaegt unter Windows sonst mit
    "path is on mount ..." fehl)."""
    import shutil
    import tempfile

    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)

    tmp_dir = tempfile.mkdtemp(dir=os.getcwd())
    try:
        file_path = os.path.join(tmp_dir, "recording.ts")
        with open(file_path, "wb") as fh:
            fh.write(b"fake video content")
        relative_path = os.path.relpath(file_path, start=os.getcwd())
        scheduler.update_job(config, job["id"], status="ready", file_path=relative_path)

        response = client.get(f"/jobs/{job['id']}/direkt")

        assert response.status_code == 200
        assert response.get_data() == b"fake video content"
        response.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_direkt_route_rejected_for_scheduled_job(client):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)

    response = client.get(f"/jobs/{job['id']}/direkt", follow_redirects=True)

    assert response.status_code == 200
    assert scheduler.get_job(config, job["id"])["status"] == "scheduled"


def test_upload_and_delete_rejected_for_scheduled_job(client):
    from videobuddy import scheduler

    config = client.app_config
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(minutes=90)
    job = scheduler.create_job(config, "ard.de", "Tatort", start, end, 3, 12)

    client.post(f"/jobs/{job['id']}/upload")
    assert scheduler.get_job(config, job["id"])["status"] == "scheduled"

    client.post(f"/jobs/{job['id']}/delete")
    assert scheduler.get_job(config, job["id"])["status"] == "scheduled"


def test_einstellungen_post_saves_settings(client):
    response = client.post(
        "/einstellungen",
        data={
            "watched_channels": ["ard.de"],
            "film_keywords": "Spielfilm\nDokumentation",
            "min_duration_minutes": "80",
            "buffer_before_minutes": "5",
            "buffer_after_minutes": "15",
        },
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "80" in body
    assert "Dokumentation" in body
