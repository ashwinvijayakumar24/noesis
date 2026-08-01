"""
LLM judge: score a Noesis export JSON against an approved gold critique.

Usage:
    # Score export vs gold
    python scripts/eval/judge.py --export results/x.json --gold gold/draft3.gold.md

    # Bootstrap a candidate gold critique from a raw PDF (edit then rename to .gold.md)
    python scripts/eval/judge.py --bootstrap-gold pdfs/draft3.pdf

Must run inside the backend container OR with OPENAI_API_KEY in env.
"""

import argparse
import json
import sys
from pathlib import Path

if Path("/app/app").exists():
    REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _svc = str(REPO_ROOT / "services" / "backend")
    if _svc not in sys.path:
        sys.path.insert(0, _svc)

EVAL_DIR = Path(__file__).resolve().parent
GOLD_DIR = EVAL_DIR / "gold"

JUDGE_SYSTEM_PROMPT = """You are a strict academic meta-reviewer evaluating an AI pre-submission analysis tool (Noesis).

You will receive:
1. NOESIS_EXPORT: the full structured output from Noesis (JSON summary).
2. GOLD_CRITIQUE: the approved reference critique for this draft (what the analysis SHOULD say).

Score Noesis on 6 dimensions, each 0–10. For EVERY sub-score you MUST include a `evidence` field with a verbatim quote from NOESIS_EXPORT that justifies your score. No quote = score is invalid; default to 5 with a note.

Dimensions:
1. grounding (0-10): Are claims/findings tied to real draft text and real cited sources? Do task anchors quote the manuscript verbatim?
2. hallucination_free (0-10): 10 = zero invented sources, quotes, or numbers. Any invented item = 0 on this dimension and must be listed in `hallucinations`.
3. coverage (0-10): Did Noesis catch the key issues the gold critique identifies? Score = recall vs gold.
4. citation_accuracy (0-10): Are citation verdicts (strong/moderate/weak/none) correct per gold?
5. actionability (0-10): Are revision tasks specific, anchored, and actionable (not vague advice)?
6. architecture_integrity (0-10): No dropped/empty sections, no null fields where content was expected, no truncated reviewer outputs.

Return ONLY valid JSON matching this exact schema:
{
  "overall": <float 0-10, mean of dims>,
  "dims": {
    "grounding": {"score": <int>, "evidence": "<verbatim quote>", "notes": "<str>"},
    "hallucination_free": {"score": <int>, "evidence": "<verbatim quote>", "notes": "<str>"},
    "coverage": {"score": <int>, "evidence": "<verbatim quote>", "notes": "<str>"},
    "citation_accuracy": {"score": <int>, "evidence": "<verbatim quote>", "notes": "<str>"},
    "actionability": {"score": <int>, "evidence": "<verbatim quote>", "notes": "<str>"},
    "architecture_integrity": {"score": <int>, "evidence": "<verbatim quote>", "notes": "<str>"}
  },
  "hallucinations": ["<list of any invented source/quote/number>"],
  "misses": ["<key issue in gold that Noesis missed>"],
  "notes": "<overall summary>"
}"""

BOOTSTRAP_SYSTEM_PROMPT = """You are an expert academic reviewer generating a REFERENCE CRITIQUE for a research draft.

This critique will serve as the ground-truth "gold standard" that an AI analysis tool is measured against.

Be thorough and specific. Cover:
- Major methodological issues (underpowered study, missing controls, confounds)
- Citation gaps (what seminal work is missing? what is misrepresented?)
- Structural problems (missing sections, weak abstract, unclear contributions)
- Novelty positioning (how does this differ from prior art?)
- Writing and clarity issues
- What a typical Reviewer 2 would say

Format as structured markdown with severity (HIGH/MEDIUM/LOW) per finding.
Be specific — quote the draft text when identifying a problem."""


def _openai_client():
    from app.core.openai_client import get_openai_client
    return get_openai_client()


def _call_gpt(client, system: str, user: str, max_tokens: int = 2000) -> str:
    from app.core.openai_client import get_completion_params
    response = client.chat.completions.create(
        model="gpt-5.2-chat-latest",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_completion_tokens=max_tokens,
        **get_completion_params(),
    )
    return response.choices[0].message.content or ""


def _truncate_export(export: dict, max_chars: int = 12000) -> str:
    """Produce a compact summary of the export for the judge context."""
    meta = (export.get("analysis") or {}).get("analysis_metadata") or {}
    profile = meta.get("manuscript_profile") or {}
    tasks = export.get("durable_revision_tasks") or []
    claims = export.get("claims") or []
    gaps = export.get("coverage_gaps") or []
    reviewers = export.get("reviewer_panel_outputs") or []
    meta_reviews = export.get("meta_reviews") or []
    citation_sugg = export.get("citation_suggestions") or []

    lines = [
        "=== NOESIS EXPORT SUMMARY ===",
        f"Routing domain: {profile.get('routing_domain')}",
        f"Verdict: {meta.get('verdict')}",
        f"Readiness score: {meta.get('readiness_score')}",
        f"Editorial recommendation: {meta.get('editorial_recommendation')}",
        "",
        f"--- REVISION TASKS ({len(tasks)}) ---",
    ]
    for t in tasks[:20]:
        lines.append(f"[{t.get('severity','?').upper()}] {t.get('task_type','')}: {t.get('problem','')[:200]}")
        if t.get("anchor_text"):
            lines.append(f"  anchor: \"{t['anchor_text'][:100]}\"")
        if t.get("suggested_action"):
            lines.append(f"  action: {t['suggested_action'][:150]}")

    lines.append(f"\n--- COVERAGE GAPS ({len(gaps)}) ---")
    for g in gaps[:10]:
        lines.append(f"  {g.get('gap_type','')}: {g.get('description','')[:200]}")

    lines.append(f"\n--- CLAIMS ({len(claims)}) ---")
    for c in claims[:15]:
        lines.append(f"  [{c.get('claim_type','')}|{c.get('citation_quality','')}] {c.get('claim_text','')[:150]}")

    lines.append(f"\n--- REVIEWER PANEL ({len(reviewers)}) ---")
    for r in reviewers:
        persona = r.get("reviewer_id") or r.get("persona") or r.get("id") or "reviewer"
        rec = r.get("recommendation") or ""
        lines.append(f"  {persona}: {rec[:100]}")
        issues = r.get("issues") or []
        for issue in issues[:5]:
            sev = issue.get('severity') or issue.get('issue_type') or '?'
            desc = issue.get('description') or issue.get('problem') or ''
            lines.append(f"    - [{sev}] {desc[:150]}")

    lines.append(f"\n--- META REVIEW ({len(meta_reviews)}) ---")
    if meta_reviews:
        mr = meta_reviews[0]
        lines.append(f"  recommendation: {mr.get('overall_recommendation','')}")
        for p in (mr.get("priorities") or [])[:5]:
            lines.append(f"  priority: {str(p)[:150]}")

    lines.append(f"\n--- CITATION SUGGESTIONS ({len(citation_sugg)}) ---")
    for cs in citation_sugg[:5]:
        lines.append(f"  {cs.get('document_title','')}: {cs.get('suggestion_type','')}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    return text


def score(export_path: Path, gold_path: Path) -> dict:
    export = json.loads(export_path.read_text())
    gold_text = gold_path.read_text()

    export_summary = _truncate_export(export)
    user_msg = f"NOESIS_EXPORT:\n{export_summary}\n\n---\nGOLD_CRITIQUE:\n{gold_text}"

    client = _openai_client()
    raw = _call_gpt(client, JUDGE_SYSTEM_PROMPT, user_msg, max_tokens=2000)

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    # Retry once with higher token budget if JSON parse fails
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print("[judge] JSON parse failed on first attempt, retrying with higher token budget…", file=__import__("sys").stderr)
        raw2 = _call_gpt(client, JUDGE_SYSTEM_PROMPT, user_msg, max_tokens=3000)
        raw2 = raw2.strip()
        if raw2.startswith("```"):
            raw2 = raw2.split("```", 2)[1]
            if raw2.startswith("json"):
                raw2 = raw2[4:]
            raw2 = raw2.rsplit("```", 1)[0]
        result = json.loads(raw2)

    # Enforce overall = mean of dims
    dim_scores = [v["score"] for v in result.get("dims", {}).values()]
    if dim_scores:
        result["overall"] = round(sum(dim_scores) / len(dim_scores), 2)

    # Hard override: any hallucination → hallucination_free dim = 0
    if result.get("hallucinations"):
        result["dims"]["hallucination_free"]["score"] = 0
        result["overall"] = round(sum(
            v["score"] for v in result["dims"].values()
        ) / len(result["dims"]), 2)

    result["export_file"] = str(export_path)
    result["gold_file"] = str(gold_path)
    return result


def bootstrap_gold(draft_path: Path) -> Path:
    import asyncio
    draft_bytes = draft_path.read_bytes()
    file_ext = draft_path.suffix.lstrip(".")

    # extract_text is async, returns dict with "text" key
    from app.services.draft_processing import extract_text
    result = asyncio.get_event_loop().run_until_complete(extract_text(draft_bytes, file_ext))
    draft_text = result.get("text") or result.get("full_text") or (result if isinstance(result, str) else "")
    if not draft_text.strip():
        print(f"[judge] Could not extract text from {draft_path}")
        sys.exit(1)

    truncated = draft_text[:15000]
    client = _openai_client()
    critique = _call_gpt(
        client,
        BOOTSTRAP_SYSTEM_PROMPT,
        f"DRAFT TEXT:\n{truncated}",
        max_tokens=3000,
    )

    GOLD_DIR.mkdir(exist_ok=True)
    out_path = GOLD_DIR / f"{draft_path.stem}.gold.draft.md"
    out_path.write_text(critique)
    print(f"[judge] Candidate gold written to: {out_path}")
    print(f"[judge] Edit it, then rename to: {draft_path.stem}.gold.md to approve.")
    return out_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Noesis eval judge")
    sub = p.add_subparsers(dest="cmd")

    score_p = sub.add_parser("score", help="Score an export against a gold file")
    score_p.add_argument("--export", required=True)
    score_p.add_argument("--gold", required=True)
    score_p.add_argument("--out", default=None, help="Write score JSON to this path")

    boot_p = sub.add_parser("bootstrap-gold", help="Generate candidate gold for a draft PDF")
    boot_p.add_argument("--draft", required=True)

    # Flat compat: judge.py --export x --gold y  (no subcommand)
    p.add_argument("--export", default=None)
    p.add_argument("--gold", default=None)
    p.add_argument("--bootstrap-gold", default=None, dest="bootstrap_gold_draft")
    p.add_argument("--out", default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Bootstrap mode
    bootstrap_draft = getattr(args, "bootstrap_gold_draft", None) or (
        args.draft if getattr(args, "cmd", None) == "bootstrap-gold" else None
    )
    if bootstrap_draft:
        dp = (REPO_ROOT / bootstrap_draft).resolve()
        bootstrap_gold(dp)
        sys.exit(0)

    # Score mode
    export_arg = args.export or getattr(args, "export", None)
    gold_arg = args.gold or getattr(args, "gold", None)
    if not export_arg or not gold_arg:
        print("[judge] Provide --export and --gold, or --bootstrap-gold <draft>")
        sys.exit(1)

    export_path = Path(export_arg).resolve()
    gold_path = Path(gold_arg).resolve()
    if not gold_path.exists():
        # Try relative to gold dir
        gold_path = (GOLD_DIR / gold_arg).resolve()
    if not export_path.exists() or not gold_path.exists():
        print(f"[judge] File not found: export={export_path} gold={gold_path}")
        sys.exit(1)

    result = score(export_path, gold_path)
    out_json = json.dumps(result, indent=2)

    out_arg = args.out
    if out_arg:
        Path(out_arg).write_text(out_json)
    else:
        print(out_json)
