# Sprint 1, 24/8 to 11/9

## Planned
Daily ingestion of SE3 prices and station 97400 weather into Neon with Silver views, the feature table feat__daily filled by a feature step in the same daily job, a baseline model registered on Hugging Face Hub with its metrics, and the project board as the team's way of working.

## Done
All of it. The daily job has run on schedule since 4/9 and refreshes feat__daily since 11/9 (771 rows, one per price area and day). The baseline model and its model card are on Hugging Face Hub, train.py trains from feat__daily, and the governance note is in docs/governance.md. 44 of 51 cards closed.

## Moved to Sprint 2, and why
The training gate and its schedule (#46, #47, #49) need the registered model's metrics and a green feature step first, both in place only on the last day. The predictions table (#30) belongs with the inference service. Parent cards #11 and #29 follow them.

## Retro actions
#76 mark each DoD row as teacher requirement or team choice (Linus, started 11/9). #77 plan Sprint 2 around the lesson topics with fewer, larger cards (planning 15/9).
