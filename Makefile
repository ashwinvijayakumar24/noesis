BACKEND = noesis-backend
REPO_ROOT := $(shell pwd)
EVAL = scripts/eval
LIMIT ?= 15
VENUE ?= ICLR.cc/2024/Conference
PAPERS ?=
PAPER_ARGS = $(if $(PAPERS),--paper-ids $(PAPERS),)

# Sync scripts/ and pdfs/ into the running container (no volume mount needed)
# Run this once after any change to scripts/eval/ or after adding PDFs
eval-sync:
	BACKEND=$(BACKEND) REPO_ROOT="$(REPO_ROOT)" $(EVAL)/_verify_live.sh
	@echo "[eval] ✓ Synced scripts/ and pdfs/ into $(BACKEND)"

eval-openreview:
	BACKEND=$(BACKEND) REPO_ROOT="$(REPO_ROOT)" $(EVAL)/_verify_live.sh
	docker exec -e EVAL_STATE_DIR=/app/scripts/eval/cache/state -e EVAL_SKIP_EXTERNAL_SOURCE_DISCOVERY=1 -e EVAL_DISABLE_PRE_REVIEWER_HALT=1 $(BACKEND) python /app/scripts/eval/run_eval.py \
		--openreview --venue $(VENUE) --limit $(LIMIT) $(PAPER_ARGS)
	docker cp $(BACKEND):/app/scripts/eval/results ./scripts/eval/
	docker cp $(BACKEND):/app/scripts/eval/openreview ./scripts/eval/
	docker cp $(BACKEND):/app/scripts/eval/cache ./scripts/eval/

eval-heldout-check:
	python3 $(EVAL)/check_heldout.py

# Run a single draft (no corpus). Run eval-sync first if scripts changed.
# Usage: make eval-run DRAFT=pdfs/draft3.pdf
eval-run: eval-sync
	docker exec $(BACKEND) python /app/scripts/eval/run_harness.py \
		--draft $(DRAFT) --no-corpus

# Run a single draft with a named corpus
# Usage: make eval-run-corpus DRAFT=pdfs/draft3.pdf CORPUS=corpus_a
eval-run-corpus: eval-sync
	docker exec $(BACKEND) python /app/scripts/eval/run_harness.py \
		--draft $(DRAFT) --corpus $(CORPUS)

# Score an export against a gold file
# Usage: make eval-judge EXPORT=scripts/eval/results/x.json GOLD=scripts/eval/gold/draft3.gold.md
eval-judge:
	docker exec $(BACKEND) python /app/scripts/eval/judge.py \
		--export /app/$(EXPORT) --gold /app/$(GOLD)

# Bootstrap a candidate gold critique for a draft
# Usage: make eval-bootstrap-gold DRAFT=pdfs/draft3.pdf
eval-bootstrap-gold: eval-sync
	docker exec $(BACKEND) python /app/scripts/eval/judge.py \
		--bootstrap-gold /app/$(DRAFT)
	@echo "[eval] Copy results back: docker cp $(BACKEND):/app/scripts/eval/gold ./scripts/eval/"

# Full eval matrix (all drafts × corpora in config.yaml)
eval: eval-sync
	docker exec $(BACKEND) python /app/scripts/eval/run_eval.py
	docker cp $(BACKEND):/app/scripts/eval/results ./scripts/eval/

# Quick eval — first 3 drafts only
eval-quick: eval-sync
	docker exec $(BACKEND) python /app/scripts/eval/run_eval.py --quick
	docker cp $(BACKEND):/app/scripts/eval/results ./scripts/eval/

# Stability test — 3 runs per cell
eval-stability: eval-sync
	docker exec $(BACKEND) python /app/scripts/eval/run_eval.py --stability 3
	docker cp $(BACKEND):/app/scripts/eval/results ./scripts/eval/

# Build corpus for one draft by auto-downloading cited papers from OpenAlex
# Usage: make eval-build-corpus DRAFT=pdfs/draft1.pdf
eval-build-corpus: eval-sync
	docker exec $(BACKEND) python /app/scripts/eval/build_corpus.py \
		--draft $(DRAFT)
	docker cp $(BACKEND):/app/scripts/eval/corpora ./scripts/eval/
	docker cp $(BACKEND):/app/scripts/eval/config.yaml ./scripts/eval/
	@echo "[eval] Corpus synced back. Re-run eval-sync before next eval run."

# Build corpora for ALL drafts in scripts/eval/pdfs/
eval-build-all-corpora: eval-sync
	docker exec $(BACKEND) python /app/scripts/eval/build_corpus.py --all
	docker cp $(BACKEND):/app/scripts/eval/corpora ./scripts/eval/
	docker cp $(BACKEND):/app/scripts/eval/config.yaml ./scripts/eval/
	@echo "[eval] All corpora synced back. Re-run eval-sync before next eval run."

# Regenerate the tracked benchmark board from every local measurement sink.
# Runs on the host (no container): it reads JSONL files under scripts/eval/ and
# writes the board into docs/.
benchmarks:
	python3 $(EVAL)/benchmarks.py
	@echo "[eval] Board: docs/BENCHMARKS.md + docs/benchmarks.json — commit both."

# Fail if the tracked board is out of date with the local sinks
benchmarks-check:
	python3 $(EVAL)/benchmarks.py --check

# Pull results back from container after a manual docker exec run
eval-pull-results:
	docker cp $(BACKEND):/app/scripts/eval/results ./scripts/eval/
	docker cp $(BACKEND):/app/scripts/eval/gold ./scripts/eval/

.PHONY: eval eval-quick eval-stability eval-sync eval-openreview eval-run eval-run-corpus \
        eval-judge eval-bootstrap-gold eval-pull-results \
        eval-build-corpus eval-build-all-corpora eval-heldout-check \
        benchmarks benchmarks-check
