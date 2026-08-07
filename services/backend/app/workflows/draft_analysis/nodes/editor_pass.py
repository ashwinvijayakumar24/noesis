"""
Editor Pass Node

Fast pre-screen (gpt-5-mini, ~1s) before committing to full reviewer panel.
Real journals do this — if paper is obviously out of scope or has fatal flaws,
don't waste reviewer time.

If proceed_to_review=False, graph routes directly to synthesize_report.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.schemas import EditorPassOutput
from app.workflows.draft_analysis.domain_routing import domain_context_block
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai_client, get_completion_params
from app.services.retry_utils import parse_chat_completion_with_retries

logger = get_logger(__name__)
client = None


def _get_client():
    global client
    if client is None:
        client = get_async_openai_client()
    return client

EDITOR_PASS_PROMPT = """You are a senior editor at a top-tier research venue performing an initial desk check.

Your job is a FAST pre-screen — not a full review. Determine whether this paper is:
1. Structurally complete enough to send to reviewers
2. Free of immediately fatal flaws
3. At a baseline publishable writing level

FATAL FLAWS (any one = reject at desk):
- Single anecdote or case study presented as generalizable evidence with no acknowledgment
- No methods or approach section at all
- Fewer than 4 distinct sections
- Obvious plagiarism signals (repeated boilerplate, mismatched citations)
- Not a research paper (blog post, listicle, opinion piece)

WRITING QUALITY:
- "publishable": Good enough to send to reviewers as-is
- "needs_revision": Has issues but not fatal; reviewers can work with it
- "major_revision": Significant rewrite needed before review is meaningful

SCOPE: Is this recognizable as a research paper in any scientific/technical field?
Set scope_appropriate=false only for clearly off-topic content (recipes, fiction, business plans).

Be lenient on quality — your job is to filter out obviously unreviable submissions,
not to pre-judge scientific merit. When in doubt, let it through (proceed_to_review=true).

IMPORTANT: Do NOT comment on section metadata anomalies (duplicate entries, 'other'
placeholders, running-header echoes) in your notes — these are parser extraction
artifacts, not manuscript flaws. Only comment on content visible in the draft text.

Return a compact structured assessment. Keep notes under 30 words and list only
fatal flaws that independently justify desk rejection."""


async def editor_pass_node(state: DraftAnalysisState) -> dict:
    """
    Fast editorial desk check before committing to full reviewer panel.
    gpt-5-mini, ~$0.0002/call.
    """
    draft_id = state.get("draft_id", "")
    logger.info(f"[EditorPass] Starting for draft_id={draft_id}")

    structure = state.get("structure") or {}
    draft_content = state.get("draft_content", "")
    editing_feedback = (state.get("analysis") or {}).get("editing_feedback") or {}
    profile = state.get("manuscript_profile") or {}

    # Build context — only the opening is needed for a fast desk screen.
    sections_present = [s.get("type", "?") for s in structure.get("sections", []) if s.get("type") != "other"]
    word_count = structure.get("word_count", 0)
    section_count = len(structure.get("sections", []))

    context = f"""PAPER OVERVIEW:
Word count: {word_count}
Section count: {section_count}
Sections present: {', '.join(sections_present) or 'unknown'}
{domain_context_block(profile)}

STAGE 1 ISSUES (mechanical):
Grammar issues: {len(editing_feedback.get('grammar_issues', []))}
Structural notes: {editing_feedback.get('structural_notes', [])}

DRAFT CONTENT (first 1200 chars):
{draft_content[:1200]}
"""

    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": EDITOR_PASS_PROMPT},
                {"role": "user", "content": context},
            ],
            max_completion_tokens=2500,
            response_format=EditorPassOutput,
            **get_completion_params(),
        )

        decision = response.parsed
        logger.info(
            f"[EditorPass] proceed={decision.proceed_to_review}, "
            f"quality={decision.writing_quality}, "
            f"fatal_flaws={len(decision.fatal_flaws)}"
        )

        return {
            "editor_decision": decision.model_dump(),
            "current_step": "Editor Pass",
            "progress_percentage": 80,
        }

    except Exception as exc:
        logger.warning(f"[EditorPass] Failed (non-fatal, letting review proceed): {exc}")
        # On failure, always let the review proceed — don't block on editor crash
        return {
            "editor_decision": {
                "proceed_to_review": True,
                "fatal_flaws": [],
                "scope_appropriate": True,
                "writing_quality": "needs_revision",
                "notes": f"Editor pass unavailable: {exc}",
            },
            "current_step": "Editor Pass (Skipped)",
            "progress_percentage": 80,
        }
