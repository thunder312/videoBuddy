"""Laufende Vorlieben (data/settings.json), siehe README "config.yaml vs.
Einstellungen in der Weboberfläche". Wird beim ersten Start mit Defaults aus
config.yaml angelegt, danach ausschließlich über die Weboberfläche geändert.
"""

from __future__ import annotations

from typing import Any

from .config import Config
from .state import JsonFileStore

SETTINGS_KEYS = (
    "watched_channels",
    "film_keywords",
    "min_duration_minutes",
    "buffer_before_minutes",
    "buffer_after_minutes",
)


def _defaults_from_config(config: Config) -> dict[str, Any]:
    return {
        "watched_channels": list(config.channel_map.keys()),
        "film_keywords": list(config.film_keywords),
        "min_duration_minutes": config.min_duration_minutes,
        "buffer_before_minutes": config.buffer_before_minutes,
        "buffer_after_minutes": config.buffer_after_minutes,
    }


def get_store(config: Config) -> JsonFileStore:
    return JsonFileStore(config.settings_file, default=_defaults_from_config(config))


def load_settings(config: Config) -> dict[str, Any]:
    store = get_store(config)
    data = store.read()
    defaults = _defaults_from_config(config)
    merged = {**defaults, **{k: v for k, v in data.items() if k in SETTINGS_KEYS}}
    return merged


def save_settings(config: Config, updates: dict[str, Any]) -> dict[str, Any]:
    store = get_store(config)

    def _apply(data: dict[str, Any]) -> dict[str, Any]:
        for key in SETTINGS_KEYS:
            if key in updates:
                data[key] = updates[key]
        return data

    return store.modify(_apply)
