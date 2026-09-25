-- Standortspalten fuer die Kartenansicht.
--
-- Warum das jetzt geht und vorher nicht: der Plan hielt fest, der
-- <address>-Block des Kulturkalenders trage "nur einen Venue-Namen, keine
-- Strasse". Das stimmt - aber nur fuer die EVENT-Detailseite. Die
-- KK-VENUE-Seite (/{ort}/{slug}) traegt in div.box-location-description eine
-- vollstaendige Postanschrift. Gemessen an den 25 Venues mit den meisten
-- kommenden Events: 24/25 liefern eine PLZ (1534 von 1588 Events).
--
-- Koordinaten kommen aus zwei Quellen, siehe tools/fetch_venue_locations.py:
--   'kk_page'   - fertiger Google-Maps-Link auf der KK-Seite, exakt, gratis
--   'nominatim' - aus der Adresse geocodiert (OSM), ein Request je Venue
-- NULL heisst "kein Standort bekannt" und ist eine gueltige Antwort: ein
-- Treffpunkt wie "Terrassenufer Dresden" hat keine Hausnummer. Solche Venues
-- fehlen auf der Karte und bleiben in der Liste - dieselbe Haltung wie bei
-- 'sonstiges' in der Kategorisierung (Entscheidung #14).
ALTER TABLE venues ADD COLUMN street         TEXT;
ALTER TABLE venues ADD COLUMN postcode       TEXT;
ALTER TABLE venues ADD COLUMN city           TEXT;
ALTER TABLE venues ADD COLUMN lat            REAL;
ALTER TABLE venues ADD COLUMN lon            REAL;
ALTER TABLE venues ADD COLUMN geo_source     TEXT
                       CHECK (geo_source IN ('kk_page', 'nominatim') OR geo_source IS NULL);
ALTER TABLE venues ADD COLUMN geo_fetched_at TEXT;

-- Die Karte fragt "alle Venues mit Koordinaten" - Teilindex, weil die Haelfte
-- der Zeilen NULL bleibt.
CREATE INDEX IF NOT EXISTS idx_venues_geo ON venues(lat, lon) WHERE lat IS NOT NULL;
