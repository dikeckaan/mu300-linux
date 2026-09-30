#!/system/bin/sh
# Device side of install.sh (runs as root on Android). Settings come from /data/local/tmp/mu300-install.env:
#   SD_MODE=0          rootfs in the free eMMC region after the last GPT partition
#   SD_MODE=1 SD_DEV   rootfs on the TF card, formatted ext4 with label mu300sd
#   OFF SIZE           free eMMC region (bytes) after the last GPT partition, as strings (SD_MODE=0)
#   OFF_S SIZE_S       the same in 512-byte sectors (Android's mksh has 32-bit arithmetic: never compute with bytes)
#   FORMAT=0|1         create ext4 mu300root internally or mu300sd on TF
#   OSES="ubuntu openwrt"  systems to (re)install from /data/local/tmp/mu300-<os>.tar.gz
#                      (plus mu300-vendor-<os>.tar.gz with the device's own vendor files for prebuilt images)
#   WIPE_LEGACY=0|1    remove a first-generation Ubuntu that lives directly in the filesystem root
#   UPDATE=0|1         keep the settings and user data of the systems being reinstalled
#   BOOT_OS            system started by the initramfs
#   DEFAULT_LINUX=0|1  keep booting Linux (otherwise every Linux boot is one-shot and returns to Android)
#   BOOT_ATTEMPTS=1-6  with DEFAULT_LINUX=1: failed boots in a row before Android (.mu300/boot-attempts)
#   PWHASH             SHA-512 crypt hash for the "ubuntu" (Ubuntu) and "root" (OpenWrt) accounts
#   IMPORT_HOTSPOT=0|1 copy Android's hotspot SSID/passphrase into each system
#   KERNEL=5.4|6.18|7.2  the kernel in the new boot image; mu300-update keeps installing that one (boot/kernel)
set -e
T=${MU300_INSTALL_TMP:-/data/local/tmp}
P=${MU300_PAYLOAD_DIR:-$T}
. "$P/mu300-install.env"
M=$T/mu300root
say() { echo "[device] $*"; }

if [ "${SD_MODE:-0}" = 1 ]; then
    R=${SD_DEV:?SD_DEV is not set}
    [ -b "$R" ] || { say "no block device $R (is the TF card inserted?)"; exit 1; }
    vol=$(sm list-volumes 2>/dev/null | sed -n 's/^\(public:[^ ]*\) mounted.*/\1/p')
    if [ -n "$vol" ]; then
        say "asking vold to unmount $vol"
        sm unmount "$vol" 2>/dev/null || true
        sm list-volumes 2>/dev/null | grep -q "^$vol mounted" && {
            say "vold still has the card mounted; unmount it in Android Storage settings"; exit 1; }
    fi
    for m in $(grep -o '^/dev/block/mmcblk1[^ ]*' /proc/mounts 2>/dev/null); do
        umount "$m" 2>/dev/null || umount -f "$m" 2>/dev/null || true
    done
    magic=$(dd if="$R" bs=1 skip=1080 count=2 2>/dev/null | od -An -tx1 | tr -d ' \n')
    label=$(dd if="$R" bs=1 skip=1144 count=16 2>/dev/null | tr -d '\000')
    if [ "$FORMAT" = 1 ]; then
        [ "$magic" != 53ef ] || [ "$label" = mu300sd ] || {
            say "refusing to format foreign ext4 filesystem '$label'"; exit 1; }
        say "creating ext4 mu300sd on $R"
        if command -v make_ext4fs >/dev/null 2>&1; then
            make_ext4fs -L mu300sd "$R"
        else
            mke2fs -b 4096 -L mu300sd "$R"
        fi
    elif [ "$magic" != 53ef ] || [ "$label" != mu300sd ]; then
        say "no mu300sd filesystem on $R (FORMAT=1 is required)"; exit 1
    fi
    mkdir -p "$M"
    mount -t ext4 -o noatime "$R" "$M"
    trap 'sync; umount "$M" >/dev/null 2>&1 || true' EXIT
else
# --- the region must not overlap any partition (checked again here, on the device itself)
end=0
for p in /sys/block/mmcblk0/mmcblk0p*; do
    e=$(( $(cat $p/start) + $(cat $p/size) ))
    [ $e -gt $end ] && end=$e
done
disk=$(cat /sys/block/mmcblk0/size)
[ "$OFF_S" -ge $end ] && [ $((OFF_S + SIZE_S)) -le $((disk - 34)) ] || { say "region overlaps partitions or the backup GPT"; exit 1; }

attach() {
    for o in /sys/block/loop*/loop/offset; do
        [ "$(cat $o 2>/dev/null)" = "$OFF" ] && { say "region already attached (${o%/loop/offset})"; exit 1; }
    done
    f=$(losetup -f 2>&1 | grep -o '/dev/block/loop[0-9]*' | head -1); n=${f##*loop}
    L=/dev/block/loop$n
    [ -b "$L" ] || mknod "$L" b $(cut -d: -f1 /sys/block/loop$n/dev) $(cut -d: -f2 /sys/block/loop$n/dev) 2>/dev/null || [ -b "$L" ]
    losetup -o $OFF -S $SIZE "$L" /dev/block/mmcblk0
    [ "$(cat /sys/block/loop$n/loop/offset)" = "$OFF" ] && [ "$(blockdev --getsize64 $L)" = "$SIZE" ] || { losetup -d $L; say "loop setup mismatch"; exit 1; }
}

sb() { dd if=/dev/block/mmcblk0 bs=512 skip=$OFF_S count=4 2>/dev/null | dd bs=1 skip=$1 count=$2 2>/dev/null; }
magic=$(sb 1080 2 | od -An -tx1 | tr -d ' \n')
label=$(sb 1144 16 | tr -d '\000')
if [ "$FORMAT" = 1 ]; then
    if [ "$magic" = 53ef ] && [ "$label" != mu300root ]; then say "refusing to format: foreign ext4 ($label) in the region"; exit 1; fi
    attach
    say "creating ext4 mu300root on $L ($((SIZE_S / 2048)) MiB)"
    mke2fs -t ext4 -L mu300root -F "$L" >/dev/null
    losetup -d "$L"
elif [ "$magic" != 53ef ] || [ "$label" != mu300root ]; then
    say "no mu300root filesystem in the region (run with FORMAT=1)"; exit 1
fi

MU300_OFF=$OFF MU300_SIZE=$SIZE sh $T/android-mount-mu300root.sh $M
trap 'sync; sh $T/android-mount-mu300root.sh -u $M >/dev/null 2>&1; true' EXIT
fi

if [ "$WIPE_LEGACY" = 1 ] && { [ -x $M/lib/systemd/systemd ] || [ -L $M/lib ]; }; then
    say "removing the root-level Ubuntu"
    for e in $M/* $M/.[!.]*; do
        case "${e##*/}" in lost+found|.mu300|ubuntu|openwrt) ;; *) rm -rf "$e" ;; esac
    done
fi

ssid=; psk=
if [ "$IMPORT_HOTSPOT" = 1 ]; then
    X=/data/misc/apexdata/com.android.wifi/WifiConfigStoreSoftAp.xml
    ssid=$(sed -n 's/.*<string name="WifiSsid">&quot;\(.*\)&quot;<\/string>.*/\1/p; s/.*<string name="WifiSsid">\([^&<]*\)<\/string>.*/\1/p' $X 2>/dev/null | head -1)
    psk=$(sed -n 's/.*<string name="Passphrase">\(.*\)<\/string>.*/\1/p' $X 2>/dev/null | head -1 | sed "s/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g; s/&quot;/\"/g; s/&apos;/'/g")
    [ -n "$ssid" ] && [ ${#psk} -ge 8 ] || { say "no usable Android hotspot config, a random password will be generated"; ssid=; psk=; }
fi

for os in $OSES; do
    tarball=$P/mu300-$os.tar.gz
    [ -f $tarball ] || { say "missing $tarball"; exit 1; }
    say "installing $os"
    rm -rf $M/$os.new && mkdir $M/$os.new
    tar -xzpf $tarball -C $M/$os.new
    # prebuilt images: firmware and Android userspace pulled from this device by install.sh (tools/vendor-overlay.py)
    if [ -f $P/mu300-vendor-$os.tar.gz ]; then
        tar -xzpf $P/mu300-vendor-$os.tar.gz -C $M/$os.new
        [ "${MU300_KEEP_PAYLOAD:-0}" = 1 ] || rm -f $P/mu300-vendor-$os.tar.gz
    elif [ "${MU300_VENDOR_FROM_DEVICE:-0}" = 1 ]; then
        sh "$P/mu300-vendor-from-device.sh" "$M/$os.new" "$os"
    fi
    # update: carry the settings and user data of the previous installation over to the new system
    if [ "${UPDATE:-0}" = 1 ] && [ -d $M/$os ]; then
        case $os in
            ubuntu) keep="etc/mu300 etc/ssh etc/hostname etc/localtime etc/timezone etc/fstab home root srv usr/local var/lib/bluetooth" ;;
            openwrt) keep="etc/config etc/mu300 etc/dropbear etc/rc.local root" ;;
        esac
        kept=
        for k in $keep; do
            [ -e "$M/$os/$k" ] || continue
            mkdir -p "$M/$os.new/$(dirname $k)"
            rm -rf "$M/$os.new/$k"
            cp -a "$M/$os/$k" "$M/$os.new/$k" && kept="$kept $k"
        done
        # services the user enabled or disabled themselves: copy the extra symlinks over, but only when the unit
        # they point at exists in the new system (stale units from an older release must not come back)
        extra=
        case $os in
            ubuntu)
                for w in $M/$os/etc/systemd/system/*.wants; do
                    [ -d "$w" ] || continue
                    t=${w##*/}
                    for l in "$w"/*; do
                        # -L, not -e: the links point at absolute paths inside the Linux root, so from Android
                        # they all look broken
                        [ -L "$l" ] || [ -e "$l" ] || continue
                        u=${l##*/}
                        if [ -L "$M/$os.new/etc/systemd/system/$t/$u" ]; then continue; fi
                        [ -e "$M/$os.new/etc/systemd/system/$u" ] || [ -e "$M/$os.new/usr/lib/systemd/system/$u" ] || continue
                        mkdir -p "$M/$os.new/etc/systemd/system/$t"
                        cp -a "$l" "$M/$os.new/etc/systemd/system/$t/$u" && extra="$extra $u"
                    done
                done ;;
            openwrt)
                for l in $M/$os/etc/rc.d/*; do
                    [ -L "$l" ] || [ -e "$l" ] || continue
                    u=${l##*/}
                    if [ -L "$M/$os.new/etc/rc.d/$u" ]; then continue; fi
                    [ -x "$M/$os.new/etc/init.d/${u#S??}" ] || [ -x "$M/$os.new/etc/init.d/${u#K??}" ] || continue
                    cp -a "$l" "$M/$os.new/etc/rc.d/$u" && extra="$extra $u"
                done ;;
        esac
        say "kept from the previous $os:$kept"
        [ -n "$extra" ] && say "kept enabled services:$extra"
    fi
    rm -rf $M/$os && mv $M/$os.new $M/$os
    R=$M/$os
    [ "${SD_MODE:-0}" = 1 ] && [ -f $R/etc/fstab ] && \
        sed -i 's|LABEL=mu300root|LABEL=mu300sd|' $R/etc/fstab
    mkdir -p $R/etc/mu300
    if [ -n "$ssid" ] && ! { [ "${UPDATE:-0}" = 1 ] && [ -s $R/etc/mu300/hotspot.conf ]; }; then
        umask 077
        printf 'SSID=%s\nPSK=%s\nBAND=5\nCHANNEL=auto\nCOUNTRY=TR\n' "$ssid" "$psk" > $R/etc/mu300/hotspot.conf
        chmod 600 $R/etc/mu300/hotspot.conf
        umask 022
    fi
    if [ "$DEFAULT_LINUX" = 1 ]; then echo linux > $R/etc/mu300/default-boot; else rm -f $R/etc/mu300/default-boot; fi
    if [ -n "$PWHASH" ]; then
        rm -f $R/etc/.mu300-accounts-from-image   # the password is the one just chosen, not one to carry over
        case $os in
            ubuntu) sed -i "s|^ubuntu:[^:]*:|ubuntu:$PWHASH:|" $R/etc/shadow ;;
            openwrt) sed -i "s|^root:[^:]*:|root:$PWHASH:|" $R/etc/shadow ;;
        esac
    fi
    [ "${MU300_KEEP_PAYLOAD:-0}" = 1 ] || rm -f $tarball
done
mkdir -p $M/.mu300
echo "$BOOT_OS" > $M/.mu300/boot-os
case ${BOOT_ATTEMPTS:-} in [1-6]) echo "$BOOT_ATTEMPTS" > $M/.mu300/boot-attempts ;; esac
case ${KERNEL:-5.4} in
    5.4|6.18|7.2) mkdir -p $M/boot; echo "${KERNEL:-5.4}" > $M/boot/kernel; echo "${KERNEL:-5.4}" > $M/boot/installed.kernel ;;
esac
# the boot image is the installer's now: a release tag left by an earlier mu300-update would describe another one
rm -f $M/boot/installed.tag
[ -n "$ssid" ] && say "hotspot: SSID $ssid imported (passphrase ${#psk} chars)"
say "installed: $(ls -d $M/ubuntu $M/openwrt 2>/dev/null | sed "s|$M/||g" | tr '\n' ' ')boot-os=$BOOT_OS default-linux=$DEFAULT_LINUX"
[ "${MU300_KEEP_PAYLOAD:-0}" = 1 ] || rm -f $P/mu300-install.env
echo MU300-INSTALL-OK   # install.sh checks for this line (set -e stops before it on any failure)
