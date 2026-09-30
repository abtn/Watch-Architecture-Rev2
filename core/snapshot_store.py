"""Immutable local content-addressed storage for K1 Snapshots."""

import hashlib
import os
import re
import tempfile
from pathlib import Path

_REFERENCE_PATTERN = re.compile(r"^snap://sha256/([0-9a-f]{64})$")


class SnapshotIntegrityError(RuntimeError):
    """Raised when an existing content-addressed object is missing or corrupt."""


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, content: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(content).hexdigest()
        reference = f"snap://sha256/{digest}"
        destination = self._path_for_digest(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            self._verify(destination, content, digest)
            return reference, f"sha256:{digest}"

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=".snapshot-",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            try:
                os.link(temporary_path, destination)
            except FileExistsError:
                self._verify(destination, content, digest)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return reference, f"sha256:{digest}"

    def read(self, reference: str) -> bytes:
        match = _REFERENCE_PATTERN.fullmatch(reference)
        if match is None:
            raise SnapshotIntegrityError("invalid_snapshot_reference")

        digest = match.group(1)
        path = self._path_for_digest(digest)
        try:
            content = path.read_bytes()
        except FileNotFoundError as error:
            raise SnapshotIntegrityError("snapshot_missing") from error

        if hashlib.sha256(content).hexdigest() != digest:
            raise SnapshotIntegrityError("snapshot_hash_mismatch")
        return content

    def _path_for_digest(self, digest: str) -> Path:
        return self._root / "sha256" / digest[:2] / digest

    @staticmethod
    def _verify(path: Path, expected: bytes, digest: str) -> None:
        actual = path.read_bytes()
        if actual != expected or hashlib.sha256(actual).hexdigest() != digest:
            raise SnapshotIntegrityError("snapshot_content_mismatch")
