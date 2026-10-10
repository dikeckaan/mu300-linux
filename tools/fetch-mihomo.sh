#!/bin/sh
# Download the pinned mihomo (Clash.Meta) release (linux arm64) that runs mu300-vpn's mihomo profiles and verify it.
#   tools/fetch-mihomo.sh [OUTDIR]   (default: .; writes OUTDIR/mihomo, picked up by tools/make-extra.sh vpn-mihomo)
set -eu
VER=1.19.32
SHA256=9dd862e28b46ff7d775f169cceebc28deccaa0a9e804237d421cd2571e0caba0
NAME=mihomo-linux-arm64-v$VER.gz
OUT=${1:-.}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/$NAME" "https://github.com/MetaCubeX/mihomo/releases/download/v$VER/$NAME"
have=$(shasum -a 256 "$tmp/$NAME" 2>/dev/null || sha256sum "$tmp/$NAME")
[ "${have%% *}" = "$SHA256" ] || { echo "checksum mismatch for $NAME" >&2; exit 1; }
gzip -dc "$tmp/$NAME" > "$tmp/mihomo"
install -m 755 "$tmp/mihomo" "$OUT/mihomo"
echo "mihomo $VER -> $OUT/mihomo"
