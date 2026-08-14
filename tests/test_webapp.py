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


def test_sendungen_shows_suggestion(client):
    response = client.get("/sendungen")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Der Blaue Planet" in body
    assert "Vorschlag" in body


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
