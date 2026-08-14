import pytest

from oerr_pvr.config import Config, DropboxConfig


@pytest.fixture
def make_config(tmp_path):
    def _make(**overrides) -> Config:
        defaults = dict(
            channel_map={
                "ard.de": "ARD Livestream",
                "zdf.de": "ZDF Livestream",
            },
            epg_urls=["https://example.invalid/epg.xml"],
            film_keywords=["Spielfilm", "Fernsehfilm"],
            min_duration_minutes=70,
            buffer_before_minutes=3,
            buffer_after_minutes=12,
            mediathek_check_delay_hours=72,
            mediathek_api_url="https://example.invalid/api/query",
            epg_refresh_minutes=360,
            poll_interval_seconds=30,
            recording_dir=str(tmp_path / "recordings"),
            state_file=str(tmp_path / "jobs.json"),
            dropbox=DropboxConfig(refresh_token="t", app_key="k", app_secret="s"),
            log_level="INFO",
        )
        defaults.update(overrides)
        return Config(**defaults)

    return _make
