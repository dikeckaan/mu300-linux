#!/bin/sh
# The online shrink for real, on Linux, as root, in a throwaway environment (a privileged arm64 container:
# tests/test_online_shrink.py starts it with docker, CI on an arm64 runner too): a 6 GiB disk image with a GPT whose
# last partition is "userdata", an F2FS on it - mounted through a device-mapper mapping as Android's metadata
# encryption has it (dm-N, one slave, all of userdata), or directly - with files on it, and then exactly what the
# installers do: tools/android-online-shrink.sh inspect, stage and start with the committed mu300-f2fs-online, the new
# table from tools/resize-last-partition.py, the worker's status until it is complete. Afterwards: both GPT copies
# are the new ones, the kernel (re-reading the disk) sees the smaller userdata, the F2FS has the target size and its
# UUID, fsck.f2fs finds nothing, and every file reads back with its checksum. Then the refusals: a probe on a
# read-only mount and a stale table. Only loop devices are touched.
#   sh tests/online-shrink-e2e.sh MAPPING     MAPPING: dm or direct
set -eu
MAPPING=${1:-dm}
TOP=$(cd "$(dirname "$0")/.." && pwd)
W=$(mktemp -d /tmp/online-e2e.XXXXXX)
LOOP=; DM=
cleanup() {
    set +e
    umount /data 2>/dev/null
    [ -z "$DM" ] || dmsetup remove mu300ud 2>/dev/null
    dmsetup remove mu300p2 2>/dev/null
    [ -z "$LOOP" ] || losetup -d "$LOOP" 2>/dev/null
    rm -rf "$W" /dev/mu300-online-* /dev/mu300-f2fs-online.lock /dev/block/by-name
}
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok: $*"; }
# getprop of an Android with file-based encryption
mkdir -p "$W/bin"
printf '#!/bin/sh\ncase $1 in ro.crypto.type) echo file ;; ro.crypto.state) echo encrypted ;; esac\n' > "$W/bin/getprop"
chmod +x "$W/bin/getprop"; PATH=$W/bin:$PATH; export PATH

DISK_BYTES=$((6 * 1024 * 1024 * 1024)); disk=$((DISK_BYTES / 512))
truncate -s $DISK_BYTES "$W/disk.img"
# like the devices: small partitions first, userdata last, its size a multiple of 2 MiB (kano's helper takes only an
# F2FS of whole sections; the devices' userdata is one)
sgdisk -n 1:2048:+16M -c 1:misc -n 2:0:+6100M -c 2:userdata "$W/disk.img" >/dev/null
LOOP=$(losetup -f --show "$W/disk.img")
# userdata: a linear mapping at the table's offsets (the container's kernel reads no partition tables), named as the
# devices' kernel names a partition is not needed: the script is told the disk (MU300_ONLINE_DISK)
MU300_ONLINE_DISK=$LOOP; export MU300_ONLINE_DISK
part() {   # part START SIZE: (re)create the "partition" mu300p2, as a restart of the device re-reads the table
    dmsetup remove mu300p2 2>/dev/null || true
    echo "0 $2 linear $LOOP $1" | dmsetup create mu300p2
    UD=$(readlink -f /dev/mapper/mu300p2)
    mkdir -p /dev/block/by-name; ln -sf "$UD" /dev/block/by-name/userdata
}
gptv() { sgdisk -i 2 "$W/disk.img" | sed -n "s/^$1 sector: \([0-9]*\).*/\1/p"; }
ud_start=$(gptv First); ud_end=$(gptv Last); ud_size=$((ud_end - ud_start + 1))
part $ud_start $ud_size
UDN=$(basename "$UD")
mkfs.f2fs -q -f "$UD" >/dev/null
SRC=$UD
if [ "$MAPPING" = dm ]; then
    # Android's metadata encryption: dm-N over all of userdata, mounted from /dev/block/dm-N
    echo "0 $ud_size linear $UD 0" | dmsetup create mu300ud
    DM=1
    SRC=$(readlink -f /dev/mapper/mu300ud)
fi
mkdir -p /data; mount -t f2fs "$SRC" /data
# files, among them some written after the table was read: the shrink moves what lies at the end
for i in 1 2 3 4 5 6; do head -c $((400 * 1024 * 1024)) /dev/urandom > /data/f$i; done
# (2.4 GiB of 5.96: the 4.96 GiB it is shrunk to keeps 2 GiB to spare, kano's margin, and data lies past it)
mkdir -p /data/dir; for i in $(seq 1 200); do echo "file $i" > /data/dir/$i; done
(cd /data && find . -type f | sort | xargs sha256sum) > "$W/sums"
sync

S=$W/stage; mkdir -p "$S"
cp "$TOP/tools/f2fs-online/mu300-f2fs-online" "$S/"
# inspect
out=$(sh "$TOP/tools/android-online-shrink.sh" inspect "$S")
echo "$out" | grep -qx ONLINE=yes || fail "inspect: $out"
v() { echo "$out" | sed -n "s/^$1=//p"; }
blocks=$(v BLOCKS); section=$(v SECTION_BLOCKS); used=$(v USED_BYTES); uuid=$(v UUID)
[ "$(v MAPPED)" = "$ud_size" ] || fail "mapped $(v MAPPED) != $ud_size"
ok "inspect ($MAPPING): $blocks blocks, sections of $section, uuid $uuid"
# the plan, as install.sh makes it: 1 GiB for Linux behind userdata
lin_s=$((1024 * 1024 * 1024 / 512))
new_end=$(( ((disk - 34) / 4096 - 1) * 4096 - lin_s - 4096 - 1 ))
new_size=$((new_end - ud_start + 1))
tgt=$(python3 "$TOP/tools/resume.py" online-target new_size=$new_size section_blocks=$section used_bytes=$used blocks=$blocks)
target=${tgt#TARGET=}
case $target in ''|*[!0-9]*) fail "online-target: $tgt" ;; esac
dd if="$LOOP" bs=512 count=34 of="$S/old-first" 2>/dev/null
dd if="$LOOP" bs=512 skip=$((disk - 33)) count=33 of="$S/old-last" 2>/dev/null
python3 "$TOP/tools/resize-last-partition.py" "$S/old-first,$S/old-last" --disk-sectors $disk --name userdata \
    --end-sector $new_end --out "$S/new" >/dev/null
mv "$S/new.head" "$S/new-first"; mv "$S/new.tail" "$S/new-last"
TOK=0123456789abcdef0123456789abcdef
st=$(sh "$TOP/tools/android-online-shrink.sh" stage "$S" $TOK)
echo "$st" | grep -qx STAGE=ok || fail "stage: $st"
[ "$(echo "$st" | sed -n 's/^SHA_NEW_FIRST=//p')" = "$(sha256sum "$S/new-first" | cut -d' ' -f1)" ] || fail 'staged copy differs'
# more writes after the plan: the worker works on the live filesystem
head -c $((8 * 1024 * 1024)) /dev/urandom > /data/late; sha256sum /data/late | sed 's|/data/|./|' >> "$W/sums"
r=$(sh "$TOP/tools/android-online-shrink.sh" start $TOK "$blocks" "$target" "$uuid" $disk)
echo "$r" | grep -qx LAUNCH=ok || fail "start: $r"
i=0
while :; do
    s=$(sh "$TOP/tools/android-online-shrink.sh" status $TOK)
    case $s in *PHASE=complete*BUSY=0*) break ;; *PHASE=unchanged*|*PHASE=failed*|*PHASE=recovery*) fail "worker: $s" ;; esac
    i=$((i + 1)); [ $i -lt 600 ] || fail "worker did not finish: $s"; sleep 1
done
ok "worker complete: $(echo "$s" | tr '\n' ' ')"
# a second start against the committed state finds nothing to do but to confirm it (resumable, never a second shrink)
sh "$TOP/tools/android-online-shrink.sh" cleanup $TOK | grep -qx CLEANUP=ok || fail cleanup
[ ! -e /dev/mu300-online-$TOK ] || fail 'stage dir left'
# both copies of the table are the new ones
dd if="$LOOP" bs=512 count=34 2>/dev/null | cmp -s - "$S/new-first" || fail 'primary GPT'
dd if="$LOOP" bs=512 skip=$((disk - 33)) count=33 2>/dev/null | cmp -s - "$S/new-last" || fail 'backup GPT'
ok 'both GPT copies are the new table'
# the kernel's view after a restart: the disk read again
umount /data
[ -z "$DM" ] || { dmsetup remove mu300ud; DM=; }
sync; part "$(gptv First)" $(( $(gptv Last) - $(gptv First) + 1 ))
[ "$(blockdev --getsz "$UD")" = "$new_size" ] || fail "the table gives userdata $(blockdev --getsz "$UD") sectors"
fsb=$(dd if="$UD" bs=4096 count=1 2>/dev/null | od -An -tu4 -j1060 -N8 | awk '{ print $1 + $2 * 4294967296 }')
fsu=$(dd if="$UD" bs=4096 count=1 2>/dev/null | od -An -tx1 -j1132 -N16 | tr -d ' \n')
[ "$fsb" = "$target" ] || fail "F2FS has $fsb blocks, not $target"
[ "$fsu" = "$uuid" ] || fail 'F2FS UUID changed'
[ $((fsb * 8)) -le "$new_size" ] || fail 'F2FS larger than its partition'
fsck.f2fs -f "$UD" > "$W/fsck" 2>&1 || { cat "$W/fsck"; fail 'fsck.f2fs'; }
ok "after the restart: userdata $new_size sectors, F2FS $fsb blocks, same UUID, fsck clean"
mount -t f2fs "$UD" /data
(cd /data && sha256sum -c "$W/sums" >/dev/null) || fail 'files differ after the shrink'
ok "every file reads back ($(wc -l < "$W/sums") files)"
# the space behind userdata is outside every partition now
python3 "$TOP/tools/resize-last-partition.py" "$S/new-first,$S/new-last" --disk-sectors $disk --name userdata --show |
    grep -qx "LAST_END=$new_end" || fail 'table does not read back'
ok 'the table reads back with userdata ending where it was planned'

# refusals
# a read-only mount: inspect says no
mount -o remount,ro /data
out=$(sh "$TOP/tools/android-online-shrink.sh" inspect "$S")
echo "$out" | grep -qx ONLINE=no || fail "read-only mount was offered: $out"
mount -o remount,rw /data
ok 'a read-only /data is refused'
# a worker given a table that is not the one on the disk changes nothing
cp "$TOP/tools/f2fs-online/mu300-f2fs-online" "$S/"
dd if="$LOOP" bs=512 count=34 of="$S/old-first" 2>/dev/null; printf 'X' | dd of="$S/old-first" bs=1 seek=600 conv=notrunc 2>/dev/null
dd if="$LOOP" bs=512 count=34 of="$S/new-first" 2>/dev/null; printf 'Y' | dd of="$S/new-first" bs=1 seek=600 conv=notrunc 2>/dev/null
sh "$TOP/tools/android-online-shrink.sh" stage "$S" $TOK | grep -qx STAGE=ok || fail 'stage 2'
out=$(sh "$TOP/tools/android-online-shrink.sh" inspect "$S"); b2=$(echo "$out" | sed -n 's/^BLOCKS=//p'); u2=$(echo "$out" | sed -n 's/^UUID=//p')
r=$(sh "$TOP/tools/android-online-shrink.sh" start $TOK "$b2" $((b2 - section * 4)) "$u2" $disk)
echo "$r" | grep -qx LAUNCH=failed || fail "a stale table was accepted: $r"
fsb2=$(dd if="$UD" bs=4096 count=1 2>/dev/null | od -An -tu4 -j1060 -N8 | awk '{ print $1 + $2 * 4294967296 }')
[ "$fsb2" = "$b2" ] || fail 'the F2FS changed although the table was stale'
ok "a stale partition table is refused before anything changes ($(echo "$r" | sed -n 's/^STAGE=//p'))"
sh "$TOP/tools/android-online-shrink.sh" cleanup $TOK >/dev/null
echo "PASS ($MAPPING)"
