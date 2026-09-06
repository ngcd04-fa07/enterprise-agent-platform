import asyncio

import boto3
from botocore.exceptions import ClientError

from app.storage.base import ObjectNotFoundError, ObjectStorage

_NOT_FOUND_ERROR_CODES = {"NoSuchKey", "404"}


class S3ObjectStorage(ObjectStorage):
    """S3-compatible object storage (Stage 21) — works against real AWS
    S3 (`endpoint_url=None`) or any S3-compatible service (MinIO, etc.,
    via `endpoint_url`) using the same boto3 client either way. The
    target bucket is expected to already exist (created by whatever
    provisions the deployment) — this class never creates one itself,
    the same way a real production S3 setup wouldn't want application
    code silently creating buckets against a live AWS account.

    Credentials come from boto3's own standard credential chain (env
    vars, shared config file, an instance/task role) — never a
    project-specific secret field in Settings, so there's no new
    secret-handling path to get wrong.

    boto3 itself is synchronous; every network call here runs on a
    thread via `asyncio.to_thread` — the same pattern
    `FilesystemObjectStorage` already uses around its own sync file I/O,
    not `aioboto3`/`aiobotocore`, to avoid a second, less-established
    async S3 client library for one call site.
    """

    def __init__(self, *, bucket_name: str, endpoint_url: str | None, region_name: str) -> None:
        self._bucket_name = bucket_name
        self._client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region_name)

    async def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get_object(self, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket_name, Key=key
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in _NOT_FOUND_ERROR_CODES:
                raise ObjectNotFoundError(key) from exc
            raise
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    async def delete_object(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket_name, Key=key)

    def generate_access_url(self, key: str) -> str:
        """A real, time-limited presigned URL — meaningful now that a
        real (or real-shaped, e.g. MinIO) object store actually exists to
        sign a URL against, unlike the filesystem backend. Not currently
        used in place of the authenticated GET /documents/{id}/content
        endpoint anywhere in this app — that endpoint's session/RBAC
        enforcement is still the access-control story; this is the
        storage abstraction being complete, not a change to how the API
        actually serves documents today.
        """
        url: str = self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket_name, "Key": key}, ExpiresIn=300
        )
        return url
