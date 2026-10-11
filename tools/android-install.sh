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
# Extras pushed as $T/mu300-extra-<name>.tar.gz (the work directory, see below) go to extra/<name> on the Linux partition
# (the VPN module, github.com/dikeckaan/mu300-linux-vpn, as mu300-extra-vpn.tar.gz; each system links it into itself
# at its first boot: mu300-extra link runs the module's hooks/link).
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
extra_ok() {  # extra_ok NAME DIR: DIR (unpacked) is that extra: ./name says so, or it is the VPN module (./VERSION and
    # its programs; for vpn mu300-vpn and its hooks)
    [ "$(cat "$2/name" 2>/dev/null)" = "$1" ] && return 0
    [ -s "$2/VERSION" ] || return 1
    case $1 in
        vpn) [ -f "$2/bin/mu300-vpn" ] && [ -f "$2/hooks/link" ] && [ -f "$2/hooks/unlink" ] ;;
        vpn-mihomo) [ -f "$2/bin/mihomo" ] ;;
        *) return 1 ;;
    esac
}
extra_from_push() {  # extra_from_push DISK: install the extras install.sh pushed ($T/mu300-extra-<name>.tar.gz)
    for f in $T/mu300-extra-*.tar.gz; do
        [ -f "$f" ] || continue
        n=${f##*/mu300-extra-}; n=${n%.tar.gz}
        x=$1/extra
        rm -rf "$x/.$n.new"; mkdir -p "$x/.$n.new"
        if tar -xzf "$f" -C "$x/.$n.new" 2>/dev/null && extra_ok "$n" "$x/.$n.new"; then
            rm -rf "$x/$n" "$x/.$n.sha256" && mv "$x/.$n.new" "$x/$n"
            say "extra $n installed ($(cat "$x/$n/release" 2>/dev/null || cat "$x/$n/VERSION" 2>/dev/null))"
        else
            rm -rf "$x/.$n.new"
            say "extra $n: the pushed file is not usable, skipped (on the device later: mu300-extra install $n)"
        fi
        rm -f "$f"
    done
    return 0
}
extra_keep_vpn() {  # extra_keep_vpn DISK OLDROOT: the system being replaced uses the VPN. The new images have no
    # mu300-vpn: it is the VPN module, linked into the system at its first boot. Without the module the VPN does not
    # come back - say so loudly (the engines of an older image or extra are no use without mu300-vpn).
    grep -q '^ENABLE=1' "$2/etc/mu300/vpn.conf" 2>/dev/null || return 0
    [ ! -f "$1/extra/vpn/bin/mu300-vpn" ] || return 0
    say "WARNING: the VPN was on in the previous system, and the VPN module is not installed: the VPN stays off"
    say "  until it is: on the device, sudo mu300-extra install vpn (github.com/dikeckaan/mu300-linux-vpn)"
}
# vpn_killswitch_wanted ROOT: the VPN on with its kill switch in the system at ROOT - a copy of the images'
# lib/vpn-orphan.sh (tests/test_vpn_hooks.py holds the copies to one matrix): ENABLE from vpn.conf, KILL_SWITCH from
# the store's settings when the store is in use, else vpn.conf; only 0 is off. Read with sed, never sourced.
vpn_conf_value() {
    [ -r "$1" ] || return 0
    sed -n "s/^$2=//p" "$1" 2>/dev/null | tail -n1 | sed "s/[[:space:]]#.*//; s/[\"' ]//g"
}
vpn_killswitch_wanted() {
    [ "$(vpn_conf_value "${1:-}/etc/mu300/vpn.conf" ENABLE)" = 1 ] || return 1
    if [ -d "${1:-}/etc/mu300/vpn/profiles" ] && [ -r "${1:-}/etc/mu300/vpn/settings" ]; then
        _vks=$(vpn_conf_value "${1:-}/etc/mu300/vpn/settings" KILL_SWITCH)
    else
        _vks=$(vpn_conf_value "${1:-}/etc/mu300/vpn.conf" KILL_SWITCH)
    fi
    [ "$_vks" != 0 ]
}
extra_vpn_precheck() {  # extra_vpn_precheck DISK: before any system is replaced. An update over a system whose VPN is
    # on with its kill switch needs the VPN module (the new images have no mu300-vpn): without it the kill switch
    # would be left to nothing, so nothing is changed, as mu300-update apply does. Kill switch off: a warning later.
    [ "${UPDATE:-0}" = 1 ] || return 0
    [ ! -f "$1/extra/vpn/bin/mu300-vpn" ] || return 0
    for o in $OSES; do
        [ -d "$1/$o" ] && vpn_killswitch_wanted "$1/$o" || continue
        say "the VPN is on with its kill switch in the $o being replaced, and the VPN module is not installed: nothing was changed"
        say "  answer yes to the installer's VPN question (or set MU300_VPN_MODULE=FILE), install it on the device first"
        say "  (sudo mu300-extra install vpn), or turn the VPN off there first (ENABLE=0 in /etc/mu300/vpn.conf)"
        exit 1
    done
    return 0
}
# --- extra end
extra_from_push $M
extra_vpn_precheck $M

ssid=; psk=
if [ "$IMPORT_HOTSPOT" = 1 ]; then
    X=/data/misc/apexdata/com.android.wifi/WifiConfigStoreSoftAp.xml
    ssid=$(sed -n 's/.*<string name="WifiSsid">&quot;\(.*\)&quot;<\/string>.*/\1/p; s/.*<string name="WifiSsid">\([^&<]*\)<\/string>.*/\1/p' $X 2>/dev/null | head -1)
    psk=$(sed -n 's/.*<string name="Passphrase">\(.*\)<\/string>.*/\1/p' $X 2>/dev/null | head -1 | sed "s/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g; s/&quot;/\"/g; s/&apos;/'/g")
    [ -n "$ssid" ] && [ ${#psk} -ge 8 ] || { say "no usable Android hotspot config, a random password will be generated"; ssid=; psk=; }
fi

# --- user-packages begin
# Packages installed on the device are not in the release's image, and an update puts the image in place while it
# keeps /etc/config (OpenWrt) and /etc/mu300: their programs were gone and their settings stayed - OpenClash's left
# the device without DNS (#116). So before the switch the update writes down what was added - the packages asked for
# by hand (OpenWrt: /etc/apk/world; Ubuntu: dpkg's packages that apt did not pull in by itself) less the image's
# own set (etc/mu300/image-packages, written when the image is built) - into etc/mu300/user-packages/ of the new
# system, and sets the UCI files of those packages aside (etc/mu300/orphaned-config/): a package that is not there
# leaves no settings behind. At its first boot the new system installs them again (mu300-user-packages, a service)
# and puts their settings back. tools/android-install.sh (the installers' update) has a copy of this block; tests
# hold the two to one text. It runs on Android too: sh, awk, sed, grep, sort - nothing else, and safe under set -e.
UPK_DIR=etc/mu300/user-packages
UPK_ORPH=etc/mu300/orphaned-config
# what is never installed again: kernel modules (the feed's are for another kernel), and what the images take out on
# purpose (sysupgrade would flash the eMMC; ujail crash-loops services on 5.4)
upk_skip() {
    case $1 in
        kmod-*|kernel|procd-ujail|procd-seccomp|luci-app-attendedsysupgrade|attendedsysupgrade-common|owut) return 0 ;;
        linux-image-*|linux-modules-*|linux-headers-*|linux-generic*|linux-firmware) return 0 ;;
    esac
    return 1
}
upk_kind() { case $1 in ubuntu) echo ubuntu ;; *) echo openwrt ;; esac; }
# upk_dpkg ROOT [manual]: dpkg's installed packages in ROOT; with manual, less those apt installed as dependencies
# (what apt-mark showmanual says, read from the files: ROOT need not be the running system)
upk_dpkg() {
    [ -f "$1/var/lib/dpkg/status" ] || return 0
    { [ "${2:-}" != manual ] || cat "$1/var/lib/apt/extended_states" 2>/dev/null || :; echo '@dpkg'; cat "$1/var/lib/dpkg/status"; } |
        awk '$0 == "@dpkg" { s = 1; next }
             $1 == "Package:" { p = $2; next }
             !s && $1 == "Auto-Installed:" && $2 == 1 { auto[p] = 1; next }
             s && $1 == "Status:" && $3 == "ok" && $4 == "installed" { inst[p] = 1 }
             END { for (p in inst) if (!(p in auto)) print p }' | sort
}
# upk_manual ROOT KIND: the packages asked for by name (OpenWrt: the world file, versions and pins taken off)
upk_manual() {
    if [ "$2" = ubuntu ]; then upk_dpkg "$1" manual; return 0; fi
    [ -f "$1/etc/apk/world" ] || return 0
    sed 's/[<>=~@ ].*//' "$1/etc/apk/world" | awk 'NF' | sort -u
}
# upk_installed ROOT KIND: every installed package
upk_installed() {
    if [ "$2" = ubuntu ]; then upk_dpkg "$1"; return 0; fi
    [ -f "$1/lib/apk/db/installed" ] || return 0
    sed -n 's/^P://p' "$1/lib/apk/db/installed" | sort -u
}
# upk_txt_names FILE: the names in etc/mu300/packages.txt ("apk list --installed": name-version-rN arch ...)
upk_txt_names() {
    [ -f "$1" ] || return 0
    awk '{print $1}' "$1" | sed 's/-r[0-9][0-9]*$//; s/-[^-]*$//'
}
# upk_pending DIR: the packages of a record not installed again yet (nor given up on)
upk_pending() {
    [ -f "$1/wanted" ] || return 0
    { for _uf in done failed; do [ ! -f "$1/$_uf" ] || sed 's/^/x /' "$1/$_uf"; done; sed 's/^/w /' "$1/wanted"; } |
        awk '$1 == "x" { d[$2] = 1; next } NF > 1 && !($2 in d) { print $2 }'
}
# What belongs to the new image, not to the device, in the directories an update keeps: its version and package
# lists in etc/mu300 (an update carried the old ones over: every update then reported the version it replaced), and
# the names of its own files in etc/config (never set aside). image_own_save NEW before the settings are copied,
# image_own_restore NEW after; upk_record removes what they keep in NEW/.mu300-image.
image_own_save() {
    rm -rf "$1/.mu300-image"; mkdir -p "$1/.mu300-image" || return 1
    for _uf in image-version image-packages packages.txt; do
        [ ! -f "$1/etc/mu300/$_uf" ] || cp "$1/etc/mu300/$_uf" "$1/.mu300-image/$_uf" || return 1
    done
    for _uf in "$1"/etc/config/*; do [ ! -e "$_uf" ] || echo "${_uf##*/}"; done > "$1/.mu300-image/config"
}
image_own_restore() {
    [ -d "$1/.mu300-image" ] || return 0
    mkdir -p "$1/etc/mu300" || return 1
    for _uf in image-version image-packages packages.txt; do
        if [ -f "$1/.mu300-image/$_uf" ]; then cp "$1/.mu300-image/$_uf" "$1/etc/mu300/$_uf" || return 1
        # a list of the old image would describe the wrong one (the version stays: "unknown" says less)
        elif [ "$_uf" != image-version ]; then rm -f "$1/etc/mu300/$_uf"; fi
    done
}
# upk_record OLD NEW OS: after the settings are in NEW, before the switch. Writes NEW/etc/mu300/user-packages/
# (wanted: the names; files: "package path" of their files in etc/; rc.d: the services enabled in OLD; from; state)
# and moves their etc/config files out of the way. MU300_KEEP_PACKAGES=0: they are not installed again (state
# skipped; mu300-user-packages retry does it later), their settings are set aside all the same.
upk_record() {
    _uo=$1 _un=$2 _uk=$(upk_kind "$3")
    _ut=$2/.mu300-image _ud=$2/$UPK_DIR
    mkdir -p "$_ut" || return 1
    # the old image's own set; a system from before that list: the new image's and the one packages.txt names
    if [ -s "$_uo/etc/mu300/image-packages" ]; then cat "$_uo/etc/mu300/image-packages"
    else
        cat "$_ut/image-packages" 2>/dev/null || :
        upk_manual "$_un" "$_uk"
        upk_txt_names "$_uo/etc/mu300/packages.txt"
    fi > "$_ut/not"
    upk_installed "$_un" "$_uk" >> "$_ut/not"
    # what an earlier update recorded and the device never got back (offline since, or skipped) stays wanted
    { upk_manual "$_uo" "$_uk"; upk_pending "$_uo/$UPK_DIR"; } > "$_ut/had"
    { sed 's/^/x /' "$_ut/not"; sed 's/^/w /' "$_ut/had"; } |
        awk '$1 == "x" { n[$2] = 1; next } NF > 1 && !($2 in n) { print $2 }' | sort -u > "$_ut/added"
    rm -rf "$_ud"
    : > "$_ut/wanted"
    while read -r _up; do upk_skip "$_up" || echo "$_up" >> "$_ut/wanted"; done < "$_ut/added"
    if [ ! -s "$_ut/wanted" ]; then
        echo "  none: everything installed is part of the new image"
        rm -rf "$_ut"
        return 0
    fi
    mkdir -p "$_ud" || return 1
    mv "$_ut/wanted" "$_ud/wanted"
    : > "$_ud/done"; : > "$_ud/failed"
    cat "$_uo/etc/mu300/image-version" > "$_ud/from" 2>/dev/null || echo unknown > "$_ud/from"
    # their files in etc/, from the package database of OLD (and of the record a pending one came from)
    if [ "$_uk" = openwrt ]; then
        { cat "$_uo/$UPK_DIR/files" 2>/dev/null || :
          [ ! -f "$_uo/lib/apk/db/installed" ] || awk '
            $0 ~ /^P:/ { p = substr($0, 3); next }
            $0 ~ /^F:/ { d = substr($0, 3); next }
            $0 ~ /^R:/ && (d == "etc" || d ~ /^etc\//) { print p " " d "/" substr($0, 3) }' "$_uo/lib/apk/db/installed"
        } | { sed 's/^/w /' "$_ud/wanted"; sed 's/^/f /'; } |
            awk '$1 == "w" { w[$2] = 1; next } ($2 in w) && NF > 2 { print substr($0, 3) }' | sort -u > "$_ud/files"
        for _uf in "$_uo"/etc/rc.d/*; do { [ -L "$_uf" ] || [ -e "$_uf" ]; } && echo "${_uf##*/}"; done > "$_ud/rc.d" || :
    else
        : > "$_ud/files"; : > "$_ud/rc.d"
    fi
    if [ "${MU300_KEEP_PACKAGES:-1}" = 0 ]; then echo skipped > "$_ud/state"; else echo pending > "$_ud/state"; fi
    echo "  $(tr '\n' ' ' < "$_ud/wanted")"
    if [ "$(cat "$_ud/state")" = skipped ]; then
        echo "  The new system does not have them, and they are not installed again (MU300_KEEP_PACKAGES=0 or"
        echo "  --no-reinstall; later: mu300-user-packages retry)."
    else
        echo "  The new system does not have them: its first boot installs them again once the device is online"
        echo "  (the result: mu300-user-packages status)."
    fi
    # their UCI files: a package that is not there must leave nothing behind that acts on the network. Only a file
    # its package owns, in etc/config, that the new image does not have itself (dhcp, firewall, luci: never).
    _um=
    while read -r _up _uf; do
        case $_uf in etc/config/?*) ;; *) continue ;; esac
        { [ -f "$_un/$_uf" ] && [ ! -L "$_un/$_uf" ]; } || continue
        ! grep -qxF "${_uf#etc/config/}" "$_ut/config" 2>/dev/null || continue
        mkdir -p "$_un/$UPK_ORPH/etc/config" && mv -f "$_un/$_uf" "$_un/$UPK_ORPH/$_uf" || return 1
        [ -n "$_um" ] || echo "  Their settings are set aside until they are back, so that they cannot act without them:"
        echo "    /$_uf -> /$UPK_ORPH/$_uf ($_up)"
        _um=1
    done < "$_ud/files"
    rm -rf "$_ut"
}
# --- user-packages end
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
        # the new image's version and package lists, and the names of its own etc/config files (upk_record)
        image_own_save "$M/$os.new"
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
        image_own_restore "$M/$os.new"
        # the packages installed on the device: written down, their settings set aside, put back at the first boot
        # (mu300-user-packages), as mu300-update apply does
        say "packages installed on the device in the previous $os:"
        upk=$(upk_record "$M/$os" "$M/$os.new" "$os") ||
            { rm -rf $M/$os.new; say "$upk"; say "$os: could not write down the packages installed on the device; $os was not replaced"; exit 1; }
        printf '%s\n' "$upk" | while IFS= read -r l; do say "$l"; done
        rm -rf "$M/$os.new/.mu300-image"
        if [ -f "$M/$os/etc/shadow" ]; then
            merge_accounts "$M/$os" "$M/$os.new" || { say "could not carry the accounts of $os over; nothing was replaced"; exit 1; }
            carried=1
            say "kept the accounts and passwords of the previous $os"
        fi
        extra_keep_vpn $M $M/$os
        [ -n "$extra" ] && say "kept enabled services:$extra"
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
