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

# The blocking eval gate, exactly as CI runs it. Free, offline, no credentials.
eval-gate:
	python3 $(EVAL)/ci_gate.py

# Same gate, but warnings are failures — this is what the nightly runs.
eval-gate-strict:
	python3 $(EVAL)/ci_gate.py --base HEAD~1 --strict

# Mine trace spans into eval case stubs. Free, offline, deterministic, $0.00.
# Its input is gitignored, so this is a local/nightly target, never a PR check.
trace-cases:
	python3 $(EVAL)/trace_cases.py --traces '$(EVAL)/results/node_eval_spans.jsonl'

trace-cases-dry:
	python3 $(EVAL)/trace_cases.py --traces '$(EVAL)/results/node_eval_spans.jsonl' --dry-run

# ---------------------------------------------------------------------------
# Local Kubernetes (kind). Raw manifests, no Helm — see infra/k8s/README.md.
# ---------------------------------------------------------------------------
K8S = infra/k8s
KIND_CLUSTER = noesis
K8S_NS = noesis

# Build the backend image and load it into the kind node's containerd.
# kind nodes cannot see your local Docker daemon's images without this.
k8s-load-image:
	docker build -t noesis-backend:dev services/backend
	kind load docker-image noesis-backend:dev --name $(KIND_CLUSTER)

# Apply everything in dependency order. Assumes the cluster, ingress-nginx and
# the noesis-secrets Secret already exist (steps 1-5 of infra/k8s/README.md).
k8s-up:
	kubectl apply -f $(K8S)/00-namespace.yaml
	kubectl apply -f $(K8S)/01-configmap.yaml
	kubectl apply -f $(K8S)/10-redis-statefulset.yaml
	kubectl apply -f $(K8S)/20-api-deployment.yaml
	kubectl apply -f $(K8S)/21-worker-deployment.yaml
	kubectl apply -f $(K8S)/30-ingress.yaml
	kubectl apply -f $(K8S)/40-pdb.yaml
	kubectl -n $(K8S_NS) rollout status deploy/noesis-api --timeout=180s
	@echo "[k8s] ✓ up — curl http://noesis.local/healthz/ready"

# Deletes the workloads, not the cluster. The PVC goes with the namespace.
k8s-down:
	kubectl delete namespace $(K8S_NS) --ignore-not-found
	@echo "[k8s] namespace dropped. Full teardown: kind delete cluster --name $(KIND_CLUSTER)"

k8s-status:
	kubectl -n $(K8S_NS) get pods,svc,statefulset,pvc,ingress,pdb -o wide

# Tail both app workloads. Usage: make k8s-logs [COMPONENT=api|worker]
COMPONENT ?= api
k8s-logs:
	kubectl -n $(K8S_NS) logs -f -l app.kubernetes.io/component=$(COMPONENT) --tail=100 --max-log-requests=5

# Pull results back from container after a manual docker exec run
eval-pull-results:
	docker cp $(BACKEND):/app/scripts/eval/results ./scripts/eval/
	docker cp $(BACKEND):/app/scripts/eval/gold ./scripts/eval/

.PHONY: eval eval-quick eval-stability eval-sync eval-openreview eval-run eval-run-corpus \
        eval-judge eval-bootstrap-gold eval-pull-results \
        eval-build-corpus eval-build-all-corpora eval-heldout-check \
        benchmarks benchmarks-check eval-gate eval-gate-strict \
        trace-cases trace-cases-dry \
        k8s-up k8s-down k8s-load-image k8s-logs k8s-status
