"""Weboberfläche (siehe README "Benutzung"): zeigt EPG-Kandidaten, nimmt die
Auswahl entgegen, zeigt den Status laufender/erledigter Jobs, verwaltet
Einstellungen. Bewusst ohne Login (siehe README "Sicherheitshinweis")."""

from __future__ import annotations

import os
import re
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, flash, redirect, render_template, request, url_for

from . import epg, scheduler
from .candidates import build_candidates
from .config import Config, load_config
from .settings import load_settings, save_settings

BERLIN = ZoneInfo("Europe/Berlin")
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

STATUS_LABELS = {
    "scheduled": "geplant",
    "recording": "läuft",
    "recorded": "aufgenommen",
    "uploading": "wird hochgeladen",
    "uploaded": "hochgeladen",
    "discarded": "verworfen (in Mediathek gefunden)",
    "canceled": "storniert",
    "failed": "fehlgeschlagen",
}


def _local_time(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M")


def _time_only(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(BERLIN).strftime("%H:%M")


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def _date_label(d) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.strftime('%d.%m.%Y')}"


def _channel_name(stream_title: str) -> str:
    """Zeigt Sendernamen ohne den "Livestream"-Zusatz aus streams.py an.
    Nur fürs Anzeigen - config.channel_map selbst bleibt unverändert, weil
    main.py den exakten Wert für die Stream-URL-Zuordnung braucht."""
    return re.sub(r"\s+", " ", stream_title.replace("Livestream", "")).strip()


def _build_table_rows(candidates, show_day_separators: bool) -> list[dict]:
    """Baut die Zeilenliste für die Sendungen-Tabelle. Bei "Alle Tage" wird
    vor der ersten Sendung eines neuen Kalendertags ein Trenner eingefügt -
    candidates ist bereits nach Startzeit sortiert (siehe candidates.py)."""
    rows: list[dict] = []
    last_date = None
    for c in candidates:
        local_date = c.start.astimezone(BERLIN).date()
        if show_day_separators and local_date != last_date:
            rows.append({"type": "separator", "label": _date_label(local_date)})
            last_date = local_date
        rows.append({"type": "candidate", "candidate": c})
    return rows


def create_app(config: Config | None = None) -> Flask:
    config = config or load_config()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.jinja_env.filters["local_time"] = _local_time
    app.jinja_env.filters["time_only"] = _time_only
    app.jinja_env.filters["status_label"] = _status_label
    app.jinja_env.filters["channel_name"] = _channel_name

    epg_cache: dict[str, object] = {"entries": [], "fetched_at": 0.0}

    def get_epg_entries():
        now = time.monotonic()
        ttl_seconds = config.epg_refresh_minutes * 60
        if now - epg_cache["fetched_at"] > ttl_seconds:
            try:
                epg_cache["entries"] = epg.fetch_epg(config.epg_urls)
                epg_cache["fetched_at"] = now
            except Exception:
                app.logger.exception(
                    "EPG-Abruf fehlgeschlagen, zeige zuletzt geladene Daten"
                )
        return epg_cache["entries"]

    @app.route("/")
    def dashboard():
        jobs = sorted(
            scheduler.list_jobs(config),
            key=lambda j: j.get("record_start", ""),
            reverse=True,
        )
        return render_template("dashboard.html", jobs=jobs)

    @app.route("/jobs/<job_id>/cancel", methods=["POST"])
    def cancel(job_id):
        if scheduler.cancel_job(config, job_id):
            flash("Aufnahme storniert.", "success")
        else:
            flash("Konnte nicht storniert werden (evtl. läuft sie schon).", "error")
        return redirect(url_for("dashboard"))

    @app.route("/sendungen")
    def sendungen():
        settings_data = load_settings(config)
        only_suggestions = request.args.get("nur_vorschlaege") == "1"
        selected_date = request.args.get("datum") or ""
        selected_channel = request.args.get("sender") or ""

        entries = get_epg_entries()
        candidates = build_candidates(entries, settings_data)
        if only_suggestions:
            candidates = [c for c in candidates if c.is_suggestion]

        available_dates = sorted(
            {c.start.astimezone(BERLIN).date() for c in candidates}
        )
        date_options = [
            {"value": d.isoformat(), "label": _date_label(d)} for d in available_dates
        ]

        if selected_date:
            candidates = [
                c
                for c in candidates
                if c.start.astimezone(BERLIN).date().isoformat() == selected_date
            ]
        if selected_channel:
            candidates = [c for c in candidates if c.channel == selected_channel]

        channel_options = {
            channel_id: config.channel_map[channel_id]
            for channel_id in settings_data["watched_channels"]
            if channel_id in config.channel_map
        }

        table_rows = _build_table_rows(candidates, show_day_separators=not selected_date)

        return render_template(
            "sendungen.html",
            candidates=candidates,
            table_rows=table_rows,
            only_suggestions=only_suggestions,
            date_options=date_options,
            selected_date=selected_date,
            channel_options=channel_options,
            selected_channel=selected_channel,
        )

    @app.route("/sendungen/aufnehmen", methods=["POST"])
    def aufnehmen():
        settings_data = load_settings(config)
        title = request.form["title"]
        scheduler.create_job(
            config,
            channel=request.form["channel"],
            title=title,
            epg_start=datetime.fromisoformat(request.form["epg_start"]),
            epg_end=datetime.fromisoformat(request.form["epg_end"]),
            buffer_before_minutes=settings_data["buffer_before_minutes"],
            buffer_after_minutes=settings_data["buffer_after_minutes"],
        )
        flash(f'"{title}" eingeplant.', "success")
        return redirect(
            url_for(
                "sendungen",
                nur_vorschlaege=request.form.get("nur_vorschlaege") or None,
                datum=request.form.get("datum") or None,
                sender=request.form.get("sender_filter") or None,
            )
        )

    @app.route("/sendungen/alle-uebernehmen", methods=["POST"])
    def alle_uebernehmen():
        settings_data = load_settings(config)
        entries = get_epg_entries()
        suggestions = [c for c in build_candidates(entries, settings_data) if c.is_suggestion]
        for candidate in suggestions:
            scheduler.create_job(
                config,
                channel=candidate.channel,
                title=candidate.title,
                epg_start=candidate.start,
                epg_end=candidate.stop,
                buffer_before_minutes=settings_data["buffer_before_minutes"],
                buffer_after_minutes=settings_data["buffer_after_minutes"],
            )
        flash(f"{len(suggestions)} Vorschläge eingeplant.", "success")
        return redirect(url_for("sendungen", nur_vorschlaege="1"))

    @app.route("/einstellungen", methods=["GET", "POST"])
    def einstellungen():
        if request.method == "POST":
            film_keywords = [
                line.strip()
                for line in request.form.get("film_keywords", "").splitlines()
                if line.strip()
            ]
            save_settings(
                config,
                {
                    "watched_channels": request.form.getlist("watched_channels"),
                    "film_keywords": film_keywords,
                    "min_duration_minutes": int(request.form["min_duration_minutes"]),
                    "buffer_before_minutes": int(request.form["buffer_before_minutes"]),
                    "buffer_after_minutes": int(request.form["buffer_after_minutes"]),
                },
            )
            flash("Einstellungen gespeichert.", "success")
            return redirect(url_for("einstellungen"))

        settings_data = load_settings(config)
        return render_template(
            "einstellungen.html", settings=settings_data, channel_map=config.channel_map
        )

    return app
