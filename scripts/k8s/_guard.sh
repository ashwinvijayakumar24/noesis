#!/usr/bin/env bash
# Shared safety guard. Sourced by every script in scripts/k8s/.
#
# These scripts scale StatefulSets to zero, patch liveness probes so they fail,
# and LPUSH junk onto a Celery broker. Every one of those is destructive. The
# only thing standing between "instructive demo" and "outage" is the context
# check below, so it lives in one file and every script calls it first.
#
# Rule: the current kubectl context must start with `kind-`. kind names its
# contexts `kind-<clustername>` and nothing else does, so this is a reliable
# "am I on a throwaway local cluster" test. infra/k8s/kind-cluster.yaml names
# the cluster `noesis`, so the expected context is `kind-noesis`.
#
# Second rule: the namespace is hardcoded to `noesis` and every kubectl call in
# every script passes -n "$K8S_NAMESPACE" explicitly. Nothing here ever runs
# against the active namespace, and nothing ever touches a cluster-scoped
# object.
set -euo pipefail

K8S_NAMESPACE="noesis"

require_kind_context() {
  local ctx
  ctx="$(kubectl config current-context 2>/dev/null || true)"

  if [[ -z "$ctx" ]]; then
    echo "[k8s] FATAL: kubectl has no current context." >&2
    echo "[k8s]        kind create cluster --config infra/k8s/kind-cluster.yaml" >&2
    exit 1
  fi

  if [[ "$ctx" != kind-* ]]; then
    echo "[k8s] FATAL: current kubectl context is '$ctx'." >&2
    echo "[k8s]        This script breaks things on purpose and will only run" >&2
    echo "[k8s]        against a kind- context. Refusing to continue." >&2
    exit 1
  fi

  if ! kubectl get namespace "$K8S_NAMESPACE" >/dev/null 2>&1; then
    echo "[k8s] FATAL: namespace '$K8S_NAMESPACE' does not exist on '$ctx'." >&2
    echo "[k8s]        kubectl apply -f infra/k8s/" >&2
    exit 1
  fi

  echo "[k8s] context=$ctx namespace=$K8S_NAMESPACE"
}

# Millisecond-resolution wall clock, portable to macOS (no `date +%s%N`).
now_ms() {
  python3 -c 'import time; print(int(time.time() * 1000))'
}
