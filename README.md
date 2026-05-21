# oslo-parking-finder

En liten Python-pipeline for å samle inn, normalisere og lagre data om
parkeringsplasser i Oslo. Målet er å bygge grunnlaget for en senere app
som finner **billig parkering** i Oslo.

Førsteversjonen fokuserer på datainnsamling og normalisering — ingen
frontend, ingen pris-beregning ennå.

## Prosjektmål

1. Bygg en utvidbar ingest-pipeline for parkeringsdata i Oslo.
2. Start med Statens vegvesen sitt **Parkeringsregister** som autoritativ
   kilde til hvor parkeringsplassene faktisk er.
3. Forbered adaptere for kommersielle operatører og kommunen, hvor
   prisinformasjon kan hentes senere:
   - Onepark
   - Aimo Park
   - Oslo kommune / Bil i Oslo
4. Hold koden enkel, modulær og lett å utvide.

## Datakilder

| Kilde | Status | Hva vi får | Notater |
|---|---|---|---|
| Statens vegvesen — Parkeringsregisteret | ✅ Implementert | Navn, adresse, koordinater, operatør, aktiv/deaktivert | Åpent API, ingen nøkkel |
| Onepark | 🟡 Stub | (senere) anlegg, adresse, priser | Ingen åpent API funnet — må parses fra onepark.no |
| Aimo Park | 🟡 Stub | (senere) anlegg, adresse, ev. ledig kapasitet | App-backend kan ha JSON-endepunkt |
| Oslo kommune / Bil i Oslo | 🟡 Stub | (senere) gateparkering, beboerparkering, soner | Sannsynligvis GeoJSON via [data.oslo.kommune.no](https://data.oslo.kommune.no/) |
| EasyPark | ⛔ Utelatt | — | Lukket API + bare betalingskanal. Se `adapters/easypark.py` for begrunnelse. |

### Parkeringsregisteret — endepunkt

Oppdaget via det offentlige kartet
([Parkeringsregisteret](https://www.vegvesen.no/trafikkinformasjon/reiseinformasjon/parkeringsregisteret)).
API-et er åpent, krever ingen autentisering.

- Liste: `GET https://parkreg-open.atlas.vegvesen.no/ws/no/vegvesen/veg/parkeringsomraade/parkeringsregisteret/v1/parkeringsomraade/`
- Detalj: `GET .../parkeringsomraade/{id}`
- Tilbydere: `GET .../parkeringstilbyder/aktive`

Listekallet returnerer **alle** områder i Norge (~21 000) på ett kall.
Vi filtrerer Oslo-poster lokalt på `poststed == "OSLO"`.

## Datamodell (normalisert CSV)

Felles felter for alle adaptere. Definert i
[`src/parking_app/models.py`](src/parking_app/models.py).

| Felt | Type | Beskrivelse |
|---|---|---|
| `name` | str | Anleggets/sonens navn |
| `address` | str \| null | Adresse, inkl. postnummer/-sted hvis tilgjengelig |
| `municipality` | str \| null | Kommune (best-effort fra `poststed`) |
| `lat` | float \| null | WGS84 breddegrad |
| `lon` | float \| null | WGS84 lengdegrad |
| `operator` | str \| null | Parkeringstilbyder |
| `source_url` | str \| null | URL som peker tilbake til kildedata |
| `source_type` | str | F.eks. `parkeringsregister`, `onepark` |
| `last_checked` | str | ISO 8601 UTC, satt ved normalisering |
| `paid_spaces` | int \| null | Avgiftsbelagte plasser (fra detalj-endepunkt) |
| `free_spaces` | int \| null | **Avgiftsfrie plasser** — grunnlaget for "gratis parkering" |
| `charging_spaces` | int \| null | Ladeplasser |
| `accessible_spaces` | int \| null | HC-plasser |
| `facility_type` | str \| null | F.eks. `LANGS_KJOREBANE`, `PARKERINGSHUS`, `AVGRENSET_OMRADE` |
| `is_park_and_ride` | bool \| null | Innfartsparkering (JA/NEI → True/False) |

Råpayload lagres alltid uendret i `data/raw/<source>_<ts>.json` for
revisjon/feilsøking.

## Kom i gang

Krever Python 3.10+.

```bash
cd oslo-parking-finder
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Kjør første ingest (Parkeringsregisteret, kun Oslo, kun aktive)
parking-ingest-register

# Alternativ: hele Norge, inkluder deaktiverte
parking-ingest-register --municipality '' --include-inactive

# Berik radene med kapasitet (gratis-plasser, lade, HC, innfartsparkering).
# Ett detalj-kall per anlegg — disk-cache i data/raw/details/ gjør re-kjøring rask.
parking-ingest-register-details              # ~2–3 min første gang
parking-ingest-register-details --limit 50   # rask røyk-test
parking-ingest-register-details --refresh    # ignorer cache

# Tester
pytest -q

# Hel-prosjekt verifikasjon (struktur + imports + pytest + CSV-sanity)
python scripts/verify.py
```

Etter kjøring:

- `data/raw/parkeringsregister_<timestamp>.json` — råpayload
- `data/normalized/parkeringsregister.csv` — normaliserte rader

Forventet resultat i dag:
- `parking-ingest-register`: ~21 000 hentet totalt, ~3 300 aktive Oslo-rader.
- `parking-ingest-register-details`: samme rader, beriket med kapasitet.
  Av ~3 300 Oslo-anlegg har **~1 700 minst én avgiftsfri plass**, ~570
  har ladeplasser, og ~30 er innfartsparkering.

## Prosjektstruktur

```
oslo-parking-finder/
├── README.md
├── pyproject.toml
├── data/
│   ├── raw/.gitkeep
│   └── normalized/.gitkeep
├── src/parking_app/
│   ├── __init__.py
│   ├── models.py            # ParkingRecord + felter
│   ├── storage.py           # save_raw / write_normalized_csv
│   ├── ingest/
│   │   └── fetch_register.py
│   └── adapters/
│       ├── __init__.py
│       ├── onepark.py        # stub
│       ├── aimopark.py       # stub
│       └── oslo_kommune.py   # stub
└── tests/
    └── test_normalize.py
```

## Antakelser

- **Kommune via poststed.** Parkeringsregisteret eksponerer `poststed`,
  ikke `kommune`. For Oslo er dette pålitelig fordi post-byen "OSLO"
  brukes konsekvent. For andre kommuner må vi senere geokode mot
  Kartverket eller bruke postnummer-til-kommune-tabell.
- **Kun aktive områder by default.** API-et returnerer både aktive og
  deaktiverte. Vi filtrerer på `deaktivert == null` (samme atferd som
  det offentlige kartet). Bruk `--include-inactive` for å se alt.
- **Prisinformasjon finnes ikke i registeret.** Parkeringsregisteret er
  en *registeret* over anlegg og tilbydere, ikke en pris-database.
  Pris må hentes fra hver operatør i neste fase.
- **Adresse er tekstuell.** Vi setter sammen `adresse, postnummer poststed`
  uten å validere mot Kartverket. Det er godt nok for visning.
- **Idempotent CSV.** Normalisert CSV skrives over hver kjøring. Råfiler
  er tidsstemplet og bevares.

## Foreslåtte neste steg

1. **Implementer Onepark-adapter.** Start med HTML-parsing av
   onepark.no's facility-lister. Berik med priser per anlegg.
2. **Implementer Oslo kommune-adapter.** Finn riktig dataset på
   data.oslo.kommune.no (beboerparkering, avgiftssoner). GeoJSON →
   ParkingRecord.
3. **Implementer Aimo Park-adapter.** Undersøk app-backend; fall back
   til HTML-parsing om nødvendig.
4. **Kryssreferanse på koordinater.** Match operatør-anlegg
   (Onepark/Aimo) mot Parkeringsregisteret via lat/lon (≤ ~50 m)
   for å bygge én rad per fysisk anlegg.
5. **Prismodell.** Utvid `ParkingRecord` med `price_per_hour`,
   `price_per_day`, `currency`, `payment_methods`. Hold bakoverkompatibilitet
   ved å tillate `None`.
6. **Vedvarende lagring.** Når antall kilder vokser: bytt ut CSV med
   SQLite (`data/parking.db`), behold CSV-eksport som artefakt.
7. **Schedulering.** Cron eller GitHub Actions: kjør ingest daglig,
   commit normaliserte CSV-er for diff/historikk.
8. **Datakvalitetstester.** Sjekk f.eks. at >95 % har koordinater,
   at lat/lon ligger innenfor Oslo bbox, ingen duplikat-id-er.

## Prosjektlogg

Se [`PROJECT_NOTES.md`](PROJECT_NOTES.md) for mål, beslutninger,
arbeidsregler og neste planlagte steg. Den filen er det levende
prosjektminnet og leses først ved gjenopptakelse av arbeid.

## Lisens

MIT.
