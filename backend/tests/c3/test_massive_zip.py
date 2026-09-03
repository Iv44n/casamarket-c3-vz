import logging
import zipfile
from pathlib import Path

import pytest

from app.c3 import massive_zip
from tests.conftest import minimal_pdf_bytes


def _write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_extract_texts_for_ids_returns_only_the_requested_ids_found_in_the_zip(
    tmp_path: Path,
):
    zip_path = tmp_path / "attention_masivo.zip"
    _write_zip(
        zip_path,
        {
            "attention_111.pdf": minimal_pdf_bytes("Hola, soy Ana"),
            "attention_222.pdf": minimal_pdf_bytes("Hola, soy Luis"),
            "attention_333.pdf": minimal_pdf_bytes("no pedido"),
        },
    )

    texts = massive_zip.extract_texts_for_ids(zip_path, ["111", "222", "999"])

    assert set(texts) == {"111", "222"}
    assert "Ana" in texts["111"]
    assert "Luis" in texts["222"]


def test_extract_texts_for_ids_returns_empty_dict_for_no_ids(tmp_path: Path):
    zip_path = tmp_path / "attention_masivo.zip"
    _write_zip(zip_path, {"attention_111.pdf": minimal_pdf_bytes("hola")})

    assert massive_zip.extract_texts_for_ids(zip_path, []) == {}


def test_extract_texts_for_ids_warns_when_nothing_matches(
    tmp_path: Path, caplog
):
    zip_path = tmp_path / "outboundattention_masivo.zip"
    _write_zip(zip_path, {"outboundattention_555.pdf": minimal_pdf_bytes("hola")})

    with caplog.at_level(logging.WARNING):
        texts = massive_zip.extract_texts_for_ids(zip_path, ["555"])

    assert texts == {}
    assert any("Ningun ID" in record.message for record in caplog.records)


def test_extract_texts_for_ids_trims_memory_every_n_pdfs_processed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(massive_zip, "_GC_EVERY_N_PDFS", 2)
    calls = []
    monkeypatch.setattr(massive_zip, "_trim_memory", lambda: calls.append(1))
    zip_path = tmp_path / "attention_masivo.zip"
    _write_zip(
        zip_path,
        {f"attention_{i}.pdf": minimal_pdf_bytes(f"caso {i}") for i in range(5)},
    )

    massive_zip.extract_texts_for_ids(zip_path, [str(i) for i in range(5)])

    # 5 PDFs procesados, cada 2 -- se llama en el 2do y el 4to, no en el 5to (todavia no
    # completo otro lote de 2).
    assert len(calls) == 2


def test_extract_texts_for_ids_does_not_trim_when_no_ids_match_the_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = []
    monkeypatch.setattr(massive_zip, "_trim_memory", lambda: calls.append(1))
    zip_path = tmp_path / "attention_masivo.zip"
    _write_zip(zip_path, {"attention_111.pdf": minimal_pdf_bytes("hola")})

    massive_zip.extract_texts_for_ids(zip_path, ["999"])

    assert calls == []


def test_trim_memory_never_raises_even_without_a_usable_libc(
    monkeypatch: pytest.MonkeyPatch,
):
    def _boom(_name):
        raise OSError("no libc.so.6 here")

    monkeypatch.setattr(massive_zip.ctypes, "CDLL", _boom)

    massive_zip._trim_memory()  # no lanza
