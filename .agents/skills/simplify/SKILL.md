---
name: simplify
description: Review the changed Noesis code for duplication, dead weight, and avoidable complexity, then fix the issues found. Use after implementation and before commit.
version: 1.0.0
user-invocable: true
---

# Simplify

This is a cleanup pass after code exists. Goal: make the current change smaller, clearer, and easier to maintain without altering intended behavior.

## Procedure

1. Inspect only the changed files first:

```bash
git diff --name-only --diff-filter=ACMR
git diff --stat
```

2. In changed code, look for:
- duplicated logic that should be shared
- dead imports, dead branches, and stale comments
- helper functions with only one trivial call site
- avoidable prop/state churn in React
- backend branching that can be flattened
- test duplication that hides intent

3. Fix issues directly when safe.

4. Re-run the smallest meaningful verification for touched areas.

## Guardrails

- Do not refactor unrelated files
- Do not widen scope into architecture changes unless the user asked
- Preserve behavior first; cleanup is only good if it lowers maintenance cost
