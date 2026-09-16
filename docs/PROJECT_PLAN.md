# Team 7 Project Plan

> Team 7, SE3 / TARGET=mean. Sprint 1: 24/8 to 10/9.
> Board: https://github.com/orgs/ithogskolan-aim25/projects/42
> Last updated 2026-09-02. The board is the live truth; this document
> explains the why and links every card.

## Project Goal

We are building a system that autonomously fetches fresh electricity price
and weather data for SE3 from public APIs, transforms it into features,
retrains the model on a schedule, exposes the model as a service that can
be queried over the internet to predict tomorrow's average electricity
price, and logs and tracks the quality of its own predictions over time.

The system consists of six components:

- **A) Feature pipeline**: ingest raw data and transform it into
  model-ready features
- **B) Training pipeline**: retrain the model on a schedule from the
  feature store
- **C) Inference service**: expose the trained model as a service
  queryable over the internet
- **D) Traceability**: track data and model lineage (which data and code
  version produced which model)
- **E) Monitoring**: log predictions and track their quality over time
- **F) CI/CD and code review**: automated testing, deployment, and
  review gates for all changes

Sprint 1 builds A and B, and designs D; C and E come later; F is already
enforced via PR gates.



## Current Status

Done:

- working electricity ingestion
- working historical weather data ingestion
- raw data stored in PostgreSQL
- Docker tested for the ingestion service
- SE3 weather station 97400 tested and confirmed (historical data)
- baseline model and exploration notebook run against real SE3/97400
  data, independently by Juan and Linus. `train.py` itself has not yet
  been run on real data (see card 5)
- Juan's baseline ingestion pipeline merged to main 1/9 (13:46,
  approved by Md Ruhul Amin)
- Sprint 1 board filled 1/9 to 2/9: 7 main cards, 4 decision issues,
  30 sub-issues with Definition of Done as checklists, all in Sprint 1

Agreed 1/9:

- Team split: Juan → fetch (#22), David → backfill (#23), Md Ruhul
  Amin + Bijoy Sarker → silver/clean view (#4), Linus → Scrum Master,
  project plan and board
- New branches (fetch, backfill, silver) to be created from the updated
  main

Decided 1/9 (#17, closed): one shared database for the whole team,
administered through David's Neon project. See Open Decisions below.



## Open Decisions

Items the team needs to resolve. Each decision is an issue with label
`decision`: context, options, decision, date. It is closed when the
decision is taken, and this plan is updated in a PR that links the issue.

Decided:

- **Neon project: shared vs. separate** (#17, closed 2/9): one shared
  database, administered through David's Neon project. Decided in the
  team chat 1/9 14:42. `db/schema.sql` applied and the backfill loaded
  2/9.

Still open:

- **Training data: actuals or forecast-like values?** (#18, card 3):
  inference-time weather must be a forecast, not observed; whether
  training data should match is still open.
- **Quantifying real forecast-error impact on MAE** (#19, card 3): the
  synthetic-noise experiment showed ~flat MAE; real forecast error is
  unmeasured.
- **Forecast ingestion (`metfcst`) card ownership** (#20, card 3): needed
  for inference, not yet assigned to a card.



## Sprint 1 Board Structure

Based on the GitHub Project board, the teacher's requirements, and what
we learned from the baseline. On the board since 2/9. Every main card
is a parent issue; every subtask is a sub-issue whose body holds the
Definition of Done as a checklist, so the board's "Sub-issues
progress" field shows how far each card has come.

The board numbers the cards in pipeline order, which differs from the
card numbers in this document. The issue numbers are the same
everywhere and are what counts.

| Board | This plan | Issue |
|---|---|---|
| 1. Fetch and backfill | card 7 | #21 |
| 2. Validate and flag raw data | card 1 | #24 |
| 3. Create clean view | card 2 | #4 |
| 4. Feature engineering | card 3 | #5 |
| 5. Schedule daily pipeline | card 4 | #10 |
| 6. Build training pipeline | card 5 | #11 |
| 7. Design traceability | card 6 | #29 |

Sub-issues carry the board number as a prefix (2.1, 2.2, ...) in the
order the work is done; the lists below does *not* follow the same order, 
please refer to the board for the live and true plan.



### 1. Validate and flag raw data (#24)

Main card. Purpose: check incoming data, flag problems, never block
insertion into raw. Duplicates across separate ingestion runs are
expected (append-only bronze, resolved by card 2's clean views). Only
a duplicate within one fetch is a genuine anomaly worth flagging.

Subtasks:

- Validate electricity data (#25)
  - DoD: required fields present · timestamps parse · no duplicates
    within a single fetched payload · price thresholds documented
    (negative prices allowed, not an error)
- Validate weather data (#26)
  - DoD: required fields present · timestamps parse · no duplicates
    within a single fetched payload · G/Y quality-code distribution
    logged
  - DoD (gaps): an absent row and a present-but-empty value count as the
    same gap · gaps in the last 30 days flagged as critical (that is the
    window we predict on), older gaps just logged · build on
    `check_weather_coverage.py` (starter repo) instead of rewriting its
    gap logic
- Handle NaN before it hits the database (#27)
  - DoD: missing weather values converted to `null` before JSON
    serialization. `json.dumps(NaN)` produces invalid JSON that
    Postgres rejects with an error that never mentions NaN (see starter
    repo's `build_weather_payload`)
- Flag, never reject (#28)
  - DoD: failed rows still land in raw · flag storage mechanism (column
    vs. log table) decided
- Document the validation rule (#52)
  - DoD: one sentence in `docs/` explaining which validation rule we
    chose and why that one · the sentence names the flag mechanism from
    #28 · any team member can explain it at stand-up. Added 2/9: the
    Friday 4/9 self-study requires exactly this sentence



### 2. Create clean view for weather and price data (#4)

Existing card. **Md Ruhul Amin** has a local version (31/8), needs
pushing for review. Reference: `db/views.sql` in the starter repo.

Subtasks:

- Weather clean view (#32)
  - DoD: correct types · picks the latest ingestion per natural key
    (station, parameter, observed_at): not row-level dedup · long
    format, one row per station/parameter/observation, no pivot to wide
    (that is a feature decision, see card 3) · UTC handling correct
    (`tz_localize`, not `tz_convert`) · `Kvalitet` and `Stationsnummer`
    preserved
- Price clean view (#33)
  - DoD: correct types · picks the latest ingestion per natural key
    (price_area, price_date) · UTC handling correct (`utc=True` parse)
- Acceptance test (#34)
  - DoD: run the backfill twice · `raw__` tables MUST grow (append-only)
    · clean views MUST NOT grow (latest-per-key wins)

Raw tables stay unchanged.



### 3. Feature engineering (#5)

Existing main card.

Subtasks:

- Decide what a feature row contains (#12)
  - DoD: inference-time weather = forecast, not observed
  - Discussion point (team decision): training data: actuals or
    forecast-like values?
- Create table (SQL) (#13)
- Fill table with data (#14)
- Align electricity/weather timestamps (#35)
  - DoD: daily aggregation reconciles hourly vs. 15-minute resolution
- Handle missing weather data (#36)
  - DoD: interpolation cutoff set (candidate: ≤6h): pending team
    approval
- Ingest forecast data (`metfcst`) (#37)
  - DoD: card ownership decided (this card or a new one)
- Verify generated feature data (#38)
  - DoD: e.g. `tomorrow_temp_mean` populated, plausible range

One feature row = the information needed for one prediction.



### 4. Schedule daily data and feature pipeline (#10)

Existing card (renamed from `run ingestion automatically every day`). Purpose: one
scheduled job per day that ingests fresh data and updates the feature
table: in that order.

Subtasks:

- Practice the mechanics first (#39) (starter repo: `hello.yml`,
  `daily_ingest_throwaway.py` + `ingest_throwaway.yaml`)
  - DoD: a `workflow_dispatch` run goes green with no schedule yet ·
    `DATABASE_URL` set as a repo secret (prints as `***` in the log),
    `PRICE_AREA` set as a repo variable (prints plainly) · one
    deliberately broken run observed, so the failure mode is known
    before it matters on the real job
- Schedule daily ingestion (electricity + weather observations) (#40)
  - DoD: runs unattended on a schedule · DB credentials via repo
    secrets, never in code · a failed run is visible (log/notification),
    not silent
- Add feature-table update as the next step in the same job (#41)
  - DoD: runs only after successful ingestion · re-runs are safe
    (idempotent: no duplicate rows on rerun/backfill)
- Choose run time (#42)
  - DoD: run time set after the day-ahead price publication time,
    verified against the elpris API we actually use · GitHub Actions
    cron is UTC (no DST). Document the chosen time in both UTC and
    Swedish local time
- Verify that the scheduled process works (#43)
  - DoD: at least one unattended run observed end-to-end · new rows in
    raw and feature table confirmed

Mechanism is GitHub Actions cron. That is what Thursday's lecture and
the starter repo's practice exercise both teach, not an open choice
between tools. Exact run time set after the choices above.



### 5. Build training pipeline (#11)

Existing main card. Purpose: retrain from the Postgres feature table
instead of CSV, and register every result as a traceable version.

Subtasks:

- Read features from PostgreSQL (#44)
  - DoD: `train.py` reads the feature table (card 3) instead of the
    CSV files · feature table delivers exactly the `FEATURES` columns
    plus the label · CSV loading and in-script feature building removed
- Retrain the baseline model (#45)
  - DoD: first documented run on real SE3 data with MAE / naive MAE /
    n_train recorded. Station 97400 is already on main in `train.py`,
    `fetch_historik.py` and `build_notebook.py` (commit c5288c3, merged
    1/9 in PR #8); only a docstring line in `fetch_historik.py` still
    mentions 98230
- Evaluate the new model (#46)
  - DoD: chronological split kept, never random · test window dates
    logged with the metrics
- Compare with baselines (#47)
  - DoD: must beat naive MAE ("tomorrow = today") · compared with the
    previous registered version · team decision: register worse models
    or not
- Register a new model version (#48)
  - DoD: shared Hugging Face account/org set up (Linus already has one:
    reuse or invite the team) · model pushed to Hugging Face Hub as a
    new version (teacher's spec, limitation #7) · metadata includes
    trained_at, metrics, n_train, git commit, training data window
- Schedule the training run (#49)
  - DoD: runs via GitHub Actions on its own schedule, separate from
    card 4's daily ingestion job (retraining does not need to run
    daily) · frequency decided by the team · DB and Hugging Face
    credentials via repo secrets, same pattern as card 4

The pipeline must run unattended without arguments, so the schedule
above can call it directly.



### 6. Design traceability (predictions table) (#29)

Main card. Component D requires every past prediction to answer four
questions: which data it was built on, which code produced it (git
commit), which model version was used, and when it was made.

Subtasks:

- Design the predictions table schema (#30)
  - DoD: columns cover all four questions above · references the model
    version registered in card 5 (Hugging Face Hub version id) · schema
    reviewed by the team before any code writes to it
- Confirm scope (#31)
  - DoD: agreed that populating this table depends on the inference
    service (component C, out of scope for Sprint 1): this card
    delivers the schema design only



### 7. Fetch and backfill raw SE3 data into Postgres (#21)

Main card, time-critical. Purpose: get real SE3 data (weather station
97400) into `raw__elpris` and `raw__weather` before Thursday 3/9, so
that the clean views (card 2), the feature table (card 3) and the first
real training run (card 5) have data. From Thursday on, the daily fetch
is handled by the scheduled job (card 4); this card is the one-off run
up to that point. The Neon decision (#17) was taken 1/9: shared
database on David's Neon project. Fetch (#22) closed 2/9 after PR #51;
backfill (#23) loaded 2/9, PR to main pending.

Subtasks:

- Fetch current SE3 data with the merged ingestion (#22, Juan)
  - DoD: merged `ingestion.py` run against the agreed Neon project ·
    electricity and weather rows for SE3 / 97400 confirmed, row counts
    logged · run repeated at least once: raw tables grow, nothing
    overwritten
- Backfill historical SE3 data (#23, David)
  - DoD: `db/schema.sql` applied on the agreed Neon project · backfill
    run for the agreed window, from-date documented · row counts per
    table logged · rerun is append-only · used as the input for card
    2's acceptance test (#34)



## Board Housekeeping (done 1/9)

- #3 closed as duplicate of #2. #1 and #2 closed as completed (ingestion
  merged 1/9); the "Item closed" workflow moved them to Done.
  
- Sprint field renamed and aligned with the course: Sprint 1 24/8 to
  10/9, Sprint 2 14/9 to 24/9, Sprint 3 28/9 to 8/10. Reviews and
  retros fall on the last day of each sprint.
  
- "In review" is reserved for work that is finished but not yet merged.

  

## How We Work the Board

- **Planned work** lives in Sprint 1 cards. Moving a card between
  sprints is a scope decision, made at stand-up, never silently.
- **Unplanned work** (a bug, a new requirement, a discovery) becomes an
  issue with label `unplanned`. Auto-add puts it on the board without a
  sprint; the Triage view (filter `no:sprint`) is the inbox the Scrum
  Master empties at stand-up: into Sprint 1 (then something else moves
  out) or left in the backlog.
- **Decisions** that change the plan are `decision` issues, closed with
  the outcome (see Open Decisions).
- **Sprint health** for the teacher and the team is reported as a
  project Status update (On track / At risk / Off track) once a week
  and whenever the risk picture changes.
- **Retrospectives** will be written to `docs/retro/`, one file per sprint.



## Sprint 1 Flow

```text
Before Thursday 3/9 (card 7, one-off):
  Fetch + backfill → Raw data

Scheduled daily (card 4):
  Raw data → Validate → Clean → Feature engineering → Feature table

Training pipeline (card 5, own GitHub Actions schedule):
  Feature table → Retrain → Evaluate → Model version

Inference service: not built in Sprint 1
  (would write to the predictions table designed in card 6)
```

## Out of Scope for Sprint 1

For Sprint 1 we are not focusing on:

- final dashboard
- advanced model optimization
- full production deployment, including the inference service itself
  (component C): Sprint 1 delivers a model version, not a queryable
  endpoint

Open decisions affecting scope are tracked in Open Decisions above.

The priority is to create a reliable path from incoming data to model
training.
