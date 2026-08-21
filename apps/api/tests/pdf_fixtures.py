"""Hand-built, minimally valid PDFs with real extractable text, for tests
that need actual PDF content — not just bytes starting with the magic
number. No PDF-authoring library is a project dependency, so this
constructs the object/xref structure directly.
"""


def build_minimal_pdf(pages: list[str]) -> bytes:
    num_pages = len(pages)
    kids = " ".join(f"{3 + 3 * i} 0 R" for i in range(num_pages))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>".encode(),
    ]

    for i, text in enumerate(pages):
        font_obj_num = 4 + 3 * i
        content_obj_num = 5 + 3 * i
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> "
                f"/MediaBox [0 0 612 792] /Contents {content_obj_num} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        stream = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode()
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(pdf)
    n = len(objects) + 1
    pdf += f"xref\n0 {n}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return pdf
