# Where the Linux filesystem goes: the free eMMC region or the SD card. Sourced by install.sh, uninstall.sh and
# tools/reset-password.sh (su_do, ask, t, die and gib are theirs).
#   region_probe     last_end / disk (sectors) and OFF / SIZE (bytes) of the free eMMC region; 1 when the device
#                    gave no answer
#   region_find_existing  existing=yes|no; an installed mu300root defines OFF / SIZE
#   region_dirty     DIRTY, how many of 16 samples across the region hold data
#   sd_probe         SD_DEV / SD_BYTES of the card in the slot (empty without one), SD_SMALL=1 when it is too small
#   sd_existing      yes when the card already holds a mu300sd filesystem, foreign for any other ext4, else no
#   choose_storage   SD_MODE=0|1; MU300_STORAGE=internal|sd answers without asking (internal while the card
#                    holds mu300sd still needs the typed word: that card would boot instead)
#   sd_kernel_ok     a card installation refuses a kernel bundle that cannot read the card
#   sd_erase         uninstall.sh: overwrite the start of the card's mu300sd filesystem (nothing else, ever)
#   write_install_env  install.sh: the text of mu300-install.env (install.ps1's InstallEnvText writes the same)

SD_MIN=$((700 * 1024 * 1024))

# One line from the device: "<block device> <512-byte sectors> <type>" for the first mmc disk that is not the
# eMMC - its first partition when it has one, the whole card otherwise. The type keeps a second eMMC or an SDIO
# function out.
sd_probe() {
    SD_DEV=; SD_BYTES=0; SD_SMALL=0
    set -- $(su_do 'for b in /sys/block/mmcblk[1-9]; do [ -e $b/device/type ] || continue; n=${b##*/}; if [ -e $b/${n}p1 ]; then echo /dev/block/${n}p1 $(cat $b/${n}p1/size) $(cat $b/device/type); else echo /dev/block/$n $(cat $b/size) $(cat $b/device/type); fi; break; done')
    [ $# -eq 3 ] && [ "$3" = SD ] || return 0
    if [ $(( $2 / 2048 )) -lt $(( SD_MIN / 1048576 )) ]; then SD_SMALL=1; return 0; fi
    SD_DEV=$1; SD_BYTES=$(( $2 * 512 ))
}

sd_existing() {
    m=$(su_do "dd if=$SD_DEV bs=1 skip=1080 count=2 2>/dev/null | od -An -tx1" | tr -d ' ')
    [ "$m" = 53ef ] || { echo no; return 0; }
    # LC_ALL=C: those bytes need not be text, and macOS's tr in a UTF-8 locale complains about them
    l=$(su_do "dd if=$SD_DEV bs=1 skip=1144 count=16 2>/dev/null" | LC_ALL=C tr -d '\000')
    # any other ext4, labelled or not, is foreign: android-install.sh's sd_prepare refuses to format it
    if [ "$l" = mu300sd ]; then echo yes; else echo foreign; fi
}

choose_storage() {
    SD_MODE=0
    _ex=no; [ -z "$SD_DEV" ] || _ex=$(sd_existing)
    case ${MU300_STORAGE:-} in
        internal) internal_over_card "$_ex"; return 0 ;;
        sd) [ -n "$SD_DEV" ] || die "$(t 'MU300_STORAGE=sd, but there is no usable SD card in the device')"
            SD_MODE=1; sd_not_foreign; return 0 ;;
        '') ;;
        *) die "$(t 'MU300_STORAGE must be internal or sd')" ;;
    esac
    [ -n "$SD_DEV" ] || return 0
    # too little room inside: the card is the way that needs no repartitioning; a card that holds an installation
    # already: that is what the device starts, so it is what an update or reinstall is about
    _d=internal; { [ "$SIZE" -lt "$SD_MIN" ] || [ "$_ex" = yes ]; } && _d=sd
    ask _st "$(t 'Where should the Linux filesystem go: internal storage or the SD card ({1}, {2})? (internal/sd)' "$SD_DEV" "$(gib "$SD_BYTES")")" $_d
    case $_st in
        internal) internal_over_card "$_ex" ;;
        sd) SD_MODE=1; sd_not_foreign ;;
        *) die "$(t 'invalid choice')" ;;
    esac
}

# boot/init starts a mu300sd card before anything on the eMMC, so an internal installation made while such a card
# is in the slot never starts. Say so, and go on only when the user types the word.
internal_over_card() {  # internal_over_card EXISTING   (sd_existing of the card in the slot)
    [ "$1" = yes ] || return 0
    echo "$(t 'The SD card ({1}) holds a Linux installation (mu300sd), and the device always starts that one first: an installation to internal storage does not start while this card is in the slot.' "$SD_DEV")"
    echo "$(t 'Take the card out before the device restarts, or erase its installation first with the uninstaller.')"
    ask _ok "$(t 'Type internal to install to internal storage anyway')" no
    [ "$_ok" = internal ] || die "$(t 'cancelled')"
}

# A card installation needs a kernel that reads the card. The mainline bundles that do say so in ./features (older
# ones gate the SD host off, FINDINGS 31j): with one of those the device would not find its card and land in Android.
sd_kernel_ok() {  # sd_kernel_ok DIR: the unpacked bundle DIR is fine for this installation
    [ "$SD_MODE" = 1 ] || return 0
    grep -qx sdcard "$1/features" 2>/dev/null || return 1
}

# Another Linux filesystem on the card may be someone's data, and the device refuses to format it. Say so now,
# not after the password, the download and the build.
sd_not_foreign() {
    [ "$(sd_existing)" = foreign ] || return 0
    die "$(t 'the SD card ({1}) holds another Linux (ext4) filesystem, and the installer never formats one that is not its own (mu300sd).' "$SD_DEV")
$(t 'Copy off what you need and format the card elsewhere, use another card, or install to internal storage (MU300_STORAGE=internal).')"
}

# The device command that erases the mu300sd filesystem on DEV (uninstall.ps1 sends the same text, so no quotes of
# either kind). The host has checked all of this already; the device checks it again right before the write, so a
# wrong DEV can never reach the eMMC: not mmcblk0, an SD card in sysfs, still ext4 labelled mu300sd. Android lets go of
# the card first (vold mounts it as /dev/block/vold/public:179,N, which no grep for the card's name finds), then
# anything mounted from the card's own nodes is unmounted; a card mount of either kind that is still there stops it.
# Prints ERASED, or REFUSED/BUSY and writes nothing.
# The first 64 MiB hold the superblock, the group descriptors and the first inode tables: mount and blkid see no
# filesystem afterwards, and the rest of the card is free space for whatever the user formats it with.
sd_erase_cmd() {  # sd_erase_cmd DEV  (/dev/block/mmcblk1p1, or /dev/block/mmcblk1 for a card without partitions)
    _d=${1#/dev/block/}; _d=${_d%p[0-9]*}
    _s=${MU300_SYSFS:-/sys}; _m=${MU300_MOUNTS:-/proc/mounts}
    printf '%s' "case $1 in */mmcblk0|*/mmcblk0p*) echo REFUSED $1 is the eMMC; exit 1 ;; esac; " \
        "[ x\$(cat $_s/block/$_d/device/type 2>/dev/null) = xSD ] || { echo REFUSED $_d is not an SD card; exit 1; }; " \
        "set -- \$(dd if=$1 bs=1 skip=1080 count=2 2>/dev/null | od -An -tx1); [ x\$1\$2 = x53ef ] || { echo REFUSED no ext4 on $1; exit 1; }; " \
        "[ x\$(dd if=$1 bs=1 skip=1144 count=16 2>/dev/null | tr -d \\\\000) = xmu300sd ] || { echo REFUSED no mu300sd on $1; exit 1; }; " \
        "for v in \$(sm list-volumes 2>/dev/null | grep -o ^public:179,[0-9]*); do sm unmount \$v >/dev/null 2>&1; done; " \
        "while read d m r; do case \$d in /dev/block/$_d|/dev/block/${_d}p*) umount \$m 2>/dev/null ;; esac; done < $_m; " \
        "grep -q -e ^/dev/block/$_d -e public:179, $_m && { echo BUSY; exit 1; }; " \
        "dd if=/dev/zero of=$1 bs=1048576 count=64 conv=notrunc 2>/dev/null; sync; echo ERASED"
}

# Only SD_DEV as sd_probe found it, and only while it holds mu300sd: any other ext4 on a card is someone's data.
# uninstall.sh asks no translated questions, so these messages stay English.
sd_erase() {
    [ -n "$SD_DEV" ] || die "no SD card to erase"
    case $SD_DEV in
        /dev/block/mmcblk0|/dev/block/mmcblk0p*) die "refusing $SD_DEV: that is the internal eMMC" ;;
        /dev/block/mmcblk[1-9]|/dev/block/mmcblk[1-9]p[0-9]|/dev/block/mmcblk[1-9]p[0-9][0-9]) ;;
        *) die "refusing $SD_DEV: not an SD card device" ;;
    esac
    [ "$(sd_existing)" = yes ] || die "the SD card ($SD_DEV) holds no mu300sd filesystem; nothing was erased"
    _o=$(su_do "$(sd_erase_cmd "$SD_DEV")")
    case $_o in *ERASED*) ;; *) die "the SD card was not erased: $_o" ;; esac
    [ "$(sd_existing)" = no ] || die "the SD card still shows a mu300sd filesystem"
}

# mu300-install.env, what android-install.sh is told. OFF/SIZE (and their sectors) are always the internal region:
# in SD mode SIZE is the card's by now and INT_SIZE keeps the region's, which the root-on-sd marker needs; the card's
# own size is read on the device.
write_install_env() {
    _rs=$SIZE; [ "$SD_MODE" = 1 ] && _rs=$INT_SIZE
    printf 'OFF=%s\nSIZE=%s\nOFF_S=%s\nSIZE_S=%s\nFORMAT=%s\nOSES="%s"\nWIPE_LEGACY=%s\nUPDATE=%s\nBOOT_OS=%s\nDEFAULT_LINUX=%s\nBOOT_ATTEMPTS=%s\nIMPORT_HOTSPOT=%s\nKERNEL=%s\nSD_MODE=%s\nSD_DEV=%s\nINTERNAL_EXISTS=%s\nPWHASH='"'"'%s'"'"'\n' \
      "$OFF" "$_rs" "$((OFF / 512))" "$((_rs / 512))" "$FORMAT" "$OSES" "$WIPE_LEGACY" "$UPDATE" "$BOOT_OS" "$DEFAULT_LINUX" "$BOOT_ATTEMPTS" "$IMPORT_HOTSPOT" "$KERNEL" "$SD_MODE" "$SD_DEV" "$INTERNAL_EXISTS" "$PWHASH"
}

# The free eMMC region: from the first 2 MiB boundary after the last partition to the last one before the backup
# GPT. Byte counts are computed here, never in the device's shell (Android's mksh has 32-bit arithmetic).
region_probe() {
    set -- $(su_do 'e=0; for p in /sys/block/mmcblk0/mmcblk0p*; do x=$(( $(cat $p/start) + $(cat $p/size) )); [ $x -gt $e ] && e=$x; done; echo $e $(cat /sys/block/mmcblk0/size)')
    [ $# -eq 2 ] || return 1
    last_end=$1; disk=$2
    start=$(( (last_end / 4096 + 1) * 4096 ))
    end=$(( ((disk - 34) / 4096 - 1) * 4096 ))
    # A partition table that ends at the end of the eMMC (one alignment block or less behind the last partition,
    # issue #65): the two boundaries cross, and a negative size is not a region. It is an empty one - the callers
    # then offer the card or make room - and its start is not read (region_find_existing).
    [ $end -gt $start ] || end=$start
    OFF=$((start * 512)); SIZE=$(( (end - start) * 512 ))
}

# region_on_disk BYTES: whether the ext4 superblock of a region at BYTES (its second KiB) lies on the eMMC. A read
# past the end of the disk never returns on this device: the dd spins on one core, survives kill -9 and heats the
# SoC until a reboot (issues #43, #52, #65 - a 32 GB eMMC whose table ends at its end puts the region's start at the
# disk's end, and the fixed offset of the first releases lies beyond a 32 GB eMMC altogether).
region_on_disk() { [ $(( ($1 + 2048) / 512 )) -le "${disk:?region_probe first}" ]; }

# an existing installation defines the region (it may have been created with a slightly different size, or at the
# fixed offset of the first releases)
region_find_existing() {
    existing=no
    for cand in $OFF 27762098176; do
        region_on_disk "$cand" || continue
        m=$(su_do "dd if=/dev/block/mmcblk0 bs=1 skip=$((cand + 1080)) count=2 2>/dev/null | od -An -tx1" | tr -d ' ')
        l=$(su_do "dd if=/dev/block/mmcblk0 bs=1 skip=$((cand + 1144)) count=16 2>/dev/null" | LC_ALL=C tr -d '\000')
        if [ "$m" = 53ef ] && [ "$l" = mu300root ]; then
            blocks=$(su_do "dd if=/dev/block/mmcblk0 bs=1 skip=$((cand + 1028)) count=4 2>/dev/null | od -An -tu4" | tr -d ' ')
            OFF=$cand; SIZE=$((blocks * 4096)); existing=yes; return 0
        fi
    done
}

# unpartitioned space should be unused: sample 16 x 1 MiB across the region and count those with data. Empty is
# 0x00 or 0xFF: an eMMC reads back what its erase leaves (EXT_CSD ERASED_MEM_CONT), and on some F50s that is 0xFF -
# counted as data, a region that was never written stopped the install with "not empty".
region_dirty() {
    step=$(( SIZE / 1048576 / 16 ))
    probe=""; i=0
    while [ $i -lt 16 ]; do probe="$probe $(( OFF / 1048576 + i * step ))"; i=$((i + 1)); done
    DIRTY=$(su_do "n=0; for s in $probe; do c=\$(dd if=/dev/block/mmcblk0 bs=1048576 skip=\$s count=1 2>/dev/null | tr -d \"\\000\\377\" | wc -c); [ \$c -gt 0 ] && n=\$((n + 1)); done; echo \$n")
}
