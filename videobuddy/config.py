"""Lädt config.yaml (Infrastruktur/Geheimnisse, siehe README)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

# EPG-Channel-IDs (Quelle: epgshare01 DE1-Feed), deren Livestreams gegen
# echte Daten geprüft per HTTP 403 aus Deutschland geoblockt sind (ORF- und
# weitere österreichische Sender - deren Streaming-Rechte sind auf
# Österreich beschränkt). Werden hier bewusst hart abgelehnt statt nur per
# Kommentar in config.example.yaml dokumentiert, damit ein späteres
# versehentliches Wieder-Eintragen (z. B. beim Copy-Paste aus einer älteren
# config) beim Start auffällt statt erst nach Tagen mit leeren Aufnahmen.
GEOBLOCKED_CHANNEL_IDS = {
    "ORF.1.de",
    "ORF.2.de",
    "ORF.III.de",
    "ORF.SPORT.+.de",
    "Servus.TV.Österreich.de",
    "ATV.de",
    "ATV.II.de",
    "oe24.TV.de",
    "PULS.4.de",
    "tv-media.PULS.24.de",
    "PULS.acht.de",
    "Sky.Sport.Austria.de",
    "Sky.Sport.Austria.1.HD.de",
    "Sky.Sport.Austria.2.HD.de",
    "Sky.Sport.Austria.3.HD.de",
    "Sky.Sport.Austria.4.HD.de",
    "Sky.Sport.Austria.5.HD.de",
    "Sky.Sport.Austria.6.HD.de",
    "Sky.Sport.Austria.7.HD.de",
}


@dataclass
class DropboxConfig:
    refresh_token: str
    app_key: str
    app_secret: str
    upload_folder: str = "/PVR-OeRR"


@dataclass
class Config:
    channel_map: dict[str, str]
    epg_urls: list[str]
    film_keywords: list[str]
    min_duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    mediathek_check_delay_hours: int
    mediathek_api_url: str
    epg_refresh_minutes: int
    poll_interval_seconds: int
    recording_dir: str
    state_file: str
    dropbox: DropboxConfig
    log_level: str = "INFO"
    settings_file: str = field(init=False)

    def __post_init__(self) -> None:
        self.settings_file = os.path.join(
            os.path.dirname(os.path.abspath(self.state_file)), "settings.json"
        )


def load_config(path: str | None = None) -> Config:
    path = path or os.environ.get("VIDEOBUDDY_CONFIG", "config.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    channel_map = raw["channel_map"]
    blocked = GEOBLOCKED_CHANNEL_IDS & channel_map.keys()
    if blocked:
        raise ValueError(
            "channel_map enthält geoblockte Sender, deren Livestream aus "
            f"Deutschland nicht erreichbar ist: {sorted(blocked)}"
        )

    dropbox_raw = raw.get("dropbox", {})
    return Config(
        channel_map=channel_map,
        epg_urls=raw["epg_urls"],
        film_keywords=raw["film_keywords"],
        min_duration_minutes=raw["min_duration_minutes"],
        buffer_before_minutes=raw["buffer_before_minutes"],
        buffer_after_minutes=raw["buffer_after_minutes"],
        mediathek_check_delay_hours=raw["mediathek_check_delay_hours"],
        mediathek_api_url=raw["mediathek_api_url"],
        epg_refresh_minutes=raw["epg_refresh_minutes"],
        poll_interval_seconds=raw["poll_interval_seconds"],
        recording_dir=raw["recording_dir"],
        state_file=raw["state_file"],
        dropbox=DropboxConfig(
            refresh_token=dropbox_raw.get("refresh_token", ""),
            app_key=dropbox_raw.get("app_key", ""),
            app_secret=dropbox_raw.get("app_secret", ""),
            upload_folder=dropbox_raw.get("upload_folder", "/PVR-OeRR"),
        ),
        log_level=raw.get("log_level", "INFO"),
    )
