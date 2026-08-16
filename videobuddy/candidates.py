"""Baut aus EPG-Einträgen + Einstellungen die Kandidatenliste für die
Weboberfläche "Sendungen wählen" (siehe README-Architekturdiagramm)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .epg import EpgEntry
from .genre_groups import GENRE_GROUPS_LOWER


@dataclass
class Candidate:
    channel: str
    title: str
    start: datetime
    stop: datetime
    duration_minutes: float
    categories: list[str]
    description: str
    is_suggestion: bool


def _matches_film_keywords(entry: EpgEntry, film_keywords: list[str]) -> bool:
    haystacks = [entry.title, *entry.categories]
    keywords_lower = [kw.lower() for kw in film_keywords]
    if any(
        kw in haystack.lower() for kw in keywords_lower for haystack in haystacks
    ):
        return True

    # Genre-Gruppen (z. B. "Sci-Fi") decken auch Tags ab, die keinen
    # gemeinsamen Teilstring mit dem Suchbegriff haben (z. B.
    # "Science-Fiction") - siehe genre_groups.py.
    category_set = set(entry.categories)
    return any(
        not category_set.isdisjoint(GENRE_GROUPS_LOWER[kw])
        for kw in keywords_lower
        if kw in GENRE_GROUPS_LOWER
    )


def build_candidates(
    epg_entries: list[EpgEntry],
    settings: dict[str, Any],
    now: datetime | None = None,
) -> list[Candidate]:
    """Nur zukünftige Sendungen auf beobachteten Sendern. "Vorschlag"
    (is_suggestion) = Mindestlänge erreicht UND Filmschlagwort in Titel oder
    Genre-Tags gefunden."""
    now = now or datetime.now(timezone.utc)
    watched = set(settings["watched_channels"])
    min_duration = settings["min_duration_minutes"]
    film_keywords = settings["film_keywords"]

    candidates: list[Candidate] = []
    for entry in epg_entries:
        if entry.channel not in watched:
            continue
        if entry.start <= now:
            continue
        is_suggestion = entry.duration_minutes >= min_duration and _matches_film_keywords(
            entry, film_keywords
        )
        candidates.append(
            Candidate(
                channel=entry.channel,
                title=entry.title,
                start=entry.start,
                stop=entry.stop,
                duration_minutes=entry.duration_minutes,
                categories=entry.categories,
                description=entry.description,
                is_suggestion=is_suggestion,
            )
        )

    candidates.sort(key=lambda c: c.start)
    return candidates
