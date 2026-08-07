#!/usr/bin/env python3
"""Zero-downtime measurement: does a rolling restart drop requests?

Fires HTTP traffic at ``noesis-api`` at a fixed rate for a fixed duration,
runs ``kubectl rollout restart deployment/noesis-api`` partway through, and
counts what the client actually saw. The claim under test is binary and easy
to check: **a rolling restart of a 2-replica Deployment should produce zero
failed requests.** The naive manifest does not achieve that, and this script
is how the gap gets a number instead of an opinion.

Run it twice and compare::

    scripts/k8s/rolling_restart_load.py --label naive
    # ...tune preStop / terminationGracePeriodSeconds in the Deployment...
    scripts/k8s/rolling_restart_load.py --label tuned

Results append to ``scripts/k8s/results/rolling_restart.jsonl`` — append-only,
one JSON record per run, keyed by a config hash covering the target, rate,
duration and restart offset. Two runs at different hashes are different
measurements and are not comparable; the ``--compare`` view enforces that.

Dependencies: Python standard library only (``urllib``, ``concurrent.futures``,
``subprocess``). Deliberately no ``hey``/``vegeta``/``requests``: this runs on a
laptop that may not have them, and ``scripts/eval/requirements.txt`` exists to
keep the eval harness's deps out of the backend image — adding a load-testing
binary to the contract for a request counter would be the wrong trade.

Why the traffic goes through the Ingress by default
---------------------------------------------------
``kubectl port-forward svc/noesis-api`` is more reproducible in one narrow
sense — no ingress controller required — but it is the WRONG instrument for
this specific measurement, and quietly so. ``port-forward`` against a Service
resolves the Service to **one** pod and pins the tunnel to it for the tunnel's
lifetime. It does not load-balance and it does not re-resolve. A rolling
restart deletes that pod, the tunnel dies, and every subsequent request fails
with a connection refusal. The run would report catastrophic downtime that the
Service never actually had: it would be measuring kubectl, not Kubernetes.

So the default target is the Ingress (kind publishes :80 on the host — see
``infra/k8s/kind-cluster.yaml``), which resolves through the Service on every
connection and therefore exercises the endpoint churn that a rolling restart
actually causes. ``--via port-forward`` is still available for a smoke test,
but any record produced that way is written with ``valid: false`` and a reason,
following the house rule in ``docs/BENCHMARKS.md`` that invalid runs are kept
and labelled rather than deleted or quietly averaged in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SINK = SCRIPT_DIR / "results" / "rolling_restart.jsonl"

NAMESPACE = "noesis"
DEPLOYMENT = "noesis-api"
SERVICE = "noesis-api"


# ---------------------------------------------------------------------------
# Guard — same rule as scripts/k8s/_guard.sh, reimplemented here because this
# is not a bash script. It must not drift: kind- context, noesis namespace,
# nothing else. This script issues a `rollout restart`, which is destructive.
# ---------------------------------------------------------------------------

def require_kind_context() -> str:
    try:
        ctx = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.exit(f"[k8s] FATAL: cannot read kubectl context: {exc}")

    if not ctx.startswith("kind-"):
        sys.exit(
            f"[k8s] FATAL: current kubectl context is '{ctx}'.\n"
            f"[k8s]        This script restarts a Deployment and will only run\n"
            f"[k8s]        against a kind- context. Refusing to continue."
        )

    ns = subprocess.run(
        ["kubectl", "get", "namespace", NAMESPACE],
        capture_output=True, text=True,
    )
    if ns.returncode != 0:
        sys.exit(f"[k8s] FATAL: namespace '{NAMESPACE}' does not exist on '{ctx}'.")

    print(f"[k8s] context={ctx} namespace={NAMESPACE}")
    return ctx


# ---------------------------------------------------------------------------
# Load generation
# ---------------------------------------------------------------------------

class Result:
    """One request outcome. Kept deliberately coarse — the interesting axis is
    the failure CLASS, not the exception's text."""

    __slots__ = ("t_offset", "latency_ms", "status", "kind", "detail")

    def __init__(self, t_offset: float, latency_ms: float, status, kind: str, detail: str = ""):
        self.t_offset = t_offset
        self.latency_ms = latency_ms
        self.status = status
        self.kind = kind          # ok | http_error | conn_error | timeout
        self.detail = detail


def fire(url: str, host_header: str | None, timeout: float, t0: float) -> Result:
    req = urllib.request.Request(url, method="GET")
    if host_header:
        req.add_header("Host", host_header)
    # No connection reuse: urllib opens a fresh TCP connection per request.
    # That is the conservative choice here — a pooled client can hide endpoint
    # churn behind an already-open socket, which is exactly the thing being
    # measured. New connection per request means every removed endpoint has a
    # chance to show up as a failure.
    start = time.perf_counter()
    offset = start - t0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            ms = (time.perf_counter() - start) * 1000
            code = resp.status
            return Result(offset, ms, code, "ok" if 200 <= code < 300 else "http_error")
    except urllib.error.HTTPError as exc:
        ms = (time.perf_counter() - start) * 1000
        return Result(offset, ms, exc.code, "http_error", f"HTTP {exc.code}")
    except socket.timeout:
        ms = (time.perf_counter() - start) * 1000
        return Result(offset, ms, None, "timeout", "socket timeout")
    except urllib.error.URLError as exc:
        ms = (time.perf_counter() - start) * 1000
        reason = getattr(exc, "reason", exc)
        kind = "timeout" if isinstance(reason, socket.timeout) else "conn_error"
        return Result(offset, ms, None, kind, f"{type(reason).__name__}: {reason}"[:200])
    except Exception as exc:  # pragma: no cover - defensive
        ms = (time.perf_counter() - start) * 1000
        return Result(offset, ms, None, "conn_error", f"{type(exc).__name__}: {exc}"[:200])


def run_load(url: str, host_header: str | None, rate: float, duration: float,
             concurrency: int, timeout: float, on_tick) -> tuple[list[Result], float]:
    """Fire `rate` requests/second for `duration` seconds.

    Returns the results and the worst observed *submission lag* — how far
    behind schedule the driver fell. If that number is large the intended rate
    was not achieved and the run's error counts are understated; it is recorded
    rather than hidden.
    """
    results: list[Result] = []
    futures = []
    max_lag = 0.0
    total = int(rate * duration)
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for i in range(total):
            due = t0 + i / rate
            sleep_for = due - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                max_lag = max(max_lag, -sleep_for)
            futures.append(pool.submit(fire, url, host_header, timeout, t0))
            on_tick(time.perf_counter() - t0)

        for fut in futures:
            results.append(fut.result())

    return results, max_lag


# ---------------------------------------------------------------------------
# Sink — mirrors scripts/eval/cascade_arms.py: append-only JSONL, one record
# per run, sorted keys, config hash so unlike runs are never differenced.
# ---------------------------------------------------------------------------

def config_hash(cfg: dict) -> str:
    blob = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def append_record(record: dict, path: Path) -> None:
    """Append-only, always. This repo has lost a measurement history to a
    rewrite once already (see the .gitignore note on scripts/eval/results)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def percentile(values: list[float], p: float):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # A truncated final line from an interrupted write. Counted, not
            # silently dropped — same house rule as benchmarks.py.
            out.append({"_unparseable": True})
    return out


def cmd_compare(path: Path) -> int:
    records = [r for r in load_records(path) if not r.get("_unparseable")]
    if not records:
        print(f"[k8s] no records in {path}")
        return 0
    bad = sum(1 for r in load_records(path) if r.get("_unparseable"))
    by_hash: dict[str, list[dict]] = {}
    for r in records:
        by_hash.setdefault(r.get("config_hash", "?"), []).append(r)

    print(f"{path}  ({len(records)} records, {bad} unparseable)\n")
    for h, group in by_hash.items():
        cfg0 = group[0].get("config", {})
        print(f"config_hash={h}   ({cfg0.get('rate_per_s')} rps x "
              f"{cfg0.get('duration_s')}s via {cfg0.get('via')} -> {cfg0.get('target')})")
        print(f"  {'label':<14} {'valid':<6} {'total':>7} {'non2xx':>7} {'conn':>6} "
              f"{'timeout':>8} {'fail%':>7} {'p50ms':>8} {'maxms':>9}")
        for r in sorted(group, key=lambda x: x.get("timestamp", "")):
            c = r["counts"]
            print(f"  {r.get('label',''):<14} {str(r.get('valid')):<6} {c['total']:>7} "
                  f"{c['http_error']:>7} {c['conn_error']:>6} {c['timeout']:>8} "
                  f"{r['failure_rate_pct']:>7} {r['latency_ms']['p50']:>8} "
                  f"{r['latency_ms']['max']:>9}")
        print()
    print("Rows under DIFFERENT config hashes are different measurements and "
          "must not be differenced.")
    return 0


# ---------------------------------------------------------------------------
# Port-forward (opt-in, and known-invalid for this measurement — see module
# docstring). Kept because it is the only path that works with no ingress
# controller installed, and a smoke test still has value.
# ---------------------------------------------------------------------------

class PortForward:
    def __init__(self, local_port: int):
        self.local_port = local_port
        self.proc = None

    def __enter__(self):
        self.proc = subprocess.Popen(
            ["kubectl", "port-forward", "-n", NAMESPACE, f"svc/{SERVICE}",
             f"{self.local_port}:8000"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.local_port), timeout=1):
                    return self
            except OSError:
                time.sleep(0.3)
        self.__exit__(None, None, None)
        sys.exit("[k8s] FATAL: port-forward never became reachable")

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", help="run label, e.g. 'naive' or 'tuned'. Required to measure.")
    ap.add_argument("--via", choices=["ingress", "port-forward"], default="ingress",
                    help="ingress (default, valid) or port-forward (smoke test, records valid:false)")
    ap.add_argument("--url", default=None,
                    help="override the target URL entirely")
    ap.add_argument("--path", default="/healthz/live",
                    help="request path (default /healthz/live: no dependencies, so a "
                         "non-2xx means the request did not reach a healthy pod)")
    ap.add_argument("--host-header", default="noesis.local",
                    help="Host header for the ingress route; avoids needing an /etc/hosts entry")
    ap.add_argument("--rate", type=float, default=20.0, help="requests per second (default 20)")
    ap.add_argument("--duration", type=float, default=60.0, help="seconds (default 60)")
    ap.add_argument("--restart-at", type=float, default=15.0,
                    help="seconds into the run at which to trigger the rollout (default 15)")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--timeout", type=float, default=5.0, help="per-request timeout, seconds")
    ap.add_argument("--local-port", type=int, default=18000)
    ap.add_argument("--no-restart", action="store_true",
                    help="control run: same load, no rollout. Establishes the noise floor.")
    ap.add_argument("--results", type=Path, default=DEFAULT_SINK)
    ap.add_argument("--compare", action="store_true",
                    help="print the existing sink grouped by config hash and exit")
    args = ap.parse_args()

    if args.compare:
        return cmd_compare(args.results)

    if not args.label:
        ap.error("--label is required (it is how two runs are told apart in the sink)")

    require_kind_context()

    invalid_reason = None
    if args.via == "port-forward":
        invalid_reason = (
            "traffic went through `kubectl port-forward svc/noesis-api`, which pins "
            "to a single pod and dies with it during a rollout. Failures below "
            "include the tunnel's own death and do not represent Service behaviour."
        )
        print(f"[k8s] WARNING: {invalid_reason}")
        print("[k8s] This record will be written with valid: false.")

    ctx = PortForward(args.local_port) if args.via == "port-forward" else None

    def build_url():
        if args.url:
            return args.url
        if args.via == "port-forward":
            return f"http://127.0.0.1:{args.local_port}{args.path}"
        return f"http://localhost{args.path}"

    started = datetime.now(timezone.utc)
    restart_fired = {"at": None, "rc": None}

    def on_tick(elapsed: float):
        if args.no_restart or restart_fired["at"] is not None:
            return
        if elapsed >= args.restart_at:
            print(f"[k8s] t={elapsed:.1f}s  kubectl rollout restart deployment/{DEPLOYMENT}")
            proc = subprocess.run(
                ["kubectl", "rollout", "restart", f"deployment/{DEPLOYMENT}", "-n", NAMESPACE],
                capture_output=True, text=True,
            )
            restart_fired["at"] = round(elapsed, 2)
            restart_fired["rc"] = proc.returncode
            if proc.returncode != 0:
                print(f"[k8s] WARNING: rollout restart failed: {proc.stderr.strip()}")

    url = build_url()
    print(f"[k8s] target={url} host={args.host_header if args.via == 'ingress' else '-'} "
          f"rate={args.rate}/s duration={args.duration}s "
          f"restart_at={'none' if args.no_restart else args.restart_at}")

    host_header = args.host_header if (args.via == "ingress" and not args.url) else None

    try:
        if ctx:
            ctx.__enter__()
        results, max_lag = run_load(url, host_header, args.rate, args.duration,
                                    args.concurrency, args.timeout, on_tick)
    finally:
        if ctx:
            ctx.__exit__(None, None, None)

    counts = {"total": len(results), "ok": 0, "http_error": 0, "conn_error": 0, "timeout": 0}
    for r in results:
        counts[r.kind] += 1
    failures = counts["http_error"] + counts["conn_error"] + counts["timeout"]
    lat = [r.latency_ms for r in results]

    status_breakdown: dict[str, int] = {}
    for r in results:
        key = str(r.status) if r.status is not None else r.kind
        status_breakdown[key] = status_breakdown.get(key, 0) + 1

    # First and last failure offsets bracket the outage window — the single
    # most useful number when comparing naive vs tuned, because a rollout that
    # drops requests drops them in one contiguous burst around each pod swap.
    fail_offsets = [round(r.t_offset, 2) for r in results if r.kind != "ok"]

    cfg = {
        "target": url,
        "host_header": host_header,
        "via": args.via,
        "path": args.path,
        "rate_per_s": args.rate,
        "duration_s": args.duration,
        "restart_at_s": None if args.no_restart else args.restart_at,
        "concurrency": args.concurrency,
        "timeout_s": args.timeout,
        "deployment": DEPLOYMENT,
        "namespace": NAMESPACE,
    }

    if max_lag > 1.0 and invalid_reason is None:
        invalid_reason = (
            f"driver fell {max_lag:.2f}s behind schedule; the intended rate of "
            f"{args.rate}/s was not achieved and failure counts are understated."
        )

    record = {
        "record_type": "rolling_restart",
        "run_id": str(uuid.uuid4()),
        "timestamp": started.isoformat(),
        "label": args.label,
        "config": cfg,
        "config_hash": config_hash(cfg),
        "counts": counts,
        "failures": failures,
        "failure_rate_pct": round(100.0 * failures / counts["total"], 4) if counts["total"] else None,
        "status_breakdown": status_breakdown,
        "latency_ms": {
            "p50": percentile(lat, 0.50),
            "p95": percentile(lat, 0.95) if len(lat) >= 20 else None,
            "max": round(max(lat), 2) if lat else None,
        },
        "latency_n": len(lat),
        "first_failure_offset_s": fail_offsets[0] if fail_offsets else None,
        "last_failure_offset_s": fail_offsets[-1] if fail_offsets else None,
        "restart": restart_fired,
        "max_submit_lag_s": round(max_lag, 3),
        "valid": invalid_reason is None,
        "invalid_reason": invalid_reason,
        "host": {"platform": sys.platform, "python": sys.version.split()[0]},
    }

    append_record(record, args.results)

    # Machine-readable line first, so `... | tail -1 | jq` works.
    print()
    print(json.dumps(record, sort_keys=True, default=str))
    print()
    print("=" * 63)
    print(f"  rolling restart under load — label={args.label}")
    print("=" * 63)
    print(f"  target              {url}")
    print(f"  requests sent       {counts['total']}  ({args.rate}/s x {args.duration}s)")
    print(f"  2xx                 {counts['ok']}")
    print(f"  non-2xx             {counts['http_error']}")
    print(f"  connection errors   {counts['conn_error']}")
    print(f"  timeouts            {counts['timeout']}")
    print(f"  FAILURE RATE        {record['failure_rate_pct']}%")
    print(f"  latency p50 / max   {record['latency_ms']['p50']} ms / {record['latency_ms']['max']} ms")
    if fail_offsets:
        print(f"  failure window      t={record['first_failure_offset_s']}s .. "
              f"t={record['last_failure_offset_s']}s  ({len(fail_offsets)} requests)")
    print(f"  rollout fired at    {restart_fired['at']}s (rc={restart_fired['rc']})")
    print(f"  valid               {record['valid']}")
    if invalid_reason:
        print(f"  invalid because     {invalid_reason}")
    print(f"  appended to         {args.results}")
    print()
    print(f"  compare runs:  {os.path.relpath(__file__)} --compare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
