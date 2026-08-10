#!/usr/bin/env python3
"""Build the Docker-free AquaDX IPK for iStoreOS 24.10 x86_64."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import shutil
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

from ipk_tools import (
    make_control_tar,
    make_outer_ipk,
    make_tar_gz_from_tree,
    installed_size_kib,
    sha256,
)


PACKAGE = "luci-app-aquadx-allnet"
VERSION = "1.0.0-1"
JRE_NAME = "OpenJDK25U-jre_x64_alpine-linux_hotspot_25.0.4_7.tar.gz"
JRE_URL = (
    "https://github.com/adoptium/temurin25-binaries/releases/download/"
    "jdk-25.0.4%2B7/" + JRE_NAME
)
JRE_SHA256 = "4a641bfa74e961efd9cc6dbfb6eccf0bec13014904433f00eb33df84c393318f"
OPENWRT_RELEASE = "24.10.7"
OPENWRT_ARCH = "x86_64"
ESSENTIAL_PROVIDED = {"libc", "kernel", "libpthread", "librt", "busybox"}


def download_file(url: str, destination: Path, attempts: int = 4) -> None:
    temporary = destination.with_suffix(destination.suffix + ".download")
    for attempt in range(1, attempts + 1):
        temporary.unlink(missing_ok=True)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "AquaDX-Packager/1.0"})
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            temporary.replace(destination)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            print(f"Download failed; retrying ({attempt}/{attempts})...")
            time.sleep(min(2**attempt, 8))


def download_jre(cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / JRE_NAME
    if archive.exists() and sha256(archive) == JRE_SHA256:
        return archive
    archive.unlink(missing_ok=True)
    print(f"Downloading {JRE_NAME}...")
    download_file(JRE_URL, archive)
    actual = sha256(archive)
    if actual != JRE_SHA256:
        archive.unlink(missing_ok=True)
        raise RuntimeError(f"JRE checksum mismatch: {actual}")
    return archive


def extract_jre(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        roots = {PurePosixPath(member.name).parts[0] for member in members if member.name}
        if len(roots) != 1:
            raise RuntimeError(f"Unexpected JRE archive roots: {roots}")
        root = next(iter(roots))
        for member in members:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != root or len(parts) == 1:
                continue
            relative = PurePosixPath(*parts[1:])
            if ".." in relative.parts:
                raise RuntimeError(f"Unsafe JRE archive path: {member.name}")
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"Unsupported JRE archive entry: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def read_package_index(feed_url: str) -> dict[str, dict[str, str]]:
    request = urllib.request.Request(feed_url + "/Packages.gz", headers={"User-Agent": "AquaDX-Packager/1.0"})
    text = gzip.decompress(urllib.request.urlopen(request, timeout=120).read()).decode()
    result: dict[str, dict[str, str]] = {}
    for block in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ": " in line:
                key, value = line.split(": ", 1)
                fields[key] = value
        if "Package" in fields:
            fields["_feed_url"] = feed_url
            result[fields["Package"]] = fields
    return result


def dependency_names(value: str) -> list[str]:
    result = []
    for expression in value.split(","):
        alternatives = []
        for candidate in expression.split("|"):
            name = re.sub(r"\s*\(.*?\)", "", candidate).strip()
            if name:
                alternatives.append(name)
        if alternatives:
            result.append(alternatives[0])
    return result


def download_offline_dependencies(cache: Path) -> list[Path]:
    root = f"https://downloads.openwrt.org/releases/{OPENWRT_RELEASE}/packages/{OPENWRT_ARCH}"
    database: dict[str, dict[str, str]] = {}
    feed_urls = [
        f"https://downloads.openwrt.org/releases/{OPENWRT_RELEASE}/targets/x86/64/packages",
        f"{root}/base",
        f"{root}/packages",
    ]
    for feed_url in feed_urls:
        database.update(read_package_index(feed_url))

    selected: set[str] = set()
    pending = ["mariadb-server", "mariadb-client", "mariadb-client-extra"]
    while pending:
        name = pending.pop(0)
        if name in selected or name in ESSENTIAL_PROVIDED:
            continue
        if name not in database:
            raise RuntimeError(f"Dependency {name!r} is absent from OpenWrt {OPENWRT_RELEASE} indexes")
        selected.add(name)
        pending.extend(dependency_names(database[name].get("Depends", "")))

    cache.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for name in sorted(selected):
        metadata = database[name]
        filename = metadata["Filename"]
        destination = cache / filename
        expected = metadata["SHA256sum"]
        if not destination.exists() or sha256(destination) != expected:
            destination.unlink(missing_ok=True)
            url = metadata["_feed_url"] + "/" + filename
            print(f"Downloading offline dependency {filename}...")
            download_file(url, destination)
        if sha256(destination) != expected:
            raise RuntimeError(f"Checksum mismatch for {filename}")
        downloaded.append(destination)
    print(f"Bundling {len(downloaded)} offline OpenWrt dependency packages")
    return downloaded


def build(
    rootfs: Path,
    license_file: Path,
    output_dir: Path,
    cache: Path,
    variant: str,
    jar: Path,
    frontend: Path,
    geoip: Path,
) -> Path:
    for required in (rootfs, jar, frontend / "index.html", geoip, license_file):
        if not required.exists():
            raise FileNotFoundError(required)

    include_runtime = variant == "full"
    jre_archive = download_jre(cache) if include_runtime else None
    dependency_packages = download_offline_dependencies(cache / "openwrt-24.10.7")
    with tempfile.TemporaryDirectory(prefix="aquadx-native-ipk-") as temp_name:
        data_root = Path(temp_name) / "data"
        shutil.copytree(rootfs, data_root)

        (data_root / "usr/lib/aquadx").mkdir(parents=True, exist_ok=True)
        shutil.copy2(jar, data_root / "usr/lib/aquadx/AquaDX.jar")
        if jre_archive is not None:
            extract_jre(jre_archive, data_root / "usr/lib/aquadx/jre")
        dependency_root = data_root / "usr/share/aquadx/deps"
        dependency_root.mkdir(parents=True, exist_ok=True)
        for dependency in dependency_packages:
            shutil.copy2(dependency, dependency_root / dependency.name)
        web_root = data_root / "usr/share/aquadx/web"
        if web_root.exists():
            shutil.rmtree(web_root)
        shutil.copytree(frontend, web_root)
        shutil.copy2(geoip, data_root / "usr/share/aquadx/GeoLite2-Country.mmdb")
        shutil.copy2(license_file, data_root / "usr/share/aquadx/LICENSE")

        size = installed_size_kib(data_root)
        variant_description = "with bundled Temurin JRE" if include_runtime else "without bundled JRE"
        control = (
            f"Package: {PACKAGE}\n"
            f"Version: {VERSION}\n"
            "Depends: luci-base\n"
            "Architecture: all\n"
            f"Installed-Size: {size}\n"
            "Section: luci\n"
            "Priority: optional\n"
            "Maintainer: AquaDX Portable maintainers\n"
            "License: CC-BY-NC-SA-4.0\n"
            f"Description: Docker-free AquaDX for iStoreOS 24.10.7 x86_64, {variant_description}.\n"
        )
        conffiles = (
            "/etc/config/aquadx\n"
            "/etc/aquadx/application.properties\n"
            "/etc/mysql/conf.d/99-aquadx.cnf\n"
            "/usr/share/aquadx/web/runtime-config.js\n"
        )
        postinst = """#!/bin/sh
[ -n "$IPKG_INSTROOT" ] || {
    /etc/init.d/aquadx stop >/dev/null 2>&1
    if command -v docker >/dev/null 2>&1; then
        docker rm -f aquadx-app aquadx-db >/dev/null 2>&1
    fi
    if [ -s /var/run/aquadx-start.pid ]; then
        kill "$(cat /var/run/aquadx-start.pid)" >/dev/null 2>&1
    fi
    rm -f /var/run/aquadx-start.pid /var/run/aquadx-stop-requested
    rm -rf /var/lock/aquadx-start.lock
    chmod 0755 /etc/init.d/aquadx /usr/libexec/aquadx-service /usr/libexec/aquadx-ctl
    if [ -d /usr/lib/aquadx/jre ]; then
        chmod 0755 /usr/lib/aquadx/jre/bin/* /usr/lib/aquadx/jre/lib/jexec /usr/lib/aquadx/jre/lib/jspawnhelper 2>/dev/null
        ln -sf /lib/ld-musl-x86_64.so.1 /usr/lib/aquadx/jre/lib/libc.musl-x86_64.so.1
    fi
    mkdir -p /opt/aquadx/data /opt/aquadx/logs
    [ -f /opt/aquadx/data/GeoLite2-Country.mmdb ] || \\
        cp /usr/share/aquadx/GeoLite2-Country.mmdb /opt/aquadx/data/GeoLite2-Country.mmdb
    rm -f /tmp/luci-indexcache /tmp/luci-modulecache/* 2>/dev/null
}
exit 0
"""
        prerm = """#!/bin/sh
[ -n "$IPKG_INSTROOT" ] || [ "$PKG_UPGRADE" = "1" ] || {
    /etc/init.d/aquadx stop >/dev/null 2>&1
    /etc/init.d/aquadx disable >/dev/null 2>&1
}
exit 0
"""
        data_tar = make_tar_gz_from_tree(data_root)
        control_tar = make_control_tar(control, conffiles, postinst, prerm)
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{PACKAGE}_{VERSION}_{variant}_all.ipk"
        output.write_bytes(make_outer_ipk(data_tar, control_tar))

    digest = sha256(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii", newline="\n"
    )
    print(f"Built: {output}")
    print(f"Size: {output.stat().st_size:,} bytes")
    print(f"SHA256: {digest}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build luci-app-aquadx-allnet with explicit input paths.")
    parser.add_argument("--rootfs", type=Path, required=True)
    parser.add_argument("--license", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--variant", choices=("noruntime", "full"), required=True)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--geoip", type=Path, required=True)
    args = parser.parse_args()
    build(
        args.rootfs.resolve(),
        args.license.resolve(),
        args.output.resolve(),
        args.cache.resolve(),
        args.variant,
        args.jar.resolve(),
        args.frontend.resolve(),
        args.geoip.resolve(),
    )


if __name__ == "__main__":
    main()
