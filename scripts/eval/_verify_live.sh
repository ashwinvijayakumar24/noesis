#!/usr/bin/env bash
set -euo pipefail

BACKEND="${BACKEND:-noesis-backend}"
REPO_ROOT="${REPO_ROOT:-$(pwd)}"
CONTAINER_ROOT="${CONTAINER_ROOT:-/app}"
HOST_PYTHON="${HOST_PYTHON:-python3}"

checksum_dir_host() {
  local dir="$1"
  "$HOST_PYTHON" - "$dir" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
digest = hashlib.md5()
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    rel = path.relative_to(root).as_posix()
    if "__pycache__/" in rel or rel.endswith(".pyc") or rel == ".DS_Store":
        continue
    digest.update(rel.encode())
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
}

checksum_dir_container() {
  local dir="$1"
  docker exec -i "$BACKEND" python - "$dir" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
digest = hashlib.md5()
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    rel = path.relative_to(root).as_posix()
    if "__pycache__/" in rel or rel.endswith(".pyc") or rel == ".DS_Store":
        continue
    digest.update(rel.encode())
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
}

verify_pair() {
  local label="$1"
  local host_dir="$2"
  local container_dir="$3"
  local host_sum
  local container_sum

  host_sum="$(checksum_dir_host "$host_dir")"
  container_sum="$(checksum_dir_container "$container_dir")"
  if [[ "$host_sum" != "$container_sum" ]]; then
    echo "[eval] checksum mismatch for $label" >&2
    echo "[eval] host      $host_sum  $host_dir" >&2
    echo "[eval] container $container_sum  $container_dir" >&2
    exit 1
  fi
  echo "[eval] checksum ok: $label $host_sum"
}

WORKFLOW_HOST="$REPO_ROOT/services/backend/app/workflows/draft_analysis"
WORKFLOW_CONTAINER="$CONTAINER_ROOT/app/workflows/draft_analysis"

echo "[eval] deleting stale .pyc files before sync"
find "$REPO_ROOT/scripts" "$WORKFLOW_HOST" -type f -name "*.pyc" -delete
docker exec "$BACKEND" find "$CONTAINER_ROOT/scripts" "$WORKFLOW_CONTAINER" -type f -name "*.pyc" -delete

echo "[eval] syncing scripts/ into $BACKEND:$CONTAINER_ROOT/scripts"
docker exec "$BACKEND" rm -rf "$CONTAINER_ROOT/scripts"
docker exec "$BACKEND" mkdir -p "$CONTAINER_ROOT/scripts" "$CONTAINER_ROOT/app"
docker cp "$REPO_ROOT/scripts/." "$BACKEND:$CONTAINER_ROOT/scripts"

echo "[eval] syncing backend app/ into $BACKEND:$CONTAINER_ROOT/app"
docker exec "$BACKEND" rm -rf "$WORKFLOW_CONTAINER"
docker cp "$REPO_ROOT/services/backend/app/." "$BACKEND:$CONTAINER_ROOT/app"

if [[ -d "$REPO_ROOT/pdfs" ]]; then
  echo "[eval] syncing pdfs/ into $BACKEND:$CONTAINER_ROOT/pdfs"
  docker exec "$BACKEND" mkdir -p "$CONTAINER_ROOT/pdfs"
  docker cp "$REPO_ROOT/pdfs/." "$BACKEND:$CONTAINER_ROOT/pdfs"
fi

verify_pair "scripts" "$REPO_ROOT/scripts" "$CONTAINER_ROOT/scripts"
verify_pair "draft_analysis workflow" "$WORKFLOW_HOST" "$WORKFLOW_CONTAINER"

PIPELINE_VERSION="$(checksum_dir_container "$WORKFLOW_CONTAINER")"
echo "[eval] live pipeline_version=$PIPELINE_VERSION"
