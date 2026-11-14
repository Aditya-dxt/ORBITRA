# ARES

**Owner:** Energy Modelling & Intelligent Decision-Making Lead

ARES consumes candidate change records produced by SatQuery and decides what to inspect, compute, defer, or stop while respecting the mission energy budget and return reserve.

## Responsibilities

- Track candidate ID, confidence, uncertainty, importance, evidence history, and status.
- Define importance scoring separately from model confidence.
- Estimate flight, capture, computation, and communication energy costs with documented units and assumptions.
- Enforce a return-energy reserve plus an agreed safety margin.
- Model recapture, stronger-model inference, and human review actions, including estimated costs and possible outcomes.
- Implement and explain B0-B4: fixed pass, uncertainty first, adaptive computation, joint policy, and greedy benefit-per-energy.
- Log selected action, reason, estimated benefit, energy cost, and reserve feasibility.
- Provide a mission simulator and explainable dashboard or report.

## Interface dependency

The SatQuery owner and ARES owner must agree on the versioned candidate schema before finalizing the loader. Confirm field names/types, image/pair identifiers, region geometry and coordinate reference, units, schema version, missing values, and validation errors. ARES should load the agreed sample records without manual edits.

## Development sequence

| Weeks | Planned ARES work | Status |
| --- | --- | --- |
| 1-3 | Review energy-aware UAV research; outline simulator | Not started |
| 4-7 | Candidate-state architecture and decision input model | Not started |
| 8-11 | Importance scoring and action outcome models | Not started |
| 12-15 | Energy model and return-reserve filter | Not started |
| 16-19 | Policies B0-B4 and decision logging | Not started |
| 20-23 | Matched-budget policy experiments and ablations | Not started |
| 24-32 | Dashboard, end-to-end integration, reporting | Not started |

## Running implementation log

Update this section for every meaningful ARES change. Record the date, summary, changed files, run instructions, checks performed, limitations, and any interface changes. Do not report an item as complete until it has been implemented and checked. Keep simulated outcomes distinct from measured results.

### Initial state - 2026-11-14

- Created the ARES module scaffold and documented its planned scope.
- No ARES code or experiments exist yet.
- Next: inspect the agreed SatQuery sample/schema with the module owner, then implement schema validation and candidate-state foundations.
