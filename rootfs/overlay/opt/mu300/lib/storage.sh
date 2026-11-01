# The device's internal storage - an eMMC (mmcblkN) or a UFS (sdX) - and its GPT partitions, found by what they are,
# never by number or name alone: the one lookup that boot/init (as /etc/mu300-storage.sh in the ramdisk),
# early-recorder, android-vendor-start and mu300-cpu use (mu300-update carries a copy, tests/test_storage_lib.py
# keeps it the same). After kanoqwq's storage.sh (his fe52afe3, issue #396).
#
# The eMMC: the disk whose card is of type MMC, else the first mmcblk disk that is not a card - the host index
# follows probe order, and under mainline the card slot once took mmc0 and left mmcblk1 to the eMMC (FINDINGS 31l).
# The UFS: a SCSI disk below the UFS host (".../22000000.ufs/host0/..."), the logical unit that holds misc - its
# other units are 4 MiB boot areas. Never a card, a USB disk or anything else: they can carry the same GPT names (a
# raw clone of a device backup), and what is found here is written to (the BCB in misc, a kernel in boot_<slot>).
# sysfs counts start and size in 512-byte sectors on both; only a GPT is in logical blocks (4096 on a UFS).
# POSIX sh for dash, bash, busybox ash and Android's mksh; set -e safe; MU300_SYS is the sysfs root (/sys).
# --- storage begin
mu300_storage_mmc() {  # mu300_storage_mmc TYPE: the whole mmcblkN disks whose card is of TYPE (MMC, SD)
    for _mu300sb in "${MU300_SYS:-/sys}"/block/mmcblk*; do
        case ${_mu300sb##*/mmcblk} in ''|*[!0-9]*) continue ;; esac   # not mmcblk0boot0, mmcblk0rpmb, ...
        [ "$(cat "$_mu300sb/device/type" 2>/dev/null)" != "$1" ] || echo "${_mu300sb##*/}"
    done
    return 0
}
mu300_storage_ufs() {  # mu300_storage_ufs DISK: is DISK a disk of the UFS host?
    case ${1##*/} in sd[a-z]|sd[a-z][a-z]) ;; *) return 1 ;; esac
    _mu300sp=$(readlink -f "${MU300_SYS:-/sys}/block/${1##*/}" 2>/dev/null) || return 1
    case $_mu300sp in */*.ufs/host[0-9]*/*) return 0 ;; esac
    return 1
}
mu300_storage_prefix() {  # mu300_storage_prefix DISK: what its partitions' names are DISK plus a number after
    case ${1##*/} in *[0-9]) echo "${1##*/}p" ;; *) echo "${1##*/}" ;; esac
}
mu300_storage_parts() {  # mu300_storage_parts DISK: the names of its partitions (mmcblk0p1 ..., sda1 ...)
    _mu300sx=$(mu300_storage_prefix "$1")
    for _mu300sq in "${MU300_SYS:-/sys}/block/${1##*/}/$_mu300sx"[0-9]*; do
        [ -d "$_mu300sq" ] && echo "${_mu300sq##*/}"
    done
    return 0
}
mu300_storage_part() {  # mu300_storage_part NAME [DISK]: the partition named NAME in the GPT of DISK (internal)
    _mu300sd=${2:-}
    [ -n "$_mu300sd" ] || _mu300sd=$(mu300_storage_disk) || return 1
    for _mu300sq in $(mu300_storage_parts "$_mu300sd"); do
        grep -qx "PARTNAME=$1" "${MU300_SYS:-/sys}/block/${_mu300sd##*/}/$_mu300sq/uevent" 2>/dev/null || continue
        echo "$_mu300sq"
        return 0
    done
    return 1
}
mu300_storage_disk() {  # mu300_storage_disk: the internal disk's name; status 1 when it is not there (yet)
    for _mu300sd in $(mu300_storage_mmc MMC); do echo "$_mu300sd"; return 0; done
    for _mu300sb in "${MU300_SYS:-/sys}"/block/sd*; do
        mu300_storage_ufs "$_mu300sb" && mu300_storage_part misc "${_mu300sb##*/}" >/dev/null &&
            { echo "${_mu300sb##*/}"; return 0; }
    done
    for _mu300sb in "${MU300_SYS:-/sys}"/block/mmcblk*; do
        case ${_mu300sb##*/mmcblk} in ''|*[!0-9]*) continue ;; esac
        [ "$(cat "$_mu300sb/device/type" 2>/dev/null)" = SD ] || { echo "${_mu300sb##*/}"; return 0; }
    done
    return 1
}
mu300_storage_sector_size() {  # mu300_storage_sector_size DISK: its logical block size, 512 or 4096
    _mu300ss=$(cat "${MU300_SYS:-/sys}/block/${1##*/}/queue/logical_block_size" 2>/dev/null) || _mu300ss=
    case $_mu300ss in 4096) echo 4096 ;; *) echo 512 ;; esac
}
# --- storage end

# The device code: 16 lowercase hex digits that name this device and no other - the first 16 of
# sha256("mu300-audio-device-v1\n" + IDENTITY), IDENTITY being "emmc:" and the eMMC's CID, or "ufs:" and the UFS's
# manufacturer and serial number (its string descriptors, "ufs:MANUFACTURER:SERIAL"), as sysfs gives them (one line,
# the newline dropped). The installers read the same files on Android (tools/device-code.sh), so Linux and Android
# give the same code; tests/test_device_code.py holds the two to it. A licence of mu300-audio names this code. The raw
# identity is never printed: only its hash leaves here. Status 1 (nothing printed) when there is no identity to read.
mu300_device_sha256() {  # stdin's sha256, lowercase hex
    if command -v sha256sum >/dev/null 2>&1; then sha256sum | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then shasum -a 256 | cut -d' ' -f1
    else openssl dgst -sha256 -r | cut -d' ' -f1; fi
}
mu300_device_identity() {  # the identity the code is made from; for mu300_device_code only, never to be shown
    _mu300dd=$(mu300_storage_disk) || return 1
    _mu300db=${MU300_SYS:-/sys}/block/$_mu300dd/device
    if mu300_storage_ufs "$_mu300dd"; then
        _mu300du=$_mu300db/../../../string_descriptors
        _mu300dm=$(cat "$_mu300du/manufacturer_name" 2>/dev/null) || _mu300dm=
        _mu300ds=$(cat "$_mu300du/serial_number" 2>/dev/null) || _mu300ds=
        [ -n "$_mu300dm" ] && [ -n "$_mu300ds" ] || return 1
        printf 'ufs:%s:%s' "$_mu300dm" "$_mu300ds"
    else
        _mu300dc=$(cat "$_mu300db/cid" 2>/dev/null) || _mu300dc=
        [ -n "$_mu300dc" ] || return 1
        printf 'emmc:%s' "$_mu300dc"
    fi
}
mu300_device_code() {  # mu300_device_code: this device's code (one line, 16 hex digits); status 1 when none
    _mu300di=$(mu300_device_identity) || return 1
    _mu300dh=$(printf 'mu300-audio-device-v1\n%s' "$_mu300di" | mu300_device_sha256) || return 1
    _mu300di=
    case $_mu300dh in [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;; *) return 1 ;; esac
    printf '%s\n' "$_mu300dh" | cut -c1-16
}
