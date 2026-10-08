/* Gemeinsame Lesezeichen (seit 2026-10-08, Davids Wunsch): ein winziger Cloudflare Worker mit D1-Datenbank.
   Die Seite bleibt statisch. Dieser Dienst zählt nur, wie viele Geräte einen Termin gemerkt haben.
   Es gibt keine Namen und keine Konten, nur eine zufällige Geräte-Kennung aus dem Browser.

   GET  /zahlen?g=<gerät>  → {"<datum|ort|titel>": n, …} für heute und später, ohne das fragende Gerät
   POST /abgleich          → Body (text/plain, JSON): {"g": "<gerät>", "l": [{"d": "2026-10-10", "k": "<datum|ort|titel>"}, …]}
                             Ersetzt alle Lesezeichen dieses Geräts durch die Liste (selbstheilend, auch nach offline).

   Einrichtung: siehe CLAUDE.md, Abschnitt „Gemeinsame Lesezeichen“. Binding der D1-Datenbank heißt DB. */

export const GRENZEN = {
  proGeraet: 100,       // höchstens so viele Lesezeichen je Gerät
  geraeteProIp: 10,     // höchstens so viele Geräte je Netz (IP) und Tag, bremst Hochtreiben
  schluessel: 300,      // Länge von datum|ort|titel
};

const SCHEMA = `CREATE TABLE IF NOT EXISTS merk (
  g TEXT NOT NULL, k TEXT NOT NULL, d TEXT NOT NULL, ip TEXT NOT NULL, t INTEGER NOT NULL,
  PRIMARY KEY (g, k))`;

const KOPF = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const antwort = (daten, status = 200, extra = {}) =>
  new Response(JSON.stringify(daten), { status, headers: { "Content-Type": "application/json", ...KOPF, ...extra } });

const GERAET = /^[A-Za-z0-9-]{16,64}$/;
const DATUM = /^\d{4}-\d{2}-\d{2}$/;

// Heute in Dresden (der Dienst läuft irgendwo auf der Welt)
export function heute(jetzt = new Date()) {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin" }).format(jetzt);
}

async function ipHash(ip, tag) {
  const roh = new TextEncoder().encode(`${ip}|${tag}|ddwg`);
  const h = await crypto.subtle.digest("SHA-256", roh);
  return [...new Uint8Array(h).slice(0, 8)].map(b => b.toString(16).padStart(2, "0")).join("");
}

// Prüft die Liste eines Geräts; gibt die gültigen, eindeutigen Einträge zurück oder null
export function liste_pruefen(l, tag) {
  if (!Array.isArray(l) || l.length > GRENZEN.proGeraet) return null;
  const gesehen = new Set(), raus = [];
  for (const x of l) {
    if (!x || typeof x.k !== "string" || typeof x.d !== "string") return null;
    if (!DATUM.test(x.d) || !x.k.startsWith(x.d + "|")) return null;
    // Vergangenes, Doppeltes und zu Langes still auslassen (die Seite kürzt auf 200 Zeichen)
    if (x.d < tag || gesehen.has(x.k) || x.k.length > GRENZEN.schluessel) continue;
    gesehen.add(x.k); raus.push({ k: x.k, d: x.d });
  }
  return raus;
}

async function zahlen(db, g, tag) {
  const { results } = await db.prepare(
    "SELECT k, COUNT(*) AS n FROM merk WHERE d >= ?1 AND g != ?2 GROUP BY k").bind(tag, g || "").all();
  const aus = {};
  for (const r of results || []) aus[r.k] = r.n;
  return aus;
}

async function abgleich(db, body, ip, tag, jetzt) {
  let daten;
  try { daten = JSON.parse(body); } catch (e) { return antwort({ fehler: "kein JSON" }, 400); }
  if (!daten || !GERAET.test(daten.g || "")) return antwort({ fehler: "Gerät fehlt" }, 400);
  const l = liste_pruefen(daten.l, tag);
  if (!l) return antwort({ fehler: "Liste ungültig" }, 400);
  const iph = await ipHash(ip, tag);
  // Bremse: zu viele verschiedene Geräte aus einem Netz am selben Tag
  const andere = await db.prepare(
    "SELECT COUNT(DISTINCT g) AS n FROM merk WHERE ip = ?1 AND g != ?2").bind(iph, daten.g).first();
  if ((andere?.n || 0) >= GRENZEN.geraeteProIp) return antwort({ fehler: "zu viele Geräte" }, 429);
  const t = Math.floor(jetzt.getTime() / 1000);
  await db.batch([
    db.prepare("DELETE FROM merk WHERE d < ?1").bind(tag),           // Vergangenes aufräumen
    db.prepare("DELETE FROM merk WHERE g = ?1").bind(daten.g),
    ...l.map(x => db.prepare("INSERT INTO merk (g, k, d, ip, t) VALUES (?1, ?2, ?3, ?4, ?5)")
      .bind(daten.g, x.k, x.d, iph, t)),
  ]);
  return antwort({ ok: true, n: l.length });
}

let schemaDa = false;
export default {
  async fetch(req, env, ctx, jetzt = new Date()) {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: KOPF });
    const db = env.DB;
    if (!schemaDa) { await db.prepare(SCHEMA).run(); schemaDa = true; }
    const url = new URL(req.url), tag = heute(jetzt);
    if (req.method === "GET" && url.pathname === "/zahlen")
      return antwort(await zahlen(db, url.searchParams.get("g"), tag), 200, { "Cache-Control": "no-store" });
    if (req.method === "POST" && url.pathname === "/abgleich") {
      const body = await req.text();
      if (body.length > 40000) return antwort({ fehler: "zu groß" }, 413);
      return abgleich(db, body, req.headers.get("CF-Connecting-IP") || "", tag, jetzt);
    }
    return antwort({ fehler: "unbekannt" }, 404);
  },
};
