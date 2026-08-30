# Meridian Ops

PII-safe control plane for the full breakdown-to-resolution workflow:

**ticket → context → rules → vehicle decision → work order → communication draft → approval → audit**

Built for the Synq AI Forward Deployment Challenge.

## One-command start

```bash
python -m pip install -r requirements.txt
python run_pipeline.py --fresh   # optional clean slate
python app.py
```

Open **http://127.0.0.1:8000**

## Demo flow (judge over the shoulder)

1. **Overview** — live metrics (breakdowns, processed, quarantined, duplicates, PII = 0)
2. Click **RUN PIPELINE** — watch stages light up (ingest → validate → … → approval gate)
3. Open a ticket → see **candidates rejected with rule + source**, then **WHY THIS VEHICLE?**
4. Click **APPROVE & SEND** → status becomes SENT
5. Run pipeline again → **0 new actions**, duplicates counted (idempotency)
6. **PROCESS NEW FILE** — drop a surprise JSON schema; safe normalize or quarantine
7. **ASK CONTEXT** — e.g. `Why was vehicle HR55CD5678 rejected?` or `R9`

## What is implemented

| Requirement | Status |
|-------------|--------|
| Exactly-once work orders & messages | ✅ SQLite action uniqueness |
| Full re-run produces identical outputs | ✅ Durable state |
| Quarantine malformed tickets | ✅ Never crashes the run |
| Surprise-file schema tolerance | ✅ Alias adapter + quarantine |
| Deterministic rules R1–R11 with citations | ✅ From dispatcher interview |
| Vehicle eligibility (season, service, hub, year…) | ✅ Hard constraints |
| Human approval gate before send | ✅ Idempotent approve |
| Audit trail (no raw PII) | ✅ JSONL + PII scan |
| Grounded context answers | ✅ Ticket / vehicle / rule lookup |
| One-command deploy | ✅ |

## Architecture

```
source files → PII-safe ingestion → canonical entities → validate/quarantine
             → persistent idempotency → deterministic rules → eligibility/ranking
             → work order + pending draft → human approval → sent + audit
```

No LLM has decision authority. Safety-critical choices are rule-engine only.

## Demo fixtures

The official challenge corpus contains personal data and is excluded from the public repo.
This repo ships **synthetic fixtures** derived from the documented Meridian rules so the full pipeline is runnable and demonstrable:

- `tickets.json` (duplicates, missing fields, alias schema, beyond-50km)
- `fleet_master.csv`
- `drivers_roster.csv`
- `maintenance_log.xlsx` (mixed Hindi-English notes)
- `meridian_trips.csv`
- `dispatcher_interview.txt`

Replace with official files when available; loaders remain compatible.

Runtime state lives under `/tmp/meridian_ops_state`.

## Tests

```bash
python -m unittest -v
```

## Outputs

- `outputs/work_orders.jsonl`
- `outputs/comms_pending.jsonl` / `comms_sent.jsonl`
- `outputs/quarantine.jsonl`
- `audit/audit.jsonl`
