# Data governance

Project brief, section 5: who owns the data we use, on which terms, whether
it contains personal data, and what happens with it after the course.

## Sources and terms

### SMHI, weather observations

- Owner: SMHI, the Swedish Meteorological and Hydrological Institute.
- Licence: Creative Commons Erkännande 4.0 SE (CC BY 4.0). Terms:
  https://www.smhi.se/data/om-smhis-data/villkor-for-anvandning,
  read on 15 September 2026.
- Requirements: name SMHI as the source and say if the data was changed;
  use only documented APIs; no mass downloads.
- Republishing: allowed. The terms page says we may copy and distribute
  SMHI's open data and create adaptations, also for commercial use, as
  long as we name SMHI as the source and say if the data was changed.
  Checked on 15 September 2026. We keep a snapshot of the raw
  observations in `data/historik_vader.csv.gz` in this repository. The
  repository is private today.
- How we comply: we use the documented metobs API at
  opendata-download-metobs.smhi.se, station 97400 Stockholm-Bromma,
  parameters 1 (temperature) and 4 (wind). `daily_ingest.py` makes one
  call per parameter per run, once a day. `data/fetch_historik.py` made
  one call per station, parameter and period for the history. Raw
  payloads are stored unchanged in `raw__weather`. Daily means, minima
  and maxima are our derived values, computed in the feature step.

### elprisetjustnu.se, day-ahead electricity prices

- Owner: elprisetjustnu.se. The prices originate from ENTSO-E in EUR,
  converted to SEK with rates from exchangeratesapi.io, and may differ
  slightly from the official prices. All prices exclude VAT, fees and
  taxes.
- Terms: there is no formal licence. The API page says the API is open
  and free, and asks that elprisetjustnu.se is credited as the source
  when the data is used publicly.
  https://www.elprisetjustnu.se/elpris-api, read on 15 September 2026.
- Republishing: not addressed. The API page says the data is freely
  available to anyone, for anything, and asks that we credit
  elprisetjustnu.se as the source when we use it publicly. It says
  nothing specific about republishing raw data. Checked on
  15 September 2026. We keep a snapshot of the raw prices in
  `data/historik_elpris.csv.gz` in this repository. The repository is
  private today.
- How we comply: one call per day and price area (SE3), raw payloads
  stored unchanged in `raw__elpris`. We credit elprisetjustnu.se here
  and in the model card.

## Personal data

No. Weather observations describe the air at one public station.
Day-ahead prices are market prices for a whole bidding zone, published
for everyone; they say nothing about any household's consumption or
contract. No table in Neon, no file in this repository and no model
input refers to a person. The only personal data around the project are
the team members' GitHub accounts in the commit history, which is the
normal public record of a repository. Credentials (`DATABASE_URL`,
`HF_TOKEN`) are secrets, not personal data, and are kept out of the
repository.

## Where the data lives

- Neon Postgres, one project owned by David and shared with the team:
  `raw__elpris`, `raw__weather`, the `silver__` views and `feat__daily`.
- This repository: `data/historik_elpris.csv.gz` and
  `data/historik_vader.csv.gz`, snapshots of the same public sources.
- Hugging Face `aim25s-team7/elpris-se3-team-7`: the trained model, no
  data.
- GitHub Actions logs: row counts only.

## After the course

The team takes the final decision in Sprint 3, see Decision 9 #71.
Until then this is our proposal:

- The repository stays in the `ithogskolan-aim25` organisation, which
  the school owns, including the csv.gz snapshots. SMHI's licence
  allows this; elprisetjustnu.se's API page does not address it.
- The Neon project is deleted by its owner when the course ends. Nothing
  in it exists only there; both sources can be fetched again.
- The Hugging Face repository stays as a portfolio piece or is deleted;
  the team decides.
- The daily GitHub Actions job is disabled at the same time, so nothing
  is fetched after the course.
