#!/bin/sh
# Maintainer: build the generic release assets used by ./install.sh (prebuilt mode) and optionally publish them.
#   tools/make-release.sh TAG             build into release/TAG and audit the contents
#   tools/make-release.sh TAG --publish   also create/update the GitHub release (gh)
# Needs docker and the kernel outputs in $MU300_KERNEL_OUT (default: out/, from kernel/build-all.sh).
# The assets must never contain proprietary files or anything from a particular device: the audit below fails the
# build if firmware, Android userspace, host keys or local settings end up in an image.
set -eu
TAG=${1:?usage: tools/make-release.sh TAG [--publish]}
PUBLISH=${2:-}
TOP=$(cd "$(dirname "$0")/.." && pwd)
KOUT=${MU300_KERNEL_OUT:-$TOP/out}
REPO=${MU300_REPO:-dikeckaan/mu300-linux}
D=$TOP/release/$TAG
IN=$D/inputs
[ -f "$KOUT/Image" ] && ls "$KOUT"/modules/*.ko >/dev/null 2>&1 || { echo "kernel outputs missing in $KOUT (kernel/build-all.sh)" >&2; exit 1; }
[ -z "$(git -C "$TOP" status --porcelain)" ] || { echo "commit your changes first: the release must match a commit" >&2; exit 1; }
rm -rf "$D" && mkdir -p "$IN/out" "$IN/tools/logdw" "$IN/tools/bt-init" "$IN/tools/gpu"

echo "==> helper binaries"
cp -R "$KOUT/modules" "$IN/out/modules"
cp "$KOUT/modules.builtin" "$KOUT/modules.builtin.modinfo" "$IN/out/"
docker build -q -t mu300-kbuild "$TOP/kernel" >/dev/null
docker build -q -t mu300-ubuntu:24.04 "$TOP/rootfs" >/dev/null
docker run --rm mu300-ubuntu:24.04 cat /bin/busybox > "$IN/busybox"; chmod +x "$IN/busybox"
docker run --rm -v "$TOP/tools":/src:ro -v "$IN/tools":/o mu300-kbuild sh -c '
  gcc -O2 -static -o /o/logdw/logdw /src/logdw/logdw.c &&
  gcc -O2 -static -o /o/bt-init/mu300-bt-init /src/bt-init/mu300-bt-init.c'
# cltest links against Android's libraries at build time only; use a local build when there is one
[ -f "$TOP/tools/gpu/cltest" ] && cp "$TOP/tools/gpu/cltest" "$IN/tools/gpu/cltest"
sh "$TOP/tools/fetch-sing-box.sh" "$IN/sing-box"
sh "$TOP/tools/fetch-xray.sh" "$IN"

echo "==> kernel bundle"
K=$D/kernel && mkdir -p "$K"
cp -R "$IN/out/modules" "$K/modules"
cp "$KOUT/Image" "$KOUT/modules.builtin" "$KOUT/modules.builtin.modinfo" "$IN/busybox" "$IN/tools/logdw/logdw" "$K/"
# the device-independent part of the boot ramdisk, which mu300-update puts behind the device's own ramdisk to update
# the kernel and the boot image without a computer (same builder and file list as install.sh)
python3 "$TOP/boot/build-boot-image.py" --generic-ramdisk --modules "$IN/out/modules" --busybox "$IN/busybox" \
  --logdw "$IN/tools/logdw/logdw" --ueventd-perms "$TOP/android-vendor/ueventd-perms.sh" \
  --out "$K/ramdisk-generic.lz4" >/dev/null
tar -C "$K" -czf "$D/mu300-kernel.tar.gz" .
rm -rf "$K"

echo "==> mainline kernel bundle"
# the 6.18 kernel for "mu300-update kernel 6.18": built by upstream/build.sh + build-modules.sh at this commit
[ -f "$TOP/upstream/out/Image" ] || { echo "upstream/out/Image missing (upstream/build.sh, build-modules.sh)" >&2; exit 1; }
sh "$TOP/upstream/make-bundle.sh" "$D/mu300-kernel-6.18.tar.gz" "$D/mu300-kernel.tar.gz"

echo "==> Ubuntu root filesystem (generic)"
B=$D/ubuntu-build && mkdir -p "$B"
tar -C "$TOP/rootfs" --exclude ./base.tar --exclude './*.tar.gz' -cf - . | tar -xf - -C "$B"
cid=$(docker create mu300-ubuntu:24.04 /bin/true); docker export "$cid" > "$B/base.tar"; docker rm "$cid" >/dev/null
cltest=""; [ -f "$IN/tools/gpu/cltest" ] && cltest="-v $IN/tools/gpu/cltest:/cltest:ro"
# shellcheck disable=SC2086
docker run --rm -v "$B":/w -v "$IN/out/modules":/kmods:ro -v "$IN/out":/kout:ro -v "$IN/tools/logdw/logdw":/logdw:ro \
  -v "$IN/tools/bt-init/mu300-bt-init":/bt-init:ro -v "$IN/sing-box":/sing-box:ro -v "$IN/xray":/xray:ro -v "$IN/hev-socks5-tunnel":/hev-socks5-tunnel:ro $cltest \
  -e MU300_VERSION="$TAG" mu300-ubuntu:24.04 bash /w/assemble.sh >/dev/null
mv "$B/mu300-ubuntu-24.04-rootfs.tar.gz" "$D/mu300-ubuntu-rootfs.tar.gz"; rm -rf "$B"

echo "==> OpenWrt root filesystem (generic)"
MU300_INPUTS="$IN" MU300_VERSION="$TAG" sh "$TOP/openwrt/build-rootfs.sh" mu300-openwrt-release.tar.gz >/dev/null
mv "$TOP/openwrt/mu300-openwrt-release.tar.gz" "$D/mu300-openwrt-rootfs.tar.gz"

echo "==> audit"
fail=0
for a in mu300-kernel mu300-kernel-6.18 mu300-ubuntu-rootfs mu300-openwrt-rootfs; do
    bad=$(tar -tzf "$D/$a.tar.gz" | sed 's|^\./||' | grep -E \
        -e '(^|/)lib/firmware/(wcnmodem|gnssmodem|wifi_board_config|bt_configure)' \
        -e '^opt/mu300/android/.+' -e '__properties__|dev-properties' \
        -e '(^|/)(libmali|libOpenCL|libGLES|libEGL|libvulkan)[^/]*\.so' \
        -e '^etc/ssh/ssh_host_' -e '^etc/mu300/(hotspot|vpn|toolkit)\.conf$' -e '^etc/dropbear/dropbear_.*_host_key' \
        | grep -vE '^opt/mu300/android/system/?$|^opt/mu300/android/system/bin/?$|^opt/mu300/android/system/bin/cltest$' || true)
    if [ -n "$bad" ]; then echo "$a contains files that must not be published:"; echo "$bad" | head -20; fail=1; fi
    mid=$(tar -xzOf "$D/$a.tar.gz" ./etc/machine-id 2>/dev/null || true)
    [ -z "$mid" ] || { echo "$a has a machine-id"; fail=1; }
done
[ $fail = 0 ] || { echo "audit failed, nothing published" >&2; exit 1; }
rm -rf "$IN"
# the updater itself: an older mu300-update fetches this one and continues with it
cp "$TOP/rootfs/overlay/opt/mu300/bin/mu300-update" "$D/mu300-update"
(cd "$D" && { shasum -a 256 *.tar.gz mu300-update 2>/dev/null || sha256sum *.tar.gz mu300-update; } > SHA256SUMS)
ls -la "$D"

[ "$PUBLISH" = --publish ] || { echo "built release/$TAG (run again with --publish to upload)"; exit 0; }
commit=$(git -C "$TOP" rev-parse HEAD)
kernel_rev=$(sed -n 's/^KERNEL_REV=//p' "$TOP/kernel/build-all.sh")
modules_rev=$(sed -n 's/^MODULES_REV=//p' "$TOP/kernel/build-all.sh")
notes=$(mktemp)
cat > "$notes" <<EOF
Prebuilt images for \`./install.sh\` (ZTE F50 / MU300). Check your device first with \`./install.sh --check\`.

| file | contents |
|---|---|
| mu300-kernel.tar.gz | Linux 5.4.254 \`Image\` and modules, static busybox and logdw for the boot image, and the generic boot ramdisk segment \`mu300-update\` uses |
| mu300-kernel-6.18.tar.gz | mainline Linux 6.18 (longterm) for \`mu300-update kernel 6.18\`: \`Image\`, modules, generic boot ramdisk segment |
| mu300-ubuntu-rootfs.tar.gz | Ubuntu 24.04 LTS root filesystem |
| mu300-openwrt-rootfs.tar.gz | OpenWrt 25.12.5 root filesystem |
| mu300-update | the on-device updater of this release (\`mu300-update apply\` switches to it before it changes anything) |

The images contain **no proprietary files**: the installer pulls the Wi-Fi/Bluetooth firmware and the Android
modem/GPU userspace from your own device and adds them during installation.

Built from $REPO@$commit with \`kernel/build-all.sh\` and \`tools/make-release.sh\`.
Corresponding source (GPL): kernel https://github.com/Enceka/android_kernel_zte_ums9620_mifi_u30air/tree/$kernel_rev ,
Wi-Fi/Bluetooth/Mali modules https://github.com/realme-kernel-opensource/realme_C51_C53_Narzo-N53-AndroidT-kernel-source/tree/$modules_rev ,
patches in \`kernel/patches\`. Ubuntu, OpenWrt and busybox packages come from their distributions' archives;
sing-box from https://github.com/SagerNet/sing-box/releases, Xray from https://github.com/XTLS/Xray-core/releases,
hev-socks5-tunnel from https://github.com/heiher/hev-socks5-tunnel/releases.
EOF
if gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
    gh release upload "$TAG" -R "$REPO" --clobber "$D"/*.tar.gz "$D/mu300-update" "$D/SHA256SUMS"
else
    gh release create "$TAG" -R "$REPO" --target "$commit" --title "MU300 Linux $TAG" --notes-file "$notes" \
      "$D"/*.tar.gz "$D/mu300-update" "$D/SHA256SUMS"
fi
rm -f "$notes"
