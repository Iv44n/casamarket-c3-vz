from pypdf import PdfWriter

from app.c3 import pdf_text
from tests.conftest import minimal_pdf_bytes


def _blank_pdf_bytes() -> bytes:
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extract_text_from_bytes_returns_the_real_text():
    text = pdf_text.extract_text_from_bytes(minimal_pdf_bytes("Hola Ana, buenos dias"))

    assert "Hola Ana" in text


def test_extract_text_from_bytes_returns_empty_string_for_a_blank_page():
    text = pdf_text.extract_text_from_bytes(_blank_pdf_bytes())

    assert text == ""


def test_extract_text_from_bytes_never_raises_on_garbage_input():
    text = pdf_text.extract_text_from_bytes(b"esto no es un pdf")

    assert text == ""
