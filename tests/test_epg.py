import os
from datetime import datetime, timezone

from videobuddy.epg import parse_xmltv

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_epg.xml")


def _load_entries():
    with open(FIXTURE_PATH, "rb") as fh:
        return parse_xmltv(fh.read())


def test_parse_xmltv_returns_all_programmes():
    entries = _load_entries()
    assert len(entries) == 3
    assert [e.title for e in entries] == ["Tatort", "Der Blaue Planet", "Tagesschau"]


def test_parse_xmltv_converts_timezone_to_utc():
    entries = _load_entries()
    tatort = entries[0]
    # 20:00 +0100 lokal == 19:00 UTC
    assert tatort.start == datetime(2026, 1, 1, 19, 0, tzinfo=timezone.utc)
    assert tatort.stop == datetime(2026, 1, 1, 20, 30, tzinfo=timezone.utc)


def test_parse_xmltv_duration_minutes():
    entries = _load_entries()
    tatort, blauer_planet, tagesschau = entries
    assert tatort.duration_minutes == 90
    assert blauer_planet.duration_minutes == 120
    assert tagesschau.duration_minutes == 15


def test_parse_xmltv_categories_and_channel():
    entries = _load_entries()
    tatort = entries[0]
    assert tatort.channel == "ard.de"
    assert tatort.categories == ["Krimi"]
    assert tatort.description == "Ein Krimi."
