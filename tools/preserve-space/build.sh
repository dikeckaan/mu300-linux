#!/bin/sh
# Optional helper only; never added to a release/boot image by this change.
set -eu
OUT=${1:?usage: tools/preserve-space/build.sh OUT (Docker with arm64 support)}
TOP=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
mkdir -p "$(dirname "$OUT")"
OUT_DIR=$(CDPATH= cd -- "$(dirname "$OUT")" && pwd)
NAME=$(basename "$OUT")
IMG=alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc
docker run --rm --platform linux/arm64 -v "$TOP":/src:ro -v "$OUT_DIR":/out "$IMG" sh -eu -c '
    apk add -q build-base linux-headers
    cc -std=c11 -Os -Wall -Wextra -Werror -static -Wl,--build-id=none /src/preserve-space.c -o /out/"$1"
' sh "$NAME"
chmod 755 "$OUT"
