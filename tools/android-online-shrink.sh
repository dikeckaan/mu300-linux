#!/system/bin/sh
# Shrink Android's userdata while Android runs and keeps its data (EXPERIMENTAL): the device side of the installers'
# "keep Android's data" way of making room. Runs in Android as root (su), pushed by install.sh / install.ps1 next to
# mu300-f2fs-online. The method - shrink the mounted F2FS online with the kernel's F2FS_IOC_RESIZE_FS instead of
# having recovery reset Android - is dikeckaan's; kanoqwq implemented it (kanoqwq/mu300-linux fe52afe3, c69be3a3,
# dad8224b: installer/backend/online_shrink.py and installer/device/f2fs-online.c), and this is his eligibility
# checks and worker launch in this project's shell form. Android itself does the shrink, on its own decrypted
# mapping: nothing here decrypts, formats or mounts anything, and it never touches misc, the boot slots or NV.
#
#   android-online-shrink.sh inspect STAGE        is /data an F2FS this can shrink? (read only; STAGE holds the helper)
#   android-online-shrink.sh stage SRC TOKEN       copy SRC's files into /dev/mu300-online-TOKEN (tmpfs, root only:
#                                                  never the userdata being resized); their SHA-256s
#   android-online-shrink.sh start TOKEN OLD_BLOCKS TARGET_BLOCKS UUID DISK_SECTORS [TAIL_SECTORS]
#                                                  the kernel's no-op probe (when the F2FS is still at OLD_BLOCKS), then
#                                                  the detached worker: shrink, backup GPT, primary GPT, each read back
#                                                  (sectors of 512 bytes: the disk's, and the backup table's at its
#                                                  end - 33, or 40 on a disk of 4096-byte blocks, a UFS)
#   android-online-shrink.sh status TOKEN          PHASE= ERRNO= BUSY= of the worker
#   android-online-shrink.sh cleanup TOKEN         remove /dev/mu300-online-TOKEN (refused while the worker runs)
# Output: KEY=VALUE lines. inspect: ONLINE=yes|no, REASON= (when no), SOURCE= NODE= MAPPED= (sectors), and the
# helper's BLOCKS= SECTION_BLOCKS= USED_BYTES= UUID=. start: LAUNCH=ok, or PROBE=refused (the kernel said no, nothing
# was changed) or LAUNCH=failed with STAGE= ERRNO=.
set -u
PATH=/system/bin:/system/xbin:/vendor/bin:/sbin:/bin:$PATH
FILES="mu300-f2fs-online old-first old-last new-first new-last"

no() { echo ONLINE=no; echo "REASON=$1"; exit 0; }
tok_ok() { case $1 in ''|*[!0-9a-f]*) return 1 ;; esac; [ ${#1} = 32 ]; }
dir_of() { echo "/dev/mu300-online-$1"; }
# the helper's key=value lines, upper-cased keys
upper() { while IFS='=' read -r k v; do [ -n "$k" ] && [ -n "${v+x}" ] && echo "$(echo "$k" | tr a-z A-Z)=$v"; done; }

# kname DEV: the kernel's name of a block device node (mmcblk0p75, dm-39), from its numbers, whatever the node is
# called (/dev/block/dm-39, /dev/mapper/...)
kname() {
    set -- $(stat -L -c '%t %T' "$1" 2>/dev/null) || return 1
    [ $# = 2 ] || return 1
    k=$(readlink -f "/sys/dev/block/$((0x$1)):$((0x$2))") || return 1
    echo "${k##*/}"
}

data_source() {
    while read -r s m t r; do
        [ "$m" = /data ] && { echo "$s $t"; return 0; }
    done < /proc/mounts
    return 1
}

cmd_inspect() {
    stage=$1
    [ -x "$stage/mu300-f2fs-online" ] || no 'the helper is not on the device'
    [ "$(getprop ro.crypto.type)" != block ] || no 'full-disk (block) encryption: only file-based encryption is known to work'
    set -- $(data_source) || no '/data is not mounted'
    src=${1:-} fs=${2:-}
    [ "$fs" = f2fs ] || no "/data is ${fs:-unknown}, not F2FS"
    udn=$(kname /dev/block/by-name/userdata) || no 'no userdata partition'
    real=$(readlink -f "$src"); node=$(kname "$real") || no "cannot tell what $src is"
    udsize=$(cat "/sys/class/block/$udn/size" 2>/dev/null)
    case $node in
        "$udn") mapped=$udsize ;;
        dm-*)
            # one mapping, on userdata alone, over all of it (kano: no layered or offset mapping)
            slaves=$(ls "/sys/class/block/$node/slaves" 2>/dev/null | tr '\n' ' ')
            [ "$slaves" = "$udn " ] || no "/data's mapping $node is not on userdata alone ($slaves)"
            mapped=$(cat "/sys/class/block/$node/size" 2>/dev/null)
            [ -n "$mapped" ] && [ "$mapped" = "$udsize" ] || no "/data's mapping $node does not cover all of userdata ($mapped of $udsize sectors)"
            ;;
        *) no "/data is mounted from $node, not from userdata ($udn)" ;;
    esac
    out=$("$stage/mu300-f2fs-online" inspect /data "$real" 2>&1) || no "the helper cannot read the F2FS: $(echo "$out" | tail -n1)"
    echo ONLINE=yes
    echo "SOURCE=$real"; echo "NODE=$udn"; echo "MAPPED=$mapped"
    echo "$out" | upper
}

cmd_stage() {
    src=$1 tok=$2
    tok_ok "$tok" || { echo STAGE=bad-token; exit 1; }
    d=$(dir_of "$tok")
    # a worker that runs still reads its inputs: they are never replaced under it
    if [ -x "$d/mu300-f2fs-online" ] && [ "$("$d/mu300-f2fs-online" lock-status)" = busy=1 ]; then echo STAGE=busy; exit 1; fi
    umask 077
    mkdir -p "$d" && chmod 700 "$d" || { echo STAGE=mkdir; exit 1; }
    for f in $FILES; do
        [ -f "$src/$f" ] || { echo "STAGE=missing-$f"; exit 1; }
        cp "$src/$f" "$d/$f" && chmod 700 "$d/$f" || { echo "STAGE=copy-$f"; exit 1; }
    done
    sync
    for f in $FILES; do echo "SHA_$(echo "$f" | tr a-z- A-Z_)=$(sha256sum "$d/$f" | cut -d' ' -f1)"; done
    echo STAGE=ok
}

cmd_start() {
    tok=$1 old=$2 target=$3 uuid=$4 disk=$5 tail=${6:-33}
    case $tail in 33|40) ;; *) echo LAUNCH=failed; echo STAGE=bad-tail; exit 1 ;; esac
    tok_ok "$tok" || { echo LAUNCH=failed; echo STAGE=bad-token; exit 1; }
    d=$(dir_of "$tok") h=$(dir_of "$tok")/mu300-f2fs-online
    [ -x "$h" ] || { echo LAUNCH=failed; echo STAGE=not-staged; exit 1; }
    set -- $(data_source); real=$(readlink -f "$1")
    # the disk userdata is on, its parent in sysfs (mmcblk0 for mmcblk0p75, sda for sda34); MU300_ONLINE_DISK only
    # for tests/online-shrink-e2e.sh
    mmc=$(readlink -f "/sys/class/block/$(kname /dev/block/by-name/userdata)/..") && mmc=/dev/block/${mmc##*/}
    mmc=${MU300_ONLINE_DISK:-$mmc}
    blocks=$("$h" inspect /data "$real" 2>/dev/null | sed -n 's/^blocks=//p')
    if [ "$blocks" = "$old" ]; then
        # the kernel takes the ioctl at all: the same size is a no-op (kano: not a dry run of the shrink)
        if ! p=$("$h" probe /data "$real" 2>&1); then
            echo PROBE=refused; echo "ERRNO=$(echo "$p" | sed -n 's/.*errno=\([0-9]*\).*/\1/p' | tail -n1)"; exit 0
        fi
    fi
    rm -f "$d/status"
    out=$("$h" start /data "$real" "$old" "$target" "$mmc" $(( (disk - tail) * 512 )) $((disk * 512)) "$uuid" "$d" 2>&1)
    case $out in
        *worker_started=*) echo LAUNCH=ok ;;
        *) echo LAUNCH=failed; echo "STAGE=$(echo "$out" | sed -n 's/.*stage=\([^ ]*\).*/\1/p' | tail -n1)"
           echo "ERRNO=$(echo "$out" | sed -n 's/.*errno=\([0-9]*\).*/\1/p' | tail -n1)" ;;
    esac
}

cmd_status() {
    tok_ok "$1" || { echo PHASE=; exit 1; }
    d=$(dir_of "$1")
    [ -d "$d" ] || { echo PHASE=gone; echo BUSY=0; exit 0; }
    sed -n 's/^phase=/PHASE=/p; s/^errno=/ERRNO=/p' "$d/status" 2>/dev/null
    "$d/mu300-f2fs-online" lock-status 2>/dev/null | upper
}

cmd_cleanup() {
    tok_ok "$1" || exit 1
    d=$(dir_of "$1")
    if [ -x "$d/mu300-f2fs-online" ] && [ "$("$d/mu300-f2fs-online" lock-status)" = busy=1 ]; then echo CLEANUP=busy; exit 1; fi
    rm -rf "$d"; echo CLEANUP=ok
}

case ${1:-} in
    inspect) cmd_inspect "${2:?}" ;;
    stage) cmd_stage "${2:?}" "${3:?}" ;;
    start) cmd_start "${2:?}" "${3:?}" "${4:?}" "${5:?}" "${6:?}" "${7:-33}" ;;
    status) cmd_status "${2:?}" ;;
    cleanup) cmd_cleanup "${2:?}" ;;
    *) echo "usage: android-online-shrink.sh inspect|stage|start|status|cleanup ..." >&2; exit 2 ;;
esac
