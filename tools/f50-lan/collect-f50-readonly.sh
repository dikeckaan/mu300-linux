#!/bin/sh
set -eu
export LC_ALL=C

release=$(uname -r)
printf 'kernel=%s\narch=%s\n' "$release" "$(uname -m)"
if [ -r /etc/os-release ]; then
    grep -E '^(VERSION_ID|OPENWRT_ARCH)=' /etc/os-release || :
fi
if [ -r /proc/config.gz ] && gzip -t /proc/config.gz 2>/dev/null; then
    printf 'config.raw.sha256='
    gzip -dc /proc/config.gz | sha256sum | cut -d ' ' -f1
    printf 'config.sorted.sha256='
    gzip -dc /proc/config.gz | grep -E '^(CONFIG_|# CONFIG_)' | sort | sha256sum | cut -d ' ' -f1
    gzip -dc /proc/config.gz | grep -E '^(# )?CONFIG_(MODULES|MODULE_UNLOAD|MODVERSIONS|MODULE_SIG(_FORCE|_ALL)?|SND_SOC(_SPRD)?|SND(_PCM|_COMPRESS_OFFLOAD|_DMAENGINE_PCM)?|CC_VERSION_TEXT|LOCALVERSION)(=| is not set)' || :
else
    echo 'config=unavailable'
fi
for name in audio-sipc audio_pipe_voice audio_pipe_voiceproc audiocp_boot sprd-pcm-audio; do
    path=/sys/bus/platform/devices/$name
    state=absent
    if [ -e "$path" ]; then
        state=unbound
        [ ! -L "$path/driver" ] || state=bound
    fi
    printf '%s=%s\n' "$name" "$state"
done
for path in "/lib/modules/$release/modules.dep" "/lib/modules/$release/build/Module.symvers" /opt/mu300/bin/mu300-audio-dsp; do
    state=absent
    [ ! -r "$path" ] || state=present
    printf '%s=%s\n' "$path" "$state"
done
if [ -r /proc/asound/cards ]; then
    awk '/^ *[0-9]+ \[/{cards++; if ($0 ~ /\[Loopback +\]/) loopback++}
        END{printf "alsa.cards=%d\nalsa.loopback_cards=%d\n", cards, loopback}' /proc/asound/cards
fi
if [ -r /proc/asound/pcm ]; then
    awk '/^[0-9]+-[0-9]+:/{print "alsa.pcm=" substr($1,1,length($1)-1)}' /proc/asound/pcm
fi
