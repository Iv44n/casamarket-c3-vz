from app.benchmarks.llm.judge import judge_conversation


class _FakeProvider:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_judge_conversation_parses_a_well_formed_response():
    provider = _FakeProvider(
        '{"has_greeting": true, "has_farewell": false, "notes": "no se despidio"}'
    )

    result = judge_conversation(provider, "Hola, buenos dias...")

    assert result.has_greeting is True
    assert result.has_farewell is False
    assert result.notes == "no se despidio"
    assert "Hola, buenos dias" in provider.prompts[0]


def test_judge_conversation_returns_none_fields_on_malformed_json():
    provider = _FakeProvider("esto no es json")

    result = judge_conversation(provider, "conversacion")

    assert result.has_greeting is None
    assert result.has_farewell is None
    assert result.raw == "esto no es json"


def test_judge_conversation_returns_none_fields_when_keys_are_missing():
    provider = _FakeProvider("{}")

    result = judge_conversation(provider, "conversacion")

    assert result.has_greeting is None
    assert result.has_farewell is None
    assert result.notes is None


def test_judge_conversation_ignores_wrong_typed_values():
    provider = _FakeProvider('{"has_greeting": "si", "has_farewell": 1, "notes": 123}')

    result = judge_conversation(provider, "conversacion")

    assert result.has_greeting is None
    assert result.has_farewell is None
    assert result.notes is None


def test_judge_conversation_strips_a_leading_think_block_before_parsing():
    raw = (
        "<think>\nVoy a analizar la conversacion para evaluar el comportamiento del "
        "agente...\n</think>\n"
        '{"has_greeting": true, "has_farewell": true, "notes": "saludo y despedida ok"}'
    )
    provider = _FakeProvider(raw)

    result = judge_conversation(provider, "conversacion")

    assert result.has_greeting is True
    assert result.has_farewell is True
    assert result.notes == "saludo y despedida ok"
    # raw se guarda completo, incluido el bloque <think>, para auditoria.
    assert result.raw == raw


def test_judge_conversation_extracts_json_surrounded_by_explanatory_text():
    raw = 'Aqui esta mi analisis: {"has_greeting": false, "has_farewell": false} listo.'
    provider = _FakeProvider(raw)

    result = judge_conversation(provider, "conversacion")

    assert result.has_greeting is False
    assert result.has_farewell is False


def test_judge_conversation_returns_none_fields_when_think_block_never_closes():
    provider = _FakeProvider("<think>razonando sin parar y sin llegar a una respuesta")

    result = judge_conversation(provider, "conversacion")

    assert result.has_greeting is None
    assert result.has_farewell is None
