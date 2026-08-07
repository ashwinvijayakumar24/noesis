#!/usr/bin/env bash
#
# break_deps.sh — the probe demonstration.
#
# One question, answered empirically: what is the difference between a
# readiness probe and a liveness probe?
#
# The textbook answer ("readiness controls traffic, liveness controls
# restarts") is easy to recite and easy to get wrong in a manifest. This script
# induces the SAME fault class twice — a health endpoint returns non-200 — and
# records that Kubernetes responds in two completely different ways:
#
#   PHASE 1  Redis goes away. /healthz/ready 503s (it checks Redis).
#            /healthz/live keeps returning 200 (it checks the process only).
#            => pod leaves the Service endpoints, restartCount stays 0,
#               phase stays Running. The pod is parked, not punished.
#            When Redis comes back the pod rejoins with zero restarts. No
#            state was lost, no cold start was paid.
#
#   PHASE 2  /healthz/live is made to fail (probe repointed at a 404 path).
#            => kubelet kills and restarts the container. restartCount climbs.
#               Repeat it and the pod enters CrashLoopBackOff.
#
# The failure mode this demonstrates the cost of: if liveness had probed Redis
# too — which is the single most common Kubernetes health-check mistake — then
# PHASE 1 would have produced PHASE 2's behaviour. Every API pod would have
# been killed simultaneously for a fault none of them caused and none of them
# could fix by restarting, turning a recoverable dependency blip into a
# self-inflicted CrashLoopBackOff across the whole Deployment, right at the
# moment the dependency comes back and the cold starts pile on.
#
# Safe to run repeatedly: every mutation is reverted in a trap, and the script
# is idempotent (it re-asserts desired state rather than toggling).
#
# Usage:
#   scripts/k8s/break_deps.sh                 # both phases
#   scripts/k8s/break_deps.sh --skip-liveness # phase 1 only (non-destructive)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/k8s/_guard.sh
source "$SCRIPT_DIR/_guard.sh"

NS="$K8S_NAMESPACE"
API_DEPLOY="noesis-api"
API_SVC="noesis-api"
REDIS_STS="noesis-redis"

# ---------------------------------------------------------------------------
# LABEL SELECTORS — get these wrong and every pod-level number below is a
# silent zero rather than an error.
#
# The manifests label pods with the recommended two-part scheme:
#   app.kubernetes.io/name=noesis            (the APPLICATION)
#   app.kubernetes.io/component=api|worker|redis   (the ROLE within it)
# The Deployment is *named* noesis-api, but no pod carries
# `app.kubernetes.io/name=noesis-api`. An earlier version of this script
# selected on exactly that, so `kubectl get pods -l ...` matched nothing,
# printed "No resources found", and every jsonpath sum over it evaluated to
# the empty string — which this script's arithmetic then reported as 0.
# A selector that matches nothing is indistinguishable from a healthy zero
# unless you look for it, so both selectors are named constants now and
# assert_selector_matches() below fails loudly if either stops resolving.
# ---------------------------------------------------------------------------
API_SELECTOR="app.kubernetes.io/name=noesis,app.kubernetes.io/component=api"
REDIS_SELECTOR="app.kubernetes.io/name=noesis,app.kubernetes.io/component=redis"

# The selector the pod-level observers use. PHASE 2 narrows this to the
# post-patch ReplicaSet (see there); everything else leaves it alone.
POD_SELECTOR="$API_SELECTOR"

# How long to wait for each observable transition before giving up.
READY_TIMEOUT=120
RECOVER_TIMEOUT=180
LIVENESS_TIMEOUT=240
POLL_INTERVAL=3

# Plain `if`, not `[[ ... ]] && VAR=1`: under set -e a bare &&-list whose
# condition is false returns non-zero and kills the script.
SKIP_LIVENESS=0
if [[ "${1:-}" == "--skip-liveness" ]]; then SKIP_LIVENESS=1; fi

require_kind_context

# ---------------------------------------------------------------------------
# Observers. Each returns one scalar so the poll loop can print a table.
# ---------------------------------------------------------------------------

# A pod list that matches nothing looks exactly like a healthy zero once it
# has been through `wc` or a sum. Fail loudly instead.
assert_selector_matches() {
  local sel="$1" what="$2" n
  n="$(kubectl get pods -n "$NS" -l "$sel" -o name 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$n" == "0" ]]; then
    echo "[k8s] FATAL: selector '$sel' matches no pods ($what)." >&2
    echo "[k8s]        Every pod-level number in this run would be a false 0." >&2
    exit 1
  fi
}

# "2" when both replicas pass readiness, "0" when neither does.
#
# `.status.readyReplicas` is ABSENT — not 0 — when no replica is ready, so the
# jsonpath yields the empty string and "$(api_ready_count)/2" rendered as "/2"
# in the summary. Normalise to 0 here, once, rather than at each call site.
api_ready_count() {
  local v
  v="$(kubectl get deployment "$API_DEPLOY" -n "$NS" \
    -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
  echo "${v:-0}"
}

api_replica_count() {
  local v
  v="$(kubectl get deployment "$API_DEPLOY" -n "$NS" \
    -o jsonpath='{.status.replicas}' 2>/dev/null || true)"
  echo "${v:-0}"
}

# The Service's backend list. THIS is the thing readiness actually controls:
# an unready pod is removed here, so no traffic is routed to it. Empty output
# means the Service has no backends and callers get a connection refusal.
api_endpoint_ips() {
  kubectl get endpoints "$API_SVC" -n "$NS" \
    -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || true
}

api_endpoint_count() {
  local ips
  ips="$(api_endpoint_ips)"
  if [[ -z "$ips" ]]; then
    echo 0
    return 0
  fi
  echo "$ips" | wc -w | tr -d ' '
}

# Summed restartCount across every api pod. The number that must NOT move in
# phase 1 and must move in phase 2.
#
# Selected by label AT EVERY SAMPLE, never from a pod-name list captured
# earlier: patching the pod template rolls a new ReplicaSet, so any pod name
# read before a patch is a tombstone a few seconds later.
api_restart_total() {
  local counts total=0 c
  counts="$(kubectl get pods -n "$NS" -l "$POD_SELECTOR" \
    -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}' 2>/dev/null || true)"
  for c in $counts; do total=$((total + c)); done
  echo "$total"
}

# Highest restartCount on any single pod. `> 0` on the post-patch ReplicaSet is
# the honest "the kubelet killed a container" signal — a sum can also be moved
# by an unrelated pod, a max cannot be mistaken for anything else.
api_restart_max() {
  local counts max=0 c
  counts="$(kubectl get pods -n "$NS" -l "$POD_SELECTOR" \
    -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}' 2>/dev/null || true)"
  for c in $counts; do if (( c > max )); then max="$c"; fi; done
  echo "$max"
}

# Distinct pod phases, e.g. "Running" or "Running Pending".
api_phases() {
  kubectl get pods -n "$NS" -l "$POD_SELECTOR" \
    -o jsonpath='{.items[*].status.phase}' 2>/dev/null | tr ' ' '\n' | sort -u | tr '\n' ',' | sed 's/,$//'
}

# Container waiting reasons, e.g. "CrashLoopBackOff". Empty when all running.
api_waiting_reasons() {
  kubectl get pods -n "$NS" -l "$POD_SELECTOR" \
    -o jsonpath='{.items[*].status.containerStatuses[*].state.waiting.reason}' 2>/dev/null \
    | tr ' ' '\n' | sort -u | tr '\n' ',' | sed 's/,$//'
}

# pod-template-hash of the ReplicaSet the Deployment is CURRENTLY rolling out.
#
# `deployment.kubernetes.io/revision` is stamped on the Deployment and on every
# ReplicaSet it has ever owned; the highest revision is the current one. Sorting
# numerically and taking the tail avoids a jsonpath filter expression (which
# needs the annotation key's dots escaped inside the predicate — easy to get
# subtly wrong and silently return nothing).
api_current_pod_hash() {
  kubectl get rs -n "$NS" -l "$API_SELECTOR" \
    -o jsonpath='{range .items[*]}{.metadata.annotations.deployment\.kubernetes\.io/revision}{" "}{.metadata.labels.pod-template-hash}{"\n"}{end}' \
    2>/dev/null | grep -E '^[0-9]+ ' | sort -n | tail -n 1 | awk '{print $2}'
}

row_header() {
  printf '  %-7s  %-9s  %-9s  %-13s  %-9s  %s\n' \
    "t(s)" "ready" "endpoints" "restartTotal" "phase" "waiting"
}

row() {
  local t="$1"
  printf '  %-7s  %-9s  %-9s  %-13s  %-9s  %s\n' \
    "$t" \
    "$(api_ready_count)/$(api_replica_count)" \
    "$(api_endpoint_count)" \
    "$(api_restart_total)" \
    "$(api_phases)" \
    "$(api_waiting_reasons)"
}

# Poll until `cond` (an expression evaluated by eval) is true, printing a row
# each interval. Returns 1 on timeout rather than exiting, so the summary still
# prints — a timeout is a result, not a crash.
poll_until() {
  local label="$1" timeout="$2" cond="$3"
  local start elapsed
  start="$SECONDS"
  row_header
  while :; do
    elapsed=$((SECONDS - start))
    row "$elapsed"
    if eval "$cond"; then
      echo "  -> $label after ${elapsed}s"
      return 0
    fi
    if (( elapsed >= timeout )); then
      echo "  -> TIMEOUT waiting for: $label (${timeout}s)"
      return 1
    fi
    sleep "$POLL_INTERVAL"
  done
}

banner() {
  echo
  echo "==============================================================="
  echo "$1"
  echo "==============================================================="
}

# ---------------------------------------------------------------------------
# Cleanup. Runs on any exit, including Ctrl-C, so a half-run never leaves the
# cluster broken.
# ---------------------------------------------------------------------------
LIVENESS_PATCHED=0

cleanup() {
  local rc=$?
  echo
  echo "[k8s] cleanup: restoring desired state"
  kubectl scale statefulset "$REDIS_STS" -n "$NS" --replicas=1 >/dev/null 2>&1 || true
  if (( LIVENESS_PATCHED == 1 )); then
    restore_liveness_probe || true
  fi
  exit "$rc"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# BASELINE
# ---------------------------------------------------------------------------
banner "BASELINE — everything healthy"

# Before anything is measured, prove the selectors resolve. Cheap, and it is
# the exact failure that made a previous run of this script report a confident
# restartTotal of 0 for a phase in which pods were demonstrably restarting.
assert_selector_matches "$API_SELECTOR" "the API pods"
assert_selector_matches "$REDIS_SELECTOR" "the Redis pod"

kubectl get pods -n "$NS" -o wide
echo
echo "Service endpoints (this is what readiness controls):"
kubectl get endpoints "$API_SVC" -n "$NS"
echo

BASE_READY="$(api_ready_count)"
BASE_ENDPOINTS="$(api_endpoint_count)"
BASE_RESTARTS="$(api_restart_total)"
BASE_PHASE="$(api_phases)"

echo "baseline: ready=$BASE_READY endpoints=$BASE_ENDPOINTS restartTotal=$BASE_RESTARTS phase=$BASE_PHASE"

if [[ "$BASE_ENDPOINTS" != "2" ]]; then
  echo "[k8s] WARNING: expected 2 endpoint addresses, got $BASE_ENDPOINTS."
  echo "[k8s]          The cluster is not at the contracted baseline; the"
  echo "[k8s]          numbers below are still real but read them with that"
  echo "[k8s]          in mind."
fi

# ---------------------------------------------------------------------------
# PHASE 1 — break the DEPENDENCY. Readiness should react; liveness must not.
# ---------------------------------------------------------------------------
banner "PHASE 1 — Redis removed (dependency fault)"

# WHY scale-to-zero rather than a NetworkPolicy:
#
#   1. Reversibility. `kubectl scale --replicas=1` restores the exact prior
#      state in one command with no object left behind. A NetworkPolicy has to
#      be deleted, and if the script dies between apply and delete, the cluster
#      is left silently firewalled — a much worse failure to inherit.
#   2. It actually works here. kind's default CNI (kindnet) does NOT enforce
#      NetworkPolicy. Applying one on a stock kind cluster is accepted by the
#      API server and then quietly does nothing, which would make this demo
#      produce a confident, wrong null result. Scaling the StatefulSet needs no
#      CNI cooperation at all.
#   3. The PVC survives, so Redis comes back with its data — the recovery half
#      of the demo stays honest.
#
# The tradeoff, stated: scale-to-zero removes DNS resolution too, so the
# backend sees a name-resolution failure rather than a connection timeout. Both
# are "Redis is unreachable" as far as /healthz/ready is concerned, but they
# are not the identical error string, and a readiness handler that only catches
# ConnectionError would pass this test and fail the real one. Worth checking
# the 503 body names the dependency (the contract says it does).

echo "Scaling statefulset/$REDIS_STS to 0 replicas..."
kubectl scale statefulset "$REDIS_STS" -n "$NS" --replicas=0
kubectl wait --for=delete pod -l "$REDIS_SELECTOR" -n "$NS" --timeout=90s || true
echo

echo "Watching the API. EXPECTED: ready -> 0, endpoints -> 0, restartTotal UNCHANGED."
# `|| true`: a timeout here is a RESULT worth printing in the summary, not a
# reason to abort before the summary exists.
poll_until "readiness dropped and endpoints emptied" "$READY_TIMEOUT" \
  '[[ "$(api_endpoint_count)" == "0" ]]' || true

P1_READY="$(api_ready_count)"
P1_ENDPOINTS="$(api_endpoint_count)"
P1_RESTARTS="$(api_restart_total)"
P1_PHASE="$(api_phases)"

echo
echo "Endpoints object with Redis down (the 'Subsets: <none>' is the point):"
kubectl get endpoints "$API_SVC" -n "$NS" -o wide || true
echo
echo "Readiness probe failure events (should name the failed dependency):"
kubectl get events -n "$NS" --field-selector reason=Unhealthy \
  --sort-by=.lastTimestamp -o wide 2>/dev/null | tail -n 5 || true

echo
echo "phase 1 result: ready=$P1_READY endpoints=$P1_ENDPOINTS restartTotal=$P1_RESTARTS phase=$P1_PHASE"
if [[ "$P1_RESTARTS" == "$BASE_RESTARTS" ]]; then
  echo "  restartCount did NOT move ($BASE_RESTARTS -> $P1_RESTARTS). Liveness correctly ignored the dependency."
else
  echo "  !! restartCount MOVED ($BASE_RESTARTS -> $P1_RESTARTS). Liveness is probing a dependency. This is the bug this build exists to prevent."
fi

# ---------------------------------------------------------------------------
# PHASE 1b — restore
# ---------------------------------------------------------------------------
banner "PHASE 1b — Redis restored (recovery, no restart ever happened)"

kubectl scale statefulset "$REDIS_STS" -n "$NS" --replicas=1
echo "Waiting for Redis to be ready..."
kubectl rollout status statefulset/"$REDIS_STS" -n "$NS" --timeout=120s || true
echo

poll_until "endpoints repopulated" "$RECOVER_TIMEOUT" \
  '[[ "$(api_endpoint_count)" == "'"$BASE_ENDPOINTS"'" ]]' || true

REC_READY="$(api_ready_count)"
REC_ENDPOINTS="$(api_endpoint_count)"
REC_RESTARTS="$(api_restart_total)"

echo
kubectl get endpoints "$API_SVC" -n "$NS"
echo
echo "recovered: ready=$REC_READY endpoints=$REC_ENDPOINTS restartTotal=$REC_RESTARTS"
echo "The pods that serve traffic now are the SAME pods that served it before:"
kubectl get pods -n "$NS" -l "$API_SELECTOR" \
  -o custom-columns='NAME:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,AGE:.metadata.creationTimestamp,READY:.status.conditions[?(@.type=="Ready")].status'

# ---------------------------------------------------------------------------
# PHASE 2 — break LIVENESS. Same class of signal, opposite response.
# ---------------------------------------------------------------------------

restore_liveness_probe() {
  echo "[k8s] restoring liveness probe path to /healthz/live"
  kubectl patch deployment "$API_DEPLOY" -n "$NS" --type=json -p \
    '[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/healthz/live"}]' \
    >/dev/null
  kubectl rollout status deployment/"$API_DEPLOY" -n "$NS" --timeout=180s || true
  LIVENESS_PATCHED=0
  # The restore rolls yet another ReplicaSet, so the phase-2 narrowing is stale
  # the moment this returns. Widen back to the whole Deployment.
  POD_SELECTOR="$API_SELECTOR"
}

L2_RESTARTS="(skipped)"
L2_WAITING="(skipped)"
L2_PHASE="(skipped)"
L2_BASE_RESTARTS="(skipped)"
L2_READY="-"
L2_ENDPOINTS="-"
L2_BASE_READY="-"
L2_BASE_ENDPOINTS="-"

if (( SKIP_LIVENESS == 1 )); then
  banner "PHASE 2 — SKIPPED (--skip-liveness)"
else
  banner "PHASE 2 — liveness made to fail (process fault)"

  # HOW, and why this way:
  #
  # The honest options were (a) kubectl exec and stall/kill the process, or
  # (b) repoint the liveness probe at a path that 404s. (a) does not actually
  # demonstrate the probe — killing PID 1 restarts the container whether a
  # liveness probe exists or not, so it proves nothing about liveness. (b)
  # leaves the process perfectly healthy and lets ONLY the probe verdict drive
  # the restart, which is exactly the variable under test.
  #
  # DISCLOSURE, because it changes how the numbers read: patching the probe
  # edits the pod template, so the Deployment rolls a NEW ReplicaSet and NEW
  # pods. Those new pods start at restartCount 0, and the pre-patch pods are
  # deleted. Phase 2's baseline is therefore the fresh pods' zero, not phase
  # 1's total. The observable that matters — restartCount climbing from 0
  # while the process itself is fine — is unaffected.
  #
  # This is also the trap an earlier version of this script fell into: it
  # summed restarts over a selector that resolved to nothing, so the baseline
  # AND the after-value were both a false 0 and the phase looked like a null
  # result while the events log was full of liveness failures. The counters
  # below are scoped to the post-patch ReplicaSet by pod-template-hash, so
  # nothing from the old generation can leak into them and nothing from the
  # new generation can be missed.

  echo "Repointing livenessProbe at /healthz/__deliberately-absent__ (404)..."
  kubectl patch deployment "$API_DEPLOY" -n "$NS" --type=json -p \
    '[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/healthz/__deliberately-absent__"}]' \
    >/dev/null
  LIVENESS_PATCHED=1

  # Wait for the new ReplicaSet to exist and place its pods before taking a
  # baseline. Note the rollout DOES complete: readiness still passes (only
  # /healthz/live was repointed), so the new pods go Ready normally and the old
  # ones retire. The kills come later, from the liveness probe, not the roll.
  L2_HASH=""
  for _ in $(seq 1 30); do
    L2_HASH="$(api_current_pod_hash)"
    if [[ -n "$L2_HASH" ]] && \
       kubectl get pods -n "$NS" -l "$API_SELECTOR,pod-template-hash=$L2_HASH" \
         -o name 2>/dev/null | grep -q .; then
      break
    fi
    sleep 2
  done

  if [[ -z "$L2_HASH" ]]; then
    echo "[k8s] WARNING: could not identify the post-patch ReplicaSet; falling"
    echo "[k8s]          back to the whole-Deployment selector."
  else
    # Narrow every pod-level observer to the post-patch generation.
    POD_SELECTOR="$API_SELECTOR,pod-template-hash=$L2_HASH"
    echo "post-patch ReplicaSet pod-template-hash=$L2_HASH; counting only its pods"
  fi

  kubectl rollout status deployment/"$API_DEPLOY" -n "$NS" --timeout=120s || true

  L2_BASE_RESTARTS="$(api_restart_total)"
  L2_BASE_READY="$(api_ready_count)/$(api_replica_count)"
  L2_BASE_ENDPOINTS="$(api_endpoint_count)"
  echo "new pods rolled; baseline for this phase: ready=$L2_BASE_READY endpoints=$L2_BASE_ENDPOINTS restartTotal=$L2_BASE_RESTARTS"
  echo

  # SUCCESS CONDITION: restartCount incremented on at least one post-patch pod.
  #
  # That single increment IS the demonstration — the kubelet decided a healthy
  # process was dead and killed it, purely on a probe verdict. CrashLoopBackOff
  # is not a different phenomenon, it is this same signal observed after
  # several more rounds, once the kubelet's restart backoff (10s, 20s, 40s ...)
  # has grown long enough that the container is caught *waiting* rather than
  # running. Waiting for it would add minutes and prove nothing extra, so it is
  # reported opportunistically below if it happens to appear, and is not the
  # condition this phase succeeds or fails on.
  #
  # TIMING, so the timeout is a considered number and not a guess:
  #   startupProbe   30 x 5s   must pass first (it probes /healthz/startup,
  #                            which is untouched, so it passes on the first
  #                            or second try)
  #   livenessProbe  5 x 15s = 75s of consecutive failures before the kill
  #   plus rollout scheduling and container start
  # Measured on kind: first restart lands ~85s after the patch, with the second
  # pod staggered ~12s behind. 240s leaves generous headroom; the previous
  # 120s ceiling on the CrashLoopBackOff wait could not have succeeded even in
  # principle.
  echo "Watching. EXPECTED: ready/endpoints stay healthy between kills while restartCount climbs."

  poll_until "restartCount incremented on at least one pod" "$LIVENESS_TIMEOUT" \
    '(( $(api_restart_max) >= 1 ))' || true

  L2_RESTARTS="$(api_restart_total)"
  L2_WAITING="$(api_waiting_reasons)"
  L2_PHASE="$(api_phases)"
  L2_READY="$(api_ready_count)/$(api_replica_count)"
  L2_ENDPOINTS="$(api_endpoint_count)"
  if [[ -z "$L2_WAITING" ]]; then
    L2_WAITING="(none yet — CrashLoopBackOff is this same signal after several backoff rounds)"
  fi

  echo
  kubectl get pods -n "$NS" -l "$POD_SELECTOR"
  echo
  echo "Liveness probe failure events:"
  kubectl get events -n "$NS" --field-selector reason=Unhealthy \
    --sort-by=.lastTimestamp -o wide 2>/dev/null | tail -n 5 || true

  echo
  restore_liveness_probe
fi

# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
banner "SUMMARY — same fault class, two responses"

printf '%-34s %-12s %-12s %-16s %-12s %s\n' \
  "stage" "ready" "endpoints" "restartTotal" "phase" "waiting"
printf '%-34s %-12s %-12s %-16s %-12s %s\n' \
  "----------------------------------" "------------" "------------" "----------------" "------------" "-------------"
printf '%-34s %-12s %-12s %-16s %-12s %s\n' \
  "baseline" "$BASE_READY/2" "$BASE_ENDPOINTS" "$BASE_RESTARTS" "$BASE_PHASE" "-"
printf '%-34s %-12s %-12s %-16s %-12s %s\n' \
  "PHASE 1  redis down" "$P1_READY/2" "$P1_ENDPOINTS" "$P1_RESTARTS" "$P1_PHASE" "-"
printf '%-34s %-12s %-12s %-16s %-12s %s\n' \
  "PHASE 1b redis restored" "$REC_READY/2" "$REC_ENDPOINTS" "$REC_RESTARTS" "$(api_phases)" "-"
printf '%-34s %-12s %-12s %-16s %-12s %s\n' \
  "PHASE 2  liveness 404 (baseline)" "$L2_BASE_READY" "$L2_BASE_ENDPOINTS" "$L2_BASE_RESTARTS" "-" "-"
printf '%-34s %-12s %-12s %-16s %-12s %s\n' \
  "PHASE 2  liveness 404 (after)" "$L2_READY" "$L2_ENDPOINTS" "$L2_RESTARTS" "$L2_PHASE" "$L2_WAITING"

cat <<'EOF'

Read the table across: `endpoints` is what readiness controls, `restartTotal`
is what liveness controls, and no row moves both.

  A dependency failed  -> endpoints went to 0, restartTotal did NOT move.
                          The pod was REMOVED FROM THE SERVICE and left alone.
                          Zero restarts. Zero lost warm state. It rejoined by
                          itself the moment the dependency returned.

  The probe failed     -> restartTotal climbed. The pod was KILLED AND
                          RESTARTED over a verdict about a process that was
                          answering /healthz/ready perfectly well the whole
                          time. Note the direction of causation in this row:
                          readiness reads 1/2 only BECAUSE a container is
                          mid-restart — the drop is a consequence of the kill,
                          not the reason for it. In PHASE 1 it was the other
                          way round, and nothing was killed at all.
                          Left running, each kill grows the kubelet's restart
                          backoff (10s, 20s, 40s, ...) until the container is
                          caught waiting and the status reads
                          CrashLoopBackOff. Same signal, later in its life —
                          which is why this script asserts on the restart
                          counter and not on the backoff label.

That is the whole distinction, and it is why /healthz/live must never touch
Redis or Supabase. A liveness probe that checks a dependency converts row 2
into row 5 for every replica at once: a shared outage nothing can restart its
way out of, made permanently worse by the restarts.

(An empty "waiting" column on the PHASE 2 row is not a missing result. It means
the container was Running at that sample rather than sitting in backoff, which
is where a liveness-killed pod spends most of the first few minutes: up,
serving, killed, up again. CrashLoopBackOff only becomes the visible status
once the backoff interval has grown long enough to catch. The restart counter
is the signal; the backoff label is just a late symptom of it.)
EOF
