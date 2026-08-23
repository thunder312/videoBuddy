import pytest
import yaml

from videobuddy.config import load_config

BASE_RAW = {
    "epg_urls": ["https://example.invalid/epg.xml"],
    "film_keywords": ["film"],
    "min_duration_minutes": 35,
    "buffer_before_minutes": 5,
    "buffer_after_minutes": 5,
    "mediathek_check_delay_hours": 72,
    "mediathek_api_url": "https://example.invalid/api/query",
    "epg_refresh_minutes": 360,
    "poll_interval_seconds": 30,
    "recording_dir": "./recordings",
    "state_file": "./data/jobs.json",
    "dropbox": {"refresh_token": "t", "app_key": "k", "app_secret": "s"},
}


def _write_config(tmp_path, channel_map):
    path = tmp_path / "config.yaml"
    raw = dict(BASE_RAW, channel_map=channel_map)
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return str(path)


def test_load_config_accepts_normal_channel_map(tmp_path):
    path = _write_config(tmp_path, {"Das.Erste.de": "ARD Livestream"})
    config = load_config(path)
    assert config.channel_map == {"Das.Erste.de": "ARD Livestream"}


def test_load_config_rejects_geoblocked_channel(tmp_path):
    """ORF & Co. sind aus Deutschland per HTTP 403 geoblockt (siehe
    GEOBLOCKED_CHANNEL_IDS) - ein versehentlicher Eintrag soll beim Start
    auffallen statt erst nach Tagen mit leeren Aufnahmen."""
    path = _write_config(
        tmp_path,
        {"Das.Erste.de": "ARD Livestream", "ORF.1.de": "ORF-1 Livestream"},
    )
    with pytest.raises(ValueError, match="ORF.1.de"):
        load_config(path)
