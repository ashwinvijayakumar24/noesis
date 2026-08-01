# SPEND_LEDGER.md

Hard ceiling for the harness + retrieval effort: **$50**.

Enforced per track via `MAX_SPEND_USD` and `NOESIS_LLM_MAX_LLS`. A run that
would cross its ceiling **aborts loudly**. It does not truncate — a truncated
run silently changes the `n` behind every number it produced, which is worse
than no number at all.

## Allocation

| Track | Ceiling | Main line items |
|---|---|---|
| H — Phase A eval | $14.00 | ~20 trajectory runs × 4 context-ceiling arms |
| H — Phase B eval | $16.00 | orchestrator + N workers, worker-count study, DAG baseline re-runs |
| H — B.5 / injection | $8.00 | injection eval set, gate on/off arms |
| R — retrieval | $6.00 | re-ingest embeddings only; the cross-encoder is local and free |
| E — end-to-end latency | $4.00 | n=3–5 real pipeline runs |
| reserve | $2.00 | |
| **total** | **$50.00** | |

## Standing caveat, inherited

> Every cost figure in this project is a **lower bound**. `match.py` bypassed
> the spend guardrails until recently, so its OpenAI calls were never recorded
> in any sink. Nothing downstream can correct for this. A figure with any
> unpriced call additionally renders as `>=`.

The new harness repo does not inherit this defect: `harness/model.py` returns
`Usage` from every call at the call site rather than reconstructing cost
afterwards, and `Usage.priced` propagates a lower-bound flag through addition.

## Actual spend

Filled in by each agent as it reports. Empty rows are unstarted work, not zero
spend — an absence, not a zero.

| Track | Agent | Budgeted | Actual | Notes |
|---|---|---|---|---|
| R | R1 contentless | $0.00 | **$0.0000** | zero-LLM by construction; asserted in test |
| R | R2 chunk ceiling | $6.00 | **$0.2906** | embeddings only; 4.8% of ceiling |
| R | R3 rerank | $2.00 | **$0.6128** | local cross-encoder $0.00; spend is the gpt-5-mini arms |
| R | P4 first-stage | $4.00 | **$1.1539** | 0 unpriced |
| E | E1 end-to-end | $4.00 | **$2.1431** | 130 calls, 0 unpriced, 3 sessions, 7 measured runs. Includes 2 discarded warmups and one failed Docling attempt ($0.2692) — everything charged, nothing omitted |
| E | P1 double parse | $3.00 | **$1.9953** | both arms, n=4 each |
| H | N11 checkpointer | $6.00 | **$1.4658** | fixture replay preferred over live runs |
| H | ADPT noesis adapter | $2.00 | **$0.1040** | $0.0729 estimated (embed usage discarded upstream), $0.0159 measured |
| H | M1 phase A/B | $14.00 | **$8.5973** | 252 paid runs, **zero unpriced calls** |
| H | Q1 quote pipeline | $3.00 | **$0.4301** | 207 calls |
| H | W1 worker yield | $4.00 | **$2.5642** | 3 arms + a label-classification pass |
| H | C3 injection v1 | $8.00 | **$4.2800** | `priced=False`, renders `>=` |
| H | C4 gate interlock | $3.50 | **$2.2654** | the gate arms themselves were free (`ScriptedModel`) |
| H | P2 injection v2 | $4.00 | **$3.5544** | includes $2.4303 spent discovering a delivery bug a free check finds in seconds |
| H | P3 size-aware alloc | $4.00 | **$2.3925** | 9 orchestrations per arm |
| H | P5 loop detection | $4.00 | **$1.6412** | trace mining was free; spend is the induction runs |
| H | H2H single vs DAG | $8.00 | **$2.2057** | includes $0.6152 buying a confound bound |
| H | H2H2 orchestrated vs DAG | $5.00 | **≈$3.77** | $1.27 of it bought nothing — a `TypeError` in an optional diagnostic destroyed a scored arm before the sink write |
| | **TOTAL** | **$50.00** | **≈$39.45** | 21% unspent |

## What the spend bought, and what it wasted

Three line items are worth reading as lessons rather than costs:

- **$2.4303 (P2)** discovering that a 200-char snippet cap ate the attack payload
  behind 177 characters of benign lead — something a free delivery check finds in
  four seconds. A `measure_delivery` pass now runs *before* anything is bought.
- **$1.27 (H2H2)** lost when a `TypeError` in an **optional** sensitivity
  diagnostic destroyed a completed, scored 12-run arm before it reached the sink.
  Fixed by ordering: write the row first, run diagnostics last, inside a `try`.
- **$0.6152 (H2H)** spent deliberately to *bound a confound* rather than assert
  it — re-running the matcher at a relaxed threshold to test whether finding
  length explained the recall gap. That is the one of the three that was worth
  every cent.
