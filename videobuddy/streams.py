"""Lädt die aktuellen HLS-Live-Stream-URLs, die das MediathekView-Projekt
selbst pflegt (siehe README). Quelle: live-streams.json aus dem MServer-Repo.

Format-Besonderheit (verifiziert gegen die echte Datei): das Root-JSON-Objekt
enthält den Key "X" für jeden Sender erneut - ein naives json.loads() würde
dabei alle bis auf den letzten "X"-Eintrag stillschweigend verlieren, weil
Python-dicts doppelte Keys überschreiben. Wir parsen deshalb mit
object_pairs_hook=list, das alle Paare in Dokumentreihenfolge erhält.
"""

from __future__ import annotations

import json
import logging
import time

import requests

logger = logging.getLogger(__name__)

LIVE_STREAMS_URL = (
    "https://raw.githubusercontent.com/mediathekview/MServer/master/dist/live-streams.json"
)
CACHE_TTL_SECONDS = 6 * 60 * 60

_cache: dict[str, tuple[float, dict[str, str]]] = {}


def parse_live_streams(raw_text: str) -> dict[str, str]:
    """Titel-Feld (z. B. "ARD Livestream") -> beste verfügbare Stream-URL.

    Die Spaltennamen stehen im zweiten "Filmliste"-Eintrag der Datei (der
    erste ist ein Versions-/Metadaten-Header), jeder folgende "X"-Eintrag ist
    eine positionsgleiche Werteliste dazu.
    """
    pairs = json.loads(raw_text, object_pairs_hook=list)

    columns: list[str] | None = None
    header_entries_seen = 0
    streams: dict[str, str] = {}

    for key, value in pairs:
        if key == "Filmliste":
            header_entries_seen += 1
            if header_entries_seen == 2:
                columns = value
            continue
        if key != "X" or columns is None:
            continue
        row = dict(zip(columns, value))
        title = (row.get("Titel") or "").strip()
        url = row.get("Url_HD") or row.get("Url")
        if title and url:
            streams[title] = url

    return streams


def fetch_live_streams(force_refresh: bool = False) -> dict[str, str]:
    """Titel -> HLS-URL. Cached für CACHE_TTL_SECONDS, fällt bei Fetch-Fehlern
    auf den letzten bekannten Stand zurück statt hart zu scheitern."""
    cached = _cache.get("streams")
    now = time.monotonic()
    if not force_refresh and cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = requests.get(LIVE_STREAMS_URL, timeout=30)
        response.raise_for_status()
        streams = parse_live_streams(response.text)
        _cache["streams"] = (now, streams)
        return streams
    except Exception:
        if cached is not None:
            logger.warning(
                "live-streams.json Abruf fehlgeschlagen, verwende letzten bekannten Stand",
                exc_info=True,
            )
            return cached[1]
        raise
