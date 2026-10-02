#!/bin/sh
# Package the mainline build (build.sh + build-modules.sh) as a kernel bundle, laid out like the release's
# mu300-kernel.tar.gz so that mu300-update can install it:
#   upstream/make-bundle.sh OUT.tar.gz [KERNEL_BUNDLE_5.4]
#     ./Image                LK-loadable kernel (wrap-image.py: LK copies it to 0x80080000)
#     ./ramdisk-generic.lz4  boot/init, busybox, logdw and the modules of upstream/module-order.txt
#     ./modules/*.ko         every module, for /lib/modules/<release> on the root filesystem
#     ./kernel.release       the kernel's release string (uname -r)
#     ./devices              the devices it runs on (f50 u30air)
#     ./modules.builtin*     what the kernel has built in, for depmod/modprobe
# busybox and logdw are the static helpers of the 5.4 bundle (default: the newest one under release/).
set -eu
TOP=$(cd "$(dirname "$0")/.." && pwd)
U=$TOP/upstream
# the build to package: upstream/out (6.18), or MU300_UPSTREAM_OUT=upstream/out-7.2 for another kernel
UO=${MU300_UPSTREAM_OUT:-$U/out}
OUT=${1:?usage: upstream/make-bundle.sh OUT.tar.gz [mu300-kernel.tar.gz]}
REF=${2:-$(ls -t "$TOP"/release/*/mu300-kernel.tar.gz 2>/dev/null | head -1)}
[ -f "$UO/Image" ] || { echo "no $UO/Image (run build.sh)" >&2; exit 1; }
[ -f "$REF" ] || { echo "no 5.4 kernel bundle for busybox/logdw (give one as the second argument)" >&2; exit 1; }

krel=$(strings "$UO/Image" | sed -n 's/^Linux version \([^ ]*\) .*/\1/p' | head -1)
[ -n "$krel" ] || { echo "cannot read the kernel release from upstream/out/Image" >&2; exit 1; }
# a module left over from another kernel release would only fail on the device, at insmod
for m in "$UO"/modules/*.ko; do
    v=$(strings "$m" | sed -n 's/^vermagic=\([^ ]*\) .*/\1/p' | head -1)
    [ "$v" = "$krel" ] || { echo "$m is built for '$v', the kernel is '$krel'" >&2; exit 1; }
done
# A matching vermagic is not enough: the shared WLAN source may have changed
# after this output was built (the IPv6 RX checksum fix exposed exactly that).
# Refuse a bundle containing the old binary rather than silently shipping it.
wlan_module=$UO/modules/sprd_wlan_combo.ko
if [ -f "$wlan_module" ] && [ -n "$(find "$U/modules/sprd_wlan_combo" -type f -newer "$wlan_module" -print -quit)" ]; then
    echo "WLAN source is newer than $wlan_module; rebuild sprd_wlan_combo for $krel" >&2
    exit 1
fi
for m in $(cat "$U/module-order.txt"); do
    [ -f "$UO/modules/$m" ] || { echo "module-order.txt names $m, which was not built" >&2; exit 1; }
done

W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
tar -xzf "$REF" -C "$W" ./busybox ./logdw
mkdir "$W/b" "$W/b/modules"
python3 "$U/wrap-image.py" "$UO/Image" "$W/b/Image"
python3 "$TOP/boot/build-boot-image.py" --generic-ramdisk --modules "$UO/modules" \
    --module-order "$U/module-order.txt" --busybox "$W/busybox" --logdw "$W/logdw" \
    --ueventd-perms "$TOP/android-vendor/ueventd-perms.sh" --out "$W/b/ramdisk-generic.lz4" >/dev/null
cp "$UO"/modules/*.ko "$W/b/modules/"
for f in modules.builtin modules.builtin.modinfo; do [ ! -f "$UO/$f" ] || cp "$UO/$f" "$W/b/"; done
echo "$krel" > "$W/b/kernel.release"
# the devices this kernel runs on; mu300-update and the installers check it (FINDINGS 33c: mainline kernels from
# before this file do not bring up the U30 Air's USB)
echo "f50 u30air" > "$W/b/devices"
tar -C "$W/b" -czf "$OUT" .
echo "$OUT: kernel $krel, $(ls "$W/b/modules" | wc -l | tr -d ' ') modules, ramdisk segment $(wc -c < "$W/b/ramdisk-generic.lz4" | tr -d ' ') bytes"
