"""Verwaltet data/jobs.json: create_job/cancel_job/list_jobs/update_job.

Wird sowohl vom Webserver (create_job beim Klick auf "Aufnehmen",
cancel_job beim Stornieren) als auch vom Scheduler-Loop (update_job für
Statuswechsel) benutzt - beide Prozesse teilen sich dieselbe Datei über
state.JsonFileStore.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Config
from .state import JsonFileStore

ACTIVE_STATUSES = ("scheduled", "recording")


def _jobs_store(config: Config) -> JsonFileStore:
    return JsonFileStore(config.state_file, default=[])


def list_jobs(config: Config) -> list[dict[str, Any]]:
    return _jobs_store(config).read()


def get_job(config: Config, job_id: str) -> dict[str, Any] | None:
    for job in list_jobs(config):
        if job["id"] == job_id:
            return job
    return None


def create_job(
    config: Config,
    channel: str,
    title: str,
    epg_start: datetime,
    epg_end: datetime,
    buffer_before_minutes: int,
    buffer_after_minutes: int,
) -> dict[str, Any]:
    """Idempotent: existiert bereits ein scheduled/recording-Job für
    denselben Sender + dieselbe EPG-Sendezeit, wird der zurückgegeben statt
    ein Duplikat anzulegen (Schutz gegen Doppelklick auf "Aufnehmen")."""
    store = _jobs_store(config)
    epg_start_iso = epg_start.isoformat()
    epg_end_iso = epg_end.isoformat()
    outcome: dict[str, Any] = {}

    def _apply(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for job in jobs:
            if (
                job["channel"] == channel
                and job["epg_start"] == epg_start_iso
                and job["epg_end"] == epg_end_iso
                and job["status"] in ACTIVE_STATUSES
            ):
                outcome["job"] = job
                return jobs

        new_job = {
            "id": uuid.uuid4().hex,
            "channel": channel,
            "title": title,
            "epg_start": epg_start_iso,
            "epg_end": epg_end_iso,
            "record_start": (
                epg_start - timedelta(minutes=buffer_before_minutes)
            ).isoformat(),
            "record_end": (
                epg_end + timedelta(minutes=buffer_after_minutes)
            ).isoformat(),
            "status": "scheduled",
            "pid": None,
            "file_path": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "recorded_at": None,
            "mediathek_check_due": None,
            "found_in_mediathek": False,
            "upload_progress": None,
            "upload_total": None,
        }
        jobs.append(new_job)
        outcome["job"] = new_job
        return jobs

    store.modify(_apply)
    return outcome["job"]


def cancel_job(config: Config, job_id: str) -> bool:
    """Storniert nur Jobs im Status "scheduled" (laufende Aufnahmen werden
    laut README nur angezeigt, nicht abgebrochen)."""
    store = _jobs_store(config)
    outcome = {"canceled": False}

    def _apply(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for job in jobs:
            if job["id"] == job_id and job["status"] == "scheduled":
                job["status"] = "canceled"
                outcome["canceled"] = True
        return jobs

    store.modify(_apply)
    return outcome["canceled"]


def update_job(config: Config, job_id: str, **fields: Any) -> dict[str, Any] | None:
    """Generischer Statuswechsel/Feld-Update für den Scheduler-Loop."""
    store = _jobs_store(config)
    outcome: dict[str, Any] = {"job": None}

    def _apply(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for job in jobs:
            if job["id"] == job_id:
                job.update(fields)
                outcome["job"] = job
        return jobs

    store.modify(_apply)
    return outcome["job"]
