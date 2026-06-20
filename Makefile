BACKEND = noesis-backend
REPO_ROOT := $(shell pwd)
EVAL = scripts/eval

# Sync scripts/ and pdfs/ into the running container (no volume mount needed)
# Run this once after any change to scripts/eval/ or after adding PDFs
eval-sync:
	docker cp "$(REPO_ROOT)/scripts" $(BACKEND):/app/scripts
	-docker cp "$(REPO_ROOT)/pdfs" $(BACKEND):/app/pdfs 2>/dev/null || true
	@echo "[eval] ✓ Synced scripts/ and pdfs/ into $(BACKEND)"

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

# Pull results back from container after a manual docker exec run
eval-pull-results:
	docker cp $(BACKEND):/app/scripts/eval/results ./scripts/eval/
	docker cp $(BACKEND):/app/scripts/eval/gold ./scripts/eval/

.PHONY: eval eval-quick eval-stability eval-sync eval-run eval-run-corpus \
        eval-judge eval-bootstrap-gold eval-pull-results \
        eval-build-corpus eval-build-all-corpora
