"""Abgleich gegen die MediathekViewWeb-API (siehe README-Architekturdiagramm
und "Offene Punkte" Punkt 3).

Request-/Response-Format ist gegen die öffentlich dokumentierte API
verifiziert (POST mit Content-Type text/plain, Response unter
result.results[]) - der End-to-End-Roundtrip gegen die echte API wurde in
dieser Sitzung nicht getestet (siehe README), dafür ist die CLI unten da:

    python -m oerr_pvr.mediathek "Titel" "Sender"
"""

from __future__ import annotations

import json
import re
import sys

import requests

DEFAULT_API_URL = "https://mediathekviewweb.de/api/query"


def query_mediathek(
    title: str, channel: str, api_url: str = DEFAULT_API_URL, size: int = 5, timeout: int = 30
) -> list[dict]:
    payload = {
        "queries": [
            {"fields": ["title"], "query": title},
            {"fields": ["channel"], "query": channel},
        ],
        "sortBy": "timestamp",
        "sortOrder": "desc",
        "future": False,
        "offset": 0,
        "size": size,
    }
    # Die API erwartet Content-Type: text/plain, sonst schlägt das
    # serverseitige JSON-Parsing fehl (bekannte Eigenheit der API).
    response = requests.post(
        api_url,
        data=json.dumps(payload),
        headers={"Content-Type": "text/plain"},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("result", {}).get("results", [])


def _normalize_channel(value: str) -> str:
    """Nur alphanumerische Zeichen, klein geschrieben - toleriert
    Schreibweise-Unterschiede zwischen config.yaml-Sendernamen (z. B.
    "ZDF.neo") und den MediathekViewWeb-Sendernamen (z. B. "ZDFneo")."""
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def is_in_mediathek(
    title: str, channel: str, api_url: str = DEFAULT_API_URL, size: int = 5
) -> bool:
    results = query_mediathek(title, channel, api_url=api_url, size=size)
    title_lower = title.strip().lower()
    channel_norm = _normalize_channel(channel)
    for entry in results:
        entry_title = entry.get("title", "").strip().lower()
        entry_channel_norm = _normalize_channel(entry.get("channel", ""))
        if entry_title != title_lower:
            continue
        if entry_channel_norm == channel_norm:
            return True
        if channel_norm and (
            channel_norm in entry_channel_norm or entry_channel_norm in channel_norm
        ):
            return True
    return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('Aufruf: python -m oerr_pvr.mediathek "Titel" "Sender"', file=sys.stderr)
        sys.exit(1)

    cli_title, cli_channel = sys.argv[1], sys.argv[2]
    cli_results = query_mediathek(cli_title, cli_channel)
    print(f"{len(cli_results)} Treffer für Titel={cli_title!r} Sender={cli_channel!r}:")
    for result in cli_results:
        print(f"  - {result.get('channel')}: {result.get('title')} ({result.get('url_video')})")
    print(f"In Mediathek gefunden (exakter Titel+Sender-Match): {is_in_mediathek(cli_title, cli_channel)}")
