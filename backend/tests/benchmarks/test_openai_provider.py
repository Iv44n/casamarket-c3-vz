from app.benchmarks.llm.openai_provider import OpenAIProvider, build_openai_provider


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeCompletion(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeOpenAIClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


def test_openai_provider_returns_the_message_content():
    client = _FakeOpenAIClient('{"has_greeting": true}')
    provider = OpenAIProvider(client=client, model="gpt-4o-mini")

    result = provider.complete("juzga esta conversacion")

    assert result == '{"has_greeting": true}'
    call = client.chat.completions.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert call["messages"] == [{"role": "user", "content": "juzga esta conversacion"}]
    assert call["response_format"] == {"type": "json_object"}


def test_openai_provider_returns_empty_string_when_content_is_none():
    client = _FakeOpenAIClient(None)
    provider = OpenAIProvider(client=client, model="gpt-4o-mini")

    assert provider.complete("x") == ""


def test_openai_provider_omits_response_format_when_disabled():
    client = _FakeOpenAIClient('{"has_greeting": true}')
    provider = OpenAIProvider(client=client, model="MiniMax-M1", use_json_response_format=False)

    provider.complete("x")

    call = client.chat.completions.calls[0]
    assert "response_format" not in call


def test_build_openai_provider_passes_through_base_url_and_json_mode_flag():
    provider = build_openai_provider(
        "mm-secreta",
        "MiniMax-M1",
        base_url="https://api.minimax.io/v1",
        use_json_response_format=False,
    )

    assert provider.model == "MiniMax-M1"
    assert provider.use_json_response_format is False
    assert str(provider.client.base_url) == "https://api.minimax.io/v1/"


def test_build_openai_provider_defaults_to_the_real_openai_endpoint():
    provider = build_openai_provider("sk-123", "gpt-4o-mini")

    assert str(provider.client.base_url) == "https://api.openai.com/v1/"
    assert provider.use_json_response_format is True
