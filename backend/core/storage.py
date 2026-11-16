"""File storage for generated and uploaded media.

Files are never served from a public directory: they are read through API
routes that go through the same access check as everything else.

Only local disk is implemented. ``Storage`` is the seam for an S3-compatible
backend; processing needs local paths, so that backend will have to download
to a temporary file in ``path()``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def save(self, source: Path, key: str) -> int: ...
    def path(self, key: str) -> Path: ...
    def copy(self, key: str, new_key: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        target = (self._root / key).resolve()
        if not target.is_relative_to(self._root):  # keys never come from users, but be strict
            raise ValueError("Storage key escapes the storage root.")
        return target

    def save(self, source: Path, key: str) -> int:
        """Copy ``source`` into storage; return its size in bytes."""
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target.stat().st_size

    def copy(self, key: str, new_key: str) -> None:
        self.save(self.path(key), new_key)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()
