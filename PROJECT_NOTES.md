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
| Adapter: Parkeringsregisteret | ✅ | 3 322 aktive Oslo-rader ved første kjøring |
| Adapter: Onepark | 🟡 stub | Implementasjonsplan i modulen |
| Adapter: Aimo Park | 🟡 stub | Implementasjonsplan i modulen |
| Adapter: Oslo kommune | 🟡 stub | Implementasjonsplan i modulen |
| Tester | ✅ | 5/5 grønne (`tests/test_normalize.py`) |
| Verifikasjonsscript | ✅ | `scripts/verify.py` — struktur + imports + pytest + CSV-sanity |
| CI / scheduling | ⛔ | Ikke startet |
| Prisdata | ⛔ | Krever operatør-adapter |

---

## 5. Neste planlagte steg

Prioritert. Når et steg er ferdig, flytt til "Gjort" og legg til en
ADR-post under §2 hvis det innebar et reelt valg.

1. **Onepark-adapter (MVP).** HTML-parsing av anleggslistene på
   onepark.no. Felter: navn, adresse, by, lat/lon (geokod hvis ikke
   eksponert). Skriv `data/normalized/onepark.csv`. Offline-test med
   lagret HTML-fikstur.
2. **Utvid `ParkingRecord` med prisfelter.** `price_per_hour`,
   `price_per_day`, `currency` — alle `None` by default. Oppdater
   `FIELDS`, CSV-skriver, README-tabell og en ADR-post her.
3. **Oslo kommune-adapter.** Identifiser riktig GeoJSON-datasett på
   data.oslo.kommune.no (start med beboerparkering / avgiftssoner).
   Mapper polygon → representativt punkt + sonenavn.
4. **Aimo Park-adapter.** Undersøk app-backend; HTML som fallback.
5. **Kryssreferanse på koordinater.** Match operatør-anlegg mot
   Parkeringsregisteret innen ~50 m for å bygge én logisk rad per
   fysisk anlegg. Vurder om dette skal bo i en egen `merge.py`.
6. **Bytt CSV → SQLite.** Behold CSV-eksport som artefakt. Trigger:
   3+ kilder integrert.
7. **Datakvalitetstester.** Andel med koordinater, lat/lon innenfor
   Oslo bbox, ingen duplikat-`id`-er, ikke-tomme `name`.
8. **Schedulering.** GitHub Actions: daglig ingest, commit normaliserte
   CSV-er for historikk-diff.

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
