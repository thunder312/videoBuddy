FROM python:3.12-slim

# ffmpeg fuers Aufnehmen, tzdata damit Europe/Berlin-Zeiten (siehe
# docker-compose.yml TZ-Env) korrekt aufgeloest werden.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oerr_pvr/ oerr_pvr/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["./entrypoint.sh"]
