"""Lädt und parst EPG-Feeds im XMLTV-Standardformat (herstellerunabhängig -
funktioniert grundsätzlich mit jeder passenden Quelle, siehe README "Offene
Punkte" Punkt 1). Welche konkrete Quelle benutzt wird, ist Sache der
config.yaml (epg_urls) und noch nicht Teil dieses Codes."""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

GZIP_MAGIC = b"\x1f\x8b"


@dataclass
class EpgEntry:
    channel: str
    title: str
    start: datetime  # tz-aware, UTC
    stop: datetime  # tz-aware, UTC
    categories: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def duration_minutes(self) -> float:
        return (self.stop - self.start).total_seconds() / 60


def _parse_xmltv_time(raw: str) -> datetime:
    """XMLTV-Zeitformat: "YYYYMMDDhhmmss [+-ZZZZ]". Fehlt der Offset, wird
    laut Standard UTC angenommen."""
    raw = raw.strip()
    if " " in raw:
        dt_part, offset_part = raw.split(" ", 1)
    else:
        dt_part, offset_part = raw, "+0000"

    dt = datetime.strptime(dt_part, "%Y%m%d%H%M%S")
    sign = -1 if offset_part.strip().startswith("-") else 1
    digits = offset_part.strip().lstrip("+-")
    hours, minutes = int(digits[:2]), int(digits[2:4])
    tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
    return dt.replace(tzinfo=tz).astimezone(timezone.utc)


def _decompress_if_gzip(content: bytes) -> bytes:
    """Manche kostenlosen XMLTV-Quellen (z. B. epgshare01.online) liefern
    .xml.gz ohne passenden Content-Encoding-Header - requests entpackt das
    dann NICHT automatisch. Magic-Bytes-Check statt URL-Endung, damit es
    unabhängig davon funktioniert, ob ein Server doch korrekt komprimiert."""
    if content[:2] == GZIP_MAGIC:
        return gzip.decompress(content)
    return content


def parse_xmltv(xml_bytes: bytes) -> list[EpgEntry]:
    xml_bytes = _decompress_if_gzip(xml_bytes)
    root = ET.fromstring(xml_bytes)
    entries: list[EpgEntry] = []

    for programme in root.findall("programme"):
        channel = programme.get("channel", "")
        start_raw = programme.get("start")
        stop_raw = programme.get("stop")
        if not channel or not start_raw or not stop_raw:
            continue

        title_el = programme.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""

        categories = [
            cat.text.strip() for cat in programme.findall("category") if cat.text
        ]

        desc_el = programme.find("desc")
        description = (desc_el.text or "").strip() if desc_el is not None else ""

        entries.append(
            EpgEntry(
                channel=channel,
                title=title,
                start=_parse_xmltv_time(start_raw),
                stop=_parse_xmltv_time(stop_raw),
                categories=categories,
                description=description,
            )
        )

    return entries


def fetch_epg(urls: list[str]) -> list[EpgEntry]:
    """Lädt und mergt mehrere XMLTV-Quellen, dedupliziert nach
    (channel, start, title) und sortiert nach Startzeit."""
    entries: list[EpgEntry] = []
    seen: set[tuple[str, datetime, str]] = set()

    for url in urls:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        for entry in parse_xmltv(response.content):
            key = (entry.channel, entry.start, entry.title)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)

    entries.sort(key=lambda e: e.start)
    return entries
