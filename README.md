# Meridian Ops

Meridian Ops is a PII-safe control plane for the full breakdown workflow: ticket ingestion, context enrichment, deterministic rule evaluation, replacement selection, work-order drafting, approval-gated communication, and a sanitized audit trail.

## Start

```powershell
python -m pip install -r requirements.txt
python run_pipeline.py
python app.py
```

Open `http://127.0.0.1:8000`. The UI includes Overview, Breakdowns, Context, Rules, Audit, and System pages.

The public repository intentionally excludes Meridian's supplied challenge corpus because it contains personal data. Place the supplied files beside the application files before running locally; in production, provide these sources through an approved private data store.

Run the same command a second time to demonstrate idempotency. Approve an eligible draft exactly once:

```powershell
python approve.py TKT-0001
```

For a clean local demo reset (only the generated state/outboxes, never source data):

```powershell
python run_pipeline.py --fresh
```

Process an evaluator surprise file:

```powershell
python run_pipeline.py path\to\surprise.json
```

Compatible JSON arrays and `tickets`, `records`, `data`, or `items` wrappers are accepted. Safe aliases such as `id`, `truck`, `hub`, `distance`, and `dest` are adapted explicitly. Ambiguous input is quarantined, never guessed.

## Architecture

```text
source files -> PII-safe ingestion -> canonical entities -> validation/quarantine
             -> persistent idempotency -> deterministic rules -> eligibility/ranking
             -> work order + pending draft -> human approval -> sent + audit
```

SQLite (`meridian_state.db`) is the durable idempotency store. The action uniqueness constraint permits one work order, one pending draft, one sent communication, and one quarantine action per stable ticket identity. JSONL outboxes are written only after durable action insertion succeeds.

## Evidence and safety

- Vehicle identity strips case, whitespace, and punctuation; display registration remains separate.
- Fleet master is authoritative for vehicle attributes/year; maintenance log for dated maintenance; dispatcher interview for operating rules. Emails corroborate rules but never override fleet or maintenance facts.
- Trips are historical (2018), so they are context evidence only, never current vehicle location.
- Personal names, phones, licence numbers, and Aadhaar values are discarded at ingestion. Outputs/audit are scanned for phone, Aadhaar, and licence patterns.
- Beyond-50km incidents remain `NEEDS_REVIEW` because the supplied corpus has no hub-distance source. This is safe containment, not fabricated routing.
- No LLM has decision or send authority. Every decision is deterministic and cited.

## Rules

`meridian_ops.py` exposes R1-R11 from the dispatcher interview: Delhi NCR winter BS6, winter hills, Shakti SLA, Vertex gate, Apex rotation, Orion year/cold-chain condition, monsoon ETA, origin/nearest-hub sourcing, service grounding, temporary repair containment, and new-driver night pairing.

## Outputs

- `outputs/work_orders.jsonl`
- `outputs/comms_pending.jsonl`
- `outputs/comms_sent.jsonl`
- `outputs/quarantine.jsonl`
- `audit/audit.jsonl`

## Tests

```powershell
python -m unittest -v
```

The suite covers normalization, duplicates/reruns, malformed quarantine, alias adaptation, beyond-50km containment, approval idempotency, grounded context, and PII scan coverage.

## Known limitation

The supplied corpus has no live hub-distance or availability feed. A production integration would add this source to resolve nearest-hub decisions beyond 50km; Meridian Ops deliberately refuses to invent it.

## Demo fixtures

Because the original challenge corpus contains personal data, this repository ships with **synthetic demo fixtures** derived from the documented Meridian rules (R1–R11):

- `tickets.json`
- `fleet_master.csv`
- `drivers_roster.csv`
- `maintenance_log.xlsx`
- `meridian_trips.csv`
- `dispatcher_interview.txt`

These allow the full pipeline (ingest → rules → selection → work order → approval → audit) to be demonstrated without exposing real PII. Replace them with the official challenge files when available; the loader and schema adapter remain compatible.

Runtime state (SQLite + outboxes) is written under `/tmp/meridian_ops_state` in constrained environments.
