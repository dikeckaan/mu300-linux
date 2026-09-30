#!/bin/sh
# Build a Magisk-installable OpenWrt-on-TF package with Linux 7.2.
# Usage: MU300_INPUTS=work MU300_UPSTREAM_OUT=upstream/out-7.2 tools/build-openwrt-tf-magisk.sh [OUT.zip]
# The TF image includes the standalone LuCI package from openwrt/luci-app-mu300.
set -eu
TOP=$(cd "$(dirname "$0")/.." && pwd)
IN=${MU300_INPUTS:-$TOP/work}
UO=${MU300_UPSTREAM_OUT:-$TOP/upstream/out-7.2}
PLUGIN=${MU300_LUCI_PLUGIN_SRC:-$TOP/openwrt/luci-app-mu300}
[ -s "$PLUGIN/Makefile" ] || { echo "standalone LuCI plugin missing: $PLUGIN (set MU300_LUCI_PLUGIN_SRC)" >&2; exit 1; }
OUT=${1:-$TOP/mu300-linux-openwrt-tf.zip}
case $OUT in /*) ;; *) OUT=$TOP/$OUT ;; esac
STAGE=$TOP/work/tf-magisk-stage
ROOTFS=$TOP/openwrt/mu300-openwrt-tf-rootfs.tar.gz
BOOT=$TOP/work/boot-linux-slotb-tf.img
GENERIC=$TOP/work/ramdisk-7.2-tf.lz4
WRAPPED=$TOP/work/Image-7.2.lk
VERSION=${MU300_VERSION:-}
[ -n "$VERSION" ] || VERSION=$(git -c safe.directory="$TOP" -C "$TOP" rev-parse --short HEAD 2>/dev/null || true)
[ -n "$VERSION" ] || VERSION=clean-tf-7.2
mkdir -p "$TOP/work"

for f in dumps/boot_a.img dumps/misc-head.bin busybox tools/logdw/logdw; do
    [ -s "$IN/$f" ] || { echo "missing $IN/$f" >&2; exit 1; }
done
for f in firmware android-subset tools/bt-init/mu300-bt-init tools/keys/mu300-keys; do
    [ -e "$IN/$f" ] || { echo "required device input missing: $IN/$f" >&2; exit 1; }
done
file "$IN/tools/keys/mu300-keys" | grep -q 'ELF 64-bit.*ARM aarch64' || {
    echo "mu300-keys must be an AArch64 executable" >&2; exit 1;
}
for f in wcn_bsp.ko sprd_wlan_combo.ko sprdbt_tty.ko mali_kbase.ko; do
    [ -s "$IN/out/modules/$f" ] || { echo "missing $IN/out/modules/$f" >&2; exit 1; }
done
[ -s "$UO/Image" ] || { echo "missing Linux 7.2 Image in $UO" >&2; exit 1; }
rel=$(strings "$UO/Image" | sed -n 's/^Linux version \([^ ]*\) .*/\1/p' | head -n1)
case $rel in 7.2.*) ;; *) echo "$UO is kernel '$rel', expected 7.2.x" >&2; exit 1 ;; esac
for m in $(cat "$TOP/upstream/module-order.txt"); do
    [ -s "$UO/modules/$m" ] || { echo "missing 7.2 module $m" >&2; exit 1; }
done

echo "==> OpenWrt rootfs ($rel modules included)"
if [ "${MU300_REUSE_BUILD:-0}" = 1 ] && [ -s "$ROOTFS" ]; then
    echo "reusing $ROOTFS"
else
    MU300_GPU=0 MU300_INPUTS="$IN" MU300_MAINLINE_OUT="$UO" MU300_LUCI_PLUGIN_SRC="$PLUGIN" \
      MU300_VERSION="$VERSION-tf-7.2" \
      sh "$TOP/openwrt/build-rootfs.sh" "$(basename "$ROOTFS")"
fi
for f in ./lib/netifd/proto/mu300cell.sh ./lib/netifd/proto/mu300cell-v6.sh ./opt/mu300/bin/mu300-keys ./opt/mu300/bin/mu300-bt-init ./opt/mu300/bin/mu300-atd ./etc/init.d/mu300-post ./usr/share/luci/menu.d/luci-app-mu300.json ./www/luci-static/resources/view/mu300/home.js ./usr/lib/lua/luci/i18n/mu300.en.lmo ./usr/lib/lua/luci/i18n/mu300.tr.lmo ./etc/init.d/unisoc-modem-ui; do
    tar -tzf "$ROOTFS" "$f" >/dev/null || { echo "built rootfs missing required file: $f" >&2; exit 1; }
done

echo "==> Linux 7.2 boot_b image"
python3 "$TOP/upstream/wrap-image.py" "$UO/Image" "$WRAPPED"
python3 "$TOP/boot/build-boot-image.py" --generic-ramdisk --modules "$UO/modules" \
  --module-order "$TOP/upstream/module-order.txt" --busybox "$IN/busybox" \
  --logdw "$IN/tools/logdw/logdw" --ueventd-perms "$TOP/android-vendor/ueventd-perms.sh" \
  --out "$GENERIC" >/dev/null
python3 "$TOP/boot/build-boot-image.py" \
  --stock-boot "$IN/dumps/boot_a.img" --misc-head "$IN/dumps/misc-head.bin" \
  --kernel "$WRAPPED" --append-ramdisk "$GENERIC" --modules "$IN/out/modules" \
  --init "$TOP/boot/init" --busybox "$IN/busybox" --logdw "$IN/tools/logdw/logdw" \
  --ueventd-perms "$TOP/android-vendor/ueventd-perms.sh" \
  --android-subset "$IN/android-subset" --out "$BOOT" >/dev/null

rm -rf "$STAGE"; mkdir -p "$STAGE"
cp "$TOP/android/magisk/mu300-openwrt-tf/module.prop" \
   "$TOP/android/magisk/mu300-openwrt-tf/customize.sh" \
   "$TOP/android/magisk/mu300-linux-switch/switch.sh" \
   "$TOP/tools/android-install.sh" "$TOP/tools/mu300-vendor-from-device.sh" "$STAGE/"
cp "$IN/busybox" "$STAGE/busybox"
cp "$ROOTFS" "$STAGE/mu300-openwrt.tar.gz"
cp "$BOOT" "$STAGE/boot-linux-slotb.img"
(cd "$STAGE" && sha256sum boot-linux-slotb.img | cut -d' ' -f1 > boot-linux-slotb.sha256)
chmod 755 "$STAGE"/*.sh "$STAGE/busybox"
rm -f "$OUT"
python3 - "$STAGE" "$OUT" <<'PY'
import os, sys, zipfile
src, out = map(os.path.abspath, sys.argv[1:])
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for name in sorted(files):
            p = os.path.join(root, name)
            z.write(p, os.path.relpath(p, src).replace(os.sep, '/'))
PY
echo "built $OUT (kernel $rel)"
