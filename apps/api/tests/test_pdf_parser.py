import pytest

from app.ingestion.pdf_parser import PdfParseError, extract_pages
from tests.pdf_fixtures import build_minimal_pdf


def test_extract_pages_single_page() -> None:
    pdf = build_minimal_pdf(["Hello World"])

    pages = extract_pages(pdf)

    assert len(pages) == 1
    assert "Hello World" in pages[0]


def test_extract_pages_multi_page_preserves_order() -> None:
    pdf = build_minimal_pdf(["Page one content", "Page two content", "Page three content"])

    pages = extract_pages(pdf)

    assert len(pages) == 3
    assert "Page one content" in pages[0]
    assert "Page two content" in pages[1]
    assert "Page three content" in pages[2]


def test_extract_pages_raises_on_garbage_input() -> None:
    with pytest.raises(PdfParseError):
        extract_pages(b"not a pdf at all")
