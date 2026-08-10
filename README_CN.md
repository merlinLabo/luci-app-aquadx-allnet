# luci-app-aquadx-allnet

[English](README_EN.md) | 简体中文

一个适用于 OpenWrt 的本地 ALL.Net 游戏服务器，并提供 LuCI 管理页面。基于 [AquaDX](https://github.com/MewoLab/AquaDX)。

## 兼容性

- OpenWrt 24.10+
- x86_64
- 至少配备 2 GB RAM 和 2 GB 可用存储空间

## 功能

AquaDX 以原生 Java 进程运行，MariaDB 使用 OpenWrt 原生软件包。

- 在“服务”菜单下提供独立的 ALL.Net Server 页面
- 导入和导出 AquaDX 数据库
- 配置多台机台、启用状态以及 TCP 80 端口转发
- 自定义 ALL.Net 服务器地址

## Release 文件

| 文件 | 用途 |
| --- | --- |
| `luci-app-aquadx-allnet_noruntime_all.ipk` | 不含运行时的安装包，需要单独安装 JRE |
| `luci-app-aquadx-allnet_1.0.0-1_full_all.ipk` | 内置 Temurin JRE，可以直接安装 |
| `luci-app-aquadx-allnet-1.0.0-source.zip` | 源代码 |

两个 IPK 均包含 AquaDX JAR、WebUI、GeoIP 数据库以及 MariaDB 的 OpenWrt 离线依赖。

## 安装不含运行时的版本

下载以下两个文件，然后将其上传到路由器的 `/tmp`：

1. `luci-app-aquadx-allnet_1.0.0-1_noruntime_all.ipk`
2. `OpenJDK25U-jre_x64_alpine-linux_hotspot_<version>.tar.gz`
* JRE 需单独下载 [Temurin JRE](https://github.com/adoptium/temurin25-binaries/releases/download/)

通过 SSH 连接路由器并执行：

```sh
opkg install /tmp/luci-app-aquadx-allnet_1.0.0-1_noruntime_all.ipk

mkdir -p /usr/lib/aquadx/jre
tar -xzf /tmp/OpenJDK25U-jre_x64_alpine-linux_hotspot_<version>.tar.gz \
  -C /usr/lib/aquadx/jre --strip-components=1
chmod 0755 /usr/lib/aquadx/jre/bin/*
chmod 0755 /usr/lib/aquadx/jre/lib/jexec /usr/lib/aquadx/jre/lib/jspawnhelper
ln -sf /lib/ld-musl-x86_64.so.1 \
  /usr/lib/aquadx/jre/lib/libc.musl-x86_64.so.1

/usr/lib/aquadx/jre/bin/java -version
```

如果 `tar` 不支持 `--strip-components`，请先将压缩包解压到一个临时目录，然后把压缩包最上层目录中的所有文件复制到 `/usr/lib/aquadx/jre`。

刷新 LuCI：

```sh
rm -f /tmp/luci-indexcache
rm -rf /tmp/luci-modulecache/*
/etc/init.d/rpcd restart
/etc/init.d/uhttpd restart
```

重新登录路由器，然后打开“服务 → ALL.Net Server”进行配置并启动服务。首次启动时，安装包会安装内置的 MariaDB 依赖，展开“运行日志”可查看进度。

## 安装完整版本

完整版本已含 JRE，直接上传 ipk 包执行安装即可：

```sh
opkg install /tmp/luci-app-aquadx-allnet_1.0.0-1_full_all.ipk
```

安装后刷新 LuCI，然后打开“服务 → ALL.Net Server”即可。

## 默认端口和数据目录

- WebUI / ALL.Net HTTP：`http://路由器地址:8088/`
- AimeDB：`路由器地址:22345`
- Billing：`路由器地址:8443`
- MariaDB：仅监听 `127.0.0.1:3369`
- 持久化数据：`/opt/aquadx/data`
- 运行日志：`/opt/aquadx/logs`
- AquaDX 配置：`/etc/aquadx/application.properties`
- LuCI/UCI 配置：`/etc/config/aquadx`

机台默认通过 TCP 80 端口访问 ALL.Net。如果 LuCI 已经占用 80 端口，请在页面中添加机台 IP 地址，会为已启用的机台创建到 AquaDX 8088 端口的转发规则。

“自定义服务器地址”字段只接受 IP 地址或主机名，例如 `192.168.1.1` 或 `host.example.com`。请勿填写协议、端口或路径。

## 源码目录结构

| 目录 | 内容 |
| --- | --- |
| `rootfs/` | 写入 IPK 根文件系统的全部 LuCI、配置和服务文件 |
| `scripts/` | IPK 构建器、校验器和归档辅助代码 |
| `ui-text/` | LuCI 页面文字和启动进度文字的 JSON 清单 |

`rootfs/` 下的目录与最终安装路径一致：

| 源码目录 | 安装路径和用途 |
| --- | --- |
| `rootfs/etc/aquadx/` | `/etc/aquadx/`，AquaDX Spring 配置 |
| `rootfs/etc/config/` | `/etc/config/`，UCI 配置 |
| `rootfs/etc/init.d/` | `/etc/init.d/`，rc.common 服务入口 |
| `rootfs/etc/mysql/conf.d/` | `/etc/mysql/conf.d/`，本地 MariaDB 配置 |
| `rootfs/usr/libexec/` | `/usr/libexec/`，服务控制脚本 |
| `rootfs/usr/share/luci/menu.d/` | LuCI“服务”菜单定义 |
| `rootfs/usr/share/rpcd/acl.d/` | LuCI RPC 权限定义 |
| `rootfs/www/luci-static/resources/view/aquadx/` | ALL.Net Server LuCI 页面 |

## 安全说明

默认配置仅适用于局域网，请勿将 WebUI、MariaDB、AimeDB 或 Billing 端口直接暴露到公网。

## 许可证和上游项目

本项目基于 AquaDX，遵循根目录中的 `LICENSE`（CC BY-NC-SA 4.0）。
Temurin、MariaDB、OpenWrt 软件包和 GeoLite2 数据库分别受其各自的第三方许可证约束。
