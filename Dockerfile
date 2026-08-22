FROM python:3.12-slim

# Systempakete, die lxml beim Bauen braucht (nur relevant, falls pip kein
# fertiges Wheel für die Architektur findet - z.B. auf 32-bit-Pi-OS/armv7).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Zweistufig: erst alles Pflichtmäßige, dann lxml als "nice to have".
# Schlägt der lxml-Build auf exotischen Architekturen fehl, läuft der Build
# trotzdem durch - der Code fällt automatisch auf html.parser zurück
# (siehe app/scrapers/base.py).
RUN grep -v '^lxml' requirements.txt | grep -v '^#' > /tmp/req-core.txt \
    && pip install --no-cache-dir -r /tmp/req-core.txt \
    && (pip install --no-cache-dir lxml==5.3.0 \
        || echo "HINWEIS: lxml nicht installierbar - benutze html.parser (unkritisch).")

COPY . .

RUN mkdir -p /app/data

EXPOSE 8080

CMD ["python", "main.py"]
