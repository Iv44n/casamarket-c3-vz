import pytest

from app.extraction import parsing


@pytest.fixture(autouse=True)
def _reset_history_cache():
    """La cache de parse_report_history() vive a nivel de modulo (persiste entre tests dentro
    de la misma corrida de pytest) -- sin este reset, un test que cachea una fila con una
    conexion sqlite:memory: descartada al final del test puede filtrarse a otro test que espera
    una DB vacia, aunque usen conexiones sqlite distintas."""
    parsing._history_cache.clear()
    yield
    parsing._history_cache.clear()
