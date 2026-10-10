#!/bin/sh
# Maintainer: build the generic release assets used by ./install.sh (prebuilt mode) and optionally publish them.
#   tools/make-release.sh TAG             build into release/TAG and audit the contents
#   tools/make-release.sh TAG --publish   also create/update the GitHub release (gh)
#   tools/make-release.sh TAG --publish --prerelease   create it as a prerelease: never "latest", so mu300-update and
#                                          the installers do not offer it until it is promoted on GitHub
# Needs docker and the kernel outputs in $MU300_KERNEL_OUT (default: out/, from kernel/build-all.sh).
# The assets must never contain proprietary files or anything from a particular device: the audit below fails the
# build if firmware, Android userspace, host keys or local settings end up in an image.
set -eu
TAG=${1:?usage: tools/make-release.sh TAG [--publish [--prerelease]]}
shift
PUBLISH="" PRERELEASE=""
for a in "$@"; do
    case $a in
        --publish) PUBLISH=--publish ;;
        --prerelease) PRERELEASE=--prerelease ;;
        *) echo "unknown option $a (usage: tools/make-release.sh TAG [--publish [--prerelease]])" >&2; exit 1 ;;
    esac
done
TOP=$(cd "$(dirname "$0")/.." && pwd)
KOUT=${MU300_KERNEL_OUT:-$TOP/out}
REPO=${MU300_REPO:-dikeckaan/mu300-linux}
D=$TOP/release/$TAG
IN=$D/inputs
[ -f "$KOUT/Image" ] && ls "$KOUT"/modules/*.ko >/dev/null 2>&1 || { echo "kernel outputs missing in $KOUT (kernel/build-all.sh)" >&2; exit 1; }
ls "$KOUT"/modules-u30air/*.ko >/dev/null 2>&1 || { echo "U30 Air modules missing in $KOUT/modules-u30air (kernel/build-all.sh)" >&2; exit 1; }
[ -z "$(git -C "$TOP" status --porcelain)" ] || { echo "commit your changes first: the release must match a commit" >&2; exit 1; }
rm -rf "$D" && mkdir -p "$IN/out" "$IN/tools/logdw" "$IN/tools/bt-init" "$IN/tools/gpu"

echo "==> helper binaries"
cp -R "$KOUT/modules" "$IN/out/modules"
cp "$KOUT/modules.builtin" "$KOUT/modules.builtin.modinfo" "$IN/out/"
docker build -q -t mu300-kbuild "$TOP/kernel" >/dev/null
docker build -q -t mu300-ubuntu:24.04 "$TOP/rootfs" >/dev/null
docker build -q --build-arg BASE=ubuntu:26.04 -t mu300-ubuntu:26.04 "$TOP/rootfs" >/dev/null
docker run --rm mu300-ubuntu:24.04 cat /bin/busybox > "$IN/busybox"; chmod +x "$IN/busybox"
docker run --rm -v "$TOP/tools":/src:ro -v "$IN/tools":/o mu300-kbuild sh -c '
  gcc -O2 -static -o /o/logdw/logdw /src/logdw/logdw.c &&
  gcc -O2 -static -o /o/bt-init/mu300-bt-init /src/bt-init/mu300-bt-init.c &&
  mkdir -p /o/keys && gcc -O2 -static -o /o/keys/mu300-keys /src/keys/mu300-keys.c'
# cltest links against Android's libraries at build time only; use a local build when there is one
[ -f "$TOP/tools/gpu/cltest" ] && cp "$TOP/tools/gpu/cltest" "$IN/tools/gpu/cltest"

echo "==> extras"
# not in the images: mu300-extra installs them on the devices that want them (mu300-extra-<name>.tar.gz)
sh "$TOP/tools/make-extra.sh" vpn "$D/mu300-extra-vpn.tar.gz" "$TAG"
sh "$TOP/tools/make-extra.sh" vpn-mihomo "$D/mu300-extra-vpn-mihomo.tar.gz" "$TAG"

echo "==> kernel bundle"
K=$D/kernel && mkdir -p "$K"
cp -R "$IN/out/modules" "$K/modules"
cp -R "$KOUT/modules-u30air" "$K/modules-u30air"
# the devices this bundle runs on (mu300-update and the installers check it)
echo "f50 u30air" > "$K/devices"
# what it can do that older bundles could not: 5.4 reads the SD card (FINDINGS 31j), so a system on the card may get
# it; its init runs from either slot, so a Linux on slot a may get it (mu300-update checks both)
printf 'sdcard\nlinux-slot\n' > "$K/features"
cp "$KOUT/Image" "$KOUT/modules.builtin" "$KOUT/modules.builtin.modinfo" "$IN/busybox" "$IN/tools/logdw/logdw" "$K/"
# the device-independent part of the boot ramdisk, which mu300-update puts behind the device's own ramdisk to update
# the kernel and the boot image without a computer (same builder and file list as install.sh)
python3 "$TOP/boot/build-boot-image.py" --generic-ramdisk --modules "$IN/out/modules" --busybox "$IN/busybox" \
  --device-modules "u30air=$KOUT/modules-u30air" \
  --logdw "$IN/tools/logdw/logdw" --ueventd-perms "$TOP/android-vendor/ueventd-perms.sh" \
  --out "$K/ramdisk-generic.lz4" >/dev/null
tar -C "$K" -czf "$D/mu300-kernel.tar.gz" .
rm -rf "$K"

echo "==> mainline kernel bundles"
# "mu300-update kernel 6.18|7.2": built by upstream/build.sh + build-modules.sh at this commit - 6.18 into
# upstream/out, 7.2 into upstream/out-7.2 (OUTDIR=out-7.2 KV=7.2.x); each build must be the version its name says
for kv in 6.18:out 7.2:out-7.2; do
    v=${kv%%:*}; o=$TOP/upstream/${kv#*:}
    [ -f "$o/Image" ] || { echo "$o/Image missing (upstream/build.sh, build-modules.sh)" >&2; exit 1; }
    rel=$(strings "$o/Image" | sed -n 's/^Linux version \([^ ]*\) .*/\1/p' | head -1)
    case $rel in "$v".*) ;; *) echo "$o holds $rel, not $v" >&2; exit 1 ;; esac
    MU300_UPSTREAM_OUT=$o sh "$TOP/upstream/make-bundle.sh" "$D/mu300-kernel-$v.tar.gz" "$D/mu300-kernel.tar.gz"
done

# 24.04 keeps the name it always had (older installers and mu300-update ask for it); 26.04 has its own
for u in 24.04 26.04; do
    echo "==> Ubuntu $u root filesystem (generic)"
    B=$D/ubuntu-build && rm -rf "$B" && mkdir -p "$B"
    tar -C "$TOP/rootfs" --exclude ./base.tar --exclude './*.tar.gz' -cf - . | tar -xf - -C "$B"
    cid=$(docker create mu300-ubuntu:$u /bin/true); docker export "$cid" > "$B/base.tar"; docker rm "$cid" >/dev/null
    cltest=""; [ -f "$IN/tools/gpu/cltest" ] && cltest="-v $IN/tools/gpu/cltest:/cltest:ro"
    # shellcheck disable=SC2086
    docker run --rm -v "$B":/w -v "$IN/out/modules":/kmods:ro -v "$IN/out":/kout:ro -v "$IN/tools/logdw/logdw":/logdw:ro \
      -v "$IN/tools/bt-init/mu300-bt-init":/bt-init:ro -v "$IN/tools/keys/mu300-keys":/keys:ro $cltest \
      -e MU300_VERSION="$TAG" mu300-ubuntu:$u bash /w/assemble.sh >/dev/null
    out=mu300-ubuntu-rootfs.tar.gz; [ $u = 24.04 ] || out=mu300-ubuntu-$u-rootfs.tar.gz
    mv "$B/mu300-ubuntu-$u-rootfs.tar.gz" "$D/$out"; rm -rf "$B"
done

echo "==> OpenWrt root filesystem (generic)"
MU300_INPUTS="$IN" MU300_VERSION="$TAG" sh "$TOP/openwrt/build-rootfs.sh" mu300-openwrt-release.tar.gz >/dev/null
mv "$TOP/openwrt/mu300-openwrt-release.tar.gz" "$D/mu300-openwrt-rootfs.tar.gz"

echo "==> OpenWrt with the MU300 control panel"
MU300_SYSTEM=openwrt-luci MU300_INPUTS="$IN" MU300_VERSION="$TAG" sh "$TOP/openwrt/build-rootfs.sh" mu300-openwrt-luci-release.tar.gz >/dev/null
mv "$TOP/openwrt/mu300-openwrt-luci-release.tar.gz" "$D/mu300-openwrt-luci-rootfs.tar.gz"

echo "==> lang extra"
# after the OpenWrt builds: it is built in the OpenWrt base image they import, from the same feed
sh "$TOP/tools/make-extra.sh" lang "$D/mu300-extra-lang.tar.gz" "$TAG"

echo "==> audit"
fail=0
for a in mu300-kernel mu300-kernel-6.18 mu300-kernel-7.2 mu300-ubuntu-rootfs mu300-ubuntu-26.04-rootfs mu300-openwrt-rootfs \
         mu300-openwrt-luci-rootfs; do
    bad=$(tar -tzf "$D/$a.tar.gz" | sed 's|^\./||' | grep -E \
        -e '(^|/)lib/firmware/(wcnmodem|gnssmodem|wifi_board_config|bt_configure)' \
        -e '^opt/mu300/android/.+' -e '__properties__|dev-properties' \
        -e '(^|/)(libmali|libOpenCL|libGLES|libEGL|libvulkan)[^/]*\.so' \
        -e '^etc/ssh/ssh_host_' -e '^etc/mu300/(hotspot|vpn|toolkit)\.conf$' -e '^etc/dropbear/dropbear_.*_host_key' \
        -e '^opt/mu300/bin/(xray|sing-box|hev-socks5-tunnel|mihomo)$' \
        | grep -vE '^opt/mu300/android/system/?$|^opt/mu300/android/system/bin/?$|^opt/mu300/android/system/bin/cltest$' || true)
    if [ -n "$bad" ]; then echo "$a contains files that must not be published:"; echo "$bad" | head -20; fail=1; fi
    mid=$(tar -xzOf "$D/$a.tar.gz" ./etc/machine-id 2>/dev/null || true)
    [ -z "$mid" ] || { echo "$a has a machine-id"; fail=1; }
done
# the panel: everything of it is in the luci asset, and nothing of it (nor Aurora) in the plain OpenWrt one
list_of() { tar -tzf "$D/$1.tar.gz" | sed 's|^\./||'; }
panel=$(list_of mu300-openwrt-luci-rootfs)
for f in usr/share/luci/menu.d/luci-app-mu300.json www/luci-static/resources/view/mu300/home.js \
         usr/libexec/rpcd/mu300dash usr/lib/lua/luci/i18n/mu300.tr.lmo usr/lib/lua/luci/i18n/mu300.zh-cn.lmo \
         www/luci-static/aurora/main.css etc/mu300/packages.txt usr/lib/lua/luci/i18n/base.tr.lmo \
         usr/lib/lua/luci/i18n/base.zh-cn.lmo; do
    printf '%s\n' "$panel" | grep -qx "$f" || { echo "mu300-openwrt-luci-rootfs lacks $f"; fail=1; }
done
plain=$(list_of mu300-openwrt-rootfs)
for f in usr/libexec/rpcd/mu300dash www/luci-static/aurora/main.css; do
    ! printf '%s\n' "$plain" | grep -qx "$f" || { echo "mu300-openwrt-rootfs has $f, which is only for openwrt-luci"; fail=1; }
done
for f in etc/mu300/packages.txt usr/lib/lua/luci/i18n/base.tr.lmo usr/lib/lua/luci/i18n/base.zh-cn.lmo; do
    printf '%s\n' "$plain" | grep -qx "$f" || { echo "mu300-openwrt-rootfs lacks $f"; fail=1; }
done
# the lang extra: catalogs only (and its manifest), and the panel's in the languages it was translated to
lx=$(tar -tzf "$D/mu300-extra-lang.tar.gz" | sed 's|^\./||')
! printf '%s\n' "$lx" | grep . | grep -Evx 'name|release|components|languages|manifest|i18n/?|i18n/[a-z0-9-]+\.[a-z]{2,3}(-[a-z]{2})?\.lmo' ||
    { echo "mu300-extra-lang.tar.gz has files that are not catalogs"; fail=1; }
for f in i18n/base.de.lmo i18n/mu300.de.lmo i18n/mu300.ja.lmo; do
    printf '%s\n' "$lx" | grep -qx "$f" || { echo "mu300-extra-lang.tar.gz lacks $f"; fail=1; }
done
# what the package list changed since the last release (MU300_PREV_RELEASE: its directory, with the assets)
if [ -n "${MU300_PREV_RELEASE:-}" ]; then
    for a in mu300-openwrt-rootfs mu300-openwrt-luci-rootfs; do
        [ -f "$MU300_PREV_RELEASE/$a.tar.gz" ] || { echo "$a: no previous asset in $MU300_PREV_RELEASE"; continue; }
        echo "==> $a: etc/mu300/packages.txt against the previous release"
        tar -xzOf "$MU300_PREV_RELEASE/$a.tar.gz" ./etc/mu300/packages.txt > "$D/packages.prev" 2>/dev/null || : > "$D/packages.prev"
        tar -xzOf "$D/$a.tar.gz" ./etc/mu300/packages.txt > "$D/packages.new" 2>/dev/null || : > "$D/packages.new"
        diff -u "$D/packages.prev" "$D/packages.new" || true
        rm -f "$D/packages.prev" "$D/packages.new"
    done
fi
# an extra holds what its name says, for the release it is published with (mu300-update compares ./release)
for x in vpn lang vpn-mihomo; do
    [ "$(tar -xzOf "$D/mu300-extra-$x.tar.gz" ./name)" = $x ] && [ "$(tar -xzOf "$D/mu300-extra-$x.tar.gz" ./release)" = "$TAG" ] ||
        { echo "mu300-extra-$x.tar.gz is not the $x extra of $TAG"; fail=1; }
done
# mu300-update refuses a kernel bundle without the SD host for a system on the card, and one whose init runs only from
# slot b for a Linux on slot a: every bundle must say it has both
for a in mu300-kernel mu300-kernel-6.18 mu300-kernel-7.2; do
    tar -xzOf "$D/$a.tar.gz" ./features 2>/dev/null | grep -qx sdcard || { echo "$a does not list sdcard in ./features"; fail=1; }
    tar -xzOf "$D/$a.tar.gz" ./features 2>/dev/null | grep -qx linux-slot || { echo "$a does not list linux-slot in ./features"; fail=1; }
done
# a mainline bundle carries the kernel's own modules next to the vendor ones (upstream/build-modules.sh): one of each
# kind - qdisc, filesystem, device mapper, USB modem, vhost - and the vendor Wi-Fi
for a in mu300-kernel-6.18 mu300-kernel-7.2; do
    l=$(tar -tzf "$D/$a.tar.gz")
    for m in sch_htb.ko ntfs3.ko dm-crypt.ko cdc_mbim.ko vhost_net.ko sprd_wlan_combo.ko; do
        printf '%s\n' "$l" | grep -qx "./modules/$m" || { echo "$a lacks modules/$m"; fail=1; }
    done
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
Prebuilt images for \`./install.sh\` (ZTE F50 / MU300 and ZTE U30 Air; the installer recognises which). Check your device
first with \`./install.sh --check\`.

| file | contents |
|---|---|
| mu300-kernel.tar.gz | Linux 5.4.254 \`Image\` and modules (with the U30 Air's own in \`modules-u30air/\`), static busybox and logdw for the boot image, and the generic boot ramdisk segment \`mu300-update\` uses |
| mu300-kernel-6.18.tar.gz | mainline Linux 6.18 (longterm) for \`mu300-update kernel 6.18\`: \`Image\`, modules, generic boot ramdisk segment |
| mu300-kernel-7.2.tar.gz | mainline Linux 7.2 (newest stable) for \`mu300-update kernel 7.2\`: the same parts |
| mu300-ubuntu-rootfs.tar.gz | Ubuntu 24.04 LTS root filesystem |
| mu300-ubuntu-26.04-rootfs.tar.gz | Ubuntu 26.04 LTS root filesystem |
| mu300-openwrt-rootfs.tar.gz | OpenWrt 25.12.5 root filesystem |
| mu300-openwrt-luci-rootfs.tar.gz | OpenWrt 25.12.5 with the MU300 control panel (luci-app-mu300 by kanoqwq, Aurora theme by eamonxg) |
| mu300-extra-vpn.tar.gz | the VPN engines, not part of the images: \`mu300-extra install vpn\` on the device (or the installer's question) puts them on the Linux partition; Xray-core $(sed -n 's/^XRAY_VER=//p' "$TOP/tools/fetch-xray.sh"), hev-socks5-tunnel $(sed -n 's/^HEV_VER=//p' "$TOP/tools/fetch-xray.sh"), sing-box $(sed -n 's/^VER=//p' "$TOP/tools/fetch-sing-box.sh") |
| mu300-extra-vpn-mihomo.tar.gz | mihomo (Clash.Meta) $(sed -n 's/^VER=//p' "$TOP/tools/fetch-mihomo.sh"), the engine of mu300-vpn's mihomo profiles (Clash/mihomo YAML subscriptions): \`mu300-extra install vpn-mihomo\` on the device (mu300-vpn fetches it itself when a mihomo profile is turned on) |
| mu300-extra-lang.tar.gz | LuCI and the MU300 panel in more languages (OpenWrt only; English, Turkish and Chinese are in the images): \`mu300-extra install lang\` on the device, or System > Languages in the panel; LuCI's catalogs from the OpenWrt 25.12.5 feed, the panel's AI-translated |
| mu300-update | the on-device updater of this release (\`mu300-update apply\` switches to it before it changes anything) |

The images contain **no proprietary files**: the installer pulls the Wi-Fi/Bluetooth firmware and the Android
modem/GPU userspace from your own device and adds them during installation.

Built from $REPO@$commit with \`kernel/build-all.sh\` and \`tools/make-release.sh\`.
Corresponding source (GPL): kernel https://github.com/Enceka/android_kernel_zte_ums9620_mifi_u30air/tree/$kernel_rev ,
Wi-Fi/Bluetooth/Mali modules https://github.com/realme-kernel-opensource/realme_C51_C53_Narzo-N53-AndroidT-kernel-source/tree/$modules_rev ,
patches in \`kernel/patches\`. Ubuntu, OpenWrt and busybox packages come from their distributions' archives;
sing-box from https://github.com/SagerNet/sing-box/releases, Xray from https://github.com/XTLS/Xray-core/releases,
hev-socks5-tunnel from https://github.com/heiher/hev-socks5-tunnel/releases,
mihomo from https://github.com/MetaCubeX/mihomo/releases,
Aurora (luci-theme-aurora 1.4.0) from https://github.com/eamonxg/luci-theme-aurora/releases/tag/v1.4.0.
EOF
if gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
    gh release upload "$TAG" -R "$REPO" --clobber "$D"/*.tar.gz "$D/mu300-update" "$D/SHA256SUMS"
else
    # shellcheck disable=SC2086
    gh release create "$TAG" -R "$REPO" --target "$commit" --title "MU300 Linux $TAG" --notes-file "$notes" $PRERELEASE \
      "$D"/*.tar.gz "$D/mu300-update" "$D/SHA256SUMS"
fi
rm -f "$notes"
