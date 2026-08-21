from abc import ABC, abstractmethod


class ObjectNotFoundError(Exception):
    pass


class ObjectStorage(ABC):
    """Provider-neutral interface for storing/retrieving document bytes.
    Business logic depends only on this — never on a specific provider SDK
    (see CLAUDE.md: "no hidden provider coupling"). The only implementation
    right now is filesystem-backed, for local dev; an S3-compatible
    implementation is deferred to Stage 21 (deployment) — see
    docs/architecture.md, object storage decision.

    Methods are async even for the filesystem implementation (which uses
    asyncio.to_thread internally) so a future S3/aioboto3 implementation
    is a drop-in swap with no change to callers.
    """

    @abstractmethod
    async def put_object(self, key: str, data: bytes, *, content_type: str) -> None: ...

    @abstractmethod
    async def get_object(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete_object(self, key: str) -> None: ...

    @abstractmethod
    def generate_access_url(self, key: str) -> str:
        """A URL the client can use to fetch this object. For the
        filesystem backend this is a path to our own authenticated
        download endpoint (access control = the existing session/RBAC
        checks) rather than an out-of-band signed URL — there's no
        public object store to sign a URL against yet. A real S3
        implementation would return an actual presigned URL instead.
        """
