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


def extract_texts_for_ids(zip_path: Path, ids: Iterable[str]) -> dict[str, str]:
    """Abre el zip UNA vez (nunca escribe los PDFs a disco -- son conversaciones de
    clientes) y busca puntualmente solo los PDFs de `ids`, por nombre exacto, en vez de
    parsear cada entrada del zip. IDs sin PDF en el zip simplemente no aparecen en el dict
    devuelto -- el caller decide que hacer con un caso cerrado sin conversacion (ver
    pipeline.build_case_benchmarks)."""
    ids = list(ids)
    texts: dict[str, str] = {}
    if not ids:
        return texts

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for id_ in ids:
            filename = _PDF_FILENAME_TEMPLATE.format(id=id_)
            if filename not in names:
                continue
            texts[id_] = pdf_text.extract_text_from_bytes(zf.read(filename))

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
