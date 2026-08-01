"""Parameter grid generation. Pure -- no database, no network."""

from __future__ import annotations

import pytest

from scripts.eval.ann_sweep.grid import (
    DEFAULT_EF_SEARCH_VALUES,
    INDEX_PREFIX,
    PRODUCTION_EF_CONSTRUCTION,
    PRODUCTION_EF_SEARCH,
    PRODUCTION_M,
    BuildConfig,
    EfSearchConfig,
    build_grid,
    ef_search_grid,
)


class TestEfSearchGrid:
    def test_default_grid_is_sorted_and_unique(self):
        grid = ef_search_grid()
        values = [c.ef_search for c in grid]
        assert values == sorted(values)
        assert len(values) == len(set(values))
        assert set(DEFAULT_EF_SEARCH_VALUES).issubset(values)

    def test_production_value_is_always_present(self):
        """A sweep that cannot locate the current operating point on its own
        curve cannot say whether that point is defensible."""
        grid = ef_search_grid([5, 7, 11])
        assert PRODUCTION_EF_SEARCH in [c.ef_search for c in grid]

    def test_exactly_one_config_is_flagged_production(self):
        flagged = [c for c in ef_search_grid() if c.is_production]
        assert len(flagged) == 1
        assert flagged[0].ef_search == PRODUCTION_EF_SEARCH
        assert "PRODUCTION" in flagged[0].label

    def test_custom_values_are_respected(self):
        grid = ef_search_grid([1, 2, 3])
        assert [c.ef_search for c in grid] == [1, 2, 3, PRODUCTION_EF_SEARCH]

    def test_duplicates_collapse(self):
        assert len(ef_search_grid([16, 16, 16])) == 2  # 16 and forced 80

    @pytest.mark.parametrize("bad", [0, -1, 2.5, "80", True])
    def test_rejects_non_positive_ints(self, bad):
        with pytest.raises(ValueError):
            ef_search_grid([bad])

    def test_to_dict_carries_the_production_flag(self):
        assert EfSearchConfig(80).to_dict() == {"ef_search": 80, "is_production_reference": True}
        assert EfSearchConfig(40).to_dict()["is_production_reference"] is False


class TestBuildGrid:
    def test_cartesian_product_ordered_by_m_then_ef_construction(self):
        grid = build_grid([8, 16], [32, 64], include_production=False)
        assert [(c.m, c.ef_construction) for c in grid] == [(8, 32), (8, 64), (16, 32), (16, 64)]

    def test_production_point_is_included_and_flagged(self):
        grid = build_grid([8], [32], include_production=True)
        prod = [c for c in grid if c.is_production]
        assert len(prod) == 1
        assert (prod[0].m, prod[0].ef_construction) == (PRODUCTION_M, PRODUCTION_EF_CONSTRUCTION)

    def test_production_not_duplicated_when_already_in_the_grid(self):
        grid = build_grid([16], [64], include_production=True)
        assert len(grid) == 1
        assert grid[0].is_production

    def test_invalid_points_are_skipped_by_default(self):
        """ef_construction < 2*m is not the configuration you asked for."""
        grid = build_grid([32], [32], include_production=False)
        assert grid == []

    def test_invalid_points_are_kept_when_skip_invalid_is_off(self):
        grid = build_grid([32], [32], include_production=False, skip_invalid=False)
        assert len(grid) == 1
        assert grid[0].buildable is False

    def test_default_grid_contains_production_and_only_valid_points(self):
        grid = build_grid()
        assert any(c.is_production for c in grid)
        assert all(c.buildable for c in grid)

    def test_index_names_are_unique_and_prefixed(self):
        names = [c.index_name for c in build_grid()]
        assert len(names) == len(set(names))
        assert all(n.startswith(INDEX_PREFIX) for n in names)

    def test_index_name_encodes_both_parameters(self):
        assert BuildConfig(32, 128).index_name == "ann_sweep_hnsw_m32_efc128"

    @pytest.mark.parametrize(
        "m,efc,ok",
        [(2, 4, True), (1, 64, False), (101, 512, False), (16, 3, False), (16, 64, True), (16, 1001, False)],
    )
    def test_buildable_matches_pgvector_bounds(self, m, efc, ok):
        assert BuildConfig(m, efc).buildable is ok

    def test_to_dict_shape(self):
        d = BuildConfig(8, 32).to_dict()
        assert d == {
            "m": 8,
            "ef_construction": 32,
            "is_production_reference": False,
            "index_name": "ann_sweep_hnsw_m8_efc32",
        }
