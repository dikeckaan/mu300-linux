#!/system/bin/sh
set -eu
SKIPUNZIP=0
ui_print "********************************"
ui_print " MU300 OpenWrt TF + Linux 7.2"
ui_print "********************************"
ui_print "- Writes only the TF card, boot_b and 32 bytes of misc"
BB=$MODPATH/busybox
chmod 755 "$BB" "$MODPATH"/*.sh
[ "$(id -u)" = 0 ] || abort "! root is required"
slot=$(getprop ro.boot.slot_suffix | "$BB" tr -d _)
[ "$slot" = a ] || abort "! Android is on slot $slot; Linux must be installed to slot b"
[ -b /dev/block/by-name/boot_b ] || abort "! boot_b was not found"
R=/dev/block/mmcblk1p1
[ -b "$R" ] || R=/dev/block/mmcblk1
[ -b "$R" ] || abort "! TF card was not found"
cat > "$MODPATH/mu300-install.env" <<EOF
SD_MODE=1
SD_DEV=$R
FORMAT=1
OSES="openwrt"
WIPE_LEGACY=0
UPDATE=0
BOOT_OS=openwrt
DEFAULT_LINUX=1
BOOT_ATTEMPTS=5
IMPORT_HOTSPOT=1
KERNEL=7.2
PWHASH=''
EOF
ui_print "- Installing OpenWrt rootfs to $R"
MU300_PAYLOAD_DIR="$MODPATH" MU300_INSTALL_TMP=/data/local/tmp/mu300-tf-install \
MU300_VENDOR_FROM_DEVICE=1 MU300_KEEP_PAYLOAD=1 \
    sh "$MODPATH/android-install.sh" || abort "! TF rootfs installation failed; boot partitions were not changed"
IMG=$MODPATH/boot-linux-slotb.img
want=$(cat "$MODPATH/boot-linux-slotb.sha256")
have=$("$BB" sha256sum "$IMG" | "$BB" cut -d' ' -f1)
[ "$have" = "$want" ] || abort "! packaged boot image checksum mismatch"
ui_print "- Writing and verifying boot_b"
"$BB" dd if="$IMG" of=/dev/block/by-name/boot_b bs=4M 2>/dev/null || abort "! writing boot_b failed"
sync
bytes=$("$BB" stat -c %s "$IMG")
back=$("$BB" dd if=/dev/block/by-name/boot_b bs=1M count=$(( (bytes + 1048575) / 1048576 )) 2>/dev/null | \
       "$BB" head -c "$bytes" | "$BB" sha256sum | "$BB" cut -d' ' -f1)
[ "$back" = "$want" ] || abort "! boot_b verification failed; misc was not changed"
ui_print "- Arming slot b"
MU300_BUSYBOX="$BB" MAGISKTMP=${MAGISKTMP:-/data/adb/magisk} \
    sh "$MODPATH/switch.sh" --no-reboot || abort "! boot slot could not be armed"
ui_print "- Installation complete; reboot to enter OpenWrt"
ui_print "- A failed Linux boot automatically returns to Android"
rm -f "$MODPATH/mu300-openwrt.tar.gz" "$MODPATH/boot-linux-slotb.img" "$MODPATH/busybox"
