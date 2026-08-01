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
| R | R1 contentless | $0.00 | | zero-LLM by construction; asserted in test |
| R | R2 chunk ceiling | $6.00 | | embeddings only |
| R | R3 rerank | $2.00 | | local cross-encoder, $0.00 expected |
| E | E1 end-to-end | $4.00 | **$2.1431** | 130 calls, 0 unpriced, 3 sessions, 7 measured runs. Includes 2 discarded warmups and one failed Docling attempt ($0.2692) — everything charged, nothing omitted. $1.8569 unspent: the spread is environmental, not sampling. Detail: `scripts/eval/E2E_LATENCY.md` §Cost |
| H | N11 checkpointer | $6.00 | | prefers fixture replay over live runs |
