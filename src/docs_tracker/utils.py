"""
Utility functions for Docs Tracker.

This module contains helper functions used across the project:
 - list immediate subfolders and files
 - compute SHA256 hash of a file
 - atomic write to avoid partial writes
 - safe retrieval of a filename stem

These helpers are designed to be small and stateless, making the core
logic in other modules easier to test.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Iterator

def list_immediate_subfolders(root: Path) -> list[Path]:
    """Return a list of all immediate subdirectories of ``root``."""
    return [p for p in root.iterdir() if p.is_dir()]


def list_files(folder: Path) -> Iterator[Path]:
    """Yield all files directly inside ``folder`` (non-recursive)."""
    for p in folder.iterdir():
        if p.is_file():
            yield p


def sha256_file(path: Path) -> str:
    """Compute the SHA256 checksum of a file and return it as a hex string."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    """Atomically write ``data`` to ``path``.

    The data is first written to a temporary file in the same directory
    and then moved to the target path. This ensures that other processes
    never see a partially written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=str(path.parent)) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    shutil.move(str(tmp_path), path)


def safe_stem(name: str) -> str:
    """Return the stem of a filename without its extension."""
    return Path(name).stem