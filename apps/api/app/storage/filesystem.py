import asyncio
from pathlib import Path

from app.storage.base import ObjectNotFoundError, ObjectStorage


class FilesystemObjectStorage(ObjectStorage):
    """Local-dev object storage backed by the filesystem. Keys are always
    server-generated (see DocumentService) — never taken verbatim from a
    client filename — but _resolve_path still defends against path
    traversal in depth, in case that ever stops being true for some
    future caller.
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        resolved = (self._root / key).resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise ValueError(f"storage key escapes storage root: {key!r}")
        return resolved

    async def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        del content_type  # unused for filesystem storage; kept for interface parity with S3
        path = self._resolve_path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)

    async def get_object(self, key: str) -> bytes:
        path = self._resolve_path(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        return await asyncio.to_thread(path.read_bytes)

    async def delete_object(self, key: str) -> None:
        path = self._resolve_path(key)

        def _delete() -> None:
            path.unlink(missing_ok=True)

        await asyncio.to_thread(_delete)

    def generate_access_url(self, key: str) -> str:
        raise NotImplementedError(
            "Filesystem storage has no out-of-band URL to sign — documents are served "
            "through the authenticated GET /documents/{id}/content endpoint instead, "
            "which enforces tenant/RBAC checks that a bare signed URL couldn't. This "
            "becomes meaningful once a real S3-compatible backend exists (Stage 21)."
        )
