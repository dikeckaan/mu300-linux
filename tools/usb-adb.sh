# Shared by install.sh and uninstall.sh: Android's USB functions set to adb alone for the time of a run (no MTP, no
# PTP), and set back at its end when the device is still in the same boot of Android. Reported by kanoqwq: an F50's
# stock MTP hangs, and Windows then resets the USB device about every ten seconds, which cuts the adb session each
# time. The device side, and why it is done this way, is tools/android-usb.sh. Not persistent: the next start of
# Android has the user's functions again.
#   MU300_USB_ADB_ONLY=0   leave the USB functions as they are
#   MU300_USB_WAIT=SECONDS how long to wait for adb after the switch (default 60)
# Uses: su_do, say, die, info, t, and answers_exit (tools/answers.sh) - usb_adb_only sets an EXIT trap that runs it.
USB_WAS= USB_BOOT=
USB_T=/data/local/tmp

usb_push() { adb push "$TOP/tools/android-usb.sh" $USB_T/android-usb.sh >/dev/null 2>&1; }
usb_word() { printf '%s\n' "$1" | sed -n 's/^MU300-USB //p' | head -n1; }

# usb_wait STATE: until adb answers again and sys.usb.state is STATE; status 1: not within MU300_USB_WAIT seconds.
# USB_SEEN: what sys.usb.state said last (empty: adb did not answer at all)
usb_wait() {
    USB_SEEN=; _uw=0
    while [ $_uw -lt "${MU300_USB_WAIT:-60}" ]; do
        sleep 1; _uw=$((_uw + 1))
        USB_SEEN=$(adb shell getprop sys.usb.state </dev/null 2>/dev/null | tr -d '\r' | head -n1)
        [ "$USB_SEEN" != "$1" ] || return 0
    done
    return 1
}

# usb_adb_only: call when root is known to work. Again after Android restarted in the same run (a new boot has the
# user's functions again).
usb_adb_only() {
    [ "${MU300_USB_ADB_ONLY:-1}" != 0 ] || return 0
    usb_push || return 0
    set -- $(usb_word "$(su_do "sh $USB_T/android-usb.sh adb-only")")
    [ "${1:-}" = switch ] || { info usb.functions "${2:-}"; return 0; }
    USB_WAS=$2 USB_BOOT=${3:-}
    trap usb_exit EXIT
    echo "  $(t 'USB of Android: adb only for this run (was {1}; MTP can stall the connection, Windows then resets it)' "$USB_WAS")"
    if usb_wait adb; then
        info usb.functions adb; info usb.was "$USB_WAS"
        return 0
    fi
    # adb is back, with other functions: Android set them again. Not worse than before: go on with them.
    if [ -n "$USB_SEEN" ]; then
        echo "  $(t 'Android kept its USB functions ({1}); going on with them' "$USB_SEEN")"
        USB_WAS=; info usb.functions "$USB_SEEN"; return 0
    fi
    USB_WAS=
    die "$(t 'the device did not come back on adb within {1} seconds after its USB was set to adb only: unplug it and plug it in again (or restart Android), then run this again (MU300_USB_ADB_ONLY=0 leaves the USB as it is)' "${MU300_USB_WAIT:-60}")"
}

# usb_restore: the functions of before, when the device is still in the boot that was switched and nothing else has
# changed them since (android-usb.sh decides; it does nothing while a reboot is under way). Not waited for.
usb_restore() {
    [ -n "$USB_WAS" ] || return 0
    _ur=$USB_WAS; USB_WAS=
    usb_push || return 0
    set -- $(usb_word "$(su_do "sh $USB_T/android-usb.sh restore $_ur $USB_BOOT" 2>/dev/null)")
    [ "${1:-}" != restore ] || echo "  $(t 'USB of Android set back to {1}' "$_ur")"
}

# the EXIT trap: the restore, then what tools/answers.sh's own trap does
usb_exit() {
    _ue=$?
    usb_restore || true
    if [ -n "${PROGRESS_FD:-}" ] && command -v answers_exit >/dev/null 2>&1; then (exit $_ue); answers_exit; fi
}
