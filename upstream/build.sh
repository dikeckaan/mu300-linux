#!/bin/bash
# Build mainline for the MU300 inside mu300-mainline-build: Image + DTB. /work = this directory, /src = kernel tree volume
set -eo pipefail
KV=${KV:-6.18.54}
# the kernel source, fetched once into the volume and checked against kernel.org's checksum list
if [ ! -d /src/linux-$KV ]; then
    base=https://cdn.kernel.org/pub/linux/kernel/v${KV%%.*}.x
    cd /src
    curl -fsSLO "$base/linux-$KV.tar.xz"
    curl -fsSL "$base/sha256sums.asc" | grep " linux-$KV.tar.xz\$" | sha256sum -c - || { rm -f linux-$KV.tar.xz; exit 1; }
    tar -xJf linux-$KV.tar.xz && rm linux-$KV.tar.xz
fi
cd /src/linux-$KV
# MU300 patches (idempotent); MU300_PROBE_STAGE=N adds the boot-stage reset probe (debug)
python3 /work/port/install.py .
[ -n "${MU300_PROBE_STAGE:-}" ] && python3 /work/debug/install-probe.py . "$MU300_PROBE_STAGE"
# a patch either applies or is applied already; anything else stops the build (it used to be skipped silently)
for p in /work/patches/*.patch; do
    if patch -p1 -N -s --dry-run < "$p" >/dev/null 2>&1; then patch -p1 -N -s < "$p"
    elif patch -p1 -R -s -f --dry-run < "$p" >/dev/null 2>&1; then :
    else echo "patch does not apply to $KV: $p" >&2; exit 1; fi
done
O=/src/out-$KV
mkdir -p $O
make O=$O ARCH=arm64 allnoconfig >/dev/null
./scripts/kconfig/merge_config.sh -m -O $O $O/.config /work/mu300-mainline.config >/dev/null
make O=$O ARCH=arm64 olddefconfig >/dev/null
# options Kconfig did not take; ones known not to exist in this kernel are listed in config-ignored.txt, any
# other one stops the build (a silently dropped option has cost a working feature before)
bad=
while IFS= read -r l; do
  case "$l" in CONFIG_*=*) k=${l%%=*}; v=${l#*=}; g=$(grep -E "^$k=" $O/.config | cut -d= -f2- || true);
    [ "$v" = n ] && { grep -q "^$k=y" $O/.config && bad="$bad\nNOT DISABLED: $k" || true; continue; }
    [ "$g" = "$v" ] || grep -qx "$k" /work/config-ignored.txt 2>/dev/null || bad="$bad\nNOT SET: $k want $v got ${g:-unset}";; esac
done < /work/mu300-mainline.config
[ -z "$bad" ] || { printf "config options not taken:$bad\n" >&2; exit 1; }
# on failure show the compiler's own messages: a plain grep for "error" also matches object names like
# fdt_strerror.o and used to fill the report with those
make O=$O ARCH=arm64 -j"$(nproc)" Image > $O/build.log 2>&1 || {
    grep -n -E ": (fatal )?error: |-Werror|treated as errors|undefined reference|No such file|Killed|internal compiler error|\*\*\*" -A3 $O/build.log | head -80 || true
    echo "--- end of build.log:"; tail -25 $O/build.log || true
    exit 1
}
cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp -I include -I scripts/dtc/include-prefixes \
  /work/dts/ums9620-mu300.dts | dtc -I dts -O dtb -o $O/ums9620-mu300.dtb -
mkdir -p /work/out
cp $O/arch/arm64/boot/Image $O/ums9620-mu300.dtb /work/out/
ls -la /work/out
