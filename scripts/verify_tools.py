"""Read helpers for the gzip/tar IPK format emitted by the builder."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path


def read_outer_ipk(path: Path) -> dict[str, bytes]:
    blob = path.read_bytes()
    assert blob.startswith(b"\x1f\x8b"), "IPK outer container must be gzip"
    result: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        for item in archive.getmembers():
            name = item.name.removeprefix("./")
            extracted = archive.extractfile(item)
            assert extracted is not None, f"outer IPK entry is not a file: {name}"
            result[name] = extracted.read()
    return result


def tar_members(blob: bytes) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        return {item.name.removeprefix("./"): item for item in archive.getmembers()}


def tar_bytes(blob: bytes, name: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        item = archive.getmember("./" + name)
        extracted = archive.extractfile(item)
        assert extracted is not None
        return extracted.read()
