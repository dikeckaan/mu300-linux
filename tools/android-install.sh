#!/system/bin/sh
# Device side of install.sh (runs as root on Android). Settings come from $T/mu300-install.env (T below):
#   OFF SIZE           free eMMC region (bytes) after the last GPT partition, as strings
#   OFF_S SIZE_S       the same in 512-byte sectors (Android's mksh has 32-bit arithmetic: never compute with bytes)
#   SD_MODE=0|1 SD_DEV with SD_MODE=1 the filesystem (label mu300sd) is the SD card block device SD_DEV instead of
#                      that region; OFF/SIZE are then not used
#   INTERNAL_EXISTS=0|1  with SD_MODE=1: an internal mu300root exists at OFF/SIZE and gets the root-on-sd marker
#   FORMAT=0|1         create the ext4 filesystem (mu300root in the region, mu300sd on the card)
#   OSES="ubuntu openwrt openwrt-luci"  systems to (re)install from $T/mu300-<os>.tar.gz
#                      (plus mu300-vendor-<os>.tar.gz with the device's own vendor files for prebuilt images)
#   WIPE_LEGACY=0|1    remove a first-generation Ubuntu that lives directly in the filesystem root
#   UPDATE=0|1         keep the settings and user data of the systems being reinstalled
#   BOOT_OS            system started by the initramfs
#   DEFAULT_LINUX=0|1  keep booting Linux (otherwise every Linux boot is one-shot and returns to Android)
#   BOOT_ATTEMPTS=1-6  with DEFAULT_LINUX=1: failed boots in a row before Android (.mu300/boot-attempts)
#   PWHASH             SHA-512 crypt hash for the "ubuntu" (Ubuntu) and "root" (OpenWrt) accounts; empty with
#                      UPDATE=1: the accounts and passwords of the previous installation stay as they are
#   IMPORT_HOTSPOT=0|1 copy Android's hotspot SSID/passphrase into each system
#   KERNEL=5.4|6.18|7.2  the kernel in the new boot image; mu300-update keeps installing that one (boot/kernel)
# Extras pushed as $T/mu300-extra-<name>.tar.gz (the work directory, see below) go to extra/<name> on the Linux partition.
set -e
# install.sh pushes everything to /data/local/tmp. The Magisk installer runs this as root from a directory only root
# can write (MU300_DEVICE_WORK): files in /data/local/tmp can be replaced by the shell user after they were checked.
T=${MU300_DEVICE_WORK:-/data/local/tmp}
. $T/mu300-install.env
M=$T/mu300root
say() { echo "[device] $*"; }
# --- sd begin
sd_ext4() {  # true when the device holds an ext4 filesystem, labelled or not
    [ "$(dd if="$1" bs=1 skip=1080 count=2 2>/dev/null | od -An -tx1 | tr -d ' \n')" = 53ef ]
}
sd_label() {  # the ext4 label of a device, empty when it is not ext4 or has none
    sd_ext4 "$1" || return 0
    dd if="$1" bs=1 skip=1144 count=16 2>/dev/null | tr -d '\000'
}
sd_disk() {  # sd_disk DEV: the disk of a partition (mmcblk1p1 -> mmcblk1); a whole disk stays as it is
    case $1 in *mmcblk[0-9]*p[0-9]*) echo "${1%p*}" ;; *) echo "$1" ;; esac
}
sd_check() {  # sd_check DEV: DEV must be on an SD card, never on the eMMC this Android runs from
    case $1 in
        */mmcblk0|*/mmcblk0p*) say "refusing $1: that is the internal eMMC, not the SD card"; return 1 ;;
    esac
    d=$(sd_disk "$1")
    # the MMC core names the card type: SD for a memory card (the eMMC says MMC, a Wi-Fi chip SDIO)
    t=$(cat "${MU300_SYSFS:-/sys}/block/${d##*/}/device/type" 2>/dev/null) || t=
    [ "$t" = SD ] || { say "refusing $1: not an SD card (type '$t')"; return 1; }
}
sd_release() {  # sd_release DEV: make Android let go of the card; nothing has been written when this fails
    # no answer from the volume manager is no proof that Android has let go: refuse
    vols=$(sm list-volumes 2>/dev/null) || { say "cannot ask Android about its volumes (sm list-volumes failed)"; return 1; }
    # adopted as internal storage, in any state: encrypted, and part of Android's data. Android's own data
    # partition is the line "private mounted null" (no colon), which is not a card.
    echo "$vols" | grep -q '^private:[^ ]* ' && {
        say "the SD card is adopted as Android internal storage; format it as portable storage first"; return 1; }
    # only the card: public:179,N (179 is the MMC block major); a USB stick (public:8,N) is not ours to touch
    for v in $(echo "$vols" | sed -n 's/^\(public:179,[^ ]*\) mounted.*/\1/p'); do
        say "asking Android to unmount $v"
        sm unmount "$v" 2>/dev/null || true
    done
    vols=$(sm list-volumes 2>/dev/null) || { say "cannot ask Android about its volumes (sm list-volumes failed)"; return 1; }
    if echo "$vols" | grep -q '^public:179,[^ ]* mounted'; then
        say "Android keeps the SD card mounted; eject it under Settings > Storage and run the installer again"; return 1
    fi
    # anything still mounted from the card's own nodes (any of its partitions). vold mounts the card through
    # /dev/block/vold/public:179,N, so this only catches mounts made by hand: the sm check above is the real
    # guard. A whole-card DEV (mmcblk1) stays as it is, so the eMMC (mmcblk0) can never match.
    d=$(sd_disk "$1")
    for m in $(sed -n -e "s|^$d \([^ ]*\) .*|\1|p" -e "s|^${d}p[0-9][0-9]* \([^ ]*\) .*|\1|p" \
            "${MU300_MOUNTS:-/proc/mounts}" 2>/dev/null); do
        umount "$m" 2>/dev/null || umount -f "$m" 2>/dev/null || true
    done
}
sd_prepare() {  # sd_prepare DEV FORMAT: create mu300sd, or check that it is there
    label=$(sd_label "$1")
    if [ "$2" = 1 ]; then
        # any other ext4, with or without a label, is someone's Linux data; FAT, exFAT or a blank card is not
        if sd_ext4 "$1" && [ "$label" != mu300sd ]; then
            say "refusing to format: foreign ext4 (${label:-no label}) on the SD card"; return 1
        fi
        # Android's own mke2fs, not a busybox one that su's PATH may find first. Its default of one inode per
        # 16 KiB is millions of inodes on a big card, and writing their tables is what made 128 GB cards slow and
        # fail (kanoqwq). So fewer: the ratio doubles up to 1 MiB while at least 65536 inodes remain (the two
        # systems, each with an old copy during an update, use about 25000). awk: the byte count is past mksh's
        # 32-bit arithmetic.
        mk=/system/bin/mke2fs; [ -x $mk ] || mk=mke2fs
        s=$(cat "${MU300_SYSFS:-/sys}/class/block/${1##*/}/size" 2>/dev/null) || s=0
        i=$(awk -v s="${s:-0}" 'BEGIN { i = 16384; while (i < 1048576 && s * 512 / (i * 2) >= 65536) i *= 2; print i }')
        say "creating ext4 mu300sd on $1 (one inode per $((i / 1024)) KiB)"
        $mk -t ext4 -F -b 4096 -m 0 -i "$i" -L mu300sd "$1" >/dev/null
    elif [ "$label" != mu300sd ]; then
        say "no mu300sd filesystem on $1 (run with FORMAT=1)"; return 1
    fi
}
sd_fstab() {  # sd_fstab ROOT: Ubuntu remounts / by label; on the card that label is mu300sd
    [ -f "$1/etc/fstab" ] || return 0
    # not sed -i: the same file content, written back in place (keeps its owner and mode)
    sed 's|^LABEL=mu300root |LABEL=mu300sd |' "$1/etc/fstab" > "$1/etc/fstab.mu300" &&
        cat "$1/etc/fstab.mu300" > "$1/etc/fstab" && rm -f "$1/etc/fstab.mu300"
}
# A device with an internal installation as well: tell its init that the card is what should boot (it then waits
# for the card instead of taking the internal system at once). Best effort - the card boots without it whenever
# the SD host is quick enough - so it always returns 0, also under set -e.
sd_mark_internal() {
    [ "${SD_MODE:-0}" = 1 ] && [ -n "${OFF:-}" ] && [ "${INTERNAL_EXISTS:-0}" = 1 ] || return 0
    I=$T/mu300root-internal
    MU300_OFF=$OFF MU300_SIZE=$SIZE sh $T/android-mount-mu300root.sh $I >/dev/null 2>&1 || return 0
    # true, not ':': a failed redirection on a special builtin like ':' ends a POSIX shell (dash) outright
    if mkdir -p $I/.mu300 2>/dev/null && true > $I/.mu300/root-on-sd 2>/dev/null; then
        say "marked the internal installation: the SD card boots first"
    fi
    sync; sh $T/android-mount-mu300root.sh -u $I >/dev/null 2>&1 || true
}
# An installation into the internal filesystem: a root-on-sd left there by an earlier card installation no longer
# says what should boot (init would wait for a card first), so it goes.
sd_unmark() {  # sd_unmark ROOT
    [ "${SD_MODE:-0}" = 1 ] || rm -f "$1/.mu300/root-on-sd"
}
# --- sd end

if [ "${SD_MODE:-0}" = 1 ]; then
    [ -b "${SD_DEV:?SD_DEV is not set}" ] || { say "no block device $SD_DEV (is the SD card inserted?)"; exit 1; }
    sd_check "$SD_DEV" || exit 1
    sd_release "$SD_DEV" || exit 1
    sd_prepare "$SD_DEV" "$FORMAT" || exit 1
    MU300_SD_DEV=$SD_DEV sh $T/android-mount-mu300root.sh $M
    trap 'sync; sh $T/android-mount-mu300root.sh -u $M >/dev/null 2>&1; true' EXIT
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

# --- legacy-wipe begin
if [ "$WIPE_LEGACY" = 1 ] && { [ -x $M/lib/systemd/systemd ] || [ -L $M/lib ]; }; then
    say "removing the root-level Ubuntu"
    for e in $M/* $M/.[!.]*; do
        case "${e##*/}" in lost+found|.mu300|ubuntu|openwrt|openwrt-*|extra) ;; *) rm -rf "$e" ;; esac
    done
fi
# --- legacy-wipe end

# --- extra begin
# Extras (mu300-extra): optional parts on the Linux partition next to the systems, in DISK/extra/<name>.
extra_from_push() {  # extra_from_push DISK: install the extras install.sh pushed ($T/mu300-extra-<name>.tar.gz)
    for f in $T/mu300-extra-*.tar.gz; do
        [ -f "$f" ] || continue
        n=${f##*/mu300-extra-}; n=${n%.tar.gz}
        x=$1/extra
        rm -rf "$x/.$n.new"; mkdir -p "$x/.$n.new"
        if tar -xzf "$f" -C "$x/.$n.new" 2>/dev/null && [ "$(cat "$x/.$n.new/name" 2>/dev/null)" = "$n" ]; then
            rm -rf "$x/$n" && mv "$x/.$n.new" "$x/$n"
            say "extra $n installed ($(cat "$x/$n/release" 2>/dev/null))"
        else
            rm -rf "$x/.$n.new"
            say "extra $n: the pushed file is not usable, skipped (on the device later: mu300-extra install $n)"
        fi
        rm -f "$f"
    done
    return 0
}
extra_keep_vpn() {  # extra_keep_vpn DISK OLDROOT: the system being replaced uses the VPN with the engines of its image
    # (older images had them in opt/mu300/bin): they stay, as the vpn extra, so the VPN comes back after the reboot
    [ ! -d "$1/extra/vpn/bin" ] || return 0
    grep -q '^ENABLE=1' "$2/etc/mu300/vpn.conf" 2>/dev/null || return 0
    [ -x "$2/opt/mu300/bin/xray" ] || [ -x "$2/opt/mu300/bin/sing-box" ] || return 0
    x=$1/extra
    rm -rf "$x/.vpn.new"; mkdir -p "$x/.vpn.new/bin"
    for e in xray hev-socks5-tunnel sing-box; do
        if [ -x "$2/opt/mu300/bin/$e" ]; then cp -p "$2/opt/mu300/bin/$e" "$x/.vpn.new/bin/$e"; fi
    done
    echo vpn > "$x/.vpn.new/name"
    cat "$2/etc/mu300/image-version" > "$x/.vpn.new/release" 2>/dev/null || echo unknown > "$x/.vpn.new/release"
    echo "taken from the image of the previous system" > "$x/.vpn.new/components"
    rm -rf "$x/vpn"; mv "$x/.vpn.new" "$x/vpn"
    say "kept the VPN engines of the previous system as the vpn extra"
}
# --- extra end
extra_from_push $M

ssid=; psk=
if [ "$IMPORT_HOTSPOT" = 1 ]; then
    X=/data/misc/apexdata/com.android.wifi/WifiConfigStoreSoftAp.xml
    ssid=$(sed -n 's/.*<string name="WifiSsid">&quot;\(.*\)&quot;<\/string>.*/\1/p; s/.*<string name="WifiSsid">\([^&<]*\)<\/string>.*/\1/p' $X 2>/dev/null | head -1)
    psk=$(sed -n 's/.*<string name="Passphrase">\(.*\)<\/string>.*/\1/p' $X 2>/dev/null | head -1 | sed "s/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g; s/&quot;/\"/g; s/&apos;/'/g")
    [ -n "$ssid" ] && [ ${#psk} -ge 8 ] || { say "no usable Android hotspot config, a random password will be generated"; ssid=; psk=; }
fi

# --- install-os begin
# Accounts are settings too, and etc/shadow is not in keep: an update carries them over the way mu300-update does,
# with its own function (copied here: this runs on Android and cannot source the new system's mu300-update; tests
# keep the two the same). The old entry of every account both systems have (hashes, group memberships merged), and
# the users and groups the old system added (ids 1000-59999). A new password (PWHASH) is put in afterwards.
ACCOUNTS_MARK=/etc/.mu300-accounts-from-image
merge_accounts() {  # merge_accounts OLD_ROOT NEW_ROOT   ("" is the running system)
    o=$1 n=$2
    [ -f "$o/etc/shadow" ] && [ -f "$n/etc/shadow" ] || return 0
    for f in passwd group shadow gshadow; do
        [ -f "$o/etc/$f" ] && [ -f "$n/etc/$f" ] || continue
        awk -F: -v OFS=: -v f="$f" -v op="$o/etc/passwd" -v og="$o/etc/group" '
            BEGIN {
                while ((getline l < op) > 0) { split(l, a, ":"); if (a[3] >= 1000 && a[3] < 60000) lu[a[1]] = 1 }
                while ((getline l < og) > 0) { split(l, a, ":"); if (a[3] >= 1000 && a[3] < 60000) lg[a[1]] = 1 }
            }
            NR == FNR { old[$1] = $0; next }
            {
                seen[$1] = 1
                if ((f == "shadow" || f == "gshadow") && ($1 in old)) { print old[$1]; next }
                if (f == "group" && ($1 in old)) {
                    split(old[$1], og4, ":"); m = $4; k = split(og4[4], om, ",")
                    for (i = 1; i <= k; i++)
                        if (om[i] != "" && index("," m ",", "," om[i] ",") == 0) m = (m == "" ? om[i] : m "," om[i])
                    $4 = m
                }
                print
            }
            END {
                for (x in old) if (!(x in seen)) {
                    if ((f == "passwd" || f == "shadow") && (x in lu)) print old[x]
                    if ((f == "group" || f == "gshadow") && (x in lg)) print old[x]
                }
            }' "$o/etc/$f" "$n/etc/$f" > "$n/etc/$f.mu300" || { rm -f "$n/etc/$f.mu300"; return 1; }
        # renamed into place, never rewritten: a crash (or a reader at boot) never sees a half-written passwd.
        # The copy made with cp -p keeps the file's owner and mode (shadow is root:shadow 0640; no stat on OpenWrt).
        if [ -s "$n/etc/$f.mu300" ]; then
            cp -p "$n/etc/$f" "$n/etc/$f.mu300-new" && cat "$n/etc/$f.mu300" > "$n/etc/$f.mu300-new" && sync &&
                mv -f "$n/etc/$f.mu300-new" "$n/etc/$f" || { rm -f "$n/etc/$f.mu300" "$n/etc/$f.mu300-new"; return 1; }
        fi
        rm -f "$n/etc/$f.mu300"
    done
    rm -f "$n$ACCOUNTS_MARK"
}
for os in $OSES; do
    tarball=$T/mu300-$os.tar.gz
    [ -f $tarball ] || { say "missing $tarball"; exit 1; }
    say "installing $os"
    rm -rf $M/$os.new && mkdir $M/$os.new
    tar -xzpf $tarball -C $M/$os.new
    newprofile=$(cat "$M/$os.new/etc/mu300/profile" 2>/dev/null || true)
    newrepo=$(cat "$M/$os.new/etc/mu300/update.conf" 2>/dev/null || true)
    newled=$(cat "$M/$os.new/etc/mu300/led.conf" 2>/dev/null || true)
    if [ "${UPDATE:-0}" = 1 ] && [ "$(cat "$M/$os/etc/mu300/profile" 2>/dev/null)" = v50 ] && [ "$newprofile" != v50 ]; then
        rm -rf "$M/$os.new"
        say 'V50: target rootfs has no V50 profile; current system was not replaced'
        exit 1
    fi
    # the account the installer gives a password (ubuntu, OpenWrt's root) and its hash in the image
    case $os in ubuntu) pwu=ubuntu ;; *) pwu=root ;; esac
    carried=0
    imghash=$(sed -n "s/^$pwu:\([^:]*\):.*/\1/p" $M/$os.new/etc/shadow 2>/dev/null | head -n1) || imghash=
    # prebuilt images: firmware and Android userspace pulled from this device by install.sh (tools/vendor-overlay.py)
    if [ -f $T/mu300-vendor-$os.tar.gz ]; then
        tar -xzpf $T/mu300-vendor-$os.tar.gz -C $M/$os.new
        rm -f $T/mu300-vendor-$os.tar.gz
    fi
    # update: carry the settings and user data of the previous installation over to the new system
    if [ "${UPDATE:-0}" = 1 ] && [ -d $M/$os ]; then
        case $os in
            ubuntu) keep="etc/mu300 etc/ssh etc/hostname etc/localtime etc/timezone etc/fstab home root srv usr/local var/lib/bluetooth" ;;
            openwrt|openwrt-*) keep="etc/config etc/mu300 etc/dropbear etc/rc.local root" ;;
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
            openwrt|openwrt-*)
                for l in $M/$os/etc/rc.d/*; do
                    [ -L "$l" ] || [ -e "$l" ] || continue
                    u=${l##*/}
                    if [ -L "$M/$os.new/etc/rc.d/$u" ]; then continue; fi
                    [ -x "$M/$os.new/etc/init.d/${u#S??}" ] || [ -x "$M/$os.new/etc/init.d/${u#K??}" ] || continue
                    cp -a "$l" "$M/$os.new/etc/rc.d/$u" && extra="$extra $u"
                done ;;
        esac
        say "kept from the previous $os:$kept"
        if [ -f "$M/$os/etc/shadow" ]; then
            merge_accounts "$M/$os" "$M/$os.new" || { say "could not carry the accounts of $os over; nothing was replaced"; exit 1; }
            carried=1
            say "kept the accounts and passwords of the previous $os"
        fi
        extra_keep_vpn $M $M/$os
        [ -n "$extra" ] && say "kept enabled services:$extra"
    fi
    if [ "$newprofile" = v50 ]; then
        mkdir -p "$M/$os.new/etc/mu300"
        echo v50 > "$M/$os.new/etc/mu300/profile"
        [ -f "$M/$os.new/etc/mu300/update.conf" ] || printf '%s\n' "$newrepo" > "$M/$os.new/etc/mu300/update.conf"
        [ -f "$M/$os.new/etc/mu300/led.conf" ] || printf '%s\n' "$newled" > "$M/$os.new/etc/mu300/led.conf"
    fi
    # The password, before the new system replaces the old one: the hash just chosen, or (an update without one) the
    # one carried over. Fail closed: a system whose account would be left with no hash, an empty one, the image's
    # default or the image's accounts is not installed, and the old one stays.
    if [ -n "$PWHASH" ]; then
        rm -f $M/$os.new$ACCOUNTS_MARK   # the password is the one just chosen, not one to carry over
        sed -i "s|^$pwu:[^:]*:|$pwu:$PWHASH:|" $M/$os.new/etc/shadow
    fi
    h=$(sed -n "s/^$pwu:\([^:]*\):.*/\1/p" $M/$os.new/etc/shadow 2>/dev/null | head -n1) || h=
    case $h in '$'?*) ;; *) h= ;; esac
    if [ -z "$h" ] || [ -e $M/$os.new$ACCOUNTS_MARK ] ||
        { [ -z "$PWHASH" ] && { [ "$carried" != 1 ] || [ "$h" = "$imghash" ]; }; }; then
        rm -rf $M/$os.new
        say "$os: $pwu would keep no password of its own (empty, the image's default, or none to carry over); $os was not replaced. Install again with MU300_PASSWORD_RESET=yes in /data/adb/mu300-install.conf (or choose a password in install.sh)"
        exit 1
    fi
    rm -rf $M/$os && mv $M/$os.new $M/$os
    R=$M/$os
    if [ "${SD_MODE:-0}" = 1 ]; then sd_fstab $R; fi
    mkdir -p $R/etc/mu300
    if [ -n "$ssid" ] && ! { [ "${UPDATE:-0}" = 1 ] && [ -s $R/etc/mu300/hotspot.conf ]; }; then
        umask 077
        printf 'SSID=%s\nPSK=%s\nBAND=5\nCHANNEL=auto\nCOUNTRY=TR\n' "$ssid" "$psk" > $R/etc/mu300/hotspot.conf
        chmod 600 $R/etc/mu300/hotspot.conf
        umask 022
    fi
    if [ "$DEFAULT_LINUX" = 1 ]; then echo linux > $R/etc/mu300/default-boot; else rm -f $R/etc/mu300/default-boot; fi
    rm -f $tarball
done
mkdir -p $M/.mu300
sd_unmark $M
echo "$BOOT_OS" > $M/.mu300/boot-os
# --- install-os end
case ${BOOT_ATTEMPTS:-} in [1-6]) echo "$BOOT_ATTEMPTS" > $M/.mu300/boot-attempts ;; esac
case ${KERNEL:-5.4} in
    5.4|6.18|7.2) mkdir -p $M/boot; echo "${KERNEL:-5.4}" > $M/boot/kernel; echo "${KERNEL:-5.4}" > $M/boot/installed.kernel ;;
esac
# the boot image is the installer's now: a release tag left by an earlier mu300-update would describe another one
rm -f $M/boot/installed.tag
[ -n "$ssid" ] && say "hotspot: SSID $ssid imported (passphrase ${#psk} chars)"
say "installed: $(ls -d $M/ubuntu $M/openwrt $M/openwrt-luci 2>/dev/null | sed "s|$M/||g" | tr '\n' ' ')boot-os=$BOOT_OS default-linux=$DEFAULT_LINUX"
sd_mark_internal
rm -f $T/mu300-install.env
echo MU300-INSTALL-OK   # install.sh checks for this line (set -e stops before it on any failure)
