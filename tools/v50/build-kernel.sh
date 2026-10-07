#!/bin/sh
# Compile the existing 6.18 mainline port on a Linux host with ARM64 Docker support.
set -eu
KV=${1:-6.18.55}
case $KV in 6.18.*) ;; *) echo 'V50 stable profile requires 6.18.x' >&2; exit 2 ;; esac
printf '%s' "$KV" | grep -Eq '^6\.18\.[0-9]+$' || exit 2
TOP=$(cd "$(dirname "$0")/../.." && pwd)
command -v docker >/dev/null || { echo 'Linux Docker is required' >&2; exit 1; }
docker info >/dev/null
docker build -t mu300-mainline-build "$TOP/upstream"
# A dedicated volume prevents experimental builds from altering the stable kernel tree.
docker volume create mu300-v50-mainline >/dev/null
for script in build.sh build-modules.sh; do
    docker run --rm -e KV="$KV" -v mu300-v50-mainline:/src -v "$TOP/upstream":/work \
        mu300-mainline-build bash "/work/$script"
done
echo 'Kernel and matching modules are under upstream/out. Use upstream/make-bundle.sh to package them.'
