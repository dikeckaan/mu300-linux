# Optional Passwall2 extra

[Chinese documentation](../../docs/passwall2-extra.zh-CN.md)

Passwall2's LuCI UI, configuration and service stay independent of the MU300 VPN
module. Compatible Xray and sing-box programs can be shared with it; installing
this extra does not turn on the MU300 VPN service. Nothing is added to the base
images or to the desktop installer's defaults.

This targets OpenWrt 25.12.x, `aarch64_generic`, and the native MU300 kernel
capabilities checked by the installer. It uses the custom-extra interface, so it
is installed explicitly from a file and is not automatically published or updated
by `mu300-update`.

## Build and install

On Linux, with Python 3.11+, host apk-tools v3 (`extract` and `mkpkg`) and the
target native kernel's configuration:

```sh
cd tools/passwall2-extra
python3 fetch.py cache
python3 build.py --cache cache --apk /path/to/apk.static \
    --config /path/to/kernel.config --output dist/passwall2.tar.gz
python3 build.py --cache cache --apk /path/to/apk.static \
    --config /path/to/kernel.config --engines bundled \
    --output dist/passwall2-full.tar.gz
```

The default **shared** build carries the app, translations and offline userspace
dependencies, but no core binaries or core APKs. A compatible installed core is
required. The **bundled** build adds one copy of each fallback binary in
`extra/passwall2/engines`, extracted from the pinned official APKs. It does not
also retain those APKs and expand a second copy into the system.

Copy the chosen file and `SHA256SUMS` to the device:

```sh
mu300-extra install passwall2 --from /tmp/passwall2.tar.gz
# or: mu300-extra install passwall2 --from /tmp/passwall2-full.tar.gz
mu300-passwall2 cores
mu300-passwall2 status
```

The UI is under **Services > Passwall2**. Fresh installs stay disabled until a
node is configured; existing enabled/disabled state is retained. `check` performs
core/kernel validation and an offline dependency simulation. `install` retries a
deferred installation. Replacing basic dnsmasq with dnsmasq-full can briefly
restart DNS/DHCP.

`packages.lock.json` records the official release asset digests and the OpenWrt
package hashes checked against signed indices. The downloader uses verified
HTTPS, direct connections and TLS 1.2. The archive has a manifest covering every
other file. Package payloads, private device files and caches are not tracked in
this repository. Upstream APKs retain their own licenses.

## Core ownership

Resolution prefers an existing custom path, then `extra/vpn-xray` or
`extra/vpn-singbox`, legacy `extra/vpn/bin`, system binaries, and finally the
private fallback when present. Current validated interfaces are **Xray 26.10.21**
and **sing-box 1.14.4**, with QUIC/uTLS/WireGuard tags checked for sing-box. Other
versions are not assumed compatible. A missing or changed provider is checked
again at launch; the installer does not silently fetch a replacement.

Passwall2's two core paths point at this extra's dispatchers. Original custom
paths are retained in its `global_app` section. Nodes, subscriptions and rules
remain Passwall2's own configuration. There are no global Xray/sing-box links,
no changes to another module's binaries, and no automatic deletion of existing
packages. Backups of the pre-install configuration stay private on the device.

The pinned Passwall2 API gets a hash-checked guard against its own updater
overwriting a dispatcher or an author-owned engine. Update a shared core through
its original module/package; update the private fallback with the extra. Unknown
API modifications are not overwritten by that guard.

Removing the extra first detaches a running OpenWrt to usable external cores.
If its only cores are this extra's private fallbacks, removal is refused until
external cores are provided or the app is removed. An inactive OpenWrt still
referencing the extra must be booted and detached first. This needs the
`mu300-extra` unlink-failure handling in this change; older managers can ignore a
failed unlink hook and must be updated before relying on this protection.

```sh
mu300-passwall2 remove
mu300-extra remove passwall2
```

Shared DNS/core dependencies are left installed for other consumers.

## Languages and validation

English source strings and official Simplified/Traditional Chinese, Russian and
Persian translations are included by default; `--languages en,zh-cn` builds a
smaller selection. The current LuCI language and unrelated pending LuCI changes
are retained. CLI status messages support Chinese/English; external tools keep
their own messages.

Tests use opaque APK fixtures for archive/layout checks and the real extra
manager for unpacking and removal. Core-selection tests exercise custom, split,
legacy, fallback and incompatible versions. Manual ARM64 OpenWrt 25.12.6 tests
ran real APK installation/postinsts, both core binaries, Lua updater guards,
configuration preservation and full-to-shared migration under PRoot/QEMU.
Kernel probes and service activation were fixtures, with native UCI replacing
the unavailable ubus transport in the Lua test. This extra has not yet been
installed on a physical router; no hardware or proxy-connectivity claim is made.

The PR description records measured archive sizes, separately from installed
storage. Shared-core storage depends on what is already installed; a smaller
archive is not a measurement of space freed on a device.
