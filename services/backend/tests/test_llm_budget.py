"""Unit tests for LLM spend guardrails (app/core/llm_budget.py)."""

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

from app.core import llm_budget
from app.core.llm_budget import (
    LLMBudgetExceeded,
    LLMCallBlocked,
    ModelPrice,
    check_llm_allowed,
    current_label,
    env_truthy,
    estimate_usd,
    llm_label,
    record_usage,
)

GUARD_ENV_VARS = (
    "NOESIS_LLM_KILL_SWITCH",
    "EVAL_REPLAY_ONLY",
    "NOESIS_LLM_MAX_SPEND_USD",
    "NOESIS_LLM_MAX_CALLS",
    "NOESIS_LLM_USAGE_LOG",
)


@pytest.fixture(autouse=True)
def clean_budget(monkeypatch):
    """Isolate every test: empty accumulator, no guard env vars set."""
    for name in GUARD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    llm_budget.reset()
    yield
    llm_budget.reset()


@pytest.fixture
def priced_model(monkeypatch):
    """Register a deterministic price so accounting can be asserted exactly."""
    monkeypatch.setitem(
        llm_budget.MODEL_PRICING_USD_PER_1M,
        "test-priced",
        ModelPrice(input_per_1m=1.0, output_per_1m=2.0, cached_input_per_1m=0.5),
    )
    return "test-priced"


# ---------------------------------------------------------------------------
# Accumulation / grouping
# ---------------------------------------------------------------------------

class TestAccumulation:
    def test_record_usage_accumulates_across_calls(self, priced_model):
        record_usage(model=priced_model, prompt_tokens=1000, completion_tokens=500, label="a")
        record_usage(model=priced_model, prompt_tokens=2000, completion_tokens=100, label="a")

        totals = llm_budget.totals()
        assert totals["calls"] == 2
        assert totals["prompt_tokens"] == 3000
        assert totals["completion_tokens"] == 600
        assert totals["total_tokens"] == 3600
        assert totals["unpriced_calls"] == 0
        # (3000 * 1.0 + 600 * 2.0) / 1e6
        assert totals["estimated_usd"] == pytest.approx(0.0042)

    def test_cached_tokens_billed_at_cached_rate(self, priced_model):
        record_usage(
            model=priced_model,
            prompt_tokens=1000,
            completion_tokens=0,
            cached_tokens=800,
            label="cached",
        )
        # 200 uncached @1.0 + 800 cached @0.5
        assert llm_budget.totals()["estimated_usd"] == pytest.approx(0.0006)
        assert llm_budget.totals()["cached_tokens"] == 800

    def test_by_model_groups_correctly(self, priced_model):
        record_usage(model=priced_model, prompt_tokens=100, completion_tokens=10, label="x")
        record_usage(model=priced_model, prompt_tokens=100, completion_tokens=10, label="y")
        record_usage(model="other-model", prompt_tokens=50, completion_tokens=5, label="x")

        grouped = llm_budget.by_model()
        assert set(grouped) == {priced_model, "other-model"}
        assert grouped[priced_model]["calls"] == 2
        assert grouped[priced_model]["prompt_tokens"] == 200
        assert grouped["other-model"]["calls"] == 1

    def test_by_label_groups_correctly(self, priced_model):
        record_usage(model=priced_model, prompt_tokens=100, completion_tokens=10, label="reviewer_panel")
        record_usage(model=priced_model, prompt_tokens=300, completion_tokens=20, label="reviewer_panel")
        record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1, label="editor_pass")

        grouped = llm_budget.by_label()
        assert grouped["reviewer_panel"]["calls"] == 2
        assert grouped["reviewer_panel"]["prompt_tokens"] == 400
        assert grouped["editor_pass"]["calls"] == 1

    def test_reset_clears_everything(self, priced_model):
        record_usage(model=priced_model, prompt_tokens=100, completion_tokens=10, label="x")
        record_usage(model="unknown-price-model", prompt_tokens=100, completion_tokens=10, label="x")
        llm_budget.reset()

        totals = llm_budget.totals()
        assert totals["calls"] == 0
        assert totals["unpriced_calls"] == 0
        assert llm_budget.total_spend_usd() == 0.0
        assert llm_budget.unpriced_calls() == 0

    def test_event_records_timestamp_and_fields(self, priced_model):
        event = record_usage(
            model=priced_model, prompt_tokens=10, completion_tokens=2, label="node"
        )
        assert event.model == priced_model
        assert event.label == "node"
        assert event.timestamp > 0
        assert event.estimated_usd is not None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_recording_is_exact(self, priced_model):
        threads_count = 20
        per_thread = 50
        barrier = threading.Barrier(threads_count)

        def worker():
            barrier.wait()
            for _ in range(per_thread):
                record_usage(
                    model=priced_model,
                    prompt_tokens=10,
                    completion_tokens=1,
                    label="concurrent",
                )

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        expected_calls = threads_count * per_thread
        totals = llm_budget.totals()
        assert totals["calls"] == expected_calls
        assert totals["prompt_tokens"] == expected_calls * 10
        assert totals["completion_tokens"] == expected_calls * 1
        assert llm_budget.total_spend_usd() == pytest.approx(
            expected_calls * (10 * 1.0 + 1 * 2.0) / 1_000_000
        )

    def test_concurrent_unpriced_counter_is_exact(self):
        threads_count = 20
        per_thread = 25
        barrier = threading.Barrier(threads_count)

        def worker():
            barrier.wait()
            for _ in range(per_thread):
                record_usage(model="model-with-no-price", prompt_tokens=5, label="x")

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert llm_budget.unpriced_calls() == threads_count * per_thread
        assert llm_budget.totals()["unpriced_calls"] == threads_count * per_thread


# ---------------------------------------------------------------------------
# Ambient node label (contextvar)
# ---------------------------------------------------------------------------

class TestLabelContextManager:
    def test_sets_and_restores(self, priced_model):
        assert current_label() is None
        with llm_label("reviewer_panel:methodology"):
            assert current_label() == "reviewer_panel:methodology"
            record_usage(model=priced_model, prompt_tokens=10, completion_tokens=1)
        assert current_label() is None

        assert llm_budget.by_label()["reviewer_panel:methodology"]["calls"] == 1

    def test_restores_on_exception(self):
        with pytest.raises(ValueError):
            with llm_label("outer"):
                raise ValueError("boom")
        assert current_label() is None

    def test_nesting_inner_wins_outer_restored(self, priced_model):
        with llm_label("a"):
            record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1)
            with llm_label("b"):
                assert current_label() == "b"
                record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1)
            assert current_label() == "a"
            record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1)

        grouped = llm_budget.by_label()
        assert grouped["a"]["calls"] == 2
        assert grouped["b"]["calls"] == 1

    def test_nesting_survives_inner_exception(self):
        with llm_label("a"):
            with pytest.raises(RuntimeError):
                with llm_label("b"):
                    raise RuntimeError("boom")
            assert current_label() == "a"
        assert current_label() is None


class TestLabelPriority:
    def test_explicit_label_beats_contextvar(self, priced_model):
        with llm_label("ambient"):
            record_usage(
                model=priced_model, prompt_tokens=1, completion_tokens=1, label="explicit"
            )
        assert set(llm_budget.by_label()) == {"explicit"}

    def test_contextvar_beats_model_name(self, priced_model):
        with llm_label("ambient"):
            record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1)
        assert set(llm_budget.by_label()) == {"ambient"}

    def test_model_name_used_when_nothing_else(self, priced_model):
        record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1)
        assert set(llm_budget.by_label()) == {priced_model}

    def test_explicit_label_matching_model_name_is_still_explicit(self, priced_model):
        """retry_utils passes label=None when no caller supplied one, so absence is
        genuinely distinguishable and no model-name heuristic is needed. A caller
        that deliberately labels a call with the model name means it."""
        with llm_label("reviewer_panel"):
            record_usage(
                model=priced_model, prompt_tokens=1, completion_tokens=1, label=priced_model
            )
        assert set(llm_budget.by_label()) == {priced_model}

    def test_none_label_lets_ambient_win(self, priced_model):
        """The path that matters: retry_utils forwards usage_label unchanged, so a
        node wrapped in llm_label() attributes correctly without editing call sites."""
        with llm_label("reviewer_panel"):
            record_usage(
                model=priced_model, prompt_tokens=1, completion_tokens=1, label=None
            )
        assert set(llm_budget.by_label()) == {"reviewer_panel"}

    def test_placeholder_label_is_treated_as_absent(self, priced_model):
        with llm_label("editor_pass"):
            record_usage(
                model=priced_model, prompt_tokens=1, completion_tokens=1, label="unknown"
            )
        assert set(llm_budget.by_label()) == {"editor_pass"}

    def test_placeholder_label_without_ambient_falls_back_to_model(self, priced_model):
        """A placeholder means "no label", so with nothing ambient the model name is
        the honest answer — better than bucketing real spend under "unknown"."""
        record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1, label="unknown")
        assert set(llm_budget.by_label()) == {priced_model}

    def test_record_response_usage_honours_contextvar(self, priced_model):
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10)
        )
        with llm_label("diagnostic_findings"):
            llm_budget.record_response_usage(response, model=priced_model)
        assert llm_budget.by_label()["diagnostic_findings"]["prompt_tokens"] == 100

    def test_retry_utils_call_site_picks_up_ambient_label(self, monkeypatch):
        """End-to-end through an unmodified call site."""
        from app.services.retry_utils import parse_chat_completion_with_retries_sync

        client = _RecordingClient()
        with llm_label("reviewer_panel:novelty"):
            parse_chat_completion_with_retries_sync(
                client,
                model="gpt-5.2-chat-latest",
                messages=[{"role": "user", "content": "hi"}],
                response_format=object,
            )

        by_label = llm_budget.by_label()
        assert by_label["reviewer_panel:novelty"]["calls"] == 1
        assert "gpt-5.2-chat-latest" not in by_label
        # model attribution is unaffected
        assert llm_budget.by_model()["gpt-5.2-chat-latest"]["calls"] == 1


class TestLabelThreadPropagation:
    """THE regression test for `run_coroutine_sync`.

    That helper starts a bare `threading.Thread` running `asyncio.run(...)`.
    ContextVars do not cross a plain Thread boundary, so without the explicit
    `contextvars.copy_context()` snapshot the ambient label is silently dropped
    exactly on the hottest path -- every node's tokens would land under the
    model name instead of the node. Deleting the `ctx.run(...)` in
    app/services/async_utils.py must make this test fail.
    """

    def test_label_survives_run_coroutine_sync(self, priced_model):
        from app.services.async_utils import run_coroutine_sync

        async def do_call():
            record_usage(model=priced_model, prompt_tokens=10, completion_tokens=1)
            return current_label()

        with llm_label("reviewer_panel:methodology"):
            seen = run_coroutine_sync(do_call())

        assert seen == "reviewer_panel:methodology"
        assert set(llm_budget.by_label()) == {"reviewer_panel:methodology"}

    def test_label_reaches_nested_tasks_inside_the_worker_thread(self, priced_model):
        from app.services.async_utils import run_coroutine_sync

        async def leaf(i: int):
            record_usage(model=priced_model, prompt_tokens=i, completion_tokens=0)

        async def fan_out():
            await asyncio.gather(*(leaf(i) for i in range(1, 4)))

        with llm_label("editor_pass"):
            run_coroutine_sync(fan_out())

        assert llm_budget.by_label()["editor_pass"]["calls"] == 3
        assert llm_budget.by_label()["editor_pass"]["prompt_tokens"] == 6

    def test_no_label_still_falls_back_to_model_name(self, priced_model):
        from app.services.async_utils import run_coroutine_sync

        async def do_call():
            record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1)

        run_coroutine_sync(do_call())
        assert set(llm_budget.by_label()) == {priced_model}

    def test_worker_thread_label_does_not_leak_back_to_caller(self, priced_model):
        from app.services.async_utils import run_coroutine_sync

        async def do_call():
            with llm_label("inner_only"):
                record_usage(model=priced_model, prompt_tokens=1, completion_tokens=1)

        with llm_label("outer"):
            run_coroutine_sync(do_call())
            assert current_label() == "outer"

        assert set(llm_budget.by_label()) == {"inner_only"}

    def test_plain_thread_without_propagation_loses_the_label(self, priced_model):
        """Pins WHY the fix is needed: a naive Thread drops the contextvar."""
        seen = {}

        def worker():
            seen["label"] = current_label()

        with llm_label("ambient"):
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

        assert seen["label"] is None

    def test_exceptions_still_propagate_through_the_context(self, priced_model):
        from app.services.async_utils import run_coroutine_sync

        async def boom():
            raise ValueError("kaboom")

        with llm_label("node"):
            with pytest.raises(ValueError, match="kaboom"):
                run_coroutine_sync(boom())
        assert current_label() is None


class TestLabelAsyncConcurrency:
    def test_concurrent_tasks_do_not_bleed(self, priced_model):
        async def task(name: str, prompt_tokens: int):
            with llm_label(name):
                # Force interleaving: both tasks are inside their block at once.
                await asyncio.sleep(0)
                assert current_label() == name
                record_usage(
                    model=priced_model, prompt_tokens=prompt_tokens, completion_tokens=0
                )
                await asyncio.sleep(0)
                assert current_label() == name
                record_usage(
                    model=priced_model, prompt_tokens=prompt_tokens, completion_tokens=0
                )

        async def main():
            await asyncio.gather(task("node_a", 10), task("node_b", 100))
            assert current_label() is None

        asyncio.run(main())

        grouped = llm_budget.by_label()
        assert grouped["node_a"]["calls"] == 2
        assert grouped["node_a"]["prompt_tokens"] == 20
        assert grouped["node_b"]["calls"] == 2
        assert grouped["node_b"]["prompt_tokens"] == 200

    def test_many_concurrent_tasks_are_exact(self, priced_model):
        async def task(i: int):
            with llm_label(f"node_{i}"):
                await asyncio.sleep(0)
                record_usage(model=priced_model, prompt_tokens=1, completion_tokens=0)

        async def main():
            await asyncio.gather(*(task(i) for i in range(50)))

        asyncio.run(main())

        grouped = llm_budget.by_label()
        assert len(grouped) == 50
        assert all(bucket["calls"] == 1 for bucket in grouped.values())

    def test_concurrent_threads_do_not_bleed(self, priced_model):
        barrier = threading.Barrier(10)

        def worker(i: int):
            with llm_label(f"thread_{i}"):
                barrier.wait()
                record_usage(model=priced_model, prompt_tokens=1, completion_tokens=0)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        grouped = llm_budget.by_label()
        assert set(grouped) == {f"thread_{i}" for i in range(10)}


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_kill_switch_blocks(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
        with pytest.raises(LLMCallBlocked) as exc:
            check_llm_allowed("some_node")
        assert "NOESIS_LLM_KILL_SWITCH" in str(exc.value)
        assert "some_node" in str(exc.value)

    def test_unset_kill_switch_allows(self):
        check_llm_allowed("some_node")  # must not raise

    def test_falsy_kill_switch_allows(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "0")
        check_llm_allowed("some_node")


class TestReplayOnly:
    def test_replay_only_blocks_with_distinct_message(self, monkeypatch):
        monkeypatch.setenv("EVAL_REPLAY_ONLY", "true")
        with pytest.raises(LLMCallBlocked) as exc:
            check_llm_allowed("eval_node")
        message = str(exc.value)
        assert "EVAL_REPLAY_ONLY" in message
        assert "NOESIS_LLM_KILL_SWITCH" not in message

    def test_kill_switch_takes_precedence_but_messages_differ(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "yes")
        monkeypatch.setenv("EVAL_REPLAY_ONLY", "yes")
        with pytest.raises(LLMCallBlocked) as exc:
            check_llm_allowed("n")
        assert "NOESIS_LLM_KILL_SWITCH" in str(exc.value)


class TestCallCeiling:
    """The pricing-independent ceiling.

    The shipped table is now populated, so the dollar ceiling fires for the five
    models in use. These tests deliberately use an UNPRICED model, because that
    is the condition the call ceiling exists for: a model missing from the table
    or renamed upstream contributes 0 to spend and slips past
    NOESIS_LLM_MAX_SPEND_USD entirely. The call ceiling still stops it.
    """

    def test_under_ceiling_passes(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "3")
        record_usage(model="unpriced-model", prompt_tokens=100, completion_tokens=10, label="x")
        check_llm_allowed("x")  # 1 < 3

    def test_reaching_ceiling_raises(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "2")
        for _ in range(2):
            record_usage(model="unpriced-model", prompt_tokens=100, completion_tokens=10, label="x")
        with pytest.raises(LLMBudgetExceeded) as exc:
            check_llm_allowed("x")
        assert "NOESIS_LLM_MAX_CALLS" in str(exc.value)

    def test_fires_even_when_spend_ceiling_is_inert(self, monkeypatch):
        """The regression this ceiling exists for: unpriced calls, generous dollar
        ceiling, yet the run must still be stoppable."""
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "1000.0")
        monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "1")
        record_usage(model="unpriced-model", prompt_tokens=999_999, completion_tokens=0, label="x")
        assert llm_budget.total_spend_usd() == 0.0  # dollar ceiling cannot fire
        assert llm_budget.unpriced_calls() == 1
        with pytest.raises(LLMBudgetExceeded):
            check_llm_allowed("x")

    def test_no_ceiling_when_unset(self):
        for _ in range(50):
            record_usage(model="unpriced-model", prompt_tokens=100, completion_tokens=0, label="x")
        check_llm_allowed("x")  # must not raise

    def test_malformed_ceiling_is_ignored(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "not-an-int")
        for _ in range(5):
            record_usage(model="unpriced-model", prompt_tokens=100, completion_tokens=0, label="x")
        check_llm_allowed("x")  # must not raise

    def test_zero_ceiling_blocks_immediately(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "0")
        with pytest.raises(LLMBudgetExceeded):
            check_llm_allowed("x")


class TestSpendCeiling:
    def test_under_ceiling_passes(self, monkeypatch, priced_model):
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "1.0")
        record_usage(model=priced_model, prompt_tokens=1000, completion_tokens=0, label="x")
        check_llm_allowed("x")  # $0.001 < $1.00

    def test_crossing_ceiling_raises(self, monkeypatch, priced_model):
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "0.001")
        record_usage(model=priced_model, prompt_tokens=2000, completion_tokens=0, label="x")
        with pytest.raises(LLMBudgetExceeded) as exc:
            check_llm_allowed("x")
        assert "NOESIS_LLM_MAX_SPEND_USD" in str(exc.value)

    def test_no_ceiling_when_unset(self, priced_model):
        record_usage(model=priced_model, prompt_tokens=10_000_000, completion_tokens=0, label="x")
        check_llm_allowed("x")  # must not raise

    def test_malformed_ceiling_is_ignored(self, monkeypatch, priced_model):
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "not-a-number")
        record_usage(model=priced_model, prompt_tokens=10_000_000, completion_tokens=0, label="x")
        check_llm_allowed("x")


class TestUnknownPricing:
    def test_estimate_is_none_for_unknown_model(self):
        assert estimate_usd("totally-unknown-model", 1000, 1000) is None

    def test_estimate_is_none_when_price_entry_has_none_rates(self, monkeypatch):
        # An entry whose rates are still unverified must estimate to None rather
        # than to $0. (This previously asserted against "gpt-5.2" while the
        # shipped table was all-None; gpt-5.2 now has a verified price, so the
        # invariant is pinned with a synthetic entry instead.)
        monkeypatch.setitem(
            llm_budget.MODEL_PRICING_USD_PER_1M,
            "unverified-model",
            ModelPrice(None, None, None),
        )
        assert estimate_usd("unverified-model", 1000, 1000) is None

    def test_estimate_is_none_when_cached_rate_unknown(self, monkeypatch):
        monkeypatch.setitem(
            llm_budget.MODEL_PRICING_USD_PER_1M,
            "partial-price",
            ModelPrice(input_per_1m=1.0, output_per_1m=2.0, cached_input_per_1m=None),
        )
        assert estimate_usd("partial-price", 1000, 100, 0) is not None
        assert estimate_usd("partial-price", 1000, 100, 500) is None

    def test_unpriced_call_increments_counter_and_contributes_zero(self):
        event = record_usage(model="unknown-model", prompt_tokens=999, completion_tokens=999, label="x")
        assert event.estimated_usd is None

        totals = llm_budget.totals()
        assert totals["unpriced_calls"] == 1
        assert totals["estimated_usd"] == 0.0
        assert totals["prompt_tokens"] == 999  # tokens are still visible

    def test_unpriced_calls_do_not_silently_bypass_ceiling_accounting(self, monkeypatch, priced_model):
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "1.0")
        record_usage(model="unknown-model", prompt_tokens=10_000_000, completion_tokens=0, label="x")
        # Unpriced spend cannot be charged against the ceiling...
        check_llm_allowed("x")
        # ...but the gap is explicitly visible, not silent.
        assert llm_budget.totals()["unpriced_calls"] == 1

        record_usage(model=priced_model, prompt_tokens=2_000_000, completion_tokens=0, label="x")
        with pytest.raises(LLMBudgetExceeded) as exc:
            check_llm_allowed("x")
        assert "unknown pricing" in str(exc.value)

    def test_get_price_prefix_match(self, monkeypatch):
        monkeypatch.setitem(
            llm_budget.MODEL_PRICING_USD_PER_1M,
            "test-priced",
            ModelPrice(1.0, 2.0, 0.5),
        )
        assert llm_budget.get_price("test-priced-2026-01-01") == ModelPrice(1.0, 2.0, 0.5)
        assert llm_budget.get_price(None) is None


# ---------------------------------------------------------------------------
# The real, shipped pricing table
# ---------------------------------------------------------------------------

class TestShippedPricingTable:
    """Pins the verified rates in MODEL_PRICING_USD_PER_1M.

    Every expected dollar figure below is computed by hand from the published
    per-1M rate, so a silent edit to the table fails here rather than showing up
    as a quietly wrong cost report. Rates retrieved 2026-07-30 from
    developers.openai.com/api/docs/pricing and each model's own docs page.
    """

    def test_no_entry_is_half_priced(self):
        """All-None (honestly unknown) or a real input price. Never in between.

        A half-filled entry would let estimate_usd emit a partial figure that
        looks authoritative -- the exact failure this table exists to avoid.
        """
        for model, price in llm_budget.MODEL_PRICING_USD_PER_1M.items():
            fields = (price.input_per_1m, price.output_per_1m, price.cached_input_per_1m)
            if all(field is None for field in fields):
                continue
            assert price.input_per_1m is not None, f"{model}: priced entry with no input rate"
            assert price.output_per_1m is not None, f"{model}: priced entry with no output rate"
            assert price.input_per_1m >= 0
            assert price.output_per_1m >= 0
            if price.cached_input_per_1m is not None:
                assert 0 <= price.cached_input_per_1m <= price.input_per_1m

    def test_gpt_5_2_exact_cost(self):
        # 200_000 in @ $1.75/1M = $0.35 ; 10_000 out @ $14.00/1M = $0.14
        assert estimate_usd("gpt-5.2", 200_000, 10_000) == pytest.approx(0.49)

    def test_gpt_5_2_cached_input_exact_cost(self):
        # 20_000 uncached @ $1.75/1M = $0.035 ; 80_000 cached @ $0.175/1M = $0.014
        assert estimate_usd("gpt-5.2", 100_000, 0, 80_000) == pytest.approx(0.049)

    def test_gpt_5_2_chat_latest_exact_cost(self):
        # same published rates as gpt-5.2
        assert estimate_usd("gpt-5.2-chat-latest", 1_000_000, 1_000_000) == pytest.approx(15.75)

    def test_gpt_5_mini_exact_cost(self):
        # 1M in @ $0.25/1M = $0.25 ; 500_000 out @ $2.00/1M = $1.00
        assert estimate_usd("gpt-5-mini", 1_000_000, 500_000) == pytest.approx(1.25)

    def test_gpt_5_mini_cached_exact_cost(self):
        # 400_000 uncached @ $0.25/1M = $0.10 ; 600_000 cached @ $0.025/1M = $0.015
        assert estimate_usd("gpt-5-mini", 1_000_000, 0, 600_000) == pytest.approx(0.115)

    def test_embedding_large_is_priced_not_unpriced(self):
        """Embeddings emit no completion tokens, so a $0 output rate is a real
        verified rate, not an unknown. Without it every embedding call would be
        miscounted as unpriced and its cost would vanish from the total."""
        assert estimate_usd("text-embedding-3-large", 1_000_000, 0) == pytest.approx(0.13)

    def test_embedding_small_is_priced_not_unpriced(self):
        assert estimate_usd("text-embedding-3-small", 1_000_000, 0) == pytest.approx(0.02)

    def test_embedding_call_contributes_to_recorded_spend(self):
        record_usage(model="text-embedding-3-small", prompt_tokens=500_000, label="rag_ingest")
        totals = llm_budget.totals()
        assert totals["unpriced_calls"] == 0
        assert totals["estimated_usd"] == pytest.approx(0.01)

    def test_embedding_with_cached_tokens_is_unpriced_not_guessed(self):
        """No cached rate is published for embeddings, so if one were ever
        reported the honest answer is None rather than an invented discount."""
        assert estimate_usd("text-embedding-3-small", 1000, 0, 500) is None

    def test_model_not_in_table_is_unpriced(self):
        assert estimate_usd("gpt-4o", 1000, 1000) is None
        event = record_usage(model="gpt-4o", prompt_tokens=1000, completion_tokens=1000, label="x")
        assert event.estimated_usd is None
        assert llm_budget.unpriced_calls() == 1
        assert llm_budget.total_spend_usd() == 0.0

    def test_dated_snapshot_resolves_to_base_entry(self):
        table = llm_budget.MODEL_PRICING_USD_PER_1M
        assert llm_budget.get_price("gpt-5.2-2026-11-04") is table["gpt-5.2"]
        assert llm_budget.get_price("gpt-5-mini-2026-08-01") is table["gpt-5-mini"]
        assert estimate_usd("gpt-5.2-2026-11-04", 200_000, 10_000) == pytest.approx(0.49)

    def test_longest_prefix_wins_over_shorter_one(self):
        """"gpt-5.2-chat-latest-..." starts with BOTH "gpt-5.2" and
        "gpt-5.2-chat-latest"; the more specific entry must win."""
        table = llm_budget.MODEL_PRICING_USD_PER_1M
        resolved = llm_budget.get_price("gpt-5.2-chat-latest-2026-11-04")
        assert resolved is table["gpt-5.2-chat-latest"]
        assert resolved is not table["gpt-5.2"]


class TestSpendCeilingWithRealPrices:
    """The capability that did not exist while the table was all-None.

    NOESIS_LLM_MAX_SPEND_USD was inert: every call was unpriced, spend stayed at
    $0, and the dollar ceiling could never fire. With verified prices it does.
    """

    def test_dollar_ceiling_now_fires_on_a_real_model(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "0.10")
        # 100_000 in @ $1.75/1M = $0.175 -> over a $0.10 ceiling
        record_usage(model="gpt-5.2", prompt_tokens=100_000, completion_tokens=0, label="node")
        assert llm_budget.total_spend_usd() == pytest.approx(0.175)
        assert llm_budget.unpriced_calls() == 0

        with pytest.raises(LLMBudgetExceeded) as exc:
            check_llm_allowed("node")
        assert "NOESIS_LLM_MAX_SPEND_USD" in str(exc.value)

    def test_under_ceiling_still_allowed_on_a_real_model(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "1.00")
        record_usage(model="gpt-5.2", prompt_tokens=100_000, completion_tokens=0, label="node")
        check_llm_allowed("node")  # $0.175 < $1.00

    def test_ceiling_accumulates_across_mixed_real_models(self, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "0.30")
        record_usage(model="gpt-5-mini", prompt_tokens=1_000_000, label="a")          # $0.25
        record_usage(model="text-embedding-3-large", prompt_tokens=1_000_000, label="b")  # $0.13
        assert llm_budget.total_spend_usd() == pytest.approx(0.38)
        with pytest.raises(LLMBudgetExceeded):
            check_llm_allowed("c")


# ---------------------------------------------------------------------------
# JSONL sink
# ---------------------------------------------------------------------------

class TestJsonlSink:
    def test_writes_one_json_object_per_line(self, monkeypatch, tmp_path, priced_model):
        path = tmp_path / "usage.jsonl"
        monkeypatch.setenv("NOESIS_LLM_USAGE_LOG", str(path))

        record_usage(model=priced_model, prompt_tokens=10, completion_tokens=1, label="a")
        record_usage(model=priced_model, prompt_tokens=20, completion_tokens=2, label="b")

        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        rows = [json.loads(line) for line in lines]
        assert rows[0]["label"] == "a"
        assert rows[1]["prompt_tokens"] == 20
        assert set(rows[0]) >= {
            "model", "label", "prompt_tokens", "completion_tokens",
            "cached_tokens", "estimated_usd", "timestamp",
        }

    def test_appends_rather_than_truncates(self, monkeypatch, tmp_path, priced_model):
        path = tmp_path / "usage.jsonl"
        path.write_text('{"pre": "existing"}\n', encoding="utf-8")
        monkeypatch.setenv("NOESIS_LLM_USAGE_LOG", str(path))

        record_usage(model=priced_model, prompt_tokens=10, completion_tokens=1, label="a")

        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"pre": "existing"}

    def test_unwritable_path_does_not_raise(self, monkeypatch, tmp_path, priced_model):
        monkeypatch.setenv(
            "NOESIS_LLM_USAGE_LOG", str(tmp_path / "no" / "such" / "dir" / "usage.jsonl")
        )
        record_usage(model=priced_model, prompt_tokens=10, completion_tokens=1, label="a")
        # accounting still happened
        assert llm_budget.totals()["calls"] == 1

    def test_no_file_written_when_env_unset(self, tmp_path, priced_model):
        record_usage(model=priced_model, prompt_tokens=10, completion_tokens=1, label="a")
        assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Env parsing
# ---------------------------------------------------------------------------

class TestEnvParsing:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "True", "yes", "YES", "on", " on "])
    def test_truthy(self, monkeypatch, value):
        monkeypatch.setenv("NOESIS_TEST_FLAG", value)
        assert env_truthy("NOESIS_TEST_FLAG") is True

    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", "", "  ", "maybe"])
    def test_falsy(self, monkeypatch, value):
        monkeypatch.setenv("NOESIS_TEST_FLAG", value)
        assert env_truthy("NOESIS_TEST_FLAG") is False

    def test_unset_is_falsy(self, monkeypatch):
        monkeypatch.delenv("NOESIS_TEST_FLAG", raising=False)
        assert env_truthy("NOESIS_TEST_FLAG") is False


# ---------------------------------------------------------------------------
# Usage extraction from SDK response shapes
# ---------------------------------------------------------------------------

class TestExtractUsage:
    def test_extracts_from_response_usage(self):
        response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                prompt_tokens_details=SimpleNamespace(cached_tokens=64),
            )
        )
        assert llm_budget.extract_usage(response) == (100, 20, 64)

    def test_extracts_without_cached_details(self):
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=6)
        )
        assert llm_budget.extract_usage(response) == (5, 6, 0)

    def test_extracts_from_nested_raw_wrapper(self):
        inner = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7, completion_tokens=8))
        wrapper = SimpleNamespace(parsed={"ok": True}, raw=inner)
        assert llm_budget.extract_usage(wrapper) == (7, 8, 0)

    def test_missing_usage_returns_none(self):
        assert llm_budget.extract_usage(SimpleNamespace(parsed={"ok": True})) is None
        assert llm_budget.extract_usage(None) is None

    def test_record_response_usage_without_usage_counts_as_unpriced(self, priced_model):
        llm_budget.record_response_usage(
            SimpleNamespace(parsed={"ok": True}), model=priced_model, label="node"
        )
        totals = llm_budget.totals()
        assert totals["calls"] == 1
        assert totals["prompt_tokens"] == 0
        # zero-token calls have a computable ($0) estimate but no real information;
        # unknown-priced models are what drive unpriced_calls.
        assert totals["estimated_usd"] == 0.0

    def test_record_response_usage_with_usage(self, priced_model):
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500)
        )
        llm_budget.record_response_usage(response, model=priced_model, label="node")
        assert llm_budget.by_label()["node"]["prompt_tokens"] == 1000
        assert llm_budget.by_label()["node"]["completion_tokens"] == 500


# ---------------------------------------------------------------------------
# Integration with retry_utils
# ---------------------------------------------------------------------------

class _RecordingClient:
    """Fake OpenAI client that fails loudly if it is ever touched."""

    def __init__(self, response=None):
        self.calls = 0
        self._response = response or SimpleNamespace(
            parsed={"ok": True},
            usage=SimpleNamespace(
                prompt_tokens=1000,
                completion_tokens=500,
                prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            ),
        )
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=self._parse))
        )

    def _parse(self, **kwargs):
        self.calls += 1
        return self._response


class TestRetryUtilsIntegration:
    def test_kill_switch_blocks_sync_wrapper_before_client_touched(self, monkeypatch):
        from app.services.retry_utils import parse_chat_completion_with_retries_sync

        monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
        client = _RecordingClient()

        with pytest.raises(LLMCallBlocked):
            parse_chat_completion_with_retries_sync(
                client,
                model="gpt-5.2-chat-latest",
                messages=[{"role": "user", "content": "hi"}],
                response_format=object,
            )

        assert client.calls == 0

    def test_replay_only_blocks_async_wrapper_before_client_touched(self, monkeypatch):
        import asyncio

        from app.services.retry_utils import parse_chat_completion_with_retries

        monkeypatch.setenv("EVAL_REPLAY_ONLY", "1")
        client = _RecordingClient()

        with pytest.raises(LLMCallBlocked) as exc:
            asyncio.run(
                parse_chat_completion_with_retries(
                    client,
                    model="gpt-5.2-chat-latest",
                    messages=[{"role": "user", "content": "hi"}],
                    response_format=object,
                )
            )

        assert client.calls == 0
        assert "EVAL_REPLAY_ONLY" in str(exc.value)

    def test_successful_sync_call_records_usage(self, monkeypatch):
        from app.services.retry_utils import parse_chat_completion_with_retries_sync

        monkeypatch.setitem(
            llm_budget.MODEL_PRICING_USD_PER_1M,
            "gpt-5.2-chat-latest",
            ModelPrice(1.0, 2.0, 0.5),
        )
        client = _RecordingClient()

        result = parse_chat_completion_with_retries_sync(
            client,
            model="gpt-5.2-chat-latest",
            messages=[{"role": "user", "content": "hi"}],
            response_format=object,
            usage_label="reviewer_panel",
        )

        assert result.parsed == {"ok": True}  # return shape unchanged
        assert client.calls == 1
        by_label = llm_budget.by_label()
        assert by_label["reviewer_panel"]["calls"] == 1
        assert by_label["reviewer_panel"]["prompt_tokens"] == 1000
        assert by_label["reviewer_panel"]["estimated_usd"] == pytest.approx(0.002)
        assert llm_budget.by_model()["gpt-5.2-chat-latest"]["calls"] == 1

    def test_label_defaults_to_model_name(self, monkeypatch):
        from app.services.retry_utils import parse_chat_completion_with_retries_sync

        client = _RecordingClient()
        parse_chat_completion_with_retries_sync(
            client,
            model="gpt-5.2-chat-latest",
            messages=[{"role": "user", "content": "hi"}],
            response_format=object,
        )
        assert "gpt-5.2-chat-latest" in llm_budget.by_label()

    def test_response_without_usage_still_returns_parsed(self):
        from app.services.retry_utils import parse_chat_completion_with_retries_sync

        client = _RecordingClient(response=SimpleNamespace(parsed={"ok": True}))
        result = parse_chat_completion_with_retries_sync(
            client,
            model="gpt-5.2-chat-latest",
            messages=[{"role": "user", "content": "hi"}],
            response_format=object,
        )
        assert result.parsed == {"ok": True}
        assert llm_budget.totals()["calls"] == 1

    def test_ceiling_blocks_second_sync_call(self, monkeypatch):
        from app.services.retry_utils import parse_chat_completion_with_retries_sync

        monkeypatch.setitem(
            llm_budget.MODEL_PRICING_USD_PER_1M,
            "gpt-5.2-chat-latest",
            ModelPrice(1.0, 2.0, 0.5),
        )
        monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "0.001")
        client = _RecordingClient()

        parse_chat_completion_with_retries_sync(
            client,
            model="gpt-5.2-chat-latest",
            messages=[{"role": "user", "content": "hi"}],
            response_format=object,
        )
        assert client.calls == 1

        with pytest.raises(LLMBudgetExceeded):
            parse_chat_completion_with_retries_sync(
                client,
                model="gpt-5.2-chat-latest",
                messages=[{"role": "user", "content": "hi"}],
                response_format=object,
            )
        assert client.calls == 1  # no second network call
