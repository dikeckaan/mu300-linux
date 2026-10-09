#!/system/bin/sh
# MU300 Linux from a Magisk zip: the whole installation, on the device, with no computer. customize.sh runs this as
# a child of Magisk's busybox (nothing here can change Magisk's own shell) and turns its exit status into the
# result: 0 installed, 3 dry run (nothing written), anything else refused or failed - the messages say what was and
# was not written.
#
# Everything device-specific - the header and AVB data of Android's boot image, the misc block, the firmware and the
# Android files - is read from this device here; the zip carries none of it. Nothing is written to the eMMC or the
# card before the systems are installed, and misc is armed last.
#
# This runs as root. Everything it checks and then uses lives in one directory only root can write (W, made under
# /data/adb): /data/local/tmp belongs to the shell user and /sdcard to every app with storage access, so a file
# there can be replaced between the check and the use. A settings file on /sdcard is read, but it can only choose
# what destroys nothing (see conf_load).
#
# MU300_LIB=1 defines the functions and runs nothing (tests/, which also set MU300_DIR to a directory laid out like
# the zip's mu300/). The MU300_* paths below point at a fake device there.
set -eu
D=${MU300_DIR:-$(cd "$(dirname "$0")" && pwd)}
# mu300-update first: it defines a say and a die of its own, which the ones below replace. MU300_LIB=1 while it is
# read makes it define its functions only; the caller's value comes back afterwards.
_mu300_lib=${MU300_LIB:-}
MU300_LIB=1
. "$D/mu300-update"
. "$D/android-boot-image.sh"
MU300_LIB=$_mu300_lib
TOP=$D                                   # i18n.sh reads $TOP/i18n
BY=${MU300_BY_NAME:-/dev/block/by-name}
SDCARD=${MU300_SDCARD:-/sdcard}
WORK_PARENT=${MU300_WORK_PARENT:-/data/adb}
W=                                       # the work directory, made by work_setup
MOUNTS=${MU300_MOUNTS:-/proc/mounts}
# the settings file that may also erase and set the password: only root can write /data/adb
TRUSTED_CONF=${MU300_TRUSTED_CONF:-/data/adb/mu300-install.conf}
# where the password is written (mode 600): root's file, or the shared storage only when a trusted conf says
# MU300_PASSWORD_FILE=sdcard (any app with storage access can read it there)
PW_FILE_ROOT=${MU300_PW_DIR:-/data/adb}/mu300-linux-password.txt
PW_FILE_SDCARD=$SDCARD/mu300-linux-password.txt
MAGISKBIN=${MAGISKBIN:-/data/adb/magisk}
MAGISKBOOT=${MAGISKBOOT:-$MAGISKBIN/magiskboot}
UBB=${MU300_UBB:-$D/busybox}             # the release's static busybox: its mkpasswd
DEVSH=${MU300_DEVICE_SH:-/system/bin/sh}
ANDROID_SH=${MU300_ANDROID_SH:-/system/bin/sh}
APATH=${MU300_ANDROID_PATH:-/system/bin:/system/xbin:/vendor/bin}
NEED_OPENWRT=$((800 * 1024 * 1024)); NEED_UBUNTU=$((1600 * 1024 * 1024)); NEED_BOTH=$((2400 * 1024 * 1024))
MU300_LANG=${MU300_LANG:-}
. "$D/i18n.sh"
. "$D/storage.sh"

say() { echo "- $*"; }
warn() { echo "! $*"; }
die() { echo "! $*"; exit 1; }
gib() { awk -v b="$1" 'BEGIN { printf "%.1f GiB", b / 1073741824 }'; }
# Android's own shell and toolbox, never Magisk's standalone busybox: its mke2fs makes ext2 only and its losetup has
# no -S. su -c sh gives install.sh exactly this environment. MU300_DEVICE_WORK tells android-install.sh where its files are.
asw() { env -u ASH_STANDALONE PATH="$APATH" MU300_DEVICE_WORK="${W:-}" "$@"; }
su_do() { asw "$DEVSH" -c "$1"; }            # storage.sh's way to run a command on the device: here it is local

android_lang() {  # the language of the Android locale: tr, zh or en
    _l=
    for _p in persist.sys.locale persist.sys.locales persist.sys.language ro.product.locale ro.product.locale.language; do
        _l=$(getprop "$_p" 2>/dev/null) && [ -n "$_l" ] && break
    done
    case ${_l%%,*} in tr|tr-*|tr_*) echo tr ;; zh|zh-*|zh_*) echo zh ;; *) echo en ;; esac
}

# ---- answers: mu300-install.conf, read line by line, never sourced (it is a text file, and this runs as root). Only
# these keys are taken. Two kinds of file:
#   trusted    /data/adb/mu300-install.conf when root owns it and nobody else can write it, and a
#              mu300-install.conf inside the zip (as trusted as the scripts it comes with)
#   untrusted  /sdcard/mu300-install.conf or /sdcard/Download/mu300-install.conf (first found): any app with
#              storage access can write these, so they choose only what destroys nothing and reveals nothing
# Trusted values win.
CONF_KEYS='MU300_STORAGE MU300_SD_ERASE MU300_REGION_OVERWRITE MU300_MODE MU300_BOOT_OS MU300_BOOT MU300_BOOT_ATTEMPTS MU300_HOTSPOT MU300_GPU MU300_PASSWORD MU300_PASSWORD_RESET MU300_PASSWORD_FILE MU300_DEVICE MU300_LANG MU300_DRY_RUN'
CONF_SET=
conf_find() { for _f in "$SDCARD/mu300-install.conf" "$SDCARD/Download/mu300-install.conf"; do [ -f "$_f" ] && { echo "$_f"; return 0; }; done; return 0; }
# erasing, formatting, overriding the model check and the password: only from a trusted file
conf_trusted_only() {  # conf_trusted_only KEY VALUE
    case $1 in
        MU300_SD_ERASE|MU300_REGION_OVERWRITE|MU300_PASSWORD|MU300_PASSWORD_RESET|MU300_PASSWORD_FILE|MU300_DEVICE) return 0 ;;
        MU300_MODE) [ "$2" = wipe ] ;;
        *) return 1 ;;
    esac
}
conf_trusted() {  # conf_trusted FILE: a regular file that root owns and nobody else can write
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    set -- $(ls -ln "$1")
    [ "${3:-}" = "${MU300_TRUSTED_UID:-0}" ] || return 1
    case $1 in ?????w*|????????w*) return 1 ;; esac
}
conf_load() {  # conf_load FILE [trusted]
    [ -n "$1" ] && [ -f "$1" ] || return 0
    _cf=$1; _tr=${2:-}; _set=; _ign=
    while IFS= read -r _line || [ -n "$_line" ]; do
        _line=$(printf '%s' "$_line" | tr -d '\r' | sed 's/^[[:space:]]*//')
        case $_line in ''|'#'*) continue ;; *=*) ;; *) continue ;; esac
        _k=$(printf '%s' "${_line%%=*}" | tr -d ' \t'); _v=${_line#*=}
        _v=$(printf '%s' "$_v" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
        case $_v in \"*\") _v=${_v#\"}; _v=${_v%\"} ;; \'*\') _v=${_v#\'}; _v=${_v%\'} ;; esac
        case " $CONF_KEYS " in
            *" $_k "*)
                # an empty value leaves the default; anything else must be exactly a value of that key before it is
                # assigned - MU300_LANG, for one, is part of a file name the moment it is set
                [ -n "$_v" ] || continue
                if ! conf_valid "$_k" "$_v"; then
                    [ "$_k" != MU300_PASSWORD ] || die "$(t 'mu300-install.conf: MU300_PASSWORD must have at least 6 characters')"
                    die "$(t 'mu300-install.conf: {1}={2} is not valid' "$_k" "$_v")"
                fi
                if [ "$_tr" != trusted ] && conf_trusted_only "$_k" "$_v"; then
                    _kv=$_k; [ "$_k" != MU300_MODE ] || _kv=$_k=$_v        # never a password's value
                    warn "$(t 'mu300-install.conf: {1} is taken only from {2}, which only root can change; ignored in {3}' "$_kv" "$TRUSTED_CONF" "$_cf")"
                    _ign="$_ign $_k"
                else
                    # $_k is one of CONF_KEYS: the eval is safe, and the value is assigned, never evaluated
                    _t=; [ "$_tr" != trusted ] || _t=1
                    eval "$_k=\$_v; SRC_$_k=\$_cf; TRUST_$_k=\$_t"; _set="$_set $_k"
                fi ;;
            *) warn "$(t 'mu300-install.conf: {1} is not a setting of this installer; ignored' "$_k")" ;;
        esac
    done < "$1"
    [ -z "$_set" ] || say "$(t 'settings from {1}:{2}' "$_cf" "$_set")"
    if [ -n "$_ign" ]; then
        if [ "$_cf" = "$TRUSTED_CONF" ]; then _c="su -c 'chown 0:0 $_cf && chmod 600 $_cf'"
        else _c="su -c 'cp $_cf $TRUSTED_CONF && chmod 600 $TRUSTED_CONF'"; fi
        say "$(t 'To use{1}, make the file one only root can change: {2}' "$_ign" "$_c")"
    fi
    CONF_SET="$CONF_SET$_set"
}
conf_read() {  # every settings file there is, the untrusted ones first so that trusted values win
    conf_load "$(conf_find)"
    _adb=
    if [ -e "$TRUSTED_CONF" ]; then
        if conf_trusted "$TRUSTED_CONF"; then _adb=trusted
        else
            warn "$(t '{1} is not owned by root, or others can change it: it is read like a file on /sdcard' "$TRUSTED_CONF")"
            conf_load "$TRUSTED_CONF"
        fi
    fi
    conf_load "$D/mu300-install.conf" trusted
    [ -z "$_adb" ] || conf_load "$TRUSTED_CONF" trusted
}
conf_valid() {  # conf_valid KEY VALUE: VALUE is exactly one this installer knows for KEY
    case $1 in
        MU300_STORAGE) case $2 in internal|sd) return 0 ;; esac ;;
        MU300_MODE) case $2 in update|wipe) return 0 ;; esac ;;
        MU300_BOOT_OS) case $2 in ubuntu|openwrt|openwrt-luci) return 0 ;; esac ;;
        MU300_BOOT) case $2 in linux|android) return 0 ;; esac ;;
        MU300_BOOT_ATTEMPTS) case $2 in [1-6]) return 0 ;; esac ;;
        MU300_SD_ERASE|MU300_REGION_OVERWRITE|MU300_PASSWORD_RESET) [ "$2" = yes ] && return 0 ;;
        MU300_HOTSPOT|MU300_GPU) case $2 in yes|no) return 0 ;; esac ;;
        MU300_PASSWORD_FILE) [ "$2" = sdcard ] && return 0 ;;
        MU300_DEVICE) case $2 in f50) return 0 ;; esac ;;
        MU300_LANG) case $2 in en|tr|zh) return 0 ;; esac ;;
        MU300_DRY_RUN) [ "$2" = 1 ] && return 0 ;;
        # any characters: it only ever goes to mkpasswd on stdin, never into a path or a command line
        MU300_PASSWORD) [ ${#2} -ge 6 ] && return 0 ;;
    esac
    return 1
}
conf_check() {  # every answer, from a file or the environment, has a value this installer knows
    for _k in $CONF_KEYS; do
        eval "_v=\${$_k:-}"
        [ -z "$_v" ] || conf_valid "$_k" "$_v" && continue
        [ "$_k" != MU300_PASSWORD ] || die "$(t 'mu300-install.conf: MU300_PASSWORD must have at least 6 characters')"
        die "$(t 'mu300-install.conf: {1}={2} is not valid' "$_k" "$_v")"
    done
}
src_of() { eval "_s=\${SRC_$1:-}"; if [ -n "$_s" ]; then echo "$_s"; else t 'default'; fi; }   # where a value came from

# ---- the device, its slots and the zip
env_check() {
    [ -n "${MU300_SKIP_ROOT_CHECK:-}" ] || [ "$(id -u)" = 0 ] || die "$(t 'this installer needs root')"
    [ -x "$MAGISKBOOT" ] || die "$(t "Magisk's magiskboot was not found; install this zip with Magisk 26 or newer")"
    chmod 755 "$UBB" 2>/dev/null || true
}
detect_device() {
    _m="$(getprop ro.product.model) / $(getprop ro.product.device)"
    say "$(t 'device: {1}' "$_m")"
    case $_m in
        *MU300*|*F50*|*mu300*|*MU3351*|*V50*) DEVICE=f50 ;;
        *) DEVICE= ;;
    esac
    [ -z "${MU300_DEVICE:-}" ] || DEVICE=$MU300_DEVICE
    [ -n "$DEVICE" ] || die "$(t 'This does not look like a ZTE F50/MU300. If it is one, put MU300_DEVICE=f50 into {1}.' "$TRUSTED_CONF")"
}
hex_at() { dd if="$1" bs=1 skip="$2" count="$3" 2>/dev/null | od -An -tx1 -v | tr -d ' \n'; }
slot_setup() {
    case $(getprop ro.boot.slot_suffix) in
        _a) ANDROID_SLOT=a; LINUX_SLOT=b ;;
        _b) ANDROID_SLOT=b; LINUX_SLOT=a ;;
        *) die "$(t 'cannot tell which slot Android runs from')" ;;
    esac
    MISC=$BY/misc; BOOT_ANDROID=$BY/boot_$ANDROID_SLOT; BOOT_LINUX=$BY/boot_$LINUX_SLOT
    [ -e "$MISC" ] && [ -e "$BOOT_ANDROID" ] && [ -e "$BOOT_LINUX" ] || die "$(t 'this is not an A/B device with misc, boot_a and boot_b')"
    # never the partition Android booted from, whatever the links say
    [ "$(readlink -f "$BOOT_ANDROID")" != "$(readlink -f "$BOOT_LINUX")" ] || die "$(t 'boot_a and boot_b are the same partition')"
    LIVE_BC=$(hex_at "$MISC" 2048 32)
    bc_valid "$LIVE_BC" || die "$(t 'misc holds no valid boot control block; nothing was changed')"
    say "$(t 'Android runs from slot {1}; Linux goes to slot {2} (boot_{2})' "$ANDROID_SLOT" "$LINUX_SLOT")"
}
# The manifest names files and is part of paths (the payload entries, $W/mu300-$OS.tar.gz): every field must be
# exactly one of the values a release has before anything is built from it - no "/", "..", leading "-" or blanks.
manifest_load() {  # the zip's manifest, read like the conf file: only these keys
    TAG= SYSTEM= OS= UBUNTU= KERNEL= KERNEL_ASSET= ROOTFS_ASSET= SHA256_KERNEL= SHA256_ROOTFS=
    while IFS='=' read -r _k _v; do
        case $_k in TAG|SYSTEM|OS|UBUNTU|KERNEL|KERNEL_ASSET|ROOTFS_ASSET|SHA256_KERNEL|SHA256_ROOTFS) eval "$_k=\$_v" ;; esac
    done < "$1"
    _ok=1
    case $TAG in v[0-9]*) ;; *) _ok= ;; esac
    case $TAG in *[!0-9A-Za-z._-]*|*..*) _ok= ;; esac
    case $SYSTEM:$OS:$UBUNTU:$ROOTFS_ASSET in
        openwrt:openwrt::mu300-openwrt-rootfs.tar.gz) ;;
        ubuntu-24.04:ubuntu:24.04:mu300-ubuntu-rootfs.tar.gz) ;;
        ubuntu-26.04:ubuntu:26.04:mu300-ubuntu-26.04-rootfs.tar.gz) ;;
        *) _ok= ;;
    esac
    case $KERNEL:$KERNEL_ASSET in
        5.4:mu300-kernel.tar.gz|6.18:mu300-kernel-6.18.tar.gz|7.2:mu300-kernel-7.2.tar.gz) ;;
        *) _ok= ;;
    esac
    for _h in "$SHA256_KERNEL" "$SHA256_ROOTFS"; do
        case $_h in *[!0-9a-f]*) _ok= ;; esac
        [ ${#_h} = 64 ] || _ok=
    done
    [ -n "$_ok" ] || die "$(t 'the zip is incomplete or damaged (its manifest is not valid)')"
    OSES=$OS
}
# A directory of this run only, which only root can enter: the payload, the scripts that run as root, the settings
# they get, the device's proprietary files and the mount points. A new name each run, so nothing an earlier run left
# behind (a filesystem still mounted after it was killed, say) is ever used or removed.
work_setup() {
    _um=$(umask); umask 077
    W=$(mktemp -d "$WORK_PARENT/mu300-magisk.XXXXXX" 2>/dev/null) || W=
    umask "$_um"
    [ -n "$W" ] && [ -d "$W" ] || { W=; die "$(t 'could not create a work directory in {1}' "$WORK_PARENT")"; }
    chmod 700 "$W"
    W=$(cd "$W" && pwd -P)                   # as /proc/mounts names it
}
# the misc block read at the start, kept as it was: arm_linux writes it back when the armed one does not verify
misc_save() {
    dd if="$MISC" of="$W/misc-bc-live.bin" bs=1 skip=2048 count=32 2>/dev/null &&
        [ "$(od -An -tx1 -v "$W/misc-bc-live.bin" | tr -d ' \n')" = "$LIVE_BC" ] ||
        die "$(t 'could not keep a copy of the misc block; nothing was changed')"
}
payload_unpack() {  # the two payload files copied out of the zip into W, and only those copies checked and used
    _need=$(( $(unzip -l "$ZIPFILE" "payload/*" | awk 'END { print $1 }') + 512 * 1048576 ))
    # -P: one line per filesystem (busybox puts a long device name on a line of its own)
    _free=$(( $(df -Pk "$W" | awk 'NR == 2 { print $4 }') * 1024 ))
    [ "$_free" -ge "$_need" ] || die "$(t 'not enough free space in {1}: {2} needed, {3} free' "$WORK_PARENT" "$(gib "$_need")" "$(gib "$_free")")"
    mkdir "$W/kernel"
    say "$(t 'Unpacking {1} and {2}' "$ROOTFS_ASSET" "$KERNEL_ASSET")"
    unzip -p "$ZIPFILE" "payload/$ROOTFS_ASSET" > "$W/mu300-$OS.tar.gz" &&
        unzip -p "$ZIPFILE" "payload/$KERNEL_ASSET" > "$W/kernel.tar.gz" || die "$(t 'could not unpack the zip')"
    [ "$(sha256sum "$W/mu300-$OS.tar.gz" | cut -d' ' -f1)" = "$SHA256_ROOTFS" ] &&
        [ "$(sha256sum "$W/kernel.tar.gz" | cut -d' ' -f1)" = "$SHA256_KERNEL" ] ||
        die "$(t 'the zip is damaged (checksum mismatch); download it again')"
    tar -xzf "$W/kernel.tar.gz" -C "$W/kernel" && rm -f "$W/kernel.tar.gz" || die "$(t 'could not unpack the kernel bundle')"
    KB=$W/kernel
    grep -qw "$DEVICE" "$KB/devices" 2>/dev/null || die "$(t 'this kernel does not support the {1}' "$DEVICE")"
}

# ---- leaving: W goes, but never a filesystem mounted in it. rm -rf into a mounted mu300root or mu300sd would
# delete the installed systems and everyone's files.
MOUNT_POINTS='mnt mu300root mu300root-internal'    # ours and android-install.sh's: only ever rmdir'd
mounted_at_or_under() {  # PATH: something is mounted on PATH or below it (also when the mount table is unreadable)
    [ -r "$MOUNTS" ] || return 0
    awk -v p="$1" '$2 == p || index($2, p "/") == 1 { f = 1 } END { exit !f }' "$MOUNTS"
}
cleanup() {  # every exit
    set +e
    write_example
    [ -n "${W:-}" ] && [ -d "$W" ] || return 0
    [ -z "${MOUNTED:-}" ] || umount_target "$MOUNTED"
    _left=
    for _e in "$W"/* "$W"/.[!.]*; do
        [ -e "$_e" ] || [ -L "$_e" ] || continue
        case " $MOUNT_POINTS " in *" ${_e##*/} "*) rmdir "$_e" 2>/dev/null || _left=1; continue ;; esac
        if mounted_at_or_under "$_e"; then _left=1; else rm -rf "$_e"; fi
    done
    rmdir "$W" 2>/dev/null || _left=1
    [ -z "$_left" ] || warn "$(t 'A Linux filesystem is still mounted in {1}; it was left as it is. Restart the device before installing again.' "$W")"
}

# ---- what to do
mount_target() {  # mount_target DIR [ro]: the Linux filesystem of the plan, with Android's mount helper
    cp "$D/android-mount-mu300root.sh" "$W/" || return 1
    _ro=; [ "${2:-}" != ro ] || _ro=1
    if [ "$SD_MODE" = 1 ]; then
        asw MU300_RO="$_ro" MU300_SD_DEV="$SD_DEV" "$ANDROID_SH" "$W/android-mount-mu300root.sh" "$1"
    else
        asw MU300_RO="$_ro" MU300_OFF="$INT_OFF" MU300_SIZE="$INT_SIZE" "$ANDROID_SH" "$W/android-mount-mu300root.sh" "$1"
    fi | grep -q '^MOUNTED' && MOUNTED=$1
}
# MOUNTED is cleared only after the helper said it unmounted; under set -e a bare failing call would end the
# function before that line
umount_target() { asw "$ANDROID_SH" "$W/android-mount-mu300root.sh" -u "$1" >/dev/null 2>&1 || return 1; MOUNTED=; }
need_for() { case $1 in openwrt) echo $NEED_OPENWRT ;; ubuntu) echo $NEED_UBUNTU ;; *) echo $NEED_BOTH ;; esac; }
no_room_inside() {  # the refusal when Linux does not fit inside, with the way out this device has
    if [ -n "$SD_DEV" ] && [ "$sd_ex" = foreign ]; then
        die "$(t 'There is too little free space inside for Linux, and the SD card ({1}) holds another Linux (ext4) filesystem, which the installer never formats. Copy off what you need and format the card elsewhere, or use another card.' "$SD_DEV")"
    elif [ -n "$SD_DEV" ]; then
        die "$(t 'There is too little free space inside for Linux. The SD card ({1}, {2}) can hold it: put MU300_STORAGE=sd and MU300_SD_ERASE=yes into {3}, a file only root can change (everything on the card is erased).' "$SD_DEV" "$(gib "$SD_BYTES")" "$TRUSTED_CONF")"
    elif [ "${SD_SMALL:-0}" = 1 ]; then
        die "$(t 'There is too little free space inside for Linux, and the SD card is smaller than 700 MiB. Use a bigger card (MU300_STORAGE=sd and MU300_SD_ERASE=yes in {1}), or make room with the installer for computers.' "$TRUSTED_CONF")"
    else
        die "$(t 'There is too little free space inside for Linux and no SD card. Insert a card (MU300_STORAGE=sd and MU300_SD_ERASE=yes in {1}), or make room with the installer for computers.' "$TRUSTED_CONF")"
    fi
}
# the storage an overwrite may hit was chosen by a trusted file, or by the installer itself (no MU300_STORAGE at
# all): for the card that means it already holds this project's mu300sd
aimed_by_trust() {  # aimed_by_trust sd|internal
    if [ -n "${MU300_STORAGE:-}" ]; then
        [ "$MU300_STORAGE" = "$1" ] && [ -n "${TRUST_MU300_STORAGE:-}" ]
    else
        [ "$1" = internal ] || [ "$sd_ex" = yes ]
    fi
}
# The settings this run erases with (MU300_MODE=wipe, MU300_SD_ERASE, MU300_REGION_OVERWRITE): after a successful
# install each becomes a comment in the trusted file, so that a standing one never applies to a later flash (the
# second zip of two would wipe the first system, every update the home directories, a new card would be erased).
USED_KEYS=
plan_storage() {
    region_probe || die "$(t 'could not read the partition table')"
    region_find_existing
    INT_OFF=$OFF; INT_SIZE=$SIZE; int_existing=$existing
    sd_probe; sd_ex=no
    [ -n "$SD_DEV" ] && sd_ex=$(sd_existing)
    case ${MU300_STORAGE:-} in
        sd) [ -n "$SD_DEV" ] || die "$(t 'MU300_STORAGE=sd, but there is no usable SD card in the device')"; SD_MODE=1 ;;
        internal)
            # boot/init starts a mu300sd card before anything on the eMMC, and nobody is here to type the word
            # storage.sh's internal_over_card asks for: an installation inside would never start
            [ "$sd_ex" != yes ] || die "$(t 'The SD card ({1}) holds a Linux installation (mu300sd), and the device always starts that one first: an installation to internal storage does not start while this card is in the slot.' "$SD_DEV")
$(t 'Take the card out and install the zip again, or install to the card (MU300_STORAGE=sd in /sdcard/mu300-install.conf).')"
            SD_MODE=0 ;;
        *)  # an installation where it is (the card first, as init looks there first), else inside when it fits
            if [ "$sd_ex" = yes ]; then SD_MODE=1
            elif [ "$int_existing" = yes ] || [ "$INT_SIZE" -ge "$(need_for "$OS")" ]; then SD_MODE=0
            else no_room_inside
            fi ;;
    esac
    if [ "$SD_MODE" = 1 ]; then
        sd_not_foreign
        existing=$([ "$sd_ex" = yes ] && echo yes || echo no); TARGET_SIZE=$SD_BYTES
    else
        existing=$int_existing; TARGET_SIZE=$INT_SIZE; DIRTY=0
        [ "$INT_SIZE" -ge $((700 * 1024 * 1024)) ] || no_room_inside
        if [ "$existing" = no ]; then
            region_dirty
            [ "$DIRTY" = 0 ] || { [ "${MU300_REGION_OVERWRITE:-}" = yes ] && aimed_by_trust internal; } ||
                die "$(t 'The free space behind the partitions is not empty ({1} of 16 samples hold data); it may be used by this firmware. To use it anyway, put MU300_STORAGE=internal and MU300_REGION_OVERWRITE=yes into {2}, a file only root can change.' "$DIRTY" "$TRUSTED_CONF")"
            [ "$DIRTY" = 0 ] || USED_KEYS="$USED_KEYS MU300_REGION_OVERWRITE"
        fi
    fi
    INTERNAL_EXISTS=0; [ "$int_existing" = yes ] && INTERNAL_EXISTS=1
    FORMAT=0; UPDATE=0
    if [ "$existing" = yes ]; then
        case ${MU300_MODE:-update} in update) UPDATE=1 ;; wipe) FORMAT=1 ;; esac
    else
        FORMAT=1
    fi
    # a wipe is used by the install that formats, also one onto a target with no filesystem yet (a blank region, a
    # new card): left standing, the next flash would wipe the system this one installs
    if [ "${MU300_MODE:-}" = wipe ] && [ "$FORMAT" = 1 ]; then USED_KEYS="$USED_KEYS MU300_MODE"; fi
    # A card is formatted only when a trusted file says MU300_SD_ERASE=yes, whatever the reason (a new card, or
    # MU300_MODE=wipe on a mu300sd one), and only when that same trust chose the card: a standing MU300_SD_ERASE=yes
    # in /data/adb must not be aimed at whatever card is in the slot by a MU300_STORAGE=sd any app can write.
    if [ "$SD_MODE" = 1 ] && [ "$FORMAT" = 1 ] && ! { [ "${MU300_SD_ERASE:-}" = yes ] && aimed_by_trust sd; }; then
        if [ "$existing" = yes ] && [ "${MU300_SD_ERASE:-}" != yes ]; then
            die "$(t 'MU300_MODE=wipe formats the SD card ({1}, {2}): the installation on it and everything else is erased. To allow that, put MU300_SD_ERASE=yes into {3} as well.' "$SD_DEV" "$(gib "$SD_BYTES")" "$TRUSTED_CONF")"
        fi
        die "$(t 'Installing to the SD card ({1}, {2}) erases everything on it. To allow that, put MU300_STORAGE=sd and MU300_SD_ERASE=yes into {3}, a file only root can change.' "$SD_DEV" "$(gib "$SD_BYTES")" "$TRUSTED_CONF")"
    fi
    if [ "$SD_MODE" = 1 ] && [ "$FORMAT" = 1 ]; then USED_KEYS="$USED_KEYS MU300_SD_ERASE"; fi
}
# HAVE_ACCOUNTS: the system of this zip is there with accounts of its own: its user (ubuntu, OpenWrt's root) has a
# crypt hash in /etc/shadow (not empty, not locked) that is not the image's default, and they are not the image's
# accounts (an older mu300-update leaves .mu300-accounts-from-image until they are carried over). Anything else, a
# shadow that cannot be read included, gets a new password: an update never keeps a default or an empty one.
image_hash() {  # image_hash USER: USER's hash in the image this zip installs (OpenWrt's root: empty); fails when the
    # image's shadow or USER's line in it cannot be read
    _ish=$(tar -xzOf "$W/mu300-$OS.tar.gz" ./etc/shadow 2>/dev/null || tar -xzOf "$W/mu300-$OS.tar.gz" etc/shadow 2>/dev/null) || _ish=
    printf '%s\n' "$_ish" | grep -q "^$1:" || return 1
    printf '%s\n' "$_ish" | sed -n "s/^$1:\([^:]*\):.*/\1/p" | head -n1
}
default_hash() {  # default_hash USER HASH: HASH is the image's own password (this image's hash, or a SHA-crypt hash of
    # the images' well-known "ubuntu", which the bundled mkpasswd can check; OpenWrt's is empty, never a hash)
    # an image whose hash cannot be read counts as the default: what cannot be decided gets a new password
    _ih=$(image_hash "$1") || return 0
    [ "$2" != "$_ih" ] || return 0
    case $2 in '$5$'*) _m=sha256 ;; '$6$'*) _m=sha512 ;; *) return 1 ;; esac
    _s=${2#\$?\$}; _s=${_s%%\$*}
    case $_s in rounds=*|'') return 1 ;; esac
    [ "$(printf '%s\n' ubuntu | "$UBB" mkpasswd -m "$_m" -S "$_s" -P 0 2>/dev/null)" = "$2" ]
}
inspect_target() {  # which systems the existing filesystem holds, and its Ubuntu release: mounted read-only
    HAVE_SYSTEMS=; HAVE_UBUNTU=; HAVE_ACCOUNTS=0
    [ "$existing" = yes ] && [ "$FORMAT" = 0 ] || return 0
    mount_target "$W/mnt" ro || die "$(t 'could not mount the existing Linux filesystem')"
    for _os in ubuntu openwrt openwrt-luci; do [ -d "$W/mnt/$_os" ] && HAVE_SYSTEMS="$HAVE_SYSTEMS $_os"; done
    _u=root; [ "$OS" != ubuntu ] || _u=ubuntu
    _h=$(sed -n "s/^$_u:\([^:]*\):.*/\1/p" "$W/mnt/$OS/etc/shadow" 2>/dev/null | head -n1) || _h=
    case $_h in
        '$'?*) if [ ! -e "$W/mnt/$OS/etc/.mu300-accounts-from-image" ] && ! default_hash "$_u" "$_h"; then
                   HAVE_ACCOUNTS=1; fi ;;
    esac
    _h=
    HAVE_UBUNTU=$(sed -n 's/^VERSION_ID="\(.*\)"/\1/p' "$W/mnt/ubuntu/usr/lib/os-release" 2>/dev/null | head -n1)
    umount_target "$W/mnt" || die "$(t 'could not unmount the Linux filesystem from {1}' "$W/mnt")"
}
plan_choices() {
    _after=$(printf '%s\n' $HAVE_SYSTEMS "$OS" | sort -u | tr '\n' ' ')
    case $_after in *ubuntu*openwrt*|*openwrt*ubuntu*) _need=$NEED_BOTH ;; *) _need=$(need_for "$OS") ;; esac
    [ "$TARGET_SIZE" -ge "$_need" ] || die "$(t 'that choice needs about {1} MiB and this device has {2} MiB of free space' "$((_need / 1048576))" "$((TARGET_SIZE / 1048576))")"
    if [ "$KERNEL" = 5.4 ] && case " $HAVE_SYSTEMS " in *" ubuntu "*) [ "$HAVE_UBUNTU" = 26.04 ] ;; *) false ;; esac; then
        die "$(t 'Ubuntu 26.04 is installed, and it needs a mainline kernel (6.18 or 7.2): use a zip with one of those kernels, or MU300_MODE=wipe.')"
    fi
    sd_kernel_ok "$KB" || die "$(t 'this kernel cannot read the SD card; use a newer zip')"
    BOOT_OS=${MU300_BOOT_OS:-$OS}
    case " $_after " in *" $BOOT_OS "*) ;; *) die "$(t 'MU300_BOOT_OS={1}, but {1} is not installed' "$BOOT_OS")" ;; esac
    DEFAULT_LINUX=1; [ "${MU300_BOOT:-linux}" = android ] && DEFAULT_LINUX=0
    BOOT_ATTEMPTS=${MU300_BOOT_ATTEMPTS:-5}
    IMPORT_HOTSPOT=1; [ "${MU300_HOTSPOT:-yes}" = no ] && IMPORT_HOTSPOT=0
    GPU=${MU300_GPU:-yes}
    PW_FILE=$PW_FILE_ROOT; [ "${MU300_PASSWORD_FILE:-}" != sdcard ] || PW_FILE=$PW_FILE_SDCARD
    # Update (keep) leaves the accounts and their passwords as they are, as mu300-update does: a password is made only
    # for a system that has none of its own yet (a new filesystem, a wipe, a system added beside another), or when
    # /data/adb/mu300-install.conf asks for one (MU300_PASSWORD, MU300_PASSWORD_RESET=yes: trusted only)
    KEEP_PW=0
    if [ "$UPDATE" = 1 ] && [ "${HAVE_ACCOUNTS:-0}" = 1 ] && [ -z "${MU300_PASSWORD:-}" ] &&
        [ "${MU300_PASSWORD_RESET:-}" != yes ]; then KEEP_PW=1; fi
    # an if, not an && list: the last command's status is the function's, and set -e would stop main on it
    WIPE_LEGACY=0; if [ "$OS" = ubuntu ] && [ "$FORMAT" = 0 ]; then WIPE_LEGACY=1; fi
}
plan_print() {
    echo
    say "$(t 'Plan')"
    echo "  $(t 'system:         {1} (zip {2}, kernel {3})' "$OS${UBUNTU:+ $UBUNTU}" "$TAG" "$KERNEL")"
    if [ "$SD_MODE" = 1 ]; then
        echo "  $(t 'storage:        SD card {1}, {2} ({3})' "$SD_DEV" "$(gib "$TARGET_SIZE")" "$(src_of MU300_STORAGE)")"
    else
        echo "  $(t 'storage:        internal, offset {1}, {2} ({3})' "$INT_OFF" "$(gib "$TARGET_SIZE")" "$(src_of MU300_STORAGE)")"
    fi
    echo "  $(t 'filesystem:     {1} ({2})' "$([ "$FORMAT" = 1 ] && t 'CREATE new ext4 (erases what is there)' || t 'keep: settings and data of {1} are kept' "$OS")" "$(src_of MU300_MODE)")"
    [ -z "$HAVE_SYSTEMS" ] || echo "  $(t 'already there:  {1}' "$HAVE_SYSTEMS")"
    echo "  $(t 'boots:          {1} ({2})' "$BOOT_OS" "$(src_of MU300_BOOT_OS)")"
    echo "  $(t 'default boot:   {1} ({2})' "$([ "$DEFAULT_LINUX" = 1 ] && t 'Linux, Android after failed boots' || t 'Android, Linux on demand')" "$(src_of MU300_BOOT)")"
    echo "  $(t 'boot attempts:  {1} failed boots in a row, then Android ({2})' "$BOOT_ATTEMPTS" "$(src_of MU300_BOOT_ATTEMPTS)")"
    echo "  $(t 'hotspot:        {1} ({2})' "$([ "$IMPORT_HOTSPOT" = 1 ] && t 'name and password copied from Android' || t 'not copied')" "$(src_of MU300_HOTSPOT)")"
    echo "  $(t 'GPU files:      {1} ({2})' "$([ "$GPU" = yes ] && t 'included' || t 'not included')" "$(src_of MU300_GPU)")"
    if [ "$KEEP_PW" = 1 ]; then
        echo "  $(t 'password:       kept: the accounts and passwords of the installed system are not changed ({1} in {2} sets a new one)' "MU300_PASSWORD_RESET=yes" "$TRUSTED_CONF")"
    elif [ -n "${MU300_PASSWORD:-}" ]; then
        echo "  $(t 'password:       from {1}, written to {2}' "$(src_of MU300_PASSWORD)" "$PW_FILE")"
    else
        echo "  $(t 'password:       generated, written to {1}' "$PW_FILE")"
    fi
    echo "  $(t 'writes:         {1}, boot_{2}, 32 bytes of misc (boot_{3}, the partition table and userdata are not touched)' "$([ "$SD_MODE" = 1 ] && echo "$SD_DEV" || t 'the Linux region')" "$LINUX_SLOT" "$ANDROID_SLOT")"
}
# Every setting, what it does and the value this run used (or would have: a refused run writes it too, with what
# was known by then), so nobody has to type it from a README. Any app can write $SDCARD, so it is never opened by
# its name: a new file with a random name is created exclusively and renamed over the target, and rename replaces
# whatever is there (a link included) instead of writing through it.
write_example() {
    _ex=$SDCARD/mu300-install.conf.example
    [ ! -d "$_ex" ] || [ -L "$_ex" ] || return 0
    _rnd=$(head -c 8 /dev/urandom 2>/dev/null | od -An -tx1 | tr -d ' \n')
    _new=$SDCARD/.mu300-install.conf.example.$$.$_rnd
    [ ! -e "$_new" ] && [ ! -L "$_new" ] || return 0
    ( set -C; {
        echo "# MU300 Linux Magisk installer settings. Copy to $SDCARD/mu300-install.conf, edit, install the zip again."
        echo "# Settings marked (root) are taken only from $TRUSTED_CONF, which only root can change: any app can write"
        echo "# to $SDCARD. Copy this file there with: su -c 'cp $SDCARD/mu300-install.conf $TRUSTED_CONF && chmod 600 $TRUSTED_CONF'"
        echo "# Values of the last run (${TAG:-}, $(date '+%Y-%m-%d %H:%M')) are shown; a line starting with # is not used."
        echo "# To use a setting, remove the # in front of its key (only there: the explanation stays a comment line)."
        echo "# MU300_MODE=wipe, MU300_SD_ERASE, MU300_REGION_OVERWRITE and MU300_PASSWORD count for one install: once a"
        echo "# successful install has used one, the installer turns its line in $TRUSTED_CONF into a comment."
        echo
        echo "# internal or sd"
        echo "#MU300_STORAGE=$([ "${SD_MODE:-0}" = 1 ] && echo sd || echo internal)"
        echo "# (root) allow formatting the SD card for Linux: everything on it is erased"
        echo "#MU300_SD_ERASE=yes"
        echo "# (root) use internal free space that holds data"
        echo "#MU300_REGION_OVERWRITE=yes"
        echo "# update (keep settings and data), or wipe (root)"
        echo "#MU300_MODE=update"
        echo "# ubuntu or openwrt: which system boots"
        echo "#MU300_BOOT_OS=${BOOT_OS:-${OS:-}}"
        echo "# linux (default boot, Android after failed boots) or android"
        echo "#MU300_BOOT=linux"
        echo "# 1-6 failed boots in a row before Android"
        echo "#MU300_BOOT_ATTEMPTS=${BOOT_ATTEMPTS:-5}"
        echo "# copy Android's hotspot name and password: yes or no"
        echo "#MU300_HOTSPOT=yes"
        echo "# Mali GPU (OpenCL) files: yes or no"
        echo "#MU300_GPU=yes"
        echo "# (root) 6+ characters; empty: generated"
        echo "#MU300_PASSWORD="
        echo "# (root) yes: a new generated password also when updating (an update keeps the existing one)"
        echo "#MU300_PASSWORD_RESET=yes"
        echo "# (root) write the password to $PW_FILE_SDCARD instead of $PW_FILE_ROOT"
        echo "#MU300_PASSWORD_FILE=sdcard"
        echo "# (root) f50, only when the model is not recognised"
        echo "#MU300_DEVICE=${DEVICE:-f50}"
        echo "# en, tr or zh"
        echo "#MU300_LANG=${MU300_LANG:-en}"
        echo "# only show what would be done"
        echo "#MU300_DRY_RUN=1"
    } > "$_new" ) 2>/dev/null &&
        [ -f "$_new" ] && [ ! -L "$_new" ] && rm -f "$_ex" && mv -f "$_new" "$_ex" 2>/dev/null
    rm -f "$_new" 2>/dev/null
    return 0
}

# ---- the password: never empty, never the image's. 12 characters without look-alikes, unless a trusted conf gives
# one.
PW_ALPHABET=abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789
CRYPT_ITOA=./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
random_chars() {  # random_chars ALPHABET N: bytes past the last whole multiple of the alphabet are skipped (no bias)
    head -c 256 /dev/urandom | od -An -tu1 -v | awk -v a="$1" -v n="$2" '
        BEGIN { l = length(a); lim = int(256 / l) * l }
        { for (i = 1; i <= NF && got < n; i++) if ($i < lim) { s = s substr(a, $i % l + 1, 1); got++ } }
        END { if (got < n) exit 1; print s }'
}
password_hash() {  # password_hash PASSWORD: SHA-512 crypt, password on stdin, as install.sh's sha512crypt.py makes it
    _salt=$(random_chars "$CRYPT_ITOA" 16) || return 1
    _h=$(printf '%s\n' "$1" | "$UBB" mkpasswd -m sha512 -S "$_salt" -P 0) || return 1
    case $_h in "\$6\$$_salt\$"?*) printf '%s' "$_h" ;; *) return 1 ;; esac
}
# FILE written with what CONTENT_CMD prints, mode 600, never through a link someone placed there: a new file with a
# random name is created exclusively in the same directory and renamed over FILE (rename replaces a link instead of
# writing through it; a link to a directory is removed first, or mv would move the file into that directory)
replace_file() {  # replace_file FILE CONTENT_CMD...
    _rf=$1; shift
    [ ! -d "$_rf" ] || [ -L "$_rf" ] || return 1
    _rnd=$(head -c 8 /dev/urandom 2>/dev/null | od -An -tx1 | tr -d ' \n')
    _new=${_rf%/*}/.${_rf##*/}.$$.$_rnd
    if ( umask 077; set -C; "$@" > "$_new" ) 2>/dev/null && [ -f "$_new" ] && [ ! -L "$_new" ] &&
        chmod 600 "$_new" && rm -f "$_rf" && mv -f "$_new" "$_rf" 2>/dev/null; then
        return 0
    fi
    rm -f "$_new" 2>/dev/null
    return 1
}

# ---- build everything in $W before anything is written
build_vendor() {
    _miss=$(collect_firmware "$W/fw") || die "$(t 'these firmware files could not be read from the device:{1}' "$_miss")
$(t 'Wi-Fi and Bluetooth need them; without them the system installs and boots but has no hotspot.')"
    collect_subset "$D/subset-files.txt" "$W/subset" || die "$(t 'could not read the Android files the modem needs from this device')"
    _gpu=
    if [ "$GPU" = yes ]; then
        if collect_gpu "$D/gpu-files.txt" "$W/gpu"; then _gpu=$W/gpu
        else warn "$(t 'the Mali GPU files are incomplete on this device; installing without them')"; fi
    fi
    vendor_overlay "$OS" "$W/fw" "$W/subset" "$_gpu" "$W/mu300-vendor-$OS.tar.gz" || die "$(t 'could not pack the vendor files')"
}
build_boot() {
    mkdir -p "$W/ramdisk/etc" "$W/boot"
    echo "$DEVICE" > "$W/ramdisk/etc/mu300-device"
    echo "$LINUX_SLOT" > "$W/ramdisk/etc/mu300-linux-slot"
    bc_files "$LIVE_BC" "$W/ramdisk/etc" || die "$(t 'could not build the boot control blocks')"
    cp -a "$W/subset" "$W/ramdisk/android" || die "$(t 'could not copy the Android files into the boot ramdisk')"
    # Linux on slot a needs an init that knows it (Tasks 1-3); the init comes from the bundle's generic segment
    if [ "$LINUX_SLOT" = a ]; then
        "$MAGISKBOOT" decompress "$KB/ramdisk-generic.lz4" "$W/generic.cpio" >/dev/null 2>&1 &&
            grep -q 'mu300-linux-slot' "$W/generic.cpio" ||
            die "$(t 'Android runs from slot b, and the kernel of this zip cannot boot Linux from slot a yet; use a newer zip')"
        rm -f "$W/generic.cpio"
    fi
    device_segment "$W/ramdisk" "$W/device.lz4" || die "$(t 'could not build the boot ramdisk (magiskboot)')"
    linux_boot_image "$BOOT_ANDROID" "$KB" "$W/device.lz4" "$W/boot" || die "$(t 'could not build the boot image')"
    # the Android-side switch arms a slot only when its image says loglevel=5 (Android's own say nothing)
    [ "$(dd if="$W/boot/new" bs=1 skip=44 count=11 2>/dev/null | od -An -tx1 | tr -d ' \n')" = 6c6f676c6576656c3d3500 ] ||
        die "$(t 'could not build the boot image')"
    say "$(t 'boot image for slot {1}: kernel {2}, {3} bytes' "$LINUX_SLOT" "$(cat "$KB/kernel.release" 2>/dev/null || echo 5.4)" "$(( $(fsize "$W/boot/new") + $(fsize "$W/boot/vbmeta") ))")"
}
build_password() {
    PW=; PWHASH=
    [ "$KEEP_PW" = 0 ] || return 0                # android-install.sh carries the accounts over
    PW=${MU300_PASSWORD:-}
    [ -n "$PW" ] || PW=$(random_chars "$PW_ALPHABET" 12) || die "$(t 'could not generate a password')"
    PWHASH=$(password_hash "$PW") || die "$(t 'could not hash the password')"
}

# ---- install: the systems, then the boot image, then misc
# mu300-install.env as install.sh writes it (storage.sh): OFF and INT_SIZE are the internal region, SIZE the region
# or, in SD mode, the card
install_env() {
    OFF=$INT_OFF; SIZE=$INT_SIZE
    if [ "$SD_MODE" = 1 ]; then SIZE=$SD_BYTES; fi
    ( umask 077; write_install_env > "$W/mu300-install.env" ) || die "$(t 'could not write {1}' "$W/mu300-install.env")"
}
install_systems() {
    say "$(t 'Installing {1} (this takes a few minutes)' "$OS")"
    cp "$D/android-install.sh" "$D/android-mount-mu300root.sh" "$W/" || die "$(t 'could not copy the installer files')"
    install_env
    asw "$ANDROID_SH" "$W/android-install.sh" 2>&1 | tee "$W/device-install.log"
    grep -q MU300-INSTALL-OK "$W/device-install.log" || die "$(t 'installation on the device failed; boot_{1} and misc were not changed' "$LINUX_SLOT")"
    if [ -s "$KB/kernel.release" ]; then        # a mainline bundle: its modules into every system on the filesystem
        mount_target "$W/mnt" || die "$(t 'could not mount the Linux filesystem for the kernel modules')"
        DISK=$W/mnt MU300_NO_DEPMOD=1 kernel_modules_into_systems "$KB" ||
            { umount_target "$W/mnt"; die "$(t 'could not install the kernel modules')"; }
        sync
        umount_target "$W/mnt" || die "$(t 'could not unmount the Linux filesystem from {1}' "$W/mnt")"
    fi
}
install_boot() {
    say "$(t 'Writing and verifying boot_{1}' "$LINUX_SLOT")"
    write_boot "$BOOT_LINUX" "$(part_size "$BOOT_LINUX")" "$W/boot/new" "$W/boot/vbmeta" "$W/boot/newfooter" ||
        die "$(t 'boot_{1} did not verify after writing; misc was not changed, so Android keeps booting' "$LINUX_SLOT")"
}
arm_linux() {  # the Linux slot's trial block, built from the misc block read at the start; misc must still hold that
    _blk=$W/ramdisk/etc/misc-bc-slot-$LINUX_SLOT-trial.bin
    [ "$(hex_at "$MISC" 2048 32)" = "$LIVE_BC" ] || die "$(t 'misc changed during the installation; Linux was not armed. Install the zip again.')"
    if dd if="$_blk" of="$MISC" bs=1 seek=2048 conv=notrunc 2>/dev/null && sync &&
        [ "$(hex_at "$MISC" 2048 32)" = "$(od -An -tx1 -v "$_blk" | tr -d ' \n')" ]; then
        return 0
    fi
    # misc may now hold anything: the block it held before goes back, and is read back too
    dd if="$W/misc-bc-live.bin" of="$MISC" bs=1 seek=2048 conv=notrunc 2>/dev/null || true
    sync || true
    [ "$(hex_at "$MISC" 2048 32)" != "$LIVE_BC" ] ||
        die "$(t 'misc did not verify after writing; the block it held before was written back and verified, so Android boots as before. Linux was not armed.')"
    # W goes when this exits: the block is kept where root can still reach it
    _keep=$WORK_PARENT/mu300-misc-bc-before.bin
    cp "$W/misc-bc-live.bin" "$_keep" 2>/dev/null || true
    die "$(t 'misc did not verify after writing, and the block it held before could not be written back: misc holds unknown bytes, and the device may not start Android. Do not reboot. Write the saved block back as root: {1}' "dd if=$_keep of=$MISC bs=1 seek=2048 conv=notrunc")"
}
pw_text() {
    printf 'MU300 Linux %s, %s\nuser: %s\npassword: %s\nDelete this file after the first login.\n' "$TAG" "$(date '+%Y-%m-%d %H:%M')" "$_users" "$PW"
    # The other system, installed beside this one by an earlier zip, keeps its password: so does the file (its block
    # from the file this one replaces), or the first zip's password would be lost with its output. Not after a
    # wipe (HAVE_SYSTEMS is empty then), and never a block of this run's user.
    case $OS in ubuntu) _ou=root _os=openwrt ;; *) _ou=ubuntu _os=ubuntu ;; esac
    case " $HAVE_SYSTEMS " in *" $_os "*) ;; *) return 0 ;; esac
    [ -f "$PW_FILE" ] && [ ! -L "$PW_FILE" ] || return 0
    awk -v u="user: $_ou" '
        /^MU300 Linux / { if (keep) printf "\n%s", b; b = ""; keep = 0 }
        $0 == "" { next }
        { b = b $0 "\n" }
        $0 == u { keep = 1 }
        END { if (keep) printf "\n%s", b }' "$PW_FILE"
}
# between quotes: a password of the conf file may hold blanks
pw_show() {
    if [ "$KEEP_PW" = 1 ]; then echo "  $(t 'password for {1}: unchanged (the one this system had)' "$_users")"; return 0; fi
    echo "  $(t 'password for {1}: "{2}"   (also in {3}; delete that file after the first login)' "$_users" "$PW" "$PW_FILE")"
}
# Shown and saved before anything is written: android-install.sh puts the hash into the systems, and a run that fails
# or is killed after that must not leave a Linux whose password nobody has seen. No file, no installation.
save_password() {
    _users=root; [ "$OS" != ubuntu ] || _users=ubuntu
    [ "$KEEP_PW" = 0 ] || return 0                # nothing new to show or save; the file stays as it is
    replace_file "$PW_FILE" pw_text || die "$(t 'could not write {1}; nothing was installed' "$PW_FILE")"
    pw_show
}
# A MU300_PASSWORD or MU300_PASSWORD_RESET line in the trusted conf, and an erasing setting this run used
# (USED_KEYS), have done their job: each becomes a comment (the file stays root's, mode 600). A key is matched as
# conf_load reads it (blanks around and inside it do not count); a conf inside the zip is never edited.
conf_drop_used() {
    awk -v d="$_drop " '{ l = $0; sub(/^[ \t]*/, "", l); k = l; sub(/=.*/, "", k); gsub(/[ \t]/, "", k)
           if (index(l, "=") && k != "" && index(d, " " k " ")) print "# " k " was used by the installer and removed"; else print }' "$TRUSTED_CONF"
}
# Linux is armed by now: nothing here may fail the run (main ignores its status), or customize.sh would call an
# installed Linux "not installed"
report() {
    _ip=192.168.77.1
    _drop=
    for _k in $USED_KEYS MU300_PASSWORD MU300_PASSWORD_RESET; do
        eval "_s=\${SRC_$_k:-}"
        [ "$_s" != "$TRUSTED_CONF" ] || _drop="$_drop $_k"
    done
    if [ -n "$_drop" ] && conf_trusted "$TRUSTED_CONF"; then
        if replace_file "$TRUSTED_CONF" conf_drop_used; then
            say "$(t 'used by this installation and removed from {1}:{2}' "$TRUSTED_CONF" "$_drop")"
        else
            warn "$(t 'could not remove{1} from {2}; remove it by hand' "$_drop" "$TRUSTED_CONF")"
        fi
    fi
    echo
    say "$(t 'Done. Reboot to start {1}.' "$BOOT_OS")"
    pw_show
    echo "  $(t 'USB network: {1}   SSH: {2}' "$_ip" "$_users@$_ip")"
    echo "  $(t 'switch systems: mu300-os {1}   back to Android: mu300-next-boot android' "$(echo $_after | tr ' ' '|')")"
    echo "  $(t 'If Linux does not start, the device returns to Android by itself.')"
    # the zip holds the release's systems and kernel only: the VPN engines are the vpn extra (mu300-extra), a
    # download of its own (a reinstall over a system that uses the VPN keeps that system's engines: android-install.sh)
    echo "  $(t 'The VPN (mu300-vpn) needs the vpn extra: Xray and sing-box. It can also be added later on the device:')"
    echo "    sudo mu300-extra install vpn"
}

main() {
    trap cleanup EXIT
    [ -n "$MU300_LANG" ] || MU300_LANG=$(android_lang)
    conf_valid MU300_LANG "$MU300_LANG" || MU300_LANG=en      # it is part of a file name in t()
    manifest_load "$D/manifest"
    echo "MU300 Linux $TAG"
    conf_read
    conf_check
    env_check
    detect_device
    slot_setup
    work_setup
    misc_save
    payload_unpack
    plan_storage
    inspect_target
    plan_choices
    plan_print
    if [ "${MU300_DRY_RUN:-}" = 1 ]; then say "$(t 'Dry run: nothing was written.')"; exit 3; fi
    build_vendor
    build_boot
    build_password
    save_password
    install_systems
    install_boot
    arm_linux
    report || true
}
[ -z "${MU300_LIB:-}" ] || return 0
main "$@"
