# Plan 00 — Headless Eval Harness (run + judge + scoreboard)

**Goal:** Run any draft PDF through the real LangGraph pipeline in Docker with a
chosen literature corpus, export the result, score it against an approved gold
critique with GPT-5.2, and aggregate scores — all from the CLI. No frontend.

**Build this FIRST. It is the measurement everything else is verified against.**

## Context / existing assets (reuse, don't reinvent)
- Workflow entry: `app.services.draft_analysis_langgraph.analyze_draft_with_langgraph(draft_id, project_id, user_id, draft_content, ...)`
- Corpus/doc ingest: `app.services.rag_ingest.ingest_document(document_id, project_id)`
- Draft RAG ingest: `app.services.draft_rag_integration.ingest_draft_for_rag(draft_id, project_id)`
- Text extract: `app.services.draft_processing.extract_text(file_bytes, file_type)`
- Existing export: `scripts/export_latest_draft_analysis.py` (read its Supabase
  read-side helpers — reuse `select_related`, `latest_analysis_row`, etc.)
- Test drafts: `pdfs/draft1.pdf` … `pdfs/draft10.pdf`
- OpenAI client: `app.core.openai_client.get_openai_client` / `get_completion_params`
  (GPT-5.2 uses `max_completion_tokens`, NOT `max_tokens`).
- The upload→analyze path the frontend uses lives in
  `app/api/routes/drafts.py` — READ it to mirror draft-row + project setup
  exactly (file_url, file_type, paper_type, active_analysis_run_id).

## Deliverables (new dir `scripts/eval/`)
```
scripts/eval/
  run_harness.py      # one draft + one corpus -> export JSON
  judge.py            # (export, gold) -> rubric score JSON
  run_eval.py         # loop drafts x corpora -> scoreboard + regression diff
  corpora/            # corpus_<name>/*.pdf  (literature sets)
  gold/               # draft<N>.gold.md     (approved reference critiques)
  results/            # per-run export JSON + scoreboard.json (gitignored)
  config.yaml         # matrix: which drafts, which corpora, thresholds
```

## Step 1 — `run_harness.py`
CLI: `python scripts/eval/run_harness.py --draft pdfs/draft3.pdf --corpus corpus_a [--no-corpus]`
1. Run INSIDE the backend container (has env + Supabase + OpenAI). Provide a
   thin wrapper: `docker exec noesis-backend python scripts/eval/run_harness.py ...`
   OR a make target. Document both.
2. Create a throwaway eval project (`project_id`) + eval user, or reuse a fixed
   `EVAL_PROJECT_ID` from env. Tag rows so cleanup is trivial.
3. Ingest the corpus: for each PDF in `corpora/<corpus>/`, insert a `documents`
   row + `ingest_document(...)`. Mirror what `routes/drafts.py` / the documents
   route does. Skip if `--no-corpus`.
4. Insert a `drafts` row for the test PDF (upload bytes to storage exactly like
   the route, set file_url/file_type). Extract text via `extract_text`.
5. Call `analyze_draft_with_langgraph(draft_id, project_id, user_id, draft_content)`.
6. Export via the read helpers from `export_latest_draft_analysis.py` into
   `results/<draft>__<corpus>__<ts>.json`. Include EVERYTHING: claims,
   citations w/ matched passages, external_sources, gaps, revision_tasks,
   reviewer panel, meta review, synthesis_report.
7. Idempotent: clear prior eval rows for that draft before re-run
   (reuse `_clear_analysis_outputs`).

## Step 2 — `judge.py`
CLI: `python scripts/eval/judge.py --export results/x.json --gold gold/draft3.gold.md`
- System prompt = strict academic meta-reviewer. Inputs: Noesis export + gold.
- Rubric, each scored 0–10 with a REQUIRED verbatim-evidence quote from the export:
  1. **Grounding** — claims/findings tied to real draft text + real sources.
  2. **Hallucination** (inverse) — any invented source/quote/number = hard 0 on this dim + flag.
  3. **Coverage** — did it catch what gold caught? (recall vs gold)
  4. **Citation accuracy** — citation verdicts correct vs gold.
  5. **Actionability** — revision tasks specific + anchored.
  6. **No architecture failure** — no dropped/empty sections, no nulls where content expected.
- Output JSON: `{overall: float, dims: {...}, hallucinations: [...], misses: [...], notes: str}`.
- Use GPT-5.2 via `get_openai_client` + structured output (mirror
  `parse_chat_completion_with_retries_sync` usage in `nodes/citation_mapping.py`).
- Determinism: temperature pinned low, score must cite evidence so re-runs are stable.

## Step 3 — `run_eval.py`
- Read `config.yaml` matrix (drafts × corpora + per-dim thresholds).
- For each cell: run_harness → judge. Collect into `results/scoreboard.json`.
- Print a table: draft | corpus | overall | halluc count | worst dim.
- Regression gate: diff vs previous `scoreboard.json`; exit non-zero if mean
  drops > 0.5 or any new hallucination appears. (CI-friendly.)

## Step 4 — gold bootstrap helper
- `python scripts/eval/judge.py --bootstrap-gold pdfs/draft3.pdf` → produce a
  CANDIDATE gold critique (LLM-drafted) into `gold/draft3.gold.draft.md` for the
  human to edit → rename to `gold/draft3.gold.md` when approved.
- Bootstrap 2–3 anchor drafts first; expand later.

## Acceptance
- [ ] `docker exec noesis-backend python scripts/eval/run_harness.py --draft pdfs/draft3.pdf --corpus corpus_a` produces a complete export JSON.
- [ ] `judge.py` scores it against a gold file and emits valid rubric JSON.
- [ ] `run_eval.py` runs ≥3 drafts headless and writes `scoreboard.json` with a printed table.
- [ ] Re-running the same cell twice yields overall scores within ±0.5 (determinism check).
- [ ] Zero frontend interaction anywhere in the loop.

## Verify
```
docker exec noesis-backend python scripts/eval/run_eval.py --quick
cat scripts/eval/results/scoreboard.json
```

## Notes / guardrails
- Keep eval data isolated (EVAL_PROJECT_ID) so it never pollutes real user data.
- Add `scripts/eval/results/` to `.gitignore`. Commit `corpora/`, `gold/`, `config.yaml`.
- Do NOT mock the pipeline — this runs the REAL graph. That is the point.
