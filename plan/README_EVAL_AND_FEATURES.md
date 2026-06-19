# Noesis — Eval Automation + Feature Hardening Plan-of-Plans

**Authored by Opus 4.8 (2026-06-17). Built by Sonnet 4.6 in fresh per-plan sessions.**

## Why this exists
Draft-analysis features mostly EXIST but leak before reaching the researcher
(the `synthesize_report` tail drops citation passages, external sources, and
meta-reviewer priorities). The architecture problem is plumbing + reliability,
not missing features. We cannot fix reliability blind, so we build the eval
harness FIRST, then fix the tail, then add the moat features.

## Decisions locked (2026-06-17)
- **Judge model**: GPT-5.2 via existing in-repo OpenAI client (`get_openai_client`).
  - Self-grading-bias guard: judge ALWAYS scores against an approved `gold/`
    critique, never free-form; rubric forces verbatim-evidence per sub-score.
- **Gold critiques**: LLM-drafted, human-approved. Bootstrap with an LLM, you
  edit/approve once, then frozen as ground truth.
- **Build workflow**: Opus writes plans (done). You run Sonnet in a FRESH
  session per plan file. Do NOT spawn Sonnet subagents from an Opus session —
  keeps Opus context hot and wastes the tokens we're conserving.

## Build order (dependency-first)
| Plan | Title | Why this order |
|------|-------|----------------|
| `00_eval_harness.md`      | Headless run + judge + scoreboard | Measurement first. Everything else is verified against it. |
| `01_synthesis_tail_fix.md`| Stop the report dropping computed signal | Cheapest, highest impact. Most "features" already compute; they die here. |
| `02_refs_extraction.md`   | "You forgot to cite X,Y,Z" | Reuses existing BibTeX-resolution pipeline. Zero-friction corpus. |
| `03_external_discovery.md`| Fix weak "missed papers" + OpenAlex citation graph | Upgrade keyword S2 search; stop over-suppression. |
| `04_citation_misrep.md`   | "Cited paper doesn't support claim" | New category moat. Few competitors do it. |
| `05_determinism_gates.md` | Per-agent output gates + eval thresholds | Locks in reliability so regressions are caught by `00`. |

## How to run a build session (per plan)
```
1. /model sonnet
2. New session in repo root.
3. "Read plan/<NN>_*.md and implement it. Run the verify command. Report scores."
4. Sonnet builds + runs `python scripts/eval/run_eval.py`, iterates until acceptance met.
```

## Definition of done (whole effort)
- `python scripts/eval/run_eval.py` runs all drafts × corpora headless, no UI.
- Mean judge score ≥ 8.5/10 across the draft set, hallucination flags = 0.
- Every computed finding (citation passage, external source, meta priority)
  reaches the final export. No tail drops.
