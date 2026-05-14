import pytest

from moodlist.llm import MalformedJSONError, call


class _FakeContent:
    def __init__(self, text): self.text = text


class _FakeMessage:
    def __init__(self, text): self.content = [_FakeContent(text)]


def test_call_passes_messages_and_returns_parsed_json(mocker):
    fake_client = mocker.MagicMock()
    fake_client.messages.create.return_value = _FakeMessage(
        '{"picks": [1, 2, 3], "reasoning": "ok", '
        '"wanted_but_missing": [], "needs_live": false}'
    )
    mocker.patch("moodlist.llm.Anthropic", return_value=fake_client)

    result = call(
        api_key="sk-test",
        model="claude-haiku-4-5-20251001",
        system="sys",
        user_blocks=[{"type": "text", "text": "hi"}],
        temperature=0.4,
    )

    assert result["picks"] == [1, 2, 3]
    fake_client.messages.create.assert_called_once()
    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    assert kwargs["system"] == "sys"
    assert kwargs["temperature"] == 0.4


def test_call_raises_on_malformed_json(mocker):
    fake = mocker.MagicMock()
    fake.messages.create.return_value = _FakeMessage("not json at all")
    mocker.patch("moodlist.llm.Anthropic", return_value=fake)
    with pytest.raises(MalformedJSONError):
        call(api_key="k", model="m", system="s", user_blocks=[], temperature=0.4)


def test_call_extracts_json_from_fenced_response(mocker):
    fake = mocker.MagicMock()
    fake.messages.create.return_value = _FakeMessage(
        'Here you go:\n```json\n{"picks":[7], "reasoning":"r", '
        '"wanted_but_missing":[], "needs_live": false}\n```'
    )
    mocker.patch("moodlist.llm.Anthropic", return_value=fake)
    result = call(api_key="k", model="m", system="s", user_blocks=[], temperature=0.4)
    assert result["picks"] == [7]


def test_call_retries_once_on_transient(mocker):
    from anthropic import APIStatusError
    fake = mocker.MagicMock()
    err = APIStatusError("boom", response=mocker.MagicMock(status_code=503),
                         body=None)
    fake.messages.create.side_effect = [err, _FakeMessage(
        '{"picks":[1], "reasoning":"r", "wanted_but_missing":[], "needs_live":false}'
    )]
    mocker.patch("moodlist.llm.Anthropic", return_value=fake)
    mocker.patch("moodlist.llm.time.sleep")  # avoid real sleep
    result = call(api_key="k", model="m", system="s", user_blocks=[], temperature=0.4)
    assert result["picks"] == [1]
    assert fake.messages.create.call_count == 2
