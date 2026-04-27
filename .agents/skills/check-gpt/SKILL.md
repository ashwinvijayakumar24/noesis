---
name: check-gpt
description: Audit Noesis Python code for GPT-5.2 regressions. Use after backend changes or before deploy to catch `max_tokens`, model drift, and other OpenAI API mistakes that would break requests.
version: 1.0.0
user-invocable: true
---

# Check GPT

Noesis uses `gpt-5.2` with `max_completion_tokens`. A single `max_tokens` regression causes a 400 error.

## Run when

- Backend OpenAI call paths changed
- Any file under `services/backend/app/` touched AI logic
- Before deploy when GPT usage might have changed

## Procedure

1. Scan Python code, not prose:

```bash
rg -n "max_tokens|max_completion_tokens|gpt-4o|gpt-5\\.2|chat\\.completions\\.create|responses\\.create" services/backend --glob '*.py'
```

2. Treat these as failures unless there is a documented exception:
- `max_tokens=`
- `model="gpt-4o"` or equivalent GPT-4o fallback
- inconsistent token parameter names in OpenAI calls

3. Verify Noesis constraints from `AGENTS.md`:
- `gpt-5.2`
- `max_completion_tokens`
- never revert to `gpt-4o`

4. Report results with file paths and the exact bad call sites.

5. If the user asked for fixes, patch the offending files and rerun the scan.

## Output format

- `Pass`: no violating Python call sites found
- `Fail`: list each violation with file path and why it is dangerous

## Guardrails

- Ignore markdown and archived notes unless the user explicitly wants doc cleanup
- Prioritize runtime code in `services/backend/app/`
- If both `Responses API` and `Chat Completions API` appear, validate each against current project conventions before editing
