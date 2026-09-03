import logging

import pypdfium2 as pdfium

logger = logging.getLogger(__name__)


def extract_text_from_bytes(data: bytes) -> str:
    """Concatena el texto de todas las paginas de un PDF. Nunca lanza -- un PDF corrupto o
    sin texto extraible (ej. escaneado como imagen, ver BENCHMARKS_PLAN.md Riesgo 5) devuelve
    "" en vez de tumbar el analisis de un caso completo.

    pypdfium2 (bindings de PDFium, el motor de Chrome), no pypdf -- reemplazado el
    2026-09-03 tras confirmar en vivo, contra un reporte masivo real de 186 PDFs, que pypdf
    retenia 767-800MB de RAM para extraer apenas 514KB de texto util (mas que el limite
    entero de RAM del servicio en Render, 512MB, y la causa confirmada de un OOM real en
    produccion). pypdfium2, al ser una extension en C (no arma el mismo tipo de ciclos de
    referencia en objetos Python que pypdf), procesa el mismo zip en ~44MB de RSS y ~0.6s en
    vez de ~800MB y ~120s -- no hace falta ningun truco de gc/malloc_trim con esta libreria."""
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        logger.warning("No se pudo leer un PDF del reporte masivo -- %s", exc)
        return ""
    try:
        pages_text = []
        for page in pdf:
            textpage = page.get_textpage()
            try:
                pages_text.append(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
        return "\n".join(pages_text).strip()
    finally:
        pdf.close()
