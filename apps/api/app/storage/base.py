from abc import ABC, abstractmethod


class ObjectNotFoundError(Exception):
    pass


class ObjectStorage(ABC):
    """Provider-neutral interface for storing/retrieving document bytes.
    Business logic depends only on this — never on a specific provider SDK
    (see CLAUDE.md: "no hidden provider coupling"). Two implementations:
    filesystem-backed (local dev, the default) and S3-compatible (Stage
    21 — see app/storage/s3.py, and docs/architecture.md's object storage
    decision for why boto3 + asyncio.to_thread rather than aioboto3).

    Methods are async even for the filesystem implementation (which uses
    asyncio.to_thread internally) so the S3 implementation is a drop-in
    swap with no change to callers — selected via Settings.storage_backend,
    see app/storage/factory.py.
    """

    @abstractmethod
    async def put_object(self, key: str, data: bytes, *, content_type: str) -> None: ...

    @abstractmethod
    async def get_object(self, key: str) -> bytes:
        """Raises ObjectNotFoundError if `key` doesn't exist."""
        ...

    @abstractmethod
    async def delete_object(self, key: str) -> None: ...

    @abstractmethod
    def generate_access_url(self, key: str) -> str:
        """A URL the client can use to fetch this object. For the
        filesystem backend this is a path to our own authenticated
        download endpoint (access control = the existing session/RBAC
        checks) rather than an out-of-band signed URL — there's no
        public object store to sign a URL against. The S3 backend
        returns a real, time-limited presigned URL instead (see
        app/storage/s3.py) — not currently used in place of the
        authenticated endpoint anywhere in this app.
        """
