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
        '{"greeting_level": "formal", "has_farewell": false, "notes": "no se despidio"}'
    )

    result = judge_conversation(provider, "Hola, buenos dias...")

    assert result.greeting_level == "formal"
    assert result.has_farewell is False
    assert result.notes == "no se despidio"
    assert "Hola, buenos dias" in provider.prompts[0]


def test_judge_conversation_returns_none_fields_on_malformed_json():
    provider = _FakeProvider("esto no es json")

    result = judge_conversation(provider, "conversacion")

    assert result.greeting_level is None
    assert result.has_farewell is None
    assert result.raw == "esto no es json"


def test_judge_conversation_returns_none_fields_when_keys_are_missing():
    provider = _FakeProvider("{}")

    result = judge_conversation(provider, "conversacion")

    assert result.greeting_level is None
    assert result.has_farewell is None
    assert result.notes is None


def test_judge_conversation_ignores_wrong_typed_values():
    provider = _FakeProvider(
        '{"greeting_level": 1, "has_farewell": 1, "spelling_ok": "si", "notes": 123}'
    )

    result = judge_conversation(provider, "conversacion")

    assert result.greeting_level is None
    assert result.has_farewell is None
    assert result.spelling_ok is None
    assert result.notes is None


def test_judge_conversation_strips_a_leading_think_block_before_parsing():
    raw = (
        "<think>\nVoy a analizar la conversacion para evaluar el comportamiento del "
        "agente...\n</think>\n"
        '{"greeting_level": "formal", "has_farewell": true, "notes": "saludo y despedida ok"}'
    )
    provider = _FakeProvider(raw)

    result = judge_conversation(provider, "conversacion")

    assert result.greeting_level == "formal"
    assert result.has_farewell is True
    assert result.notes == "saludo y despedida ok"
    # raw se guarda completo, incluido el bloque <think>, para auditoria.
    assert result.raw == raw


def test_judge_conversation_extracts_json_surrounded_by_explanatory_text():
    raw = 'Aqui esta mi analisis: {"greeting_level": "ninguno", "has_farewell": false} listo.'
    provider = _FakeProvider(raw)

    result = judge_conversation(provider, "conversacion")

    assert result.greeting_level == "ninguno"
    assert result.has_farewell is False


def test_judge_conversation_returns_none_fields_when_think_block_never_closes():
    provider = _FakeProvider("<think>razonando sin parar y sin llegar a una respuesta")

    result = judge_conversation(provider, "conversacion")

    assert result.greeting_level is None
    assert result.has_farewell is None


def test_judge_conversation_parses_a_casual_greeting():
    # El caso real que motivo este criterio: un saludo breve seguido de inmediato por un
    # pedido debe calzar en "casual", no en "ninguno".
    provider = _FakeProvider(
        '{"greeting_level": "casual", "has_farewell": false, '
        '"notes": "saludo casual, sin despedida"}'
    )

    result = judge_conversation(provider, "Buenos Dias me indica su codigo anydesk...")

    assert result.greeting_level == "casual"


def test_judge_conversation_discards_an_invalid_greeting_level():
    provider = _FakeProvider('{"greeting_level": "amable", "has_farewell": true}')

    result = judge_conversation(provider, "conversacion")

    assert result.greeting_level is None


def test_judge_conversation_parses_complexity_and_handled_well_for_complexity():
    provider = _FakeProvider(
        '{"greeting_level": "formal", "has_farewell": true, "complexity": "alta", '
        '"handled_well_for_complexity": false, "notes": "caso dificil mal resuelto"}'
    )

    result = judge_conversation(provider, "conversacion")

    assert result.complexity == "alta"
    assert result.handled_well_for_complexity is False


def test_judge_conversation_discards_an_invalid_complexity_value():
    provider = _FakeProvider(
        '{"greeting_level": "formal", "has_farewell": true, "complexity": "extrema", '
        '"handled_well_for_complexity": true}'
    )

    result = judge_conversation(provider, "conversacion")

    assert result.complexity is None


def test_judge_conversation_parses_spelling_ok():
    provider = _FakeProvider(
        '{"greeting_level": "formal", "has_farewell": true, "spelling_ok": false, '
        '"notes": "varios errores de tipeo"}'
    )

    result = judge_conversation(provider, "conversacion")

    assert result.spelling_ok is False


def test_judge_conversation_returns_none_spelling_ok_when_missing():
    provider = _FakeProvider('{"greeting_level": "formal", "has_farewell": true}')

    result = judge_conversation(provider, "conversacion")

    assert result.spelling_ok is None


def test_judge_conversation_parses_informed_transfer_when_case_had_a_transfer():
    provider = _FakeProvider(
        '{"greeting_level": "formal", "has_farewell": true, "complexity": "media", '
        '"handled_well_for_complexity": true, "informed_transfer": true}'
    )

    result = judge_conversation(provider, "conversacion", transferred_from_agents=["Ana"])

    assert result.informed_transfer is True


def test_judge_conversation_discards_informed_transfer_when_case_had_no_transfer():
    # El LLM podria responder informed_transfer de todos modos (no se le pidio, pero no esta
    # prohibido) -- no aplica cuando el caso no tuvo transferencia, asi que se descarta a None
    # en vez de tomarlo al pie de la letra.
    provider = _FakeProvider(
        '{"greeting_level": "formal", "has_farewell": true, "complexity": "media", '
        '"handled_well_for_complexity": true, "informed_transfer": true}'
    )

    result = judge_conversation(provider, "conversacion", transferred_from_agents=[])

    assert result.informed_transfer is None


def test_judge_conversation_prompt_includes_transfer_question_only_when_transferred():
    provider_with_transfer = _FakeProvider(
        '{"greeting_level": "casual", "has_farewell": true, "complexity": "baja", '
        '"handled_well_for_complexity": true, "informed_transfer": true}'
    )
    provider_without_transfer = _FakeProvider(
        '{"greeting_level": "casual", "has_farewell": true, "complexity": "baja", '
        '"handled_well_for_complexity": true}'
    )

    judge_conversation(provider_with_transfer, "conversacion", transferred_from_agents=["Ana"])
    judge_conversation(provider_without_transfer, "conversacion", transferred_from_agents=[])

    assert "transferido" in provider_with_transfer.prompts[0]
    assert "informed_transfer" in provider_with_transfer.prompts[0]
    assert "informed_transfer" not in provider_without_transfer.prompts[0]


def test_judge_conversation_prompt_includes_the_origin_agent_names_when_transferred():
    provider = _FakeProvider('{"greeting_level": "casual", "has_farewell": true}')

    judge_conversation(
        provider, "conversacion", transferred_from_agents=["Ana Perez", "Luis Gomez"]
    )

    assert "Ana Perez, Luis Gomez" in provider.prompts[0]


def test_judge_conversation_prompt_asks_the_notes_to_reference_the_transfer_when_applicable():
    # El nombre del agente origen aparece DOS veces cuando hay transferencia: una en la
    # pregunta 6, otra en el pedido especifico a la nota de auditoria de que lo mencione --
    # confirma que el hint de la nota (no solo la pregunta) tambien lo incluye.
    provider = _FakeProvider('{"greeting_level": "casual", "has_farewell": true}')

    judge_conversation(provider, "conversacion", transferred_from_agents=["Ana Perez"])

    assert provider.prompts[0].count("Ana Perez") == 2


def test_judge_conversation_prompt_asks_for_a_multi_sentence_note_not_a_summary():
    provider = _FakeProvider('{"greeting_level": "casual", "has_farewell": true}')

    judge_conversation(provider, "conversacion")

    prompt = provider.prompts[0]
    assert "no un simple resumen" in prompt.lower()
    assert "justific" in prompt.lower()


def test_judge_conversation_prompt_always_includes_greeting_and_spelling_questions():
    provider = _FakeProvider('{"greeting_level": "formal", "has_farewell": true}')

    judge_conversation(provider, "conversacion")

    prompt = provider.prompts[0]
    assert "casual" in prompt and "formal" in prompt
    assert "ortografia" in prompt
