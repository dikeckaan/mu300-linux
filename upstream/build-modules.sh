#!/bin/bash
# Build the out-of-tree vendor modules (WCN) against the mainline tree built by build.sh.
# Run inside the mu300-mainline-build container: bash /work/build-modules.sh [module-dir...]
set -eo pipefail
KV=${KV:-6.18.54}
[ "$(uname -m)" = aarch64 ] || export CROSS_COMPILE=${CROSS_COMPILE:-aarch64-linux-gnu-}
K=/src/linux-$KV
O=/src/out-$KV
OUT=/work/${OUTDIR:-out}   # as in build.sh
# every out-of-tree module, in dependency order (wlan/bt use wcn_bsp, the PMIC watchdog and Mali the modem's headers)
mods=${*:-wcn_bsp sprd_wlan_combo sprdbt_tty sprd_modem sprd_pmic_wdt mali}
mkdir -p $OUT/modules
# a full build starts clean, so no module of another kernel release ends up next to the new ones
[ $# -gt 0 ] || rm -f $OUT/modules/*.ko $OUT/modules/*.log
# Module.symvers for the built-in exports (pcie-sprd etc.)
make -C $K O=$O ARCH=arm64 -j"$(nproc)" modules > $O/modules.log 2>&1 || { tail -20 $O/modules.log; exit 1; }
extra=
for m in $mods; do
    rm -rf /src/mod-build/$m && mkdir -p /src/mod-build && cp -r /work/modules/$m /src/mod-build/$m
    # wlan/bt use wcn_bsp's exports and its vendor headers (../wcn_bsp/kinclude)
    [ -d /src/mod-build/wcn_bsp ] || cp -r /work/modules/wcn_bsp /src/mod-build/wcn_bsp
    # the PMIC watchdog talks to pm_sys over SIPC, so it needs the modem stack's headers next to it
    [ -d /src/mod-build/sprd_modem ] || cp -r /work/modules/sprd_modem /src/mod-build/sprd_modem
    # the Mali DDK needs its own configuration switches (same ones the 5.4 build uses)
    margs=
    kcflags=
    [ "$m" = mali ] && kcflags="-I/src/mod-build/mali/kinclude"
    # the Mali driver calls Trusty for protected mode, so it needs the vendor trusty headers that ship with
    # the modem modules
    [ "$m" = mali ] && [ ! -d /src/mod-build/mali/kinclude ] && cp -r /work/modules/sprd_modem/kinclude /src/mod-build/mali/kinclude
    [ "$m" = mali ] && margs="src=/src/mod-build/mali CONFIG_MALI_MIDGARD=m CONFIG_MALI_PLATFORM_NAME=qogirn6pro CONFIG_MALI_DEVFREQ=y CONFIG_DEVFREQ_THERMAL=y CONFIG_MALI_DEBUG=n CONFIG_MALI_FENCE_DEBUG=n BUILD=no"
    make -C $O ARCH=arm64 M=/src/mod-build/$m KBUILD_EXTRA_SYMBOLS="$extra" KCFLAGS="$kcflags" $margs -j"$(nproc)" modules 2>&1 | tee $OUT/modules/$m.log
    [ -f /src/mod-build/$m/Module.symvers ] && extra="$extra /src/mod-build/$m/Module.symvers"
    find /src/mod-build/$m -name '*.ko' -exec cp {} $OUT/modules/ \;
done
ls -la $OUT/modules/*.ko
