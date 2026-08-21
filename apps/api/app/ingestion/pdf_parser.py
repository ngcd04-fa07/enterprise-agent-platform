import io

from pypdf import PdfReader


class PdfParseError(Exception):
    pass


def extract_pages(data: bytes) -> list[str]:
    """One string per page, in order. Extraction quality depends entirely
    on pypdf — scanned/image-only PDFs will yield empty strings (OCR is
    out of scope until a scanned-PDF path exists; see the project brief's
    later-format roadmap).
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise PdfParseError(str(exc)) from exc
