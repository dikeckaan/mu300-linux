# Android web-panel plugin: system switcher

A browser plugin for the device's **Android-side web management panel** that switches to Linux (OpenWrt) in one
tap: it arms the boot slot Android is not on and reboots. It is the web-panel twin of the Magisk module
(`android/magisk/mu300-linux-switch`, `mu300-linux` / `switch.sh`) and writes the same block.

## What it writes

Exactly 32 bytes: the AOSP `bootloader_control` block at offset `0x800` of `misc`. It reads the live block,
sets `slot_suffix` to the Linux slot and the two metadata bytes (Linux priority 15 / tries 2 / successful 0,
Android priority 14 / tries 1 / successful 1), recomputes the CRC32 (IEEE 802.3, over the first 28 bytes,
little-endian at bytes 28-31), writes it back with `dd`, reads it back and refuses to reboot if the block does
not match. The Android slot comes from `getprop ro.boot.slot_suffix` (falling back to the `slot_suffix` bytes in
`misc`), so any A/B layout works; `boot_a`, `boot_b`, the GPT and `userdata` are untouched.

## Host requirements

The plugin is not a standalone page: it runs inside the panel host, which must provide

* `runShellWithRoot(command, timeout)` - run a shell command as root, resolving `{ success, content }`;
* `createFixedToast(id, html)` / `createToast(text[, colour])` and `t(key)` for its own chrome;
* a `#collapseBtn_menu` element whose next sibling holds `.collapse_box` (where the button is added).

That host is the FeiMao Android panel. **The V50's stock Android panel does not provide this API**, so the
plugin only works where such a host (or an equivalent one) is present. On the stock V50 Android the same switch
is available as `su -c mu300-linux` (the Magisk module) or, from Linux, as LuCI's "Reboot to Android"; this file
is kept for panels that do host plugins.

## Installing

Copy `mu300-system-switch.js` into the panel host's plugin directory (the host loads every `.js` there; the file
is a `//<script>`-wrapped snippet, not an ES module).
