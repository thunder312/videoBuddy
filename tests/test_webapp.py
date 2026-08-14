from datetime import datetime, timedelta, timezone

import pytest

from oerr_pvr import epg
from oerr_pvr.epg import EpgEntry
from oerr_pvr.webapp import create_app


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
