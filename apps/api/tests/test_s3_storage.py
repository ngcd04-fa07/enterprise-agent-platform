"""Tests S3ObjectStorage against moto's in-process fake AWS (Stage 21) —
no real AWS account, no network, no MinIO container needed for this
suite; deterministic and fast. Mirrors test_filesystem_storage.py's
shape exactly, proving both implementations satisfy the same ObjectStorage
contract.
"""

import boto3
import pytest
from moto import mock_aws

from app.storage.base import ObjectNotFoundError
from app.storage.s3 import S3ObjectStorage

_BUCKET = "test-bucket"
_REGION = "us-east-1"


@pytest.fixture
def s3_storage():  # type: ignore[no-untyped-def]
    with mock_aws():
        boto3.client("s3", region_name=_REGION).create_bucket(Bucket=_BUCKET)
        yield S3ObjectStorage(bucket_name=_BUCKET, endpoint_url=None, region_name=_REGION)


async def test_put_and_get_object_roundtrip(s3_storage: S3ObjectStorage) -> None:
    await s3_storage.put_object(
        "org/doc.pdf", b"%PDF-1.4 fake content", content_type="application/pdf"
    )
    content = await s3_storage.get_object("org/doc.pdf")

    assert content == b"%PDF-1.4 fake content"


async def test_get_object_raises_when_missing(s3_storage: S3ObjectStorage) -> None:
    with pytest.raises(ObjectNotFoundError):
        await s3_storage.get_object("does/not/exist.pdf")


async def test_delete_object_is_idempotent(s3_storage: S3ObjectStorage) -> None:
    await s3_storage.put_object("org/doc.pdf", b"content", content_type="application/pdf")

    await s3_storage.delete_object("org/doc.pdf")
    await s3_storage.delete_object("org/doc.pdf")  # second delete must not raise

    with pytest.raises(ObjectNotFoundError):
        await s3_storage.get_object("org/doc.pdf")


async def test_generate_access_url_returns_a_real_presigned_url(
    s3_storage: S3ObjectStorage,
) -> None:
    await s3_storage.put_object("org/doc.pdf", b"content", content_type="application/pdf")

    url = s3_storage.generate_access_url("org/doc.pdf")

    assert url.startswith("https://")
    assert _BUCKET in url
    assert "org/doc.pdf" in url
    # A presigned URL carries its own auth in the query string — proof
    # this is a real signed URL, not just a bare path.
    assert "Signature=" in url or "X-Amz-Signature=" in url


async def test_content_type_is_preserved(s3_storage: S3ObjectStorage) -> None:
    await s3_storage.put_object("org/doc.pdf", b"content", content_type="application/pdf")

    stored = boto3.client("s3", region_name=_REGION).get_object(Bucket=_BUCKET, Key="org/doc.pdf")

    assert stored["ContentType"] == "application/pdf"
