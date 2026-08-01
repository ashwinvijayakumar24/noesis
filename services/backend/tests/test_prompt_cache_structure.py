"""Structural guarantees that make OpenAI's automatic prefix cache usable.

No network. These tests pin the *shape* of the reviewer-panel prompt:

  * the invariant prefix (system message + shared user prefix) is byte-identical
    across all three personas — this is the property the cache keys on;
  * the variable persona block appears strictly after that prefix;
  * nothing volatile (timestamp, uuid, run/draft id) leaks into the prefix;
  * the manuscript-compaction flag defaults OFF and, when on, produces bounded
    output including for a manuscript with no detectable section headings.
"""

import re

import pytest

from app.workflows.draft_analysis.nodes.reviewer_panel import (
    REVIEWER_PERSONAS,
    REVIEWER_PROMPTS,
    SHARED_REVIEWER_PREAMBLE,
    _reviewer_manuscript_text,
    _section_excerpts,
    build_reviewer_messages,
    build_shared_reviewer_prefix,
    reviewer_compaction_enabled,
)

REVIEWER_TYPES = ("literature_positioning", "methodology", "clarity")


def _state(draft: str = "## Methods\nWe measured the thing.\n") -> dict:
    return {
        "draft_id": "draft-abc-123",
        "project_id": "project-xyz",
        "user_id": "user-42",
        "draft_content": draft,
        "paper_type": "empirical",
        "structure": {"sections": [{"type": "methods", "title": "Methods"}], "word_count": 4200},
        "manuscript_profile": {
            "genre": "empirical",
            "study_design": "cohort",
            "domain_tags": ["biomedical", "clinical"],
            "routing_domain": "biomedical",
            "evidence_mode": "empirical",
        },
        "claims": [],
        "claims_with_citations": [],
        "coverage_gaps": [],
        "external_sources": [],
        "diagnostic_findings": [],
        "structural_feedback": [],
    }


def _common_prefix_len(a: str, b: str) -> int:
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return i


@pytest.mark.unit
def test_system_message_is_byte_identical_across_personas():
    state = _state()
    systems = {
        build_reviewer_messages(state, rt)[0]["content"] for rt in REVIEWER_TYPES
    }
    assert len(systems) == 1
    assert systems.pop() == SHARED_REVIEWER_PREAMBLE


@pytest.mark.unit
def test_shared_user_prefix_is_byte_identical_across_personas():
    state = _state()
    users = [build_reviewer_messages(state, rt)[1]["content"] for rt in REVIEWER_TYPES]
    shared = build_shared_reviewer_prefix(state)

    for user in users:
        assert shared in user
        assert user.index(shared) < 50, "shared prefix must sit at the head of the message"

    # Every pair actually shares that many leading bytes — the property the
    # prompt cache keys on. A regression here silently zeroes the hit rate.
    for i in range(len(users)):
        for j in range(i + 1, len(users)):
            assert _common_prefix_len(users[i], users[j]) >= len(shared)


@pytest.mark.unit
def test_manuscript_and_calibration_live_in_the_invariant_prefix():
    marker = "SENTINEL-MANUSCRIPT-BODY-TOKEN"
    state = _state(draft=f"## Methods\n{marker}\n")
    shared = build_shared_reviewer_prefix(state)

    assert marker in shared, "manuscript must be in the shared prefix, not per-persona"
    assert "RATING CALIBRATION" in SHARED_REVIEWER_PREAMBLE
    assert "GROUNDING RULE" in SHARED_REVIEWER_PREAMBLE


@pytest.mark.unit
def test_persona_block_appears_after_the_shared_prefix():
    state = _state()
    shared = build_shared_reviewer_prefix(state)
    for rt in REVIEWER_TYPES:
        user = build_reviewer_messages(state, rt)[1]["content"]
        persona = REVIEWER_PERSONAS[rt]
        assert persona in user
        assert user.index(persona) >= len(shared)
        # And the other two personas must not leak in.
        for other in REVIEWER_TYPES:
            if other != rt:
                assert REVIEWER_PERSONAS[other] not in user


@pytest.mark.unit
def test_no_persona_identity_leaks_into_the_prefix():
    state = _state()
    prefix = SHARED_REVIEWER_PREAMBLE + build_shared_reviewer_prefix(state)
    for token in ("Reviewer A", "Reviewer B", "Reviewer D", "literature_positioning"):
        assert token not in prefix


@pytest.mark.unit
def test_prefix_contains_no_timestamp_uuid_or_run_id():
    state = _state()
    prefix = SHARED_REVIEWER_PREAMBLE + build_shared_reviewer_prefix(state)

    forbidden = {
        "uuid": re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I),
        "iso_timestamp": re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"),
        "epoch_seconds": re.compile(r"\b1[6-9]\d{8}\b"),
    }
    for name, pattern in forbidden.items():
        assert not pattern.search(prefix), f"{name} found in cacheable prefix"

    # Ids that are handed to the node but must never be interpolated.
    for volatile in (state["draft_id"], state["project_id"], state["user_id"]):
        assert volatile not in prefix


@pytest.mark.unit
def test_prefix_is_stable_across_repeated_builds():
    state = _state()
    builds = {build_shared_reviewer_prefix(_state()) for _ in range(5)}
    assert len(builds) == 1
    assert builds.pop() == build_shared_reviewer_prefix(state)


# ---------------------------------------------------------------------------
# Compaction flag
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_compaction_defaults_off(monkeypatch):
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)
    assert reviewer_compaction_enabled() is False


@pytest.mark.unit
def test_compaction_off_preserves_full_manuscript(monkeypatch):
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)
    draft = "## Methods\n" + ("Detail sentence. " * 4000)
    assert _reviewer_manuscript_text(draft) == draft
    assert draft in build_shared_reviewer_prefix(_state(draft=draft))


@pytest.mark.unit
def test_compaction_on_bounds_a_large_manuscript(monkeypatch):
    monkeypatch.setenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", "1")
    assert reviewer_compaction_enabled() is True

    draft = "\n".join(
        f"## {title}\n" + ("Body sentence for this section. " * 400)
        for title in ("Introduction", "Methods", "Results", "Discussion", "Limitations")
    )
    compacted = _reviewer_manuscript_text(draft)
    assert len(compacted) < len(draft)
    # 1400 chars/section x max 7 sections, plus small headers.
    assert len(compacted) <= 7 * 1400 + 500


@pytest.mark.unit
def test_section_excerpts_handles_manuscript_with_no_sections():
    draft = "x" * 50000
    excerpt = _section_excerpts(draft)
    assert excerpt == "x" * 5000  # documented fallback


@pytest.mark.unit
def test_section_excerpts_handles_empty_input():
    assert _section_excerpts("") == ""
    assert _section_excerpts(None) == ""


@pytest.mark.unit
def test_reviewer_prompts_still_carry_persona_and_calibration():
    """`reviewer_judge` consumes REVIEWER_PROMPTS as a standalone system prompt."""
    for rt in REVIEWER_TYPES:
        assert REVIEWER_PERSONAS[rt] in REVIEWER_PROMPTS[rt]
        assert "RATING CALIBRATION" in REVIEWER_PROMPTS[rt]
