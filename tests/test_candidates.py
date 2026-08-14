from datetime import datetime, timedelta, timezone

from videobuddy.candidates import build_candidates
from videobuddy.epg import EpgEntry

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

SETTINGS = {
    "watched_channels": ["ard.de"],
    "film_keywords": ["Spielfilm", "Fernsehfilm"],
    "min_duration_minutes": 70,
}


def _entry(**overrides) -> EpgEntry:
    defaults = dict(
        channel="ard.de",
        title="Tatort",
        start=NOW + timedelta(hours=2),
        stop=NOW + timedelta(hours=2, minutes=90),
        categories=["Krimi"],
        description="",
    )
    defaults.update(overrides)
    return EpgEntry(**defaults)


def test_filters_out_unwatched_channels():
    entries = [_entry(channel="zdf.de")]
    assert build_candidates(entries, SETTINGS, now=NOW) == []


def test_filters_out_past_programmes():
    entries = [_entry(start=NOW - timedelta(hours=1), stop=NOW - timedelta(minutes=30))]
    assert build_candidates(entries, SETTINGS, now=NOW) == []


def test_marks_suggestion_when_long_enough_and_keyword_in_category():
    entries = [_entry(categories=["Spielfilm"], stop=NOW + timedelta(hours=2, minutes=90))]
    candidates = build_candidates(entries, SETTINGS, now=NOW)
    assert len(candidates) == 1
    assert candidates[0].is_suggestion is True


def test_marks_suggestion_when_keyword_in_title():
    entries = [_entry(title="Der Spielfilm des Abends", categories=[])]
    candidates = build_candidates(entries, SETTINGS, now=NOW)
    assert candidates[0].is_suggestion is True


def test_not_a_suggestion_when_too_short():
    entries = [_entry(categories=["Spielfilm"], stop=NOW + timedelta(hours=2, minutes=30))]
    candidates = build_candidates(entries, SETTINGS, now=NOW)
    assert candidates[0].is_suggestion is False


def test_not_a_suggestion_without_keyword():
    entries = [_entry(categories=["Nachrichten"])]
    candidates = build_candidates(entries, SETTINGS, now=NOW)
    assert candidates[0].is_suggestion is False


def test_sorted_by_start_time():
    later = _entry(title="Spaeter", start=NOW + timedelta(hours=5), stop=NOW + timedelta(hours=6))
    earlier = _entry(title="Frueher", start=NOW + timedelta(hours=1), stop=NOW + timedelta(hours=2))
    candidates = build_candidates([later, earlier], SETTINGS, now=NOW)
    assert [c.title for c in candidates] == ["Frueher", "Spaeter"]
