# OVERNIGHT_RUN.md

Autonomous run started 2026-08-01. Appended to as each agent lands. Every entry
records what was measured, its `n`, what was committed, and what it cost.

**Budget:** $50 nominal, slight overage authorised. **$22.75 spent at start.**

**Stop conditions:** all queued work complete, or a fatal bug (data loss, a
broken `main`, production contacted, or a budget breach beyond tolerance).

---

## Queue

| # | agent | scope | budget | status |
|---|---|---|---|---|
| 1 | **H2H** | agent vs Noesis DAG on shared labels — the project's own acceptance test, never run | $8.00 | 🔄 running |
| 2 | **P1** | PDF parsed twice per upload — 68.66 s p50, 39.2% of the user-visible path | $3.00 | 🔄 running |
| 3 | **P2** | `injection_v2` with write-shaped payloads — makes the gate's real-model factor measurable | $4.00 | 🔄 running |
| 4 | **P4** | first-stage recall — 86.5% of misses were never in the candidate pool | $4.00 | 🔄 running |
| 5 | **P5** | loop detection: exercise it under real pressure, or retire the claim | $4.00 | 🔄 running |
| 6 | **P3** | size-aware step allocation — 19/30 workers still starve | $3.00 | ⏸ held |

**P3 is held deliberately.** It changes `OrchestratorConfig`, which H2H is
measuring right now. Landing it mid-flight would silently change the system
under test — the exact failure this project hit five times already. It launches
when H2H reports.

---

## Standing rules for every agent tonight

Unchanged from the day's work, restated because they are what makes the output
worth anything:

1. Every metric carries its `n`. Every `recall@k` carries its **recomputed** ceiling.
2. Results append-only, keyed by config hash. Nothing is differenced across hashes.
3. A capability not observed firing in the logs is not a capability.
4. Negative results ship. A defense that does not reduce ASR, an optimisation
   that does not help, a detector that never binds — all get published as such.
5. Nothing is weakened to make a result land.
6. Production Supabase is never contacted. Local only.

---

## Log

### Start — 2026-08-01

State at handoff: harness **475 tests** green and standalone; Noesis backend
**1068 passed** with 2 known pre-existing failures. Both repos pushed. Board
regenerated and verified byte-identical across two runs.

Completed before tonight: Phase A, Phase B, Phase B.5, the retrieval track
(reranking, contentless, chunk ceiling), user-visible latency, durable resume,
and three production fixes (`663e0f6` reranker no-op, `0ee82d5` fixture label
leak, checkpointer manuscript leak).
