from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import ObjectStorage
from app.storage.filesystem import FilesystemObjectStorage


@lru_cache
def get_object_storage() -> ObjectStorage:
    """FastAPI dependency / app-wide accessor. The only implementation
    right now is filesystem-backed (see app/storage/base.py) — swapping to
    S3-compatible storage later only touches this function.
    """
    return FilesystemObjectStorage(get_settings().storage_root)
