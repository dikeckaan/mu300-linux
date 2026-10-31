# Making room by a reset of Android, and the installation that resumes afterwards - EXPERIMENTAL (docs/FINDINGS.md
# 112). Ported from kano's desktop installer (kanoqwq/mu300-linux, branch clean-tf-7.2: desktop/installer.py and
# desktop/boot/part-prepare.sh, commits f6b0668d and 0e19fe32); the transaction itself is tools/resume.py's. Sourced by
# install.sh (su_do, dev_pull, adb_prop, sha256_of, ask, say, die, t, info, progress, gib are its own; needs $TOP,
# $WORK, $T).
#
# userdata is shrunk as before (only it: the last partition), but Android's data is not cleared by this installer:
# Android's own recovery is asked to format it (the bootloader message in misc, "--wipe_data"), which also starts
# its encryption anew - with file-based encryption a filesystem cleared from outside is one Android cannot mount, and
# recovery then waits for a person at a screen these devices do not have. Before anything is written, a transaction
# and a backup are saved on this computer; a token goes to the start of the region that is made, outside every
# partition, where the reset does not reach. After the reset - Android set up again, USB debugging on and root back -
# the installer finds the transaction and continues, when the device, its slot, its partition table (both copies,
# every CRC), the region, the token and this installer's tools are still the ones it was prepared with.
#
# The other way (EXPERIMENTAL, method=online in the transaction): Android keeps its data. Its F2FS is shrunk while it
# runs, by its own kernel (F2FS_IOC_RESIZE_FS, tools/f2fs-online and tools/android-online-shrink.sh), and only then is
# the smaller table written; Android restarts normally, and nothing is reset or set up again. The method is
# dikeckaan's; kanoqwq implemented it (kanoqwq/mu300-linux fe52afe3, c69be3a3, dad8224b). Offered when /data is an F2FS
# on all of userdata, directly or through one device-mapper mapping (file-based and metadata encryption), never with
# block encryption. A run that is interrupted continues from where the device is, and only from a known state.
#
#   MU300_BACKUP_DIR=DIR    where the transactions and backups are kept (default ~/mu300-backups)
#   MU300_RESUME=0|1        0 (--no-resume): never resume; 1 (--resume): resume, or stop when there is nothing to
#   MU300_TRANSACTION=FILE  (--transaction FILE) this transaction, not the newest one for the device
#   MU300_F2FS_ONLINE=FILE  the online way's helper (default tools/f2fs-online/mu300-f2fs-online)

RESUME=0; RESUME_FILE=
BACKUP_DIR=${MU300_BACKUP_DIR:-${HOME:-.}/mu300-backups}
resume_py() { python3 "$TOP/tools/resume.py" "$@"; }

# resume_pending: any transaction waiting in BACKUP_DIR (for any device). The installer does not update itself then:
# the transaction is bound to the tools that made it.
resume_pending() {
    [ "${MU300_RESUME:-}" != 0 ] || return 1
    [ -n "${MU300_TRANSACTION:-}" ] && return 0
    [ -d "$BACKUP_DIR" ] && command -v python3 >/dev/null 2>&1 && [ -n "$(resume_py find "$BACKUP_DIR" 2>/dev/null)" ]
}

# resume_facts: what identifies the device and its userdata, and how Android keeps its data (sysfs and properties,
# read only): SERIAL CID UD_NODE UD_START UD_SIZE CRYPTO (yes|no|unknown) CRYPTO_STATE CRYPTO_TYPE DATA_SOURCE
resume_facts() {
    # (no double quotes: install.ps1 sends the same text, and Windows PowerShell 5.1 drops them on the way to adb)
    _rf=$(su_do 'd=$(readlink -f /dev/block/by-name/userdata); n=${d##*/}; b=${n%p*}; case $n in sd*) b=${n%%[0-9]*} ;; esac; echo NODE=$n; echo CID=$(cat /sys/class/block/$b/device/cid 2>/dev/null); u=/sys/class/block/$b/device/../../../string_descriptors; echo UFS=$(cat $u/manufacturer_name 2>/dev/null):$(cat $u/serial_number 2>/dev/null); echo START=$(cat /sys/class/block/$n/start); echo SIZE=$(cat /sys/class/block/$n/size); echo STATE=$(getprop ro.crypto.state); echo TYPE=$(getprop ro.crypto.type); while read s m r; do case $m in /data) echo SOURCE=$s; break ;; esac; done < /proc/mounts; echo FSB=$(dd if=$s bs=4096 count=1 2>/dev/null | od -An -tu4 -j1060 -N8); echo FSU=$(dd if=$s bs=4096 count=1 2>/dev/null | od -An -tx1 -j1132 -N16 | tr -d \\040\\012); echo MAGIC=$(dd if=$d bs=1 skip=1024 count=4 2>/dev/null | od -An -tx1 | tr -d \\040\\012); echo EXT=$(dd if=$d bs=1 skip=1080 count=2 2>/dev/null | od -An -tx1 | tr -d \\040\\012)')
    _rv() { printf '%s\n' "$_rf" | sed -n "s/^$1=//p" | head -n1; }
    UD_NODE=$(_rv NODE); CID=$(_rv CID); UD_START=$(_rv START); UD_SIZE=$(_rv SIZE)
    # a UFS has no CID: its manufacturer and serial number (string descriptors), hashed to the same 32 hex digits
    # (issue #396; the GPT disk GUID of such a unit is a placeholder, 11111111-2222-..., shared by every one)
    case $UD_NODE:$(_rv UFS) in
        sd*:?*:?*) CID=$(python3 -c 'import hashlib, sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:32])' \
                         "ufs:$(_rv UFS)") || CID= ;;
    esac
    CRYPTO_STATE=$(_rv STATE); CRYPTO_TYPE=$(_rv TYPE); DATA_SOURCE=$(_rv SOURCE)
    # the F2FS on /data, as its superblock says now: blocks (two 32-bit halves) and UUID (the online way's checks)
    set -- $(_rv FSB); FS_BLOCKS=; [ $# != 2 ] || FS_BLOCKS=$(( $1 + ($2 << 32) )); FS_UUID=$(_rv FSU)
    _m=$(_rv EXT); [ "$_m" = 53ef ] || _m=$(_rv MAGIC)
    SERIAL=$(adb_prop ro.serialno)
    # (kano's checks of the identity: an eMMC partition node and the eMMC's 128-bit CID - or a UFS one's, and its hash)
    case $UD_NODE in mmcblk[0-9]p[0-9]*|sd[a-z][0-9]*) ;; *) return 1 ;; esac
    case $UD_NODE in *[!a-z0-9]*) return 1 ;; esac
    [ ${#CID} = 32 ] || return 1
    case $CID in *[!0-9a-f]*) return 1 ;; esac
    case $UD_START$UD_SIZE in ''|*[!0-9]*) return 1 ;; esac
    [ -n "$SERIAL" ] || return 1
    CRYPTO=$(resume_py encrypted state="$CRYPTO_STATE" type="$CRYPTO_TYPE" source="$DATA_SOURCE" magic="$_m")
}

# resume_region NEW_LAST_END: RG_START and RG_END (sectors) of the free region behind a userdata that ends before
# sector NEW_LAST_END - tools/storage.sh's region_probe arithmetic
resume_region() {
    RG_START=$(( ($1 / 4096 + 1) * 4096 ))
    RG_END=$(( ((disk - ${GPT_TAIL:-33} - 1) / 4096 - 1) * 4096 ))
    [ $RG_END -gt $RG_START ] || RG_END=$RG_START
}

# resume_backup DIR: what an installation reads first and what the prepare writes over, copied to DIR on this
# computer and checked against the device: the partition table (as read for the plan), the first block of misc, both
# slots' boot and boot chain partitions. Never the NV or calibration partitions. A SHA256SUMS lists them.
resume_backup() {
    _bd=$1
    mkdir -p "$_bd" || die "$(t 'could not create {1}' "$_bd")"
    cp "$WORK/gpt/gpt.head" "$_bd/gpt.head" && cp "$WORK/gpt/gpt.tail" "$_bd/gpt.tail" ||
        die "$(t 'could not copy the partition table into the backup')"
    su_do 'dd if=/dev/block/by-name/misc bs=4096 count=1 2>/dev/null > /data/local/tmp/mu300-pull.bin' >/dev/null
    adb pull /data/local/tmp/mu300-pull.bin "$_bd/misc-head.bin" >/dev/null 2>&1 || true
    su_do 'rm -f /data/local/tmp/mu300-pull.bin' >/dev/null
    [ -s "$_bd/misc-head.bin" ] || die "$(t 'could not read the misc header from the device')"
    for _bp in boot uboot sml teecfg trustos vbmeta; do
        for _bs in a b; do
            say "$(t 'Backing up {1}' "${_bp}_$_bs")"
            dev_pull "/dev/block/by-name/${_bp}_$_bs" "$_bd/${_bp}_$_bs.img"
            _bw=$(su_do "sha256sum /dev/block/by-name/${_bp}_$_bs" | cut -d' ' -f1)
            [ -n "$_bw" ] && [ "$_bw" = "$(sha256_of "$_bd/${_bp}_$_bs.img")" ] ||
                die "$(t 'the copy of {1} is not what the device holds; nothing was changed' "${_bp}_$_bs")"
        done
    done
    (cd "$_bd" && for _f in gpt.head gpt.tail misc-head.bin *.img; do printf '%s  %s\n' "$(sha256_of "$_f")" "$_f"; done) > "$_bd/SHA256SUMS"
}

# resume_push LOCAL REMOTE: LOCAL to the device, and there with the checksum it has here (a push that stopped
# halfway leaves a short file, which dd would write)
resume_push() {
    adb push "$1" "$2" >/dev/null 2>&1 || true
    [ "$(su_do "sha256sum $2" | cut -d' ' -f1)" = "$(sha256_of "$1")" ]
}

# resume_prepare NEW_END: the destructive stage. Everything has been asked and the backup made; the transaction is
# saved before the first write. Then: the partition table (the backup copy first), read back and checked; the token
# at the start of the region, read back; the bootloader message that has recovery format userdata, read back, with
# the A/B boot control block behind it as it was. The transaction then says "prepared". Android keeps running from
# its slot; nothing of boot_a, boot_b or the boot chain is written.
resume_prepare() {
    _ne=$1
    resume_region $((_ne + 1))
    _tok=$(resume_py token) || die "$(t 'could not make a token')"
    RESUME_FILE=$RESUME_BD/transaction.json
    _id=$(resume_py identity "$TOP" "${PKG:+$PKG/mu300/manifest}") || die "$(t 'could not compute the installer identity')"
    resume_py new "$RESUME_FILE" serial="$SERIAL" slot="$ANDROID_SLOT" cid="$CID" node="$UD_NODE" start="$UD_START" \
        size="$UD_SIZE" disk="$disk" target=$((_ne - UD_START + 1)) need=$((RG_END - RG_START)) usable_end="$USABLE_END" \
        region_start="$RG_START" region_end="$RG_END" token="$_tok" identity="$_id" crypto="$CRYPTO" \
        crypto_state="$CRYPTO_STATE" crypto_type="$CRYPTO_TYPE" backup="$RESUME_BD" ||
        die "$(t 'could not save the transaction; nothing was changed')"
    info resume.transaction "$RESUME_FILE"
    echo "  $(t 'transaction saved: {1}' "$RESUME_FILE")"
    resume_py marker "$_tok" "$WORK/gpt/marker.bin" && resume_py bcb "$WORK/gpt/bcb.bin" ||
        die "$(t 'could not prepare the files to write; nothing was changed')"

    step repartition 50
    say "$(t 'Rewriting the partition table')"
    python3 "$TOP/tools/resize-last-partition.py" "$WORK/gpt/gpt.head,$WORK/gpt/gpt.tail" \
        --disk-sectors "$disk" --sector-size "$ILBS" --name userdata --end-sector "$_ne" --out "$WORK/gpt/new" || die "$(t 'the resize was refused; nothing is changed')"
    for _f in new.head new.tail marker.bin bcb.bin; do
        resume_push "$WORK/gpt/$_f" "$T/mu300-$_f" ||
            { su_do "rm -f $T/mu300-new.head $T/mu300-new.tail $T/mu300-marker.bin $T/mu300-bcb.bin" >/dev/null
              die "$(t 'the new partition table did not arrive on the device as it was made; nothing is changed')"; }
    done
    _bc=$(su_do 'dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null | od -An -tx1 -v' | tr -d ' \n')
    # the backup copy first: if power is lost between the two, the primary is still the old table and the device
    # boots, which is the recoverable order
    su_do "dd if=$T/mu300-new.tail of=/dev/block/$IDISK bs=512 seek=$((disk - GPT_TAIL)) conv=fsync 2>/dev/null" >/dev/null
    su_do "dd if=$T/mu300-new.head of=/dev/block/$IDISK bs=512 conv=fsync 2>/dev/null" >/dev/null

    say "$(t 'Verifying')"
    su_do "dd if=/dev/block/$IDISK bs=512 count=$GPT_HEAD 2>/dev/null > /data/local/tmp/gpt.head" >/dev/null
    su_do "dd if=/dev/block/$IDISK bs=512 skip=$((disk - GPT_TAIL)) count=$GPT_TAIL 2>/dev/null > /data/local/tmp/gpt.tail" >/dev/null
    adb pull /data/local/tmp/gpt.head "$WORK/gpt/after.head" >/dev/null 2>&1 || true
    adb pull /data/local/tmp/gpt.tail "$WORK/gpt/after.tail" >/dev/null 2>&1 || true
    su_do 'rm -f /data/local/tmp/gpt.head /data/local/tmp/gpt.tail' >/dev/null
    check=$(python3 "$TOP/tools/resize-last-partition.py" "$WORK/gpt/after.head,$WORK/gpt/after.tail" \
              --disk-sectors "$disk" --sector-size "$ILBS" --name userdata --show) || die "$(t 'the table on the device does not read back as valid GPT.')
$(t "The backup copy at the end of the disk was written first, so Android's own repair may still fix this. Do not power off.")"
    got=$(echo "$check" | sed -n 's/^LAST_END=//p')
    [ "$got" = "$_ne" ] || die "$(t 'the table did not take (userdata still ends at {1}). Nothing else was changed.' "$got")"
    echo "  $(t 'userdata now ends at sector {1}' "$got")"

    # the token: the first 4 KiB of the region, outside every partition from now on
    su_do "dd if=$T/mu300-marker.bin of=/dev/block/$IDISK bs=512 seek=$RG_START count=8 conv=notrunc,fsync 2>/dev/null" >/dev/null
    [ "$(su_do "dd if=/dev/block/$IDISK bs=512 skip=$RG_START count=8 2>/dev/null | sha256sum" | cut -d' ' -f1)" = "$(sha256_of "$WORK/gpt/marker.bin")" ] ||
        die "$(t 'the token did not read back from the device; misc was not changed, Android keeps its data. Run the installer again.')"

    # the reset, by Android's own recovery: the bootloader message in the first 2 KiB of misc
    say "$(t "Asking Android's recovery to reset Android's data on the next boot")"
    su_do "dd if=$T/mu300-bcb.bin of=/dev/block/by-name/misc bs=2048 count=1 conv=notrunc,fsync 2>/dev/null" >/dev/null
    [ "$(su_do 'dd if=/dev/block/by-name/misc bs=2048 count=1 2>/dev/null | sha256sum' | cut -d' ' -f1)" = "$(sha256_of "$WORK/gpt/bcb.bin")" ] &&
        [ "$(su_do 'dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null | od -An -tx1 -v' | tr -d ' \n')" = "$_bc" ] ||
        die "$(t 'the request for the reset did not read back from misc. The partition table is changed already: run the installer again, it continues from here.')"
    su_do "sync; rm -f $T/mu300-new.head $T/mu300-new.tail $T/mu300-marker.bin $T/mu300-bcb.bin" >/dev/null
    resume_py set "$RESUME_FILE" state=prepared || die "$(t 'could not save the transaction')"
}

# resume_lookup: RESUME=1 and RESUME_FILE when a transaction waits for this device (or MU300_TRANSACTION names one);
# dies when --resume was asked for and there is none. Needs region_probe (disk) and slot_setup.
resume_lookup() {
    [ "${MU300_RESUME:-}" != 0 ] || return 0
    # nothing saved on this computer, and not asked for: nothing more is read from the device
    [ "${MU300_RESUME:-}" = 1 ] || resume_pending || return 0
    command -v python3 >/dev/null 2>&1 || die "$(t '{1} not found' python3)"
    if ! resume_facts; then
        [ "${MU300_RESUME:-}" != 1 ] || die "$(t 'could not read what identifies this device (serial, eMMC CID, userdata)')"
        return 0
    fi
    RESUME_FILE=${MU300_TRANSACTION:-}
    [ -n "$RESUME_FILE" ] || RESUME_FILE=$(resume_py find "$BACKUP_DIR" "$SERIAL" "$CID" 2>/dev/null)
    if [ -z "$RESUME_FILE" ]; then
        [ "${MU300_RESUME:-}" != 1 ] || die "$(t 'no saved transaction for this device in {1} (--transaction FILE names one)' "$BACKUP_DIR")"
        return 0
    fi
    [ -f "$RESUME_FILE" ] || die "$(t '{1} not found' "$RESUME_FILE")"
    RESUME=1
    info resume.transaction "$RESUME_FILE"
    say "$(t 'A prepared installation is waiting: {1}' "$RESUME_FILE")"
    if [ "$(resume_py get "$RESUME_FILE" method 2>/dev/null)" = method=online ]; then
        echo "  $(t "EXPERIMENTAL: it continues the installation that made room by shrinking Android's data in place. --no-resume ignores it.")"
    else
        echo "  $(t 'EXPERIMENTAL: it continues the installation that made room by resetting Android. --no-resume ignores it.')"
    fi
}

# resume_validate [soft]: every check of the transaction against the device, before anything is written
# (resume.py check, read only); dies with the reason - with soft (--check) says it and returns 1.
resume_validate() {
    mkdir -p "$WORK/gpt"
    rm -f "$WORK/gpt/resume.head" "$WORK/gpt/resume.tail" "$WORK/gpt/resume-marker.bin" "$WORK/gpt/resume-bcb.bin"
    su_do "dd if=/dev/block/$IDISK bs=512 count=$GPT_HEAD 2>/dev/null > /data/local/tmp/gpt.head" >/dev/null
    su_do "dd if=/dev/block/$IDISK bs=512 skip=$((disk - GPT_TAIL)) count=$GPT_TAIL 2>/dev/null > /data/local/tmp/gpt.tail" >/dev/null
    adb pull /data/local/tmp/gpt.head "$WORK/gpt/resume.head" >/dev/null 2>&1 || true
    adb pull /data/local/tmp/gpt.tail "$WORK/gpt/resume.tail" >/dev/null 2>&1 || true
    su_do 'rm -f /data/local/tmp/gpt.head /data/local/tmp/gpt.tail' >/dev/null
    _rs=$(python3 "$TOP/tools/resize-last-partition.py" "$WORK/gpt/resume.head,$WORK/gpt/resume.tail" \
            --disk-sectors "$disk" --sector-size "$ILBS" --name userdata --show 2>&1) || _rs=
    [ -n "$_rs" ] || die "$(t 'could not read the partition table')"
    _rg() { printf '%s\n' "$_rs" | sed -n "s/^$1=//p"; }
    _rr=$(resume_py get "$RESUME_FILE" region_start) || die "$(t 'could not read the transaction {1}' "$RESUME_FILE")"
    _rr=${_rr#region_start=}
    case $_rr in ''|*[!0-9]*) die "$(t 'could not read the transaction {1}' "$RESUME_FILE")" ;; esac
    su_do "dd if=/dev/block/$IDISK bs=512 skip=$_rr count=8 2>/dev/null > /data/local/tmp/mu300-pull.bin" >/dev/null
    adb pull /data/local/tmp/mu300-pull.bin "$WORK/gpt/resume-marker.bin" >/dev/null 2>&1 || true
    su_do 'dd if=/dev/block/by-name/misc bs=2048 count=1 2>/dev/null > /data/local/tmp/mu300-pull.bin' >/dev/null
    adb pull /data/local/tmp/mu300-pull.bin "$WORK/gpt/resume-bcb.bin" >/dev/null 2>&1 || true
    su_do 'rm -f /data/local/tmp/mu300-pull.bin' >/dev/null
    # the online way, interrupted before "prepared": where the device is decides (online_recover; never with --check,
    # which writes nothing)
    _rm=$(resume_py get "$RESUME_FILE" method state | tr '\n' ' ')
    _fsf=
    case $_rm in
        *method=online*)
            _fsf="fs_blocks=${FS_BLOCKS:-} fs_uuid=${FS_UUID:-}"
            case $_rm in *state=prepared-request*)
                if [ "${1:-}" = soft ]; then
                    echo "  $(t "The prepared installation cannot be continued: {1}" "$(t "the shrink of Android's data did not finish; run the installer without --check, it checks where it got to")")"
                    return 1
                fi
                if ! online_recover; then RESUME=0; RESUME_FILE=; return 0; fi
                region_probe || die "$(t 'could not read the partition table from the device (is su granted? try again)')"
                resume_validate
                return ;;
            esac ;;
    esac
    _id=$(resume_py identity "$TOP" "${PKG:+$PKG/mu300/manifest}")
    _ok=0
    _out=$(resume_py check "$RESUME_FILE" serial="$SERIAL" slot="$ANDROID_SLOT" cid="$CID" node="$UD_NODE" \
        start="$UD_START" size="$UD_SIZE" disk="$disk" gpt_first="$(_rg LAST_FIRST)" gpt_end="$(_rg LAST_END)" \
        usable_end="$(_rg USABLE_END)" region_start=$((OFF / 512)) region_end=$(( (OFF + SIZE) / 512 )) \
        marker="$WORK/gpt/resume-marker.bin" bcb="$WORK/gpt/resume-bcb.bin" identity="$_id" $_fsf) || _ok=$?
    info resume.check "$_out"
    if [ $_ok != 0 ]; then
        if [ "${1:-}" = soft ]; then
            echo "  $(t 'The prepared installation cannot be continued: {1}' "${_out#RESUME-REFUSED: }")"
            return 1
        fi
        die "$(t 'The prepared installation cannot be continued: {1}' "${_out#RESUME-REFUSED: }")
$(t 'Nothing was written. Keep the device as it is and keep {1}.' "$RESUME_FILE")
$(t 'Another transaction: --transaction FILE. To install as if nothing had been prepared: --no-resume (the region is then treated as space that holds data).')"
    fi
    echo "  $(t 'the device, its slot, its partition table, the region, the token and this installer are the ones the transaction was made with')"
}

# ---------------------------------------------------------------- the online way: Android keeps its data
ONLINE_BIN=${MU300_F2FS_ONLINE:-$TOP/tools/f2fs-online/mu300-f2fs-online}
ONLINE_SH=${MU300_ONLINE_SH:-$TOP/tools/android-online-shrink.sh}     # (MU300_ONLINE_SH: tests/fakeonline.py)
ONLINE_T=$T/mu300-online
online_sh() { su_do "sh $ONLINE_T/android-online-shrink.sh $1"; }
_ov() { printf '%s\n' "$1" | sed -n "s/^$2=//p" | head -n1; }

# online_inspect: can userdata shrink while Android keeps its data? ONLINE=yes|no and ONLINE_REASON; with yes, what
# the F2FS is: ON_BLOCKS, ON_SECTION (blocks of a section), ON_USED (bytes), ON_UUID. Reads only (the helper and the
# script go to /data/local/tmp/mu300-online).
online_inspect() {
    ONLINE=no; ONLINE_REASON=; ON_BLOCKS=; ON_SECTION=; ON_USED=; ON_UUID=
    if [ ! -s "$ONLINE_BIN" ] || [ ! -s "$ONLINE_SH" ]; then
        ONLINE_REASON=$(t 'this installer has no mu300-f2fs-online (tools/f2fs-online)'); return 0
    fi
    su_do "rm -rf $ONLINE_T; mkdir -p $ONLINE_T; chmod 777 $ONLINE_T" >/dev/null
    resume_push "$ONLINE_BIN" "$ONLINE_T/mu300-f2fs-online" && resume_push "$ONLINE_SH" "$ONLINE_T/android-online-shrink.sh" ||
        { ONLINE_REASON=$(t 'the helper did not arrive on the device as it is here'); return 0; }
    su_do "chmod 700 $ONLINE_T/mu300-f2fs-online" >/dev/null
    _oi=$(online_sh "inspect $ONLINE_T")
    if [ "$(_ov "$_oi" ONLINE)" != yes ]; then
        ONLINE_REASON=$(_ov "$_oi" REASON); [ -n "$ONLINE_REASON" ] || ONLINE_REASON=$(t 'no answer from the device')
        return 0
    fi
    ON_BLOCKS=$(_ov "$_oi" BLOCKS); ON_SECTION=$(_ov "$_oi" SECTION_BLOCKS); ON_USED=$(_ov "$_oi" USED_BYTES); ON_UUID=$(_ov "$_oi" UUID)
    case "$ON_BLOCKS$ON_SECTION$ON_USED" in ''|*[!0-9]*) ONLINE_REASON=$(t 'the helper gave no geometry'); return 0 ;; esac
    [ ${#ON_UUID} = 32 ] || { ONLINE_REASON=$(t 'the helper gave no geometry'); return 0; }
    ONLINE=yes
}

# online_target NEW_SIZE: ON_TARGET, the F2FS blocks for a userdata of NEW_SIZE sectors; 1 and ON_WHY when Android's
# data does not fit (resume.py online-target: whole sections, 2 GiB to spare, kano's margin)
online_target() {
    ON_WHY=; _ot=$(resume_py online-target new_size="$1" section_blocks="$ON_SECTION" used_bytes="$ON_USED" blocks="$ON_BLOCKS" 2>&1)
    ON_TARGET=${_ot#TARGET=}
    case $ON_TARGET in ''|*[!0-9]*) ON_WHY=${_ot#REFUSED: }; ON_WHY=${ON_WHY#resume.py: }; ON_TARGET=; return 1 ;; esac
}

# online_prepare NEW_END: the online way's destructive stage, everything asked and the backup made. The transaction
# first (state prepared-request, the old and the new table in its backup), then online_commit.
online_prepare() {
    _ne=$1
    resume_region $((_ne + 1))
    _tok=$(resume_py token) || die "$(t 'could not make a token')"
    RESUME_FILE=$RESUME_BD/transaction.json
    python3 "$TOP/tools/resize-last-partition.py" "$WORK/gpt/gpt.head,$WORK/gpt/gpt.tail" \
        --disk-sectors "$disk" --sector-size "$ILBS" --name userdata --end-sector "$_ne" --out "$RESUME_BD/gpt-new" || die "$(t 'the resize was refused; nothing is changed')"
    (cd "$RESUME_BD" && for _f in gpt-new.head gpt-new.tail; do printf '%s  %s\n' "$(sha256_of "$_f")" "$_f"; done) >> "$RESUME_BD/SHA256SUMS"
    _id=$(resume_py identity "$TOP" "${PKG:+$PKG/mu300/manifest}") || die "$(t 'could not compute the installer identity')"
    resume_py new "$RESUME_FILE" serial="$SERIAL" slot="$ANDROID_SLOT" cid="$CID" node="$UD_NODE" start="$UD_START" \
        size="$UD_SIZE" disk="$disk" target=$((_ne - UD_START + 1)) need=$((RG_END - RG_START)) usable_end="$USABLE_END" \
        region_start="$RG_START" region_end="$RG_END" token="$_tok" identity="$_id" crypto="$CRYPTO" \
        crypto_state="$CRYPTO_STATE" crypto_type="$CRYPTO_TYPE" backup="$RESUME_BD" method=online \
        fs_uuid="$ON_UUID" fs_blocks="$ON_BLOCKS" fs_target="$ON_TARGET" ||
        die "$(t 'could not save the transaction; nothing was changed')"
    info resume.transaction "$RESUME_FILE"
    echo "  $(t 'transaction saved: {1}' "$RESUME_FILE")"
    online_commit
}

# online_declined WHY: the kernel or the helper said no before anything changed: the transaction is put aside
online_declined() {
    resume_py set "$RESUME_FILE" state=declined >/dev/null 2>&1 || true
    online_sh "cleanup $(resume_py get "$RESUME_FILE" token | sed 's/^token=//')" >/dev/null 2>&1 || true
    die "$1
$(t "Nothing was changed: Android keeps its data and its partition table. To make room by resetting Android instead, run the installer again and answer reset.")"
}

# online_commit: stage the helper and both tables in /dev/mu300-online-TOKEN, run the worker (the shrink, then the
# backup table, then the primary, each read back), wait for it, check the table and the F2FS, write the token. For a
# new transaction and for one whose worker stopped after the shrink (online_recover). The transaction then says
# "prepared".
online_commit() {
    _tok=$(resume_py get "$RESUME_FILE" token | sed 's/^token=//')
    _bd=$(resume_py get "$RESUME_FILE" backup | sed 's/^backup=//')
    _fb=$(resume_py get "$RESUME_FILE" fs_blocks | sed 's/^fs_blocks=//'); _ft=$(resume_py get "$RESUME_FILE" fs_target | sed 's/^fs_target=//')
    _fu=$(resume_py get "$RESUME_FILE" fs_uuid | sed 's/^fs_uuid=//'); _rs=$(resume_py get "$RESUME_FILE" region_start | sed 's/^region_start=//')
    _ne=$(( $(resume_py get "$RESUME_FILE" start | sed 's/^start=//') + $(resume_py get "$RESUME_FILE" target | sed 's/^target=//') - 1 ))
    resume_py marker "$_tok" "$WORK/gpt/marker.bin" || die "$(t 'could not prepare the files to write; nothing was changed')"
    step repartition 50
    say "$(t "Shrinking Android's data in place (Android keeps running; this can take a few minutes)")"
    su_do "rm -rf $ONLINE_T; mkdir -p $ONLINE_T; chmod 777 $ONLINE_T" >/dev/null
    for _p in "$ONLINE_BIN:mu300-f2fs-online" "$ONLINE_SH:android-online-shrink.sh" "$_bd/gpt.head:old-first" "$_bd/gpt.tail:old-last" \
              "$_bd/gpt-new.head:new-first" "$_bd/gpt-new.tail:new-last"; do
        resume_push "${_p%:*}" "$ONLINE_T/${_p##*:}" ||
            die "$(t 'the new partition table did not arrive on the device as it was made; nothing is changed')"
    done
    _st=$(online_sh "stage $ONLINE_T $_tok")
    [ "$(_ov "$_st" STAGE)" = ok ] && [ "$(_ov "$_st" SHA_NEW_FIRST)" = "$(sha256_of "$_bd/gpt-new.head")" ] &&
        [ "$(_ov "$_st" SHA_NEW_LAST)" = "$(sha256_of "$_bd/gpt-new.tail")" ] &&
        [ "$(_ov "$_st" SHA_MU300_F2FS_ONLINE)" = "$(sha256_of "$ONLINE_BIN")" ] ||
        die "$(t 'the new partition table did not arrive on the device as it was made; nothing is changed')"
    _go=$(online_sh "start $_tok $_fb $_ft $_fu $disk $GPT_TAIL")
    info online.start "$(printf '%s' "$_go" | tr '\n' ' ')"
    if [ "$(_ov "$_go" PROBE)" = refused ]; then
        online_declined "$(t "Android's kernel does not shrink this F2FS while it is mounted (errno {1})." "$(_ov "$_go" ERRNO)")"
    fi
    [ "$(_ov "$_go" LAUNCH)" = ok ] ||
        online_declined "$(t 'the helper refused to start ({1}, errno {2}).' "$(_ov "$_go" STAGE)" "$(_ov "$_go" ERRNO)")"
    online_wait "$_tok"
    # what the worker reports is checked here once more: both copies of the table, and the F2FS
    say "$(t 'Verifying')"
    su_do "dd if=/dev/block/$IDISK bs=512 count=$GPT_HEAD 2>/dev/null > /data/local/tmp/gpt.head" >/dev/null
    su_do "dd if=/dev/block/$IDISK bs=512 skip=$((disk - GPT_TAIL)) count=$GPT_TAIL 2>/dev/null > /data/local/tmp/gpt.tail" >/dev/null
    rm -f "$WORK/gpt/after.head" "$WORK/gpt/after.tail"
    adb pull /data/local/tmp/gpt.head "$WORK/gpt/after.head" >/dev/null 2>&1 || true
    adb pull /data/local/tmp/gpt.tail "$WORK/gpt/after.tail" >/dev/null 2>&1 || true
    su_do 'rm -f /data/local/tmp/gpt.head /data/local/tmp/gpt.tail' >/dev/null
    [ "$(sha256_of "$WORK/gpt/after.head")" = "$(sha256_of "$_bd/gpt-new.head")" ] &&
        [ "$(sha256_of "$WORK/gpt/after.tail")" = "$(sha256_of "$_bd/gpt-new.tail")" ] ||
        die "$(t 'the table on the device is not the one that was made. Do not restart or power off the device; run the installer again, it checks where the shrink got to.')"
    resume_facts || die "$(t 'could not read what identifies this device (serial, eMMC CID, userdata)')"
    [ "$FS_BLOCKS" = "$_ft" ] && [ "$FS_UUID" = "$_fu" ] ||
        die "$(t "Android's data is not at the size it was shrunk to ({1} blocks). Do not restart the device; run the installer again." "$FS_BLOCKS")"
    echo "  $(t "Android's data: {1}, the same filesystem as before" "$(gib $((FS_BLOCKS * 4096)))")"
    echo "  $(t 'userdata now ends at sector {1}' "$_ne")"
    # the token: the first 4 KiB of the region, outside the shrunk filesystem and, from Android's next start, outside
    # every partition
    resume_push "$WORK/gpt/marker.bin" "$T/mu300-marker.bin" || die "$(t 'the token did not read back from the device; run the installer again, it continues from here.')"
    su_do "dd if=$T/mu300-marker.bin of=/dev/block/$IDISK bs=512 seek=$_rs count=8 conv=notrunc,fsync 2>/dev/null; rm -f $T/mu300-marker.bin" >/dev/null
    [ "$(su_do "dd if=/dev/block/$IDISK bs=512 skip=$_rs count=8 2>/dev/null | sha256sum" | cut -d' ' -f1)" = "$(sha256_of "$WORK/gpt/marker.bin")" ] ||
        die "$(t 'the token did not read back from the device; run the installer again, it continues from here.')"
    online_sh "cleanup $_tok" >/dev/null 2>&1 || true
    su_do "rm -rf $ONLINE_T" >/dev/null
    resume_py set "$RESUME_FILE" state=prepared || die "$(t 'could not save the transaction')"
}

# online_wait TOKEN: until the worker is done. It runs on without adb: a computer that loses the device says so and
# stops, and the next run of the installer finds where it got to.
online_wait() {
    _lost=0; _last=
    while :; do
        _s=$(online_sh "status $1" 2>/dev/null)
        _ph=$(_ov "$_s" PHASE); _busy=$(_ov "$_s" BUSY)
        if [ -z "$_ph$_busy" ]; then
            _lost=$((_lost + 1))
            [ $_lost -lt "${MU300_ONLINE_LOST_TRIES:-30}" ] || die "$(t "The device does not answer while Android's data is being shrunk; the shrink goes on there. Do not restart or power off the device: connect it again and run the installer again, it checks where the shrink got to.")"
        else
            _lost=0
        fi
        if [ -n "$_ph" ] && [ "$_ph" != "$_last" ]; then echo "  $(t 'shrink: {1}' "$_ph")"; info online.phase "$_ph"; _last=$_ph; fi
        case $_ph:$_busy in
            complete:0) return 0 ;;
            unchanged:0|failed:0)
                online_declined "$(t "Android's kernel refused the shrink (errno {1}); the filesystem was read back at its old size." "$(_ov "$_s" ERRNO)")" ;;
            recovery:0|gone:0)
                die "$(t "The shrink stopped where it cannot tell by itself what happened (errno {1}). Do not restart or power off the device. Keep {2}; run the installer again, it checks where the shrink got to." "$(_ov "$_s" ERRNO)" "$RESUME_FILE")" ;;
            *:0) [ -n "$_ph" ] || die "$(t 'The shrink did not start. Run the installer again, it checks where the shrink got to.')" ;;
        esac
        sleep "${MU300_ONLINE_POLL:-2}"
    done
}

# online_recover: a transaction of the online way that did not get to "prepared" (the computer lost the device,
# or the installer stopped): where the device is now decides, never a guess. A worker that still runs is waited for;
# the old table and the old size: nothing happened, the transaction is put aside (returns 1, a new plan follows); the
# old table and the target size: the worker stopped between the two, and it runs again to commit the table; the new
# table and the target size: committed, only the token is left. Anything else stops, with the backups kept.
online_recover() {
    _tok=$(resume_py get "$RESUME_FILE" token | sed 's/^token=//')
    _bd=$(resume_py get "$RESUME_FILE" backup | sed 's/^backup=//')
    say "$(t 'The shrink of {1} did not finish: checking where it got to' "$RESUME_FILE")"
    su_do "mkdir -p $ONLINE_T; chmod 777 $ONLINE_T" >/dev/null
    resume_push "$ONLINE_SH" "$ONLINE_T/android-online-shrink.sh" || die "$(t 'no answer from the device')"
    [ "$(_ov "$(online_sh "status $_tok")" BUSY)" != 1 ] || online_wait "$_tok"
    resume_facts || die "$(t 'could not read what identifies this device (serial, eMMC CID, userdata)')"
    _os=$(resume_py online-state "$RESUME_FILE" head="$WORK/gpt/resume.head" tail="$WORK/gpt/resume.tail" fs_blocks="$FS_BLOCKS" fs_uuid="$FS_UUID")
    info online.state "$_os"
    case ${_os#STATE=} in
        unchanged)
            resume_py set "$RESUME_FILE" state=declined >/dev/null
            echo "  $(t 'Nothing had changed yet: the device has its old partition table and Android its data. That transaction is put aside.')"
            return 1 ;;
        shrunk|committed)
            echo "  $(t "Android's data is at its new size; the partition table is finished now")"
            online_commit
            [ "$UD_SIZE" != "$(resume_py get "$RESUME_FILE" size | sed 's/^size=//')" ] ||
                { say "$(t 'Done - Android restarts once now, with the smaller userdata, and keeps its data')"
                  ask rb "$(t 'Reboot now? (yes/no)')" yes MU300_ANS_REBOOT
                  progress done result ok repartitioned yes resume pending transaction "$RESUME_FILE"
                  [ "$rb" = yes ] && adb reboot
                  echo "  $(t 'Run the installer again once Android is up: it continues from here.')"
                  exit 0; }
            return 0 ;;
        *)
            die "$(t "Cannot tell where the shrink got to: the partition table and Android's data are neither before nor after it. Nothing was written. Keep the device as it is and keep {1}; the partition table from before is {2}." "$RESUME_FILE" "$_bd/gpt.head")" ;;
    esac
}

# online_reboot_wait BOOT_ID: after the restart, until Android is up with root again, in a boot other than BOOT_ID (adb
# can still answer from the old one for a moment); a terminal run then goes on by itself
online_reboot_wait() {
    say "$(t 'Waiting for Android to start again')"
    _w=0
    while [ $_w -lt 150 ]; do
        sleep 2; _w=$((_w + 1))
        [ "$(adb get-state 2>/dev/null)" = device ] || continue
        [ "$(adb_prop sys.boot_completed)" = 1 ] || continue
        _b=$(adb shell cat /proc/sys/kernel/random/boot_id </dev/null 2>/dev/null | tr -d '\r')
        [ -n "$_b" ] && [ "$_b" != "$1" ] || continue
        [ "$(su_do 'id -u' 2>/dev/null)" = 0 ] && return 0
    done
    return 1
}
