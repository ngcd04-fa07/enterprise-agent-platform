from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import ObjectStorage
from app.storage.filesystem import FilesystemObjectStorage
from app.storage.s3 import S3ObjectStorage


@lru_cache
def get_object_storage() -> ObjectStorage:
    """FastAPI dependency / app-wide accessor. Which implementation gets
    built is Settings.storage_backend (Stage 21) — swapping providers
    only ever touches this function, never a caller.
    """
    settings = get_settings()
    if settings.storage_backend == "s3":
        if settings.s3_bucket_name is None:
            # Unreachable via normal startup — Settings' own validator
            # (_validate_s3_backend_has_a_bucket) already enforces this.
            # A real check, not an assert (S101): asserts can be
            # stripped under -O, which would silently turn this into a
            # None passed to S3ObjectStorage instead of a clear error.
            raise RuntimeError("s3_bucket_name is required when storage_backend=s3")
        return S3ObjectStorage(
            bucket_name=settings.s3_bucket_name,
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
        )
    return FilesystemObjectStorage(settings.storage_root)
