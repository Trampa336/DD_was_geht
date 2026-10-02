# DD was geht

Persönlicher Dresdner Veranstaltungskalender: Club, Konzerte, Subkultur, Demos.
Live: https://trampa336.github.io/DD_was_geht/

Scraper holen Termine von Sammelkalendern und den Seiten der Orte, legen Doppelte
zusammen und bauen eine statische Seite (PWA). GitHub Actions aktualisiert sie täglich.

    python3 -m venv --copies venv
    venv/bin/pip install -r requirements.txt
    venv/bin/python -m ddwg scrape    # Termine holen, baut ausgabe/index.html
    venv/bin/python -m ddwg build     # ohne Netz neu bauen
    venv/bin/python -m pytest tests

Details, Regeln und Aufbau: [CLAUDE.md](CLAUDE.md)
