from __future__ import annotations

import hashlib
import ctypes
import errno
import os
from pathlib import Path
import re
import sys
import tempfile


def atomic_rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically rename while refusing an existing destination.

    Fail closed on platforms without a no-replace rename primitive.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(source_bytes, destination_bytes, 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, source_bytes, -100, destination_bytes, 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise RuntimeError("this platform lacks an atomic no-replace rename primitive")
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError(error, os.strerror(error), destination)
        raise OSError(error, os.strerror(error), destination)


_VERSION_RE = re.compile(r"^(?P<base>.+)-v(?P<version>0|[1-9][0-9]*)$")


def require_tex_file(path: Path) -> Path:
    path = path.expanduser().absolute()
    if path.suffix.lower() != ".tex":
        raise ValueError(f"expected a .tex file: {path}")
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise ValueError(f"not a regular file: {path}")
    return path


def next_version_path(source: Path) -> tuple[Path, int, int]:
    """Return (destination, input version, output version).

    Only a terminal ``-vN`` in the stem is a version. An unversioned input is
    version zero. Leading-zero suffixes are rejected rather than guessed.
    """
    source = require_tex_file(source)
    stem = source.stem
    ambiguous = re.search(r"-v0[0-9]+$", stem)
    if ambiguous:
        raise ValueError(f"ambiguous leading-zero version suffix: {source.name}")
    match = _VERSION_RE.fullmatch(stem)
    if match:
        base = match.group("base")
        current = int(match.group("version"))
    else:
        base = stem
        current = 0
    following = current + 1
    return source.with_name(f"{base}-v{following}{source.suffix}"), current, following


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exclusive_copy(source: Path, destination: Path) -> dict[str, int | str]:
    """Copy one coherent source snapshot and atomically publish without overwrite.

    Data and metadata are applied through owned file descriptors. The final no-replace
    rename is atomic and fails if the destination appears concurrently.
    """
    source = require_tex_file(source)
    destination = destination.expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination_fd, staging_name = tempfile.mkstemp(
        prefix=f".{destination.name}.staging-", dir=destination.parent,
    )
    staging_file = Path(staging_name)
    source_fd = -1
    digest = hashlib.sha256()
    try:
        source_fd = os.open(source, os.O_RDONLY)
        before = os.fstat(source_fd)
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                view = view[written:]
        after = os.fstat(source_fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in fields):
            raise RuntimeError("source changed while snapshotting")
        path_stat = os.stat(source, follow_symlinks=True)
        if any(getattr(before, field) != getattr(path_stat, field) for field in fields):
            raise RuntimeError("source path changed while snapshotting")
        os.fchmod(destination_fd, before.st_mode & 0o777)
        os.utime(destination_fd, ns=(before.st_atime_ns, before.st_mtime_ns))
        os.fsync(destination_fd)
        staged = os.fstat(destination_fd)
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if destination_fd >= 0:
            os.close(destination_fd)

    atomic_rename_noreplace(staging_file, destination)
    published = os.stat(destination, follow_symlinks=False)
    if (published.st_dev, published.st_ino) != (staged.st_dev, staged.st_ino):
        raise RuntimeError("published destination does not match the owned snapshot")
    return {
        "sha256": digest.hexdigest(),
        "source_dev": before.st_dev,
        "source_ino": before.st_ino,
        "destination_dev": published.st_dev,
        "destination_ino": published.st_ino,
        "size": published.st_size,
    }


def same_file_if_present(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except FileNotFoundError:
        return False
