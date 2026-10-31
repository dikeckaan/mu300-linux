#!/bin/sh
# Build the openclash extra: the pinned luci-app-openclash .apk, the hooks that install it into the running OpenWrt
# system, and the command that does the same by hand. mu300-extra installs it like any other extra; the installer of
# the systems builds it from the apk it downloads (install.sh, install.ps1).
#   tools/make-openclash-extra.sh APK OUT.tar.gz [TAG]
# APK: luci-app-openclash-<version>.apk (the installer checks it against the pinned hash of its release)
# TAG: the mu300-linux release it is published with (as the other extras' ./release)
set -eu
APK=${1:?usage: tools/make-openclash-extra.sh APK OUT.tar.gz [TAG]}
OUT=${2:?usage: tools/make-openclash-extra.sh APK OUT.tar.gz [TAG]}
TAG=${3:-dev}
TOP=$(cd "$(dirname "$0")/.." && pwd)
[ -s "$APK" ] || { echo "make-openclash-extra: $APK not found" >&2; exit 1; }
case $TAG in ''|*[!A-Za-z0-9._-]*) echo "make-openclash-extra: bad tag '$TAG'" >&2; exit 1 ;; esac
tmp=$(mktemp -d "${TMPDIR:-/tmp}/mu300-openclash-extra.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
x=$tmp/x
mkdir -p "$x/hooks" "$x/bin"
cp "$APK" "$x/openclash.apk"
cp "$TOP/tools/openclash-extra/hooks/link" "$TOP/tools/openclash-extra/hooks/unlink" "$x/hooks/"
cp "$TOP/tools/openclash-extra/bin/mu300-openclash" "$x/bin/"
chmod 755 "$x/hooks/link" "$x/hooks/unlink" "$x/bin/mu300-openclash"
printf 'openclash\n' > "$x/name"
printf '%s\n' "$TAG" > "$x/release"
# ./manifest: the sha256 of every file, as sha256sum writes it (mu300-update checks the unpacked tree against it)
if command -v sha256sum >/dev/null 2>&1; then hash() { sha256sum "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then hash() { shasum -a 256 "$1" | cut -d' ' -f1; }
else echo "make-openclash-extra: no sha256sum or shasum" >&2; exit 1; fi
( cd "$x" && find . -type f ! -name manifest | LC_ALL=C sort | while read -r f; do printf '%s  %s\n' "$(hash "$f")" "$f"; done ) > "$x/manifest"
# root-owned entries, whichever tar builds it (macOS bsdtar, Linux GNU tar), as the other extras are; macOS's
# extended attributes would come along as ._ files, which no extra may hold
_xt=
tar --version 2>/dev/null | grep -qi bsdtar && _xt=--no-xattrs
COPYFILE_DISABLE=1 tar -czf "$OUT" $_xt --owner=0 --group=0 --numeric-owner -C "$x" . ||
    { echo "make-openclash-extra: could not write $OUT" >&2; exit 1; }
echo "openclash extra ($TAG): $OUT, $(du -h "$OUT" | cut -f1)" >&2
