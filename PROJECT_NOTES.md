# PROJECT_NOTES

Levende prosjektlogg for `oslo-parking-finder`. Oppdateres ved hver
milepæl. Lest først av agenten ved gjenopptakelse av arbeidet for å
holde retning over lange tråder.

> Hvis denne filen og README sier ulike ting: **README er sannheten om
> hvordan koden brukes**, **denne filen er sannheten om hvor vi er på
> vei og hvorfor**.

---

## 1. Mål

Bygg en utvidbar Python-pipeline som samler inn, normaliserer og lagrer
data om parkering i Oslo, slik at det senere kan brukes i en app som
finner **billig parkering**.

Førsteversjonen prioriterer datainnsamling og normalisering. Ingen
frontend, ingen brukervalg, ingen prisberegning ennå.

Suksesskriterier for fase 1 (datainnsamling):
- Minst 3 reelle datakilder integrert (Parkeringsregisteret + 2 til).
- Normalisert datasett med koordinater for > 95 % av postene.
- Prisdata (per time / per døgn) for minst én operatør.
- Daglig, idempotent kjøring som kan automatiseres.

---

## 2. Viktige beslutninger (ADR-lite)

Kronologisk. Nyeste øverst. Hver post: dato, beslutning, kort begrunnelse.

### 2026-05-21 — Bruke `parkreg-open.atlas.vegvesen.no` som faktisk API-host
Den offisielt dokumenterte URL-en hos vegvesen.no (`www.vegvesen.no/ws/...`)
gir 404. Det reelle, åpne endepunktet ble funnet ved å inspisere
nettverkstrafikken til det offentlige Parkeringsregister-kartet. Ingen
auth kreves. Vi bruker dette direkte og dokumenterer det i README.

### 2026-05-21 — Hente hele Norge, filtrere lokalt
API-et returnerer alle ~21 000 områder i ett kall. Vi filtrerer Oslo
klientside (`poststed == "OSLO"`). Enklere enn paginering, og frontend
gjør det samme.

### 2026-05-21 — `poststed` som proxy for kommune
Registeret eksponerer ikke kommune. For Oslo er post-byen "OSLO"
pålitelig. For andre kommuner må vi senere innføre postnr→kommune-oppslag.

### 2026-05-21 — `requests` som eneste runtime-dep
Standardbibliotekets `urllib` ville fungert, men `requests` gir mye
bedre feilbehandling. Holder dep-listen til én pakke.

### 2026-05-21 — CSV først, SQLite senere
CSV er nok for én kilde og er menneskelig lesbar. Vi bytter til SQLite
når 3+ kilder er på plass eller når vi trenger spørringer på tvers.

### 2026-05-21 — Idempotent normalisert CSV, tidsstemplet rå-data
Normalisert CSV (`data/normalized/<source>.csv`) overskrives ved hver
kjøring. Rå-payload (`data/raw/<source>_<ts>.json`) bevares for revisjon
og diffing.

### 2026-05-21 — Stub-adaptere fra dag én
Onepark, Aimo Park og Oslo kommune har skjelett-moduler som hever
`NotImplementedError`. Dette låser grensesnittet (`SOURCE_TYPE` + `fetch()
-> list[ParkingRecord]`) før vi bygger ut.

### 2026-05-21 — EasyPark utelatt som datakilde
Evaluert etter forslag fra bruker. Konklusjon: ikke nå. To grunner:
(1) Utviklerportalen krever kommersiell avtale; ingen åpen tilgang.
(2) EasyPark er en *betalingskanal*, ikke et priskatalog — prisene
eies av operatøren (kommunen, Aimo, Onepark, ...) som vi allerede
planlegger å hente direkte. Hvis vi senere vil vise "betal med EasyPark"
på en rad, blir det et `payment_methods`-felt på `ParkingRecord`,
ikke en egen adapter. Dokumentert i `adapters/easypark.py`.

Oppfølging samme dag: bruker påpekte at EasyPark sin *nettside* kan ha
priser. Sjekket: nei, prissidene handler om EasyParks eget servicegebyr,
ikke om sone-priser. Bekreftet beslutning.

### 2026-05-21 — Berike Parkeringsregister-data med detaljfelter
Istedenfor en ny adapter, beriker vi eksisterende rader med kapasitets-
felter fra detalj-endepunktet (`antallAvgiftsfriePlasser` m.fl.). Dette
gir oss en konkret gratis-liste uten ny datakilde. Implementert i
`ingest/fetch_register_details.py` med disk-cache i
`data/raw/details/<id>.json`.

### 2026-05-21 — Utvide `ParkingRecord` med kapasitetsfelter
6 nye nullable felter: `paid_spaces`, `free_spaces`, `charging_spaces`,
`accessible_spaces`, `facility_type`, `is_park_and_ride`. Alle `None`
by default. `FIELDS` utvidet. `scripts/verify.py` leser nå header
direkte fra `FIELDS` for å unngå drift.

### 2026-05-22 — Statisk Leaflet-kart som første UI
"Fase 1": en selvstendig HTML-fil (`parking-build-map`) som leser den
normaliserte CSV-en og produserer et Leaflet-kart med klyngede markører,
fargekoding (gratis/blanding/avgift), sidepanel-filtre, og Google Maps-
lenke per anlegg. Null infrastruktur, gjenbruker eksisterende data.
Frontend-koden kan senere bytte datakilde fra inlinet JSON til et
`/api/parking`-endepunkt uten omskriving. Logikken bor i
`parking_app.web.build_map` slik at den kan testes; HTML-malen bruker
str.replace (ikke f-string) for å unngå brace-konflikt med JS.

### 2026-05-22 — GitHub Pages + ukentlig auto-bygging, kartet som PWA
Fase 1.5: publisere kartet på GitHub Pages slik at brukeren åpner
`https://etmagnussen.github.io/oslo-parking-finder/` på telefonen uten
å installere noe, og kan legge det til på startskjermen som en app.
GitHub Actions kjører hver søndag 06:00 UTC: ingest → enrich → build →
deploy. Ingen lokal PC trengs i daglig drift. PWA-elementer (manifest,
192/512-ikoner, maskable-ikon, theme-color, apple-touch-icon, viewport
med `viewport-fit=cover` og `100dvh`) lagt inn i HTML-templaten.
Ikoner genereres reproduserbart av `scripts/make_icons.py` (ren stdlib
PNG-encoder). Build-mappen `web/dist/` er gitignored — kun kilder
committes. Konsekvens: brukeren kan jobbe utelukkende fra mobil ved å
sende prompts til assistenten; assistenten committer; CI bygger og
publiserer.

---

## 3. Gjeldende arbeidsregler

Disse reglene gjelder med mindre vi eksplisitt avtaler noe annet.

**Kode**
- Python 3.10+. Standardbibliotek først; ny dep krever notat her.
- Type hints på alle offentlige funksjoner.
- Logging via `logging`, ikke `print` (untatt i CLI-sluttoppsummering).
- Norsk i README og notater; engelsk i kode, docstrings og logger.

**Datamodell**
- Alle adaptere må returnere `list[ParkingRecord]`.
- Nye felter på `ParkingRecord` skal være bakoverkompatible (default
  `None`) og dokumenteres her under "Beslutninger" + i README-tabellen.
- Rekkefølgen i `models.FIELDS` styrer CSV-kolonner — ikke endre den
  uten en notat her.

**Filer og data**
- Aldri commit av rå- eller normalisert data — `.gitignore` håndterer
  dette, `.gitkeep` bevarer mappestrukturen.
- Tidssoner: alt vi lagrer som timestamp er ISO 8601 UTC.

**Tester**
- Hver adapter får minst én offline-test med syntetisk respons.
- Nettverkstester er valgfrie og må kunne skippes når det ikke er nett.

**Git-flyt**
- Små, tematiske commits. Conventional commits-prefiks: `feat:`, `fix:`,
  `docs:`, `chore:`, `refactor:`, `test:`.
- Hver milepæl: oppdater denne filen før commit som avslutter milepælen.

**Agent-arbeidsmåte**
- Les `PROJECT_NOTES.md` først i hver nye økt.
- Jobb i små steg. Etter hvert større steg: oppsummer hva som ble gjort,
  hvilke filer ble endret, og hva neste steg er.
- Hvis API-format eller responser er uklare: bygg beste førsteversjon
  med TODO-notater i koden og en linje under "Åpne spørsmål" nedenfor.
- Stopp og spør bare når et valg har vesentlig påvirkning (datamodell,
  ny avhengighet, ny lagringsteknologi).

**Edit → verify-løkke (obligatorisk fra 2026-05-21)**
1. Etter enhver endring i kodefiler skal det kjøres relevant verifikasjon:
   tester hvis de finnes, ellers script-kjøring, import-validering eller
   filsjekk — den sterkeste praktiske kontrollen.
2. Ny funksjonalitet skal følges av minst én enkel test eller kjørbar
   verifikasjon når det er praktisk.
3. Hvis verifikasjon feiler: forsøk å rette automatisk og kjør på nytt.
   Gjenta til den består, eller til vi er reelt blokkert og trenger
   input fra bruker.
4. Foretrekk små endringer fremfor store.
5. Rapport per oppgave skal inneholde: filer endret, verifikasjon kjørt,
   resultat, eventuelle feil rettet, anbefalt neste steg.

---

## 4. Status

| Komponent | Status | Notat |
|---|---|---|
| Prosjektstruktur | ✅ | Opprettet 2026-05-21 |
| Datamodell (`ParkingRecord`) | ✅ | 9 felter, dokumentert i README |
| Lagring (raw + normalized CSV) | ✅ | `parking_app.storage` |
| Adapter: Parkeringsregisteret | ✅ | 3 326 aktive Oslo-rader · detalj-berikelse · 1 691 m/gratis-plasser |
| Adapter: Onepark | 🟡 stub | Implementasjonsplan i modulen |
| Adapter: Aimo Park | 🟡 stub | Implementasjonsplan i modulen |
| Adapter: Oslo kommune | 🟡 stub | Implementasjonsplan i modulen |
| EasyPark | ⛔ utelatt | Lukket API + bare betalingskanal. Se `adapters/easypark.py`. |
| UI — statisk kart | ✅ | `parking-build-map` → Leaflet HTML, 3 326 markører, filtre, Google Maps-lenker |
| Tester | ✅ | 15/15 grønne (normalize, enrich, build_map) |
| Verifikasjonsscript | ✅ | `scripts/verify.py` — struktur + imports + pytest + CSV-sanity |
| CI / scheduling | ⛔ | Ikke startet |
| Prisdata | ⛔ | Krever operatør-adapter |

---

## 5. Neste planlagte steg

0. **Aktivere GitHub Pages i repo-innstillinger og kjøre workflow én
   gang manuelt** — må gjøres én gang etter første push av workflow-fila.
   Innstillinger → Pages → Source: "GitHub Actions". Deretter Actions →
   "Build & deploy map" → "Run workflow".

Prioritert. Når et steg er ferdig, flytt til "Gjort" og legg til en
ADR-post under §2 hvis det innebar et reelt valg.

1. **Vurdere GitHub Pages-publisering.** Når brukeren har testet det
   statiske kartet en stund, vurder om vi skal aktivere Pages slik at
   kartet er tilgjengelig fra telefonen uten filoverføring.
2. **Oslo kommune-adapter — takstgrupper.** Parse priser per takstgruppe
   (2012, 2200, 2300, ...) fra
   [oslo.kommune.no](https://www.oslo.kommune.no/gate-transport-og-parkering/parkering/priser-og-betaling-for-parkering/).
   Gir oss "hva koster sone X for elbil/fossilbil", samt avgiftstider
   (når er det gratis utenfor avgiftstid).
3. **Utvid `ParkingRecord` med prisfelter.** Foreslått:
   `tariff_group`, `price_per_hour_petrol`, `price_per_hour_ev`,
   `free_outside_hours_from`, `free_outside_hours_to`, `currency`.
   Alle nullable.
4. **Onepark-adapter (MVP).** HTML-parsing av anleggslistene på
   onepark.no, med priser om mulig. Offline-test med lagret HTML-fikstur.
5. **Oslo kommune-adapter — sone-GeoJSON.** Identifiser riktig datasett
   på data.oslo.kommune.no for soner/beboerparkering. Mapper polygon
   → representativt punkt + sonenavn, lenker mot takstgruppe.
6. **Aimo Park-adapter.** Undersøk app-backend; HTML som fallback.
7. **Kryssreferanse på koordinater.** Match operatør-anlegg mot
   Parkeringsregisteret innen ~50 m for å bygge én logisk rad per
   fysisk anlegg. Vurder om dette skal bo i en egen `merge.py`.
8. **Bytt CSV → SQLite.** Behold CSV-eksport som artefakt. Trigger:
   3+ kilder integrert.
9. **Datakvalitetstester.** Andel med koordinater, lat/lon innenfor
   Oslo bbox, ingen duplikat-`id`-er, ikke-tomme `name`.
10. **Schedulering.** GitHub Actions: daglig ingest, commit normaliserte
    CSV-er for historikk-diff.
11. **Fase 2 — FastAPI-backend.** Når prisdata er inne. Frontend
    gjenbrukes; bytter ut inlinet JSON med fetch til `/api/parking`.

---

## 6. Åpne spørsmål

Ting vi ikke har bestemt enda. Når en blir besvart, flytt svaret til
§2 som en ADR.

- Skal vi geokode operatør-adresser via Kartverket eller Nominatim?
  (Lisens og rate-limit varierer.)
- Hvordan håndtere prisstrukturer som varierer på tid (rushtid,
  helg, natt)? Trolig en sekundærtabell — ikke flate felter på
  `ParkingRecord`.
- Bør "billig" beregnes på pris/time, pris/døgn, eller en kontekst-
  avhengig blanding? Påvirker datamodell og senere ranking.

---

## 7. Gjort (logg)

- **2026-05-21** — Bootstrappet prosjektstruktur, datamodell, storage,
  Parkeringsregister-adapter, README, tester. Første ingest kjørte OK:
  21 660 hentet, 3 322 normaliserte Oslo-rader.
- **2026-05-21** — Lagt til `PROJECT_NOTES.md` som levende prosjektminne.
- **2026-05-21** — Vedtatt edit → verify-løkke som arbeidsregel. Lagt til
  `scripts/verify.py` (struktur + imports + pytest + CSV-sanity).
  Full verifikasjon kjørt: 5/5 tester grønne, 3 322 Oslo-rader, 100 %
  koordinatdekning, 100 % innenfor Oslo bbox.
- **2026-05-21** — EasyPark evaluert og forkastet som datakilde
  (ADR-post over). Lagt til `adapters/easypark.py` som dokumentert
  blindspor (ingen `fetch()`).
- **2026-05-21** — Utvidet `ParkingRecord` med 6 kapasitetsfelter.
  Implementert `ingest/fetch_register_details.py` med disk-cache.
  Lagt til 5 nye tester (10/10 grønne). Full ingest kjørt: 3 326/3 326
  anlegg beriket, **1 691 har minst én avgiftsfri plass**, 573 lade,
  29 innfartsparkering.
- **2026-05-22** — Bygd statisk Leaflet-kart (`parking-build-map`):
  3 326 markører, fargekoding etter gratis/avgift, sidepanel-filtre,
  Google Maps-deep-links. 5 nye tester (15/15 grønne totalt).
  Verifisert visuelt i Playwright — filter "bare gratis" gir 1 691
  anlegg, identisk med CSV-tellingen.
