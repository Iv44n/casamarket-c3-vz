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


def test_judge_conversation_parses_complexity_and_handled_well_for_complexity():
    provider = _FakeProvider(
        '{"has_greeting": true, "has_farewell": true, "complexity": "alta", '
        '"handled_well_for_complexity": false, "notes": "caso dificil mal resuelto"}'
    )

    result = judge_conversation(provider, "conversacion")

    assert result.complexity == "alta"
    assert result.handled_well_for_complexity is False


def test_judge_conversation_discards_an_invalid_complexity_value():
    provider = _FakeProvider(
        '{"has_greeting": true, "has_farewell": true, "complexity": "extrema", '
        '"handled_well_for_complexity": true}'
    )

    result = judge_conversation(provider, "conversacion")

    assert result.complexity is None


def test_judge_conversation_parses_informed_transfer_when_case_had_a_transfer():
    provider = _FakeProvider(
        '{"has_greeting": true, "has_farewell": true, "complexity": "media", '
        '"handled_well_for_complexity": true, "informed_transfer": true}'
    )

    result = judge_conversation(provider, "conversacion", had_transfer=True)

    assert result.informed_transfer is True


def test_judge_conversation_discards_informed_transfer_when_case_had_no_transfer():
    # El LLM podria responder informed_transfer de todos modos (no se le pidio, pero no esta
    # prohibido) -- no aplica cuando el caso no tuvo transferencia, asi que se descarta a None
    # en vez de tomarlo al pie de la letra.
    provider = _FakeProvider(
        '{"has_greeting": true, "has_farewell": true, "complexity": "media", '
        '"handled_well_for_complexity": true, "informed_transfer": true}'
    )

    result = judge_conversation(provider, "conversacion", had_transfer=False)

    assert result.informed_transfer is None


def test_judge_conversation_prompt_includes_transfer_question_only_when_had_transfer():
    provider_with_transfer = _FakeProvider(
        '{"has_greeting": true, "has_farewell": true, "complexity": "baja", '
        '"handled_well_for_complexity": true, "informed_transfer": true}'
    )
    provider_without_transfer = _FakeProvider(
        '{"has_greeting": true, "has_farewell": true, "complexity": "baja", '
        '"handled_well_for_complexity": true}'
    )

    judge_conversation(provider_with_transfer, "conversacion", had_transfer=True)
    judge_conversation(provider_without_transfer, "conversacion", had_transfer=False)

    assert "transferencia" in provider_with_transfer.prompts[0]
    assert "informed_transfer" in provider_with_transfer.prompts[0]
    assert "informed_transfer" not in provider_without_transfer.prompts[0]
