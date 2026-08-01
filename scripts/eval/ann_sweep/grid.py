"""Parameter grids for the HNSW sweep.

Two grids, because the two parameter families have completely different costs:

* ``ef_search`` is a QUERY-TIME knob. Changing it needs no rebuild, so sweeping
  it densely is nearly free and it is the knob that should actually be tuned.
* ``m`` and ``ef_construction`` are BUILD-TIME knobs. Every point costs an index
  build and disk. The grid is therefore deliberately small and always includes
  production's point so the rest of the grid has a reference.

pgvector's accepted ranges (pgvector 0.8, `hnswvalidate`/reloption bounds):
m in [2, 100], ef_construction in [4, 1000] and >= 2*m. Values outside those
ranges are still legal *inputs* here -- the sweep records the build failure
rather than refusing to try, because "this configuration cannot be built" is a
result worth having on disk.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

#: pgvector's own defaults, which production inherited by not specifying WITH (...).
PRODUCTION_M = 16
PRODUCTION_EF_CONSTRUCTION = 64

#: The value hard-coded inside match_document_chunks / match_single_document_chunks
#: (migration 036, `SET LOCAL hnsw.ef_search = 80`).
PRODUCTION_EF_SEARCH = 80

#: pgvector's session default, which every OTHER vector RPC runs at.
PGVECTOR_DEFAULT_EF_SEARCH = 40

#: Doubling ladder around production. Spans "obviously too small" (10) through
#: "obviously past the point of diminishing returns" (640) so the curve has
#: visible flat regions on both sides rather than only the interesting middle.
DEFAULT_EF_SEARCH_VALUES: tuple[int, ...] = (10, 20, 40, 80, 160, 320, 640)

#: Build grid. Small on purpose -- each point is an index build.
DEFAULT_M_VALUES: tuple[int, ...] = (8, 16, 32)
DEFAULT_EF_CONSTRUCTION_VALUES: tuple[int, ...] = (32, 64, 128, 256)


@dataclass(frozen=True)
class EfSearchConfig:
    """One query-time point. No rebuild required."""

    ef_search: int

    @property
    def is_production(self) -> bool:
        return self.ef_search == PRODUCTION_EF_SEARCH

    @property
    def label(self) -> str:
        suffix = "  (PRODUCTION)" if self.is_production else ""
        return f"ef_search={self.ef_search}{suffix}"

    def to_dict(self) -> dict:
        return {"ef_search": self.ef_search, "is_production_reference": self.is_production}


@dataclass(frozen=True)
class BuildConfig:
    """One build-time point: an alternative HNSW index over the same column."""

    m: int
    ef_construction: int

    @property
    def is_production(self) -> bool:
        return self.m == PRODUCTION_M and self.ef_construction == PRODUCTION_EF_CONSTRUCTION

    @property
    def index_name(self) -> str:
        """Distinct name per point, prefixed so cleanup can find strays."""
        return f"ann_sweep_hnsw_m{self.m}_efc{self.ef_construction}"

    @property
    def label(self) -> str:
        suffix = "  (PRODUCTION)" if self.is_production else ""
        return f"m={self.m}, ef_construction={self.ef_construction}{suffix}"

    @property
    def buildable(self) -> bool:
        """Whether pgvector will accept these reloptions.

        Advisory only. The sweep still ATTEMPTS unbuildable points so the
        failure is recorded from the database rather than predicted here.
        """
        return 2 <= self.m <= 100 and 4 <= self.ef_construction <= 1000 and self.ef_construction >= 2 * self.m

    def to_dict(self) -> dict:
        out = asdict(self)
        out["is_production_reference"] = self.is_production
        out["index_name"] = self.index_name
        return out


#: Prefix every index this package creates. Cleanup and stray detection key off it.
INDEX_PREFIX = "ann_sweep_hnsw_"


def ef_search_grid(values: tuple[int, ...] | list[int] | None = None) -> list[EfSearchConfig]:
    """Deduplicated, ascending ef_search grid, always including production's 80.

    Production's value is forced in even if the caller omitted it: a sweep that
    cannot locate the current operating point on its own curve cannot say
    whether that point is defensible, which is the entire question.
    """
    raw = list(values if values is not None else DEFAULT_EF_SEARCH_VALUES)
    for v in raw:
        # Validated BEFORE the set/sort: mixing a str in would blow up sorted()
        # with a TypeError that says nothing about which value was wrong.
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise ValueError(f"ef_search values must be positive ints, got {v!r}")
    vals = set(raw)
    vals.add(PRODUCTION_EF_SEARCH)
    return [EfSearchConfig(ef_search=v) for v in sorted(vals)]


def build_grid(
    m_values: tuple[int, ...] | list[int] | None = None,
    ef_construction_values: tuple[int, ...] | list[int] | None = None,
    include_production: bool = True,
    skip_invalid: bool = True,
) -> list[BuildConfig]:
    """Cartesian m x ef_construction grid, ordered (m, ef_construction) ascending.

    ``skip_invalid`` drops points pgvector would reject outright (notably
    ef_construction < 2*m, which it silently clamps in some versions and errors
    on in others -- either way the point is not the configuration you asked for,
    so measuring it would mislabel the result).
    """
    ms = list(m_values if m_values is not None else DEFAULT_M_VALUES)
    efcs = list(ef_construction_values if ef_construction_values is not None else DEFAULT_EF_CONSTRUCTION_VALUES)

    seen: set[tuple[int, int]] = set()
    out: list[BuildConfig] = []
    for m in ms:
        for efc in efcs:
            cfg = BuildConfig(m=m, ef_construction=efc)
            if skip_invalid and not cfg.buildable:
                continue
            if (cfg.m, cfg.ef_construction) in seen:
                continue
            seen.add((cfg.m, cfg.ef_construction))
            out.append(cfg)

    if include_production:
        prod = BuildConfig(PRODUCTION_M, PRODUCTION_EF_CONSTRUCTION)
        if (prod.m, prod.ef_construction) not in seen:
            out.append(prod)

    return sorted(out, key=lambda c: (c.m, c.ef_construction))
