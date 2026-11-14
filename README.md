# ORBITRA

ORBITRA is a proposed software system for energy-aware satellite-to-drone change verification. The prototype is intended to turn image-derived change candidates into explainable inspection or computation decisions under a limited energy budget. It does not claim to control or fly a physical drone.

## Project structure

- `ARES/` - Energy modelling and intelligent decision-making. ARES tracks candidate state, estimates action costs, enforces a return-energy reserve, evaluates policies B0-B4, and records decisions.
- `SatQuery/` - Satellite/image-query and computer-vision work. SatQuery produces candidate change records for ARES.

Each developer owns their module folder. Cross-module changes should be coordinated and documented in both module READMEs.

## Integration contract

The module owners will agree on and version a candidate-record schema before final integration. The contract should specify field names and types, image/pair identifiers, region geometry and coordinate reference, units where applicable, confidence, uncertainty, predicted change, schema version, and missing-value behavior. A sample record and validation behavior belong in the module documentation. ARES should consume SatQuery output without manual edits.

The end-to-end prototype should load and validate candidate records, apply an ARES policy under a defined energy budget and return reserve, log the chosen action and its rationale/cost/feasibility, and show resulting candidate status in a dashboard or report. Recapture and verification outcomes must be labelled as simulated when real repeated UAV observations are unavailable.

## Development plan

The synopsis schedule is 32 weeks. The current ownership plan is:

| Weeks | SatQuery | ARES | Joint checkpoint |
| --- | --- | --- | --- |
| 1-3 | Dataset audit and change-detection literature | Energy-aware UAV research and simulator outline | Confirm scope and interface draft |
| 4-7 | Loader, preprocessing, baseline detector | Candidate-state architecture | Freeze schema v1 and sample |
| 8-11 | Candidate regions, confidence, uncertainty | Importance and action-outcome models | Review fields and end-to-end sample |
| 12-15 | Export and alignment checks | Energy model and return-reserve filter | First integration |
| 16-19 | Detector/schema integration | Policies B0-B4 and decision logs | Simulated decision cycle |
| 20-23 | Vision evaluation and error analysis | Matched-budget experiments and ablations | Compare results |
| 24-32 | Integration support and vision validation | Dashboard and end-to-end integration | Validate, report, present |

This is a plan, not a claim that implementation or experiments are complete. The synopsis lists three students; this repository plan assigns module ownership to two active developers and does not assign or remove the third listed student.

## Repository workflow

Both module owners work on the shared `main` branch in their separate folders. Pull the latest `main` before starting and before pushing. Coordinate pushes so they do not overlap. Keep commits focused; do not force-push, reset shared history, or commit in the other owner's folder without agreement.

For each meaningful update, update the relevant module README with what changed, run instructions, checks performed, limitations, and interface changes. The ARES README is the ongoing implementation log for ARES. During integration, update both module READMEs and this overview as needed.

## Current status

Repository scaffold and initial documentation created. No module implementation, experiments, or measured results are claimed yet. See `ARES/README.md` and `SatQuery/README.md` for current module status.
