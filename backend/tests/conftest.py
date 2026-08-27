def minimal_pdf_bytes(text: str) -> bytes:
    """Construye a mano un PDF minimo, valido, de una sola pagina con `text` como contenido
    de un content stream real (BT/Tj/ET) -- no hay libreria de generacion de PDFs en las
    dependencias de este proyecto (pypdf solo lee/manipula, no dibuja texto), asi que los
    tests de extraccion de texto (pdf_text.py, massive_zip.py) construyen el PDF ellos mismos
    en vez de depender de un archivo de fixture externo."""
    content = f"BT /F1 24 Tf 10 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 200 200] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]

    pdf = b"%PDF-1.4\n"
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"

    xref_offset = len(pdf)
    pdf += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        pdf += ("%010d 00000 n \n" % offset).encode()
    pdf += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF"
    )
    return pdf
