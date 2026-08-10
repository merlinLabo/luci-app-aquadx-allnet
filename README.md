# luci-app-aquadx-allnet

English | [简体中文](README_CN.md)

An ALL.Net game server for OpenWrt and provides a Luci management page. Based on [AquaDX](https://github.com/MewoLab/AquaDX). 

## Compatibility

- OpenWrt 24.10+
- x86_64
- At least 2 GB of RAM and 2 GB of free storage are recommended

## Features

AquaDX runs as a native Java process, and MariaDB uses native OpenWrt packages.

- A dedicated ALL.Net Server page under the LuCI Services menu
- Import and export the AquaDX database
- Configure multiple cabinets, enabled states, and TCP port 80 forwarding
- Customize the ALL.Net server address advertised to cabinets

## Release Assets

| File | Purpose |
| --- | --- |
| `luci-app-aquadx-allnet_noruntime_all.ipk` | No-Runtime package. JRE must be installed separately |
| `luci-app-aquadx-allnet_1.0.0-1_full_all.ipk` | Bundles Temurin JRE and can be installed directly |
| `luci-app-aquadx-allnet-1.0.0-source.zip` | Ssource code  |

Both IPKs include the AquaDX JAR, WebUI, GeoIP database, and offline OpenWrt dependencies for MariaDB.

## Installing the No-Runtime Package

Download the following two files then upload them to `/tmp` on the router:

1. `luci-app-aquadx-allnet_1.0.0-1_noruntime_all.ipk`
2. `OpenJDK25U-jre_x64_alpine-linux_hotspot_<version>.tar.gz`
[Temurin JRE](https://github.com/adoptium/temurin25-binaries/releases/download/)

Connect to the router over SSH and run:

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

If `tar` does not support `--strip-components`, extract the archive into a temporary directory first, then copy every file from the archive’s top-level directory into `/usr/lib/aquadx/jre`.

Refresh LuCI:

```sh
rm -f /tmp/luci-indexcache
rm -rf /tmp/luci-modulecache/*
/etc/init.d/rpcd restart
/etc/init.d/uhttpd restart
```

Sign in your router again, then open Services → ALL.Net Server to configure and start the service. On the first start, the package installs the bundled MariaDB dependencies. Expand Runtime Log to monitor progress.

## Installing the Full Package

The full package does not require a separate JRE installation:

```sh
opkg install /tmp/luci-app-aquadx-allnet_1.0.0-1_full_all.ipk
```

Refresh LuCI after installation, then open Services → ALL.Net Server and start the service.

## Default Ports and Data Directories

- WebUI / ALL.Net HTTP: `http://ROUTER_ADDRESS:8088/`
- AimeDB: `ROUTER_ADDRESS:22345`
- Billing: `ROUTER_ADDRESS:8443`
- MariaDB: listens only on `127.0.0.1:3369`
- Persistent data: `/opt/aquadx/data`
- Runtime logs: `/opt/aquadx/logs`
- AquaDX configuration: `/etc/aquadx/application.properties`
- LuCI/UCI configuration: `/etc/config/aquadx`

Cabinets access ALL.Net over TCP port 80 by default. If LuCI already occupies port 80, add the cabinet IP addresses on the page. The application creates forwarding rules to AquaDX port 8088 only for enabled cabinets.

The Custom Server Address field accepts only an IP address or hostname, such as `192.168.1.1` or `host.example.com`. Do not include a protocol, port, or path.

## Source Directory Layout

| Directory | Contents |
| --- | --- |
| `rootfs/` | All LuCI, configuration, and service files written into the IPK root filesystem |
| `scripts/` | IPK builder, verifier, and archive helper code |
| `ui-text/` | JSON inventories for LuCI page text and startup-progress text |

Directories under `rootfs/` mirror their final installation paths:

| Source Directory | Installation Path and Purpose |
| --- | --- |
| `rootfs/etc/aquadx/` | `/etc/aquadx/`, AquaDX Spring configuration |
| `rootfs/etc/config/` | `/etc/config/`, UCI configuration |
| `rootfs/etc/init.d/` | `/etc/init.d/`, rc.common service entry point |
| `rootfs/etc/mysql/conf.d/` | `/etc/mysql/conf.d/`, local MariaDB configuration |
| `rootfs/usr/libexec/` | `/usr/libexec/`, service control scripts |
| `rootfs/usr/share/luci/menu.d/` | LuCI Services menu definition |
| `rootfs/usr/share/rpcd/acl.d/` | LuCI RPC permission definition |
| `rootfs/www/luci-static/resources/view/aquadx/` | ALL.Net Server LuCI page |

## Security Notes

The default configuration is intended for a trusted LAN. Do not expose the WebUI, MariaDB, AimeDB, or Billing ports directly to the Internet. 

## License

This project is based on AquaDX and follows the root `LICENSE` (CC BY-NC-SA 4.0). 
Temurin, MariaDB, OpenWrt packages, and the GeoLite2 database are governed by their respective third-party licenses.
