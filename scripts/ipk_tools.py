"""Small reproducible IPK archive helpers used by the standalone builder."""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from pathlib import Path


SOURCE_DATE_EPOCH = 1_700_000_000
EXECUTABLES = {
    "etc/init.d/aquadx",
    "usr/libexec/aquadx-ctl",
    "usr/libexec/aquadx-service",
}


def payload_mode(relative: str) -> int:
    if relative in EXECUTABLES or relative.startswith("usr/lib/aquadx/jre/bin/"):
        return 0o755
    if relative.endswith("/lib/jexec") or relative.endswith("/lib/jspawnhelper"):
        return 0o755
    return 0o644


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_size_kib(root: Path) -> int:
    return (sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) + 1023) // 1024


def add_tree(archive: tarfile.TarFile, root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        info = archive.gettarinfo(str(path), arcname=f"./{relative}")
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mtime = SOURCE_DATE_EPOCH
        if path.is_dir():
            info.mode = 0o755
            archive.addfile(info)
        elif path.is_file():
            info.mode = payload_mode(relative)
            with path.open("rb") as stream:
                archive.addfile(info, stream)
        else:
            raise RuntimeError(f"Unsupported payload entry: {path}")


def make_tar_gz_from_tree(root: Path) -> bytes:
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=SOURCE_DATE_EPOCH) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            add_tree(archive, root)
    return raw.getvalue()


def make_control_tar(control: str, conffiles: str, postinst: str, prerm: str) -> bytes:
    members = {
        "./control": (control.encode(), 0o644),
        "./conffiles": (conffiles.encode(), 0o644),
        "./postinst": (postinst.encode(), 0o755),
        "./prerm": (prerm.encode(), 0o755),
    }
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=SOURCE_DATE_EPOCH) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, (content, mode) in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = mode
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = SOURCE_DATE_EPOCH
                archive.addfile(info, io.BytesIO(content))
    return raw.getvalue()


def make_outer_ipk(data_tar: bytes, control_tar: bytes) -> bytes:
    members = {
        "./debian-binary": b"2.0\n",
        "./data.tar.gz": data_tar,
        "./control.tar.gz": control_tar,
    }
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=SOURCE_DATE_EPOCH) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as archive:
            for name, content in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = SOURCE_DATE_EPOCH
                archive.addfile(info, io.BytesIO(content))
    return raw.getvalue()
