import httpx
import pytest

from agentgov.providers.openai_compatible import OpenAICompatibleProvider


@pytest.mark.parametrize("status", [403, 503])
def test_provider_failure_explains_model_and_redacts_key(monkeypatch, status):
    secret = "private-test-key"
    response = httpx.Response(
        status,
        json={"error": {"message": f"Model unavailable for {secret}"}},
        request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)
    provider = OpenAICompatibleProvider("https://example.test/v1", "", "gpt-5.6-luna", api_key=secret)
    with pytest.raises(RuntimeError) as error:
        provider.complete("Plan a task", "leader")
    message = str(error.value)
    assert f"HTTP {status}" in message
    assert "gpt-5.6-luna" in message
    assert "Model unavailable" in message
    assert secret not in message
    assert "[REDACTED]" in message


def test_non_json_provider_failure_does_not_publish_raw_response(monkeypatch):
    response = httpx.Response(
        502,
        text="<html>internal proxy debug data</html>",
        request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)
    provider = OpenAICompatibleProvider("https://example.test/v1", "", "test", api_key="secret")
    with pytest.raises(RuntimeError, match="HTTP 502") as error:
        provider.complete("Plan", "leader")
    assert "internal proxy debug data" not in str(error.value)
