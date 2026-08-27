import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)


def extract_text_from_bytes(data: bytes) -> str:
    """Concatena el texto de todas las paginas de un PDF. Nunca lanza -- un PDF corrupto o
    sin texto extraible (ej. escaneado como imagen, ver BENCHMARKS_PLAN.md Riesgo 5) devuelve
    "" en vez de tumbar el analisis de un caso completo."""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError) as exc:
        logger.warning("No se pudo leer un PDF del reporte masivo -- %s", exc)
        return ""
    return "\n".join(pages_text).strip()
