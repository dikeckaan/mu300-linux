#!/bin/sh
# Build the MU300 OpenWrt (or ImmortalWrt) rootfs tarball (runs on the host; needs Docker with arm64 support).
#   openwrt/build-rootfs.sh OUT.tar.gz
#   MU300_FLAVOUR=immortalwrt openwrt/build-rootfs.sh OUT.tar.gz
# Inputs (same as rootfs/assemble.sh, all optional except modules):
#   out/modules/*.ko  out/modules.builtin*  firmware/  android-subset/  android-gpu-subset/
#   tools/logdw/logdw  tools/bt-init/mu300-bt-init  tools/gpu/cltest  busybox (static, full)
#   xray, hev-socks5-tunnel (tools/fetch-xray.sh) and sing-box (tools/fetch-sing-box.sh), for mu300-vpn
#   upstream/out/modules/*.ko (optional: out-of-tree WCN modules for the mainline 6.18 kernel)
set -eu
FLAVOUR=${MU300_FLAVOUR:-openwrt}
case $FLAVOUR in
    openwrt)     VER=${MU300_WRT_VER:-25.12.5}; BASEURL=https://downloads.openwrt.org/releases ;;
    # ImmortalWrt is an OpenWrt fork: same package manager, same layout, more drivers and LuCI apps
    immortalwrt) VER=${MU300_WRT_VER:-25.12.2}; BASEURL=https://downloads.immortalwrt.org/releases ;;
    *) echo "unknown flavour '$FLAVOUR' (openwrt or immortalwrt)" >&2; exit 1 ;;
esac
KREL=5.4.254-gb50db5b6224c
OUT=${1:-mu300-$FLAVOUR-$VER-rootfs.tar.gz}
TOP=$(cd "$(dirname "$0")/.." && pwd)
# build inputs (out/, firmware/, android-subset/, tools binaries, busybox) may live outside the checkout
IN=${MU300_INPUTS:-$TOP}
TARBALL=$FLAVOUR-$VER-armsr-armv8-rootfs.tar.gz
URL=$BASEURL/$VER/targets/armsr/armv8

cd "$TOP"
if [ ! -f "openwrt/$TARBALL" ]; then
    curl -fL -o "openwrt/$TARBALL" "$URL/$TARBALL"
fi
want=$(curl -fsL "$URL/sha256sums" | sed -n "s/^\([0-9a-f]*\) \*$TARBALL$/\1/p")
have=$(shasum -a 256 "openwrt/$TARBALL" 2>/dev/null || sha256sum "openwrt/$TARBALL")
[ "${have%% *}" = "$want" ] || { echo "checksum mismatch for $TARBALL" >&2; exit 1; }
docker import --platform linux/arm64 "openwrt/$TARBALL" mu300-$FLAVOUR-base:$VER >/dev/null
# OpenWrt ships an unsigned regulatory.db; this kernel requires the signed database (wens key), so take Debian/Ubuntu's
REGDB=$(mktemp -d)
docker run --rm --platform linux/arm64 -v "$REGDB":/o ubuntu:26.04 sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq wireless-regdb >/dev/null && cp /usr/lib/firmware/regulatory.db /usr/lib/firmware/regulatory.db.p7s /o/"

opt() { [ -e "$IN/$1" ] && echo "-v $IN/$1:/in/$2:ro" || true; }

# The required input first, with a readable message: without it docker fails somewhere inside the build.
ls "$IN/out/modules"/*.ko >/dev/null 2>&1 || {
    echo "no kernel modules in $IN/out/modules - build them first (kernel/build-linux.sh), or point" >&2
    echo "MU300_INPUTS at the directory that has out/modules, firmware/ and android-subset/." >&2
    exit 1
}
# The optional ones decide whether the image can use the modem, Wi-Fi, the GPU or the VPN at all. Missing ones
# used to be skipped silently, which produces an image that boots and then does nothing useful.
for o in firmware android-subset android-gpu-subset tools/logdw/logdw tools/bt-init/mu300-bt-init tools/gpu/cltest busybox sing-box xray hev-socks5-tunnel upstream/out/modules; do
    [ -e "$IN/$o" ] && echo "  + $o" || echo "  - $o   (missing: the image is built without it)"
done
# shellcheck disable=SC2046
docker run --rm --platform linux/arm64 \
  -v "$TOP/rootfs/overlay/opt/mu300":/in/opt-mu300:ro -v "$TOP/rootfs/overlay/etc/mu300/vpn.conf.example":/in/vpn.conf.example:ro -v "$TOP/openwrt/overlay":/in/overlay:ro \
  -v "$TOP/boot/module-order.txt":/in/module-order.txt:ro -v "$IN/out/modules":/in/modules:ro \
  $(opt out/modules.builtin modules.builtin) $(opt out/modules.builtin.modinfo modules.builtin.modinfo) \
  $(opt firmware firmware) $(opt android-subset android-subset) $(opt android-gpu-subset android-gpu-subset) \
  $(opt tools/logdw/logdw logdw) $(opt tools/bt-init/mu300-bt-init bt-init) $(opt tools/gpu/cltest cltest) \
  $(opt busybox busybox) $(opt sing-box sing-box) $(opt xray xray) $(opt hev-socks5-tunnel hev-socks5-tunnel) $(opt upstream/out/modules mainline-modules) -v "$TOP/openwrt":/out -v "$REGDB":/in/regdb:ro \
  -e KREL=$KREL -e OUT="$(basename "$OUT")" -e MU300_VERSION="${MU300_VERSION:-dev}" mu300-$FLAVOUR-base:$VER /bin/sh -eu -c '
mkdir -p /var/lock /var/run /tmp
apk update >/dev/null
# openssl-util: mu300-vpn fetches the VPN server certificate with it to pin, for links that ask for allowInsecure
apk add wpad-basic-mbedtls wifi-scripts iwinfo wireless-regdb iw bash ip-full coreutils-stty openssl-util >/dev/null
# ujail drops CAP_PERFMON (38), which this 5.4 kernel does not know: jailed services (dnsmasq, ntpd) crash-loop
apk del procd-ujail procd-seccomp >/dev/null 2>&1 || true
# online firmware upgrades flash whole-disk armsr images: that would overwrite the eMMC, so remove them
apk del luci-app-attendedsysupgrade attendedsysupgrade-common owut >/dev/null 2>&1 || true
R=/build/root; mkdir -p $R
# copy the live filesystem of this container (the OpenWrt rootfs plus packages), without runtime mounts
for e in /*; do
    case "$e" in /proc|/sys|/dev|/build|/in|/out|/tmp) continue ;; esac
    cp -a "$e" $R/
done
mkdir -p $R/proc $R/sys $R/dev $R/tmp $R/run $R/opt
# Docker bind-mounts these three into the container, so the copy above picks up the build host versions:
# a resolv.conf pointing at the internal Docker DNS (which broke every lookup the device itself made), a hosts
# file with the container id, and a hostname that was the container id. Put the OpenWrt ones back.
# (no apostrophes in here: this whole block is one single-quoted argument to sh -c)
ln -sf /tmp/resolv.conf $R/etc/resolv.conf
printf "127.0.0.1\tlocalhost\n\n::1\tlocalhost ip6-localhost ip6-loopback\nff02::1\tip6-allnodes\nff02::2\tip6-allrouters\n" > $R/etc/hosts
printf "mu300\n" > $R/etc/hostname   # the real one comes from uci (etc/uci-defaults/90-mu300)
cp -a /in/opt-mu300 $R/opt/mu300
cp -a /in/overlay/. $R/
mv $R/sbin/sysupgrade $R/sbin/sysupgrade.openwrt && mv $R/usr/libexec/mu300-sysupgrade $R/sbin/sysupgrade
M=$R/lib/modules/$KREL; mkdir -p $M
cp /in/modules/*.ko $M/          # ubox kmodloader expects the modules flat in /lib/modules/<release>/
for f in modules.builtin modules.builtin.modinfo; do [ -e /in/$f ] && cp /in/$f $M/; done
[ -d /in/firmware ] && { mkdir -p $R/lib/firmware; cp -a /in/firmware/. $R/lib/firmware/; }
# tools shared with the Ubuntu image look under /usr/lib/firmware (mu300-bt-init, for one); OpenWrt keeps
# firmware in /lib/firmware
mkdir -p $R/usr/lib && ln -sfn ../../lib/firmware $R/usr/lib/firmware
cp /in/regdb/regulatory.db /in/regdb/regulatory.db.p7s $R/lib/firmware/
if [ -d /in/android-subset ]; then
    mkdir -p $R/opt/mu300/android && cp -a /in/android-subset/. $R/opt/mu300/android/
    mv $R/opt/mu300/android/dev/__properties__ $R/opt/mu300/android/dev-properties && rmdir $R/opt/mu300/android/dev
fi
[ -d /in/android-gpu-subset ] && cp -a /in/android-gpu-subset/. $R/opt/mu300/android/
[ -e /in/cltest ] && { mkdir -p $R/opt/mu300/android/system/bin; cp /in/cltest $R/opt/mu300/android/system/bin/cltest; chmod 755 $R/opt/mu300/android/system/bin/cltest; }
[ -e /in/logdw ] && { cp /in/logdw $R/opt/mu300/bin/logdw; chmod 755 $R/opt/mu300/bin/logdw; }
[ -e /in/bt-init ] && { cp /in/bt-init $R/opt/mu300/bin/mu300-bt-init; chmod 755 $R/opt/mu300/bin/mu300-bt-init; }
[ -f /in/sing-box ] && { cp /in/sing-box $R/opt/mu300/bin/sing-box; chmod 755 $R/opt/mu300/bin/sing-box; }
for b in xray hev-socks5-tunnel; do [ -f /in/$b ] && { cp /in/$b $R/opt/mu300/bin/$b; chmod 755 $R/opt/mu300/bin/$b; }; done
# full static busybox for the tools OpenWrt busybox leaves out (od, timeout, mountpoint, losetup, rfkill, telnetd)
if [ -e /in/busybox ]; then
    cp /in/busybox $R/opt/mu300/bin/busybox; chmod 755 $R/opt/mu300/bin/busybox
    mkdir -p $R/opt/mu300/busybox-bin
    for a in od timeout losetup telnetd getty; do
        chroot $R /bin/sh -c "command -v $a" >/dev/null 2>&1 && continue
        ln -sf ../bin/busybox $R/opt/mu300/busybox-bin/$a
    done
fi
mkdir -p $R/etc/mu300
# the VPN is configured the same way on both systems, and mu300-toolkit copies this to start a vpn.conf
cp /in/vpn.conf.example $R/etc/mu300/vpn.conf.example
printf "%s\n" "${MU300_VERSION:-dev}" > $R/etc/mu300/image-version
# enable the services (rc.common "enable" needs ubus, which is not running in the build container)
# accounts still those of the image until an installer or mu300-update puts the device ones in place
: > $R/etc/.mu300-accounts-from-image
for s in mu300-accounts mu300-vendor mu300-hw mu300-post mu300-toolkit mu300-atd mu300-modem-log mu300-wifi-client; do
    n=$(sed -n "s/^START=//p" $R/etc/init.d/$s)
    ln -sf ../init.d/$s $R/etc/rc.d/S$n$s
done
# busybox PATH is /usr/sbin:/usr/bin:/sbin:/bin, so the commands go into /usr/bin
for c in mu300-toolkit mu300-next-boot mu300-os mu300-update mobile-data mu300-at mu300-vpn wifi-client; do ln -sf /opt/mu300/bin/$c $R/usr/bin/$c; done
# no kernel of its own: OpenWrt kmods (6.12) and grub are unused on this device
rm -rf $R/lib/modules/6.* $R/boot
# out-of-tree modules for the experimental mainline kernel (upstream/)
if ls /in/mainline-modules/*.ko >/dev/null 2>&1; then
    # the release the modules were built for (their vermagic), not a version written down here
    krel=$(for f in /in/mainline-modules/*.ko; do tr "\0" "\n" < $f | sed -n "s/^vermagic=\([^ ]*\) .*/\1/p"; break; done)
    [ -n "$krel" ] && mkdir -p $R/lib/modules/$krel && cp /in/mainline-modules/*.ko $R/lib/modules/$krel/
fi
cd $R && tar -czf /out/$OUT .
ls -la /out/$OUT'
rm -rf "$REGDB"
