#!/bin/sh
# Build the opt-in U30 Air hostapd patch in a dedicated OpenWrt 25.12.5 armv8 SDK.
# This edits the SDK's package recipe and replaces its .config. No device is contacted.
# usage: build-u30-sae.sh /absolute/path/to/sdk /absolute/path/to/output
set -eu
[ "$#" = 2 ] || { echo "usage: $0 SDK OUTPUT" >&2; exit 2; }
TOP=$(cd "$(dirname "$0")/.." && pwd)
SDK=$(cd "$1" && pwd)
mkdir -p "$2"
OUT=$(cd "$2" && pwd)
PACKAGE=$SDK/package/feeds/base/hostapd
TARGET=package/feeds/base/hostapd
if [ ! -f "$PACKAGE/Makefile" ]; then
    PACKAGE=$SDK/package/network/services/hostapd
    TARGET=package/network/services/hostapd
fi
[ -f "$PACKAGE/Makefile" ] || {
    echo "hostapd recipe missing; run scripts/feeds update base and scripts/feeds install -p base hostapd in the SDK" >&2
    exit 1
}
PATCH=$TOP/openwrt/patches/hostapd/990-u30-sae-offload.patch

# Refuse another source version, an unreviewed package revision, or a conflicting local patch.
python3 - "$PACKAGE" "$PATCH" <<'PY'
import pathlib, re, shutil, sys
p, source = map(pathlib.Path, sys.argv[1:])
recipe = p / 'Makefile'
text = recipe.read_text()
if not re.search(r'^PKG_SOURCE_VERSION:=ca266cc24d8705eb1a2a0857ad326e48b1408b20$', text, re.M):
    raise SystemExit('Unsupported hostapd source; use the OpenWrt 25.12.5 armv8 SDK')
target = p / 'patches' / source.name
if target.exists() and target.read_bytes() != source.read_bytes():
    raise SystemExit('Conflicting local SAE patch; use a dedicated clean SDK')
release = re.search(r'^PKG_RELEASE:=(\d+)$', text, re.M)
if not release or (release[1] not in ('1', '5') and not (release[1] == '6' and target.exists())):
    raise SystemExit('Unsupported package revision; expected SDK r1, recorded r5, or this patched r6')
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(source, target)
recipe.write_text(re.sub(r'^PKG_RELEASE:=[15]$', 'PKG_RELEASE:=6', text, flags=re.M))
PY

cd "$SDK"
cat > .config <<'CONFIG'
CONFIG_TARGET_armsr=y
CONFIG_TARGET_armsr_armv8=y
CONFIG_TARGET_armsr_armv8_DEVICE_generic=y
# CONFIG_ALL is not set
# CONFIG_ALL_NONSHARED is not set
# CONFIG_ALL_KMODS is not set
CONFIG_PACKAGE_hostapd-common=m
CONFIG_PACKAGE_wpad-basic-openssl=m
CONFIG_DRIVER_11AC_SUPPORT=y
CONFIG_DRIVER_11AX_SUPPORT=y
CONFIG_WPA_MSG_MIN_PRIORITY=3
CONFIG
make defconfig
make "$TARGET/clean"
make -j"${MU300_JOBS:-4}" "$TARGET/compile" V=s

# Keep hostapd-common and wpad from the same recipe revision. apk resolves normal library dependencies.
for name in hostapd-common wpad-basic-openssl; do
    count=0
    for package in "$SDK"/bin/packages/aarch64_generic/base/"$name"-*.apk; do
        [ -s "$package" ] || continue
        cp "$package" "$OUT/"
        count=$((count + 1))
    done
    [ "$count" = 1 ] || { echo "expected exactly one $name APK, found $count" >&2; exit 1; }
done
echo "Built U30 SAE packages in $OUT; enablement and limitations: docs/U30AIR-SAE.md"
