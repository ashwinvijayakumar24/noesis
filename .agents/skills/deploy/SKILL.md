---
name: deploy
description: "Deploy Noesis frontend changes to production with a release gate: verify critical checks first, then ship and confirm user-facing SEO assets if the environment is configured."
version: 1.0.0
user-invocable: true
---

# Deploy

This skill is for shipping Noesis safely, not for bypassing release checks.

## Release gate

Before deploying, confirm:
- relevant tests passed
- no unresolved `check-gpt` or `security-check` findings remain
- required DB migrations are accounted for

## Procedure

1. Identify the deploy surface. Default assumption from project docs:
- frontend on Vercel
- backend and infra handled separately

2. If frontend deploy is intended, run the project’s Vercel flow from the correct directory and capture the resulting production URL.

3. Verify critical public assets after deploy if applicable:
- landing page loads
- metadata reflects current positioning
- `robots.txt`
- `sitemap.xml`
- canonical/OG basics if part of the change

4. Report:
- what was deployed
- environment/URL
- checks performed
- any remaining manual steps such as Supabase migrations

## Guardrails

- Do not deploy blindly if the Vercel project is not linked or credentials are missing
- Do not claim backend or migration deployment happened unless it was explicitly executed
- Stop and surface blockers instead of improvising production changes
