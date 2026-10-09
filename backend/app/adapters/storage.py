"""StorageProvider interface + the local-filesystem implementation.

Services never call `open()` — they hand bytes to a StorageProvider and
persist the returned path (backend.md). Phase 2 ships the local-disk
provider that writes onto the mounted upload volume; a checksum is the
caller's job (records service), not the store's.
"""

import asyncio
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path


class StorageProvider(ABC):
    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str) -> str:
        """Store bytes under `key`; return the storage path to persist."""

    @abstractmethod
    async def get(self, path: str) -> bytes: ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Remove a stored file when the database transaction fails."""


class LocalStorageProvider(StorageProvider):
    """Writes under a single base directory (the compose upload volume).
    `key` is treated as a relative path; parent dirs are created."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        dest = self._safe_path(str(self._base / key))

        def _write() -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary: str | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as upload:
                    temporary = upload.name
                    upload.write(data)
                    upload.flush()
                    os.fsync(upload.fileno())
                os.replace(temporary, dest)
            finally:
                if temporary is not None:
                    Path(temporary).unlink(missing_ok=True)

        await asyncio.to_thread(_write)
        return str(dest)

    async def get(self, path: str) -> bytes:
        return await asyncio.to_thread(self._safe_path(path).read_bytes)

    def _safe_path(self, path: str) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self._base.resolve()):
            raise ValueError("Storage path escapes upload directory")
        return resolved

    async def delete(self, path: str) -> None:
        await asyncio.to_thread(self._safe_path(path).unlink, missing_ok=True)
