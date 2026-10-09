#!/bin/sh
# Build the MU300 OpenWrt (or ImmortalWrt) rootfs tarball (runs on the host; needs Docker with arm64 support).
#   openwrt/build-rootfs.sh OUT.tar.gz
#   MU300_FLAVOUR=immortalwrt openwrt/build-rootfs.sh OUT.tar.gz
#   MU300_SYSTEM=openwrt-luci openwrt/build-rootfs.sh OUT.tar.gz   (OpenWrt with the MU300 control panel and Aurora)
# OUT is written into openwrt/ under its base name.
# Inputs (same as rootfs/assemble.sh, all optional except modules):
#   out/modules/*.ko  out/modules.builtin*  firmware/  android-subset/  android-gpu-subset/
#   tools/logdw/logdw  tools/bt-init/mu300-bt-init  tools/keys/mu300-keys  tools/gpu/cltest  busybox (static, full)
#   upstream/out/modules/*.ko (optional: out-of-tree WCN modules for the mainline 6.18 kernel)
# openwrt-luci only: MU300_LUCI_THEME_APK, a local copy of the pinned Aurora .apk (offline builds; else downloaded)
set -eu
FLAVOUR=${MU300_FLAVOUR:-openwrt}
case $FLAVOUR in
    openwrt)     VER=${MU300_WRT_VER:-25.12.5}; BASEURL=https://downloads.openwrt.org/releases ;;
    # ImmortalWrt is an OpenWrt fork: same package manager, same layout, more drivers and LuCI apps
    immortalwrt) VER=${MU300_WRT_VER:-25.12.2}; BASEURL=https://downloads.immortalwrt.org/releases ;;
    *) echo "unknown flavour '$FLAVOUR' (openwrt or immortalwrt)" >&2; exit 1 ;;
esac
SYSTEM=${MU300_SYSTEM:-openwrt}
case $SYSTEM in
    openwrt) ;;
    # the panel on ImmortalWrt was never tested by anyone
    openwrt-luci)
        [ "$FLAVOUR" = openwrt ] || { echo "MU300_SYSTEM=openwrt-luci is built on OpenWrt only, not $FLAVOUR" >&2; exit 1; } ;;
    *) echo "unknown system '$SYSTEM' (openwrt or openwrt-luci)" >&2; exit 1 ;;
esac
KREL=5.4.254-gb50db5b6224c
# the default name: mu300-<system>-<version>-rootfs.tar.gz; ImmortalWrt keeps its own (it has only the plain system)
if [ "$FLAVOUR" = immortalwrt ]; then OUT=${1:-mu300-immortalwrt-$VER-rootfs.tar.gz}; else OUT=${1:-mu300-$SYSTEM-$VER-rootfs.tar.gz}; fi
TOP=$(cd "$(dirname "$0")/.." && pwd)
# build inputs (out/, firmware/, android-subset/, tools binaries, busybox) may live outside the checkout
IN=${MU300_INPUTS:-$TOP}
# Without its cellular protocol netifd has no wan and the image boots without mobile data. openwrt-luci also needs
# the IPv6 relay monitor: its first boot selects relay mode (91-mu300-luci), and mu300cell.sh then runs it. Plain
# OpenWrt never selects relay, and builds without it.
CELL=$TOP/openwrt/overlay/lib/netifd/proto/mu300cell.sh
[ -s "$CELL" ] || { echo "required cellular protocol helper missing: $CELL" >&2; exit 1; }
if [ "$SYSTEM" = openwrt-luci ]; then
    [ -s "$TOP/openwrt/luci-overlay/lib/netifd/proto/mu300cell-v6.sh" ] || {
        echo "required cellular protocol helper missing: openwrt/luci-overlay/lib/netifd/proto/mu300cell-v6.sh" >&2; exit 1;
    }
fi
# sipa_eth0 into fw4's software flowtable (applied below, the build fails when it no longer applies)
FW4PATCH=$TOP/openwrt/patches/fw4-sipa-offload.patch
[ -s "$FW4PATCH" ] || { echo "missing $FW4PATCH" >&2; exit 1; }
# the docker mounts of the panel system, as the positional parameters (OUT is read above): each path stays one
# argument, spaces and all
set --
if [ "$SYSTEM" = openwrt-luci ]; then
    # Keep the upstream Aurora theme reproducible. Its APK is installed while
    # assembling the rootfs, so the theme is present on first boot without a
    # network-dependent uci-defaults install step. Bootstrap remains available.
    THEME_APK=${MU300_LUCI_THEME_APK:-$TOP/work/luci-theme-aurora-1.4.0-r20260920.apk}
    # pinned here, not overridable: MU300_LUCI_THEME_APK may swap the file, never the hash it is checked against
    THEME_SHA=05f9015e0a4e2859f6a153f69e472f2984481490d4ce6db19b8a41bba7264f1e
    if [ ! -s "$THEME_APK" ]; then
        [ -z "${MU300_LUCI_THEME_APK:-}" ] || {
            echo "theme package missing: $THEME_APK" >&2; exit 1;
        }
        mkdir -p "$TOP/work"
        curl -fL -o "$THEME_APK.part" \
          https://github.com/eamonxg/luci-theme-aurora/releases/download/v1.4.0/luci-theme-aurora-1.4.0-r20260920.apk
        mv "$THEME_APK.part" "$THEME_APK"
    fi
    theme_hash=$(shasum -a 256 "$THEME_APK" 2>/dev/null || sha256sum "$THEME_APK")
    [ "${theme_hash%% *}" = "$THEME_SHA" ] || {
        echo "Aurora APK checksum mismatch: $THEME_APK" >&2; exit 1;
    }
    # The panel's catalogs in the image: Turkish and Simplified Chinese (the others are the lang extra,
    # tools/make-extra.sh). A catalog without translations (English: the msgids are the English text) is no file at
    # all. Named by LuCI's code for the language (openwrt/luci-languages.tsv: zh_Hans is zh-cn), or LuCI does not
    # load them.
    CAT=$(mktemp -d)
    for l in tr zh_Hans; do
        code=$(awk -F '\t' -v d="$l" '$1 == d {print $2}' "$TOP/openwrt/luci-languages.tsv")
        [ -n "$code" ] || { echo "no row for $l in openwrt/luci-languages.tsv" >&2; exit 1; }
        python3 "$TOP/tools/po2lmo.py" "$TOP/openwrt/luci-app-mu300/po/$l/mu300.po" "$CAT/mu300.$code.lmo"
    done
    [ -s "$CAT/mu300.tr.lmo" ] || { echo "no Turkish catalog built from openwrt/luci-app-mu300/po/tr" >&2; exit 1; }
    [ -s "$CAT/mu300.zh-cn.lmo" ] || { echo "no Chinese catalog built from openwrt/luci-app-mu300/po/zh_Hans" >&2; exit 1; }
    set -- -v "$THEME_APK:/in/luci-theme-aurora.apk:ro" -v "$TOP/openwrt/luci-app-mu300:/in/luci-plugin:ro" \
        -v "$TOP/openwrt/luci-overlay:/in/luci-overlay:ro" -v "$CAT:/in/catalogs:ro"
fi
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
# The optional ones decide whether the image can use the modem, Wi-Fi or the GPU at all. Missing ones
# used to be skipped silently, which produces an image that boots and then does nothing useful.
for o in firmware android-subset android-gpu-subset tools/logdw/logdw tools/bt-init/mu300-bt-init tools/keys/mu300-keys tools/gpu/cltest busybox upstream/out/modules; do
    [ -e "$IN/$o" ] && echo "  + $o" || echo "  - $o   (missing: the image is built without it)"
done
# shellcheck disable=SC2046
docker run --rm --platform linux/arm64 \
  -v "$TOP/rootfs/overlay/opt/mu300":/in/opt-mu300:ro -v "$TOP/rootfs/overlay/etc/mu300/vpn.conf.example":/in/vpn.conf.example:ro -v "$TOP/openwrt/overlay":/in/overlay:ro \
  -v "$FW4PATCH":/in/fw4-sipa-offload.patch:ro \
  -v "$TOP/boot/module-order.txt":/in/module-order.txt:ro -v "$IN/out/modules":/in/modules:ro \
  $(opt out/modules.builtin modules.builtin) $(opt out/modules.builtin.modinfo modules.builtin.modinfo) \
  $(opt firmware firmware) $(opt android-subset android-subset) $(opt android-gpu-subset android-gpu-subset) \
  $(opt tools/logdw/logdw logdw) $(opt tools/bt-init/mu300-bt-init bt-init) $(opt tools/keys/mu300-keys keys) $(opt tools/gpu/cltest cltest) \
  $(opt busybox busybox) $(opt upstream/out/modules mainline-modules) -v "$TOP/openwrt":/out -v "$REGDB":/in/regdb:ro "$@" \
  -e KREL=$KREL -e OUT="$(basename "$OUT")" -e MU300_VERSION="${MU300_VERSION:-dev}" mu300-$FLAVOUR-base:$VER /bin/sh -eu -c '
mkdir -p /var/lock /var/run /tmp
apk update >/dev/null
# openssl-util: mu300-vpn fetches the VPN server certificate with it to pin, for links that ask for allowInsecure;
# i2c-tools, gpiod-tools: only the U30-Air-only helpers mu300-usb and mu300-nfc use them (unused on this board)
apk add wpad-basic-mbedtls wifi-scripts iwinfo wireless-regdb iw bash ip-full coreutils-stty openssl-util \
    i2c-tools gpiod-tools >/dev/null
# the router protocols LuCI offers, with their tools: WireGuard, PPTP/L2TP (PPPoE is in the base), 6in4/6rd/DS-Lite,
# GRE and VXLAN, ipset, and SQM (cake). Their kmod-* dependencies install the 6.12 modules of the feed, removed below like
# every other kmod: the mainline kernels have them built in or as modules of their own (mu300-mainline.config), 5.4
# has some of them only
apk add wireguard-tools luci-proto-wireguard ppp-mod-pptp xl2tpd 6in4 6rd ds-lite gre luci-proto-gre vxlan \
    luci-proto-vxlan ipset sqm-scripts luci-app-sqm >/dev/null
# the pinned Aurora theme
[ -d /in/luci-plugin ] && apk add --allow-untrusted /in/luci-theme-aurora.apk >/dev/null
# ujail drops CAP_PERFMON (38), which this 5.4 kernel does not know: jailed services (dnsmasq, ntpd) crash-loop
apk del procd-ujail procd-seccomp >/dev/null 2>&1 || true
# online firmware upgrades flash whole-disk armsr images: that would overwrite the eMMC, so remove them
apk del luci-app-attendedsysupgrade attendedsysupgrade-common owut >/dev/null 2>&1 || true
# LuCI in Turkish and Simplified Chinese besides English, in both systems: the translation of luci-base and of
# every LuCI app the image has that the feed translates (apk checks each package against the signed index). Their
# own uci-defaults, run by apk here, register the languages in luci.languages; the other languages are the lang
# extra (mu300-extra install lang).
i18n=
for c in base $(apk list --installed "luci-app-*" | sed -n "s/^luci-app-\([^ ]*\)-[0-9][^ -]* .*/\1/p"); do
    for l in tr zh-cn; do
        apk search "luci-i18n-$c-$l" | grep -q "^luci-i18n-$c-$l-[0-9]" && i18n="$i18n luci-i18n-$c-$l"
    done
done
echo "LuCI translations:$i18n"
for l in tr zh-cn; do
    case " $i18n " in *" luci-i18n-base-$l "*) ;; *) echo "no LuCI base translation $l in the feed" >&2; exit 1 ;; esac
done
apk add $i18n >/dev/null
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
# the status-LED controller and its OpenWrt event reconciler: keep them executable (git does not track the bit on a
# Windows checkout)
chmod 0755 $R/opt/mu300/bin/led-status $R/opt/mu300/bin/mu300-led-events
# mu300cell reports sipa_eth0 as l3_device only, so fw4 leaves it out of its software flowtable and the cellular
# downlink takes the slow forwarding path. --fuzz=0: a changed fw4 that no longer matches fails the build.
# (patch goes into the build container only: the image was copied above)
apk add patch >/dev/null
patch --batch --fuzz=0 -d $R -p1 -i /in/fw4-sipa-offload.patch
grep -q sipa_eth0 $R/usr/share/ucode/fw4.uc || { echo "fw4 patch not applied" >&2; exit 1; }
apk del patch >/dev/null   # out of packages.txt below, which lists what the image has
if [ -d /in/luci-plugin ]; then
    [ -d /in/luci-overlay ] && cp -a /in/luci-overlay/. $R/
    cp -a /in/luci-plugin/root/. $R/
    cp -a /in/luci-plugin/htdocs/. $R/www/
    chmod 0755 $R/etc/init.d/unisoc-modem-ui $R/etc/hotplug.d/net/90-unisoc-usb-host $R/etc/hotplug.d/iface/90-unisoc-usb-host $R/usr/libexec/rpcd/mu300dash $R/usr/libexec/unisoc-modem/*
    # the panel catalogs, named as LuCI names the language (base.zh-cn.lmo: mu300.zh-cn.lmo)
    for f in /in/catalogs/mu300.*.lmo; do cp "$f" $R/usr/lib/lua/luci/i18n/; done
    [ -s $R/www/luci-static/aurora/main.css ] || { echo "Aurora theme assets missing" >&2; exit 1; }
    # the default theme is set on first boot (etc/uci-defaults/91-mu300-luci), after the themes pick their own
    grep -q "mediaurlbase=.*/luci-static/aurora" $R/etc/uci-defaults/91-mu300-luci || {
        echo "Aurora theme is not the LuCI default" >&2; exit 1;
    }
fi
# the languages LuCI offers (System > System > Language and Style lists English and these); the base catalogs register
# their own, this covers one that did not
L=$R/usr/lib/lua/luci/i18n
for l in tr zh-cn; do
    [ -s $L/base.$l.lmo ] || { echo "LuCI catalog base.$l.lmo missing" >&2; exit 1; }
done
uci -c $R/etc/config -q get luci.languages.tr >/dev/null || uci -c $R/etc/config set luci.languages.tr="Türkçe (Turkish)"
uci -c $R/etc/config -q get luci.languages.zh_cn >/dev/null ||
    uci -c $R/etc/config set luci.languages.zh_cn="$(printf "\347\256\200\344\275\223\344\270\255\346\226\207 (Simplified Chinese)")"
uci -c $R/etc/config commit luci
uci -c $R/etc/config show luci.languages
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
[ -e /in/keys ] && { cp /in/keys $R/opt/mu300/bin/mu300-keys; chmod 755 $R/opt/mu300/bin/mu300-keys; }
# the VPN engines are not part of the image: they are the vpn extra (mu300-extra install vpn)
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
for s in mu300-accounts mu300-vendor mu300-hw mu300-post mu300-toolkit mu300-atd mu300-modem-log mu300-wifi-client mu300-buttons; do
    n=$(sed -n "s/^START=//p" $R/etc/init.d/$s)
    ln -sf ../init.d/$s $R/etc/rc.d/S$n$s
done
if [ -d /in/luci-plugin ]; then
    n=$(sed -n "s/^START=//p" $R/etc/init.d/unisoc-modem-ui)
    ln -sf ../init.d/unisoc-modem-ui $R/etc/rc.d/S${n}unisoc-modem-ui
    # the SMS pool behind the panel (K69, D11): openwrt-luci only, the sms command stays the SMS tool of every system
    chmod 0755 $R/opt/mu300/bin/mu300-sms $R/opt/mu300/bin/mu300-smsd $R/etc/init.d/mu300-smsd
    n=$(sed -n "s/^START=//p" $R/etc/init.d/mu300-smsd)
    ln -sf ../init.d/mu300-smsd $R/etc/rc.d/S${n}mu300-smsd
    # the dashboard AT channels, nr6 and nr7 (K19): the collector of the panel prefers them over nr1
    chmod 0755 $R/etc/init.d/mu300-atd-dash
    n=$(sed -n "s/^START=//p" $R/etc/init.d/mu300-atd-dash)
    ln -sf ../init.d/mu300-atd-dash $R/etc/rc.d/S${n}mu300-atd-dash
    # the routes of relay mode to the LAN (K37): it starts ndp-learn only when wan is in relay mode
    chmod 0755 $R/opt/mu300/bin/ndp-learn $R/lib/netifd/proto/mu300cell-v6.sh $R/etc/init.d/mu300-ndp
    n=$(sed -n "s/^START=//p" $R/etc/init.d/mu300-ndp)
    ln -sf ../init.d/mu300-ndp $R/etc/rc.d/S${n}mu300-ndp
    ln -sf /opt/mu300/bin/mu300-sms $R/usr/bin/mu300-sms
fi
# what apk installed, for comparing two builds (packages on the release feed are not pinned)
apk list --installed | sort > $R/etc/mu300/packages.txt
# busybox PATH is /usr/sbin:/usr/bin:/sbin:/bin, so the commands go into /usr/bin (the same list as Ubuntu)
for c in $(cat /in/opt-mu300/lib/path-commands); do ln -sf /opt/mu300/bin/$c $R/usr/bin/$c; done
# no kernel of its own: OpenWrt kmods (6.12) and grub are unused on this device
rm -rf $R/lib/modules/6.* $R/boot
# the modules of the mainline kernel (upstream/out: the vendor ones and those of the kernel itself, about 20 MiB), so that
# a switch to it needs nothing more; mu300-update installs those of the bundle it boots over them
if ls /in/mainline-modules/*.ko >/dev/null 2>&1; then
    # the release the modules were built for (their vermagic), not a version written down here
    krel=$(for f in /in/mainline-modules/*.ko; do tr "\0" "\n" < $f | sed -n "s/^vermagic=\([^ ]*\) .*/\1/p"; break; done)
    [ -n "$krel" ] && mkdir -p $R/lib/modules/$krel && cp /in/mainline-modules/*.ko $R/lib/modules/$krel/
fi
cd $R && tar -czf /out/$OUT .
ls -la /out/$OUT'
rm -rf "$REGDB" ${CAT:+"$CAT"}
