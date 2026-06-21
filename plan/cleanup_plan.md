# Codebase Cleanup Plan

## Context
Codebase cluttered with stale exports, old eval run outputs, a committed 1.3G venv, old planning docs, and one-off scripts. Clutter makes it harder for Claude/Codex to read context. Goal: bare-minimum tree. **Codex is actively running (through Phase 4b) in `scripts/eval/` and `services/backend/app/workflows/draft_analysis/` — those are OFF LIMITS.**

## DO NOT TOUCH (active work / required by tools)
- `scripts/eval/**` — Codex live here (new: fetch_openreview.py, atomize_reviews.py, match.py, judge_openreview.py, node_eval.py, pipeline_cache.py, openreview/, cache/). Old eval (`judge.py`, `build_corpus.py`, `gold/`) retires only at plan Phase 9 — **keep until then**.
- `scripts/eval/pdfs/`, `scripts/eval/corpora/` — eval inputs (gitignored PDFs, keep dirs).
- `services/backend/app/workflows/draft_analysis/**` — pipeline under eval.
- `AGENTS.md` — Codex reads this by convention. KEEP.
- `codex_prompt.md`, `plan/openreview_eval_plan.md` — current task. KEEP.
- `CLAUDE.md`/`claude.md`, `README.md`, `Makefile`, `infra/`, `services/`, `.github/`.

---

## Bucket A — Safe immediate delete (untracked, gitignored, regenerable) → ~1.32 GB
Pure local `rm` — not in git, nothing references them.
- `.spike-venv/` — **1.3G** committed-nowhere venv. `rm -rf` (gitignored).
- `exports/` — 2.6M old draft-analysis exports (json+md). User: "exports should be gone." `rm -rf` (gitignored).
- `scripts/eval/results/draft*__*.json` — 17M old GPT-gold run outputs. `rm`. **Preserve any `openreview_*.json`** Codex may have written.
- `pdfs/` (root) — empty, gitignored. `rm -rf`.
- `prompt.md`, `prompt_openreview_eval.md` — untracked scratch; task consumed into plan. `rm`.
- `issues.md`, `scripts/proof_meta_owns_tasks.py` — untracked scratch. `rm`.
- stray `__pycache__/`, `*.pyc` — purge.

## Bucket B — Tracked, recommend `git rm` (old/superseded docs + spike scripts) → ~450K
- `historical/` — 40 tracked files, May 28 archive (old plans, pitch decks, mini-plans). `git rm -r`.
- `general_issues.md`, `PDF_PARSING_RFC.md` — old root docs, superseded.
- `scripts/parser_spike.py` — spike script (only self/gitignore refs).
- `scripts/export_latest_draft_analysis.py` — superseded by eval harness export.

## Bucket C — Old plan docs (optional; low value, low size)
`plan/00_eval_harness.md … 05_determinism_gates.md`, `plan/README_EVAL_AND_FEATURES.md`, `plan/pipeline_refactor_plan.md` document the CURRENT pipeline Codex is evaluating. Small (8 files). Recommend **move to `plan/archive/`** rather than delete — keeps design context without cluttering active `plan/` root. Or `git rm` if you want them fully gone.

## Bucket D — Needs verification before delete (DEFER until Codex idle)
Dead UI/backend components. Chat feature already fully removed (verified: no `*chat*` files, no ChatBox/ChatMessage refs in frontend). Remaining orphans (104 frontend .tsx, backend services) require an import-graph scan to delete safely. **Do NOT guess-delete.** Run a dedicated orphan-detection pass (Explore agent grepping each component's inbound imports) when Codex is not mid-run, to avoid races and false positives from dynamic/string registration.

---

## Execution order
1. Bucket A (instant space win, zero risk) → reclaims ~1.32G.
2. Bucket B (`git rm`, one commit: "chore: remove stale archive + spike scripts").
3. Bucket C (move to archive or rm — user choice).
4. Bucket D — separate session after Codex done; verify-then-delete.

## Verification
- After A/B: `git status` clean except intended deletions; `make eval-*` / backend still import (no removed file was referenced — confirmed for Bucket A/B).
- Codex unaffected: nothing in `scripts/eval/` or `draft_analysis/` touched.
