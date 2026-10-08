// Test für dienst/lesezeichen.js ohne Cloudflare: D1 wird mit node:sqlite nachgebaut.
// Läuft über tests/test_dienst_lesezeichen.py (pytest) oder direkt: node --test tests/dienst_lesezeichen.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import dienst, { GRENZEN, liste_pruefen, heute } from "../dienst/lesezeichen.js";

// Kleiner Nachbau der D1-Schnittstelle (prepare/bind/all/first/run/batch)
function fakeD1() {
  const roh = new DatabaseSync(":memory:");
  const stmt = (sql, werte = []) => ({
    bind: (...w) => stmt(sql, w),
    all: async () => ({ results: roh.prepare(sql).all(...werte) }),
    first: async () => roh.prepare(sql).get(...werte) ?? null,
    run: async () => roh.prepare(sql).run(...werte),
  });
  return {
    prepare: sql => stmt(sql),
    batch: async l => { roh.exec("BEGIN"); try { for (const s of l) await s.run(); roh.exec("COMMIT"); } catch (e) { roh.exec("ROLLBACK"); throw e; } },
  };
}

const env = { DB: fakeD1() };
const JETZT = new Date("2026-10-08T10:00:00Z");
const G1 = "geraet-aaaaaaaaaaaaaaaa", G2 = "geraet-bbbbbbbbbbbbbbbb", G3 = "geraet-cccccccccccccccc";
const K = "2026-10-10|sektor|nachtschicht", K2 = "2026-10-11|ostpol|konzert", ALT = "2026-10-01|scheune|vorbei";

const holen = (pfad, init = {}, ip = "1.2.3.4") =>
  dienst.fetch(new Request("https://x.dev" + pfad, { ...init, headers: { "CF-Connecting-IP": ip } }), env, {}, JETZT)
    .then(async r => ({ status: r.status, daten: await r.json().catch(() => null) }));
const abgleich = (g, l, ip) => holen("/abgleich", { method: "POST", body: JSON.stringify({ g, l }) }, ip);
const eintrag = k => ({ d: k.slice(0, 10), k });

test("heute in Dresdner Zeit", () => {
  assert.equal(heute(new Date("2026-10-08T22:30:00Z")), "2026-10-09");
});

test("Liste prüfen: Vergangenes und Doppeltes fallen still raus, Unsinn wird abgelehnt", () => {
  assert.deepEqual(liste_pruefen([eintrag(K), eintrag(K), eintrag(ALT)], "2026-10-08"), [eintrag(K)]);
  assert.equal(liste_pruefen([{ d: "2026-10-10", k: "2026-10-11|falsch" }], "2026-10-08"), null);
  assert.equal(liste_pruefen("x", "2026-10-08"), null);
  assert.deepEqual(liste_pruefen([eintrag(K + "x".repeat(400)), eintrag(K2)], "2026-10-08"), [eintrag(K2)]);
  assert.equal(liste_pruefen(Array(GRENZEN.proGeraet + 1).fill(eintrag(K)), "2026-10-08"), null);
});

test("zählen: andere Geräte ja, das eigene nicht", async () => {
  assert.equal((await abgleich(G1, [eintrag(K), eintrag(K2)])).status, 200);
  assert.equal((await abgleich(G2, [eintrag(K)])).status, 200);
  assert.deepEqual((await holen("/zahlen?g=" + G3)).daten, { [K]: 2, [K2]: 1 });
  assert.deepEqual((await holen("/zahlen?g=" + G1)).daten, { [K]: 1 });
});

test("Abgleich ersetzt die Liste des Geräts (Entfernen wirkt)", async () => {
  await abgleich(G1, [eintrag(K2)]);
  assert.deepEqual((await holen("/zahlen?g=" + G3)).daten, { [K]: 1, [K2]: 1 });
  await abgleich(G1, []);
  assert.deepEqual((await holen("/zahlen?g=" + G3)).daten, { [K]: 1 });
});

test("ungültige Anfragen", async () => {
  assert.equal((await abgleich("kurz", [eintrag(K)])).status, 400);
  assert.equal((await holen("/abgleich", { method: "POST", body: "{kaputt" })).status, 400);
  assert.equal((await holen("/gibtsnicht")).status, 404);
  const opt = await dienst.fetch(new Request("https://x.dev/abgleich", { method: "OPTIONS" }), env, {}, JETZT);
  assert.equal(opt.status, 204);
  assert.equal(opt.headers.get("Access-Control-Allow-Origin"), "*");
});

test("Bremse: höchstens 10 Geräte je Netz und Tag", async () => {
  const ip = "9.9.9.9";
  for (let i = 0; i < GRENZEN.geraeteProIp; i++)
    assert.equal((await abgleich(`spam-${String(i).padStart(16, "0")}`, [eintrag(K2)], ip)).status, 200);
  assert.equal((await abgleich("spam-zuviel-000000000", [eintrag(K2)], ip)).status, 429);
  // ein bekanntes Gerät aus dem Netz darf weiter abgleichen
  assert.equal((await abgleich("spam-0000000000000000", [], ip)).status, 200);
});
