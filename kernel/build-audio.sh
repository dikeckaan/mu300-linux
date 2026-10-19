#!/bin/sh
# Build Unisoc's ASoC/AGDSP driver set against the 5.4 kernel this project already builds.
#
# These are the drivers behind real call audio: the audio DSP loader, the VBC voice DAI and the machine card
# that binds the board's sound@0 node. They are not part of the stock F50 module set, because ZTE ships this
# board with audio disabled - but the device tree nodes are all there, fully populated, and the kernel config
# already has CONFIG_SND_SOC, SND_SOC_COMPRESS and SND_SOC_TOPOLOGY built in.
#
#   kernel/build-audio.sh [OUT]       default: work/k54/audio-modules
#
# Needs kernel/build-all.sh to have run first: it builds against /src/out-linux in the mu300-kernel volume.
#
# Three things about this build are not obvious and cost an evening each:
#
#   * Order matters and one pass is not enough. audio_sipc needs symbols from agdsp_access, the DAIs need the
#     platform, the card needs all of them. Dependencies are resolved by building repeatedly and handing every
#     Module.symvers produced so far to the next attempt.
#   * A failed attempt has to be cleaned before it is retried. The leftover objects link a second time and the
#     error is "duplicate symbol: __this_module", which says nothing about the real problem.
#   * The UMP9620 codec only compiles with BSP_KERNEL_DEFCONFIG=sprd_qogirn6pro_defconfig. Its Kbuild hides
#     -DCONFIG_SND_SOC_UNISOC_CODEC_UMP9620 behind that, and without it the failure is an implicit declaration
#     of TO_STRING several hundred lines away.
#
# Two directories never build and should not: dmaengine_2stage_pcm and i2s are for older Unisoc SoCs (their
# VBC_DAI_NORMAL comes from the pike2/sharkl3/sharkle headers), and this one uses VBC v4.
set -eu
TOP=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$TOP/work/k54/audio-modules}
VOL=mu300-kernel
MODULES_REPO=https://github.com/realme-kernel-opensource/realme_C51_C53_Narzo-N53-AndroidT-kernel-source.git
MODULES_REV=4381465ccaf87fcf3215b9cd42f4a685df40e5e0

docker build -q -t mu300-kbuild "$TOP/kernel" >/dev/null
W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT

cp -R "$TOP/kernel/." "$W/"
docker run --rm -v "$VOL":/src -v "$W":/work \
  -e MODULES_REPO="$MODULES_REPO" -e MODULES_REV="$MODULES_REV" \
  mu300-kbuild bash -euc '
M=kernel_modules/kernel5.4
cd /src/realme
git sparse-checkout set $M/wcn/wlan/wlan_combo $M/wcn/bluetooth/driver $M/gpu/natt/mali $M/audio_driver
git checkout -q "$MODULES_REV" 2>/dev/null || true
A=/src/ext-audio
[ -d $A ] || cp -r /src/realme/$M/audio_driver $A
# audio_mem needs a way to be told where the DSP regions are, since this board does not describe them
if ! grep -q audio_mem_region $A/sprd_audio/audiomem/audio_mem.c; then
    (cd $A && patch -p1 -s -f < /work/patches/audio-mem-fixed-region.patch)
    find $A/sprd_audio/audiomem -name "*.o" -delete 2>/dev/null || true
    rm -f $A/sprd_audio/audiomem/*.ko
fi
# an AGDSP image from another board needs the absolute shm addresses moved to match it
if ! grep -q audio_mem_apply_shm_shift $A/sprd_audio/audiomem/audio_mem.c; then
    (cd $A && patch -p1 -s -f < /work/patches/audio-mem-shm-shift.patch)
    find $A/sprd_audio/audiomem -name "*.o" -delete 2>/dev/null || true
    rm -f $A/sprd_audio/audiomem/*.ko
fi
# MCDT skips every register write when its enable bit is clear, and on this board nothing sets it
if ! grep -q "enabled the agcp mcdt clock" $A/sprd_audio/mcdt/mcdt_r2p0/mcdt_hw_r2p0.c; then
    (cd $A && patch -p1 -s -f < /work/patches/mcdt-enable-clock.patch)
    find $A/sprd_audio/mcdt -name "*.o" -delete 2>/dev/null || true
    rm -f $A/sprd_audio/mcdt/mcdt_r2p0/*.ko
fi
# and a codec that never arrives must not take the whole card down with it
if ! grep -q dummy_on_defer $A/sprd/machine/sprd_card/sprd-asoc-card-utils.c; then
    (cd $A && patch -p1 -s -f < /work/patches/sprd-card-dummy-on-defer.patch)
    find $A/sprd/machine/sprd_card -name "*.o" -delete 2>/dev/null || true
    rm -f $A/sprd/machine/sprd_card/*.ko
fi
# Three fixes from the Rongyue E5 port of the same drivers (kanoqwq/e5-linux, same SoC family, measured there):
# period events from an hrtimer because the AGCP DMA interrupt never arrives, no DMA position read while the
# AGCP domain is asleep, and the DSP front ends offered only the formats and layouts the DSP takes.
# And two of ours: a DSP reply left behind by a killed command no longer fails the next one (FINDINGS 188), and
# the MCDT watermark and DMA fragment of the voice capture tap are module parameters, voice_c_wmk and voice_c_frag.
for p in audio-pcm-period-timer:sprd_pcm_period_tick:sprd/platform/dmaengine_pcm \
         audio-pcm-pointer-agcp-access:last_pointer:sprd/platform/dmaengine_pcm \
         audio-fe-dai-formats:fe_dai_uses_mcdt:sprd/dai/vbc/v4/fe_dai \
         audio-sipc-stale-reply:dropped:sprd_audio/audiosipc \
         audio-fe-voice-c-mcdt-params:voice_c_wmk:sprd/dai/vbc/v4/fe_dai; do
    name=${p%%:*}; rest=${p#*:}; mark=${rest%%:*}; dir=${rest#*:}
    if ! grep -rq "$mark" $A/$dir; then
        (cd $A && patch -p1 -s -f < /work/patches/$name.patch)
        find $A/$dir $A/sprd_audio/agdsp_access -name "*.o" -delete 2>/dev/null || true
        rm -f $A/$dir/*.ko $A/sprd_audio/agdsp_access/*.ko
    fi
done
cd /src/zte-u30air

# headers these Kbuilds include by name without putting the directory on their own path
INC="-I$A/sprd_audio/agdsp_access -I$A/sprd_audio/audiomem -I$A/sprd_audio/audiosipc"
INC="$INC -I$A/sprd/include -I$A/sprd/platform/include -I$A/sprd/platform/dmaengine_pcm"
INC="$INC -I$A/sprd/codec/sprd -I$A/sprd/dai/vbc/v4/vbc_dai"

DIRS="sprd_audio/agdsp_access sprd_audio/audiomem sprd_audio/audiosipc sprd_audio/audiocpboot
sprd_audio/audiodvfs sprd_audio/audiodspdump sprd_audio/mcdt/mcdt_r2p0 sprd_audio/audio_pipe
sprd_audio/audiopipe sprd_audio/saudio
sprd/platform/platform_routing sprd/platform/dmaengine_pcm sprd/platform/compr_2stage_dma
sprd/dai/sprd_dai sprd/dai/vaudio sprd/dai/vbc/v4/vbc_dai sprd/dai/vbc/v4/fe_dai
sprd/codec/sprd/ump9620/power sprd/codec/sprd/ump9620/power_dev sprd/codec/sprd/ump9620/codec
sprd/codec/dummy-codec sprd/codec/sprd/ucp1301
sprd/machine/sprd_card"

syms() { find $A -name Module.symvers | tr "\n" " "; }
build() {
    d=$A/$1
    [ -f "$d/Kbuild" ] || return 0
    ls "$d"/*.ko >/dev/null 2>&1 && return 0          # already built in an earlier pass
    find "$d" -name "*.o" -delete 2>/dev/null || true # or the retry links __this_module twice
    rm -f "$d"/*.mod "$d"/*.mod.c "$d"/Module.symvers "$d"/modules.order 2>/dev/null || true
    make O=/src/out-linux ARCH=arm64 LLVM=1 LLVM_IAS=1 CC=clang LD=ld.lld -j"$(nproc)" \
        M=$d KCFLAGS="$INC" BSP_KERNEL_DEFCONFIG=sprd_qogirn6pro_defconfig \
        KBUILD_EXTRA_SYMBOLS="$(syms)" modules >/tmp/b.log 2>&1 \
        || echo "   still unbuilt: $1 ($(grep -m1 -E "error:|undefined!" /tmp/b.log | cut -c1-110))"
}
for pass in 1 2 3; do
    echo "==> pass $pass"
    for d in $DIRS; do build "$d"; done
done
mkdir -p /work/out
find $A -name "*.ko" -exec cp {} /work/out/ \;
llvm-strip --strip-debug /work/out/*.ko 2>/dev/null || true
echo "$(ls /work/out/*.ko | wc -l) audio modules"
'
mkdir -p "$OUT"
rm -f "$OUT"/*.ko
cp "$W"/out/*.ko "$OUT/"
echo "$(ls "$OUT"/*.ko | wc -l) modules in $OUT"
