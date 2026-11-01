#!/system/bin/sh
# Android's USB functions while an installer works over adb (runs as root on Android; install.sh, install.ps1, the
# uninstallers and the web installer push it and run it under su). Reported by kanoqwq: on an F50 the stock firmware's
# MTP function hangs, and Windows then resets the whole USB device about every ten seconds - which ends the adb
# session the installer uses each time. Nothing here needs MTP (or PTP), so for the time of an installation the
# device offers adb alone.
#
#   android-usb.sh adb-only          when the functions include mtp or ptp (and adb): switch to "adb" alone.
#                                    MU300-USB switch OLD BOOT_ID    (the switch starts a second later, detached)
#                                    MU300-USB keep CONFIG BOOT_ID   (no mtp/ptp: nothing to do)
#                                    MU300-USB skip CONFIG BOOT_ID   (no adb in them, a reboot under way, or a value
#                                                                    this script does not know: left alone)
#   android-usb.sh restore OLD BOOT_ID   back to OLD, only in the boot that was switched (BOOT_ID) and only while the
#                                    functions are still "adb" (the switch's): MU300-USB restore OLD, else
#                                    MU300-USB keep CONFIG
#
# How (the F50's stock init.ums9620_2h10_ufi.usb.rc and AOSP's init.usb.configfs.rc, read from an F50's vendor and
# system images, B09): sys.usb.config is what init builds the configfs gadget from. Android's UsbDeviceManager
# (UsbHandlerLegacy: these devices have no USB gadget HAL) switches by setting it to "none", waiting for
# sys.usb.state to say "none", then setting the new value - the same here. "adb" is a configuration every
# configfs Android has (AOSP's own rc), and the F50's vendor rc builds it as 19d2:1352 with ffs.adb alone for each
# persist.vendor.sys.modem.diag value (none, disable, ,gser, ,vser). The stock default is ecm,mtp,adb (19d2:1353).
# Only sys.usb.config is set, never persist.sys.usb.config: the next start of Android has the user's functions
# again, whatever happens to this computer. UsbDeviceManager keeps its own idea of the functions (it was not asked)
# and does not set them again while it has nothing to change.
#
# Changing the functions takes the USB device away and back (adb drops for a few seconds; Windows and macOS see
# another USB product id): the caller waits for adb, see tools/usb-adb.sh and tools/usb-adb.ps1.
#   MU300_GETPROP, MU300_SETPROP, MU300_BOOT_ID, MU300_USB_DELAY, MU300_USB_DETACH=0: for the tests
set -u
GETPROP=${MU300_GETPROP:-/system/bin/getprop}; [ -x "$GETPROP" ] || command -v "$GETPROP" >/dev/null 2>&1 || GETPROP=getprop
SETPROP=${MU300_SETPROP:-/system/bin/setprop}; [ -x "$SETPROP" ] || command -v "$SETPROP" >/dev/null 2>&1 || SETPROP=setprop
BOOT_ID_FILE=${MU300_BOOT_ID:-/proc/sys/kernel/random/boot_id}

boot_id() { tr -d '\n ' < "$BOOT_ID_FILE" 2>/dev/null; }
# a value of sys.usb.config this script passes on: functions as init's rc files name them, comma-separated
config_ok() { case $1 in ''|*[!a-z0-9_,]*) return 1 ;; esac; }
has() { case ,$1, in *,$2,*) return 0 ;; esac; return 1; }

# _switch CONFIG: none, until sys.usb.state says none (5 s at most), then CONFIG
_switch() {
    sleep "${MU300_USB_DELAY:-1}"
    "$SETPROP" sys.usb.config none
    _n=0
    while [ "$("$GETPROP" sys.usb.state)" != none ] && [ $_n -lt 10 ]; do sleep 0.5; _n=$((_n + 1)); done
    "$SETPROP" sys.usb.config "$1"
}
# switch CONFIG: _switch in a session of its own, so that the end of this adb session (the first thing the switch
# does) does not end it
switch() {
    if [ "${MU300_USB_DETACH:-1}" = 0 ]; then _switch "$1"; return; fi
    if command -v setsid >/dev/null 2>&1; then
        setsid sh "$0" _switch "$1" </dev/null >/dev/null 2>&1 &
    else
        ( trap '' HUP; _switch "$1" ) </dev/null >/dev/null 2>&1 &
    fi
}

cfg=$("$GETPROP" sys.usb.config)
boot=$(boot_id)
case ${1:-} in
    adb-only)
        if ! config_ok "$cfg" || ! has "$cfg" adb || [ -n "$("$GETPROP" sys.powerctl)" ]; then
            echo "MU300-USB skip ${cfg:-none} $boot"
        elif has "$cfg" mtp || has "$cfg" ptp; then
            echo "MU300-USB switch $cfg $boot"
            switch adb
        else
            echo "MU300-USB keep $cfg $boot"
        fi ;;
    restore)
        old=${2:-} want=${3:-}
        config_ok "$old" || { echo "usage: android-usb.sh restore CONFIG BOOT_ID" >&2; exit 2; }
        if [ -z "$want" ] || [ "$want" != "$boot" ] || [ "$cfg" != adb ] || [ -n "$("$GETPROP" sys.powerctl)" ]; then
            echo "MU300-USB keep ${cfg:-none}"
        else
            echo "MU300-USB restore $old"
            switch "$old"
        fi ;;
    _switch) config_ok "${2:-}" && _switch "$2" ;;
    *) echo "usage: android-usb.sh adb-only | restore CONFIG BOOT_ID" >&2; exit 2 ;;
esac
