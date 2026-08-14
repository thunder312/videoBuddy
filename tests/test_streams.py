import os

from oerr_pvr.streams import parse_live_streams

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "live_streams_sample.json")


def _load_fixture() -> str:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def test_parse_live_streams_keeps_all_duplicate_keys():
    """Naives json.loads() wuerde hier nur den letzten "X"-Eintrag behalten
    (3Sat) - alle drei Sender muessen erhalten bleiben."""
    streams = parse_live_streams(_load_fixture())

    assert set(streams.keys()) == {"ARD Livestream", "ZDF Livestream", "3Sat Livestream"}


def test_parse_live_streams_prefers_hd_url_when_present():
    streams = parse_live_streams(_load_fixture())

    assert streams["ARD Livestream"] == "https://example.invalid/ard/hd/master.m3u8"


def test_parse_live_streams_falls_back_to_normal_url():
    streams = parse_live_streams(_load_fixture())

    assert streams["ZDF Livestream"] == "https://example.invalid/zdf/master.m3u8"
    assert streams["3Sat Livestream"] == "https://example.invalid/3sat/master.m3u8"


def test_parse_live_streams_naive_json_loads_would_lose_data():
    """Dokumentiert den Sonderfall aus der README: ein stinknormales
    json.loads() behaelt pro Key nur den letzten Wert."""
    import json

    naive = json.loads(_load_fixture())
    assert naive["X"] == ["3Sat", "Livestream", "3Sat Livestream", "", "", "", "", "",
                           "https://example.invalid/3sat/master.m3u8", "http://3sat.de",
                           "", "", "", "", "", "", "", "", "", ""]
