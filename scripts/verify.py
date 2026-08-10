#!/usr/bin/env python3
"""Validate the Docker-free AquaDX IPK payload and metadata."""

from __future__ import annotations

import hashlib
import io
import argparse
import re
import tarfile
from pathlib import Path

from verify_tools import read_outer_ipk, tar_bytes, tar_members


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a luci-app-aquadx-allnet IPK.")
    parser.add_argument("--ipk", type=Path, required=True)
    parser.add_argument("--jar", type=Path)
    args = parser.parse_args()
    ipk = args.ipk.resolve()
    include_runtime = "_full_all.ipk" in ipk.name
    outer = read_outer_ipk(ipk)
    assert list(outer) == ["debian-binary", "data.tar.gz", "control.tar.gz"]
    assert outer["debian-binary"] == b"2.0\n"
    control = tar_bytes(outer["control.tar.gz"], "control").decode()
    assert "Package: luci-app-aquadx-allnet\n" in control
    assert "Version: 1.0.0-1\n" in control
    assert "Architecture: all\n" in control
    dependency_line = next(line for line in control.splitlines() if line.startswith("Depends:"))
    assert dependency_line == "Depends: luci-base"
    assert "docker" not in dependency_line.lower()

    members = tar_members(outer["data.tar.gz"])
    required = {
        "etc/config/aquadx",
        "etc/init.d/aquadx",
        "etc/mysql/conf.d/99-aquadx.cnf",
        "usr/lib/aquadx/AquaDX.jar",
        "usr/share/aquadx/deps/mariadb-server_11.4.8-r2_x86_64.ipk",
        "usr/share/aquadx/deps/mariadb-client_11.4.8-r2_x86_64.ipk",
        "usr/share/aquadx/deps/mariadb-client-extra_11.4.8-r2_x86_64.ipk",
        "usr/libexec/aquadx-service",
        "usr/share/aquadx/web/index.html",
        "www/luci-static/resources/view/aquadx/overview.js",
    }
    missing = sorted(required.difference(members))
    assert not missing, f"missing entries: {missing}"
    if include_runtime:
        assert "usr/lib/aquadx/jre/bin/java" in members
        assert "usr/lib/aquadx/jre/lib/jspawnhelper" in members
    else:
        assert not any(name.startswith("usr/lib/aquadx/jre/") for name in members)
    for name in (
        "etc/init.d/aquadx",
        "usr/libexec/aquadx-ctl",
        "usr/libexec/aquadx-service",
    ):
        assert members[name].mode & 0o111, f"{name} is not executable"
    if include_runtime:
        for name in ("usr/lib/aquadx/jre/bin/java", "usr/lib/aquadx/jre/lib/jspawnhelper"):
            assert members[name].mode & 0o111, f"{name} is not executable"

    service = tar_bytes(outer["data.tar.gz"], "usr/libexec/aquadx-service").decode()
    view = tar_bytes(outer["data.tar.gz"], "www/luci-static/resources/view/aquadx/overview.js").decode()
    uci_config = tar_bytes(outer["data.tar.gz"], "etc/config/aquadx").decode()
    assert "docker " not in service.lower()
    assert "ld-musl-x86_64.so.1" in service
    assert "opkg install /usr/share/aquadx/deps/*.ipk" in service
    assert "file:/usr/share/aquadx/web/" in service
    assert 'paths.mai2-plays="$DATA_DIR/data/' in service
    assert "运行日志" in view
    assert "启动进度" in view
    assert "ALL.Net Server 已停止" in view
    assert "ALL.Net Server 运行中" in view
    assert "应用修改" in view
    assert "开机自动启动" in view
    assert "基于 AquaDX 的本地 ALL.Net 游戏服务器" in view
    assert "打开 WebUI" in view
    assert "启动服务" in view and "关闭服务" in view
    assert "查看服务器日志" not in view
    assert "例如 192.168.0.101" not in view
    assert "这里直接显示 AquaDX 写入的" not in view
    assert "机台默认访问 ALL.Net 的 TCP 80，如 80 端口被占用，可指定机台 IP 进行端口转发" in view
    assert "新增机台" in view and "备注" in view
    assert "修改已应用" in view
    assert "导出数据库文件" in view and "导入数据库文件" in view
    assert "aquadx-database-import.upload" in view
    assert "aquadx-machine-number" in view
    assert "aquadx-machine-enabled" in view
    assert "apply-settings-v3" in view
    assert "background-color:#f0ad4e" in view
    assert "'placeholder': '备注'" in view
    assert "margin-left:48px" in view
    assert "设置已保存" not in view
    assert "}, '保存')" not in view
    assert "服务器地址" in view and "自定义服务器地址" in view
    assert "启用自定义服务器地址后必须输入地址" in view
    assert "请输入有效的服务器 IPv4 地址或主机名" in view
    assert "log-all" in view
    ctl = tar_bytes(outer["data.tar.gz"], "usr/libexec/aquadx-ctl").decode()
    assert "AquaDX.log" in ctl
    assert "progress)" in ctl and "launcher.log" in ctl
    assert "set-game-ip" in ctl
    assert "apply-settings" in ctl
    assert "apply-settings-v2" in ctl
    assert "apply-settings-v3" in ctl
    assert "server-address" in ctl
    assert "list-clients" in ctl
    assert "apply_settings" in service
    assert "apply_settings_v2" in service
    assert "apply_settings_v3" in service
    assert "custom_server_address_enabled" in service
    assert '--allnet.server.host="$effective_server_address"' in service
    assert "schedule_settings_restart" in service
    assert "option custom_server_address_enabled '0'" in uci_config
    assert "option custom_server_address ''" in uci_config
    assert 'aquadx.main.game_client="$client_enabled|$client_ip|$client_remark"' in service
    assert "parse_game_client" in service
    assert 'client_enabled="${client_entry%%|*}"' in service
    assert "config_list_foreach main game_client" in service
    assert "uci -q add_list aquadx.main.game_client" in service
    assert "mysqldump" in service
    assert "export_database_worker" in service and "import_database_worker" in service
    assert "pre-import-" in service
    assert 'log "Starting ALL.Net Server"' in service
    assert 'log "安装 MariaDB 及 Java Runtime"' in service
    assert 'log "启动 Java  (-Xms$JAVA_XMS -Xmx$JAVA_XMX)"' in service
    assert 'log "ALL.Net Server 已启动 (http://$(uci -q get network.lan.ipaddr):$FRONTEND_PORT/)"' in service
    assert 'log "等待应用超时"' in service
    assert "configure_game_redirect" in service
    assert "tcp dport 80" in service
    offline_packages = [name for name in members if name.startswith("usr/share/aquadx/deps/") and name.endswith(".ipk")]
    assert len(offline_packages) >= 10, f"too few offline packages: {len(offline_packages)}"

    nested_controls = {}
    with tarfile.open(fileobj=io.BytesIO(outer["data.tar.gz"]), mode="r:gz") as data_archive:
        for name in offline_packages:
            item = data_archive.getmember("./" + name)
            nested_file = data_archive.extractfile(item)
            assert nested_file is not None
            with tarfile.open(fileobj=io.BytesIO(nested_file.read()), mode="r:gz") as nested_outer:
                control_member = nested_outer.getmember("./control.tar.gz")
                control_file = nested_outer.extractfile(control_member)
                assert control_file is not None
                with tarfile.open(fileobj=io.BytesIO(control_file.read()), mode="r:gz") as control_archive:
                    package_control = control_archive.extractfile("./control")
                    assert package_control is not None
                    fields = {}
                    for line in package_control.read().decode().splitlines():
                        if ": " in line:
                            key, value = line.split(": ", 1)
                            fields[key] = value
                    nested_controls[fields["Package"]] = fields

    system_provided = {"libc", "kernel", "libpthread", "librt", "busybox"}
    available = set(nested_controls).union(system_provided)
    unresolved = []
    for package, fields in nested_controls.items():
        for expression in fields.get("Depends", "").split(","):
            alternatives = {
                re.sub(r"\s*\(.*?\)", "", item).strip()
                for item in expression.split("|")
            }
            alternatives.discard("")
            if alternatives and not alternatives.intersection(available):
                unresolved.append((package, sorted(alternatives)))
    assert not unresolved, f"unresolved nested dependencies: {unresolved}"
    assert "poll.add" in view and "readLog" in view
    jar = tar_bytes(outer["data.tar.gz"], "usr/lib/aquadx/AquaDX.jar")
    if args.jar:
        assert digest(jar) == digest(args.jar.resolve().read_bytes())
    print(f"Verified native IPK: {ipk}")
    print(f"Payload entries: {len(members):,}")
    print(f"Offline dependency closure: {len(nested_controls)} packages, complete")
    print(f"JAR SHA256: {digest(jar)}")


if __name__ == "__main__":
    main()
