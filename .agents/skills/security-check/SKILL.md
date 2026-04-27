---
name: security-check
description: Run a focused Noesis security pass for secrets, auth gaps, unsafe query patterns, and payment or research-data exposure. Use before deploys and after backend/auth changes.
version: 1.0.0
user-invocable: true
---

# Security Check

Noesis handles academic research data, Supabase auth, and Stripe billing. Focus on concrete risks, not generic security theater.

## Run when

- Before deploy
- Auth, billing, upload, export, or API route changes landed
- New environment variables or service integrations were added

## Procedure

1. Scan for likely secrets and unsafe config:

```bash
rg -n "(OPENAI|SUPABASE|STRIPE|SECRET|TOKEN|PASSWORD|API_KEY|SERVICE_ROLE)" . --glob '!**/.env*' --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**'
```

2. Review backend routes for missing auth or quota enforcement around sensitive operations:

```bash
rg -n "APIRouter|@router\\.(get|post|put|patch|delete)|Depends\\(" services/backend/app/api/routes --glob '*.py'
```

3. Check for high-risk patterns:
- raw SQL or unsafe string interpolation
- service-role Supabase usage in user-facing paths
- file upload handling without validation
- export endpoints without auth checks
- Stripe webhook verification mistakes
- permissive CORS or debug behavior in prod paths

4. Rank findings:
- P0: secret exposure, unauthenticated sensitive route, payment bypass, arbitrary file access
- P1: injection risk, broken authorization boundaries, unsafe upload flow
- P2: weak hardening, noisy but non-exploitable config issues

5. Output findings first, ordered by severity, with file references and concrete exploit/risk statements.

## Guardrails

- Do not invent vulnerabilities without code evidence
- Prefer route and service code over README/security docs
- If no findings exist, say that explicitly and note any residual testing gaps
