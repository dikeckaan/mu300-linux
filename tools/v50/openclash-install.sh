#!/bin/sh
# Explicit local inputs, supplied by the user and checked before apk executes.
# Usage: sh openclash-install.sh PACKAGE.apk SHA256 CORE SHA256
set -eu
[ "$(id -u)" = 0 ] && [ -f /etc/openwrt_release ] || { echo 'Run as root on OpenWrt' >&2; exit 1; }
[ "$#" = 4 ] || { echo 'usage: openclash-install.sh PACKAGE.apk SHA256 CORE SHA256' >&2; exit 2; }
for hash in "$2" "$4"; do
    [ "${#hash}" = 64 ] && ! printf '%s' "$hash" | grep -q '[^0-9a-f]' || exit 2
done
[ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo 'APK hash mismatch' >&2; exit 1; }
[ "$(sha256sum "$3" | cut -d' ' -f1)" = "$4" ] || { echo 'Core hash mismatch' >&2; exit 1; }
[ -c /dev/net/tun ] || { echo 'TUN unavailable' >&2; exit 1; }
# Verify actual TUN operation rather than trusting a metadata package.
ip tuntap add dev v50tuncheck mode tun
ip tuntap del dev v50tuncheck mode tun
chmod 0755 "$3"
"$3" -v
if apk info -e dnsmasq >/dev/null 2>&1; then
    echo 'Replace dnsmasq with dnsmasq-full in a backed-up maintenance session first.' >&2
    exit 1
fi
apk info -e dnsmasq-full >/dev/null 2>&1 || { echo 'Install compatible dnsmasq-full first' >&2; exit 1; }
# OpenWrt feed kmods must match uname -r. Do not spoof missing kernel features.
for name in kmod-tun kmod-nf-conntrack-netlink; do
    apk info -e "$name" >/dev/null 2>&1 || {
        echo "Prepare $name for kernel $(uname -r); see docs/v50/OPENCLASH.zh-CN.md" >&2
        exit 1
    }
done
apk add curl ruby ruby-yaml unzip luci-compat
apk add --allow-untrusted "$1"
uci set openclash.config.enable=0
uci commit openclash
/etc/init.d/openclash stop || true
/etc/init.d/openclash disable
mkdir -p /etc/openclash/core
cp "$3" /etc/openclash/core/clash_meta
chmod 0755 /etc/openclash/core/clash_meta
echo 'Installed with proxy disabled. Apply the TUN compatibility patch, import configuration and validate first.'
