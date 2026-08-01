# Docker Compose Profiles

## Why

Docker Desktop on the dev machines is allocated **~8.2 GB**:

```
$ docker info --format '{{.MemTotal}}'
8217903104
```

GROBID (`lfoppiano/grobid:0.7.0`) and Docling (`docling-serve-cpu`) are each
multi-GB images, and on Apple Silicon both run under `linux/amd64` emulation,
which adds further overhead. Starting the whole stack at once OOMs. Planned
additions — a local Postgres+pgvector service (`core`) and Langfuse
observability (`obs`) — only make the ceiling worse.

Profiles let you start only the slice a given task needs.

## Profiles

| Profile | Services | Approx. memory | Notes |
|---|---|---|---|
| `core` | redis *(+ pgvector Postgres, TODO)* | **~15 MB** (measured: 14.52 MiB) | Base infra. Safe to leave running. |
| `parse` | grobid, docling-serve | **~3-5 GB** | PDF parsing sidecars. Emulated amd64. |
| `app` | redis, backend, celery-worker, frontend | **~1-2 GB** | Cannot start alone — see hazard. |
| `obs` | *(reserved — Langfuse, not yet added)* | ~500 MB - 1 GB | No service declares it yet, so it does **not** appear in `docker compose config --profiles`. |
| `full` | everything | **> 8 GB** | **Will not fit in 8 GB. Reference only.** |

Memory figures other than `core` are estimates; only `core` was measured.

## Services in multiple profiles

`redis` carries `core`, `app`, and `full`. Both `backend` and `celery-worker`
have `depends_on: redis` with `condition: service_healthy`, so starting `app`
must be able to bring redis up on its own. The pgvector Postgres service will
follow the same pattern (`core` + `app` + `full`) once added.

## Cross-profile `depends_on` hazard

`celery-worker` (profile `app`) has `depends_on: grobid`, and `grobid` is in
`parse` only. **Compose does not auto-enable a dependency's profile.** Verified
on Compose v2.40.3:

```
$ docker compose --profile app config --services
service "celery-worker" depends on undefined service "grobid": invalid compose project
# exit 1
```

`grobid` was deliberately *not* added to `app` — that would pull a multi-GB
emulated image into the light path and defeat the purpose of profiles. Instead,
start the app together with the parsers:

```
$ docker compose --profile app --profile parse config --services
grobid
redis
backend
celery-worker
docling-serve
frontend
# exit 0
```

If you want a genuinely light app-only stack, comment out the two `grobid`
lines under `celery-worker`'s `depends_on`. That is a behavioural change, so
make it deliberately.

No other hazards: `backend -> redis` (redis carries `app`), `frontend ->
backend` (both `app`). `docling-serve` is reached only over `DOCLING_URL` at
request time and is never a `depends_on` target, so `app` does not drag it in.

## Commands

```bash
cd infra

# lightest — redis only
docker compose --profile core up -d
docker compose ps
docker compose --profile core down

# parsers only
docker compose --profile parse up -d

# the application (must include parse — see hazard above)
docker compose --profile app --profile parse up -d

# everything — will not fit in 8 GB
docker compose --profile full up -d

# stop everything and drop volumes
docker compose down -v

# introspection
docker compose config --quiet                    # validate syntax
docker compose config --profiles                 # list defined profiles
docker compose --profile core config --services  # what a profile starts
docker stats --no-stream                         # live memory use
```
