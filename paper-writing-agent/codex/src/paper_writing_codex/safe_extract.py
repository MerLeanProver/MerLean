from __future__ import annotations

import gzip
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tempfile
import zipfile

from .versioning import atomic_rename_noreplace


MAX_MEMBERS = 5000
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024


def _safe_relative(name: str) -> Path:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe archive member path: {name!r}")
    if ":" in pure.parts[0]:
        raise ValueError(f"unsafe archive member path: {name!r}")
    return Path(*pure.parts)


def _copy_limited(incoming, outgoing, maximum: int) -> int:
    total = 0
    while True:
        chunk = incoming.read(min(1024 * 1024, maximum - total + 1))
        if not chunk:
            return total
        total += len(chunk)
        if total > maximum:
            raise ValueError("archive member exceeds size limit")
        outgoing.write(chunk)


def _open_parent(root_fd: int, relative: Path) -> tuple[int, str]:
    parts = relative.parts
    if not parts:
        raise ValueError("empty archive member path")
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o755, dir_fd=current)
            except FileExistsError:
                pass
            following = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current,
            )
            os.close(current)
            current = following
        return current, parts[-1]
    except Exception:
        os.close(current)
        raise


def _ensure_directory(root_fd: int, relative: Path) -> None:
    parent_fd, leaf = _open_parent(root_fd, relative)
    try:
        try:
            os.mkdir(leaf, 0o755, dir_fd=parent_fd)
        except FileExistsError:
            directory_fd = os.open(
                leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd,
            )
            os.close(directory_fd)
    finally:
        os.close(parent_fd)


def _open_new_file(root_fd: int, relative: Path):
    parent_fd, leaf = _open_parent(root_fd, relative)
    try:
        descriptor = os.open(
            leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644, dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)
    return os.fdopen(descriptor, "wb")


def _extract_tar(archive: Path, staging_fd: int) -> None:
    total = 0
    with tarfile.open(archive, "r:*") as bundle:
        member_count = 0
        for member in bundle:
            member_count += 1
            if member_count > MAX_MEMBERS:
                raise ValueError("archive has too many members")
            relative = _safe_relative(member.name)
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ValueError(f"archive links/devices are forbidden: {member.name}")
            if member.isdir():
                _ensure_directory(staging_fd, relative)
                continue
            if not member.isfile():
                raise ValueError(f"unsupported archive member: {member.name}")
            if member.size > MAX_FILE_BYTES:
                raise ValueError(f"archive member too large: {member.name}")
            total += member.size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("archive exceeds total size limit")
            extracted = bundle.extractfile(member)
            if extracted is None:
                raise ValueError(f"could not read archive member: {member.name}")
            with extracted, _open_new_file(staging_fd, relative) as outgoing:
                copied = _copy_limited(extracted, outgoing, MAX_FILE_BYTES)
            if copied != member.size:
                raise ValueError(f"short archive member: {member.name}")


def _extract_zip(archive: Path, staging_fd: int) -> None:
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("archive has too many members")
        for info in infos:
            relative = _safe_relative(info.filename.rstrip("/"))
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"archive symlinks are forbidden: {info.filename}")
            if info.is_dir():
                _ensure_directory(staging_fd, relative)
                continue
            if info.file_size > MAX_FILE_BYTES:
                raise ValueError(f"archive member too large: {info.filename}")
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("archive exceeds total size limit")
            with bundle.open(info) as incoming, _open_new_file(staging_fd, relative) as outgoing:
                copied = _copy_limited(incoming, outgoing, MAX_FILE_BYTES)
            if copied != info.file_size:
                raise ValueError(f"short archive member: {info.filename}")


def safe_extract(archive: Path, destination: Path) -> None:
    archive = archive.expanduser().absolute()
    destination = destination.expanduser().absolute()
    if not archive.is_file():
        raise FileNotFoundError(archive)
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("source archive exceeds compressed-size limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    # Extract into a private sibling, then atomically rename with no replacement.
    # Failed/raced runs retain their hidden staging directory for inspection; no
    # pathname cleanup can delete a replacement created by another process.
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
    staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    staged_identity = os.fstat(staging_fd)
    try:
        if tarfile.is_tarfile(archive):
            _extract_tar(archive, staging_fd)
        elif zipfile.is_zipfile(archive):
            _extract_zip(archive, staging_fd)
        elif archive.suffix.lower() in {".gz", ".gzip"}:
            with gzip.open(archive, "rb") as incoming, _open_new_file(staging_fd, Path("main.tex")) as outgoing:
                _copy_limited(incoming, outgoing, MAX_FILE_BYTES)
        else:
            raise ValueError("unsupported source archive; expected tar, zip, or gzip")
        published_source = os.stat(staging, follow_symlinks=False)
        if not stat.S_ISDIR(published_source.st_mode) or (
            published_source.st_dev, published_source.st_ino
        ) != (staged_identity.st_dev, staged_identity.st_ino):
            raise RuntimeError("archive staging directory was replaced before publication")
        atomic_rename_noreplace(staging, destination)
    finally:
        os.close(staging_fd)
