// Rauchtest der Oberfläche mit Playwright (Chromium). Aufruf: node tests/oberflaeche_check.mjs <pfad zu index.html>
// Gibt ein JSON mit Messwerten aus; die Bewertung macht tests/test_oberflaeche.py.
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
// require statt import: so findet Node auch ein global installiertes playwright (NODE_PATH)
const { chromium } = createRequire(import.meta.url)("playwright");

const datei = process.argv[2];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 800 } });
const fehler = [];
page.on("pageerror", (e) => fehler.push(String(e)));
page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) fehler.push(m.text()); });
// Kein Netz: fremde Bilder und Karten-Skripte werden abgebrochen, der Test läuft überall gleich
await page.route(/^https?:/, (route) => route.abort());
const aus = { fehler };
try {
  await page.goto(pathToFileURL(datei).href);
  await page.waitForSelector("#tage .tag", { timeout: 10000 });
  aus.tage = await page.locator("#tage .tag").count();
  aus.termine = await page.locator("#tage [data-ev]").count();
  aus.kacheln = await page.locator("#tage .gk").count();

  // Termin-Blatt: Tipp auf den ersten Termin öffnet es, Escape schließt es wieder
  await page.locator("#tage [data-ev]").first().click();
  await page.waitForSelector("#sheet:not([hidden])");
  aus.blattTitel = (await page.locator("#sheet-inhalt h2").first().textContent()) || "";
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.getElementById("sheet").hidden);

  // Filter-Blatt
  await page.locator("[data-filter]").click();
  await page.waitForSelector("#sheet:not([hidden])");
  aus.filterTitel = (await page.locator("#sheet-inhalt h2").first().textContent()) || "";
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.getElementById("sheet").hidden);

  // Suche
  await page.locator("[data-suche]").click();
  await page.waitForSelector("#su-feld");
  await page.fill("#su-feld", process.argv[3] || "");
  await page.waitForTimeout(300);
  aus.suchtreffer = await page.locator("#su-treffer [data-ev]").count();
  await page.keyboard.press("Escape");
} catch (e) {
  aus.abbruch = String(e);
}
await browser.close();
console.log(JSON.stringify(aus));
