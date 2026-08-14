"""Weboberfläche (siehe README "Benutzung"): zeigt EPG-Kandidaten, nimmt die
Auswahl entgegen, zeigt den Status laufender/erledigter Jobs, verwaltet
Einstellungen. Bewusst ohne Login (siehe README "Sicherheitshinweis")."""

from __future__ import annotations

import os
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


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def create_app(config: Config | None = None) -> Flask:
    config = config or load_config()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.jinja_env.filters["local_time"] = _local_time
    app.jinja_env.filters["status_label"] = _status_label

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
        entries = get_epg_entries()
        candidates = build_candidates(entries, settings_data)
        if only_suggestions:
            candidates = [c for c in candidates if c.is_suggestion]
        return render_template(
            "sendungen.html", candidates=candidates, only_suggestions=only_suggestions
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
