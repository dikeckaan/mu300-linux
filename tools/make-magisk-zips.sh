#!/bin/sh
# Build the Magisk installer zips of a release, one per system and kernel (design:
# docs/superpowers/specs/2026-10-05-magisk-installer-design.md):
#   tools/make-magisk-zips.sh RELEASE_DIR OUT_DIR [TAG]
# RELEASE_DIR holds the release's assets exactly as published; every one must match its SHA256SUMS. The zips contain
# the installer, the switch module, the 5.4 bundle's static busybox and the two assets of their combination - no file
# from any device: the installer reads those on the device it runs on. Every zip is checked against an exact list
# of names before it counts.
set -eu
USAGE='usage: tools/make-magisk-zips.sh RELEASE_DIR OUT_DIR [TAG]'
TOP=$(cd "$(dirname "$0")/.." && pwd)
R=$(cd "${1:?$USAGE}" && pwd)
: "${2:?$USAGE}"
TAG=${3:-$(basename "$R")}
# The installer's manifest_load accepts only this tag, so a zip built with another one would fail on the device
# instead of here; the tag also goes into sed replacements and file names, so this comes before either.
tag_ok=1
case $TAG in v[0-9]*) ;; *) tag_ok= ;; esac
case $TAG in *[!0-9A-Za-z._-]*|*..*) tag_ok= ;; esac
[ -n "$tag_ok" ] || { echo "the tag '$TAG' is not one the installer accepts: v[0-9] and then letters, digits, . _ - (no ..)" >&2; exit 1; }
sha() { (sha256sum "$1" 2>/dev/null || shasum -a 256 "$1") | cut -d' ' -f1; }
for f in mu300-kernel.tar.gz mu300-kernel-6.18.tar.gz mu300-kernel-7.2.tar.gz mu300-openwrt-rootfs.tar.gz \
         mu300-openwrt-luci-rootfs.tar.gz mu300-ubuntu-rootfs.tar.gz mu300-ubuntu-26.04-rootfs.tar.gz; do
    want=$(awk -v f="$f" '$2 == f || $2 == "*" f {print $1}' "$R/SHA256SUMS")
    [ -n "$want" ] && [ -f "$R/$f" ] && [ "$(sha "$R/$f")" = "$want" ] ||
        { echo "$f is missing from $R or does not match its SHA256SUMS" >&2; exit 1; }
done
mkdir -p "$2"; O=$(cd "$2" && pwd)
# Magisk wants an integer that grows: the date in the tag (v2026.10.06 -> 20261006)
code=$(printf '%s' "$TAG" | tr -cd 0-9 | cut -c1-9); [ -n "$code" ] || code=1
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
tar -xzOf "$R/mu300-kernel.tar.gz" ./busybox > "$W/busybox"
[ -s "$W/busybox" ] || { echo "mu300-kernel.tar.gz has no busybox" >&2; exit 1; }

# what every zip holds besides its payload, by name (the audit below compares against this)
COMMON='META-INF/com/google/android/update-binary META-INF/com/google/android/updater-script module.prop customize.sh
action.sh switch.sh system/bin/mu300-linux mu300/install.sh mu300/android-boot-image.sh mu300/mu300-update
mu300/android-install.sh mu300/android-mount-mu300root.sh mu300/storage.sh mu300/i18n.sh mu300/i18n/tr.tsv
mu300/i18n/zh.tsv mu300/subset-files.txt mu300/gpu-files.txt mu300/busybox mu300/manifest'
stage() {  # stage DIR SYSTEM KERNEL ROOTFS_ASSET KERNEL_ASSET OS UBUNTU
    S=$1
    mkdir -p "$S/META-INF/com/google/android" "$S/system/bin" "$S/mu300/i18n" "$S/payload"
    I=$TOP/android/magisk/installer; M=$TOP/android/magisk/mu300-linux-switch
    cp "$I/update-binary" "$I/updater-script" "$S/META-INF/com/google/android/"
    sed -e "s/@TAG@/$TAG/" -e "s/@CODE@/$code/" -e "s/@SYSTEM@/$2/" -e "s/@KERNEL@/$3/" "$I/module.prop.in" > "$S/module.prop"
    cp "$I/customize.sh" "$M/action.sh" "$M/switch.sh" "$S/"
    cp "$M/system/bin/mu300-linux" "$S/system/bin/"
    cp "$I/mu300-install.sh" "$S/mu300/install.sh"
    cp "$TOP/tools/android-boot-image.sh" "$TOP/tools/android-install.sh" "$TOP/tools/android-mount-mu300root.sh" \
       "$TOP/tools/storage.sh" "$TOP/tools/i18n.sh" "$S/mu300/"
    # the checkout's (in CI the tag's, so the release's own): the installer needs bootimg_from_stock, which an older
    # release's mu300-update does not have when zips are built locally from one
    cp "$TOP/rootfs/overlay/opt/mu300/bin/mu300-update" "$S/mu300/mu300-update"
    cp "$TOP/i18n/tr.tsv" "$TOP/i18n/zh.tsv" "$S/mu300/i18n/"
    cp "$TOP/android-vendor/subset-files.txt" "$TOP/android-vendor/gpu-files.txt" "$S/mu300/"
    cp "$W/busybox" "$S/mu300/busybox"
    cp "$R/$4" "$R/$5" "$S/payload/"
    printf 'TAG=%s\nSYSTEM=%s\nOS=%s\nUBUNTU=%s\nKERNEL=%s\nKERNEL_ASSET=%s\nROOTFS_ASSET=%s\nSHA256_KERNEL=%s\nSHA256_ROOTFS=%s\n' \
        "$TAG" "$2" "$6" "$7" "$3" "$5" "$4" "$(sha "$R/$5")" "$(sha "$R/$4")" > "$S/mu300/manifest"
}
audit() {  # audit ZIP ROOTFS_ASSET KERNEL_ASSET: exactly the names it should hold, the payload stored
    printf '%s\n' $COMMON "payload/$2" "payload/$3" | LC_ALL=C sort > "$W/want"
    unzip -Z1 "$1" | LC_ALL=C sort > "$W/have"
    diff "$W/have" "$W/want" >&2 || { echo "$1 does not hold exactly the expected files (< extra, > missing)" >&2; return 1; }
    [ "$(unzip -Zv "$1" 'payload/*' | grep -c 'compression method: *none')" = 2 ] || { echo "$1: the payload is compressed" >&2; return 1; }
}
: > "$O/SHA256SUMS-magisk"
for s in openwrt:mu300-openwrt-rootfs.tar.gz:openwrt: \
         openwrt-luci:mu300-openwrt-luci-rootfs.tar.gz:openwrt-luci: \
         ubuntu-24.04:mu300-ubuntu-rootfs.tar.gz:ubuntu:24.04 \
         ubuntu-26.04:mu300-ubuntu-26.04-rootfs.tar.gz:ubuntu:26.04; do
    name=${s%%:*}; rest=${s#*:}; rootfs=${rest%%:*}; rest=${rest#*:}; os=${rest%%:*}; ubuntu=${rest#*:}
    for k in 5.4:mu300-kernel.tar.gz 6.18:mu300-kernel-6.18.tar.gz 7.2:mu300-kernel-7.2.tar.gz; do
        kv=${k%%:*}; kasset=${k#*:}
        # Ubuntu 26.04's programs need system calls 5.4 does not have (install.sh refuses the pair too)
        [ "$ubuntu" = 26.04 ] && [ "$kv" = 5.4 ] && continue
        zip=mu300-magisk-$TAG-$name-k$kv.zip
        S=$W/$name-$kv
        stage "$S" "$name" "$kv" "$rootfs" "$kasset" "$os" "$ubuntu"
        rm -f "$O/$zip"
        (cd "$S" && find . -type f ! -path './payload/*' | sed 's|^\./||' | LC_ALL=C sort | zip -X -q -9 "$O/$zip" -@ &&
            zip -X -q -0 "$O/$zip" "payload/$kasset" "payload/$rootfs")
        audit "$O/$zip" "$rootfs" "$kasset" || { rm -f "$O/$zip"; exit 1; }
        rm -rf "$S"
        printf '%s  %s\n' "$(sha "$O/$zip")" "$zip" >> "$O/SHA256SUMS-magisk"
        echo "$zip: $(wc -c < "$O/$zip" | tr -d ' ') bytes"
    done
done
