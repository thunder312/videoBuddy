"""Scheduler-Loop (siehe README): führt nur bereits ausgewählte Aufnahmen
zur richtigen Zeit aus, fragt selbst kein EPG ab. Läuft als eigener Prozess
neben dem Webserver (`python -m videobuddy.main`), beide teilen sich denselben
data/-Ordner."""

from __future__ import annotations

import logging
import os
import re
import signal
import time
from datetime import datetime, timedelta, timezone

from . import dropbox_upload, mediathek, recorder, scheduler, streams
from .config import Config, load_config

logger = logging.getLogger("videobuddy.main")

# Zusätzlicher Puffer nach record_end, bevor eine Aufnahme trotz laufender
# PID als beendet erzwungen wird (Sicherheitsnetz falls is_finished() eine
# wiederverwendete PID fälschlich als "läuft noch" liest).
SAFETY_MARGIN_MINUTES = 5

_stop = False


def _handle_signal(signum, _frame) -> None:
    global _stop
    logger.info(
        "Signal %s empfangen, beende Scheduler-Loop nach aktuellem Durchlauf", signum
    )
    _stop = True


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _mediathek_channel_hint(stream_title: str) -> str:
    """Grobe Heuristik: aus dem streams.py-Titel ("ARD Livestream", "WDR
    Livestream (Deutschland)") den wahrscheinlichen MediathekViewWeb-
    Sendernamen ableiten. mediathek.is_in_mediathek() toleriert zusätzlich
    Teilstring-Treffer für genau diesen Fall."""
    name = stream_title.replace("Livestream", "")
    name = re.sub(r"\([^)]*\)", "", name)
    return name.strip()


def _delete_if_exists(path: str | None) -> None:
    if not path:
        return
    if os.path.exists(path):
        os.remove(path)
    log_path = path + ".log"
    if os.path.exists(log_path):
        os.remove(log_path)


def _process_scheduled(config: Config, job: dict, now: datetime) -> None:
    if _parse_iso(job["record_start"]) > now:
        return
    try:
        live_streams = streams.fetch_live_streams()
        stream_title = config.channel_map.get(job["channel"])
        stream_url = live_streams.get(stream_title) if stream_title else None
        if not stream_url:
            raise RuntimeError(f"Kein Live-Stream für Sender '{job['channel']}' gefunden")

        record_start = _parse_iso(job["record_start"])
        record_end = _parse_iso(job["record_end"])
        output_path = recorder.build_output_path(
            config.recording_dir, job["channel"], job["title"], record_start
        )
        pid = recorder.start_recording(stream_url, output_path, record_end)
        scheduler.update_job(
            config, job["id"], status="recording", pid=pid, file_path=output_path
        )
        logger.info("Aufnahme gestartet: %s (%s), pid=%s", job["title"], job["channel"], pid)
    except Exception as exc:
        logger.exception("Aufnahme konnte nicht gestartet werden: %s", job["title"])
        scheduler.update_job(config, job["id"], status="failed", error=str(exc))


def _process_recording(config: Config, job: dict, now: datetime) -> None:
    record_end = _parse_iso(job["record_end"])
    overdue = now >= record_end + timedelta(minutes=SAFETY_MARGIN_MINUTES)
    if not (recorder.is_finished(job.get("pid")) or overdue):
        return

    mediathek_check_due = now + timedelta(hours=config.mediathek_check_delay_hours)
    scheduler.update_job(
        config,
        job["id"],
        status="recorded",
        recorded_at=now.isoformat(),
        mediathek_check_due=mediathek_check_due.isoformat(),
    )
    logger.info("Aufnahme beendet: %s (%s)", job["title"], job["channel"])


def _process_recorded(config: Config, job: dict, now: datetime) -> None:
    due = job.get("mediathek_check_due")
    if not due or _parse_iso(due) > now:
        return
    try:
        stream_title = config.channel_map.get(job["channel"], "")
        channel_hint = _mediathek_channel_hint(stream_title)
        found = mediathek.is_in_mediathek(
            job["title"], channel_hint, config.mediathek_api_url
        )
        if found:
            _delete_if_exists(job["file_path"])
            scheduler.update_job(config, job["id"], status="discarded")
            logger.info("In Mediathek gefunden, lokal gelöscht: %s", job["title"])
        else:
            scheduler.update_job(config, job["id"], status="uploading")
            dropbox_upload.upload_file(job["file_path"], config.dropbox)
            _delete_if_exists(job["file_path"])
            scheduler.update_job(config, job["id"], status="uploaded")
            logger.info("Zu Dropbox hochgeladen: %s", job["title"])
    except Exception as exc:
        logger.exception("Mediathek-Check/Upload fehlgeschlagen: %s", job["title"])
        scheduler.update_job(config, job["id"], status="failed", error=str(exc))


def run_once(config: Config) -> None:
    now = datetime.now(timezone.utc)
    for job in scheduler.list_jobs(config):
        status = job["status"]
        if status == "scheduled":
            _process_scheduled(config, job, now)
        elif status == "recording":
            _process_recording(config, job, now)
        elif status == "recorded":
            _process_recorded(config, job, now)


def run_forever(config: Config | None = None) -> None:
    config = config or load_config()
    logging.basicConfig(
        level=config.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    logger.info(
        "Scheduler-Loop gestartet (poll_interval_seconds=%s)", config.poll_interval_seconds
    )

    while not _stop:
        try:
            run_once(config)
        except Exception:
            logger.exception("Unerwarteter Fehler im Scheduler-Durchlauf")
        for _ in range(config.poll_interval_seconds):
            if _stop:
                break
            time.sleep(1)


if __name__ == "__main__":
    run_forever()
