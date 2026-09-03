import ctypes
import gc
import logging
import zipfile
from collections.abc import Iterable
from pathlib import Path

from . import pdf_text

logger = logging.getLogger(__name__)

# Confirmado en vivo (por el usuario, contra un zip real de 'attention') -- un PDF por
# atencion, nombrado "attention_<ID atencion>.pdf". Se asume el mismo prefijo para
# 'outboundattention' hasta confirmarlo con un zip real de esa direccion (ver
# BENCHMARKS_PLAN.md Riesgo 1) -- si resulta distinto, el fix es de una linea aca.
_PDF_FILENAME_TEMPLATE = "attention_{id}.pdf"

# pypdf arma ciclos de referencia internos por PDF que el refcounting normal de CPython no
# limpia solo -- confirmado en vivo el 2026-09-03 midiendo RSS contra un zip real de 186 PDFs:
# sin nada de esto, terminaba en 767-800MB de RSS para extraer apenas 514KB de texto util (mas
# que el limite entero de RAM del servicio en Render, 512MB, causando el OOM real que se vio
# en produccion). gc.collect() solo no alcanza (RSS seguia en ~670MB): gc.collect() libera los
# objetos Python pero el malloc de glibc no le devuelve esas paginas al SO solo -- hace falta
# pedirselo explicitamente con malloc_trim. Con ambos combinados, el mismo zip bajo a ~587MB.
# Sigue sin ser gratis (no soluciona el problema de fondo, que es cuanta memoria por PDF pide
# pypdf mientras lo esta parseando) pero es la mitigacion mas simple y de menor riesgo posible
# -- sin dependencias nuevas, sin cambiar la arquitectura del pipeline.
_GC_EVERY_N_PDFS = 20


def _trim_memory() -> None:
    """Best-effort: en un sistema sin glibc o sin malloc_trim (no deberia pasar en el
    contenedor Linux de produccion, pero si en un dev/CI raro, ej. musl o macOS) simplemente
    no hace nada -- esto es una optimizacion, nunca debe tumbar la extraccion de un caso
    real."""
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def extract_texts_for_ids(zip_path: Path, ids: Iterable[str]) -> dict[str, str]:
    """Abre el zip UNA vez (nunca escribe los PDFs a disco -- son conversaciones de
    clientes) y busca puntualmente solo los PDFs de `ids`, por nombre exacto, en vez de
    parsear cada entrada del zip. IDs sin PDF en el zip simplemente no aparecen en el dict
    devuelto -- el caller decide que hacer con un caso cerrado sin conversacion (ver
    pipeline.build_case_benchmarks). Cada `_GC_EVERY_N_PDFS` PDFs procesados, fuerza una
    liberacion de memoria (ver _trim_memory) -- pypdf retiene mucha mas memoria por PDF de la
    que deberia, y en un reporte masivo tipico (100-200 PDFs) eso solo alcanza para tumbar
    el proceso entero por OOM en un servicio con poca RAM (ver el comentario junto a
    _GC_EVERY_N_PDFS)."""
    ids = list(ids)
    texts: dict[str, str] = {}
    if not ids:
        return texts

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        processed = 0
        for id_ in ids:
            filename = _PDF_FILENAME_TEMPLATE.format(id=id_)
            if filename not in names:
                continue
            texts[id_] = pdf_text.extract_text_from_bytes(zf.read(filename))
            processed += 1
            if processed % _GC_EVERY_N_PDFS == 0:
                _trim_memory()

    if not texts and names:
        logger.warning(
            "Ningun ID de %d candidatos calzo con el patron de nombre '%s' dentro de %s -- "
            "puede que esta direccion use un nombre de archivo distinto (ver "
            "BENCHMARKS_PLAN.md Riesgo 1).",
            len(ids),
            _PDF_FILENAME_TEMPLATE,
            zip_path.name,
        )
    return texts
