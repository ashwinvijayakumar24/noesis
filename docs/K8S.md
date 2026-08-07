# Kubernetes: the Noesis backend as a self-healing, autoscaling workload

A learning build. Noesis runs on ECS in production and the compose stack is the
local development environment; nothing here is deployed. The point was to take
a workload with real, awkward properties — a stateless API, a long-running
I/O-bound Celery worker, and a stateful broker they both depend on — and make
Kubernetes handle its actual failure modes rather than a tutorial's.

Everything below that carries a number is either measured by a script in this
repo or marked **not measured**. Nothing is estimated and presented as
observed. That is the same rule the eval harness runs under
(`docs/BENCHMARKS.md`), and it applies here for the same reason: a fabricated
number is worse than a blank one, because a blank one gets filled in. Null
results and invalid attempts are published with their reason rather than
deleted, same as there.

The predictions recorded before each run are left in place with the outcome
scored against them, including where they were wrong.

### The cluster the numbers came from

Every measurement in this document was taken on one run of this cluster, on one
laptop. Read every `n` accordingly.

| | |
|---|---|
| kind | v0.32.0, cluster `noesis`, node image `kindest/node:v1.36.1` |
| topology | 1 control-plane + 1 worker |
| host | Docker Desktop, Apple Silicon, MemTotal 8 217 903 104 (8.2 GB), 10 CPUs |
| ingress | ingress-nginx `controller-v1.11.3` (kind provider manifest) |
| autoscaler | KEDA v2.16.1 |
| image | `noesis-backend:dev`, 1.24 GB, from `services/backend/Dockerfile` |
| workloads | `noesis-api` Deployment ×2, `noesis-worker` Deployment, `noesis-redis` StatefulSet + 1 Gi PVC |

**EKS was not attempted.** Nothing in this document was run on a managed
control plane, on more than two nodes, or on hardware that resembles
production.

---

## What was built

| path | what |
|---|---|
| `infra/k8s/kind-cluster.yaml` | 2-node kind cluster, ingress-ready control plane, :80/:443 published |
| `infra/k8s/00-namespace.yaml` | everything in `noesis`; `kubectl delete ns noesis` is a complete teardown |
| `infra/k8s/01-configmap.yaml` | non-secret runtime config, mirroring compose's `environment:` blocks |
| `infra/k8s/02-secret.example.yaml` | template; the real Secret is built from `services/backend/.env` |
| `infra/k8s/50-keda-scaledobject.yaml` | KEDA `ScaledObject`, Redis-list trigger on the `analysis` queue |
| `scripts/k8s/_guard.sh` | the kind-context guard every script sources first |
| `scripts/k8s/break_deps.sh` | readiness-vs-liveness, demonstrated by breaking things |
| `scripts/k8s/rolling_restart_load.py` | zero-downtime measurement under a rolling restart |
| `scripts/k8s/queue_depth_demo.sh` | queue-depth autoscaling, timelined |

Workloads: Deployment `noesis-api` (2 replicas, :8000), Deployment
`noesis-worker`, StatefulSet `noesis-redis`. Services: `noesis-api`
(ClusterIP :8000) and `noesis-redis` (headless :6379).

**Safety.** Every script in `scripts/k8s/` refuses to run unless
`kubectl config current-context` starts with `kind-`, and every kubectl call
passes `-n noesis` explicitly. These scripts scale a StatefulSet to zero and
deliberately break a liveness probe; the guard is what makes it acceptable to
have them in a repo at all.

---

## The three-probe split

The backend exposes three endpoints that look similar and mean entirely
different things:

| endpoint | asks | consulted by | consequence of failing |
|---|---|---|---|
| `/healthz/live` | is this process wedged? | livenessProbe | container is **killed and restarted** |
| `/healthz/ready` | can this process serve a request right now? | readinessProbe | pod is **removed from the Service** |
| `/healthz/startup` | has this process finished booting? | startupProbe | liveness/readiness held off until it passes |

`/healthz/ready` checks Redis and Supabase and returns 503 naming the failed
dependency. `/healthz/live` checks nothing but the process itself.

### RESULT — the readiness probe caught a real config bug on the first apply

This was not a planned experiment. It is the most useful thing the build
produced, so it goes first.

On the first `kubectl apply`, both API pods reached `Running` and then sat at
`0/1` for **3 m 31 s**. The startup probe passed after the usual
connection-refused retries; readiness returned 503 continuously. From inside
the pod:

```
503 {"status":"not_ready","failed":["redis"],
     "checks":{"redis":{"status":"unhealthy","error":"ConnectionError"},
               "supabase":{"status":"ok"}}}
```

The cause is two Redis config paths in the same codebase that had drifted apart:

| path | source | value in-cluster | used by |
|---|---|---|---|
| broker URL | `app/celery_app.py:18` builds `redis://$REDIS_HOST:$REDIS_PORT/$REDIS_DB` | correct — the ConfigMap sets all three | Celery worker (fine) |
| `REDIS_URL` | `app/core/config.py:32`, `Optional[str] = None`, defaulting in code to the **compose** hostname `redis://redis:6379/0` | a name that does not resolve in-cluster | `progress_tracking.py` and the readiness probe |

The worker was healthy the whole time because it never reads the second one.
The fix is a single ConfigMap line, not a code change —
`REDIS_URL: "redis://noesis-redis:6379/0"` in `infra/k8s/01-configmap.yaml`,
where the comment records the failing payload.

**Why this is the headline.** `services/backend/app/main.py:183` still serves
the legacy `/health`, and its entire body is `return {"status": "ok"}`. That
endpoint would have reported both pods healthy. The endpoints controller would
have put them in the Service, the Ingress would have sent them traffic, and
every queue operation would have failed — a silent production bug, discovered
by users. The dependency-checking readiness probe turned it into a pod that
refused to accept traffic at all, before any traffic existed. The failure mode
was converted from *wrong answers served* to *no answers served*, which is the
whole argument for a readiness probe that checks its dependencies.

(That legacy `/health` is left alone deliberately: compose healthchecks and AWS
target groups point at it.)

### Why liveness must not probe dependencies

This is the mistake worth having a demo for, because it looks like diligence.
If liveness also checked Redis, then a Redis blip would make every API pod fail
its liveness probe *simultaneously*. The kubelet would kill and restart all of
them, for a fault none of them caused and none of them can fix by restarting.
Repeat, and the Deployment enters CrashLoopBackOff. When Redis comes back, the
API is now in exponential backoff and cold-starting — the dependency recovered
and the service did not.

Readiness handles exactly this case correctly, and does nothing else: it parks
the pod out of the load balancer, leaves the process alive and warm, and lets
it rejoin the instant the dependency returns. No restart, no cold start, no
lost in-flight state.

`scripts/k8s/break_deps.sh` induces the same class of signal twice — a health
endpoint returning non-200 — and shows the two responses side by side.

It breaks Redis by **scaling the StatefulSet to zero rather than applying a
NetworkPolicy**, for three reasons: `kubectl scale --replicas=1` restores the
prior state in one command and leaves no object behind (a script that dies
mid-run leaves a NetworkPolicy silently firewalling the namespace); kind's
default CNI, kindnet, does not enforce NetworkPolicy at all, so the policy
would be accepted and quietly do nothing, producing a confident wrong null
result; and the PVC survives, so the recovery half of the demo is honest. The
tradeoff, stated: scale-to-zero also removes DNS, so the readiness handler sees
a resolution failure rather than a connection timeout. Both are "Redis is
unreachable", but they are not the same exception, and a handler that only
catches `ConnectionError` would pass this test and fail the real one.

Liveness is broken by repointing the probe at a path that 404s, not by killing
the process: killing PID 1 restarts the container whether a liveness probe
exists or not, so it proves nothing about liveness. Repointing the probe leaves
the process perfectly healthy and makes the probe verdict the only variable.
Caveat recorded in the script and here: patching the probe edits the pod
template, so the Deployment rolls new pods and phase 2's `restartCount`
baseline is those fresh pods' zero.

### RESULTS — probe behaviour

**Phase 1 — dependency failure.** `scripts/k8s/break_deps.sh`, Redis
StatefulSet scaled to 0 and back.

| stage | ready | endpoints | restartTotal | phase |
|---|---|---|---|---|
| baseline | 2/2 | 2 | 0 | Running |
| redis down | 0/2 | 0 | **0** | Running |
| redis restored | 2/2 | 2 | **0** | Running |

Both pods stayed `phase=Running` throughout. Zero restarts. They rejoined the
Service endpoints on their own, with no intervention and no cold start.

**Phase 2 — probe failure.** Liveness `httpGet.path` repointed to
`/healthz/deliberately-missing` (404). Same class of signal — a health endpoint
returning non-200 — different probe.

| t | observation |
|---|---|
| 0 s | patch applied, new ReplicaSet rolls out |
| 12 s | new pods Running, `restartCount` 0 |
| 73 s | `restartCount` still 0 |
| 85 s | pod `…kklwq` `restartCount` 0 → 1, ready false |
| 97 s | pod `…tzt6v` `restartCount` 0 → 1 (staggered); `kklwq` back to ready true |
| 109 s + | both pods at `restartCount` 1, ready true *between* kills, cycle continues |

Events confirmed the mechanism: `Liveness probe failed: HTTP probe failed with
statuscode: 404` × 18.

The timing checks out against the manifest: `failureThreshold: 5` ×
`periodSeconds: 15` = 75 s, plus probe scheduling lag, against an observed
~85 s to first restart. Note that the pods report `ready=true` between
restarts — readiness was never the failing probe, which is exactly the
separation the manifest is trying to buy.

**The contrast is the result.** A real dependency outage produced zero restarts
and automatic recovery. A failing liveness probe produced repeated container
kills on a process that was perfectly healthy. A liveness probe that checked
Redis would have turned the first table into the second, on every replica
simultaneously.

**Instrumentation note — the first run's numbers were fabricated by a bug, and
one of them was a false zero that agreed with the answer.** Keep this; it is
the most useful thing in the section.

The first automated run printed `restartTotal 0` for phase 2 while the event
log already showed 18 liveness failures. Root cause was not the accounting: it
was the selector. Every pod-level observer in `break_deps.sh` used
`-l app.kubernetes.io/name=noesis-api`, and **no pod carries that label** — the
manifests use the two-part recommended scheme, `app.kubernetes.io/name=noesis`
plus `app.kubernetes.io/component=api`. `noesis-api` is the *Deployment's*
name, not its `name` label. So the selector matched nothing at every sample,
`kubectl get pods -l …` printed `No resources found`, and summing an empty
jsonpath yielded `0` forever. The poll condition `restart_total > baseline`
could never become true, so phase 2 was guaranteed to time out no matter how
long it ran.

The sharp part is phase 1. Its assertion is that a count must **not** move —
and a selector matching nothing satisfies that perfectly. **Phase 1's original
`restartTotal 0` was not a measurement, it was an empty sum.** It was reported
as a clean result because it happened to equal the expected answer. A false
zero and a healthy zero are indistinguishable once summed, which is the general
hazard: an assertion that something stays at zero is silently satisfied by an
instrument that observes nothing at all.

Both phases were re-run after fixing the selector, and phase 2 now narrows to
the post-patch ReplicaSet via `pod-template-hash` (patching a probe rolls a new
RS, so the pods being watched must be the new ones). The re-run confirms the
finding — phase 1 genuinely holds at 0 restarts with a validated selector:

| stage | ready | endpoints | restartTotal |
|---|---|---|---|
| baseline | 2/2 | 2 | 0 |
| phase 1: redis down | 0/2 | 0 | 0 |
| phase 1b: redis restored | 2/2 | 2 | 0 |
| phase 2: liveness 404, after 63 s | 1/2 | 1 | **1** |

The script now calls `assert_selector_matches()` at baseline and fails loudly
if either selector stops resolving, so a future rename cannot reproduce this
silently. Two smaller fixes fell out of the same pass: `0/2` had been rendering
as a blank `/2` because `.status.readyReplicas` is *absent* rather than `0`
when nothing is ready, and the 120 s `CrashLoopBackOff` deadline was
unreachable in principle (75 s to first kill plus a rollout, then several
backoff rounds) — the success condition is now `restartCount >= 1`, which is
the signal the demo actually needs.

Phase 2 reached its first restart in 63 s on the re-run versus ~85 s on the
manual run; the startup probe passed on the first attempt that time. The
manual-run timeline above is retained as the more conservative figure.

**Predictions, scored.** Recorded before the run: phase 1 shows endpoints → 0
with `restartTotal` unchanged and phase `Running`; phase 2 shows `restartTotal`
climbing and `CrashLoopBackOff`.

| prediction | outcome |
|---|---|
| phase 1: endpoints → 0, `restartTotal` unchanged, `Running` | **correct** — 0 endpoints, 0 restarts, Running. Scored against the re-run only: the first run's `0` was an empty sum (see the instrumentation note) and could not have falsified anything. |
| phase 2: `restartTotal` climbs | **correct** — 0 → 1 on both pods, cycle continuing |
| phase 2: reaches `CrashLoopBackOff` | **not observed** in the ~2 min window watched. The pods were killed and came back ready between kills; the run was stopped before backoff could accumulate. The prediction is neither confirmed nor refuted — the observation window was too short. |

The stated falsifier — "if phase 1's `restartTotal` moves, the liveness probe
is touching a dependency and the manifest is wrong" — did not fire.

---

## QoS classes

Kubernetes assigns every pod a QoS class from its resource spec alone, and that
class decides eviction order when a node runs out of memory. It is not a knob;
it is a consequence, which is why it is easy to get by accident.

| class | condition | evicted |
|---|---|---|
| Guaranteed | every container sets requests **and** limits, and they are equal, for both cpu and memory | last |
| Burstable | requests set, but not equal to limits (or limits absent) | second |
| BestEffort | no requests and no limits anywhere | **first** |

The intent for this workload:

- **`noesis-redis`** — Guaranteed. It is the broker; if it is evicted, both the
  API's readiness and the worker's ability to do anything at all go with it.
  It is also the one component whose memory ceiling is genuinely predictable.
- **`noesis-api`** — Burstable. Two replicas behind a Service, cheap to
  restart, and its memory floor is well below its peak during a PDF upload.
  Paying Guaranteed's reservation for that headroom on a 2-node kind cluster
  buys nothing.
- **`noesis-worker`** — Burstable, with a memory limit that is real. LangGraph
  plus a PDF parse is the memory-hungriest thing here, and `--pool=gevent`
  means one pod holds many concurrent tasks' working sets at once.

Nothing should be BestEffort. A BestEffort pod is the first thing the kubelet
kills under pressure, and on a 2-node cluster that pressure is a matter of when.

### RESULTS — observed QoS, and an inverted eviction order

Read off the live cluster with
`kubectl get pods -n noesis -o custom-columns=POD:.metadata.name,QOS:.status.qosClass`:

| pod | intended above | observed | requests → limits |
|---|---|---|---|
| `noesis-api-*` (2 replicas) | Burstable | **Guaranteed** | 250m/512Mi == 250m/512Mi |
| `noesis-worker-*` | Burstable | Burstable | 100m/512Mi → 1/1536Mi |
| `noesis-redis-0` | Guaranteed | **Burstable** | 50m/64Mi → 250m/256Mi |

Both of the divergent rows are the same mistake, and together they inverted the
eviction order across the whole namespace. QoS is a *consequence* of the
requests/limits spec, not something declared — so neither pod's class was
chosen, both were inherited from numbers written for other reasons:

- `noesis-api` got Guaranteed because its requests happen to equal its limits.
- `noesis-redis-0` got Burstable because its limits were set generously above
  its requests, which is normally the sensible default.

The result is that under node memory pressure the kubelet would evict the
**singleton broker** before the **two fungible API replicas**. That is backwards
in the way that matters: losing `noesis-redis-0` fails the readiness probe on
every API pod at once *and* stops the worker — the exact fleet-wide dependency
failure the probe section is about — while the pods being protected are the
cheap, rescheduleable ones sitting behind a Service.

Resolved by editing the manifest, not the intent: `10-redis-statefulset.yaml`
now sets requests == limits (250m/256Mi) so Redis is Guaranteed. The API was
left Guaranteed rather than demoted to the Burstable the section argues for —
on a 2-node cluster there is no contention to reclaim, and eviction order only
has to be *relatively* correct, which it now is (Redis and API both Guaranteed,
worker Burstable and therefore reaped first).

The observed column above is the pre-fix state. It is kept rather than
re-measured away: the point of the section is that this class is easy to get by
accident, and it was got by accident here, twice, in manifests written to
explain it.

Nothing was observed as BestEffort, but note that this is a weak check: no pod
was measured under actual memory pressure, and no eviction was induced. The
QoS class is read off the API server, not demonstrated — so the corrected
ordering above is likewise reasoned, not proven.

---

## The rolling-restart race

A rolling restart of a 2-replica Deployment should be invisible. In the naive
manifest it is not, and the reason is a race that no amount of readiness
configuration fixes on its own.

When a pod is deleted, two things happen **concurrently**, not in sequence:

1. the kubelet sends `SIGTERM` to the container, and
2. the endpoints controller removes the pod from the Service, which then has to
   propagate to every kube-proxy on every node.

Nothing orders (2) before (1). A well-behaved server that shuts down promptly
on `SIGTERM` therefore stops accepting connections while kube-proxy on some
node is still routing to it — and those requests get a connection reset. The
better the server's shutdown hygiene, the worse this is.

The fix is to make the container deliberately slow to die:

- **`preStop: sleep N`** — the kubelet runs the preStop hook *before* sending
  `SIGTERM`, so this buys the endpoints removal time to propagate while the pod
  is still serving. It is a sleep and it is meant to be one; there is nothing
  to poll, because the thing being waited for is state in other nodes' iptables.
- **`terminationGracePeriodSeconds`** — must exceed `preStop` + the longest
  in-flight request, or the kubelet `SIGKILL`s mid-request and undoes the
  point. The grace period is a budget that the preStop sleep spends from.
- **`maxUnavailable: 0`** with 2 replicas, so the replacement is Ready before
  the incumbent is touched.
- A **PodDisruptionBudget**, which covers the other half of the problem: node
  drains and cluster upgrades, which the Deployment's rollout strategy does not
  govern at all.

`scripts/k8s/rolling_restart_load.py` puts a number on it: fixed-rate traffic,
a `kubectl rollout restart` fired mid-flight, and a count of every non-2xx,
connection error and timeout the client saw.

**It drives traffic through the Ingress, not a port-forward, and that is
load-bearing.** `kubectl port-forward svc/noesis-api` resolves the Service to
*one* pod and pins the tunnel to it — it does not load-balance and does not
re-resolve. A rolling restart deletes that pod, the tunnel dies, and every
subsequent request fails. The run would report catastrophic downtime the
Service never had: it would be measuring kubectl. `--via port-forward` still
exists for smoke tests, but any record it produces is written `valid: false`
with the reason attached, per the house rule in `docs/BENCHMARKS.md` that
invalid runs are kept and labelled rather than deleted.

The driver opens a fresh TCP connection per request (no keep-alive). A pooled
client can hide endpoint churn behind an already-open socket, which is exactly
the thing under measurement.

Results append to `scripts/k8s/results/rolling_restart.jsonl`, keyed by a
config hash over target, rate, duration and restart offset. Runs under
different hashes are different measurements and are never differenced —
`--compare` groups by hash and prints them separately.

### RESULTS — requests dropped by a rolling restart

Load: 20.0 req/s × 60.0 s = 1200 requests, concurrency 16, client timeout 5 s,
path `/healthz/live`, through the Ingress.
`kubectl rollout restart deployment/noesis-api` fired at t = 15.0 s. Both runs
share config hash `5b7858d02dcf`, so they are directly comparable.

- `naive` — `maxSurge 1`, `maxUnavailable 1`, **no preStop hook**, grace 30 s
- `tuned` — `maxSurge 1`, `maxUnavailable 0`, `preStop: exec sleep 5`,
  `terminationGracePeriodSeconds: 30`

| label | total | non-2xx | conn errors | timeouts | failures | failure rate | p50 ms | p95 ms | max ms | valid |
|---|---|---|---|---|---|---|---|---|---|---|
| `control` (no restart) | — | — | — | — | — | — | — | — | — | **not measured** |
| `naive` | 1200 | 4 (all 502) | 0 | 11 | 15 | **1.25 %** | 3.79 | 8.82 | 5003.5 | yes |
| `tuned` | 1200 | 0 | 0 | 0 | 0 | **0.00 %** | 3.59 | 9.06 | 101.54 | yes |

Run IDs: `naive` `5d77981a-2dd0-48ba-9e0f-9a0a899532f7`, `tuned`
`b0a7dba0-1847-45f7-b921-d99f69b626c6`. Both records are in
`scripts/k8s/results/rolling_restart.jsonl`.

The `naive` failures are not spread across the run. They occupy a single window
from **t = 26.0 s to t = 30.11 s — 4.1 s wide**, 11 s after the restart was
fired, which is the endpoints-propagation race the section above describes and
not background noise. The `naive` max latency of 5003.5 ms **is** the 5 s client
timeout: those eleven requests did not return slowly, they never returned. The
`tuned` max of 101.54 ms is the largest real response in the run.

p50 and p95 are effectively unchanged between arms (3.79 → 3.59 ms, 8.82 →
9.06 ms). The preStop hook did not make the steady state slower; it moved the
tail.

**The control arm was not run.** That is a gap, and it is the gap the section
above says to close first: without a no-restart baseline, the noise floor at
this rate on this cluster is unestablished. What partially substitutes for it
is the `tuned` arm — 1200/1200 with the restart fired — which puts an upper
bound of 0 failures on ambient noise *for that run*. It does not license
attributing all 15 `naive` failures to the rollout on its own; the 4.1 s
clustering does.

**What this is and is not.** n = 1 per arm, one restart per run, one laptop,
one cluster. This establishes the mechanism and the direction — the race is
real, and preStop plus `maxUnavailable: 0` closed it here — not a confidence
interval. A second `naive` run could plausibly land anywhere from 0 to several
dozen failures depending on where the restart falls relative to probe periods.
No claim is made about the magnitude of 1.25 %.

---

## Why queue depth beats CPU for the Celery worker

`noesis-worker` runs `--pool=gevent` against queues `default,analysis,insights`
(`infra/docker-compose.yml:244`). Every task it runs is blocked on a network
socket — OpenAI, Supabase, GROBID — not on a core. One draft analysis is
measured at ~215 s mean and 13 LLM calls (`scripts/eval/E2E_LATENCY.md`, n=7);
essentially all of that is waiting.

So a worker holding 40 queued analyses is 40 greenlets parked in `epoll`: near
zero CPU, maximum backlog. A CPU-based HPA reads that as an idle pod. It does
not merely fail to scale up — **it scales down exactly when the backlog is
worst**, because a worker waiting on I/O burns less CPU than one doing nothing.
The signal is not weak, it is inverted.

Queue depth is the metric that moves in the same direction as the pain, so the
`ScaledObject` uses KEDA's `redis` scaler on the broker list directly.

**The key is `analysis`**, verified in kombu rather than assumed:
`kombu/transport/redis.py:1039` publishes with
`client.lpush(self._q_for_pri(queue, pri), ...)`, and `_q_for_pri`
(`kombu/transport/redis.py:1024`) returns the bare queue name when priority is
0. `services/backend/app/celery_app.py:39-41` declares
`Queue("default")` / `Queue("analysis")` / `Queue("insights")` and sets no
`broker_transport_options` — no `global_keyprefix`, no priorities — so the list
key is exactly `analysis`. Two things would break that silently: a
`global_keyprefix` (kombu prefixes every key,
`kombu/transport/redis.py:230`, and the trigger would read an empty list
forever while the backlog grew), or enabling priorities (kombu shards the list
into `analysis`, `analysis\x06\x163`, `\x06\x166`, `\x06\x169`, and the trigger
would see only the priority-0 shard).

Settings and their reasons: `minReplicaCount: 1` (not 0 — a cold worker pays a
full Python + LangGraph import, and this worker also serves `default` and
`insights`, which the trigger does not watch); `maxReplicaCount: 5` (the
ceiling is the OpenAI account, not the cluster — draft analysis is capped at
30/min in Celery's `task_annotations`); `listLength: 10` (10 queued analyses is
~35 minutes of work for one worker, so depth 50 asks for exactly 5);
`cooldownPeriod: 300` (one task runs ~215 s, and `task_acks_late` means an
evicted in-flight task is *redelivered*, costing another 215 s and another
~$0.20 — so eager scale-down is expensive, not just untidy).

`scripts/k8s/queue_depth_demo.sh` demonstrates it. Two honest caveats, both
also stated loudly in the script:

1. **The messages are synthetic.** This repo has no cheap or no-op Celery task
   — every registered task hits OpenAI and Supabase. So the script LPUSHes
   well-formed Celery protocol-v2 envelopes carrying a task name that is
   deliberately not registered. The worker raises `NotRegistered`, logs it, and
   drops the message: no task code runs, no API call is made, nothing is
   written. The failure is the intended behaviour.
2. **The backlog has to be held there.** Unregistered messages are rejected in
   microseconds, so 50 of them drain faster than KEDA's polling interval and
   the autoscaler would never see them. `--sustain` tops the queue back up for
   a fixed duration to emulate a genuine backlog. That is a simulation of load,
   and it is labelled as one — it demonstrates the *scaler*, not throughput.

**What is *not* measured here.** The CPU argument above is mechanistic — gevent
greenlets parked on OpenAI sockets — and it stays an argument. **CPU
utilisation of the worker under backlog was not measured in this run, and no
CPU-based HPA was run as a comparison arm.** Nothing below is evidence that
queue depth beat CPU; it is evidence that queue depth works.

### RESULTS — replica count vs queue depth

ScaledObject as applied: `redis` scaler, `listName: analysis`,
`listLength: 10`, `activationListLength: 0`, `minReplicaCount: 1`,
`maxReplicaCount: 5`, `pollingInterval: 15` (patched to 5 s during the run).
KEDA generated the HPA `keda-hpa-noesis-worker`.

#### Two null attempts first

Both are informative, so both are published.

| attempt | setup | observed | replicas |
|---|---|---|---|
| 1 | `queue_depth_demo.sh --count 60 --sustain 180` | `LLEN` read **0 at every one of 33 samples** over 181 s | never left 1; peak 1 |
| 2 | `minReplicaCount` patched to 0 so the worker scaled to zero first, then `--count 60 --sustain 90 --poll 5` | scaled **0 → 1** (so the activation trigger *did* fire on depth), then `LLEN` back to 0 at every sample | never went past 1 |

Diagnosed cause, and it is **not** prefetch: `app/celery_app.py:62` already sets
`worker_prefetch_multiplier=1`. The demo enqueues deliberately unregistered
messages (`noesis.k8s_demo.__unregistered__`) precisely so no OpenAI money is
spent, and Celery rejects those in microseconds. A single consumer drains 60 of
them well inside one polling interval, so `LLEN` is 0 every time KEDA looks.
The script's `--sustain` top-up could not outrun the drain. Caveat 2 in the
section above anticipated this and still underestimated it.

**What attempts 1 and 2 actually measured was the drain rate, not the
autoscaler.** They are recorded as nulls, not as evidence that KEDA does not
scale.

#### The valid run — consumer paused

To make replica count track queue depth, the consumer was removed: the worker
container's command was replaced with `sleep 3600` and its celery liveness
probe was deleted. State plainly what is therefore under test — **"does replica
count track queue depth", not "can workers drain a queue"**. No throughput claim
follows from this table.

| t (s) | queue depth (`LLEN analysis`) | worker replicas | ready | HPA desired |
|---|---|---|---|---|
| 0 | 0 | 1 | 1 | 1 |
| 8 | 0 | 1 | 1 | 1 |
| 16 | 60 | 1 | 1 | 1 |
| 24 | 60 | **5** | **5** | **5** |
| 32 … 189 | 60 (steady) | 5 | 5 | 5 |

The backlog is visible at t = 16 s and not yet acted on; by t = 24 s five
replicas are up and Ready.

Peak replicas observed: **5**. Time from depth appearing to 5 **ready**
replicas: **≤ 8 s** (the sampling interval is 8 s, so this is an upper bound,
not a resolution).

Target math: `ceil(60 / 10) = 6`, clamped to `maxReplicaCount: 5`. Observed
exactly 5 — the clamp, not the target, is what set the number.

#### Scale-down: `cooldownPeriod` is not what governs it

The queue was drained (`DEL`) at t = 0.

| t (s) | replicas |
|---|---|
| 0 (drained) | 5 |
| 107 | 5 |
| 260 | 5 |
| **271** | **1** |

Replicated twice more on the fixed `queue_depth_demo.sh`, measured from the
moment the queue emptied: **297 s** and **306 s**. Three independent
observations of 271 / 297 / 306 s against a 300 s window — the spread is the
sampling interval plus where the drain lands inside the HPA's evaluation cycle,
not variance in the mechanism.

The ScaledObject's `cooldownPeriod`
(`infra/k8s/50-keda-scaledobject.yaml:52`) **did not govern this**, and the
comment beside it reasoning from the 215 s task duration is reasoning about the
wrong knob. KEDA's `cooldownPeriod` applies **only to the scale-to-zero and
scale-from-zero transition**. Every scaling decision *above* zero belongs to
the HPA that KEDA generates, and that HPA's
`behavior.scaleDown.stabilizationWindowSeconds` defaults to **300 s**. The
observed 271 s is consistent with the HPA default and not with
`cooldownPeriod`.

This distinction is commonly misread, including in the manifest comment in this
repo. If faster scale-down were wanted, the correct lever is
`advanced.horizontalPodAutoscalerConfig.behavior.scaleDown` on the
ScaledObject — not `cooldownPeriod`, which would have no effect on this
transition at any value.

#### Scale to zero

With `minReplicaCount` patched to 0 (attempt 2 above), the worker Deployment
went to **0 replicas** with no backlog and returned to **1** when depth
appeared. Worth one line because it is the capability a plain CPU-based HPA
does not have at all: an HPA's floor is 1, so the idle cost of a worker that is
doing nothing is one pod, permanently. The shipped manifest still sets
`minReplicaCount: 1` for the cold-start reason given above; the zero was
observed, not adopted.

---

## Secrets — a pre-existing leak found on the way in

Packaging the backend for Kubernetes surfaced a bug that predates this build
and affected the compose stack too.

`services/backend/` had **no `.dockerignore`**, and its Dockerfile does
`COPY . /app`. So `services/backend/.env` — `OPENAI_API_KEY`,
`SUPABASE_SERVICE_ROLE_KEY` — was being baked into every image layer, including
every image `docker-compose build` had ever produced. Anyone with the image had
the keys, and layer history keeps them even if a later layer deletes the file.

Fixed by adding `services/backend/.dockerignore`. Secrets now enter the cluster
as a Kubernetes Secret built from the same file rather than shipped inside the
image:

```
kubectl create secret generic noesis-secrets -n noesis \
  --from-env-file=services/backend/.env
```

Noted honestly: a Kubernetes Secret is base64, not encryption, and this cluster
has no encryption-at-rest configuration and no external secret store. This
moves the keys out of a distributable artefact and into cluster state. That is
a real improvement and it is not the same thing as secret management.

---

## What this build does not do

Stated so the writeup is not read as more than it is.

- **It is not deployed.** Production is ECS. Nothing here has served a user
  request.
- **EKS was not attempted.** Every number here is from kind on one laptop.
  Nothing was run on a managed control plane.
- **Postgres is not deployed** — production is Supabase, remote and managed, so
  there is nothing to model in-cluster.
- **The frontend is not deployed** — it is on Vercel.
- **GROBID and Docling are not deployed** (`infra/k8s/01-configmap.yaml` points
  them at the discard port on purpose). Any upload needing a PDF body parse
  fails in this cluster **by design**. That is scoped, not overlooked: those
  images are multi-GB under amd64 emulation and would OOM the 8.2 GB Docker
  this ran on.
- **No CPU-vs-queue-depth comparison was run.** The argument for the queue
  trigger is mechanistic; worker CPU under backlog was never measured.
- **No control arm for the rolling-restart measurement**, so the noise floor is
  unestablished — see that section.
- **No mTLS, no NetworkPolicy, no RBAC beyond defaults.** kindnet does not
  enforce NetworkPolicy anyway (see above), so writing one would be theatre.
- **Redis has no persistence guarantees worth the name here** — a StatefulSet
  with a PVC on a kind cluster is a shape, not a durability story.
- **No cost or capacity claim is made.** Nothing in this build was measured on
  hardware that resembles production.
