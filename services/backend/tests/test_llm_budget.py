"""Unit tests for LLM spend guardrails (app/core/llm_budget.py)."""

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
    env_truthy,
    estimate_usd,
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

    With MODEL_PRICING_USD_PER_1M unpriced, the dollar ceiling can never trip:
    every call is unpriced, contributes 0 to spend, and NOESIS_LLM_MAX_SPEND_USD
    stays inert. These tests use an UNPRICED model on purpose, to prove the call
    ceiling still fires under exactly the conditions that defeat the dollar one.
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

    def test_estimate_is_none_when_price_entry_has_none_rates(self):
        # The shipped table deliberately leaves rates as None until verified.
        assert estimate_usd("gpt-5.2", 1000, 1000) is None

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
