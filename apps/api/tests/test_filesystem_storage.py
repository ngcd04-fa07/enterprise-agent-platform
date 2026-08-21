from pathlib import Path

import pytest

from app.storage.base import ObjectNotFoundError
from app.storage.filesystem import FilesystemObjectStorage


async def test_put_and_get_object_roundtrip(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(str(tmp_path))

    await storage.put_object(
        "org/doc.pdf", b"%PDF-1.4 fake content", content_type="application/pdf"
    )
    content = await storage.get_object("org/doc.pdf")

    assert content == b"%PDF-1.4 fake content"


async def test_get_object_raises_when_missing(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(str(tmp_path))

    with pytest.raises(ObjectNotFoundError):
        await storage.get_object("does/not/exist.pdf")


async def test_delete_object_is_idempotent(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(str(tmp_path))
    await storage.put_object("org/doc.pdf", b"content", content_type="application/pdf")

    await storage.delete_object("org/doc.pdf")
    await storage.delete_object("org/doc.pdf")  # second delete must not raise

    with pytest.raises(ObjectNotFoundError):
        await storage.get_object("org/doc.pdf")


async def test_rejects_key_that_escapes_storage_root(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(str(tmp_path))

    with pytest.raises(ValueError, match="escapes storage root"):
        await storage.put_object("../escape.pdf", b"content", content_type="application/pdf")


def test_generate_access_url_not_implemented_for_filesystem_backend(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(str(tmp_path))

    with pytest.raises(NotImplementedError):
        storage.generate_access_url("org/doc.pdf")
