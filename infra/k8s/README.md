# Noesis on kind — raw Kubernetes manifests

Runs the FastAPI backend, the Celery worker and Redis on a local
[kind](https://kind.sigs.k8s.io/) cluster. Raw YAML, no Helm, on purpose —
this is a learning build and the comments in the manifests are half the point.

## What is and is not in the cluster

| Component | In cluster | Why |
|---|---|---|
| `noesis-api` (FastAPI) | yes | Deployment, 2 replicas, ClusterIP + Ingress |
| `noesis-worker` (Celery) | yes | Deployment, 1 replica, **no Service** |
| `noesis-redis` | yes | StatefulSet + headless Service + 1Gi PVC. The real broker. |
| Postgres / pgvector | **no** | Production is Supabase (remote managed). The compose `pgvector` service is eval-only. |
| Frontend | **no** | Ships on Vercel. |
| GROBID / Docling | **no** | Multi-GB images under amd64 emulation; they OOM an 8 GB Docker. Their URLs point at `127.0.0.1:9` so calls fail fast instead of hanging. PDF body parsing is therefore broken in this cluster, by design. |

## Files, in apply order

```
kind-cluster.yaml          # kind topology (not a k8s object)
00-namespace.yaml
01-configmap.yaml          # non-secret config
02-secret.example.yaml     # TEMPLATE — copy to 02-secret.yaml (gitignored)
10-redis-statefulset.yaml  # StatefulSet + headless Service
20-api-deployment.yaml     # Deployment + ClusterIP Service
21-worker-deployment.yaml  # Deployment only
30-ingress.yaml
40-pdb.yaml
```

## Runbook

All commands are run from the **repo root**.

### 1. Create the cluster

```bash
kind create cluster --config infra/k8s/kind-cluster.yaml
kubectl cluster-info --context kind-noesis
```

### 2. Build the image and load it into kind

kind nodes have their own containerd; an image in your local Docker daemon is
invisible to them until it is loaded.

```bash
docker build -t noesis-backend:dev services/backend
kind load docker-image noesis-backend:dev --name noesis
```

### 3. Install ingress-nginx

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

### 4. Namespace and config

```bash
kubectl apply -f infra/k8s/00-namespace.yaml
kubectl apply -f infra/k8s/01-configmap.yaml
```

### 5. Create the Secret

Easiest path — reuse the `.env` file compose already consumes:

```bash
kubectl create secret generic noesis-secrets \
  --namespace noesis \
  --from-env-file=services/backend/.env
```

Or copy the template and fill it in (`infra/k8s/02-secret.yaml` is gitignored):

```bash
cp infra/k8s/02-secret.example.yaml infra/k8s/02-secret.yaml
$EDITOR infra/k8s/02-secret.yaml
kubectl apply -f infra/k8s/02-secret.yaml
```

### 6. Apply the workloads, in order

Redis first: both the API and the worker connect to the broker on boot, and
readiness will hold them out of service until it is up.

```bash
kubectl apply -f infra/k8s/10-redis-statefulset.yaml
kubectl apply -f infra/k8s/20-api-deployment.yaml
kubectl apply -f infra/k8s/21-worker-deployment.yaml
kubectl apply -f infra/k8s/30-ingress.yaml
kubectl apply -f infra/k8s/40-pdb.yaml
```

Steps 4–6 are what `make k8s-up` does.

### 7. Host entry

```bash
echo "127.0.0.1 noesis.local" | sudo tee -a /etc/hosts
```

### 8. Verify

```bash
kubectl -n noesis get pods,svc,statefulset,pvc,ingress,pdb

kubectl -n noesis rollout status deploy/noesis-api --timeout=180s
kubectl -n noesis rollout status deploy/noesis-worker --timeout=180s

# Broker reachable from inside the cluster
kubectl -n noesis exec statefulset/noesis-redis -- redis-cli ping     # PONG

# Worker actually consuming
kubectl -n noesis exec deploy/noesis-worker -- \
  celery -A app.celery_app inspect ping --timeout 10

# Through the ingress
curl -i http://noesis.local/healthz/ready

# Bypass the ingress if the above fails — isolates ingress from app
kubectl -n noesis port-forward svc/noesis-api 8000:8000 &
curl -i http://localhost:8000/healthz/ready
```

### 9. Tear down

```bash
kubectl delete namespace noesis          # workloads only; keeps the cluster
kind delete cluster --name noesis        # everything, including the PVC
```

`make k8s-down` does the second one.

## Troubleshooting

- **`ErrImagePull` / `ImagePullBackOff`** — the image was not loaded into the
  node. Re-run `make k8s-load-image`, then
  `kubectl -n noesis rollout restart deploy/noesis-api deploy/noesis-worker`.
  (`imagePullPolicy: IfNotPresent` is what makes the local tag usable at all.)
- **API pod stuck `0/1 Running`** — readiness is failing. It depends on Redis
  and Supabase: `kubectl -n noesis logs deploy/noesis-api` and check the Secret
  actually has `SUPABASE_URL` / `OPENAI_API_KEY`
  (`kubectl -n noesis get secret noesis-secrets -o jsonpath='{.data}' | tr ',' '\n'`).
- **`CreateContainerConfigError`** — the Secret does not exist yet. Step 5.
- **404 from `noesis.local`** — ingress-nginx is not installed, or `/etc/hosts`
  is missing the entry. `kubectl -n ingress-nginx get pods`.
- **Pod evicted under memory pressure** — the worker (Burstable QoS) is
  evicted before the API (Guaranteed). That ordering is deliberate; see the
  QoS comments in the two Deployment manifests.
- **PVC `Pending`** — kind's local-path provisioner is not ready yet; it only
  binds once the pod is scheduled (`WaitForFirstConsumer`).
