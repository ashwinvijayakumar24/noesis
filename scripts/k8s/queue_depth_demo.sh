#!/usr/bin/env bash
#
# queue_depth_demo.sh — autoscale the Celery worker on queue depth, and watch.
#
# Pushes N messages onto the Celery `analysis` queue in Redis, holds the depth
# there for a while, and records the worker replica count over time so the KEDA
# ScaledObject in infra/k8s/50-keda-scaledobject.yaml can be seen doing its job.
#
# ---------------------------------------------------------------------------
# THE MESSAGES ARE SYNTHETIC AND WILL FAIL ON PICKUP. READ THIS.
# ---------------------------------------------------------------------------
# This repo has no cheap or no-op Celery task. Every registered task
# (app/tasks/{document,draft,insights}_analysis.py, bibtex_resolution_task.py,
# paper_recommendation_tasks.py) hits OpenAI and Supabase and costs real money
# — scripts/eval/E2E_LATENCY.md measures one draft analysis at ~$0.20 and
# ~215 s. Enqueuing 50 of those to demonstrate an autoscaler would be absurd.
#
# So this script LPUSHes correctly-framed Celery protocol-v2 envelopes carrying
# a task name that is deliberately NOT registered:
#
#     noesis.k8s_demo.__unregistered__
#
# What happens when a worker picks one up: Celery raises NotRegistered, logs
# "Received unregistered task of type ...", and REJECTS the message. It is not
# retried and not requeued — the message is dropped. Nothing is written to
# Supabase, no OpenAI call is made, no money is spent, and no user-visible
# state is touched. The failure is the intended behaviour, not an accident.
#
# The envelopes are well-formed on purpose. A malformed blob would also make
# LLEN go up (which is all KEDA reads), but it would produce a decode error in
# the worker instead of a clean rejection, and a decode error is a worse thing
# to teach a reader to expect.
#
# Blast radius: the `analysis` list in Redis DB 0 of the in-cluster
# StatefulSet, on a kind cluster, and nothing else.
# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
# WHY THE DEFAULT MODE PAUSES THE CONSUMER
# ---------------------------------------------------------------------------
# First attempts at this demo ran with the worker consuming normally and
# top-ups every 5s. Both runs measured LLEN 0 at every single sample and
# replicas never left 1 — a clean, confident null result, and a wrong one.
#
# The reason is not prefetch. app/celery_app.py:62 already sets
# worker_prefetch_multiplier=1, so a worker holds one unacked message at a
# time. The reason is that these messages are DELIBERATELY UNREGISTERED (see
# above): Celery decodes the envelope, finds no such task, logs NotRegistered
# and rejects it. That path never leaves memory. One consumer disposes of 60
# of them in well under a second — far inside a 5s poll, never mind KEDA's 15s
# pollingInterval. --sustain cannot outrun it: the top-up and the drain are not
# in the same order of magnitude. What that setup actually measured was Celery's
# rejection throughput. It never put a backlog in front of the autoscaler.
#
# So the DEFAULT is --pause-consumer: the worker Deployment's container command
# is swapped for `sleep 3600` (and its celery `inspect ping` livenessProbe
# removed, since a sleeping container cannot answer it and would crash-loop).
# Nothing consumes the queue, the depth is real and stable, and KEDA's reaction
# to it is the only variable left moving.
#
# BE CLEAR ABOUT WHAT THIS DOES AND DOES NOT SHOW:
#   Under test     : does the replica count track queue depth?
#   NOT under test : can the workers drain a queue?
# A paused consumer removes throughput from the experiment on purpose. The
# autoscaler's input is LLEN and nothing else, so holding LLEN steady by
# stopping the drain is a valid way to exercise it — but the resulting timeline
# says nothing whatsoever about how fast real work would clear. The banner the
# script prints at runtime says the same thing; it is not buried here.
#
# --live-consumer restores the old behaviour (worker consuming, --sustain
# top-ups). It is kept because it is a real measurement of something, just not
# of the autoscaler.
#
# The worker Deployment is ALWAYS restored on exit — normal exit, error, or
# Ctrl-C — by re-applying infra/k8s/21-worker-deployment.yaml, which is the
# declared state rather than a remembered snapshot.
#
# Usage:
#   scripts/k8s/queue_depth_demo.sh                     # 50 msgs, consumer paused
#   scripts/k8s/queue_depth_demo.sh --count 60 --sustain 90 --poll 5
#   scripts/k8s/queue_depth_demo.sh --live-consumer     # worker keeps consuming
#   scripts/k8s/queue_depth_demo.sh --drain-only        # just empty the queue

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/k8s/_guard.sh
source "$SCRIPT_DIR/_guard.sh"

NS="$K8S_NAMESPACE"
WORKER_DEPLOY="noesis-worker"
REDIS_POD="noesis-redis-0"

# The declared state of the worker. Restoring from this file rather than from a
# snapshot captured at runtime means a crash mid-patch still converges to what
# the repo says the cluster should look like.
WORKER_MANIFEST="$SCRIPT_DIR/../../infra/k8s/21-worker-deployment.yaml"

# Pods are labelled name=noesis + component=worker. The Deployment is *named*
# noesis-worker but nothing carries `app.kubernetes.io/name=noesis-worker`, so
# selecting on that matches nothing and prints "No resources found".
WORKER_SELECTOR="app.kubernetes.io/name=noesis,app.kubernetes.io/component=worker"

# The Redis key. For Celery's Redis transport the broker key IS the queue name
# — there is no prefix unless broker_transport_options sets one, and
# services/backend/app/celery_app.py:39-41 declares the queues with no
# transport options at all. Confirmed rather than assumed; see docs/K8S.md.
QUEUE_KEY="analysis"

COUNT=50
SUSTAIN=120
POLL=5
TOPUP_EVERY=5
DRAIN_ONLY=0
PAUSE_CONSUMER=1   # default; see the header note

while [[ $# -gt 0 ]]; do
  case "$1" in
    --count)   COUNT="$2"; shift 2 ;;
    --sustain) SUSTAIN="$2"; shift 2 ;;
    --poll)    POLL="$2"; shift 2 ;;
    --drain-only) DRAIN_ONLY=1; shift ;;
    --pause-consumer) PAUSE_CONSUMER=1; shift ;;
    --live-consumer)  PAUSE_CONSUMER=0; shift ;;
    -h|--help) sed -n '2,90p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

require_kind_context

redis_cli() {
  kubectl exec -n "$NS" "$REDIS_POD" -- redis-cli "$@"
}

queue_depth() {
  redis_cli LLEN "$QUEUE_KEY" 2>/dev/null | tr -d '\r' || echo "?"
}

worker_replicas() {
  kubectl get deployment "$WORKER_DEPLOY" -n "$NS" \
    -o jsonpath='{.status.replicas}' 2>/dev/null || echo "?"
}

worker_ready() {
  kubectl get deployment "$WORKER_DEPLOY" -n "$NS" \
    -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0
}

hpa_desired() {
  # KEDA creates an HPA named keda-hpa-<scaledobject>. Read it generically so
  # a rename does not break the demo.
  kubectl get hpa -n "$NS" -o jsonpath='{.items[0].status.desiredReplicas}' 2>/dev/null || echo "-"
}

# Emit `n` Celery envelopes on stdout, ONE PER LINE.
#
# One line per message, and the push loop below runs INSIDE the Redis pod. Two
# things this avoids, both of which were observed:
#   - `kubectl exec` per message: ~0.5-1s of round trip each, so 60 messages
#     take a minute and the depth never reaches N at any single instant — the
#     ramp you are trying to photograph is smeared out below the sample rate.
#   - building one giant argv on the host and word-splitting it: the payloads
#     contain spaces, so the split does not land where you think. One run
#     collapsed 60 messages into a single LPUSH argument and reported LLEN 1.
# Reading newline-delimited payloads on the pod's stdin sidesteps both: the
# host does no splitting, and the depth appears in one batch.
#
# json.dumps never emits a raw newline, so line-delimiting is safe.
emit_payloads() {
  python3 - "$QUEUE_KEY" "$1" <<'PY'
import base64, json, sys, uuid

key, n = sys.argv[1], int(sys.argv[2])
out = []
for _ in range(n):
    task_id = str(uuid.uuid4())
    # Celery protocol v2: args/kwargs/embed are the body; everything the worker
    # routes on lives in headers. See celery.app.amqp.as_task_v2.
    body = base64.b64encode(
        json.dumps([[], {}, {"callbacks": None, "errbacks": None,
                            "chain": None, "chord": None}]).encode()
    ).decode()
    envelope = {
        "body": body,
        "content-encoding": "utf-8",
        "content-type": "application/json",
        "headers": {
            "lang": "py",
            # DELIBERATELY UNREGISTERED. The worker will raise NotRegistered,
            # log it, and drop the message. No task code runs.
            "task": "noesis.k8s_demo.__unregistered__",
            "id": task_id,
            "root_id": task_id,
            "parent_id": None,
            "group": None,
            "argsrepr": "()",
            "kwargsrepr": "{}",
            "origin": "queue_depth_demo.sh",
            "retries": 0,
            "eta": None,
            "expires": None,
            "timelimit": [None, None],
        },
        "properties": {
            "correlation_id": task_id,
            "reply_to": str(uuid.uuid4()),
            "delivery_mode": 2,
            "delivery_info": {"exchange": "", "routing_key": key},
            "priority": 0,
            "body_encoding": "base64",
            "delivery_tag": str(uuid.uuid4()),
        },
    }
    out.append(json.dumps(envelope))
sys.stdout.write("\n".join(out) + "\n")
PY
}

# Single kubectl exec; the `while read` loop runs in-pod so all N LPUSHes land
# within a few tens of milliseconds of each other.
enqueue() {
  local n="$1"
  (( n <= 0 )) && return 0
  emit_payloads "$n" | kubectl exec -i -n "$NS" "$REDIS_POD" -- sh -c \
    'while IFS= read -r line; do redis-cli LPUSH "$0" "$line" >/dev/null; done' \
    "$QUEUE_KEY"
}

drain() {
  echo "[k8s] draining $QUEUE_KEY (DEL — synthetic messages only)"
  redis_cli DEL "$QUEUE_KEY" >/dev/null 2>&1 || true
}

# ---------------------------------------------------------------------------
# Consumer pause / restore.
# ---------------------------------------------------------------------------
WORKER_PAUSED=0

pause_consumer() {
  echo "[k8s] pausing the consumer: worker command -> sleep 3600, livenessProbe removed"
  # Two ops in one patch so the container never exists in the intermediate
  # state where it sleeps AND is probed with `celery inspect ping` — that probe
  # cannot pass against a sleeping container and would crash-loop the pod,
  # which looks exactly like a broken demo.
  kubectl patch deployment "$WORKER_DEPLOY" -n "$NS" --type=json -p \
    '[{"op":"replace","path":"/spec/template/spec/containers/0/command","value":["sleep","3600"]},
      {"op":"remove","path":"/spec/template/spec/containers/0/livenessProbe"}]' >/dev/null
  WORKER_PAUSED=1
  # strategy: Recreate — the old pod goes away before the new one starts, so
  # there is a short window with no consumer at all. That is the desired state
  # here anyway.
  kubectl rollout status deployment/"$WORKER_DEPLOY" -n "$NS" --timeout=180s || true
}

restore_consumer() {
  echo "[k8s] restoring the worker from $(basename "$WORKER_MANIFEST") (declared state)"
  kubectl apply -f "$WORKER_MANIFEST" >/dev/null || true
  WORKER_PAUSED=0
}

cleanup() {
  local rc=$?
  echo
  drain
  echo "[k8s] queue depth after drain: $(queue_depth)"
  # ALWAYS, including Ctrl-C and error exits: a paused worker left behind is a
  # cluster that silently stops processing everything.
  if (( WORKER_PAUSED == 1 )); then
    restore_consumer
  fi
  exit "$rc"
}
trap cleanup EXIT
# EXIT alone does not fire on SIGINT/SIGTERM in every bash; re-raise through
# the EXIT trap explicitly.
trap 'exit 130' INT
trap 'exit 143' TERM

if (( DRAIN_ONLY == 1 )); then
  exit 0
fi

# ---------------------------------------------------------------------------

if (( PAUSE_CONSUMER == 1 )); then
  cat <<EOF

###############################################################################
#                                                                             #
#   THE CONSUMER IS PAUSED FOR THIS RUN.                                      #
#                                                                             #
#   The noesis-worker container is being replaced with \`sleep 3600\` and its   #
#   celery livenessProbe removed. NOTHING will consume the queue.             #
#                                                                             #
#   UNDER TEST      : does the replica count track queue depth?               #
#   NOT UNDER TEST  : can the workers drain a queue? (they cannot — they are  #
#                     asleep). This timeline says nothing about throughput.   #
#                                                                             #
#   Why: the synthetic messages are unregistered tasks, which a live Celery    #
#   worker rejects in microseconds. One consumer empties 60 of them inside a   #
#   single poll, LLEN reads 0 at every sample, and the autoscaler is never     #
#   shown a backlog at all. Pausing the consumer is what makes the input       #
#   variable (queue depth) actually hold still.                                #
#                                                                             #
#   The worker is restored from infra/k8s/21-worker-deployment.yaml on exit,   #
#   including on Ctrl-C.   Re-run with --live-consumer to skip all of this.   #
#                                                                             #
###############################################################################

EOF
fi

echo
echo "==============================================================="
echo "BEFORE"
echo "==============================================================="
kubectl get scaledobject,hpa -n "$NS" 2>/dev/null || echo "(no ScaledObject/HPA — is KEDA installed?)"
echo
kubectl get pods -n "$NS" -l "$WORKER_SELECTOR"
echo
echo "worker replicas : $(worker_replicas) (ready $(worker_ready))"
echo "queue '$QUEUE_KEY': depth $(queue_depth)"
echo

if (( PAUSE_CONSUMER == 1 )); then
  pause_consumer
  echo
fi

echo "==============================================================="
if (( PAUSE_CONSUMER == 1 )); then
  echo "ENQUEUE $COUNT synthetic messages (consumer paused), watch for ${SUSTAIN}s"
else
  echo "ENQUEUE $COUNT synthetic messages, holding depth for ${SUSTAIN}s"
fi
echo "==============================================================="
START="$SECONDS"

printf '  %-7s  %-8s  %-10s  %-10s  %s\n' "t(s)" "depth" "replicas" "ready" "hpa_desired"
LAST_TOPUP=0
MAX_REPLICAS=0

# Sample BEFORE pushing. Without a pre-push row the timeline opens at whatever
# depth the first post-push sample happens to catch, and there is no recorded
# evidence that the queue started empty and the replica count started at the
# floor — which is half of what the ramp is supposed to show.
printf '  %-7s  %-8s  %-10s  %-10s  %s\n' \
  "0" "$(queue_depth)" "$(worker_replicas)" "$(worker_ready)" "$(hpa_desired)"

enqueue "$COUNT"

while :; do
  T=$((SECONDS - START))
  D="$(queue_depth)"
  R="$(worker_replicas)"
  # `&&`-chained as a bare statement would be a set -e landmine (a false
  # condition makes the whole list return non-zero and kills the script), so
  # this is a plain if.
  if [[ "$R" =~ ^[0-9]+$ ]] && (( R > MAX_REPLICAS )); then MAX_REPLICAS="$R"; fi
  printf '  %-7s  %-8s  %-10s  %-10s  %s\n' "$T" "$D" "$R" "$(worker_ready)" "$(hpa_desired)"

  if (( T >= SUSTAIN )); then break; fi

  # Top-ups only make sense when something is draining. With the consumer
  # paused the depth is already stable, and re-pushing would just inflate it
  # past COUNT and change the target the autoscaler is solving for.
  if (( PAUSE_CONSUMER == 0 )) && (( T - LAST_TOPUP >= TOPUP_EVERY )); then
    LAST_TOPUP="$T"
    if [[ "$D" =~ ^[0-9]+$ ]] && (( D < COUNT )); then
      enqueue $((COUNT - D))
    fi
  fi
  sleep "$POLL"
done

echo
echo "==============================================================="
echo "DRAIN — stop topping up, let the backlog clear, watch scale-down"
echo "==============================================================="
drain

DRAIN_START="$SECONDS"
# Scale-down here is governed by the generated HPA's
# behavior.scaleDown.stabilizationWindowSeconds (300s), NOT by the
# ScaledObject's cooldownPeriod — see the note at the end of this script.
# 420s is that window plus headroom for the HPA's 15s evaluation cadence.
DRAIN_DEADLINE=420
printf '  %-7s  %-8s  %-10s  %-10s  %s\n' "t(s)" "depth" "replicas" "ready" "hpa_desired"
while :; do
  T=$((SECONDS - START))
  R="$(worker_replicas)"
  printf '  %-7s  %-8s  %-10s  %-10s  %s\n' "$T" "$(queue_depth)" "$R" "$(worker_ready)" "$(hpa_desired)"
  if [[ "$R" == "1" ]]; then
    echo "  -> back to minReplicaCount after ${T}s total ($((SECONDS - DRAIN_START))s after the queue emptied)"
    break
  fi
  if (( SECONDS - DRAIN_START >= DRAIN_DEADLINE )); then
    echo "  -> TIMEOUT: still at $R replicas $((SECONDS - DRAIN_START))s after the drain."
    echo "     Not necessarily wrong — the HPA's scaleDown stabilization window"
    echo "     is 300s by design, and it restarts on every sample that still"
    echo "     recommends a higher count."
    break
  fi
  sleep "$POLL"
done

echo
echo "==============================================================="
echo "AFTER"
echo "==============================================================="
kubectl get scaledobject,hpa -n "$NS" 2>/dev/null || true
echo
kubectl get pods -n "$NS" -l "$WORKER_SELECTOR"
echo
echo "peak worker replicas observed: $MAX_REPLICAS"
echo
cat <<'EOF'
What to look for in the timeline above:

  t=0, depth 0, replicas 1                    -> the pre-push baseline, on the
      timeline on purpose so the ramp has something to be a ramp from.
  depth jumps to N with replicas still at 1   -> the backlog exists and CPU,
      had you scaled on it, would be near idle: this worker runs --pool=gevent
      and every queued job is blocked on an OpenAI socket, not on a core.
  replicas climb toward maxReplicaCount       -> KEDA read LLEN, not CPU.
      The target is ceil(LLEN / listLength) clamped to maxReplicaCount, so
      depth 60 with listLength 10 asks for 6 and gets 5.
  after DEL, replicas hold, then drop         -> see below; this takes minutes.

SCALE-DOWN IS SLOWER THAN cooldownPeriod, AND cooldownPeriod IS NOT WHY.
Measured on this cluster across runs: after DEL the depth was 0 immediately,
replicas held at 5 for ~271-306 s, then dropped straight to 1.

  KEDA's `cooldownPeriod` governs ONLY the scale-to-zero / scale-from-zero
  transition. With minReplicaCount 1 there is no zero to go to, so it is inert
  here and reading the delay off it is simply the wrong knob.

  Every scaling decision ABOVE zero is made by the HorizontalPodAutoscaler KEDA
  generates (keda-hpa-noesis-worker), and its scale-downs are held by
  behavior.scaleDown.stabilizationWindowSeconds — 300s, which is both the
  Kubernetes default and what 50-keda-scaledobject.yaml sets explicitly. The
  HPA takes the maximum recommendation over that trailing window, so the clock
  effectively starts at the last sample that still wanted more replicas.
  ~271s is that window, not a cooldown.

  To make scale-down faster, shorten
  advanced.horizontalPodAutoscalerConfig.behavior.scaleDown
  (stabilizationWindowSeconds, and/or a Pods/Percent policy). Lowering
  cooldownPeriod changes nothing while minReplicaCount is above zero.

A CPU-based HPA on this workload does not merely fail to scale up. It scales
DOWN when the backlog is worst, because a worker waiting on 40 concurrent HTTP
responses uses less CPU than one doing nothing at all.
EOF

if (( PAUSE_CONSUMER == 1 )); then
  cat <<'EOF'

REMINDER: the consumer was asleep for this entire run. What was demonstrated is
that replica count tracks queue depth. Nothing above measures how fast real
tasks drain, and it should not be quoted as if it did.
EOF
fi
