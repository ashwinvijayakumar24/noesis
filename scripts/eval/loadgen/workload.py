"""The unit of work: one draft-analysis graph run.

``GraphWorkload`` calls ``run_draft_analysis_workflow`` directly rather than
going through ``analyze_draft_with_langgraph``, because the latter is the
publish path -- it writes results to Supabase and is explicitly out of scope.
What is invoked is the graph and only the graph.

Inputs come from the state fixtures in ``scripts/eval/cache/state/*/`` which
carry real manuscripts (26k-141k chars), real ``parse_artifact`` and real
``parser_quality`` captured from production runs. Using them means the *input
size distribution* is real even when the LLM is stubbed, and it means parsing is
excluded by construction rather than by accident: the fixtures are already
parsed.

Three settings are forced and asserted, not assumed:

``stage_only=True``       every node's persistence path is gated on it
``checkpoint_enabled=False``  the one write that is NOT gated on stage_only
``fresh draft_id``        so nothing can collide with a real row
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import EVAL_DIR

__all__ = ["Fixture", "load_fixtures", "GraphWorkload", "SyntheticGraphWorkload"]

STATE_DIR = EVAL_DIR / "cache" / "state"


@dataclass(frozen=True)
class Fixture:
    paper_id: str
    draft_content: str
    paper_type: str
    citation_style: str
    parse_artifact: dict
    parser_quality: dict
    structure: dict

    @property
    def chars(self) -> int:
        return len(self.draft_content)


def load_fixtures(state_dir: Path | None = None, papers: list[str] | None = None) -> list[Fixture]:
    """Read ``extract_structure.json`` from each fixture directory.

    That file is the earliest captured state, so it holds the graph's *inputs*
    and none of its outputs -- replaying from it exercises all 18 nodes rather
    than resuming a partly-completed run.
    """
    root = Path(state_dir or STATE_DIR)
    out: list[Fixture] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        if papers and d.name not in papers:
            continue
        f = d / "extract_structure.json"
        if not f.is_file():
            continue
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not s.get("draft_content"):
            continue
        out.append(
            Fixture(
                paper_id=d.name,
                draft_content=s["draft_content"],
                paper_type=s.get("paper_type") or "journal_article",
                citation_style=s.get("citation_style") or "auto",
                parse_artifact=s.get("parse_artifact") or {},
                parser_quality=s.get("parser_quality") or {},
                structure=s.get("structure") or {},
            )
        )
    return out


class GraphWorkload:
    """One call == one full 18-node graph run.

    Fixtures are assigned round-robin by request index, so two runs of the same
    load model see the same manuscript in the same slot and a latency difference
    between them cannot be an input-size artefact.
    """

    def __init__(
        self,
        fixtures: list[Fixture],
        *,
        seed_structure: bool = True,
        project_id: str | None = None,
        user_id: str | None = None,
    ):
        if not fixtures:
            raise ValueError("GraphWorkload needs at least one fixture")
        self.fixtures = fixtures
        self.seed_structure = seed_structure
        # Deliberately synthetic ids. Every Supabase read keyed on them returns
        # empty (and under the write guard, returns empty regardless), so no
        # production row is read and none can be written.
        self.project_id = project_id or str(uuid.uuid4())
        self.user_id = user_id or str(uuid.uuid4())
        self.node_times: list[dict] = []

    def fixture_for(self, index: int) -> Fixture:
        return self.fixtures[index % len(self.fixtures)]

    async def __call__(self, index: int) -> dict:
        # Imported lazily: install_stubs() must have patched the client modules
        # before graph.py binds them at import time.
        from app.workflows.draft_analysis.graph import run_draft_analysis_workflow

        fx = self.fixture_for(index)
        draft_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        state = await run_draft_analysis_workflow(
            draft_id=draft_id,
            project_id=self.project_id,
            user_id=self.user_id,
            draft_content=fx.draft_content,
            checkpoint_enabled=False,   # the one write not gated on stage_only
            paper_type=fx.paper_type,
            citation_style=fx.citation_style,
            initial_structure=fx.structure if self.seed_structure else None,
            parse_artifact=fx.parse_artifact,
            parser_quality=fx.parser_quality,
        )
        elapsed = time.perf_counter() - t0

        # stage_only must have survived the whole run. A node that flipped it
        # would have re-enabled every persistence path in the graph.
        if state.get("stage_only") is not True:
            raise AssertionError(
                f"stage_only was {state.get('stage_only')!r} at graph exit -- "
                "persistence paths were live during a load run"
            )

        reviewers = state.get("reviewer_outputs") or []
        return {
            "paper_id": fx.paper_id,
            "chars": fx.chars,
            "graph_seconds": round(elapsed, 4),
            "reviewer_branches": len(reviewers),
            "desk_rejected": not (state.get("editor_decision") or {}).get(
                "proceed_to_review", True
            ),
        }


class SyntheticGraphWorkload:
    """A workload with a known service time. Used by the tests, never for results.

    The schedulers must be testable without importing the backend, and a claim
    like "open and closed loop diverge" is only checkable against a workload
    whose true service time is a constant the test chose.
    """

    def __init__(self, service_seconds: float, *, capacity: int | None = None):
        self.service_seconds = service_seconds
        self._sem = asyncio.Semaphore(capacity) if capacity else None
        self.max_concurrent = 0
        self._live = 0

    async def __call__(self, index: int) -> dict:
        if self._sem is not None:
            async with self._sem:
                return await self._serve()
        return await self._serve()

    async def _serve(self) -> dict:
        self._live += 1
        self.max_concurrent = max(self.max_concurrent, self._live)
        try:
            await asyncio.sleep(self.service_seconds)
        finally:
            self._live -= 1
        return {"graph_seconds": self.service_seconds}
