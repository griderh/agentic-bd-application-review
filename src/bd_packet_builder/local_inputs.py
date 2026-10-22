"""Bounded, read-only local inputs shared by developer validation commands."""

import os
import stat
from pathlib import Path


class LocalInputError(ValueError):
    """Safe local path, size, or mutation error without input contents."""


def read_local_input(root: Path, relative: Path, boundary: Path, limit: int) -> bytes:
    """Read beneath a resolved root; reject symlinks and detected concurrent changes."""
    if relative.is_absolute() or ".." in relative.parts or not relative.is_relative_to(boundary):
        raise LocalInputError(f"Input must be a relative file within {boundary.as_posix()}")
    target = root / relative
    if target.resolve() != target:
        raise LocalInputError("Local inputs must not resolve through a symlink")
    with target.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise LocalInputError("Local input must be a regular file")
        if before.st_size > limit:
            raise LocalInputError("Local input exceeds its byte limit")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    current = target.stat()
    if target.resolve() != target:
        raise LocalInputError("Local input changed to a symlink while reading")
    if (
        len(data) > limit
        or len(data) != before.st_size
        or any(
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            != (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            for info in (after, current)
        )
    ):
        raise LocalInputError("Local input changed while reading")
    return data
