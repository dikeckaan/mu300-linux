#!/bin/sh
# Set a new Linux password without booting Linux. Run on a macOS/Linux host with the device in rooted Android
# (adb + su); it mounts the Linux filesystem from Android and rewrites the password hash in /etc/shadow. With an
# installation on the SD card (ext4 labelled mu300sd) that one is changed: it is the one that boots.
#
#   tools/reset-password.sh [ubuntu|openwrt|openwrt-luci|all]      (default: all; both is an alias of all)
#
# Forgot the password and Linux boots by default? Unplug the device about ten seconds after it powers on and plug
# it back in: the bootloader sees an unfinished boot and falls back to Android, then run this.
set -eu
WHICH=${1:-all}
[ "$WHICH" = both ] && WHICH=all
TOP=$(cd "$(dirname "$0")/.." && pwd)
T=/data/local/tmp

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
su_do() { adb shell "su -c '$1'" </dev/null | tr -d '\r'; }
# tools/storage.sh finds the SD card; this script is English only
t() { printf '%s' "$1"; }
gib() { awk -v b="$1" 'BEGIN { printf "%.1f GiB", b / 1073741824 }'; }

case $WHICH in ubuntu|openwrt|openwrt-luci|all) ;; *) die "usage: $0 [ubuntu|openwrt|openwrt-luci|all]" ;; esac
command -v adb >/dev/null || die "adb not found"
command -v python3 >/dev/null || die "python3 not found"
. "$TOP/tools/linux-mode.sh"
require_android
[ "$(su_do 'id -u')" = 0 ] || die "su does not work on the device"

say "Looking for the Linux filesystem"
# an installation on the SD card is the one that boots (boot/init looks there first, also when there is one in
# internal storage too), so it is the one whose password is reset
. "$TOP/tools/storage.sh"; sd_probe
MOUNTENV=
if [ -n "$SD_DEV" ] && [ "$(sd_existing)" = yes ]; then
    MOUNTENV="MU300_SD_DEV=$SD_DEV"
    echo " SD card $SD_DEV (mu300sd), $(gib "$SD_BYTES"): the installation that boots"
    echo " (an installation in internal storage, if there is one, is left as it is)"
fi
OFF=; SIZE=
if [ -z "$MOUNTENV" ]; then
    # the same search install.sh does; all byte arithmetic happens here, not in Android's 32-bit shell
    set -- $(su_do 'e=0; for p in /sys/block/mmcblk0/mmcblk0p*; do x=$(( $(cat $p/start) + $(cat $p/size) )); [ $x -gt $e ] && e=$x; done; echo $e $(cat /sys/block/mmcblk0/size)')
    [ $# -eq 2 ] || die "could not read the partition table from the device"
    disk=$2
    for cand in $(( ($1 / 4096 + 1) * 4096 * 512 )) 27762098176; do
        region_on_disk "$cand" || continue    # never read past the end of the eMMC (storage.sh)
        m=$(su_do "dd if=/dev/block/mmcblk0 bs=1 skip=$((cand + 1080)) count=2 2>/dev/null | od -An -tx1" | tr -d ' ')
        l=$(su_do "dd if=/dev/block/mmcblk0 bs=1 skip=$((cand + 1144)) count=16 2>/dev/null" | tr -d '\000')
        if [ "$m" = 53ef ] && [ "$l" = mu300root ]; then
            blocks=$(su_do "dd if=/dev/block/mmcblk0 bs=1 skip=$((cand + 1028)) count=4 2>/dev/null | od -An -tu4" | tr -d ' ')
            logbs=$(su_do "dd if=/dev/block/mmcblk0 bs=1 skip=$((cand + 1048)) count=4 2>/dev/null | od -An -tu4" | tr -d ' ')
            OFF=$cand; SIZE=$((blocks * (1024 << logbs))); break
        fi
    done
    [ -n "$OFF" ] || die "no Linux filesystem found on this device (neither mu300root in internal storage nor mu300sd on an SD card)"
    echo " internal storage: offset $OFF, $((SIZE / 1048576)) MiB"
fi

say "Mounting the Linux filesystem"
adb push "$TOP/tools/android-mount-mu300root.sh" $T/ >/dev/null
out=$(su_do "${MOUNTENV:-MU300_OFF=$OFF MU300_SIZE=$SIZE} sh $T/android-mount-mu300root.sh $T/mu300root")
# ALREADY-MOUNTED is a failure too (the card or region is in use elsewhere)
echo "$out" | grep -q '^MOUNTED' || die "could not mount the Linux filesystem ($out)"
# always unmount again, also when something below fails
trap 'su_do "sync; sh '"$T"'/android-mount-mu300root.sh -u '"$T"'/mu300root" >/dev/null 2>&1 || true' EXIT

systems=$WHICH
[ "$WHICH" = all ] && systems="ubuntu openwrt openwrt-luci"
found=
for os in $systems; do
    [ "$(su_do "[ -f $T/mu300root/$os/etc/shadow ] && echo y")" = y ] && found="$found $os"
done
[ -n "$found" ] || die "no installed system found on the Linux filesystem"
echo " systems:$found"

printf 'New password for "ubuntu" (Ubuntu) and "root" (OpenWrt, openwrt-luci): '
[ -t 0 ] && stty -echo; read -r pw1; printf '\nRepeat: '; read -r pw2; [ -t 0 ] && stty echo; echo
[ "$pw1" = "$pw2" ] && [ ${#pw1} -ge 6 ] || die "passwords differ or are shorter than 6 characters"
HASH=$(printf '%s\n' "$pw1" | python3 "$TOP/tools/sha512crypt.py")
case $HASH in \$6\$*) ;; *) die "could not build the password hash" ;; esac

for os in $found; do
    case $os in ubuntu) user=ubuntu ;; openwrt|openwrt-*) user=root ;; esac
    # the hash contains $ and /, which the device shell would expand inside su -c: edit the file on this computer
    tmp=$(mktemp)
    adb shell "su -c 'cat $T/mu300root/$os/etc/shadow > /data/local/tmp/mu300-pull.bin'" </dev/null >/dev/null
    adb pull /data/local/tmp/mu300-pull.bin "$tmp" >/dev/null 2>&1
    adb shell "su -c 'rm -f /data/local/tmp/mu300-pull.bin'" </dev/null >/dev/null
    [ -s "$tmp" ] || { rm -f "$tmp"; die "$os: could not read /etc/shadow"; }
    HASH=$HASH USER=$user python3 - "$tmp" <<'PY' || { rm -f "$tmp"; die "$os: no line for that account in /etc/shadow"; }
import os, sys
path = sys.argv[1]
user, hashv = os.environ['USER'], os.environ['HASH']
lines = open(path).read().split('\n')
hit = False
for i, l in enumerate(lines):
    f = l.split(':')
    if f[0] == user and len(f) > 2:
        f[1] = hashv          # also clears a locked (!) or empty password
        lines[i] = ':'.join(f)
        hit = True
open(path, 'w').write('\n'.join(lines))
sys.exit(0 if hit else 1)
PY
    adb push "$tmp" $T/shadow.new >/dev/null
    rm -f "$tmp"
    # write through the existing file so owner and mode stay as they are
    su_do "cat $T/shadow.new > $T/mu300root/$os/etc/shadow && rm -f $T/shadow.new"
    ok=$(adb shell "su -c 'cat $T/mu300root/$os/etc/shadow'" </dev/null | tr -d '\r' | awk -F: -v u="$user" '$1 == u && $2 ~ /^\$6\$/ {n++} END {print n + 0}')
    [ "$ok" = 1 ] || die "$os: the password line was not rewritten"
    say "$os: password of \"$user\" reset"
done
su_do "sync"
echo
echo "Boot Linux again: from Android run boot/android-boot-linux.sh, or reboot if Linux is the default."
