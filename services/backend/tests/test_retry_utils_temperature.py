from types import SimpleNamespace

from app.services.retry_utils import (
    _sanitize_structured_completion_kwargs,
    parse_chat_completion_with_retries_sync,
)


class FakeParseEndpoint:
    def __init__(self):
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(parsed={"ok": True})


class FakeClient:
    def __init__(self):
        self.parse_endpoint = FakeParseEndpoint()
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(parse=self.parse_endpoint.parse)
            )
        )


def test_sanitize_structured_completion_removes_gpt52_zero_temperature():
    kwargs = {
        "model": "gpt-5.2-chat-latest",
        "temperature": 0,
        "max_completion_tokens": 100,
    }

    sanitized = _sanitize_structured_completion_kwargs(kwargs)

    assert "temperature" not in sanitized
    assert kwargs["temperature"] == 0
    assert sanitized["max_completion_tokens"] == 100


def test_sanitize_structured_completion_leaves_other_models_unchanged():
    kwargs = {"model": "some-other-model", "temperature": 0}

    assert _sanitize_structured_completion_kwargs(kwargs)["temperature"] == 0


def test_sync_parse_wrapper_does_not_forward_gpt52_zero_temperature():
    client = FakeClient()

    response = parse_chat_completion_with_retries_sync(
        client,
        model="gpt-5.2-chat-latest",
        messages=[{"role": "user", "content": "test"}],
        max_completion_tokens=100,
        temperature=0,
        response_format=object,
    )

    assert response.parsed == {"ok": True}
    assert "temperature" not in client.parse_endpoint.kwargs
    assert client.parse_endpoint.kwargs["model"] == "gpt-5.2-chat-latest"
