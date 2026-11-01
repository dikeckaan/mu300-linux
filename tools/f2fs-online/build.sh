#!/bin/sh
# Build mu300-f2fs-online (kanoqwq's online F2FS shrink helper) for the device's Android: one static aarch64 binary
# (musl), in a pinned Alpine image with fixed flags, so the same source gives the same bytes. The native test
# (test-f2fs-online.c) runs first, in the same image.
#   tools/f2fs-online/build.sh [OUT]   OUT defaults to tools/f2fs-online/mu300-f2fs-online (the copy in git, which
#                                      the installers push); needs docker with arm64 support
# tests/test_online_shrink.py checks that the copy in git is this build of this source (SHA256SUMS next to it).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$HERE/mu300-f2fs-online}
IMG=alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc
mkdir -p "$(dirname "$OUT")"
o=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cp "$HERE/mu300-f2fs-online.c" "$HERE/test-f2fs-online.c" "$tmp/"
docker run --rm --platform linux/arm64 -v "$tmp":/w -w /w "$IMG" /bin/sh -eu -c '
apk add -q gcc musl-dev linux-headers
F="-O2 -Wall -Wextra -Werror -ffile-prefix-map=/w=. -fno-ident"
gcc $F test-f2fs-online.c -o /tmp/test && /tmp/test >/dev/null
gcc $F -static -Wl,--build-id=none mu300-f2fs-online.c -o mu300-f2fs-online
strip mu300-f2fs-online
'
cp "$tmp/mu300-f2fs-online" "$o"
chmod 755 "$o"
if [ "$o" = "$HERE/mu300-f2fs-online" ]; then
    (cd "$HERE" && for f in mu300-f2fs-online.c mu300-f2fs-online; do
        printf '%s  %s\n' "$( (sha256sum "$f" 2>/dev/null || shasum -a 256 "$f") | cut -d' ' -f1)" "$f"; done) > "$HERE/SHA256SUMS"
fi
echo "$o: $(wc -c < "$o") bytes, sha256 $( (sha256sum "$o" 2>/dev/null || shasum -a 256 "$o") | cut -d' ' -f1)"
