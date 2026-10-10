# Findings: running Linux on the ZTE F50 / MU300 (Unisoc T760)

Everything below was verified on a ZTE F50 (hardware MU300, firmware `MU300_ZYV1.0.0B09`,
Android 13, stock kernel `5.4.254-android12-9-g9c6342244991`) during September 2026.
Each item lists the symptom, the root cause and the fix, so it can be reused for other
UMS9620 devices (for example the ZTE U30 Air).

**Update 2026-10-07:** the sections from 31 on were measured in October 2026, on mainline kernels as well as 5.4,
and on more boards (a second F50, the U30 Air: §33, §34). This is a lab notebook, newest last: a later section can
correct an earlier one. Where that happened, the earlier text is kept and an **Update** note under it points to
what replaced it. The table below gives each section's state.

## Contents

| § | Title | Status |
|---|---|---|
| 1 | Slot b one-shot trial (never touch boot_a) | partly superseded by §17, §33a and PR #30 (Linux on either slot) |
| 2 | Boot ramdisk must be LZ4 legacy | current |
| 3 | Logs without a serial console | current |
| 4 | USB gadget dependency chain | current (module count: see note) |
| 5 | The ~290 s power cut (PM co-processor watchdog) | current |
| 6 | Load average of about 12 is not CPU usage | current (5.4); for 6.18 see §31e, §31g |
| 7 | Matching source | current |
| 8 | Build notes | current |
| 9 | Unused space after userdata | current |
| 9b | There is no second home for the rootfs | current |
| 10 | Mounting gotchas | current |
| 11 | systemd 259 works on 5.4 | current |
| 12 | USB Ethernet must be up before the host activates ECM | current (NCM is now the default function) |
| 13 | Userland needing newer syscalls | current (Ubuntu 26.04 offered again, mainline only) |
| 13b | One reader at a time on the modem's AT tty | current |
| 13b-2 | The modem stops answering on Linux | superseded: not reproduced since (§13f-1, §31, §35) |
| 13f | The data call completes and still nothing arrives | current (fixed) |
| 13f-1 | How it looked while it was open | superseded by §13f |
| 13g | The same dead downlink, a different cause | current; open: why the watchdog missed it |
| 13h | Ubuntu never started the delegate at all | current (fixed) |
| 13e | The mailbox stops sending after one slow delivery | current (fixed) |
| 13c | Reading this tty needs `read -t` | current |
| 13d | Memory shared with the modem must not be mapped write-back | current |
| 14 | Wi-Fi bring-up | current (MAC and warning: superseded by §34, §31g) |
| 14b | Wi-Fi station mode: decided at boot, and one way only | partly superseded by §31n (interface recreation) |
| 14c | The Wi-Fi driver can panic the kernel while it is still starting | current (fixed) |
| 15 | Radio, registration and the data bearer | current |
| 16 | Rootfs details found while testing data | current |
| 26b | The tunnel needs sing-box's gvisor stack on this kernel | current |
| 26c | SMS needs PDU mode | current |
| 26e | The Xray engine | current (engines now the vpn extra, PR #31) |
| 17 | Linux as default without losing the Android fallback | current (updated in place; PR #39) |
| 18 | Services and drivers Android runs that the minimal port lacked | current |
| 19 | systemd ordering pitfall | current |
| 20 | Diagnosing early power cuts | current |
| 20b | Telling a userspace reboot from a power cut | current |
| 21 | One LAN for USB and Wi-Fi | current (subnet per device: §33b) |
| 22 | Regulatory database | current |
| 23 | Only one AP; 5 GHz AP needs the DS Parameter Set element | current |
| 26 | Modem resets and mobile data recovery | current (address check added: §31c) |
| 26d | USSD, and the AT lock | current |
| 27 | Where the missing ~550 MiB of RAM goes | current |
| 28 | Mali-G57 GPU (OpenCL) without Android | current |
| 29 | OpenWrt 25.12 next to Ubuntu | current (third system: §35) |
| 30 | Installer notes | current |
| 24 | No internal audio hardware | open |
| 24b | A second board, from a clean install: where the stall actually is | open |
| 25 | SC2355 Bluetooth on BlueZ | current |
| 31 | Ubuntu on 6.18, and what it takes | current (kernel now 6.18.55) |
| 31a | Wi-Fi RX: sync_for_device stopped invalidating | current |
| 31b | The modem units' ordering cycle | current |
| 31c | A context that comes back with a new address | current |
| 31d | Evidence of a failed boot | current |
| 31e | sipa-set-rps: a thread that never started | current |
| 31f | The delegate on OpenWrt: -EINPROGRESS taken for a failure | current |
| 31g | Three warnings on every boot, three vendor bugs | current |
| 31h | Power-off, and the command line's crutches | current |
| 31i | A Wi-Fi card that is late at boot panicked the board | current |
| 31j | SD host under mainline | partly superseded by §31l (mmc numbering) |
| 31k | The Linux filesystem on the SD card | current; the hang is open in §31m |
| 31l | The card slot took mmc0 | current |
| 31m | Hard hangs in the first seconds under 6.18 | open |
| 31n | Wi-Fi powered off and on at the same time: an Oops in the RX interrupt | current (fixed, PR #41); remaining races open |
| 31o | KVM, and the module set a router needs | current |
| 32 | Old kernels, an idle IPA, and an update that ended in Android | current |
| 32a | The offset in init, replaced by every boot image update | current |
| 32b | The Magisk installer on a device | partly superseded by PR #40 (passwords in update mode) |
| 33 | The same board with a battery | partly superseded by §33d, §33f |
| 33a | misc and boot_b were looked up before the eMMC existed | current |
| 33b | Two devices on one computer | current (identity extended in §33j) |
| 33c | Mainline on the U30 Air: the USB PHY waited for a Type-C driver | partly superseded by §33d (battery) |
| 33d | The U30 Air's battery under mainline | current; open: charger-type detection to be retested |
| 33e | USB host on the U30 Air | partly superseded by §33d (charger driver) |
| 33f | The U30 Air's LEDs | current |
| 33g | The U30 Air's NFC tag | current |
| 33h | A trial guard that outlived its experiment, again | current |
| 33i | A reboot "with the hotspot off" that never brought it back | current |
| 33j | Two devices restored from one backup | current |
| 33k | Vendor driver fixes from the U30 Air test, measured | current |
| 34 | LEDs, and the defects from a second board's test | current |
| 35 | kanoqwq's fixes, measured | current (panel languages: PR #48) |
| 36 | Power profiles: idle radios, the charging boot, the charge guard | current; power table and device questions open (PR #62) |
| 37 | System suspend | current (fixes on branch `suspend-drivers`); power not measured |
| 38 | Three defects from users' reports, 2026-10-07 | current |
| 38a | A read past the end of the eMMC never returns | current (fixed) |
| 38b | RNDIS: the port kept the bridge's address | current (fixed) |
| 38c | fw4 on 5.4: the boot ruleset without the LAN, and a reload that always fails | current (fixed at boot; a reload by hand still needs the flowtable deleted first) |

## Hardware and firmware facts

| Item | Value |
|---|---|
| SoC | Unisoc T760 (UMS9620, "qogirn6pro"), board `ums9620_2h10_feimao` |
| RAM | 2 GiB (about 1.4 GiB visible to Linux, the rest is reserved for modem/TEE) |
| Storage | eMMC, about 58.25 GiB (122159104 sectors) |
| PMIC | UMP9620 (+ UMP9621), charger IC bq2560x/sgm41513, fuel gauge sc27xx-fgu |
| Wi-Fi/BT | SC2355 "Marlin3" on PCIe, firmware `MARLIN3_20A_RLS2_W24.45.4` |
| USB | DWC3 (`25100000.dwc3`) + MUSB (`musb-hdrc.1.auto`), Type-C on the PMIC |
| Bootloader | Unisoc LK ("sprdlk"), Trusty TEE, A/B slots |
| Boot images | boot and vendor_boot are Android header v4, page 4096, LZ4 legacy ramdisks |

**Update 2026-10-07:** the charger entry is the device tree's, not the F50's hardware: nothing answers at the
charger's address 0x6b on the F50 (§24, §33d). The U30 Air has the chip, an SGM41511 (a bq25601), §33d.

## Boot chain and safe testing

### 1. Slot b one-shot trial (never touch boot_a)
* Linux is written to **boot_b** only, and the 32-byte AOSP `bootloader_control` block at
  offset `0x800` of `misc` is set so that slot b has the highest priority.
* **Unisoc LK treats `tries_remaining == 1 && successful_boot == 0` as an already failed boot**
  (`ANDROID: slot 1 booted fail, rolling back spl and reboot into normal`). A one-shot trial therefore
  needs `tries_remaining = 2`: LK decrements it to 1 and boots slot b; if that boot fails, the next boot
  rolls back to slot a.
* Linux `init` writes the original slot-a block back to `misc` as one of its first steps, so any later
  reboot returns to Android.

  **Update 2026-10-07:** three later changes. In default-Linux mode init does not restore slot a (§17). The
  restore runs after the vendor modules, once the eMMC exists, about 10 s in (§33a). And since PR #30 Linux can
  be on slot a, with Android on b (after an OTA, the Magisk installer does this). init takes the booted slot from
  LK and restores the other one (`linux_slot_detect` in `boot/init`). "boot_b" in this file means the Linux
  slot's boot partition.
* The `uboot_log` partition contains LK's ring log. It is the best source for "which slot was chosen" and
  "why did it reset" (`rst_mode`, `charge first poweron reset`, watchdog flags).

### 2. Boot ramdisk must be LZ4 legacy
* Symptom: `RAMDISK: lz4 image found at block 0`, `RAMDISK: incomplete write (-28 != 8388608)`, then
  `VFS: Unable to mount root fs on unknown-block(1,0)`.
* Cause: vendor_boot's ramdisk is LZ4 legacy; a gzip boot ramdisk appended to it is not unpacked as an
  initramfs by this 5.4 kernel, which then falls back to the legacy `/dev/ram0` image path.
* Fix: compress the boot ramdisk with `lz4 -l`. Also add a `dev/console` node to the cpio.

### 3. Logs without a serial console
* The stock cmdline has `loglevel=1`, so nothing reaches `console-ramoops`.
* pstore only survives a warm reset. Most failures on this device end in a power cut, so init also
  persists its stage list and `dmesg` into unused space inside **boot_b at 48 MiB (8 MiB)**; it is read
  back from Android.
* A USB CDC-ACM function (`acm.GS0`) next to ECM gives a login console on the host
  (`/dev/cu.usbmodem*` on macOS) that works even when networking does not.

## Hardware bring-up with the vendor modules

### 4. USB gadget dependency chain
The UDC only appears when the whole chain probes, in this order:
`extcon-usb-gpio` (the PHY node references `extcon-gpio`) → PHYs → `sc27xx_adc` → `sprd_battery_info`
→ `sprd-charger-manager` → `sc27xx_fuel_gauge` → `bq2560x-charger` (provides the `otg-vbus` regulator used as
`vbus-supply` by DWC3 and MUSB) → `dwc3-sprd` / `musb_sprd`.
* **`sc27xx_adc` must be loaded before the fuel gauge.** The vendor `sc27xx-fgu` driver returns a hard error
  (not `-EPROBE_DEFER`) when its IIO channel is missing and is never probed again.
* The exact working order of the 86 modules is in `boot/module-order.txt`.

  **Update 2026-10-07:** the list now has 85 entries. `sipa-dele.ko` left it and is loaded after the modem
  (§13f).

### 5. The ~290 s power cut (PM co-processor watchdog)
* Symptom: Linux runs normally, then the device loses power about 290 s after boot. LK shows
  `charge first poweron reset`, not a watchdog reset.
* Cause: the PM co-processor (CM4, `pm_sys`) runs its own watchdog. `sprd_pmic_wdt` disarms it by sending
  `watchdog rstoff` over an SIPC sbuf channel, but that channel only becomes ready after Android's
  `modem_control` reloads `pm_sys` (and the modem) through Trusty (`kernelbootcp` TA).
* Fix: run Android's own `/vendor/bin/modem_control` in a chroot with Android's bionic linker and
  libraries. Requirements that were each discovered by failure:
  1. Copy `/dev/__properties__` from a running Android so property reads work.
  2. Create `/dev/block/by-name` links and apply Android's node ownership (`ueventd.rc` plus `chown`/`chmod`
     from vendor `init*.rc`), because `modem_control` drops to uid `system` (1000).
  3. Bind-mount a copy of `/proc/cmdline` with `androidboot.slot_suffix=_a` so it loads the `_a` modem images
     (LK passes `_b` when booting the trial slot).
  4. **Exec the binary directly.** `sprd_modem_loader` rejects every ioctl/write unless `current->comm` is
     exactly `modem_control` (`drivers/unisoc_platform/modem_loader`); running it as
     `linker64 /vendor/bin/modem_control` makes the task name `linker64`.
  5. Provide a sink for liblog (`tools/logdw`, listens on `/dev/socket/logdw`), otherwise the daemon's logs vanish.
* Result: `kbc_verify_all_avb2() ret = 0`, `SEC_KBC_START_CP() ret = 0`,
  `sprd-pmic-wdt: sbuf ready for pmic wdt init!`, `Modem Alive`, and no more power cut.

### 6. Load average of about 12 is not CPU usage
Vendor kernel threads (`sprd-rotation/N`, `sipa-*`, `slog`) wait in `D` state; Linux counts them in the load
average. `top` shows about 98 % idle.

## Custom kernel

### 7. Matching source
* The ZTE U30 Air kernel (`github.com/Enceka/android_kernel_zte_ums9620_mifi_u30air`, "downloaded from ZTE
  opensource") is exactly 5.4.254, covers 137 of the 150 F50 vendor modules and all but one derived config
  symbol of the F50 stock config.
* Missing from that tree: camera/display/GPU/touch modules (not used on this device) and the Wi-Fi driver
  `sprd_wlan_combo`, which is taken from the realme C51/C53 AndroidT kernel_modules drop.
* An older Unisoc 5.4.147 tree lacks the whole qogirn6pro USB stack and is not usable.

### 8. Build notes
* Full LTO needs more than 8 GiB in the linker step; ThinLTO keeps CFI and links fine.
* Stock config + `kernel/mu300-linux.fragment` adds devtmpfs, fhandle, autofs, SysV IPC, namespaces, nftables,
  btrfs/xfs/squashfs, NFS/CIFS, USB serial/modem/audio host drivers, crypto user API, CDC-ACM gadget, and removes
  `STATIC_USERMODEHELPER` and forced module signatures.
* All vendor modules must be rebuilt from the same tree (symbol CRCs change).

## Root filesystem on free eMMC space

### 9. Unused space after userdata
* `userdata` is 20 GiB and ends at sector 54218752; the GPT's last usable LBA is 122155007 and the backup GPT
  is at the very end. About **32.4 GiB between them belongs to no partition** and read back as zeros.
* The rootfs is an ext4 filesystem (`mu300root`) at byte offset `27762098176` (sector 54222848), 32.39 GiB,
  accessed through a loop device with an offset. **The GPT, userdata and all Android partitions are unchanged.**
* `userdata` uses metadata encryption (`dm-default-key`, `inlinecrypt`), so it cannot be shrunk or shared.

### 9b. There is no second home for the rootfs
Asked for often, because a smaller eMMC variant leaves less free space behind `userdata`. Measured on the device:

* **An image file inside `userdata` cannot work.** Metadata encryption covers the whole partition, not just file
  contents: `mmcblk0p75` reads as ciphertext from Linux - 4079 of the first 4096 bytes are non-zero, no ext4 magic
  at `0x438` (`2d81`), no f2fs magic at `0x400` (`58931da1`). The same `dd` on our own region returns `53ef` and
  the label `mu300root`, so this is the partition and not the reader. The key lives in keymaster and `metadata`
  and Android unwraps it at boot, so a file created from Android is unreadable from Linux whatever we do to it.
* **`blackbox` (500 MiB) and `fulldumpdb` (2 GiB) are not spare.** They look unused, but sampling shows
  `fulldumpdb` non-zero in 16 of 16 samples (it starts with a `note` record) and `blackbox` in 1 of 16: the
  firmware writes crash dumps there.
* So the gap after `userdata` is all there is. The installer no longer demands 4 GiB of it: the installed systems
  measure ~320 MiB (OpenWrt) and ~580 MiB (Ubuntu) and an update keeps the previous one as `<os>.old`, so it asks
  for 800 MiB, 1.6 GiB or 2.4 GiB depending on the choice, and prints the eMMC size and the end of the last
  partition, which identifies the variant when it still does not fit.

* **On the 32 GB variant the space can be made, by shrinking `userdata` - EXPERIMENTAL.** Reported in issue #2
  on a unit whose eMMC is 29.12 GiB (61079552 sectors) with partitions ending at sector 40095744 and `userdata`
  filling the rest, so `--check` computed a negative free size and refused. Shrinking `userdata`'s GPT entry
  left 10 GiB behind it and the installer then ran unmodified.
  * Why only `userdata`: it is the **last** partition, so its end moves and nothing else does. Every other
    partition keeps its offset and the AVB descriptors and the boot chain stay valid. That is the entire
    safety argument, and it does not transfer to any other partition on these devices.
  * `install.sh` offers it when there is no room, asks how many GiB to give Linux and keeps at least 4 GiB for
    Android and 800 MiB for Linux, and requires ERASE to be typed. `uninstall.sh` offers to grow it back, off
    by default because on the 64 GB variant that would hand the factory gap to Android.
    `tools/resize-last-partition.py` does the edit: it validates both GPT copies and every CRC first, refuses
    if the named partition is not the last one, and re-reads what it produced before handing it over. The
    backup GPT is written before the primary, so a power cut between the two leaves the old table and a device
    that still boots.
  * **It rewrites the partition table and erases everything in Android.** Take a full backup first
    (`tools/backup-device.sh`), and treat the path as experimental: it has been done by hand on one device.

### 10. Mounting gotchas
* busybox `mount -o loop,offset=` only creates a loop for regular files; for a block device the options go to
  ext4 and fail with `EINVAL`. Use `losetup -o` and verify `/sys/block/loopN/loop/offset`.
* Android's `losetup -f` can return a loop index whose node does not exist yet; allocate, wait for the node and
  refuse to attach the same offset twice (two loops mounting one ext4 corrupted it once).
* Toybox `od` on 64 MiB is extremely slow; never interrupt a safety check, an interrupted pipeline "passed" once.

## Ubuntu on kernel 5.4

The root filesystem moved from Ubuntu 26.04 to 24.04 LTS: 26.04's userland starts to depend on syscalls newer than
5.4 (below), 24.04 is supported until 2029 and runs on 5.4 without workarounds.

**Update 2026-10-07:** Ubuntu 26.04 is offered again, as a beta, and only with a mainline kernel (6.18 or 7.2).
`install.sh` refuses it with 5.4 for the `openat2` reason in §13. Releases ship `mu300-ubuntu-26.04-rootfs.tar.gz`
next to 24.04 (v2026.10.11).

### 11. systemd 259 works on 5.4
5.4 is systemd's minimum baseline; the system boots to `running` with the `old-kernel` taint.

### 12. USB Ethernet must be up before the host activates ECM
* Symptom: macOS shows the "MU300 Linux USB Ethernet" interface as `inactive` forever, no DHCP, although on the
  device `usb0` is UP with carrier.
* Cause: `usb0` was only brought up by a systemd unit a few seconds after the UDC was bound. f_ecm reports the link
  in its first CONNECT notification and macOS' `AppleUserECM` does not pick up a later "connected" notification.
* Fix: `ifconfig usb0 up` immediately after binding the UDC in the initramfs.

**Update 2026-10-07:** the gadget now offers NCM by default, with ECM only as a fallback. Windows 10 2004+ and 11
bind their inbox driver to NCM, and Windows has no ECM driver. RNDIS is available on request (§35, K6). See
`setup_usb_gadget` in `boot/init`. The same applies to §3's "next to ECM". The rule above, bring the link up before
the host looks, still holds.

### 13. Userland needing newer syscalls
* Ubuntu 26.04's GNU `tar` (1.35+dfsg-4ubuntu0.4) fails with `Cannot stat: Function not implemented` for every
  path, creating and extracting: it resolves paths with `openat2` (Linux 5.6) and has no fallback. 24.04's tar does
  not use `openat2`.
* `ssh.service` is socket-activated (24.04 and 26.04); enable `ssh.socket`, not only `ssh.service`.
* Extracting an archive that contains a `lib/` directory over Ubuntu replaces the `/lib -> usr/lib` symlink with a
  directory (systemd then disappears). Always ship files under `usr/lib/...`.
* `docker export` leaves `/etc/hostname` empty.

### 13b. One reader at a time on the modem's AT tty, and reopen it after a modem restart
`/dev/stty_nr*` are SIPC channels, not real serial ports, and the data goes to **one** reader. While a process
holds the channel, a second one that opens the device reads nothing - it is not broken, it is simply not the owner.

Both of the things this section has claimed over time are true, of different situations, and telling the two apart
is the whole problem:

* A descriptor that was open **across a modem restart** (`AT+SFUN=4`, or a CP crash) refers to a channel that no
  longer exists, so it reads nothing - and because it still occupies the device, every other opener is shut out
  too, which is what made it look permanent. Closing it and opening the device again fixes *that* case
  immediately. Measured: with the daemon holding a stale descriptor, all six channels are silent; with the daemon
  stopped, all six answer `OK` at once.
* **Closing the descriptor while the modem is running does the opposite: the channel never answers again.**
  Measured on 5.4, with `AT+CGACT?` answering normally minutes earlier: `mu300-atd` was killed and started again -
  one close, one open, nothing else - and from then on `/dev/stty_nr1` accepted writes and returned nothing, for
  the remaining forty minutes of that boot. Everything tried against it failed: opening it raw with no daemon at
  all, opening `nr0`-`nr5` together, draining `nr0`, and `/etc/init.d/mu300-vendor restart` - `modem_control`
  re-attaches without reloading the modem (the kernel logs `modem_control has get lock 0`, and no boot follows).
  Only a reboot brings it back. The modem is fine throughout: `nr0` keeps delivering `+SIND` and `+ECIND`, and
  debugfs `modem` still reports `run_state: 1`.

A reopen is therefore the only cure for one case and the cause of the other, so the daemon needs evidence before
it decides, and `nr0` is that evidence: the modem's unsolicited output never stops while it is running, so a `nr0`
that is still producing lines means the modem is alive and this descriptor is fine - whatever else is wrong,
closing it can only make things worse.

Three rules follow, and `mu300-atd` implements all three:

* **Exactly one owner.** The daemon holds the tty and serves one command at a time through a pair of fifos in
  `/run/mu300-at`; `mu300-at "AT+CSQ"` asks it, and `mobile-data` uses it automatically when it is running. Nothing
  else may open the device - including `stty -F`, which is an open and a close of its own.
* **Drain `nr0`.** It is read continuously into a capped log under `/run/mu300-at/urc/`, the way Android's RIL
  holds all six channels open. It is not a cure for a silent channel - that was tried - but registration and PDP
  changes are announced there and nowhere else, and `stty_nr0.log` is what the reopen rule below is built on.
  `nr2`-`nr5` are left alone by default (`MU300_AT_URC_CHANNELS` takes them): a drainer owns its channel as
  completely as the daemon owns `nr1`, and measured, those four say nothing at all.
* **Reopen only when the modem is really gone.** Five unanswered commands, at most one reopen every five minutes,
  and only when `stty_nr0.log` has been quiet for 240 s as well. The earlier rule - reopen after two or three
  unanswered commands - traded a working modem for a dead one on any device busy enough to miss a few replies.

"Exactly one owner" has to be enforced, not assumed. On the mainline kernel the modem kept going quiet a few
minutes after every boot, and it was neither the channel nor the modem: **a second `mu300-atd` had been started**
(procd respawning it, a service started twice). Two daemons read the same `/dev/stty_nr1` and each gets part of
every reply, and the newcomer removes and recreates the command fifo under the one already running, so every
command returns empty. What follows looks exactly like a lost network - the watchdog sees no context, takes the
interface down, netifd tears `wan` down and rebuilds it for ever - while the modem is untouched: stopping every
daemon and starting a single one answered `+CSQ: 43,24` with `+CGACT:1,1` still active. `mu300-atd` now takes
`/run/mu300-at/lock` before it opens the tty or creates the fifo; a second instance waits there instead of
exiting, so a spare is always ready to take over if the owner is killed.

The lock alone was not enough, because `mobile-data` could still walk past it. Its `at()` asks the daemon when
`/run/mu300-at/cmd` exists and opens `/dev/stty_nr1` itself when it does not - and "no fifo" is not the same as
"no daemon". Remove `/run/mu300-at` under a running `mu300-atd` (a stale lock cleaned up by hand, a `tmpfiles`
sweep) and the daemon keeps its descriptor while the fifo is gone, so every `mobile-data` call takes the direct
path and becomes a second reader on a channel that hands each line to exactly one of them. Found on the device:
`mu300-at` reporting "the daemon is not reading commands" while `/proc/*/fd` showed `mu300-atd` *and*
`mobile-data watch` both holding `/dev/stty_nr1`. `mobile-data` now checks `/run/mu300-at/lock/pid` before it
opens anything: a live `mu300-atd` behind that pid means "refuse and say so", and otherwise it takes the same
lock for the length of the command. `tty_setup` obeys the same check, since `stty -F` is an open and a close.

Also make sure only one bring-up runs at a time: `mobile-data up` from the service and from the watchdog used to
run concurrently, and the two of them take the channel lock away from each other for every single AT command, so
neither finishes. `mobile-data` now holds `/run/mu300-mobile-data-up.lock` while it works, `down()` leaves the
context alone while a bring-up owns the channel, and only one watchdog runs.

Verified on 5.4 after these changes: a full `down`/`up` cycle followed by AT queries, and 12 queries over two
minutes with the watchdog polling at the same time - all answered, no reopen needed.

A lock for this has to avoid one trap: **ash and dash run an `EXIT` trap when a subshell exits**, and the daemon
runs a subshell per command (`reply=$(collect ...)`). A `trap 'rm -rf $LOCK' EXIT` therefore deleted the lock a
second after taking it, and the next daemon walked straight in - the very failure the lock was meant to stop, now
happening every few seconds. Clean up on `INT`/`TERM` only, and only when the pid in the lock is still ours.

### 13b-2. The modem stops answering on Linux - and it is not the mainline port (open)
**Measured on both kernels and on stock Android, in that order, and the answer is not what it looked like.** The
modem stops talking to the AP partway through every Linux boot and never comes back without a reboot:

| System | First AT reply | Then | `sipa_eth0` |
|---|---|---|---|
| mainline 6.18.52 | 67 s | silent 22 s later | address, `rx=0` |
| vendor 5.4.254 | 60 s | silent 17 s later | address, `rx=0` |
| stock Android 13 | - | keeps working | address, **`rx=104`** |

So this is **not a regression in the mainline port**: the vendor kernel the device shipped with fails the same way
on the same day, and Android on the same hardware, SIM and carrier passes traffic. What is missing is on our side
of userspace, and it is missing on both kernels. Android runs a full modem stack (RIL, `phoneserver`/`atcmdsrv`,
`slogmodem`, the IMS bridge); we run `modem_control`, `cp_diskserver` and `refnotify` and nothing else - and
`refnotify` cannot even open `/dev/stime_ch` (ENODEV, the time-sync channel), on both kernels. The 5.4 module list
also loads `sipa_usb`, `sprd_pamu3` and `sfp_core`, none of which the mainline build has, though 5.4 shows `rx=0`
with them, so they are not sufficient by themselves.

The rest of this section is what was measured while the failure was still thought to be mainline's. Typical run: `+CSQ: 44,26` at 67 s, nothing at 89 s. What dies is the CP's side of SIPC - the outbox
(CP -> AP) mailbox interrupt stops counting, the modem's own log stops at the same moment, and after the mailbox
fix (13e) the AP's messages still go out and are simply never answered. Restarting the vendor daemons does not
recover it; `modem_control` reloading the modem does not either.

The timing is not fixed: measured deaths 24 s to 60 s after the first successful command (53 s, 87 s, 90 s, 91 s,
109 s of uptime), and not a fixed number of commands either - ten in a fast loop, four at one command every ten
seconds.

Ruled out by measurement, so that nobody spends another evening on them:

* **Our own boot recorder.** It did write 8 MiB to the eMMC every five seconds and that is worth fixing on its own
  (fixed since: `early-recorder` writes only what it has, not the whole 8 MiB window), but with it disabled the
  channel still died.
* **A cached alias of the modem's shared memory.** The vendor device tree marks these reservations without
  `no-map` (only `rebootescrow` has it), so the 5.4 kernel maps them exactly the same way.
* **The modem power manager.** `sprd_mpm_init_resource_ops()` is never called in the 5.4 tree either, so the NULL
  request/release callbacks are normal for this SoC.
* **The data attach.** With `wan` disabled and no `AT+CGDATA` at all, the channel dies just the same.
* **Two daemons on the channel** (real bug, fixed in 13b) and **the modem log ring filling** (real, 257 KB were
  sitting unread, drained now) - neither stops the failure.
* **A full software mailbox queue** (real bug, fixed in 13e) - the AP can send again, and the modem still goes
  quiet.

Also ruled out by the same differential: **our own services**. With `mu300-atd` and `mobile-data` killed and a
single shell holding the tty, the channel still went silent (132 s instead of ~90 s).

The next step is therefore not a kernel one: find what the CP expects from the AP that Android provides and we do
not - the time-sync channel `refnotify` cannot open is the most concrete lead, followed by running more of the
vendor modem userspace in the chroot the way `modem_control` already is.

**Update 2026-10-07:** this failure has not been seen since. The modem now answers for whole boots on both kernels:
SMS and data on 6.18 (§31), and on 20 soft reboots of two devices the RIL handshake and registration worked on every
boot, with a single `AT+SFUN=4` in the whole run (§35). Which change ended it was not established. The likeliest is
§13f-1's `AT+CGDATA` timeout: a late `CONNECT` was read as the answer to the next command. The delegate's load order
(§13f) also changed in this period. Treat this section as history.

### 13f. The data call completes and still nothing arrives - fixed: the delegate has to come after the modem
**Fixed.** The downlink works: DNS resolves through the carrier's own resolvers and a TCP handshake to
1.1.1.1:443 completes, with `rx_packets` and the IPA receive interrupt climbing for the first time. What it
took was loading `sipa-dele.ko` after the modem is up instead of with the rest of the modem stack. The
measurements that led there are kept below, because most of them are about what the *wrong* answers look like.

Before and after, on the same device and SIM, one boot apart:

| | before | after |
|---|---|---|
| `sipa_eth0` rx_packets | 0, always | climbs with every request |
| irq 64 `sprd,multi-sipa-0` | 0 | 67 and rising |
| `SIPA_RM_RES_PROD_CP` | released, ref 0 | granted, ref 1 |
| `nic`: `rc` / `nrt` | 0 / 1 | 4 / 0 |
| channel 5-120 | no trace of it | `send open msg` at 50.9 s, `receive open msg` and `success` at 60.8 s |
| `sipa_dele` conversation | silent | `type=5 flag=1` -> `CONS_WWAN_DL 0->2` -> `type=6 flag=1`, cycling |

The modem answers the channel open the moment it is up - `smsg_ch_open(dst, chan, -1)` waits, and 60.8 s is
exactly when `modem_control` has the CP talking. So the old early load did not fail because the call was made
too early in itself; it failed because the CP was *reset* underneath it afterwards, which is the path where
`smsg_recv` errors out and `conn_thread` exits for good.

Two things that are not this bug, and cost time looking like it:

* **A stopped VPN leaves its policy routing behind.** `/etc/init.d/mu300-vpn stop` removes neither the
  `sbtun` rules (prefs 9000-9010, table 2022) nor sing-box itself, so every packet still goes into a tunnel
  with nothing at the other end and every test reads `Operation not permitted`. That is an EPERM from routing,
  not from the modem, and it made a working data path look dead.

  **Update 2026-10-07:** `mu300-vpn off` now removes rules that a dead engine left behind (`routing_cleanup`,
  prefs 9000-9010 and table 2022), and every exit of the Xray engine takes its routes down (§26e). A service stop
  still leaves the kill switch up on purpose. Only `ENABLE=0` or `mu300-vpn off` removes it. Since PR #31 the engines
  are not in the images at all, see §26e.
* **A resolv.conf left behind by Docker.** Images built before the build fix carry the container's
  `nameserver 192.168.65.7` as a regular file rather than the symlink to `/tmp/resolv.conf`, so every name
  lookup fails while addresses work fine.

What is left is not ours: with the tunnel down, DNS and 1.1.1.1:443 are reachable over the bearer and other
destinations time out, which is the carrier restricting where this SIM may go.

### 13f-1. How it looked while it was open
Measured step by step on 5.4 with the release userspace, so none of it is a mainline or a script regression:

* `AT+CFUN?` is **0 at boot** - the radio is off until `mobile-data` turns it on. Any experiment that stubs
  `mobile-data` out is testing a device with no radio, which is why "the AT channel survives when nothing
  attaches" proved less than it looked.
* With the radio on, the bring-up is textbook: `+CEREG: 2,1` (registered), `AT+CGACT=1,1` returns `^ORIG: 1,2 OK`,
  `AT+CGACT?` reports `+CGACT:1,1`, `AT+CGCONTRDP=1` hands back an address, a netmask and both DNS servers, and
  `AT+CGDATA="M-ETHER",1` answers `^ORIG: 1,2` and then `CONNECT`.
* Configure `sipa_eth0` with exactly that address and route, and **`rx_packets` stays at 0**. Not one downlink
  packet, on either kernel, while stock Android on the same device, SIM and carrier shows `rx=104`.
* `cid 11` is the IMS context (`ims.MNC002.MCC286.GPRS`), not a second internet bearer, and no other `sipa_ethN`
  receives anything either.

**`AT+CGDATA` needs a long timeout.** It answers `^ORIG` first and `CONNECT` ten to twenty seconds later. The
eight-second budget `mobile-data` used meant the reply landed after we had given up, so the next command read
*that* instead of its own answer - which is most of what "the AT channel dies after the attach" really was.
Raised to 45 s.

What is left is the IPA receive path itself. Two differences from Android are recorded but neither is proven:
its RIL defines the context as `AT+CGDCONT=<cid>,"IP",<apn>,"",0,0,0,0,1` (IPv4 only, with the vendor's extra
parameters) where we ask for `IPV4V6`; and its `SIPA_RM_RES_CONS_WWAN_DL` is granted while ours is never
requested - though in `sipa_nic.c` that consumer belongs to PCIe-source nics, and this modem is on-chip.

**The Android reference, taken on the same device with data working** (`sipa_eth0 rx=419 tx=1440`), so that the
Linux dump has something to be compared against rather than reasoned about. Mount debugfs first - Android does
not (`mount -t debugfs debugfs /sys/kernel/debug`):

```
suspend_stage = 0x0 rc = 80 sc = 79 pf = 1          # and 0x3f / 80 / 80 / 0 a second later: it sleeps when idle
mode_state = 0x0 is_bypass = 0x1
open = 0 src_mask = 0x7070 netid = 0 fcs = 0 rm_flow_ctrl = 0 rr = 0 rw = 1 release_in_progress = 1 nrt = 0 rip = 0
DEVICE: sipa_eth0, src_id 6, netid 0, state UP      # rx_errors = 81, tx_errors = 81
SIPA_RM_RES_PROD_IPA      ref_count = 1 state = 2 (granted)
SIPA_RM_RES_PROD_CP       ref_count = 1 state = 2 (granted)
SIPA_RM_RES_CONS_WWAN_UL  ref_count = 1 state = 2 (granted)
SIPA_RM_RES_CONS_WWAN_DL  ref_count = 0 state = 0 (released)   # never granted, even with data flowing
sipa_dummy0: all 419 packets on CPU0, last_irq_trigger set, last_read_empty 0
```

**The configuration is identical to ours.** Same interface name, same `src_id 6`, same `netid 0`, same
`src_mask 0x7070`, same `is_bypass = 0x1`. So the netid/src_id mapping is not the problem, bypass mode is not the
problem, and `CONS_WWAN_DL` being released is not the problem either - Android passes downlink with it released.
What differs is only the history: `rc = 80` against our `rc = 0`, `nrt = 0` against our `nrt = 1`. Ours has never
been woken, because nothing has ever transmitted through it in the boot that was dumped. **The comparison that
matters has therefore still not been made**: the Linux dump has to be taken while packets are actually being
pushed at `sipa_eth0`, and then read field by field against the block above.

**The downlink is the modem's decision, and it asks first.** This is the part the Android log settles, and it
reframes everything above. With data flowing, `dmesg` on Android is a conversation on SIPC channel 120
(`SMSG_CH_COMM_SIPA`, dst 5 = `SIPC_ID_PSCP`), repeating every few seconds:

```
sipa_dele: smsg_recv, smsg_cnt=295, dst=5, chan=120, type=5, flag=0x1   <- the modem asks
sipa_dele: prod_id:4, on_cmd, flag = 1
sipa_dele: sipa_dele get pd success ret = 0
sipa_rm:   SIPA_RM_RES_CONS_WWAN_DL state changed 0->2                  <- the AP grants
sipa_dele: smsg_send, dst=5 chan=120 type=6 flag=1                      <- and acks
...three seconds later...
sipa_dele: smsg_recv, ... type=5, flag=0x2                              <- the modem lets it go
sipa_rm:   SIPA_RM_RES_CONS_WWAN_DL state changed 2->0
```

So `CONS_WWAN_DL` is not released on a working system, as a single sample suggested - it cycles, granted for as
long as the modem has something to deliver. And nothing arrives until the AP answers that request. **A
`sipa_dele` that is not holding up its end is therefore a complete explanation of our symptom**: the modem is
never given permission, so it never sends, so `sipa_receiver_notify_cb` is never called and `rx_packets` stays
at zero while everything else looks correct.

Checking it costs one command, because both halves of the exchange are `pr_info`:

    dmesg | grep -E 'sipa_dele|sipa_rm'

Nothing at all is the interesting answer. Two ways that happens, both visible:

* `sipa_delegator failed to open dst 5 channel 120` - `smsg_ch_open` refused.
* No message of any kind, including that one. `conn_thread` calls `smsg_ch_open(dst, chan, -1)`, and the `-1`
  waits for ever by design ("the channel open may hang, we call it in the thread context"). If the modem side
  never opens channel 120, the kthread simply sits there and says nothing.

Worth knowing while reading the probe: `dts parsing failed` and `get resource failed for remote-base!` are
**not** the failure. `sipa_dele_plat_drv_probe` logs them and carries on, and Android prints them too.

**The delegate gets exactly one attempt, and ours has been taking it too early** (not yet confirmed on the
device, but it follows from the source and from our boot order). `conn_thread`'s first act is
`smsg_ch_open(dst, chan, -1)`, and with the modem not up that ends one of two ways: it waits for ever for an
OPEN that never comes, or `smsg_recv` returns an error, `smsg_ch_open` frees the channel, and the thread logs
`sipa_delegator failed to open dst 5 channel 120` and **returns**. The reopen handling further down
(`case SMSG_TYPE_OPEN: smsg_open_ack(...)`) only ever runs *after* that first open succeeds, so a modem restart
is survivable and a modem that was never there is not. There is no second chance either: `sipa_dele` is
`[permanent]` in `/proc/modules`, so it cannot be removed and inserted again.

Our order made that likely. The initramfs loaded `sipa-dele.ko` with the rest of the modem stack at about
twenty seconds, while `modem_control` does not have the CP talking until about sixty - measured on this device,
`sprd-sbuf: channel 5-*` and `sbuf ready for pmic wdt init` both land at 60.8 s. Android loads it the other way
round. `sipa-dele-start` now waits for one of those two lines before inserting the module, and
`boot/module-order.txt` and `upstream/module-order.txt` no longer carry it. Nothing regresses if the theory is
wrong: `sipa_core` creates every consumer resource itself, and the delegator only adds `PROD_CP` and the
`CONS_WWAN_UL -> PROD_CP` edge, so `sipa_eth0` still opens exactly as before.

Note that this needs a **rebuilt boot image** to take effect - an image that still loads the delegate early
leaves nothing for `sipa-dele-start` to do, by design.

**Do not test this with ping.** On this network ICMP does not come back even over a link that works: on stock
Android, with data flowing, `ping -I sipa_eth0 8.8.8.8` reports 100 % loss, and that form binds to the device,
so it is the cellular path rather than a VPN swallowing the echo. A TCP connect on the same interface completes
and `rx_packets` climbs. The signal to read is that counter, not whether a connect succeeded - the connect may
be carried by a VPN, and on Android it was (`ip route get 1.1.1.1` goes to `tun0`), but the VPN's own packets
still leave and arrive over `sipa_eth0`, which is the only WAN this device has. `mu300-ipa-dump` does it this
way; several earlier "nothing arrives" measurements here were ping-based and proved less than they looked.

Two smaller differences from the same reference, both cheap to copy and neither yet tested:

* Android keeps **IPv6 switched off on that interface** (`/proc/sys/net/ipv6/conf/sipa_eth0/disable_ipv6` is 1);
  ours carries a link-local address. This fits its RIL defining the context as `"IP"` rather than our `"IPV4V6"`.
* Its `rx_errors` and `tx_errors` are equal and non-zero (81 each) on a link that works, so those counters are
  not by themselves a sign of trouble.

**Read the IPA state before theorising - `/sys/kernel/debug/sipa/` answers most of it**, and two of its fields
are easy to misread:

* `nic`: `suspend_stage`, `rc` (resumes), `sc` (suspends), `is_bypass`, then one line per allocated nic. A fresh
  boot that has sent nothing shows `suspend_stage = 0x3f rc = 0` and that is **correct, not a fault**: the driver
  sets `suspend_stage = SIPA_SUSPEND_MASK` in probe (`sipa_core.c`) and the hardware is woken lazily, by the
  first transmit, through `sipa_nic_rm_res_request()`. Likewise `open = 0` on a nic line means `NIC_OPEN`, since
  that enum starts at 0 (`sipa_priv.h`) - an open nic, not a closed one. Any conclusion drawn from these two has
  to come from a dump taken *while traffic is being pushed at `sipa_eth0`*.
* `rm_res` prints the whole producer/consumer graph with its states, `fifo_cfg` the seventeen common FIFOs,
  `flow_ctrl` the per-FIFO enter/exit counts, and `sipa_eth/sipa_eth0/stats` the driver's own packet counters -
  which are the ones to trust, since a route pointing at the interface is not the same as packets reaching it.

### 13g. The same dead downlink, a different cause: the PDP context, not the IPA
The downlink stopped again, and every counter read exactly like 13f's "before" column: `rx_packets` 0 since
boot, `SIPA_RM_RES_PROD_CP` released with ref 0, `suspend_stage = 0x3f`, `nic`'s `nrt = 1`. That invites the
13f diagnosis a second time. It was wrong. `AT+CGACT?` answered:

    +CGACT:1,0
    +CGACT:11,1

The internet context was gone while the IMS context stayed up, and `sipa_eth0` still carried the address from
the previous call - so `ip addr` and every check built on it kept passing. `mobile-data up` brought cid 1 back,
the interface took a new address, and `rx_packets` moved on the first DNS query. Nothing about the IPA, the
delegate or the kernel was involved.

**An idle link reads as a broken one.** SIPA runtime-suspends a few seconds after the last packet. Suspended,
`suspend_stage` is `0x3f` (`SIPA_SUSPEND_MASK`, the value `sipa_probe` starts from), every resource is
Released and `alloc_skb_cnt` is 0, because the receive buffers are posted on resume and handed back on
suspend. That is the normal idle state, not a fault: `docs/reference/android-ipa-state.txt` section 15 shows
Android cycling through it every few seconds. In `sipa/nic`, `rc` and `sc` count resumes and suspends - awake
is `rc == sc + 1`, and `rc == sc` only means nothing has been sent lately. **None of these counters mean
anything unless traffic is actually leaving while you read them.** Drive the link first, then look.

Two things make "traffic is leaving" much harder to establish than it sounds, and both produced false
positives here before the real cause turned up:

* **sing-box's tun answers ICMP itself.** Its `ip rule` set sends locally generated packets into table 2022
  as well (pref 9001 `lookup 2022 suppress_prefixlength 0`, and the tunnel routes are `0.0.0.0/1` and
  `128.0.0.0/2`, which a prefix-length-0 suppression does not catch), so binding the source with
  `ping -I <cellular address>` does not escape it either. Every ping then succeeds in well under a
  millisecond while `sipa_eth0`'s `tx_packets` never moves. A sub-millisecond reply from a public address is
  the tell. Stop sing-box before believing any ping, and check `tx_packets` alongside it.
* **The kill-switch turns the next attempt into a different lie.** With sing-box stopped but the firewall up,
  the same ping returns `sendto: Operation not permitted` - an EPERM from `table inet mu300_vpn`, which reads
  like the modem refusing traffic. Both have to be down, or the test has to be a hole punched in
  `accept_to_wan` and taken straight back out.

The carrier answers DNS but drops ICMP to 8.8.8.8, so a failed ping is not evidence either way on this SIM.
Resolve a name against the address `AT+CGCONTRDP` hands back and watch `rx_packets`; that is the cheap test
that does not lie.

**A cosmetic write could take the data call down with it.** `mobile-data`'s `up()` ends by putting the blue
LED on. The PMIC rejected that write once (`echo: write error: Invalid argument`), and under `set -euo
pipefail` the `&&` list failing ended the function one line before it reported success - after the context was
already up. So the call was live and the caller saw a failure. The LED writes go through a `led()` helper now
that cannot fail. Worth remembering for any other cosmetic side effect in a path that matters.

Still open: `mobile-data watch` was running and its check does look at `AT+CGACT?`, so it should have caught
the dropped context and reconnected. It did not, and this round did not establish why.

### 13h. Ubuntu never started the delegate at all
The fix in 13f moved `sipa-dele.ko` out of the module list into `extra-modules`, which starts `sipa-dele-start` when
it finds `$M/sipa-dele.ko` with `M=/lib/modules/$(uname -r)`. OpenWrt keeps its modules flat in that directory; the
Ubuntu image keeps them under `extra/`. The test was false on Ubuntu, nothing was started and nothing was logged
(not even the log file the redirection would have created), and every Ubuntu image since then came up with an
address on `sipa_eth0`, a finished `mobile-data` and no downlink. What made it look like working on the test unit
was a VPN still pointed at an HTTP proxy on the computer at the other end of the USB cable: `wget` succeeded with
`sipa_eth0` at rx 0 **and tx 0**. Both scripts now look in both places. Measured on Ubuntu afterwards: the delegate
loads at boot, `rx_packets` climbs, and the Xray tunnel reaches its server over the bearer.

### 13e. The mailbox stops sending after one slow delivery (mainline)
On the mainline kernel the modem went quiet about ninety seconds into every boot - `+CSQ: 44,26` at 67 s, nothing
at 89 s - and stayed quiet until a reboot. It was neither the modem nor the channel: writing an AT command left
the mailbox registers untouched (`/dev/mbox`: INBOX `msg_low` identical before and after), so **the AP was not
sending anything at all**. `mbox-deliver-th` was asleep in `sprd_mbox_deliver_thread`, and the inbox interrupt had
fired **zero** times since boot.

`sprd_mbox_send_data()` queues a message in a software fifo when `phy_ops->send()` fails, and only the inbox
interrupt - raised when a delivery completes or a channel blocks - wakes the thread that drains it. But
`check_mbox_chan_state()` also fails with `-ETIMEDOUT` when the remote core is merely slow to take the previous
message, and that raises no interrupt at all. One such timeout leaves the fifo non-empty for ever, and from then
on every message takes the "fifo is not empty, queue it" path: the AP never speaks to the modem again.

The fix is in the driver, not in the timeout: queueing now wakes the deliver thread itself, and the thread retries
what is still queued (1 ms apart) instead of waiting for an interrupt that may never come.

### 13c. Reading this tty needs `read -t`, and only bash or busybox ash have it
Two ways of timing out a read do **not** work here, and both fail silently:

* **dash has no `read -t`.** It is `/bin/sh` on Ubuntu and Debian, so a `#!/bin/sh` script using `read -t` fails on
  every read with "Illegal option", spins through its timeout and returns an empty reply. The symptom is a daemon
  that answers nothing while burning exactly one timeout of CPU per command (measured: 17.9 s for three 6 s
  commands).
* **The termios timer is ignored.** `stty min 0 time 5` changes nothing: the driver blocks in `sbuf_read` until the
  modem says something, possibly for ever. Visible as `wchan = sbuf_read` with zero CPU time.

`read -t` in bash and in busybox ash uses `poll()`, which this driver does implement, so both work. `mu300-atd` and
`mu300-at` re-exec themselves under bash (or busybox ash) when the shell running them has no `-t`.

Apply `stty` to the already-open descriptor (`stty raw -echo <&3`), never `stty -F /dev/stty_nr1`: the `-F` form is
an extra open and close of the device, which takes the channel away from whoever owns it (13b).

### 13d. Memory shared with the modem must not be mapped write-back (mainline)
The modem and the AP share regions that are reserved **inside** System RAM (no `no-map` in the device tree), and
the modem does not snoop the AP's caches. The vendor 5.4 driver maps them with
`vm_map_ram(pages, count, -1, pgprot_noncached(PAGE_KERNEL))`. Newer kernels removed the `prot` argument from
`vm_map_ram()`, and a port that reaches for `memremap(..., MEMREMAP_WC | MEMREMAP_WB)` instead gets **write-back**,
because write-combine is never available for a linear-mapped region.

The modem then starts, asks for its NV data and never finishes: the NV server reads one good packet and logs
`fail SIZE` on the next, writes three chunks, stalls, and `modem_control` gives up with `wait modem alive timeout`
(`g_modem_state = 8`). `ioremap_wc()` cannot fix it either - the kernel refuses ioremap for System RAM addresses
(`WARNING at arch/arm64/mm/ioremap.c:27`) and the code silently falls back to the cached mapping.

`vmap(pages, count, VM_MAP, prot)` still takes a pgprot, so building the page array and mapping non-cached, the way
the vendor driver did, brings the modem up: `fail SIZE` goes to 0 and "Modem Alive" arrives.

## Wi-Fi (SC2355 / Marlin3)

### 14. Bring-up
* Modules: `pcie-sprd-misc`, `pcie-sprd`, `wcn_bsp`, `sprd_wlan_combo`.
* Firmware and board config come from Android's `/odm/firmware`: `wcnmodem.bin`, `gnssmodem.bin`,
  `wifi_board_config.ini`, `wifi_board_config_ab.ini`. Place them in `/usr/lib/firmware`.
* The realme `wlan_combo` driver falls back to `wifi_board_config_hulk.ini` for unknown projects; the firmware then
  asserts with `CMD_DOWNLOAD_INI / LOAD_INI_DATA_FAILED` and the chip stays in "card dump" state, so `wlan0` cannot
  be brought up (`RTNETLINK answers: No such device`). `kernel/patches/wlan_combo-default-board-config.patch` fixes it.
* `rmmod wcn_bsp` crashes the kernel; reboot instead of reloading the Wi-Fi stack.
* The driver logs `API version not match` for a few command IDs (the realme driver is slightly older than the ZTE
  firmware) and a `WARNING` in `sc2355_free_cmd_buf` (spin_unlock_bh in IRQ context).

  **Update 2026-10-07:** the warning was a real lock bug and is fixed on both kernels
  (`kernel/patches/wlan_combo-tx-complock-irqsave.patch`, §31g).
* Verified after the fix: the driver parses `wifi_board_config.ini`, `wlan0` comes up, `iw dev wlan0 scan` lists
  nearby networks and `hostapd` (nl80211, WPA2) reaches `AP-ENABLED`. The MAC address is randomized on each load.

  **Update 2026-10-07:** not any more. The 5.4 driver reads LK's `androidboot.wifimac`, as the mainline port does
  (`kernel/patches/wlan_combo-bootargs-mac.patch`, §34).
* A crash right after installing a module can leave a 0-byte `.ko` on ext4; run `sync` after installing files.

## Mobile data without Android RIL

### 14b. Wi-Fi station mode: decided at boot, and one way only
The SC2355 can be an access point or a client of somebody else's network, but the switch only goes one way:

* The driver creates `wlan0` in **station** mode. hostapd turns it into an access point, and after that nothing
  turns it back. `iw dev wlan0 set type managed` is refused with `Invalid argument` even with the interface down
  and out of the bridge, although `iw phy phy0 info` lists `managed` among the supported modes.
* Deleting and recreating the interface **breaks the radio until the next reboot**: the driver powers the WCN
  chip down and up through an SDIO path (`WCN BASEstart_marlin SDIO card dump`), which is not how Marlin3 is
  attached on this board, and the result is `sprd-wlan: failed to power on WCN!` on every later open. A second
  interface does not help either - with the first one still present the firmware answers scans with
  `sc2355_scan_timeout`.

  **Update 2026-10-07:** this was measured on 5.4, recreating a station after the AP. It is not a general rule.
  Under 6.18, OpenWrt's netifd deletes the driver's station `wlan0` and adds an AP interface on every boot
  (`iface 'wlan0' deleted`, then `type 3 added`, §31n), and the AP comes up. What went wrong in §31n was a race
  with the probe's power-off, not the recreation itself.

So the mode belongs to the boot: `mu300-wifi-client.service` runs before `mu300-hotspot.service`, joins the saved
network while `wlan0` is still a station, and holds `/run/mu300-wifi-client.active`, which the hotspot unit refuses
to start on (`ConditionPathExists=!`). Going back to the hotspot needs no reboot, because that is the direction
hostapd can do by itself.

**WPA3/SAE does not work**: wpa_supplicant negotiates SAE correctly but every association is rejected with
`status_code=1`, so Wi-Fi 7 / WPA3-only networks (a "MLO" SSID, for instance) cannot be joined. The driver says so
itself: `iw phy` lists `connect` but no `authenticate` command (the SME is in the firmware), and wpa_supplicant 2.10
(built with SAE: `get_capability auth_alg` has it) leaves SAE out of `wpa_cli get_capability key_mgmt`. wifi-client
asks that, and refuses a network whose every access point is SAE-only as soon as the supplicant's scan shows it. WPA2 works;
measured on the device: 18 networks scanned, joined, DHCP address, and the Wi-Fi default route (metric 50) taking
precedence over mobile data (metric 100).

### 14c. The Wi-Fi driver can panic the kernel while it is still starting (mainline)
Two boots in a row died at about 29 s with `Unable to handle kernel paging request at 00000000000030b0`,
`pc : sc2355_pcie_tx_cmd_pop_list+0x2c [sprd_wlan_combo]`, reached from `dw_handle_msi_irq` - "Fatal exception in
interrupt", so the kernel stops and LK falls back to Android on the next boot. The captured trace is in
`/sys/fs/pstore/dmesg-ramoops-*`, which Android can read after the failed boot.

The chip reports finished commands with an MSI, and the bus callbacks are registered around `tx_init()` and
`tx_deinit()` - which allocates `hif->tx_mgmt` and sets it back to NULL. An interrupt inside that window walks
`&tx_mgmt->tx_list_cmd.cmd_to_free`, which is offset `0x30b0` from NULL. Both PCIe pop callbacks now return the
buffers to the bus and leave when there is no tx context yet.

### 15. Radio, registration and the data bearer
* AT channels: `/dev/stty_nr0` carries unsolicited results (URCs); `/dev/stty_nr1` is a clean command channel.
* After `modem_control` boots the modem the radio is off (`+CFUN: 0`). Android's RIL (`libimpl-ril.so`) uses the Unisoc
  commands `AT+SFUN=2` (SIM on) and `AT+SFUN=4` (protocol stack on); afterwards `+CFUN: 1` and the modem registers
  (`+CEREG: 2,1,...,13` = E-UTRA-NR dual connectivity, i.e. 5G NSA).
* The network activates the default EPS bearer (CID 1, IPv4v6) by itself. `AT+CGCONTRDP=1` returns the address as
  `a.b.c.d.m.m.m.m` plus DNS servers. `AT+CGDATA="M-ETHER",1` answers `CONNECT` and binds the bearer to
  `sipa_eth0` (`sipa_eth<cid-1>`, raw IP, `NOARP`). Assign the address as /32 and route `default dev sipa_eth0`.
* Measured on a Turkcell 5G NSA SIM: about 9.3 MB/s download and 1.3 MB/s upload. `rootfs/.../mobile-data` implements
  up/down/status/sim-reset and NAT (`nftables masquerade` + MSS clamping) so USB/Wi-Fi clients can share the link.
* AT responses can arrive after a short read timeout and then show up as answers to the next command. Drain the channel
  before sending and read until the final result code (`OK`, `ERROR`, `+CME ERROR`, `CONNECT`).
* Hot-swapping the SIM leaves it busy (`+CME ERROR: 14`) and registration stays at emergency-only (`+CEREG: 2,8`);
  reboot after changing the SIM.
* A SIM without an active data plan still registers and gets an address; TCP handshakes may even succeed, but no data
  flows. Check the plan before debugging the data path.

### 16. Rootfs details found while testing data
* `docker export` leaves an empty `/etc/resolv.conf`: `resolvectl query` works but glibc programs cannot resolve names.
  Link it to `../run/systemd/resolve/stub-resolv.conf`.
* busybox/toybox tar drop xattrs, so `ping` loses `cap_net_raw`; `mu300-fixups.service` restores it.
* Android's uid `system` (1000) is also Ubuntu's first user, so modem device nodes show up as owned by `ubuntu`.

### 26b. The tunnel needs sing-box's gvisor stack on this kernel
**2026-10-09: the VPN moved to its own repository.** `mu300-vpn`, its drivers and engines are the module of
[dikeckaan/mu300-linux-vpn](https://github.com/dikeckaan/mu300-linux-vpn) now, installed as the `vpn` extra
(`mu300-extra install vpn`); the images carry none of it. These findings (26b, 26e, 26f) stay here as they were
written, and are continued in that repository's docs; paths like `/opt/mu300/lib/vpn` are the module's, linked into
each system by its `hooks/link`.

Everything through the VPN failed while the VPN itself looked healthy: it connected to its server, resolved
names through the tunnel, and `sbtun` counted the packets going in. Applications got `Connection refused` from
`nc` and `Failed to send request: Operation not permitted` from `uclient-fetch`, and sing-box logged one line
per connection - `router: pre-match[0] => sniff` - and nothing after it. No outbound was ever selected.

The cause is the tun inbound's default **system** stack, which this 5.4 vendor kernel cannot support. It says so
at startup, in a warning that is easy to read as cosmetic:

    inbound/tun[tun-in]: enable offload: set udp offload: TUNSETOFFLOAD: invalid argument

`"stack": "gvisor"` carries its own TCP/IP and does not ask the kernel for any of it. With that one field,
`apk update` goes from "8 unavailable, 145 distinct packages" to **"OK: 11168 distinct packages available"**,
with the kill switch active the whole time.

Worth remembering while chasing something like this: DNS kept working throughout, because it is hijacked and
answered inside sing-box rather than carried as a TCP connection. A tunnel that resolves names but carries no
traffic points at the stack, not at routing or the firewall - both of which were searched first, and neither of
which had a rule with a non-zero counter.

### 26c. SMS needs PDU mode, and Turkish needs more than that
Text mode (`AT+CMGF=1`) looks like the easy way and is unusable here. Whenever the sender is a name rather than
a number - which is most of what a SIM in a router receives - this modem returns the address mangled:

    +CMGL: 1,"REC READ","144414+4140224P444",,"26/09/17,17:18:47+12"

The PDU for the same message says type-of-address `0xD0`, alphanumeric, and the packed septets spell
`ADANA BLD`. Changing `AT+CSCS` does not help: `IRA`, `GSM` and `HEX` all return the same broken string, HEX
simply in hex. Text mode also cannot tell you that three stored messages are one long message.

So `sms` works in PDU mode and decodes the frames itself, in awk, because busybox awk is the only interpreter
on the device - no python, no lua, no perl. It does have `and()`, `or()`, `lshift()` and `rshift()`, and
`printf "%c"` writes a raw byte for anything under 256, which is enough to emit UTF-8 a byte at a time.

**Turkish arrives as ordinary GSM 7-bit with a header saying to read it against a different table.** The user
data header carries information element `0x25` (national language locking shift) with value `0x01`, and without
honouring it the text comes out the right shape with the wrong letters - `hastası` as `hastasì`, `bağışta` as
`baøìæta`, `Aladağ` as `Aladaø`. Eight positions move (`0x04 0x07 0x0B 0x0C 0x1C 0x1D 0x40 0x60`), and they are
exactly the Turkish ones. The header has to be walked element by element for this: the concatenation element is
not always first, and the language element never is.

Sending picks the encoding from the text - GSM 7-bit while every character fits it, UCS-2 otherwise, which is
what makes `ığşçöü ÇĞİÖŞÜ` survive. Verified by sending to the SIM's own number and reading it back intact.

### 26e. The Xray engine, and a connectivity test that could only say no
(Now the VPN module of [dikeckaan/mu300-linux-vpn](https://github.com/dikeckaan/mu300-linux-vpn): see 26b.)


**Update 2026-10-07:** since PR #31 the engines (Xray-core, hev-socks5-tunnel, sing-box) are not in the Ubuntu or
OpenWrt images. They are an optional release asset, `mu300-extra-vpn.tar.gz`, installed with
`mu300-extra install vpn` or by the installer's question. `mu300-vpn` looks in `extra/vpn/bin` first. Since PR #49,
Tailscale's own traffic also goes through the tunnel (`TAILSCALE=0` opts out). The engine choice below still
holds (`mu300-vpn`, `ENGINE` default).
`mu300-vpn` now defaults to `ENGINE=xray`: Xray-core does VLESS, hev-socks5-tunnel owns a plain kernel TUN (`xtun`)
and hands each flow to Xray's SOCKS port on loopback. Neither installs routes, so the script does, with sing-box's
rule prefs and table (9000-9010, table 2022): Xray's own sockets carry mark `0x2d0` and go to `main`, as do the LAN
and the server's address; everything else goes to `xtun`. The device's own DNS - dnsmasq's upstream, which is the
carrier resolver and does not answer from the far end of a tunnel - is DNAT'd to `REMOTE_DNS`. Every exit path
removes all of it, because routing left behind by a dead engine is what made sing-box's crashes look like a dead
modem.

The kill switch does **not** carry over, even though Xray's sockets carry the same mark: before the tunnel exists
the server's name is resolved through dnsmasq and its certificate fetched with openssl, both unmarked, and the kill
switch drops both - the engine never comes up and the device is left with nothing. sing-box does its bootstrap
lookup on its own marked socket, which is why it never had this problem. So an unset `ENGINE` picks sing-box when
`KILL_SWITCH=1` (what an updated device with an old `vpn.conf` has), and `ENGINE=xray` with the kill switch on
runs without it and says so.

Measured on OpenWrt: the device's exit IP is the server's, `apk add` works through the tunnel, and a Wi-Fi client's
flows are forwarded into `xtun`. The Ubuntu side uses the same script but has not been run on the device.

**allowInsecure is gone in Xray 26.** Its replacement, `pinnedPeerCertSha256`, accepts exactly one leaf
certificate. For a link that asks for allowInsecure the script manages the pin: fetched once with openssl when
there is none and stored as `TLS_PIN_SHA256` in `vpn.conf`, left alone on later starts, and fetched again only when
Xray reports `peer cert is unrecognized (against pinnedPeerCertSha256)` - a renewal - after which the service
restarts itself. Xray reports that failure at **info** level, which a `warning` log level hides completely; the
script runs Xray at info with the access log off and passes only warnings and worse to the system log. `xray tls
ping` is no substitute for openssl here: it tries without SNI first, and a server that ignores that attempt keeps it
waiting past any sensible timeout. (The server this was tested against presents a Let's Encrypt certificate that
expired in December 2025 - which is why its link asks for allowInsecure. The pin skips the expiry check.)

**busybox `nc` on this OpenWrt has no `-w`.** `nc -w 6 HOST PORT` prints the usage text and exits 1, so a
reachability test built on its exit status reports every destination as closed. That produced a confident and
wrong "this SIM reaches nothing but the carrier's DNS" - the same bearer carried the VPN minutes later. Test TCP
with `wget -T` or `curl -m`, check the tool's own exit status rather than a pipe's, and run the test once against
something that must succeed before believing a failure. To test the bearer while a tunnel runs, route a single
address around it: `ip rule add pref 8999 to <addr> lookup main`, test, delete the rule.

### 26f. One VPN command for every protocol: profiles and engine drivers
(Now the VPN module of [dikeckaan/mu300-linux-vpn](https://github.com/dikeckaan/mu300-linux-vpn): see 26b.)

`mu300-vpn` spoke one protocol: a VLESS link in `vpn.conf`. People have WireGuard configs, OpenVPN files,
Clash/mihomo subscriptions and raw Xray/sing-box JSON from their panels, so it now keeps named profiles under
`/etc/mu300/vpn` (`profile import|add|edit|use|remove|export|show|list`, `settings`, `engines`, `check`) and runs
the active one through a driver per engine (`/opt/mu300/lib/vpn/<type>.sh`: `drv_check`, `drv_gen`, `drv_start`,
`drv_alive`, `drv_stop`, `drv_import`...). The core owns what the drivers must not differ in: the kill switch, the
routing (rules 9000-9010, table 2022), the DNS nat and the Tailscale rules. The decisions:

* **ENABLE stays in `vpn.conf`.** Everything else moved, but the switch has too many readers to move with it:
  `mu300-update` and `android-install.sh` (a VPN in use keeps its engines across an update), `wifi-client` (the kill
  switch is fatal only when the VPN is on), `mu300-extra` (refuses to remove the vpn extra while ENABLE=1), the
  dashboard, and every older image, which must find a working VLESS VPN after a downgrade. So `on`/`off` write that
  one line and `vpn.conf` keeps its legacy keys; `wifi-client` and the dashboard read `KILL_SWITCH` and the engine
  from the store first and fall back to `vpn.conf`.
* **Migration by snapshot diff.** At every start (any command, as root) the legacy keys of `vpn.conf` are compared
  with `legacy.snapshot`, the keys as last migrated; only a key whose value changed since is applied (a setting
  set, or profile `legacy` updated). The first run moves everything, a later run does nothing, and a later edit of
  `vpn.conf` - the old README's way, or an older image's `save_pin` after a downgrade and upgrade - wins for the
  keys it touched while settings made with the new commands are kept otherwise. A plain "vpn.conf wins" would undo
  every `settings set`; "the store wins" would ignore the edit the old instructions tell people to make.
* **Marks per engine.** The kill switch lets only traffic marked `0x2d0` (720) out on an uplink, and rule 9000
  keeps marked traffic off the tunnel, so each driver marks its engine's own sockets: Xray's `sockopt.mark` on every
  outbound (and on every dialer nested inside one - xhttp's `downloadSettings`, a `dialerProxy`), sing-box's
  `route.default_mark`, mihomo's `routing-mark`, WireGuard's `wg set fwmark`, OpenVPN's `--mark`. No engine needs an
  exception in the kill switch, which is unchanged.
* **The resolve window.** A server name (WireGuard's Endpoint, OpenVPN's remote, a link's host, the `vnext`
  servers of raw JSON) has to be resolved before the tunnel exists, and with the kill switch up the device's own DNS
  is dropped too (26e's reason Xray needed the sing-box substitute). The core opens the download window's ruleset
  with only the DNS sets filled, resolves, and puts the full kill switch back - one nft transaction each way, never
  a gap. VLESS on Xray behind the kill switch still runs on sing-box, as before, so the existing tests hold.
* **Raw configs are parsed once, strictly, and rebuilt from an allowlist.** A panel's JSON runs as root and could
  open a listener on the LAN, expose an API, bind another interface or write a file. It is read by `jq` once
  (`json_strict`: one object, no duplicate keys, no two keys equal under Go's case folding, since the engines'
  decoders match field names without regard to case and jq keeps the last duplicate silently) and the engine gets a
  new document built from what the allowlist accepts, with the inbound, the log, the mark and the bootstrap DNS
  written last so they always win. An allowlist, not a denylist, because each engine release adds features (some of
  which listen) faster than a denylist would follow. No jq regex (OpenWrt's jq may lack it) and jq's own errors are
  never shown (they quote the file); refusals name a key from our own lists, never a value. What a config may do -
  pick outbounds, route between them, name its DNS - is also its exposure: a `direct`/`freedom` outbound goes past
  the kill switch with the engine's mark, by the config's own choice.
* **OpenVPN never reads the user's file.** The `.ovpn` is tokenized with openvpn's own lexical rules (what the two
  could read differently is refused: a backslash, a quote inside a word, a `</` prefix inside a key block), held to
  an allowlist of directives and key blocks, and openvpn runs only `$RUN/openvpn.conf`, which we write, with our
  options after it: `--route-noexec` and pull-filters for `redirect-gateway`, `route`, `setenv`,
  `block-outside-dns`, and only our own `--up` script. Not `--route-nopull`: it would also drop the pushed
  `dhcp-option DNS`, which is the one thing from the server the up script wants.
* **sing-box keeps `auto_route`.** Its own routing does exactly what the core does (same prefs, same table), so the
  driver says `DRV_ROUTES=self` and the core only adds the Tailscale rules and the DNS nat, as before.
* **jq is in the images** (Ubuntu, OpenWrt, Arch): the raw-JSON drivers need it, and `wireguard-tools` goes into
  Ubuntu and Arch (OpenWrt has it). Nothing else grows; mihomo is the new `vpn-mihomo` extra.

Measured on the U30 Air (OpenWrt, mainline), stated as what was seen and no more: the migration of the device's
working legacy VLESS `vpn.conf` produced profile `legacy` with the same exit IP, without the link ever being read
or printed. Import from stdin, `check`, and switching `legacy` -> a WireGuard profile -> `legacy` worked, with the
routes and rules of the previous profile cleaned up each time and the tunnel up. Then the carrier: on the U30 Air's
SIM, UDP to the WireGuard port never reaches the server - `tcpdump` on `sipa_eth0` shows the marked packets leaving
the device, and the same UDP sent from a Mac on another network arrives at the server - and OpenVPN over TCP
connects but the TLS handshake times out, while the same `.ovpn` completes from the home network. The carrier
drops that UDP and DPI-blocks OpenVPN's TLS; the VLESS profile goes through. The WireGuard and OpenVPN drivers were
verified on the device up to that point, no further.

## Default boot

### 17. Linux as default without losing the Android fallback
* LK decrements `tries_remaining` before booting a slot and rolls back when it finds `tries == 1 && !successful`.
  The one-shot trial arms slot b with `tries = 2`.
* Default-Linux mode never sets `successful_boot`. Instead:
  1. init skips the slot-a restore when `/etc/mu300/default-boot` in the rootfs says `linux` (slot b is left at `tries = 1`);
  2. `mu300-boot-ok.service` runs 30 s after `multi-user.target` and writes the `tries = 2` block again.
* A boot that never reaches `mu300-boot-ok` therefore leaves `tries = 1`, and the next boot rolls back to Android.
* Verified: `mu300-next-boot linux` + reboot returned to Linux and re-armed slot b; `mu300-next-boot android` + reboot
  booted slot a.

**Update 2026-10-07:** the list above is the first version, and the rest of this section replaces three things in
it. Slot b is re-armed with `tries = N + 1`, not 2. `mu300-boot-ok` waits for the USB network and SSH, not for
`multi-user.target` (`mu300-boot-ok.service`, still 30 s). Since PR #39, an arm from Android after LK's own fallback
restarts init's count (`stage=boot-tries-restart`, the `boot-tries` block in `boot/init`). Before that, in exactly that
case, init counted N + 1 and sent the first boot after `su -c mu300-linux` back to Android.

**One interrupted boot was enough to lose Linux.** Re-arming with `tries = 2` gives Linux exactly one boot that
may fail. `mu300-boot-ok` runs about a minute after power-on, so pulling the plug once during that minute - or
a power cut, or a crash - sent the next boot to Android. The initramfs has its own counter meant to allow five
such boots, but LK always got there first, so it never mattered. (`uboot_log` shows it plainly: `bootable slot 1
... tries_remaining: 1, successful_boot: 0`, `check rollback slot 1 tries: 1`, `Booting slot_a`.)

Now the user picks N, 1-6, at install (default 5; stored in `.mu300/boot-attempts` on the Linux disk, changed
later with `mu300-next-boot attempts N`), and slot b is re-armed with `tries = N + 1`. LK decrements on every boot
and rolls back at 1, so N boots in a row that never reach boot-ok are allowed and the next one is Android. The
field is three bits, hence the upper limit. The initramfs counter now reads the same N and fires on the same
boot, as a backstop.

**Update 2026-10-09: locked Linux.** `mu300-next-boot lock` arms the Linux slot `successful = 1` (byte `0xEF` for
slot b: prio 15, tries 6, successful). LK never counts a successful slot down, so it never rolls back; the initramfs
skips its backstop when it sees the bit in misc and `.mu300/boot-lock` on the disk (the bit alone, set by anything
else, keeps the backstop), and its standalone fallback (no system to start) stays on telnet with `/run/to-android`
instead of restoring Android's slot. `mu300-update` arms the usual attempts (`--trial`, `0x6F`) before it writes a
boot image or rolls one back, and `mu300-boot-ok` locks again after the first good boot. Verified on the U30 Air
(7.2.9): lock -> `ef`; a new boot image -> `6f`; its first boot -> `ef` again; a boot with `.mu300/boot-tries` at 9
stayed in Linux with `stage=boot-locked (no backstop)`.

* The block is rebuilt at run time from the initramfs' `tries = 2` block, because `mu300-update` does not replace
  the boot image and an older one carries only that block. Byte 14 is slot b's `prio | tries << 4 |
  successful << 7`; the CRC-32 over the first 28 bytes comes from `gzip`, whose stream trailer is the same
  CRC-32. Before writing anything the script rebuilds `tries = 2` and requires it to match the initramfs' block
  byte for byte, and falls back to that block otherwise.
* An older boot image still has the initramfs counter fixed at five, which sends a device to Android after four
  failed boots whatever N says.
* Measured with N = 5 on OpenWrt, with boot-ok suppressed for two boots: LK booted slot b from `tries = 6`, then
  from 5, then from 4 - two unconfirmed boots in a row stayed in Linux - and the next good boot re-armed 6. Not
  run to exhaustion; the rollback at `tries = 1` is the LK behaviour above.

**Boot-ok used to wait for every service.** It was ordered `After=multi-user.target`, so one service that never
finished - `mobile-data` stuck on a busy AT channel in an older Ubuntu image - kept the boot unconfirmed however
usable it was, and the next reboot counted it as failed. It now follows only the USB network and SSH: a boot you
can log in to is a good one. Measured on Ubuntu: SSH at 47 s, boot-ok at 79 s, independent of the rest.

`mu300-os` also carries `default-boot` to the system it switches to. The initramfs reads it from the system it
boots, so switching from one where Linux is the default to one where it was never set made the first reboot
there go to Android.

## Parity with Android

### 18. Services and drivers Android runs that the minimal port lacked
* `cp_diskserver` persists modem NV (`nr_fixnv*`, `nr_runtimenv*`); on first start it immediately wrote pending
  "dirty" NV data, so without it modem NV changes are lost. `refnotify` handles modem reference-clock requests.
  Both run from the same chroot; `srtd` needs Android's binder radio HAL and is skipped.
* Drivers that load cleanly after the modem is up: `sprd_soc_thm`, `thermal-generic-adc`, `sprd_cpu_cooling` (binds
  cpufreq and CPU hotplug cooling to `soc-thmzone` with trips at 70/85/110 °C), `leds-sc27xx-bltc` (RGB status LED),
  `zte_card_holder_det`, `sc27xx-vibra`, `sprd_cp_dvfs`, `sprd_ddr_dvfs`. `zte_sar` loads but the aw9610x SAR sensor
  is not populated on this board (`-201`).
* Android disables audio entirely (`ro.audioserver.disabled=true`, no sound cards) although the device tree has an
  enabled sound card (`unisoc,vbc-v4-codec-sc2730`), the UMP9620 codec and an AW883xx smart amplifier that answers on I2C.
* Android's hotspot (`WifiConfigStoreSoftAp.xml`) lives on the metadata-encrypted `/data`, so Linux cannot read it; it
  has to be copied while Android runs. No factory default Wi-Fi credential is stored in a readable partition.
* RAM: Android uses about 960 MiB of the 1.4 GiB; Ubuntu with all services about 480 MiB, of which ~100 MiB is
  unreclaimable vendor-driver slab. journald is capped (`RuntimeMaxUse=16M`).

### 19. systemd ordering pitfall
* A unit `Before=ssh.socket` that keeps default dependencies is ordered after `basic.target`, while `ssh.socket` is
  before `sockets.target` (before `basic.target`). systemd silently drops `ssh.socket` from the boot transaction and SSH
  never starts. Units that must run before sockets need `DefaultDependencies=no`.

### 20. Diagnosing early power cuts
* The initramfs log loop ends at `switch_root` and journald flushes only after local filesystems are up, so a power cut in
  the first seconds of systemd leaves no log. `mu300-early-recorder.service` keeps writing `dmesg` to the boot_b log area
  for the first five minutes.

  **Update 2026-10-07:** it now writes every 2 s for the first 90 s, then every 10 s (§31d). It runs up to 300 s on
  Ubuntu (`mu300-early-recorder.service`) and up to 420 s from OpenWrt's preinit
  (`openwrt/overlay/lib/preinit/05_mu300_early_recorder`). It writes only what it has collected, not the full
  8 MiB.

### 20b. Telling a userspace reboot from a power cut, and finding who asked for it
`/sys/fs/pstore/console-ramoops-0` survives into the next boot and separates the two cases in one line. A power cut or a
watchdog leaves the log ending mid-sentence; a deliberate reboot ends with the kernel's own

    [   46.468782]c0 [    T1] reboot: Restarting system with command 'shell'

`[T1]` is the task that made the call, and on OpenWrt that is procd: busybox `reboot` does not call the syscall itself,
it hands the request to init, so *every* userspace reboot on this image shows up as pid 1 no matter who started it. The
pstore line therefore says "userspace asked", never who. Three things together do say who, and all three write to
`/mnt/mu300-disk/.mu300/` so they survive the reboot they are recording:

* **not** a wrapper on `/sbin/reboot`. That was tried and it deadlocks the device: on OpenWrt `reboot` hands the
  request to procd, and procd runs `/sbin/reboot` itself on the way down - straight back into the wrapper, which
  execs busybox, which tells procd again. Nothing reboots, `reboot` simply returns and the machine keeps
  running, and the only sign is the audit file gaining an entry whose caller is `pid=1 /sbin/procd`. Hours were
  lost to this twice over: once wondering why the device would not reboot, and once reading the two entries an
  earlier operator's `reboot` had left as evidence of something deliberate. If a wrapper is wanted anyway, it
  must call `reboot(2)` directly (`busybox reboot -f`) rather than exec the applet that talks to init,
* a line at the top of each `/etc/rc.button/*` handler - OpenWrt's `reset` handler reboots on a *short* press
  (`SEEN < 1`), so a bouncing key is a plausible cause and worth ruling in or out explicitly,
* a kprobe on the syscall for anything that bypasses `/sbin/reboot`, which needs no module:

      echo 'p:mu300reboot __arm64_sys_reboot' > /sys/kernel/debug/tracing/kprobe_events
      echo 1 > /sys/kernel/debug/tracing/events/kprobes/mu300reboot/enable
      cat /sys/kernel/debug/tracing/trace_pipe >> /mnt/mu300-disk/.mu300/reboot-trace.log &

  `trace_pipe` is worth the reader process: the trace buffer itself does not survive the reboot, and procd sleeps a
  second before it calls the syscall, which is long enough for the line to reach the disk.

`gpio-keys` on this board exposes `KEY_VOLUMEDOWN`, `KEY_VOLUMEUP` and `KEY_POWER` (`B: KEY=1c000000000000 0`) and no
`KEY_RESTART`, so `/etc/rc.button/reset` cannot fire here; `/etc/rc.button/power` runs `poweroff`, which the kernel
would log as "Power down" rather than "Restarting system".

## LAN, Wi-Fi bands and regulatory

### 21. One LAN for USB and Wi-Fi
* `br-lan` (192.168.77.1/24) bridges `usb0` and `wlan0`; one dnsmasq serves both.

  **Update 2026-10-07:** 192.168.77.1 is the F50's default. The U30 Air uses `.78` (`mu300-lan-ip`, §33b), and
  `lan.conf` or LuCI can change either.
* cfg80211 refuses to bridge `wlan0` ("Device does not allow enslaving to a bridge") because `IFF_DONT_BRIDGE` stays set:
  the SC2355 driver marks the interface as AP but returns an error from `change_virtual_intf` when tearing down the
  previous firmware mode fails, so cfg80211 skips clearing the flag. `kernel/patches/wlan_combo-allow-bridging-ap.patch`.
* After moving modules, delete old copies: `depmod` indexes every subdirectory and `modprobe` loaded stale drivers from
  an `extra.old/` directory for several boots.

### 22. Regulatory database
* This 5.4 kernel only has the `sforshee` regdb certificate; current `wireless-regdb` is signed by `wens`, so
  `iw reg reload` fails with `-ENODATA`, the domain stays `00` and 5 GHz is `NO-IR`. Android's own `regulatory.db` is
  signed by a different certificate and is rejected too. `kernel/patches/regdb-wens-certificate.patch` adds mainline's
  `wens.hex`. cfg80211 tries to load the database before the rootfs is mounted, so userspace runs `iw reg reload` first.

### 23. Only one AP; 5 GHz AP needs the DS Parameter Set element
* `iw list`: `#{ managed, AP } <= 1` — only one AP interface, so 2.4 and 5 GHz cannot be served simultaneously.
* Symptom: with hostapd on channel 36 the firmware answered `CMD_START_AP` with `SPRD_CMD_STATUS_NOT_SUPPORT_ERROR`
  (HT/VHT), or accepted it and never sent beacons (non-HT), for every country, channel, rate set and HT/VHT/PMF setting
  tried. Android's SoftAP on the same firmware runs on 5180 MHz with 80 MHz.
* Stock (ZTE) and realme `sc2355_start_ap` are identical, so the command payload was captured on Android with a kprobe
  on `sc2355_send_cmd_recv_rsp` (`msg->data` at +24, command id at data-11). Android's beacon contains a DS Parameter Set
  element (`03 01 24`) on 5 GHz — Unisoc's hostapd adds it — while upstream hostapd only adds it on 2.4 GHz. The
  firmware takes the AP channel from that element.
* `kernel/patches/wlan_combo-5ghz-ap-ds-params.patch` inserts the element when hostapd omits it. Verified: 802.11a/n/ac
  AP on channel 36 at 80 MHz (seen by a client, disappears when hostapd stops). The firmware offers 5 GHz AP only on
  36-48 and 149-165 (its ACS channel list); `hotspot-start` uses HT40/VHT80 there, and `hotspot-verify` still falls back
  to 2.4 GHz if the firmware refuses.
* The wiphy rate table lists HT MCS rates as legacy bitrates, so hostapd advertises odd "extended rates" (some with the
  basic-rate bit); Android does the same and the firmware ignores them.
* hostapd's 20/40 MHz coexistence scan (`HT_SCAN`) completes on this driver; the log line after it can lag because
  hostapd's stdout is block-buffered.
* The stock driver prints the SoftAP passphrase to the kernel log (`vendor_softap_convert_para`); Android `dmesg`
  captures contain it.

### 26. Modem resets and mobile data recovery
* The modem firmware occasionally resets: it sends an smsg (type 12, "channel 0 not opened" on the AP side),
  `sipa_delegate: modem_reset`, and `modem_control` stops and reloads the modem through Trusty. It comes back with
  `+CFUN: 0`, no registration and no PDP context, while `sipa_eth0` keeps its stale address, so clients lose internet.
  Android's RIL reconnects silently.
* `mobile-data watch` (`mu300-mobile-data-watch.service`) checks `AT+CGACT?` and the interface address every 30 s and
  runs `up` again after two failed checks; `mobile-data down` sets `/run/mu300-mobile-data-down` so a manual disconnect
  is respected. Verified by switching the radio off: data returned without intervention.

  **Update 2026-10-07:** the check also compares the interface's address with the context's (`AT+CGPADDR`). A
  context can come back with a new address while `sipa_eth0` keeps the old one (§31c).

### 26d. USSD, and the AT lock that made the channel look dead
Three separate traps, and the first one hid the other two for an evening. `mu300-ussd` handles all three.

* **The AT lock meant two things at once.** `/run/mu300-at/lock` was both "`mu300-atd` holds the channel", which
  lasts for the life of the system, and "one client at a time", which lasts for one command. Whichever ran second
  won: a client removed the daemon's directory as it exited, after which the lock behaved as a plain client mutex
  and everything worked — so the collision stayed invisible. Restart the daemon and it takes the directory back,
  and from that moment every client waits out its full 90 s and prints `mu300-at: busy` at a completely idle
  modem. Ownership is now `/run/mu300-at/owner`; `lock` is the client mutex alone.
  * The failure looks exactly like a wedged SIPC channel, which sends you after the modem instead of the lock.
    What tells them apart: `cat /run/mu300-at/owner/pid` against `ps`, and whether `+CSQ` is still ticking in
    `urc/stty_nr0.log` — a wedged channel goes quiet, a blocked lock does not.
  * Do not diagnose this by polling `mu300-at` in a loop. Each call takes the client lock, so the loop queues up
    behind the command already waiting for its answer and genuinely jams what was only blocked.
* **A USSD code has to be sent as hex.** `AT+CUSD=1,"*101#",15` answers `+CME ERROR: 3`, and still does after
  `AT+CSCS="GSM"` — so this is not the character set behaving as documented. `AT+CUSD=1,"2A31303123",15` is
  accepted whatever `AT+CSCS` says.
* **The answer arrives on a different channel than the command.** The command gets a bare `OK` on `/dev/stty_nr1`;
  the `+CUSD` turns up seconds later on nr0, the unsolicited channel. Anything waiting for it on nr1 waits for
  ever. `mu300-atd`'s drainer logs nr0 to `/run/mu300-at/urc/stty_nr0.log`, and that log is what to read — waiting
  on a file also costs the modem nothing, which is the point after the trap above.
* `drain()` in `mu300-atd` now appends what it reads to `urc/stty_nr1.log` instead of discarding it, so a late
  answer on the command channel is recoverable too. `+CMTI` (a new SMS) lands there the same way.
* The third `+CUSD` field is a **CBS** coding scheme, not an SMS one: 15 is the GSM alphabet, 72 is UCS2, which is
  what a Turkish menu comes back as. The body is hex-dumped one byte per character, not packed septets.
  `awk -v mode=ussd -v hex=... -v dcs=... -f sms-pdu.awk` decodes both.
* Verified end to end: `mu300-ussd '*101#'` returns the SIM's own number, and a `dcs=72` body decodes with its
  Turkish characters intact.

### 27. Where the missing ~550 MiB of RAM goes
* `Memory: 1430144K/2097084K available ... 617788K reserved`. The device tree reserves 464 MiB for the modem firmware
  (`cp-modem@88000000`, needed for 4G/5G), 24 MiB for Trusty (`tos-mem`), 8 MiB SIPC shared memory, 3 MiB DDR training
  data and a few small areas; the kernel image (~35 MiB) and the page tables for 2 GiB (~32 MiB) make up the rest.
  `cma_share` (48 MiB) is still usable for movable pages.
* Not needed on Linux: `logobuffer` (9 MiB, there is no display) and `sysdump-uboot` (16 MiB, bootloader crash dumps).
  `kernel/patches/of-reserved-mem-skip.patch` adds `CONFIG_OF_RESERVED_MEM_SKIP` (the boot image command line is not
  passed on by LK, so a cmdline option alone would not work); MemTotal grew from 1447 to 1473 MiB.
* `mu300-zram.service` adds lz4 zram swap of half the RAM (swappiness 100).


### 28. Mali-G57 GPU (OpenCL) without Android
* The stock `mali_kbase.ko` (DDK r40p0) does not load: 166 of its 335 imported symbol CRCs differ from this kernel.
  realme's `kernel_modules` master branch has the same DDK (`gpu/natt/mali`, r40p0-01eac0, UK 11.36, platform
  `qogirn6pro`); an older checkout of the tree has r34p0 (UK 11.31), which Android's r40p0 userspace would not accept.
  `kernel/build-mali.sh` builds it; it probes `23140000.gpu` as "arch 9.0.9 r0p1" and creates `/dev/mali0`.
* Userspace is Android's `libGLES_mali.so` (it is also `libOpenCL.so` and the Vulkan ICD), a bionic library with a
  37-library closure (VNDK apex, bionic, gralloc/mapper HIDL stubs). It runs in the existing vendor chroot with
  `LD_LIBRARY_PATH` covering vendor, egl, VNDK and bionic; `/dev/ion` is enough for OpenCL buffers.
* Test programs are built for bionic with plain clang (`--target=aarch64-linux-android29`, linked against the device's
  `libc.so`/`libdl.so`/`libOpenCL.so`) and a small `_start` that calls `__libc_init` (`tools/gpu/`), so no NDK is needed.
  `android-gpu-run /system/bin/cltest`: "OpenCL 3.0 v1.r40p0-01eac0", device "Mali-G57 r0p1", 4M-element kernel
  verified correct.
* There is no display, so GLES/Vulkan are only usable off-screen. The driver adds about 45 MiB of memory use.

## OpenWrt

### 29. OpenWrt 25.12 next to Ubuntu
* Layout: the ext4 area holds `/openwrt` (and `/ubuntu`, or Ubuntu directly in the root on first installs);
  `/.mu300/boot-os` selects the system and `init` starts `/lib/systemd/systemd` or procd's `/sbin/init`. The disk stays
  mounted at `/mnt/mu300-disk`; `mu300-os ubuntu|openwrt` switches. (**Update 2026-10-07:** a third system,
  `openwrt-luci`, OpenWrt with the MU300 control panel, sits next to them (§35). `mu300-os` switches to any system
  directory on the disk.) `openwrt/build-rootfs.sh` builds the rootfs from the
  official armsr/armv8 tarball (checksum-verified) with apk, our kernel modules flat in `/lib/modules/<release>`
  (ubox kmodloader), the vendor chroot and procd services (`mu300-vendor`, `mu300-hw`, `mu300-post`).
* Cellular WAN is a netifd protocol (`proto mu300cell`, option `apn`), so LuCI/fw4 handle routing, DNS and NAT;
  `mobile-data watch` calls `ifup wan` after modem resets.
* Pitfalls found on the device:
  * procd mounts `/dev` as a 512 KiB tmpfs: copying the 85 MiB Android property area gives empty files and
    `modem_control` never boots the modem (power cut at ~290 s). The property area is now bind-mounted (also on Ubuntu,
    saving the RAM).
  * procd preloads `/lib/libsetlbf.so` into services; the chroot runners unset `LD_PRELOAD` or the bionic linker fails.
  * `ujail` drops capability 38 (CAP_PERFMON), unknown to 5.4, so jailed services crash-loop; `procd-ujail` is removed.
  * OpenWrt's busybox lacks `od`, `timeout`, `losetup`, `telnetd`; the static busybox provides them, plus a tiny
    `mountpoint` script (neither busybox has it).
  * GNU `stty` fails on the modem tty ("unable to perform all requested operations"); it is non-fatal now.
  * `wifi`/netifd wireless handlers are in `wifi-scripts` (with `iwinfo`, `wireless-regdb`), not pulled in by `wpad`.
  * macOS keeps the ECM link inactive after netifd reconfigures `usb0`; a hotplug hook re-enumerates the gadget on every
    LAN ifup.
  * The kernel had no nftables sets (`CONFIG_NF_TABLES_SET`), so fw4's ruleset (`ct state vmap {...}`) was rejected as a
    whole and there was no NAT; the fragment now enables sets, objref, flow offload, redirect, quota and friends.
  * OpenWrt's `regulatory.db` is unsigned; this kernel wants the signed one (Debian's `wireless-regdb`).
  * cfg80211 requests `regulatory.db` at 1.6 s, before the rootfs exists; the direct load fails and the request sits in the
    sysfs firmware fallback for 60 s (no userspace helper answers it, neither on OpenWrt nor with systemd-udevd), and
    `iw reg reload` returns ENOENT meanwhile. `regdb-load` answers the pending requests through `/sys/class/firmware`,
    then reloads; the country is applied before netifd starts hostapd.
  * Attended sysupgrade ("Check online for firmware upgrades") and `sysupgrade` would flash a whole-disk armsr image
    (own GPT, kernel 6.12) over the eMMC and brick the device. The packages are removed and `/sbin/sysupgrade` only allows
    configuration backups.
  * `wifi-scripts` generates an open "OpenWrt" network on first boot; `openwrt-wifi-config` replaces it once (marker
    `/etc/mu300/wifi-configured`) with the imported SSID/WPA2 settings.
* Verified after reboots: 5 GHz AP (channel 36), cellular WAN, a USB client's traffic leaves with the modem's public IP;
  memory use about 140 MiB.
* The early recorder runs from preinit, so a failed OpenWrt boot leaves dmesg, `ps`, `logread` and the Android logcat in
  boot_b for `tools/collect-logs.sh`.


### 30. Installer notes
* Android's `/system/bin/sh` (mksh) does 32-bit arithmetic: byte offsets of the Linux region (27 GiB) overflow, so the
  device script works in sectors. mksh also lets a failing EXIT trap replace the exit status; the installer checks for an
  explicit success line instead.
* `adb shell`/`exec-out` read stdin and swallow answers piped into a script; every call uses `</dev/null`.
* Android restarts once shortly after booting back from a Linux fallback; start the installer when Android has settled.
* A first-generation install (Ubuntu directly in the filesystem root) is replaced by `/ubuntu`; `init` still boots the
  old layout if no `/ubuntu` exists.

## Audio

### 24. No internal audio hardware
* The DT enables a sound card, the UMP9620 codec and an AW883xx amplifier at `6-0034`, and Android disables audio.
  With `i2c-dev`, nothing answers at 0x34 (nor at the bq2560x address 0x6b), and there is no AGDSP firmware partition.
  The board has no speaker path; only Bluetooth or USB-host audio devices are possible.
* **A virtual card is enough for software that only needs a device.** The stock config leaves `SND_DRIVERS` off,
  which is what gates `snd-aloop` and `snd-dummy`; the fragment turns it on and builds both as modules.
  `snd-aloop` then gives card 0 with two PCM devices of eight substreams each - write to `hw:0,0` and the same
  audio comes back on `hw:0,1` - which is what a call bridge or a SIP gateway on the device needs to hand audio
  between two programs. Verified on the device: `/proc/asound/cards` shows `Loopback`, and `/dev/snd` has
  `controlC0`, `pcmC0D0c/p` and `pcmC0D1c/p`. It carries no cellular voice by itself; that still needs the AGDSP
  path below.
* **The whole Unisoc audio stack now builds and loads on this kernel** - `kernel/build-audio.sh` produces 23
  modules from the realme `unisoc-5.4` kernel_modules tree, and all 23 insmod cleanly: the DSP loader
  (`sprd_audcp_boot`), `agdsp_access`, `audio_sipc`, `audio_mem`, the VBC v4 voice DAI
  (`snd-soc-sprd-vbc-v4`, `snd-soc-sprd-vbc-fe`), the UMP9620 codec, the PCM platform and the machine card.
  Nothing in the kernel config had to change: `CONFIG_SND_SOC`, `SND_SOC_COMPRESS` and `SND_SOC_TOPOLOGY` are
  already built in. The build's three pitfalls are written up in that script.
* The device tree is not the problem either, which was the expectation. `sound@0` is `status = "okay"` and
  carries `sprd-audio-card,name`, `,routing`, `,headset` and `sprd,syscon-agcp-ahb`; `audiocp_boot` has its
  full register set - `bootvector`, `bootaddress_sel`, `corereset`, `coreshutdown`, `sysreset`, `sysstatus`,
  `deepsleep`. The machine driver finds it: the log shows `vbc-rxpx-codec-sc27xx sound@0`, exactly the binding
  the community Android modules use.
* **What stops it is the DSP itself.** `sound@0` probes and defers for ever, because the DAI link cannot be
  parsed until the audio SIPC channel to the DSP exists, and that channel reports
  `[Audio:SMSG] ERR:aud_smsg_ch_open ipc ENODEV`. The DSP is not running, and it cannot be started here: this
  board's device tree has no `audio-mem`/`audiodsp-mem` reserved region (another UMS9620 device uses
  0xaf700000 3 MiB and 0xafa00000 6 MiB), and there is no AGDSP firmware partition on the device. The
  community Android flow supplies both - an image taken from a different device, written to
  `/sys/devices/platform/audiocp_boot/agdsp` between `stop` and `start`.
* **The gap is exactly one device tree property.** `audio-mem-mgr` on this board carries every Unisoc audio
  address there is - `sprd,cmdaddr`, `sprd,smsg-addr`, `sprd,shmaddr-dsp-vbc`, `sprd,offload-addr`,
  `sprd,ddr32-dma`, `sprd,iram-ap-base`, `sprd,iram-dsp-base` and a dozen more - and is missing only
  `memory-region`. `audio_mem` reads that property as two phandles (`of_parse_phandle(np, "memory-region", 0)`
  and `1`) pointing at reserved DDR; without them `audio_mem_alloc(MEM_AUDCP_DSPBIN)` has nothing to hand
  `sprd_audcp_boot`, so the image cannot be written and the DSP never starts. ZTE kept the whole audio
  description and removed the reservation, which is consistent with a board built without a speaker.
* There is no firmware file to look for, incidentally: `sprd_audcp_boot` has no `request_firmware()` at all.
  Userspace writes the image into the `agdsp` sysfs attribute in chunks (`agdsp_store` memcpys into
  `base_addr_virt`) between `stop` and `start`. Searching the F50's `super` for an `agdsp`-shaped filename
  finds only slog config (`agdsp.conf`) and dump-region names (`AGDSP_MEM`, `AGDSP_PCM`) - no image.
* **The memory map has a hole of exactly the right size in exactly the right place.** The F50 reserves up to
  `ae8fffff` (`ch_ddr`) and then nothing until `b0000000` (`logobuffer`), leaving about 23 MiB free. The
  addresses another UMS9620 device uses for audio - 0xaf700000 (3 MiB) and 0xafa00000 (6 MiB) - both fall in
  that hole, and the second ends precisely where `logobuffer` begins. That is a strong sign they are the right
  addresses for this SoC family rather than a guess.
* **The reservation works, and it unblocked the DSP.** `of-reserved-mem-add.patch` reserves the two ranges
  (`CONFIG_OF_RESERVED_MEM_ADD="0xaf700000,3M;0xafa00000,6M"`) and `audio-mem-fixed-region.patch` lets
  `audio_mem` be told where they are. Measured on the device after a reboot into that kernel:

      OF: fdt: Reserved memory: reserved 0x00000000af700000 size 0x0000000000300000 (reserved_mem_add)
      OF: fdt: Reserved memory: reserved 0x00000000afa00000 size 0x0000000000600000 (reserved_mem_add)
      [Audio:MEM] memory-region 1 from module parameters: 0xaf700000 size 0x300000
      [Audio:MEM] dsp_bin (addr, size): (0xaf700000, 0x300000)
      [Audio:SBLCK] audio_sblock_create: p_rxblks[6].addr 0xaf71d060
      [Audio:SMSG] aud_smsg_send: dst=1, channel=3

  The last two lines are the point: the audio SIPC channel that used to answer `ENODEV` now allocates its
  blocks inside the reserved region and sends to the DSP. `mu300-audio-dsp` loads the 23 drivers with the right
  parameters.
* The card now parses **57 of its 58 dai links**, where before it deferred at link 0 and never moved.
  `BE_VOICE_PCM_P` - the back end the SIP gateway needs - parses fine. It stops on the last one,
  `BE_FAST_P_SMART_AMP`, with `get dai name for 'codec' failed!(-517)`: that link wants the smart amplifier,
  which this board does not have (nothing answers at I2C 0x34, and the DT's own `sprd,spk-ext-pa-info` count
  fails with -22). Links whose `codec` phandle is simply missing already fall back to a dummy codec - the
  driver says so - but a codec that *defers* is treated as fatal, and `asoc_sprd_card_probe` gives up, so no
  card registers and nothing re-probes.
* `sprd-card-dummy-on-defer.patch` handles the smart amplifier: `dummy_on_defer=1` lets a codec that keeps
  deferring fall back to the dummy the way a missing one already does. It applies **only to the codec** -
  `args_count` is NULL exactly on the codec call, and handing the cpu dai a dummy instead of deferring kills
  the card at link 0 instead of 57, which is how that was found.
* The firmware exists and is 6 MiB, which settles which region is which: `l_agdsp_a.img` goes in
  `audiodsp-mem` at 0xafa00000, and `audio-mem` at 0xaf700000 3 MiB is the shared memory. The driver confirms
  it - `sprd_audcp_boot audiocp_boot: base_addr_phy = 0xafa00000, bin size = 0x600000`. There is no image in
  this repository and there cannot be: the project publishes no proprietary files, and unlike the Wi-Fi and
  modem firmware there is no copy on the device to take.
* **The card registers: `sprdphone-sc2730`, 19 PCM devices, `FE_ST_VOICE_PCM_P` at card 1 device 53.** That
  is the same card the community Android modules produce, and that endpoint is exactly what sipserver looks
  for. `mu300-audio-dsp load` does it in one command and it survives a reboot.
* **The last thing in the way was the DMA engine, and nothing says so.** `CONFIG_SPRD_DMA` is a module and
  nothing pulls it in, so `/sys/class/dma` is empty, `sprd-pcm-audio` defers for want of a channel, its
  component never registers, and `snd_soc_register_card` fails with `ASoC: failed to init link FE_NORMAL_AP01:
  -517` - a message that names a link and says nothing about DMA. Loading `virt-dma` and `sprd-dma` brings up
  two controllers with sixty channels, and `sprd-pcm-audio`, `sprd-pcm-iis` and `sprd-compr-audio` register
  behind them.
* The card's own probe runs before those components exist and **is not retried**: it returns 0 even when
  `snd_soc_register_card` deferred, so nothing re-probes it. Binding `sound@0` again by hand once everything
  is up is what completes it.
* `mu300-audio` brings the card up at boot on both systems - a procd `boot()` that backgrounds itself, because
  binding takes about half a minute of waiting on probes and busybox init does not spawn the consoles until
  sysinit returns. It runs `load` and never `start`, so nothing at boot can reach the reboot below.
* **The reboot below is no longer reproducible, and the explanation given for it does not hold.** Android's own
  module writes the firmware with `sound@0` *unbound* and binds afterwards; doing the same here did not reboot
  the device either, so "the card must be registered first" is not the rule it was written up as. Kept below as
  the record of what was actually measured at the time. What it is not is a reason to avoid `start`.
* **Starting the DSP reboots the device only when the card is not registered.** Measured both ways: with
  `sprdphone-sc2730` up, writing the firmware and the reset registers leaves the device running (uptime went
  from 972 s to 1225 s across the attempt); with the card missing - which is what happens before `sprd-dma` is
  loaded - the console shows an orderly CPU shutdown and `reboot: Restarting system` seconds later. It is a
  deliberate reboot from userspace, not a panic. Registering the card is what exercises `agdsp_access_enable`,
  so with no card the AGDSP power domain is never brought up and `start_store` writes `RESET_SEL`, `CORE_RESET`
  and `SYS_RESET` into a domain that is off. `mu300-audio-dsp start` now refuses unless the card is present.
  The register sequence itself was compared against the driver and the device tree and is not the problem:
  `reset_sel` 0x0ba8/0xffffffff, `corereset` 0x0b88/0x1, `sysreset` 0x0b98/0x400000, `bootprotect` 0x0078 with
  the 0x9620 magic, and the boot vector is written - "dsp reboot by DDR!" means the `dsp-reboot-mode` property
  is absent and the mode is **0**, which is the branch that sets the vector.
* **`status` is a struct, not a number**, which is why a working DSP looked like a failed one:
  `struct audcp_status { u32 core_status; u32 sys_status; u32 sleep_status; }`, and `sys_status` is 0 for
  "power up finished" and 7 for "power off". After the first firmware write and start it read
  `core=0 sys=0 sleep=6` - the DSP was up. Read it with `od -An -tu4 -N12`.
* **The start is once per boot, and that is all it needs to be.** From the cold state (`sys=7 sleep=0`) it
  works every time; re-running it on a DSP that has already been booted leaves `sys=7` with every step still
  reporting success. `mu300-audio` does it once at boot, after the card, which is the only ordering that is
  safe anyway.
* **`sys` flips between 0 and 7 on its own** - that is the DSP's power management, not a failure. Reading the
  status at an arbitrary moment says little; what says the path works is opening the endpoint:

      [ASoC: PCM ] sprd_pcm_preallocate_dma_ddr32_buffer alloc size = 0x20000
      [Audio:MEM] audio_mem_alloc mem_type=5 addr = 0xaf725000, size=0x20000
      [ASoC: PCM ] sprd_pcm_close FE_DAI_ID_VOICE_PCM_P Close Playback

  `/dev/snd/pcmC1D53p` opens and closes cleanly and takes its DMA buffer from the reserved region. What has
  not been done is a call carrying audio through it.
* **The card registers with every route switched off**, and that is the last thing in the way of a PCM. Opening
  one gives `aplay: Unable to install hw params`, which reads like a driver that cannot do 16-bit 48 kHz — it
  can; the real line is a few above it in dmesg:

      FE_NORMAL_AP01: ASoC: no backend DAIs enabled for FE_NORMAL_AP01

  The DPCM front ends are joined to their back ends by ~70 `S_..._SWITCH` mixer controls, all off at probe
  (`S_NORMAL_AP01_P_CODEC SWITCH`, `S_VOICE_PCM_P SWITCH`, `S_VOICE_P_CODEC SWITCH`, …). Android's HAL sets
  them from its own configuration and there is nothing to inherit here. `mu300-audio-dsp routes` sets the ones
  this board can use; with the route on, `hw_params` installs and `BE_DAI_ID_NORMAL_AP01_CODEC` comes up.
* **An idle AGDSP reads exactly like one that never started.** The power domain is only up while something is
  using it, so `sys_status` is 7 whenever no PCM is open - and `mu300-audio-dsp start` used to check it one
  second after the firmware write and report "the DSP did not come up" over a load that had gone fine.
* **Powered is not running, and confusing the two cost an evening.** Opening a PCM produces

      [sprd-aud-agdsp] agdsp_access_enable, ap_access_ena_reg (wake up dsp) val = 0x20
      [sprd-aud-agdsp] agdsp_access_enable, ap_access_ena_reg (wake up done) val = 0x20

  with no `wait agdsp power up timeout`, and `status` then reads `core=0 sys=0`. On its own that only says the
  power domain came up, which `agdsp_access_enable()` does through the PMU whether or not the core has anything
  to execute. It is not a test of the firmware.
* **`/dev/audio_dsp_log` is not that test either, and believing it was cost an evening and a wrong writeup.**
  It returns nothing (`sblock_receive wait interrupted`, `dsp_log_read: failed to receive block`) on a DSP that
  is demonstrably running: this firmware simply does not log. "The log is silent, so the core is dead" was
  stated here as a measurement and it was an inference, from one negative signal.
* **The test that does settle it is `aud_send_cmd`'s own trace**, because its exit line is only reachable when
  the DSP replied - an unanswered command retries four times and then leaves through `failed to get command`,
  never printing it (`audio-sipc.c` around line 700). What the kernel actually logs here is

      [Audio:SIPC] aud_send_cmd out,cmd =5 id:0 ret-value:0,repeat_count=1

  `repeat_count=1` is a reply on the first attempt. **The AGDSP is running and answering.** `mu300-audio-dsp`
  reports power-up and liveness separately, and uses this for the second.
* **Android does not get further than this either**, which is worth knowing before spending a week on it. Its
  AudioCP times out too - from `f50_bluetooth_microphone_experimental`'s `service.sh`:

      # AudioCP still times out on F50 even with the donor memory layout. Keep the
      # probe manual so a failed 104-second codec loop cannot stall every boot.

  and the Whale HAL module's README lists, as explicitly outside what it achieves: cellular call routing
  through the F50's own earpiece, speaker and microphone, and **SIP/WebSocket apps bridging cellular RX/TX
  through `AudioRecord`/`AudioTrack`** - which is exactly the thing a SIP gateway needs. What does work there
  is media audio, system sounds, and cellular calls over a **Bluetooth headset's SCO link**, which does not go
  through the AGDSP at all. `S_VOICE_P_BT` and `S_VOICE_C_BT` exist in the mixer, so that route is reachable
  from here too, and BlueZ already runs on this device (section 25).
* **Every register the AP is supposed to write is written correctly**, read back from the silicon with
  `tools/mu300-peek` (this kernel has `# CONFIG_DEVMEM is not set`, so there is no `/dev/mem` and a small
  module is the only way to look). The two syscons are `/soc/syscon@64900000` (phandle 2) and
  `@64910000` (phandle 4), both `sprd,ums9620-glbregs`, and after `start`:

  | | address | read back | |
  |---|---|---|---|
  | bootprotect | `0x64900078` | `0x80009620` | the 0x9620 magic, unlocked |
  | bootvector | `0x64900140` | `0x57d00040` | `(0xafa00000 + 0x80) >> 1`, exactly right |
  | bootaddress_sel | `0x64900144` | `0x00000001` | set |
  | sysshutdown / coreshutdown | `0x649103d0` / `0x3d4` | bit 25 clear | force-shutdown released |
  | corereset / sysreset / reset_sel | `0x64910b88` / `0xb98` / `0xba8` | all 0 | resets released |

  And the firmware really is in DDR: peeking `0xafa00000` shows `SharkL5_AUDCP_20…` where the file has it.
* **Look at the right shared memory.** `0xaf700000` is `sprd,ddr32-dma`, a DMA buffer, and it holds only the
  AP's own ring descriptors - staring at it and concluding "the core writes nothing" was another wrong
  inference. The AP↔DSP mailbox is elsewhere, and the F50's own `/audio-mem-mgr` node gives every address:

      sprd,ddr32-dma        0xaf700000 + 0x200000      sprd,cmdaddr          0xaf980000 + 0x400
      sprd,ddr32-dspmemdump 0xaf900000 + 0x80000       sprd,smsg-addr        0xaf980400 + 0xa10
      sprd,iram-ap-base     0x56800000                 sprd,shmaddr-dsp-vbc  0xaf981210 + 0x1400

  `start` zeroes those areas (`sprd_audcp_memset_communication_area`), and they fill in again once the domain
  powers: the ring header returns at `0xaf980400` with `0x07` and `0x01` appearing after it. That node also
  settles the naming scare for good - its own `compatible` is `unisoc,audio-mem-sharkl5`, on a board whose
  syscons are `sprd,ums9620-glbregs`. SharkL5 is Unisoc's lineage label here, not a different chip.
* **The profiles load from `/lib/firmware`, and `tools/vbc-profile` builds them.** Writing 1 to
  `Audio Structure Profile Update` / `DSP VBC Profile Update` / `CVS Profile Update` gives
  `vbc_profile_loading, return 0` for blobs converted from the vendor XML, and writing a mode to the matching
  `… Profile Select` then applies it (`vbc_profile_try_apply, now_mode[0]=0`) and sends the DSP a 620-byte
  parameter payload it acknowledges. The one thing about the XML that is not guessable: **`id` is an offset
  into the whole mode array, not into the mode it appears in** - mode 1's first field is at `struct_size`,
  mode 2's at twice that. Reading it as per-mode puts every field but mode 0's out of range, and the converter
  checks the two readings against each other (`byte_off // len_mode` against the element's own `mode=`) so the
  mistake cannot come back silently.
* **`[MCDT] agcp mcdt clocl not available` means what it says: MCDT is switched off.** It is easy to dismiss,
  because it is logged during teardown, after `agdsp_access_disable()` has dropped the power domain - which is
  where it was first seen, and it was written off here as an artifact of that. It is not. `MODULE_EB0_STS` at
  `0x64900000` (the AGCP AHB syscon, phandle 2) read `0x2063e2d1`, and `BIT_MCDT_EN` is `BIT(12)`:

      0x2063e2d1  ->  bits 15..12 = 0xe = 1110  ->  bit 12 clear

  `check_agcp_mcdt_clock()` therefore returned false and **every** MCDT register access was skipped, setup
  included - `mcdt_reg_read`, `mcdt_reg_raw_write` and `mcdt_reg_update` each return early without touching the
  hardware. `mcdt_dac_dma_enable … mcdt_dma_ap_channel=1` still prints, which is what makes it look healthy.
  Nothing in the audio drivers ever writes that bit; they only read it. Setting it (bit 12 at `0x64900000`,
  while the AGDSP domain is powered, since the register lives inside it) silences the errors, and it persists.
  `AUD_EB_V2` (21), `AUDIF_CKG_AUTO_EN_V2` (22) and `VBC_EB_V2` (15) were already set.
  * This matters for the **voice** path, which is the one that runs through MCDT. Normal playback does not: its
    trace has no MCDT lines at all and goes through `AP01_PLY_FIFO` in VBC instead, so the MCDT bit is not what
    stalls media audio.
* **The profiles are a *call* structure, not a media one**, which is worth knowing before spending time on
  media playback. `audio_structure.xml`'s modes are Handset, Handsfree, Headset4P/3P, BTHS, BTHSNREC,
  TypeC_Digital, HighVolume and Hac, each with NB1/NB2/WB1/WB2/SWB1/FB1/VOIP1 (modes 0-62), plus four
  Loopback modes (63-66). There is no media mode at all.
* **`param_id` in the select value is load-bearing.** The value is `(mode << 24) | (param_id << 16) | dsp_case`,
  and with `param_id` 0 the apply does nothing visible. With `0x5e` - which is what a working device of this
  family carries in both selects - the driver copies the mode into the DSP's shared memory:

      [Audio:SIPC] cmd =11 sharemem_info.id=…, phy_iram_addr=0xaf981210, size=0x6c4

  and `0xaf981210` is `sprd,shmaddr-dsp-vbc` from the device tree. `mu300-audio-dsp profiles [MODE]` does the
  whole sequence.
* **A working reference exists and is worth borrowing from.** A ZTE MU5358 (ums9632, a later VBC generation)
  registers the same `sprdphone-sc2730` card and does carry call audio. Diffing `tinymix` on it between idle
  and an active call shows exactly 18 controls move, and they are all routing and output: `DSP_VOICE_PLAY`,
  every input of the `VBC_DA0_CODEC` mixer at once (VOICE, FAST, MM, OFFLOAD, LOOP, VOIP, AP23, FM),
  `agdsp_access_en`, and the codec's own `AO Mixer AOL/AOR`, `DA AOR`, `EAR_AOL Mixer DACAOL`, `Earpiece
  Function` and `Speaker Function`. Its names belong to a newer VBC, but the shape carried over: turning on
  *every* `S_*_CODEC SWITCH` here, not just the scene's own, plus that codec tree and `agdsp_access_en`, was
  tried and changed nothing.
  * Neither the F50's own Android nor a ZTE U30 Air (the same ums9620, and the kernel this project builds
    against) has any audio at all - no card, no audio modules, no reserved memory, and the same
    `audio-mem-mgr` node with no `memory-region`. So within the UMS9620 hotspots there is no working example
    to copy; the MU5358 is a different chip.
  * The U30 Air is still useful: `/odm/etc/audio_params/sprd/` on it holds the **native** UMS9620 parameter
    XMLs (`audio_structure`, `dsp_vbc`, `cvs`, `dsp_smartamp` and more), which are a better source for
    `tools/vbc-profile` than the community package's donor copies from another device.
* **Where it actually stops** - measured from `/proc/asound/card1/pcm0p/sub0/status` during a playback attempt:

      state: RUNNING   hw_ptr: 160   appl_ptr: 24160   avail: 0      (unchanged from t=2s to t=10s)

  The DMA advances **once**, by 160 frames, and then freezes with the application blocked on a full buffer,
  until ALSA gives up and `aplay` reports `write error: I/O error`. 160 is exactly the `burst:160` the driver
  programs, and `/proc/interrupts` shows both `sprd_dma` lines at zero throughout: the DMA does one burst and
  then waits for a request from the VBC FIFO that never comes.
  * **The VBC registers say the AP side did its job.** Read during a stalled stream (safe only then - see the
    warning above), at `0x56510020`:

        AUD_EN 0x00000300   AUD_DMA_EN 0x00000003   PLY_FIFO0_STS 0x000024a1   PLY_FIFO1_STS 0x000024a1
        AUD_INT_EN 0x00000004   AUD_INT_STS 0x00000010

    The playback FIFO is enabled, both DMA channels are on, and the FIFO's low nine bits read 0xa1 = **161
    words sitting in it, unchanging** - which matches hw_ptr's 160 frames exactly. The DMA filled the FIFO
    once; nothing is taking data out of it. In this design that consumer is the DSP.
  * Parameters and modes are exhausted as an explanation. Both parameter sets were tried with the working
    `param_id` 0x5e - the community's donor set from a ZTE Voyage 41S (which is the same T760/UMS9620 as this
    board, and a phone with real audio) and the U30 Air's native set - across modes 0, 2, 7, 9, 28 and the
    Loopback mode 63. Every one stalls identically. The two sets are equivalent where it would matter: their
    `dsp_vbc` mode 7 is byte-identical, and `audio_structure` differs only in tuning (EQ curves, gains, an AEC
    switch), so neither is a stripped-down build.
  * Everything around it checks out. The trigger path runs in full - `ap_vbc_fifo_clear`,
    `ap_vbc_fifo_enable enable=1`, `ap_vbc_aud_dma_chn_en enable=1`, then `aud_send_cmd_no_wait cmd: 0x7
    value2: 0x1` to start the DSP. The codec end is powered: `DAC: On`, `CLK_DAC: On`, `DIG_CLK_DAC_BUF: On`,
    `CP_LDO: On` in `/sys/kernel/debug/asoc/sprdphone-sc2730/sc27xx-audio-codec/dapm/`. The SMSG interrupt
    fires and the DSP answers. Enabling dynamic debug on `snd_soc_sprd_vbc_v4`, `mcdt_hw_r2p0`,
    `sprd_dmaengine_pcm` and `audio_sipc` (`echo 'module <m> +p' > /sys/kernel/debug/dynamic_debug/control`)
    is what makes all of this visible, and is the first thing to do when picking this up.
  * Tried and made no difference: every `VBC_SYSTEM_DEV_CHANGE` / `VBC_CUSTM_DEV_CHANGE` device type,
    `VBC_DL_MUTE`/`VBC_UL_MUTE` off, `VBC_VOLUME`, the whole codec output tree (`HPL/HPR Mixer DAC… Switch`,
    `AO Mixer`, `EAR_…`, the `* Function` and `* Mute` controls), `Virt Output Switch` and `agdsp_access_en`.
    The last two are worth knowing about anyway: they appear in the Whale HAL's own string table, along with
    `VBC_SRC_BT_DAC`/`ADC`, `SYS_IIS1`/`SYS_IIS3`, `Inter PA Config` and `Codec Digital Access Disable` -
    intersecting `amixer controls` with `strings` on `audio.primary.whale.so` is a cheap way to see the whole
    vocabulary the vendor userspace uses.
  * **An AGDSP image has its addresses compiled in, and boards do not agree on them.** This is why the Moto
    G35 image takes the device down: its own device tree, pulled out of `vendor_boot.img` in the same
    firmware, puts `audio-mem` at `0xaf600000` and a **7 MiB** DSP region at `0xaf900000`, with `cmdaddr`
    `0xaf880000` and `shmaddr-dsp-vbc` `0xaf881210` - a megabyte below this board's `0xaf700000` /
    `0xafa00000` / `0xaf980000`. Written to the wrong base it runs into memory that belongs to something
    else. The same fact read the other way is reassuring: the donor image answers SIPC commands at
    `0xaf980000`, so it *is* built for this board's layout and is in the right place.
    * `CONFIG_OF_RESERVED_MEM_ADD` now reserves `0xaf600000,3M;0xaf900000,7M`, which is contiguous to
      `0xb0000000` and covers this board's layout as well, so one boot image can host either.
      `kernel/patches/audio-mem-shm-shift.patch` adds `shm_shift` for the addresses that are absolute in the
      device tree rather than derived from the region.
    * **The Moto image does not come up here, at its own addresses either.** With
      `ddr32_base=0xaf600000 dspbin_base=0xaf900000 dspbin_size=0x700000 shm_shift=0x100000` the driver
      reports `ldinfo 0xaf900000 / 7340032` and `cmdaddr is now 0xaf880000`, matching that board's device
      tree, and the device stays up instead of dying as it does at the wrong base - and the DSP still never
      answers (`failed to get command`, `audio_sblock_thread: fail to send SMSG_CMD_SBLOCK_INIT to dsp`).
      The donor image answers on the first try at this board's own addresses. Whatever the Moto image wants
      beyond a matching memory map, it is not the addresses.
    * Worth knowing if you pick that up: `audio_mem` has **three** DT parsers (whale2, sharkl2, sharkl5) and
      this board's node is `compatible = "unisoc,audio-mem-sharkl5"`. A change made in the whale2 one compiles,
      loads, accepts its module parameter and does nothing, which is a quiet way to lose an experiment.
    * Also: the boot service loads `audio_mem` at startup and the module is `[permanent]`, so trying a
      different layout means `/etc/init.d/mu300-audio disable`, reboot, load by hand, and remember to
      re-enable it afterwards.
  * **Three things took the board down** hard enough that slot B lost its boot trial and LK rolled back to
    Android. Recovery is `ANDROID_SERIAL=<the MU300> boot/android-boot-linux.sh <the image on boot_b>`, which
    verifies `boot_b` and rewrites only the 32-byte block in `misc`. The three: writing the Moto G35 AGDSP
    image; opening a **capture** stream (`arecord -D hw:1,0` with `S_NORMAL_AP01_C_CODEC` on, which died
    before its first log line); and **reading AGCP-domain MMIO while the domain was powered down**. That last
    one is the trap worth remembering - `0x56510000` (VBC), MCDT and the AGCP AHB syscon all hang the bus if
    touched with the AGDSP asleep, so a "harmless read-only peek" is not harmless. Hold a PCM open first.
* How the profile mechanism works, since the above depends on it: the parameters come from the Whale HAL on
  Android, and `vbc_profile_loading()` fetches them with `request_firmware()` under the bare names `audio_structure`,
  `dsp_vbc`, `cvs` and `dsp_smartamp`, and checks a magic - so the kernel will load them from `/lib/firmware`
  with no HAL involved, and writing 1 to the matching `… Profile Update` mixer control is what triggers it:

      struct vbc_fw_header { char magic[16]; u32 num_mode; u32 len_mode; };   /* "audio_profile" */
      /* then num_mode * len_mode bytes of packed mode data */

  The community's donor-params module ships the same three as XML for `/odm/etc/audio_params/sprd`, and those
  carry exactly what the header needs - `<dsp_vbc … num_mode="0x48" struct_size="0x6c4">` and then every field
  with its `offset`, `bits` and `val`. `tools/vbc-profile` converts one to the other.
* The F50 has no `l_agdsp` partition to take an image from (the list has `ch_sys`, `pm_sys`, `nr_modem`,
  `nr_phy` and nothing for audio). A genuine Qogirn6pro image does exist and is easy to fetch: Motorola's
  Moto G35 (UMS9620, codename *manila*) ships `QogirN6Pro_AUDCP_DSP_lit_dm.bin`, 6 MiB, in its official
  firmware - and its header reads `SharkL5_AUDCP_2024Y_VER_5003`, same lineage label as the donor's 2022 build,
  with byte-identical entry code at `+0x80`. Loading it in place of the donor took the board down hard enough
  that slot B lost its trial and LK rolled back to Android, so it is not a drop-in; the donor image is the one
  that runs.
* Things that are *not* the cause, each checked: the firmware is byte-identical to the image Android uses
  (sha256 `378ceea7…b937`, and the module verifies that same hash); the memory is genuinely reserved
  (`/sys/kernel/debug/memblock/reserved` shows `0xaf700000..0xafffffff`, 3 MiB + 6 MiB); `ldinfo` agrees at
  `0xafa00000` size `0x600000`, which is the image exactly, so `agdsp_store()` copies all of it; and the load
  order does not matter - Android writes the firmware with `sound@0` **unbound** and binds afterwards, which
  was tried here and neither rebooted nor helped. The image's header reads `SharkL5_AUDCP_2022Y_VER_2548` /
  `AUDCP.SharkL6` although this SoC is Qogirn6pro, which looks damning and is a red herring: it is the same
  image Android boots media audio with.
* `agdsp_store()` clamps every write to `ldinfo`'s size minus what it has already taken, so a firmware bigger
  than the reserved region is truncated silently and `dd` still reports success. Read the size back from
  `$BOOT/ldinfo` - `char name[32]; u32 load_phy_addr; u32 size`, so
  `od -An -tu4 -j32 -N8`. On this board it is 0xafa00000 and 6291456 bytes, which is the image exactly.
* Also worth knowing: the community Android module's `l_agdsp_a` symlink under `/dev/block/by-name` is for the
  Whale audio HAL, not the kernel - `sprd_audcp_boot` has no `request_firmware()` and no path of its own.
* A2DP over BlueZ needs none of this.

### 24b. A second board, from a clean install: where the stall actually is
Everything in 24 was measured on one hand-built unit. On 2026-09-23 the audio stack was put on a second F50 from a
clean `install.sh` (the audio kernel, its modules, the donor firmware, and profiles converted from the U30 Air's
native XML), and the stall was taken apart further. Audio still does not move; what follows is what is now known.

**Two traps on the way in, both in how the modules get loaded.**
* Running `depmod -a` with the audio modules in `/lib/modules/<release>/audio` makes them visible to `modprobe`, and
  from then on udev and the kernel's own `request_module()` load them first - without parameters. `audio_mem`
  comes up with no memory region (`memory-region 1 unavailable!(-19)`), `snd_soc_sprd_card` without
  `dummy_on_defer`, both are `[permanent]`, and the card never registers. `mu300-audio-dsp` does pass both
  parameters; it just never gets to. `/etc/modprobe.d/mu300-audio.conf` now keeps `modprobe` away from all 23
  (`install <name> /bin/false`); `mu300-audio-dsp` uses `insmod` and is not affected.
* Closing a voice stream can panic the kernel: `Asynchronous SError Interrupt` in `regmap_read <-
  check_agcp_mcdt_clock <- mcdt_dac_dma_disable <- fe_hw_free`. The MCDT driver reads an AGCP register on the way
  down, after the AGDSP domain has already dropped - the same bus hang as in 24, from inside the driver. Holding
  the domain with the `agdsp_access_en` mixer control for the length of a call avoids it; `mu300-voice` does.

**Reading the hardware without hanging it.**
* `/proc/asound/card1/vbc` dumps the DSP-side VBC registers (the DSP copies them to shared memory on request) and
  the AP-side ones with the domain held. Safe at any time, and the best single view of the stall.
* The codec's analog half and its AUDIF interface live in the PMIC and are always powered. Their registers are in
  `/sys/kernel/debug/regmap/spi4.0/registers` at `codec register - 0x3000 + 0x1000` (`CODEC_REG`, codec offset
  0x1000): `AUD_CFGA_CLK_EN` is PMIC 0x100, `AUD_CFGA_DAC_FIFO_STS` 0x144, the analog clocks 0x1068. Reading
  the whole file takes minutes over ADI; it seeks, though - lines are 15 bytes and registers 4 apart, so
  `dd bs=15 skip=$((reg / 4)) count=1` reads one.
* The digital codec (`unisoc,audio-codec-dig-agcp`, 0x56360000) and the AGCP gates at 0x56200000 are inside the
  domain: read them only while a PCM holds it, and check the stream is still RUNNING just before the read.

**What the stall is not** - each measured with a stream stalled at `hw_ptr` 160:
* not the DSP powering down: during the stall the domain is up (`0x64910544` reads 0, idle it reads 0x70700), and
  the auto-shutdown bit in `coreshutdown` is cleared by the running side itself;
* not the IIS being routed to USB (`VBC_IIS_INF_SYS_SEL` defaults to `vbc_iis_to_aon_usb`; `vbc_iis_to_pad` changes
  nothing), nor the codec being off: with the vendor route below, DAPM and the PMIC agree it is fully on;
* not the audio PLL: nothing requests it (`AUDPLL_REL_CFG` 0x64910a48 reads 0; bit 5 is `AUDIO_SEL`), but forcing
  it on (`FRC_ON`) locks it (`lock_done` at 0x64320068 bit 17) and changes nothing;
* not the AGCP clock gates (`vbc-24m`, `tmr-26m`, `dma-cp`, `iis0-2`, `src48k` are all on during a stream).

**The vendor route, from the U30 Air.** `/odm/etc/audio_route.xml` on the U30 Air (the same ums9620) says what the
HAL sets for a codec playback device: `ag_iis0_ext_sel_v2 = aud_4ad_iis0_da0` (AGCP IIS0 into the codec's DA0 -
this board had it at `pad_top`, i.e. out to pins with nothing on them), every `S_*_P_CODEC SWITCH`, 24-bit IIS
with `VBC_IIS_TX0_LRMOD_SEL = RIGHT_HIGH`, DAC0/DAC1 on IIS port 0, and the device's own mixers (`Speaker Function`
and the AO mixer). Applied in full, the codec powers up and clocks (PMIC 0x100 = 0x2, analog clocks on, DAC
enabled) - and its DAC FIFO stays empty with the write pointer at 0 (0x144 = 0x80): **nothing arrives over AUDIF
from the digital codec.** `AUDIF_EB` (0x56390000 bit 3) is only ever set by the VAD/ADC clock widget, and setting
it by hand, with its pad clock, does not change that either.

**With VBC as IIS master, the pipeline moves - slowly.** `VBC_IIS_MASTER_ENALBE = enable` with `VBC_IIS_MST_SEL_0_TYPE
= VBC_MASTER_INTERNAL` is the first setting in all of this that gets past `hw_ptr` 160: about 23000 frames go at
once, then 80-120 frames/s, i.e. one 160-frame burst about every two seconds. The DSP-side dump shows why it is
not the DA side any more: the IIS async FIFO moves (0xf88) and DAC0's FIFO reads empty (0xe7c) - DA is starved,
not stuck. What is missing is the DSP being told the AP FIFO has data: `AUD_INT_EN` (0x44) has no play-FIFO
interrupt enabled and the DSP-side DMA enable (0xeb0) is 0; neither is written by any AP driver - the firmware
sets them, and here it does not, so it falls back to polling. With the codec as master (VBC slave), nothing moves.

**Calls.** The call scene is the hostless `FE_VOICE` (device 5), which Android's HAL starts with `pcm_start()`;
`tools/pcmhost` does the same and the scene goes RUNNING during a real call. `FE_VOICE_PCM_P` (what the far end
should hear) still stops after its first burst, with the scene running, with every `AT+SSAM` mode 0-8, and in
master mode. And the call itself **ends after about 20 seconds** - which, the owner reports, it also does on this
board under stock Android: VoLTE drops a call that sends no media, and the modem never gets uplink frames from the
DSP. That is the same symptom one layer down: the DSP runs, answers commands, and moves no audio in any scene.
The one route known to work on Android is a Bluetooth headset over SCO, where the BT controller clocks the IIS.

**The DSP-side registers are not AP-addressable.** The driver's `/proc/asound/<card>/vbc` dump reads DSP-side
registers (base `0x01700000` in the driver's numbering) through the DSP, by IPC (`SND_VBC_DSP_IO`). Reading the same
offset directly from the AP at `0x56510000 + 0xe7c` - outside the 1 KiB AP VBC window - hangs the bus: the board
drops off USB and the network. To change a DSP-side register, write `"<reg> <val>"` in hex to that proc file
instead (`vbc_proc_write` -> `dsp_vbc_reg_write`, e.g. `echo 1700eb0 1`); never map it from the AP.

## Bluetooth

### 25. SC2355 Bluetooth on BlueZ
* Transport: `sprdbt_tty` (realme `wcn/bluetooth/driver/tty-pcie`, built with `BSP_BOARD_UNISOC_WCN_SOCKET=pcie`) exposes
  an H4 tty `/dev/ttyBT0` over the WCN PCIe link and registers a `bluetooth` rfkill that powers the BT function.
  `btattach -B /dev/ttyBT0 -P h4` creates `hci0`.
* Vendor init (Android `libbt-sprd_suite`, Marlin3): before the stack starts, send `0xFCA0` with the 176-byte PSKey block
  from `bt_configure_pskey.ini` (BD address at bytes 20..25, little endian), `0xFCA2` with the 252-byte RF block from
  `bt_configure_rf.ini`, then `0xFCA1 00 00 01` (dual mode, enable). `tools/bt-init/mu300-bt-init.c` does this. Without the
  PSKey upload the controller reports a fixed placeholder address.
* The firmware advertises Hold Mode and Park State in its LMP features, but `Write Default Link Policy Settings` returns
  `Invalid HCI Command Parameters` for any value that includes them (0x0000/0x0001/0x0004/0x0005 accepted, 0x0007 rejected).
  The 5.4 kernel sets every advertised mode, so the init sequence aborts and `hciconfig hci0 up` fails with `EINVAL`.
  `kernel/patches/bluetooth-marlin3-link-policy.patch` requests only Role Switch and Sniff (Bluetooth is built in, so this
  needs the kernel rebuild).
* Android keeps the real BT address in `/data/vendor/bluetooth/btmac.txt` on encrypted `/data`; Linux uses
  `BDADDR=` from `/etc/mu300/bluetooth.conf` or a stable locally administered address derived from `machine-id`.
* Verified: `bluetoothd` powers the adapter and LE/BR-EDR scanning lists nearby devices.
* Rebuilding with a modified tree appends `-dirty` to the kernel release and breaks module loading; `.scmversion` with
  `-gb50db5b6224c` in the source tree keeps the release string stable.

## Mainline 6.18 as a daily kernel

Everything here was measured on the test device (64 GB F50, Vodafone TR, 5G NSA) with 6.18.54 and the
upstream/ modules, running the release's Ubuntu and OpenWrt images.

**Update 2026-10-07:** the port has been on 6.18.55 since PR #26 (`KV` in `upstream/build.sh`), and it also builds
against 7.2.9, shipped as `mu300-kernel-7.2.tar.gz`. Sections 31e onwards were mostly measured on 6.18.55 and 7.2.9.

### 31. Ubuntu on 6.18, and what it takes
Ubuntu had never been booted on the mainline kernel. With the kernel bundle from `upstream/make-bundle.sh`,
installed by `mu300-update` (modules into every system, the boot image built on the device), it boots in under
45 s and runs the hotspot, USB NCM, Bluetooth, the modem with SMS, the VPN and mobile data - the downlink
included, which had never been shown on 6.18: the delegate's handshake completes and a 20 MB download goes
through.

Speed at one spot, alternating kernels within minutes (signal -99 to -107 dBm, so downloads say little):
upload is about twice as fast on 6.18 (0.29-0.34 MB/s against 5.4's 0.167 MB/s). 5.4 never exceeded exactly
166 650 B/s in any upload, with or without the VPN - a ceiling that constant is the device's, not the network's.

### 31a. Wi-Fi RX: sync_for_device stopped invalidating (hang under load)
A client uploading over Wi-Fi hung the board within 40 s. The Marlin3 driver waits for the device to finish an
RX buffer by reading a flag in it and "refreshed" the buffer between retries with `dma_sync_single_for_device()`.
On arm64 that call invalidated `DMA_FROM_DEVICE` buffers until 5.19 and cleans them since, so the CPU kept
reading a stale line: every check failed (`hw still writing`, 369 times in the hung boot's log), the checksum
taken from the same stale descriptor was wrong (`hw csum failure`), and each failure went to the 115200 baud
console at loglevel 8 from the RX path. `dma_sync_single_for_cpu()` is the call for reading what the device
wrote. After the fix: 3 x 15 MB uploads and a 30 MB download over Wi-Fi, no error. The IPA driver syncs the right
way round already.

Consequence for 5.4: IPv6 TCP and UDP from Wi-Fi clients get through on 6.18 (SSH and DNS over IPv6 measured),
but not on 5.4, whose Wi-Fi driver carries `wlan_combo-rx-software-checksum.patch` - the only difference in that
path. The patch's "hw csum failure" may well have had this stale read as its cause too.

### 31b. The modem units' ordering cycle (both kernels)
`cp_diskserver` was ordered before `mu300-vendor`, which runs before `sysinit.target`, while its default
dependencies put it after `sysinit.target`: a cycle, which systemd broke by dropping `cp_diskserver` and
`refnotify` from the boot transaction (on 5.4 it happened to break it elsewhere). On 6.18 it showed because the
modem's nodes appear about 18 s in, after the units' `ConditionPathExists=/dev/modem` had been evaluated.
`cp_diskserver` has no default dependencies now, the conditions look for the driver
(`/sys/module/sprd_modem_loader`), and `mu300-vendor` waits for the node.

### 31c. A context that comes back with a new address (both kernels)
After the radio or the network dropped the bearer, the LTE modem attaches again by itself and the default context
is active again - with a new address, while `sipa_eth0` keeps the old one: it sends and never receives. The
watchdog only asked whether the context was active and the interface had an address. It compares the address
(`AT+CGPADDR`) now. `AT+CFUN=4` from scratch: radio back on, new address noticed, internet back after 72 s.

### 31d. Evidence of a failed boot
Two boots in about twenty (one Ubuntu, one OpenWrt) died shortly after `switch_root` - the OpenWrt one between 11
and 21 s by the early recorder - and left nothing. Three gaps, all closed:
* The 6.18 config had no lockup detectors, so `softlockup_panic`/`hardlockup_panic` from `boot/init` had nothing
  behind them. Soft and (buddy) hard lockup detectors now panic; hung tasks are only reported.
* `mu300-early-recorder` was never enabled in the Ubuntu image; it is, and writes every 2 s for the first 90 s.
* pstore works: `sysrq-c` -> panic -> Linux again a minute later, with the panic in
  `/var/lib/systemd/pstore/dmesg-ramoops-0`. `systemd-pstore` moves the records out of `/sys/fs/pstore` at boot,
  which is why that directory looked empty after the failures.
Also: the Wi-Fi driver's per-frame traces pushed a boot's messages out of the ring buffer within a minute (now
`pr_debug`, and `log_buf_len=4M`), and systemd's 10 min reboot watchdog was rejected by the UMP9620 PMIC watchdog
(maximum 300 s), so a hang during reboot was not caught (`RebootWatchdogSec=2min`).

### 31e. sipa-set-rps: a thread that never started
The vendor comments the thread's wake-up out ("zsw changed", to keep `rps_cpus` fixed) but still creates it, so it
sat in its pre-start state - uninterruptible - for good: one more on the load average, and on 6.18 a hung-task
report every two minutes. It is not created any more.

`sipa-free-N` and `sipa-fill-recv-N` had the same pre-start sleep for a different reason: they are created with
`kthread_create()` and first woken in the IPA's runtime-PM resume, which never comes on a device without a SIM. On
the second F50 (no SIM, Ubuntu) under release v2026.10.08's 6.18.54: both in D state, the 1-minute load 2.34 at
5 minutes of uptime, two "blocked for more than 120 seconds" reports at 246 s. They now start at once and wait,
interruptibly, for a flag set where the vendor woke them (6.18.55 #7): both in S state, load 0.27 / 0.32 / 0.19 at
11 minutes, 0 reports. F50 #1 (SIM) on the same kernel: mobile data and its VPN up (exit address shown, GitHub
reached), both threads running. The vendor 5.4 kernel has the same threads in D state (plus `sipa-set-rps`,
`slog-0-0` and the Wi-Fi TX thread: load about 5.4 at idle on the second F50); 5.4 reports no hung tasks, and it was
left as it is.

### 31f. The delegate on OpenWrt: -EINPROGRESS taken for a failure
On OpenWrt the downlink died on some boots and the board crashed on others, and the recorder and pstore (31d)
caught both crashes in the delegate's connection thread `dele-4-5`: a call through NULL (`pc : 0x0`,
`lr : conn_thread+0x188 [sipa_dele]`) and a soft lockup, 22 s in `console_flush_all`. The probe log explains
them:

    sipa_rm: driver CB returned with -115
    sipa_rm: SIPA_RM_RES_PROD_CP state changed 1->3
    sipa_rm: SIPA_RM_RES_PROD_CP does not exist
    sipa_delegate soc:ipa-apb:sipa-dele: cp_delegator_init failed: -22

OpenWrt brings the WAN up before the delegate is loaded (at ~80 s), so `CONS_WWAN_UL` is already granted when
`sipa_delegator_start()` makes it depend on `PROD_CP`. That starts requesting the producer and returns
`-EINPROGRESS` - which the vendor code took for a failure: it deleted `PROD_CP` again, `cp_delegator_init()`
ignored that result, failed on the next dependency ("does not exist"), and the failed probe freed the delegator
under the connection thread it had already started. On Ubuntu the delegate is loaded before there is traffic,
the call returns 0, and none of this happens. Fixed in the module: `-EINPROGRESS` is success, the result of
`sipa_delegator_start()` is checked, the Wi-Fi offload dependencies (unused here) are warnings, and the delegator
is no longer devm-allocated. The 5.4 kernel has the same driver in its own tree and the same crash on OpenWrt ("Kernel
panic - not syncing: CFI failure (target: 0x0)" in `dele-4-5`, caught while testing v2026.09.29); it gets the same
fix as `kernel/patches/sipa-delegate-einprogress.patch`.

### 31g. Three warnings on every boot, three vendor bugs
6.18 printed three `WARNING:`s on every boot; each one is a bug in the vendor drivers:
* `kernel/softirq.c:429 __local_bh_enable_ip` from `sc2355_free_cmd_buf`: the Wi-Fi command list's `complock` is
  taken with `spin_lock_bh` in the PCIe tx-complete interrupt, and the same lock is taken with only bottom halves off
  in process context - that interrupt arriving on the CPU holding it spins forever. Both places now use
  `spin_lock_irqsave`.
* `tty_port_link_device` from `mtty_probe` (`sprdbt_tty`): the tty driver is allocated with one line and a second,
  never used port is linked at index 1 - past the end of `driver->ports[]`. 5.4 has no check there and writes it;
  6.18 refuses with the warning. The second port is no longer linked.
* `dev_addr_check`, "sipa_eth0: Incorrect netdev->dev_addr": `sipa_eth`, `seth` and `sipa_usb` wrote their random
  MAC straight into `netdev->dev_addr`; `eth_hw_addr_random()` sets it through `dev_addr_set()`.

A look at `dmesg` itself (Ubuntu's journal misses the first seconds of the kernel log) found two more:
* `device_create_file` / `sysfs_create_file_ns`, "Attribute base_addr: read permission without 'show'", four times
  per boot: `sipx`, `sblock`, `sbuf`, `smem`, `smsg` and the mailbox each created a `base_addr` attribute with
  neither show nor store, on an embedded `platform_device` that is never registered - it could never be read. Gone.
* `dev_addr_check` for `sipa_dummy0`: the same direct `dev_addr` write as above; now `eth_hw_addr_set()`.

And the idle load average of 2.0 was two kernel threads parked in D state for good: `slog-0-0` polls every 2 s for
the modem log to be switched on with an uninterruptible `msleep()`, and the Wi-Fi `SC2355_TX_THREAD` waits for work
with `wait_for_completion()`. They now sleep interruptibly and in `TASK_IDLE`; the idle load is about 0.4.

7.x adds one of its own: a workqueue has to say whether it is per-CPU or unbound (`WQ_PERCPU`, which 6.18 has
too, or `WQ_UNBOUND`), and `trusty` and six Mali queues said neither ("trusty-nop-wq is using neither WQ_PERCPU or
WQ_UNBOUND"). They say `WQ_PERCPU` now - what the kernel picked for them anyway.

The Wi-Fi lock and the Bluetooth port come from the same vendor sources as the 5.4 modules, so the 5.4 build
patches them as well (`kernel/patches/wlan_combo-tx-complock-irqsave.patch`, `sprdbt-tty-one-port.patch`); there
the second port really was written past the end of `ports[]`, since 5.4 does not check.

The 6.18 bundle also carries `modules.builtin` and `modules.builtin.modinfo` now: without them depmod warned and
`modprobe` of a built-in driver failed. Three boots after the fixes: no warnings, Wi-Fi AP, mobile data, Bluetooth
(24 devices in a scan) up.

### 31h. Power-off, and the command line's crutches
6.18 had only the PMIC restart (patch 0001): `poweroff` fell through to PSCI `SYSTEM_OFF`. The same patch now
registers a power-off handler that does what the vendor's `sc27xx-poweroff` does for the UMP9620 - clear
`LDO_XTL_EN` and `SLP_LDO_PD_EN` in `SLP_CTRL` (0x2248), then write 1 to `PWR_PD_HW` (0x2020). It cuts the power:
ramoops lives in RAM, and after `reboot` the next boot finds the old console there ("reboot: Restarting system"),
after `poweroff` it finds nothing. The F50 has no battery, so on a powered USB port the PMIC switches it on again
about a minute later; unplugged, it stays off.

The command line still carries four bring-up flags. Measured on the running system, what each one keeps:
* `clk_ignore_unused`: 315 of 551 clocks are on with no driver holding them (bus, config, DSP, camera, thermal,
  PWM clocks ...). This is where power could be saved - and where the risk is, because the modem, the Wi-Fi
  firmware and the vendor modules touch hardware behind some of them without the clock API. Not changed yet.
* `pd_ignore_unused`: nothing - the only generic power domain (`sipa-sys`) has active devices (USB, IPA).
* `regulator_ignore_unused`: one regulator, `LDO_VDDSIM0` - the SIM's supply, which the modem uses and no Linux
  driver claims. Without the flag the kernel would switch the SIM off. Required.
* `fw_devlink=permissive`: required. Without it (and `pd_ignore_unused`) the board booted but the USB gadget
  never came up - it waits for suppliers in the vendor device tree that no driver provides - and since Linux
  itself was fine, the boot counted as good and the board stayed in a Linux without USB until it was forced back
  to Android.

### 31i. A Wi-Fi card that is late at boot panicked the board
Rebooting OpenWrt on 5.4 again and again (testing v2026.09.29), one boot ended in "WCN BOOT: error: Waiting for
PCIe scan card timeout", `sprd_pcie_remove`, "Unable to handle kernel paging request at virtual address
ffffffffffffffe8" in `__wake_up_locked` from `complete()`, and a panic - back to Android. The SC2355 does not always
show up on the PCIe bus within the 5 s the vendor driver waits; the timeout then removes the half-probed card, and
`sprd_pcie_remove()` completes `remove_done`, which only `sprd_pcie_remove_card()` initialises - a completion that
was never set up. It is initialised before every scan now, `remove` checks for a probe that never set its data, and
a timed-out scan is tried once more before Wi-Fi and Bluetooth are given up. Both copies of the driver: the 5.4
tree (`kernel/patches/wcn-pcie-scan-timeout.patch`) and `upstream/modules/wcn_bsp`.

### 31j. SD host under mainline
The stock device tree of the F50 (read from `/proc/device-tree/soc/ap-ahb` under 6.18) describes three
`sprd,sdhci-r11` hosts, all `status = "okay"`:

| node | `sprd,name` | bus-width | properties |
|---|---|---|---|
| `sdio@22200000` | `sdio_emmc` | 8 | `non-removable`, `no-sd`, `no-sdio`, HS200/HS400/HS400ES |
| `sdio@22210000` | `sdio_sd` | 4 | `cd-gpios = <0x170 35 0>`, `no-mmc`, `no-sdio`, `sd-uhs-sdr50`, `sd-uhs-sdr104`, `vmmc-supply`, `vqmmc-supply`, `sd-detect-pol-syscon`, `sd-hotplug-{debounce-cn,debounce-en,protect-en,rmldo-en}-syscon` |
| `sdio@22220000` | `sdio_wifi` | 4 | `no-sd`, `no-mmc`, SDR50/SDR104 |

The mainline port used to let only the `non-removable` host probe, so the F50 showed `mmc0` alone with a card in
the slot. The gate now lets the eMMC and the `sdio_sd` host through; `sdio_wifi` stays unprobed (Wi-Fi is on PCIe).

`/proc/device-tree/aliases` (read under 6.18.55) has no `mmc` entries at all, only cooling devices, `eth*`, `i2c*`,
`serial*`, `spi*`, `v4-modem*` and a few others. The host numbers therefore come from the probe order, not from an
alias: `mmc0` is `22200000.sdio` (the eMMC) and `mmc1` is `22210000.sdio` (the slot), under 6.18 and 5.4 alike.
That the eMMC is `mmcblk0` is what init and the installers rely on when they look at `mmcblk[1-9]` for the card - which under mainline held only by luck (31l).

Phandle 0x170 is `gpio@2000c0`, `sprd,qogirn6pro-eic-sync`. Mainline's `sprd-eic` binds it, but as a chip of 24
lines (`gpiochip3: 24 GPIOs`), and the slot's card detect is line 35: the lookup fails, `mmc_of_parse()` returns
`-EPROBE_DEFER` at about 2.09 s, and the host would stay deferred. `mmc_of_parse()` requests the CD GPIO before it
reads the write protect GPIO, the bus mode properties (`sd-uhs-sdr104`, `no-sdio`, `no-mmc`, ...) and the power
sequence, so it returns before any of those. For that host alone the port therefore removes `cd-gpios` from the
node (`of_remove_property`), runs the parse again (now without a CD GPIO: -ENOENT, which it accepts) and sets
`MMC_CAP_NEEDS_POLL`; it logs "MU300: CD GPIO deferred, polling the card slot". `sdhci-sprd` has
`SDHCI_QUIRK_BROKEN_CARD_DETECTION`, so without a CD GPIO every poll that finds no card tries to start one.

The first version of this edit only masked the `-EPROBE_DEFER` and kept the half-done parse; the measurements of
that build (the card ran at 50 MHz "high speed", every poll tried SDIO, SD and MMC) are these, on the F50 with a
32 GB SDHC card (SL32G, manfid 0x000003), kernels built 2026-10-04:

- 6.18.55: `mmc0 mmc1`; `mmcblk1` type `SD`, 62333952 sectors (29.7 GiB); "new high speed SDHC card" at 2.61 s;
  50 MHz, 4 bits, timing "sd high-speed", 3.30 V. 64 MiB of random data written at offset 8 MiB with
  `conv=fsync` in 4.0 s and read back with `iflag=direct` in 5.3 s; `cmp` equal. No `mmc1` line with crc,
  timeout or error (the brief's `grep -ciE "crc|timeout.*mmc1"` counts 5, all of them "CPU features: CRC32" and
  four "sprd-wlan: CRC value" lines).
- The log with the card in: 4 `mmc1` lines, the same at 55 s, 89 s, 211 s and 313 s of uptime. The poll is silent:
  the `mmc1` interrupt counter grew by 117 in 121 s (about one request a second), with no new log lines.
- 7.2.9: the same 4 lines and deferral message, `mmcblk1` type `SD`, same size; 64 MiB written in 4.7 s, read in
  4.8 s, `cmp` equal, no `mmc1` crc/timeout/error line; 64 interrupts in 67 s; `sdio_wifi` unbound.
- 5.4 (release v2026.09.30's kernel): `mmc0 mmc1 mmc2` (the vendor driver also probes `sdio_wifi`);
  `/dev/mmcblk1` and `/dev/mmcblk1p1`, type `SD`, 62333952 sectors. The vendor EIC driver gives the card detect
  ("Got CD GPIO"), and the card runs as "ultra high speed SDR104" after tuning, at 23.75 s (the vendor modules
  load late). That time did not come back: on the card installation (31k, "Kernel 5.4") seven boots had
  `mmcblk1` at 3.40 to 3.63 s, well before init looks for it. Init still allows a card under 5.4 up to 30 s
  instead of 8 when it waits at all (a host that waits for its card-detect line instead of polling).

- That build, card pulled at 392 s of uptime: "mmc1: card aaaa removed", `/dev/mmcblk1*` gone, and the log stayed
  at 5 `mmc1` lines from 419 s to 603 s.

With the complete parse (6.18.55 #4 and 7.2.9 #4), booted without a card: `mmc0 mmc1`, no `/dev/mmcblk1`,
`cd-gpios` gone from `/proc/device-tree/.../sdio@22210000`. Both kernels logged five "mmc1: Got command interrupt
0x00000001 (or 0x00020000) even though no command operation was in progress" with an SDHCI register dump each
(Cmd 0x371a = CMD55, 0x081a = CMD8; Resp[0] 0xffffffff), all between 5 s and 28 s of uptime: 91 `mmc1` lines.
The count then stayed at 91 at 68, 130, 192 and 253 s (6.18) and 69, 131, 192 and 254 s (7.2). The empty slot's
poll costs about 19 `mmc1` interrupts a second (6.18: 3516 in 184 s; 7.2: 3513 in 184 s); `top` showed 100 % and
96 % idle.

With the card in at boot (both #4 kernels): "new UHS-I speed SDR104 SDHC card" at 2.45 s (6.18) and 2.44 s (7.2),
`ios` 208 MHz, 4 bits, timing "sd uhs SDR104", signal 1.80 V (`vddsdio` reads 1800000 uV), 4 `mmc1` lines and none
of the "Got command interrupt" dumps: those come from the empty slot. 64 MiB at offset 8 MiB, twice each, `cmp`
equal, no `mmc1` crc/timeout/error/busy line: 6.18 write 3.78 s and 3.72 s (16.9 and 17.2 MiB/s), read 2.49 s and
2.38 s (25.7 and 26.9 MiB/s); 7.2 write 3.70 s and 3.72 s (17.3 and 17.2 MiB/s), read 2.37 s and 2.60 s (27.0 and
24.6 MiB/s). Against the half-parse build's high speed mode: reads about twice as fast, writes about the same.

A card inserted while 6.18 #4 ran (booted without it) was found by the poll: "new UHS-I speed SDR104 SDHC card" at
279.3 s of uptime. It never became usable: about 2.3 s after each detection "Card stuck being busy!
__mmc_poll_for_busy", "tried to HW reset card, got error -110", "mmcblk1: unable to read partition table", "card
aaaa removed", and 0.4 s later the next detection. 14 detections in 37 s (279 s to 316 s), 156 `mmc1` lines by
306 s; `/dev/mmcblk1*` present only between a detection and its removal. After the last removal `ios` showed
400 kHz, 1 bit, legacy, 3.30 V while `vddsdio` read 1800000 uV. A reboot with the card in gave the working SDR104
card above.

The loop was looked for again without hands (2026-10-05, 6.18.55 #7, F50 #1 running its internal system so that the
card was not the root): the `sdio_sd` host unbound from `sdhci_sprd_r11` and bound again five times (once, then
with 0, 30, 1 and 1 s between). Each time "card aaaa removed", then "new UHS-I speed SDR104 SDHC card" about
0.35 s after the bind, `mmcblk1p1` back, `ios` SDR104 at 1.80 V, and 0 "stuck being busy" or `mmc1` error, timeout
or crc lines. A rebind is a fresh probe with a power cycle of the slot, so it is not the case above (a host that had
polled an empty slot for minutes); that one needs a card put in by hand and stays open. No kernel change was made.

### 31k. The Linux filesystem on the SD card
Measured on the F50 with the same SL32G card (29.7 GiB, 62331871 sectors in `mmcblk1p1`) on 2026-10-04/05, with
the installer of this branch, the 6.18.55 #4 bundle and the v2026.10.08 root filesystems, Ubuntu 24.04 and OpenWrt
on the card, the earlier installation still in the internal region.

- **Formatting.** Android's `/system/bin/mke2fs` (1.46.2) with `-b 4096 -m 0` and one inode per 256 KiB for this
  card (about 121000 inodes; the ratio grows with the card, up to 1 MiB, while at least 65536 inodes remain). The
  format and the unpacking of both systems took about 70 s. Ubuntu 24.04 is 10790 tar entries and OpenWrt 1482,
  so 65536 inodes still leave room for an `<os>.old` of each during an update. The default of one inode per 16 KiB
  is millions of inodes on a 128 GB card; that is what kanoqwq found slow and failing there.
- **Where it went.** The summary said `writes: SD card /dev/block/mmcblk1p1, boot_b, 32 bytes of misc`; the device
  log `marked the internal installation: the SD card boots first`, and `/.mu300/root-on-sd` was in the internal
  filesystem. Booted: `/run/mu300-root-dev` `/dev/mmcblk1p1`, `/mnt/mu300-disk` the card, Ubuntu's `findmnt /`
  `/dev/mmcblk1p1[/ubuntu]` with `LABEL=mu300sd` in its fstab; the hotspot up in both systems; mobile data
  connected (this test SIM carries traffic only through a VPN, so nothing further was tried there).
- **Update.** `mu300-update boot` with a 6.18 bundle that has no `./features` refused (`this kernel bundle cannot
  read the SD card, and this system runs from it; nothing was changed`, boot_b unchanged); with the `sdcard`
  bundle it installed the 31 modules into both systems and the device booted from the card again.
- **Reboots.** A loop rebooted OpenWrt on the card 19 times; 18 came back on the card and 1 hung (the 10th, below):
  1 failure in 19. Of the 18, 17 came up undisturbed, each with the card found at 2.43 to 2.46 s ("new UHS-I speed
  SDR104"), 0 `mmc1` error, timeout or crc lines, and SSH 106 s after the `reboot` (91 s of uptime); in the 12th
  the cable was pulled and plugged back in while the board was starting, and the cold boot after that came up on
  the card as well. None landed on the internal system. Two restarts from outside the loop (reboots meant for
  another board on the same address) also came up on the card, as did the five reboots of the steps before the
  loop.
- **One boot hung.** The 10th reboot stopped at 15.09 s of uptime: init had found the card (`stage=sd-root
  dev=/dev/mmcblk1p1` at 8.08 s), switched to OpenWrt at 8.13 s, procd had loaded `/etc/modules.d`, and the last
  line in `console-ramoops` is `mali 23140000.gpu: GPU identified as 0x1 arch 9.0.9 r0p1 status 0`. A good boot
  goes on with "No priority control manager is configured" 9 ms later. No panic, no oops, no watchdog reset. The
  board then did not enumerate on USB (the hub port showed a connected device that was never enabled). After it
  was powered again, LK started Android (slot b had `tries_remaining: 1`, not successful). It happened once in 19,
  in the Mali driver's probe, long after the card was mounted, so it does not look like the card. It may be a hang
  in the Mali driver under 6.18, or the power may have dropped at that moment (the board has no battery, and its
  cable was found to need replugging later the same night). Which of the two is open.
  It came back on 2026-10-05 with 6.18.55 #7 (the IPA thread fix of 31e), on a soft reboot from the card after
  four good boots of that kernel on F50 #1 (two from the card, two of the internal system; one of each after arming
  from Android): the board did not enumerate (the dock port showed "connect" and never "enable"), and a power cycle of
  that port (which does not cut the board's power on this dock) did not bring it back. About 20 minutes later it
  was in Android on its own: LK found slot b at `tries_remaining 1` (armed at 6). That was **one** hung Linux boot,
  not five: LK's log has no `final bootargs` in the four boots after it - each found the PMIC watchdog's reset flag,
  went into its sysdump and was reset before the dump was done (31m). That boot (`console-ramoops`) had found the
  card (`stage=sd-root` at 5.06 s), switched to OpenWrt at 5.12 s and ends at 7.19 s ("random: crng init done", in
  OpenWrt's preinit), with no panic or oops; `dmesg-ramoops` was an old one. Armed again from Android, it booted
  from the card at once. So the hang is not the card; what it is stays open (31m).
- **Uninstall.** Internal kept, card erased: `erased (/dev/block/mmcblk1p1)`, the internal `root-on-sd` marker
  removed, the internal systems intact; `install.sh --check` then reported `existing mu300sd filesystem: no`.
- **Without the card.** Simulated by relabelling the card's filesystem away from `mu300sd` on F50 #1 (2026-10-05,
  6.18.55 #7, OpenWrt on the card, the older installation still in the internal region with its `root-on-sd`
  marker): the card stays in the slot and is set up at 2.45 s as on every boot, but holds no `mu300sd`. With a
  foreign label (`photos`) init mounted the internal system at 5.21 s, waited for a card for 8.85 s
  (`stage=sd-root-missing (marker present, booting the internal system)` at 14.06 s) and started the internal
  OpenWrt; with no label at all the same, 5.19 s and 14.05 s (8.86 s). The wait stayed at 8 s: the card that is
  there is set up (`sd_coming` false), so the 30 s allowance is not used. Labelled `mu300sd` again from the internal
  system (`e2label`), the next boot started the card again (`stage=sd-root dev=/dev/mmcblk1p1` at 5.09 s). On this
  board the internal OpenWrt has `default-boot` android, so init restored slot a on those fallback boots
  (`stage=misc-restored`): the reboot after each landed in Android, and `su -c mu300-linux` started Linux again. A
  system of the user's in default-Linux mode would stay in Linux. A card that is physically pulled was not tried (no
  hands at the board), nor a device with no internal system and no card (it would have meant erasing F50 #1's
  internal installation); for those there are the unit tests of the root selection (`tests/test_boot_init.py`,
  RootSelect).
- **Kernel 5.4.** Release v2026.10.08's 5.4 bundle with this branch's init in its generic ramdisk and `sdcard` in
  `./features`, installed on the card system with `mu300-update kernel 5.4` (2026-10-05): 7 boots, 2 with the init
  from before the longer wait and 5 with the one that has it, all from the card (`/run/mu300-root-dev`
  `/dev/mmcblk1p1`, OpenWrt). `mmcblk1` at 3.40 to 3.63 s and `p1` at 3.43 to 5.35 s; the
  vendor modules done at 10.23 to 11.00 s and `stage=sd-root dev=/dev/mmcblk1p1` at 11.65 to 12.49 s, so init found
  the card on its first look and never waited; 0 `mmc1` error, timeout or crc lines in the five boots counted. The
  wait that now runs past 8 s while a card may still be coming was checked against the live 5.4 sysfs: a card that
  is set up stops it (`sd_coming` 1), a 5.4 host with no card device yet keeps it going (0). Back on 6.18.55 with
  the same init: 2 boots from the card, `mmcblk1` at 2.46 and 2.47 s, `stage=sd-root` at 8.05 and 8.12 s.
- **U30 Air.** No SD host at all: `/sys/class/mmc_host` holds `mmc0` only, `/sys/block` only `mmcblk0*` (Android,
  stock kernel). `sd_probe` finds nothing, and the installers never ask.

### 31l. The card slot took mmc0
31j's "`mmc0` is the eMMC by probe order" does not hold under mainline. On F50 #1 (6.18.55, OpenWrt on the card,
2026-10-05), boot 19 of a 20-boot soft-reboot loop came up with the card on `mmc0` (`mmc0: new UHS-I speed SDR104
SDHC card`, `mmcblk0: mmc0:aaaa SL32G`) and the eMMC on `mmc1` (`stage=persist-target dev=/dev/mmcblk1p38`). init
then looked for the card on `mmcblk[1-9]` (the eMMC, no `mu300sd`) and for the internal region on `/dev/mmcblk0`,
the card: the first candidate offset lies past the card's end, `dd bs=1 skip=` cannot seek there and busybox reads
its way instead, byte by byte. No stage line after `usb-bind-done` for 297 s, then `stage=timer-reboot` at 302 s;
the next boot was normal. From outside it looked like a hang (no SSH for 6 minutes).

Both sdhci-sprd hosts probe asynchronously (`PROBE_PREFER_ASYNCHRONOUS`) and the index is taken in
`sdhci_pltfm_init()`, first come first served. In the other 19 boots of that loop the two hosts registered 0.05 to
20 ms apart (the slot's first in one of them, already holding index 1). Before the polled card slot (31j) the slot's
host deferred on its card-detect GPIO and always came second.

* Kernel port (`upstream/port/install.py`): the card slot's host returns `-EPROBE_DEFER` until the eMMC's host is
  added (checked before `sdhci_pltfm_init()`, which allocates the index). The slot registers about 0.28 s after the
  eMMC now, the card is set up at about 2.75 s instead of 2.45 s and `stage=sd-root` comes at 5.10 to 5.16 s instead
  of 5.04 to 5.07 s.
* init and the Linux tools no longer rely on the number: init takes the eMMC as the `mmcblk` disk whose card type
  is `MMC` and the card candidates from the `SD` disks, looks for the region only on the eMMC and never past its
  end, and writes `<eMMC>@<offset>` to `/run/mu300-root-dev` (`mu300-update` takes any `@` there for internal);
  early-recorder and android-vendor-start find the eMMC's partitions by name or type. (The Android-side tools run
  on the stock kernel, where the eMMC is `mmcblk0`, and are unchanged.)
* Every Linux-side lookup by GPT name - init's `misc` and `boot_<slot>` (the BCB, the persistent log,
  `/run/mu300/misc-dev` for mu300-next-boot), early-recorder's log partition, `mu300-update`'s kernel partition and
  the `by-name` links - looks only at the eMMC: the disk of type `MMC`, else the first `mmcblk` disk that is not `SD`,
  never a card. A card can carry the same names (a raw clone of a device backup) and would otherwise be written to.
* `ueventd-perms.sh` no longer touches block devices by number: Android's `mmcblk1p*` rule (the card, for vold,
  `root:system`) is dropped - no vendor daemon run here opens the card, and gid 1000 is the first user on Linux -
  and `mmcblk0rpmb` became `mmcblk*rpmb` (only the eMMC has an RPMB partition).
* The cost of the kernel wait: if the eMMC's host never binds, the card slot's host stays deferred, so there is no
  root on the card without a working eMMC host.

Verification on F50 #1 (6.18.55 with the port, OpenWrt on the card, soft reboots): the eMMC on `mmc0` in 20 boots
of 20; the new init told the eMMC and the card apart correctly in 10 boots of 10.

### 31m. Hard hangs in the first seconds under 6.18 (open)
Investigated on F50 #1 on 2026-10-05: OpenWrt on the card, soft-reboot loops from the Mac (`reboot`, SSH expected
within 200 s). The boots of the card system had two temporary preinit hooks: a 1 s heartbeat into the kernel log
(with the cluster frequencies) and a copy of the previous boot's `console-ramoops` onto the card.

| kernel | boots | hard hangs | other |
|---|---|---|---|
| 6.18.55 #7 (f50-leds-fixes) | 20 | 1 (Mali probe, boot 12) | 1 init stall, the card on `mmc0` (31l) |
| main + the mmc fix, old init | 20 | 0 | - |
| main + the mmc fix, new init | 10 | 1 (preinit, boot 1) | - |

Together with the two earlier ones (31k's 10th reboot, the 12:55 one in 31k), there are two signatures:
- **The Mali probe.** The last line is `mali 23140000.gpu: GPU identified as 0x1 arch 9.0.9 r0p1 status 0` (12.85 s;
  15.09 s in 31k). Up to that line the log matches a good boot line for line. A good boot prints `No priority
  control manager is configured` 9 ms later. In between, the probe powers the GPU off (top force-shutdown, GPLL off,
  vddgpu DCDC disabled, 10 us) and on again within milliseconds (DCDC on + 10 us, GPLL, top power, soft reset,
  clocks, `top_state` polled), and then reads `COHERENCY_FEATURES`.
- **About 7.2 to 7.6 s, in OpenWrt's preinit.** The last line is `random: crng init done` (7.19 and 7.55 s). The
  heartbeat came at 6.54 s and not at 7.55 s. Nothing in that window loads modules or touches the GPU.
In both, the heartbeat stops together with the kernel log: no soft or hard lockup report (the buddy detector is
built in), no hung-task report (the timeout was 8 s in these boots), no panic. The whole SoC stops, the way it does
on a bus access that never completes. The PMIC watchdog (procd: 30 s) then resets the board.

**One hang costs five tries.** After the PMIC watchdog's reset, LK (a userdebug build) sees `hw watchdog rst int
pending` and goes into `sprd_sysdump`: a minidump plus a zlib-compressed full RAM dump (40 s for the first 848 MiB).
It is reset again before the dump is done, so the flag stays set and the next LK does the same. LK's log shows no
`final bootargs` for those boots: no kernel was started. Each round takes a slot b try. The board ends in Android
about 20 minutes after the hang (1274 and 1290 s measured). The same pattern appears for the 00:36 and 12:55 hangs
of 2026-10-05 (LK boots 36-39 and 48-51). A reboot that is not a watchdog reset (a panic, init's 300 s timer) goes
straight back to Linux.

Ruled out or not reproduced on a running board:
- CPU DVFS: all three clusters through all their frequencies with the userspace governor, 377146 changes in 100 s,
  no hang.
- vddgpu and GPU power cycling: 400 cycles through `power_policy` (always_on, then coarse_demand, then wait until
  vddgpu is off), no hang.
- f50-leds-fixes' sipa change (F3): the hangs occur with and without it, and before the modem starts.
- Found on the way: `rmmod mali_kbase` panics with an SError in `mali_platform_term()` (`regmap_update_bits` on a
  GPU-side register with the GPU off), after a `dump_stack` from `mali_poweron_clear_flag()`. Nothing unloads Mali,
  so it is not a boot path. It does show that a GPU-side access at the wrong time is fatal on this SoC.
Still open: which access stalls the bus. A hang rate of about 2 in 50 boots needs a reproducer, or 100+ boots per
variant, before a change (for example a delay or poll before the probe's first GPU read) can be measured.

### 31n. Wi-Fi powered off and on at the same time: an Oops in the RX interrupt
F50 #1, OpenWrt from the card on 6.18.55 (main's code), 20 soft reboots: one hang (boot 11). This one left pstore:
```
15.494580 sprd-wlan: Power off WCN (1 time)          <- end of the probe, wlan0 already registered
15.494597 WCN PCIE: [+]mchn_deinit(7, 1)              ... 9, 11, 4, 5: about 24 ms each
15.543125 sprd-wlan: iface 'wlan0' deleted            <- netifd: station iface out, AP iface in
15.616675 ...  iface 'wlan0'(5c:7d:..) type 3 added
15.627387 misc wlan wlan0: iface_open
15.627393 misc wlan wlan0: Power on WCN (0 time)
15.627399 WCN BASEstart_marlin [MARLIN_WIFI]
15.627422 sprd-wlan: pcie_post_init: register 6 ops   <- while the probe is still in mchn_deinit(10)
15.636823 sprd-wlan: ctx_id:0 cmd_id:9 [CMD_SYNC_VERSION]rsp received
15.640183 WCN PCIE: [-]mchn_deinit(10)                <- the probe's power-off goes on: hif = NULL
15.640193 WCN BASEstop_marlin [MARLIN_WIFI]
15.648698 Unable to handle kernel paging request at virtual address 00000000000030b8
pc : pcie_rx_handle+0x34/0x1e0 [sprd_wlan_combo]
lr : mchn_hw_pop_link+0x8c/0xa0 [wcn_bsp]
 mchn_hw_pop_link <- edma_rx_pop_isr <- hisrfunc <- msi_irq_handle <- sprd_pcie_msi_irq   (CPU 0, swapper)
Kernel panic - not syncing: Fatal exception in interrupt
```
The board did not reset after `panic=5`; it came back in Android about 8 minutes later.

The cause is in the driver, not the bus. `power_cnt` is atomic, the transitions behind it are not. The probe
registers wlan0 and then powers the chip off from the probe thread, outside RTNL. OpenWrt's netifd replaced and
opened the interface within 130 ms. The open's power-on saw the count at 0 and ran `start_marlin` + `post_init`
while the probe's power-off was still in `post_deinit`. That power-off then finished: it cleared
`sc2355_hif.hif` after `post_init` had set it, and `stop_marlin` powered the chip down under a live interface. The
next RX MSI, on a channel the open had registered again, read `hif->rx_mgmt` through the NULL hif (`0x30b8`, a
field offset from NULL). iface_open and iface_close are both under RTNL, so a hotspot or `wifi down/up` restart cannot do
this; only the probe and remove can. main's PCIe post-init change (`wlan_combo-pcie-post-init-retry`) only
restores the static channel table and did not widen the window. The 5.4 driver has the same code; Ubuntu's hostapd
opens wlan0 about 10 s after the probe, which is why the Ubuntu boots never showed it.

Fix, both kernels (`upstream/modules/sprd_wlan_combo`, `kernel/patches/wlan_combo-wcn-power-serialise.patch`):
- `sprd_iface_set_power` holds a mutex (`hif->power_lock`) across the whole transition, so an open waits for the
  probe's power-off and then powers on from scratch.
- `pcie_rx_handle` drops a list that arrives without a context (no hif or no `rx_mgmt`) and logs once ("RX on
  channel N with no Wi-Fi context"). The TX pop handlers and `pcie_rx_fill_mbuf` already had such checks on 6.18
  (14c).
- `sc2355_hif.hif` is published with a release store before the channels are registered, read with an acquire
  load, and cleared only after they are unregistered.
- Found in review:
  - The probe's error paths and `remove` powered off after `sprd_core_free` had freed `priv`, and `hif` with it.
    They now power off first.
  - A power-on that failed in `post_init` or the version sync left the chip started with the count at 0, and
    after a failed sync the channels stayed registered too. It is now undone the way a power-off does.

Measured on F50-B (Ubuntu 24.04, 6.18.55 with the fix):
- 30 soft reboots, each started only after `mu300-boot-ok` had confirmed the one before: 0 Oops, 0 "no Wi-Fi
  context" lines, pstore empty, every boot confirmed.
  - 14 boots in hotspot mode (AP up every time). A 15th, at 23:47, was the user unplugging the board and is not
    counted.
  - 16 boots as a Wi-Fi client (joined KEDI 5G every time). In these, a temporary unit opened wlan0 as soon as the
    driver registered it, to recreate the pstore boot's timing (Ubuntu's hostapd opens about 10 s later).
  - In all 16 the open came 1 to 16 ms after the probe's power-off began, about 140 ms before that power-off's
    `stop_marlin`. That is the window of the Oops. In all 16 the open's `start_marlin` came after it.
- 30 hotspot restarts (`systemctl restart mu300-hotspot`, a full WCN power-off and power-on each): AP up after
  every one, 0 Oops.
- The 6.18.55 and 7.2.9 modules build. The 5.4 patch applies after the others and compiles against the 5.4 tree;
  the module link was not run.

Not covered:
- `edma_chn_deinit` (wcn_bsp) frees a channel's ring lock and mbuf pool after a bare `msleep(20)`, without masking
  the channel or `synchronize_irq`.
- `mchn_hw_pop_link` reads `mchn->ops[chn]` twice.
- An MSI still running on another CPU while a channel is torn down is therefore still possible. It is pre-existing
  and was not seen.
- The 5.4 driver also lacks 6.18's TX-side checks (14c).

31m's silent hangs (the SoC stops at the Mali probe or at `crng init done`, no log) do not match this: here the
kernel logged an Oops and panicked. A chip powered down by `stop_marlin` under a live PCIe link could stall a bus
access, though, so this fix may remove some of that class. Not shown.

### 31o. KVM, and the module set a router needs
The mainline config (allnoconfig plus `mu300-mainline.config`) never had `CONFIG_KVM`, so 6.18 and 7.2 had no
`/dev/kvm`, although the firmware starts every CPU at EL2 (`CPU: All CPU(s) started at EL2` on all three kernels).
The vendor 5.4 kernel has it: on F50-B, 5.4.254 logs `kvm [1]: Hyp mode initialized successfully` (nVHE: 5.4 runs
the host at EL1). With `VIRTUALIZATION`/`KVM` built in, 6.18.55 and 7.2.9 log `kvm [1]: VHE mode initialized
successfully` (IPA size limit 40 bits, GICv3 system registers, no GICv2 emulation: the stock DT has no GICV
region). A static test program (`KVM_GET_API_VERSION` 12, a VM, one vCPU, four guest instructions whose store to an
unmapped address must come back as an MMIO exit with the value 42) passed on 5.4, 6.18 and 7.2.

The same change brought the modules people expect on a router or a small server, as modules so the Image stays
small: netfilter (conntrack helpers, queue/log, the remaining nft expressions, ipset types, the xt matches and
targets iptables-nft and Docker use through `nft_compat`, IPVS, br_netfilter), tunnels and links (bonding, team,
dummy, ifb, macvtap, ipvlan, vxlan, geneve, VRF, IPIP/GRE/FOU, ip6 tunnels and GRE), IPsec (xfrm_user, ESP/AH/
IPcomp, xfrm interfaces), L2TP, PPPoE, PPTP, MPPE, TLS, socket diagnostics, tc (HTB, HFSC, netem, fq, PIE, flower,
u32, ematches, police/mirred/ctinfo/ct and the other actions), vhost-net/vsock, USB (QMI/MBIM/Huawei NCM/EEM
modems, AQC111, printers, MediaTek/Ralink/Realtek Wi-Fi sticks with mac80211, btusb, snd-usb-audio, uinput/uhid),
device mapper (crypt, verity, snapshot, thin), MD RAID 0/1/10, NBD, filesystems (btrfs, f2fs, XFS, ntfs3, HFS+,
FUSE, ISO 9660/UDF, NFS client and server, CIFS, ksmbd), the crypto user API with XTS/CTR/CBC/GCM/CCM/
ChaCha20-Poly1305 and the ARMv8 AES/GHASH engines, and binfmt_misc. Built in, because they cost little and
container runtimes look for them: `/proc/config.gz` (check-config scripts read it without loading a module), PSI,
the net_prio/net_cls/misc cgroups, CFS bandwidth, block throttling. What was built in stays built in: three defaults the new options would have turned into modules (SIT,
the AX8817X and CDC subset USB drivers) were left out of the fragment. Not taken: legacy iptables/ebtables tables
(`NETFILTER_XTABLES_LEGACY`: Ubuntu and OpenWrt run iptables over nftables), kexec (arm64 has it only with
`PM_SLEEP_SMP`, not built here).

| | 6.18.55 before | 6.18.55 after | 7.2.9 before | 7.2.9 after |
|---|---|---|---|---|
| Image (bytes) | 16 281 608 | 17 311 752 | 16 705 544 | 17 864 712 |
| modules in the bundle | 31 (vendor) | 360 | 31 | 377 |
| bundle (`mu300-kernel-*.tar.gz`) | 9.4 MB | 15.7 MB | 9.6 MB | 16.4 MB |

The modules unpack to 20 MiB (6.18, debug sections stripped) under `/lib/modules/<release>`. Boot time on F50-B
(Ubuntu 24.04, no SIM) did not move: kernel 5.50 s before, 5.43 s after (7.2: 5.42 s); userspace is 3 min 42 s
both times, the mobile-data watch waiting for a modem without a SIM.

Packaging: `build-modules.sh` now runs `modules_install` (stripped) and puts the kernel's own modules flat into
`out/modules` next to the vendor ones, refusing a vendor module with an in-tree name. The layout on the device did
not change: `mu300-update` already put the bundle's flat directory under `extra/` on Ubuntu, where depmod indexes
every module there (`modprobe dm-crypt` pulls in `dm-mod`), and flat into `/lib/modules/<release>` on OpenWrt, where
ubox's kmodloader resolves dependencies from each module's `depends=`. With a set this size it now replaces the
modules of an earlier bundle of the same release instead of adding to them (a module a newer bundle dropped stayed
loadable). The generic ramdisk still loads only `module-order.txt`. On F50-B, `modprobe` of 34 new modules
(sch_cake, ntfs3, cdc_ether, cdc_mbim, dm-crypt, vhost_net, xfrm_user, esp4, pppoe, bonding, vxlan, btrfs, nfs,
cifs, snd-usb-audio, btusb, mt7921u, br_netfilter, ip_vs, ifb, act_mirred, algif_skcipher and others) succeeded on
6.18 and 7.2, a cake qdisc went onto a dummy link, and no Oops followed; USB network, the Wi-Fi client and the 5 GHz
hotspot came up on both.

OpenWrt's packages ask for `kmod-*` packages, which apk installs from the feed for OpenWrt's own kernel (6.12);
`build-rootfs.sh` then deletes `lib/modules/6.*` as it always did, so apk's database is satisfied and the running
kernel's modules (built in, or from the bundle) are what loads; the `/etc/modules.d` lists the kmods leave behind
make kmodloader load the matching mainline modules at boot. The images now carry wireguard-tools and
luci-proto-wireguard, PPTP and L2TP (xl2tpd), 6in4/6rd/DS-Lite, GRE and VXLAN with their LuCI protocols, ipset,
and SQM (sqm-scripts, luci-app-sqm; cake is built in on mainline and on 5.4, ifb a module on both); apk resolves
the whole set together (65 kmods). xl2tpd starts at boot and listens on UDP 1701, which fw4 closes on WAN. The
images also carry the 6.18 modules from `upstream/out` (about 20 MiB unpacked, some 6 MB more in the tarball), so
the switch to 6.18 needs nothing more. Not tried on an OpenWrt device in this round.

## Updating on the device

### 32. Old kernels, an idle IPA, and an update that ended in Android
A report: a device on the vendor 5.4 kernel, updated with `mu300-update`, only ever started Android afterwards.
Reproduced on the test board with an older installer boot image (kernel #11 of 20 September) and the systems of
v2026.09.21. The boot image of v2026.09.27 (kernel #13) does not have the problem below: its downlink works after
four and a half idle minutes, with the same failed power-off messages in the log. Which of the published boot
images have it was not established, so the update protects all of them:

* After about two minutes without mobile traffic the IPA tries to power off and fails
  (`Polling check power off reg timed out`, `sipa power off maybe fail`). From then on the downlink is dead
  until the next boot: `rx_packets` of `sipa_eth0` stops, TLS handshakes time out, and neither the data
  watchdog (the address is still right) nor a reconnect of mobile data brings it back.
* The old `mu300-update` downloaded one system, unpacked it for a few minutes - exactly the quiet time the IPA
  needs - and then started the next download. `curl` had no timeout and hung there, and twice the board reset
  without a trace (no pstore, no persistent log) right when the next network transfer started: once between
  the two systems, once at the start of the boot image step. A reset while boot_b is being written leaves slot b
  unbootable, and LK then falls back to Android on every boot - the reported symptom.

A reset does not have to hit the boot_b write to end in Android, though. With the boot scheme of the older boot
images slot b is armed for one boot (`tries_remaining 2`, see 1); a crash leaves it at 1, and LK's log on the next
start reads `check rollback slot 1 tries: 1` - `Have not get right slot` - Android, for good, with boot_b intact.
`su -c mu300-linux` in Android (or the Magisk module's button) arms slot b again and Linux starts as before; the
newer boot images count failed boots instead (5 in a row before Android).

`mu300-update` now:
* downloads everything the update needs (the systems and the kernel bundle) first, checks every file against
  the release's `SHA256SUMS`, and only then changes anything; the unpacking and the boot_b write need no network;
* keeps the IPA from going idle while it runs: a ping every 3 s (to 1.1.1.1 and to 223.5.5.5, which is reachable
  from mainland China). With it, a 26 MB download after four otherwise quiet minutes on kernel #11 ran at 5 MB/s;
  without it the download after the same pause never started;
* cuts off stalled transfers (`--connect-timeout`, `--speed-limit`) and resumes partial files, so a dead downlink
  is an error message ("reboot, then run mu300-update apply right away") instead of a hang;
* stops the data watchdog while it installs, so no redial happens in the middle of the boot_b write.

The full old-user path (installer boot_b with kernel #11, both systems reinstalled, boot image written) then took
40 s, and the board started the new kernel.

### 32a. The offset in init, replaced by every boot image update
A user installed 6.18 with the installer and got "MU300 standalone Linux ... automatically reboots to Android
after 300 seconds": the root filesystem was not found. `boot/init` finds the Linux region at `ROOT_OFFSET`, a number
in the file - our test board's region (27762098176). The installer writes the device's own offset into that
line, but that init lives in the device's ramdisk segment, and the generic segment behind it - what
`mu300-update` puts there for every kernel and boot image update since v2026.09.27, and what the installer adds for
a mainline kernel - brings its own init, which replaces the file, with the default. On every device whose region
is somewhere else, each such boot image went looking at the test board's offset, dropped into standalone mode and
went back to Android: the boot image did not have to be broken for "the update always ends in Android", which is
very likely what the report of section 32 was too. The test board never showed it: its region is the default.

init now finds the region itself, as the installer places it - the first 2 MiB boundary after the last partition
(from sysfs) - and takes the first candidate that holds the mu300root filesystem (ext4 magic and label), the
number in the file only as the last one. Tested with a generic segment whose default was wrong on purpose:
"stage=root-offset found=27762098176 (default 12884901888)", and the board booted. A device left in Android by
this needs one reinstall from a computer (the installer's `update` keeps settings and data); from v2026.09.29 on
every generic segment carries the new init.

Found on the way: the account merge rewrote `/etc/passwd` and friends in place (a reader at first boot could see a
half-written file: `Failed to resolve user 'messagebus'`); it now writes a copy and renames it, and
`mu300-accounts` runs before tmpfiles, sysusers and D-Bus. `rollback` removed `<os>.broken` even when that was the
system still running (only rm's `--preserve-root` stopped it), and `apply`, `rollback` and `clean` could remove
`<os>.old` while it was the running system (an apply or rollback without the reboot in between); all of them now
check whether a directory is the running root (`[ / -ef dir ]`) first.

### 32b. The Magisk installer on a device: an unmount that worked, and a password file with one system
On the second F50 (Android on slot a, Magisk 30.6, an Ubuntu and an OpenWrt on the internal region), zips built
from a local release of main: every run of the installer, a dry run included, stopped after unpacking with "could not
unmount the Linux filesystem", nothing written. The read-only look at what is installed had mounted and read the
filesystem; `android-mount-mu300root.sh -u` then failed, because Android's umount (toybox) frees the loop device of
what it unmounts and the `losetup -d` after it ends in "No such device or address". The computer installers,
uninstall and reset-password never look at `-u`'s status; the Magisk installer does. The helper now detaches only a
loop that is still attached.

With that fixed, the OpenWrt 6.18 zip (with `MU300_MODE=wipe` in `/data/adb/mu300-install.conf`: a fresh region)
installed in 32 s and booted (`/run/mu300/linux-slot` b, boot-ok counted); the wipe line became a comment. The
Ubuntu 24.04 5.4 zip then installed beside it in 36 s as an update, OpenWrt untouched (its LAN setting kept), and
`mu300-os` switched between them. But its password file replaced the first one: the OpenWrt root password, still
the one in use, was then nowhere on the device. The file now keeps the other system's entry while that system stays
on the filesystem (not after a wipe); on the device, OpenWrt and then Ubuntu again left a file with both, and the
OpenWrt shadow hash matched the password in it.

**Update 2026-10-07:** since PR #40 an update (keep mode) leaves the system's accounts and passwords as they are.
No password is generated and no password file is written. A password is made only for a new filesystem, a wipe,
a system added beside another, or when `MU300_PASSWORD`/`MU300_PASSWORD_RESET=yes` asks for one. The install
refuses a system that would be left with an empty password or the image's default. See
`android/magisk/installer/mu300-install.sh` and `tools/android-install.sh`. No device test of that change is
recorded.

## ZTE U30 Air

### 33. The same board with a battery

The U30 Air (`ro.product.device` U30Air, firmware `U30Air_SSV1.0.0B14`) is `ums9620_2h10_feimao` like the F50: same
SoC, same 64 GB eMMC and partition layout (partitions end at sector 54218752, so the Linux region is at the same
offset), and its stock kernel is the very source this project builds (Enceka's tree is named after it). Its
`/proc/config.gz` differs from the F50's in 19 symbols, all about the battery and its surroundings: ZTE's "SQC"
charger stack (`sqc_charger`, `sqc_bq2560x`, `sqc_netlink`, `charger_policy_service`, `zte_power_supply`,
`zte_misc`), `SC27XX_PD`, GPIO and LDO LEDs, a SAR sensor (`SAR_PARA` bougain instead of anthurium) and an NFC tag.
Two are built in on the U30 Air (`I2C_CHARDEV`, `I2C_SMBUS`); everything else is a module or a bool that only
changes modules.

The first boot with the F50 modules (one-shot trial) reached switch_root and ran, but the host never saw USB:
`sprd-charger-manager` probed with -517 for good, because the U30 Air's device tree describes the SQC charger
manager, and the F50 build of that module is `charger-manager.c` while `VENDOR_SQC_CHARGER` swaps in
`charger-manager-sqc-comm.c`. The USB PHY and dwc3 wait on the charger/Type-C side, so no gadget.

`kernel/build-u30air.sh` builds the F50 config plus `kernel/u30air.fragment` in a second build directory and keeps
what differs. The Image has to stay the F50 one, so the check is the set of symbols vmlinux exports: `I2C_SMBUS=m`
changed it (the i2c core gains `of_i2c_setup_smbus_alert`), and no U30 Air driver needs it, so it is left out;
`I2C_CHARDEV` is a module. Comparing whole files marks nearly every module as different (build id, symbol table
order), so the comparison is on `.text`, `.rodata`, `.data`, `.modinfo` and `__ksymtab_strings`; that leaves 15
modules. The load order (`boot/module-order-u30air.txt`) is the F50's with the charger block replaced, checked
against every module's `depends=` (the fuel gauge needs the charger manager, which needs the SQC modules and
`charger_policy_service`).

init picks the set: `/etc/mu300-device` (written by the installer into the device segment of the ramdisk, which an
update's generic segment does not replace), else the device tree (`/charger_policy_service` exists only on the U30
Air). The set is used only when `linux-modules/u30air/kernel.release` matches `uname -r`, since a mainline kernel's
generic segment brings its own modules and order but leaves these in place.

With them: 93/93 modules, USB network, the hotspot, Bluetooth, mobile data, `/sys/class/power_supply/battery`
(capacity, status) and the charger's `usb`/`ac` online flags. The battery LED is the charger's own; the others are
`gpio-leds` (`pwr_green`, `net_blue`/`net_red`/`net_green`/`net_white`, `wifi_blue`/`wifi_white`), driven by
`mu300-led`. No `LEDS_TRIGGER_NETDEV` in this kernel, so the Wi-Fi LED follows the hotspot service, not traffic.

**Update 2026-10-07:** that LED list is wrong. Of the GPIO LEDs only `net_blue` is wired. The others are
LDO-switched camera supplies and the PMIC's keypad backlight sink, and the remaining six `gpio-leds` light nothing
(§33f).

### 33a. misc and boot_b were looked up before the eMMC existed

`sdhci-sprd` is one of the vendor modules, so the eMMC appears only once they are loaded (about 10 s in). init looked
for misc and boot_b before that: 20 s of polling for nothing, then `misc-NOT-FOUND` - slot a was never restored by
init, and there was no persistent log (`persist-target dev=none`). It happened on the F50 as well; the trial boots
there were rescued by the bootloader's own counting. The lookup now runs after the modules (misc and boot_b at
10.7 s on both devices), and the reboot timer, which started earlier, reads boot_b from `/run/bootb`.

### 33b. Two devices on one computer

Every device had `192.168.77.1` and the same USB MAC addresses (`02:50:00:00:77:0x`). The subnet now goes with the
kind of device (F50 `.77`, U30 Air `.78`; `mu300-lan-ip`, `lan.conf` still overrides it) and the gadget MACs are
`02:50:<md5 of the serial>:<subnet>:0x`. `mu300-vpn` always keeps the device's own LAN out of the tunnel: a
`vpn.conf` copied from an F50 said `LAN_CIDRS=192.168.77.0/24`, which on a `.78` device would have sent every reply
to its USB and Wi-Fi clients into the tunnel.

### 33c. Mainline on the U30 Air: the USB PHY waited for a Type-C driver that does not exist

The first 6.18 boot on the U30 Air came up completely - systemd, mobile data, the VPN, the hotspot - with no USB at
all: no network, no serial console. Its persistent log said `25310000.ssphy: cannot add phy` and `dwc3: failed to
initialize core`. After LK's dtbo merge the PHY's `extcon` on the F50 is `/extcon-gpio` (`linux,extcon-usb-gpio`,
which mainline has), on the U30 Air `typec@380` - the PMIC's Type-C block, `sprd,sc27xx-typec`, which has no driver
under mainline, so `usb_add_phy_dev()` deferred for ever. Both boards have the VBUS GPIO node: the ssphy driver now
points the property at it when it names the Type-C block. Found with the device's own log, since there was no USB to
look through: init persists it into boot_b, and it was read from Android afterwards (`tools/collect-logs.sh`).

A boot without USB is also a boot you cannot end: it counted as good, so only failing five boots by hand brought
the device back. `build-boot-image.py --trial-guard SECONDS` is for such experiments: init leaves a timer running
past switch_root (from a copy of busybox in `/run`, reached through its working directory, since switch_root deletes
the ramdisk and moves `/run`) that reboots unless `/run/stay` exists by then; with a one-shot trial that is back in
Android. A reading of the PMIC registers through debugfs (`regmap/spi4.0/registers`) during these tests locked up a
CPU for 23 s and panicked the board - the ADI bus does not take a full register sweep.

Two more things that only show with two devices on one computer: every gadget had the USB serial number
`MU300LINUX`, and macOS gave the second device a serial port but no network interface; it is now
`MU300LINUX-<serial number>`. And under mainline `/proc/cmdline` is the kernel's forced command line, without
`androidboot.serialno`: init reads the bootloader's from `/chosen/bootargs` in the device tree.

Under 6.18 and 7.2 the U30 Air has USB, mobile data, the VPN, the hotspot, Bluetooth and its LEDs
(`CONFIG_LEDS_GPIO`). The battery is not reported: its charger and fuel gauge (the SQC stack and `sc27xx-fgu` on
the UMP9620) have no mainline drivers (for the charger IC see 33d: it does not charge without one).
(**Update 2026-10-07:** both are reported now. Patches 0004-0006 add the UMP9620 fuel gauge, and mainline's
`bq256xx` drives the charger and switches charging on, which Android had left off (§33d, PR #55).) Kernel bundles now name
the devices they run on (`./devices`): mu300-update and the installers do not put a bundle from before this onto a
U30 Air.

### 33d. The U30 Air's battery under mainline

Under 6.18 the PMIC's efuse, ADC and fuel gauge (`sprd,ump9620-efuse/-adc/-fgu`) appeared as platform devices with
no driver: mainline's sc27xx drivers know the SC2731/SC2730 family only. Patches 0004-0006 add UMP9620 from the
values in Unisoc's 5.4 drivers:

- efuse: 64 blocks, read directly from a window at 0x40 once the controller's RTC clock is on and ungated
- ADC: its own scale table and ratios, a battery-voltage detection graph for scale 1, calibration from two efuse
  words per graph (bits 15:4), and a vote for its 26 MHz clock in an AON register (`sprd_adc_pm_reg`) around each
  conversion
- fuel gauge: enable bits at 0x2008/0x2010, the 4200 mV calibration in bits 15:7. `bat-temp` is the NTC's voltage
  on this board, not a temperature (71.2 "degrees" at first): the battery node's `voltage-temp-table` converts it.
  Without a charger driver the status came from the battery current (patch 0010 now takes it from the charger, see
  below). Mainline read a discharge current
  as ~2 billion: `u32 cur - 8192` wraps below zero; the vendor driver casts to s64 first.

The first status fallback asked for the capacity, whose calibration asks for the status: a stack overflow in the
first second of every boot. Five of them in a row put the device back into Android by itself - the fallback did
its job - and the panic was in pstore.

The charger is an SGM41511 (part 0010 in REG0B, a bq25601), I2C bus 6 at 0x6b, DT node `charger@6b` with
`ti,bq2560x_chg`, `monitored-battery`, `extcon`, an `otg-vbus` regulator and the vendor `vindpm-value` (4270 mV), and
no interrupt. Under 5.4 the vendor SQC stack drives it. An earlier version of this section said that under mainline
it "charges on its power-on defaults"; that was wrong. The chip runs on the battery and keeps its registers across a
reboot, so mainline found it as Android had left it. Read on the U30 Air under 7.2.9 (2026-10-06):

```
00:04 01:8a 02:8b 03:6f 04:58 05:87 06:67 07:40 08:24 09:00 0a:80 0b:14
```

REG01 has CHG_CONFIG (bit 4) at 0: charging off. REG00 has the input current at 500 mA, REG02 the charge current at
660 mA, REG04 VREG at 4.208 V, and REG05 the watchdog off. REG08 reports a USB host (SDP) with power good and no
charging. Under 6.18 and 7.2 the battery never charged, and drained while the device was plugged in. The fuel gauge
still said Full, 100 % at 3.88 V, because its status came from the current.

Mainline's `bq256xx` driver now handles the node. `port/install.py` adds the compatible to its OF and I2C tables with
the bq25601's data, and patch 0009 changes the following for that node only:

- No register cache. The driver's cache starts from the power-on defaults, so every read-modify-write would have
  written them back over Android's values (and over `mu300-usb`'s OTG bit in REG01).
- The charge current is at most 1.98 A, Android's value. The battery node says 3 A, which is too much for this
  4050 mAh cell. VREG is at most 4.208 V: Android's REG04 has that, while the node says 4.3 V. Termination is on and
  the watchdog off. VINDPM comes from `vindpm-value`, rounded up to the chip's 100 mV steps.
- The node has no `input-current-limit-microamp`, and the driver's default of 2.4 A is too much for a 500 mA USB
  port. The input current is 500 mA until a charger type is known. The type comes from the UMP9620's own charger
  detection (`sprd_pmic_detect_charger_type()`, as `sc2731_charger` and the Unisoc kernel use it): SDP 500 mA,
  CDP 1.5 A, DCP 2 A, and `usb_type` from the same result. The charger's own input detection (IINDET_EN in REG07,
  then VBUS_STAT in REG08) drives D+/D-, which on this board are the USB gadget's lines to the computer. It runs
  only when the PMIC device or its result is missing, and the driver says so once. With it, SDP or unknown is
  500 mA, CDP 1.5 A, DCP 2 A and non-standard 1 A. The type is read at probe and again on every VBUS change. With no interrupt, those changes come from the extcon. If the node's
  extcon is not the `extcon-usb-gpio` device (on the U30 Air the PHY's points at the PMIC's Type-C block, which has
  no driver, 33c), the driver uses that device, as the USB PHY does. Each run also switches charging on.
- `charge_type` on `/sys/class/power_supply/bq256xx-charger` is the userspace switch: `N/A` stops charging, also
  across plugs, and `Fast` starts it again. `status`, `online`, `usb_type`, `input_current_limit` and
  `constant_charge_current` are there as well. There is no second `bq256xx-battery` supply.
- The fuel gauge is in the charger's `supplied_to`, and patch 0010 makes it take its status from
  `bq256xx-charger`, as it does from the SC27xx chargers.

The driver owns 6-006b now, so `mu300-usb` reaches the chip with `i2cget/i2cset -f` and leaves its watchdog off.
On expiry, the watchdog would drop the driver's settings. Nothing answers at 0x6b on the F50 (24). If its DT has
the node, the probe stops at the first read.

On the U30 Air under 7.2.9 (2026-10-06) the driver binds (`part 2, rev 0`), switches charging on (Android had left
CHG_CONFIG at 0), and the fuel gauge reads +219 mA at 3.888 V, status Charging. Two things were wrong in that
first build:

- `sc27xx-pmic spi4.0: failed to detect charger type`, so the driver fell back to IINDET_EN. On that Mac CDP port
  the result was usb_type 0 and 500 mA; Android uses 1.5 A there. `port/install.py` had given the UMP9620 the
  SC2730's detection register, 0x1b9c. The UMP9620's BC1.2 status register is 0x239c (`UMP9620_CHARGE_STATUS` in
  Unisoc's `sprd-bc1p2.h`), with the bits mainline expects: DONE 11, SDP 7, DCP 6, CDP 5. The edit now uses it,
  and input detection has to be tested again.
- `sc27xx-fgu/capacity` read 575. The FGU's always-on user area keeps the last capacity across a reboot, and
  Android keeps it in 0.1 %. Until then the status had been Full, and the calibration that runs whenever the
  battery is not charging forced anything above 100 back to 100. Patch 0011 reads and saves that value in 0.1 % on
  the UMP9620, and clamps the reported capacity to 0-100. (Its format was wrong: see 2026-10-07 below.)

2026-10-07, U30 Air under 7.2.9 with 0009-0011: charged from about 60 % (Android said 65 % at 4.04 V under 1.3 A) for
about 1.5 h at 1.1-1.3 A. Then bq256xx-charger said Full (charge_type Trickle), and the battery rested at 4.146 V with
+2 mA, so it was physically full. `sc27xx-fgu` said status Full and capacity 58, and over the whole charge the capacity
had read 57.5, 59 and 58. Two faults in the driver, and a third that is still open:

- The user-area format. Unisoc's 5.4 driver (`sc27xx_fgu_save_last_cap()`/`read_last_cap()`, `FCC_PERCENT` 1000)
  keeps the capacity as whole percent in bits 7:0 and tenths in bits 11:8. That makes 575 (0x23f) 63.2 %, close to
  Android's 65 %, not 57.5 %. Android's own capacity is in 0.1 % internally (its `sc27xx-fgu` capacity read 615 when `battery` said 65), but that is not
  what it stores. The 0.1 % that 0011 wrote back would read as something else under Android (580 = 0x244 = 68.2 %).
  Mainline's arithmetic is in whole percent throughout (`init_cap`, `ocv2cap`, the delta from the coulomb count over
  `total_cap`), and 0011 had converted at the user area, so the units inside the driver agreed. The value read was
  the wrong one.
- No calibration at the end of a charge. Mainline sets 100 % only when the OCV is above the top of the OCV table.
  The charger ends at VREG 4.208 V, below the top of the table (4.3 V and up for these cells), so with Full and 4.146 V
  nothing moved the 58. Mainline also writes the user area only on a first power-on, so every boot started again
  from the value Android had left.
- Open: the coulomb count should have added about 40 % (1.6-1.8 Ah of a 4050 mAh cell). Its arithmetic matches the
  vendor's (`clbcnt * 10 / 72 / cur_1000ma_adc` mAh, the same registers, 2 Hz) and does not overflow at these values,
  and nothing calibrates while the status is Charging. A reboot during the charge would explain the 59 -> 58 step
  (each boot restarted from the stale saved value), but not the small rise. `charge_now` (uAh) is the raw counter:
  it should rise by about 1.2 Ah per hour at 1.2 A. If it does not, the UMP9620's counter needs something the
  driver does not do.

Patch 0011 is replaced (`0011-power-sc27xx-fuel-gauge-UMP9620-saved-capacity-and-full.patch`). On UMP9620 it reads
the saved value in Android's format and writes whole percent, which is the same number in both formats. A value that
is not a capacity in that format goes to the OCV. So does a multiple of 10 with tenths, which the first 0011 may have
written: the OCV table decides it right away with the battery at rest (under 50 mA), and under load the value is taken
in Android's format. Either way dmesg says `boot capacity N % (saved 0x...)` or `... from the OCV`. The capacity is
written to the user area whenever its whole percent changes. A Full from a charger driver (not 0006's guess from the
current) sets 100 % while the OCV table puts the battery at 70 % or more. The reported value stays within 0-100. Built
for 6.18.55 and 7.2.9. Not yet tested on the device.

### 33e. USB host on the U30 Air, and a trial guard that outlived its trial

Mainline had the gadget side of the dwc3 only: no host stack, no `/sys/bus/usb` at all. With dual-role dwc3, xHCI,
mass storage, HID and the USB network/serial drivers it is a host as well, and it still starts as a gadget (the
dwc3 node has `usb-role-switch` and no default mode: peripheral), so the USB network to a computer comes up as
before. Two things the vendor stack does elsewhere:

- The role. Under 5.4 the PMIC's Type-C block decides; it has no mainline driver, so the role is chosen from
  userspace: dwc3 opens its role switch to it in 7.2, patch `6.18/0007` does it on UMS9620 in 6.18 (a patch 7.2
  does not need goes into `patches/<version>/`). dwc3 tells the PHY about the role through `otg_set_vbus()`, which
  the PHY did not provide: it has an otg structure now (host eye pattern, A-type ID, D+/D- pull-downs).
- The 5 V. `vbus-supply` is the charger's `otg-vbus` regulator, and the charger (SGM41511, part 0010 in REG0B, on
  the I2C controller at 22a0000) has no driver under mainline. `mu300-usb` sets its OTG_CONFIG bit (REG01 bit 5)
  and turns its watchdog off (REG05 5:4), which would otherwise return it to its defaults 40 s after the write,
  boost included. It refuses host mode while REG08 reports power good (a computer or charger on VBUS), and turns
  the boost off at boot: the chip runs on the battery and keeps its registers across a reboot.

  **Update 2026-10-07:** the charger has a driver under mainline now, `bq256xx` (§33d, PR #55). `mu300-usb` still
  sets the OTG bit, but through `i2cget`/`i2cset -f` while the driver owns 6-006b. It leaves the chip's watchdog
  off, because the watchdog would drop the driver's settings.

A Logitech receiver (HID) and a flash drive (FAT, mounted and read) worked through a USB-C adapter under 6.18 and
7.2. The drive read at ~3 MB/s with or without the PHY's host settings; it is an old stick, not yet compared
elsewhere. HDMI through the same adapter needs DisplayPort alternate mode over USB-C, which this project has on
neither kernel.

Two restarts during these tests, both about 600 s after boot, were not the USB: `mu300-update` keeps the device
segment of whatever image is in boot_b, and boot_b held a `--trial-guard 600` experiment - so every boot restarted
after ten minutes. init now honours a guard only in a trial boot (Linux not the default), and says so.

### 33f. The U30 Air's LEDs: three kinds of wiring, and lights that never went out

Under mainline the network and Wi-Fi lights stayed lit whatever Linux did. Lighting each LED the kernel knew, one
at a time, while someone watched the device, showed where they are:

| light | colour | wired to |
|---|---|---|
| battery | white, red, blue | the PMIC's RGB LED (`sc27xx-bltc`): its *green* channel is white |
| network | blue | GPIO 117 (`net_blue`) |
| network | white | LDO VDDCAMA0 |
| network | red | the PMIC's keypad backlight sink (`keyboard-backlight`) |
| Wi-Fi | white | LDO VDDCAMA1 |
| Wi-Fi | blue | LDO VDDCAMA2 |

The device tree's six other GPIO LEDs (`pwr_green`, `net_red`, `net_green`, `net_white`, `wifi_blue`,
`wifi_white`) light nothing; they come from a ZTE board file shared with other products, and Android never writes
them either. The lights that never went out were the LDO ones: ZTE's `zte_ldo_leds` switches the camera supplies
VDDCAMA0-2 (3.3 V) through `vddcamaN_status`, mainline had no consumer for them, and `regulator_ignore_unused`
kept the bootloader's "on". `leds-zte-ldo` (upstream/port) makes them `zte-ldo0..2` and starts them dark, and
`leds-sc27xx-kpled` (after Unisoc's keypad driver, current mode) brings the red back under its Android name. What
each colour means was read from Android: sampling `/sys/class/leds` with the radio off shows the network LED
cycling red / white / off, and `vddcama0` lit on 5G. mu300-led now follows it (blue on 4G, white on 5G, red
without service); `mobile-data` reads the access technology (`AT+COPS?`) again on every watchdog round, since it
changes under a live connection.

The PMIC's LED also carries the heat alarm (`thermal-guard`, now running on 5.4 too, where it only watches): one
colour at a time, since the white outshines red and blue when they are mixed.

### 33g. The U30 Air's NFC tag

The device tree's `st,st21nfc` at `i2c@2260000` 0x08 is a leftover: nothing answers there. The tag is a Fudan FM11NT08
dual-interface EEPROM at 0x57 on the same bus (I2C bus 2), which answers only while GPIO 190 (ZTE's
`ntag-reset-gpio`, driven by its `fm11tag` module under 5.4) is low; GPIO 127 is its field-detect interrupt. The
memory is NTAG-like: UID and lock bytes, the capability container `e1 10 6d 00` (872 bytes of NDEF), then the NDEF
TLV from 0x10. ZTE's `Fm11ntagService` writes a WSC Wi-Fi record (WPA2-PSK, AES) with the hotspot's name and
password; `mu300-nfc wifi` writes the same bytes (compared page by page against ZTE's: nothing to write).

A phone got nothing from the tag at first, under Linux and under Android alike, although the field-detect interrupt
counted every tap. ZTE's web interface had NFC off (`settings global webserver_nfc_switch_status=0`, the factory
state of this unit); switching it on there once made the tag answer phones from then on, under Linux too, so the
switch is kept in the chip, presumably in its configuration block at 0x3b0 (which also holds the I2C address).
The data area was unchanged by it: reading all 1 KiB with the switch on and off, the only difference is bit 5 of
byte 0x3bf (0x20 set: off), in the configuration block at 0x3b0 that also holds the I2C address (0x57 at 0x3b3).
`mu300-nfc on|off` changes that bit alone. With it on, URLs and text written by `mu300-nfc` reached a phone; a
Wi-Fi record joins Android phones, while iOS reads URL records by itself but does nothing with a WSC record.

### 33h. A trial guard that outlived its experiment, again

The U30 Air restarted about every ten minutes after coming back from Android (`su -c mu300-linux`). init said
`stage=trial-guard 600s`: the device segment of boot_b still held the guard of an old `--trial-guard 600`
experiment, and `mu300-update` keeps that segment. 33e made init honour a guard only in a trial boot, but a boot
from Android with mu300-linux is exactly that. The generic ramdisk segment, which every update appends behind the
device segment, now carries an empty `etc/mu300-trial-guard` (a later file replaces an earlier one), and an
experiment's guard goes into a segment of its own behind the generic one.

### 33i. A reboot "with the hotspot off" that never brought it back

Reported: after rebooting from mu300-toolkit because the hotspot was on, SSH was gone. The toolkit's "join a
network" offers exactly that reboot when the radio is the access point (this driver cannot turn an AP back into a
station), and `wifi-client scan-mode on` left `/etc/mu300/wifi-scan-mode` in place until a network was joined: the
hotspot stayed off at that boot and at every boot after, and whoever had come in over it had no way back but USB.
The flag is now taken at boot into `/run` (mu300-wifi-scan-mode.service), for that boot only, a transient timer
brings the hotspot back after 10 minutes when nothing was joined, and the toolkit says before the reboot that a
session over the hotspot ends there and where to come back. Newer-release notes at login came in the same change.

### 33j. Two devices restored from one backup

A second F50 restored from the first one's backup came up with the same `androidboot.serialno` (the bootloader
reads it from the restored data), so 33b's gadget identity was the same on both: the same USB serial number and
the same host MAC. macOS gave the one network interface to whichever enumerated last, and the other had none.
init now adds the eMMC's serial (`androidboot.emmcid`, which the bootloader passes on both boards; it is the
product serial field of the eMMC's CID, hex characters 21-28): the USB serial number is
`MU300LINUX-<serial>-<emmc serial>` and the MACs are `02:50:<md5 of both>:<subnet>:0x`. Not read from the CID in
`/sys` when the argument is missing: init sets up USB before the modules that find the eMMC are loaded (and under
mainline the eMMC may or may not be there yet), so the identity would change from boot to boot; without the argument
it is the serial number alone, as before.

Decided for every device, not only for clones (a device cannot tell it is one): after this update each computer sees
a new network adapter once - macOS sets up a new interface by itself (measured on the U30 Air and an F50: an address
45-48 s after the reboot), Windows installs the adapter again and may ask once more which kind of network it is on,
and a computer that kept a setting for the old adapter (a fixed address, a firewall rule by MAC) has to be told about
the new one.

### 33k. Vendor driver fixes from the U30 Air test, measured

Before and after on the U30 Air (the "before" being the kernels of the overnight test), per boot:

| | before | after |
|---|---|---|
| reboots on 6.18.55 | 1 panic in 5: 855 `sipa_dele get pd fail ret = 1`, soft lockup in `cp_dele_on_commad`, a 68 s shutdown | 20 of 20 clean: no `get pd fail`, no lockup, no new pstore dump, shutdown 20-30 s, mobile data on every boot |
| `cannot create duplicate filename` (sipc debug devices) | 12, with 13 call traces | 0 and 0; the four `/dev/sipc_*` once |
| `br-lan: hw csum failure` (Wi-Fi RX) | 1 per boot | 0 over a boot and ten Wi-Fi joins of a phone |
| IPv6 TCP from a Wi-Fi client to the device's link-local | never connected (the SYN was dropped for its firmware sum) | connects |
| `to free list empty` / `out of time` | 302 / 46 in 5 minutes | 0 / 0 |
| USB ping from a Mac, 100 at 100 ms (NCM) | 4.98 ms | 1.46 ms |

Throughput did not move beyond its spread: phone -> device 537-555 vs 553-571 Mbit/s, device -> phone 424-474 vs
410-453, Mac -> device over USB 337 vs 333, device -> Mac 268 vs 267, both ways at once 190/153 vs 215/148.

* sipa_dele: `pm_runtime_get_sync()` returns 1 for a device already active; the vendor loop took it for a failure
  and retried every millisecond for ever. A failure is now answered with `SMSG_VAL_DELE_REQ_FAIL`. What the CP does
  with that answer to ENABLE is not known (the vendor never sent one), and the failure needs runtime PM switched off
  under a suspended device, which these tests did not produce.
* Wi-Fi RX: the firmware's sum is checked against the frame's pseudo-header and only a match is trusted
  (CHECKSUM_UNNECESSARY); IPv4 options, IPv6 extension headers and a UDP length short of the IP payload are left to
  the stack, since where the firmware starts its sum is not documented.
* Wi-Fi PCIe post-init runs on every power-on of the chip (each hotspot start): 5 restarts, 5 post-inits. Its error
  path, which used to leave the channel table NULL for the next power-on and the failed channel half set up, was
  reviewed, not produced.
* Rejected: the fork's reorder change (its timer was not pushed forward by out-of-order frames before either; the
  change would let a new hole be skipped almost at once, and 20 ms is short for block-ack retries), its CHECKSUM_NONE
  for every frame, and its latency probes.
* Measuring Wi-Fi with an Android phone: flushing the phone's neighbour entry for its gateway made Android give up
  the network and join another saved one; `cmd wifi set-network-selection-config enabled enabled -a 2` keeps it on
  the network it is on while testing (and `-a 0` restores it).

## The second F50

### 34. LEDs, and the defects from a second board's test
A second F50 (restored from F50 #1's backup, with its own eMMC and factory Wi-Fi address) was tested from a user's
point of view; what came out of it, measured on 2026-10-05:

* **LEDs.** The F50 has the PMIC's RGB LED and the keypad backlight sink (`keyboard-backlight`, 0-127), nothing
  else. ZTE's Android (read from `/sys/class/leds` on the second F50, no SIM) lights `sc27xx:red` without service
  and `keyboard-backlight` at 48 while the hotspot is up (0 when it is stopped, 48 again when it starts). The Wi-Fi
  light stayed dark under Linux because `mu300-led` mapped no Wi-Fi LED on the F50. Now: network blue on 4G, white
  (the green channel) on 5G, red without service; Wi-Fi `keyboard-backlight` 48. Every state was driven and read
  back on both F50s; on F50 #1 (OpenWrt) the hotspot switched off and on the way LuCI does it
  (`uci set wireless.ap0.disabled=1; uci commit; reload_config`) gave 48, 0, 48 (`mu300-led wifi sync` from a
  procd reload trigger on `wireless`, which follows wlan0 for two minutes: turned off and on again at once, hostapd
  took 63 s to report AP-ENABLED, and the LED followed within a second).
* **mu300-update.** It already skipped systems at the release's version (`ubuntu: already v2026.10.08`); a
  rollback's `ubuntu.broken` (655 MB) stayed on the disk through every update. `apply` now removes stale
  `<os>.broken` copies, never the running root, before counting free space: used space 2.8 G before, 2.2 G after.
* **Early kernel messages.** `journalctl -k` shows nothing: journald has `ReadKMsg=no`, and `kmsg-forward` writes
  warnings as `journalctl -t kernel`. It also read with `dmesg --follow-new`, so the boot's first seconds (the call
  traces of 6.18) were never written. The first start of a boot now forwards the buffer from its start, with the
  kernel's timestamps: on the second F50 the journal began at `[0.000000]` under 5.4, and had 24 messages from the
  first 3 s under 6.18. A ring buffer that has already wrapped (5.4's vendor chatter wraps it within hours) is lost
  either way; this is about the boot.
* **5.4 Wi-Fi MAC.** The vendor driver takes the address from Android's `/mnt/vendor/wifimac.txt`; under Linux it
  used a random `40:45:da:...` on every boot. It now reads LK's `androidboot.wifimac` from `/chosen/bootargs`, as the
  mainline port does: `5c:7d:ae:b4:0b:d0` (the second F50's bootargs) over two 5.4 boots and a 6.18 one; F50 #1's is
  `5c:7d:ae:b4:0b:be`.

## The third system

### 35. kanoqwq's fixes, measured: openwrt-luci on F50 #1 and the U30 Air

The third system (OpenWrt with the MU300 control panel, built from this branch) was installed next to the systems
already there - F50 #1 on its card (`/openwrt`, `/ubuntu`, now `/openwrt-luci`; kernel 6.18.55, boot image
v2026.10.08), the U30 Air on its internal region (`/ubuntu`, now `/openwrt-luci`; 7.2.9) - with the vendor files,
`hotspot.conf` and the password of the system of the same device, and booted with `mu300-os openwrt-luci`. Both
devices went back to their own system afterwards. The boot images were not replaced: what only a new init does
(K5/K9 early lease from the initramfs, K6 RNDIS, the USB mode the panel saves, K1's "never a kept copy") is
covered by the unit tests, not by these boots. The reboots are soft reboots (F50 #1 cannot be power-cycled
remotely; the U30 Air has a battery), not cold boots.

Two defects showed on the first boot and are fixed:

* `android-vendor-start` (from main, the slot work): `L=$(cat /run/mu300/linux-slot)` under `set -e` ended the
  script when the boot image does not publish that file, before `modem_control`; procd restarted it every 10 s and
  the AT channel never answered (8 restarts in 100 s, `no valid answer to the RIL handshake` every 36 s). Any device
  whose rootfs is newer than its boot image had no modem. Now the slot falls back to the command line.
* Every check of a dead AT owner printed `mu300-at: line 96: can't open /proc/7668/cmdline` into radio.log
  (`tr < /proc/$pid/cmdline 2>/dev/null` reports the failed redirection before its own `2>/dev/null` applies).
  And `mu300-sms` named its lock with `cksum`, which OpenWrt's busybox does not have (`cksum: not found` in the
  panel's SMS details).

Per boot, from `/run/mu300/boot-timeline` and `radio.log` (seconds after the kernel started):

| | F50 #1 (9 boots) | U30 Air (11 boots) |
|---|---|---|
| vendor start -> props (K40, K41: no logdw second) | 0.01 | 0.01 |
| RIL handshake `AT+SMMSWAP=0` answered (K57) | 24.5-25.0, 9/9 OK | 24.9-25.6, 11/11 OK |
| radio on (`CFUN: 1`) after one `AT+SFUN=4` | 28.0-28.6 | 28.6-29.3 |
| registered (K23: within 60 s, "wait modem alive timeout" never) | 30.1-30.7, 0 timeouts | 30.8-31.4, 0 timeouts |
| sipa-dele loaded by the dial (K45-K47) | 35.3-40.9 | 40.0-41.7 |
| address on sipa_eth0 | 37.4-43.1 | 42.1-43.9 |
| radio-warmup done (K20) / its dial waited for it | 31.3-32.7 / yes | 33.5-34.1 / yes |
| hostapd ENABLED, "AP not up, retrying" (K15) | 9/9, 0 | 11/11, 0 |
| nr6/nr7 dashboard daemons (K19), early lock hook cleared (K65) | 9/9, 9/9 | 10/10, 10/10 |
| USB host (macOS) answers ping after the reboot command | 24-27 s, lease 3600 s (preinit, K11) | 24-25 s, lease 3600 s |

A tenth F50 boot hung hard (no USB, back in Android after about 20 minutes, `su -c mu300-linux` brought it back):
the known 6.18 hang of FINDINGS 31m, counted apart. K23 and K57 passed on soft reboots (F50 #1 9 + 1 hang counted
apart, U30 Air 11); cold boots not run (F50 #1 cannot be power-cycled remotely, the U30 Air has a battery). On the U30
Air, ten `ifdown wan; ifup wan` gave the WAN back in
8.15-8.17 s each, `dmesg | grep -ci "cfi\|sipa_dele.*panic"` 0, one `AT+SFUN=4` in the whole run.

* **K4** (region probe through a loop device): busybox `dd` seeks. The probe at the region offset took 0.01-0.04 s
  on the F50 and 0.05-0.08 s (with sudo) on the U30 Air: nothing to win, not taken.
* **K12** (one 100 ms rebind at boot instead of the lease check): macOS got its lease on every boot with both
  running, but the Windows host was not reachable and no Linux USB host was attached, so the gate (three hosts) did
  not pass. The `usb-ready` instance went; `--if-no-lease` and the re-enumeration (K10) stay.
* **K6** (RNDIS in one configuration): not measured, no Windows host; kept (only an explicit RNDIS choice uses it,
  and mainline kernels have no RNDIS, where the saved choice falls back to NCM).
* **K25/K26 early lease on a custom LAN**: with `network.lan.ipaddr=192.168.90.1` the Mac was on 192.168.90.200
  25 s after the reboot command, and on 192.168.77.200 25 s after changing it back.
* **Relay IPv6 (K30, K35-K37) without NDP relay**: the carrier gives a /64 by RA (2a00:1880:a00a:ee32::/64 on the
  F50) and fills `+CGCONTRDP`'s IPv6 address with the interface identifier only (`0.0.0.0.0.0.0.0.24.219...`, the
  prefix zero) and two IPv6 DNS servers (2a00:1880:101:c::1, ::3). The phone on Wi-Fi and the Mac on USB took SLAAC
  addresses in that /64 from the relayed RA; `ndp-learn` routed it to br-lan at metric 128; no /128 route existed
  anywhere. A DNS query over IPv6 from the Mac's SLAAC address to 2a00:1880:101:c::1 was forwarded (nft counters
  1 out, 1 in) and answered. Wider traffic could not be tried: both lines were in the carrier's walled garden (no
  credit: DNS answered, ICMP and HTTP did not, the same under the device's own Ubuntu). The spoofed-NS test was not
  run (no tool to craft one on the LAN side); ndp-learn takes no LAN input at all. `uci show dhcp` has no
  `ndp`/`ndproxy` option. A changed `network.wan.ipv6` reaches `mu300-ndp` only at the next boot, as its header says.
* **SMS (K58, K69)**: sending failed on both lines whatever `AT+CAVIMS` was (`+CMS ERROR: 28` on the U30 Air,
  `313` on the F50, the same with 0 and 1): the lines have no credit, so `AT+CAVIMS=1` is kept (no difference
  measured) and receiving was not tried. `AT+CMGL=4` marks messages read on this modem: on F50 #1's SIM the first
  listing showed 35 as REC UNREAD, the second 35 as REC READ. Since 2026-10-09 the pool moves what it holds off
  the SIM (each slot read back with `AT+CMGR` and deleted only while it still holds the PDU that was pooled, after
  the pool's file is on the disk): a full SIM (35/35 on the U30 Air's) took no more messages, and the second part of
  a long reply then never arrived, so the pool never saw it. On that SIM one sync moved 34 slots off, and the
  missing part of the waiting message arrived within a minute.
* **Update keeps the user's settings (I3)**: on openwrt-luci with the language, theme, `pdptype` and `ipv6` changed,
  mu300-update's `apply_one` with a newer image and a reboot kept all four, and `dhcp` had no NDP option. The device
  check covered those four (91-mu300-luci). The update now keeps the user's network settings too: 90-mu300 is split
  the same way (first-install defaults behind `system.mu300.defaults`; an install from before it is told by wan
  proto `mu300cell`), so the LAN address and mask, `ip6assign`, the APN, hostname, time zone and br-lan's members
  stay as the user set them; flow offloading too, except once on the first update of an install from before the
  marker, which switches it on (`mu300-ttl` turns it off again at boot while a TTL is set). Checked on the U30 Air:
  its openwrt-luci from before the marker, hostname changed to `u30test`, updated by `apply_one` with the new image:
  after the reboot the hostname, LAN address and `ip6assign` 60 were kept, the marker was set, WAN and the Mac's
  lease came up. Open: the pinned USB host entry keeps its address when the LAN moves to another subnet (a later
  fix should re-derive it from the LAN).
* **TTL and the flowtable (K28, R23)**: `mu300-ttl set 64` turned flow offloading off and the sipa_eth0 flowtable
  went (1 -> 0); `off` brought both back.
* **TTL in tc keeps the flowtable (mainline)**: the nft rule sits in postrouting, which an offloaded flow never
  reaches: `nf_flow_offload_ip_hook` (ingress of br-lan) rewrites the packet and hands it to `neigh_xmit` ->
  `dev_queue_xmit` on sipa_eth0. `dev_queue_xmit` still runs clsact's egress hook (`sch_handle_egress`) before the
  qdisc, for every packet whichever way it came, so a `matchall` filter there with `pedit ex munge ip ttl set N pipe
  csum ip` (and `ip6 hoplimit set N`) rewrites offloaded and device-own traffic alike, and flow offloading can stay
  on. Needs `NET_SCH_INGRESS` (clsact), `NET_CLS_ACT`, `NET_CLS_MATCHALL`, `NET_ACT_PEDIT` and `NET_ACT_CSUM`
  (mu300-mainline.config: the last three are modules, loaded one by one - OpenWrt's kmodloader `modprobe` takes one
  module per call) and a `tc` that has pedit's `ex` syntax (OpenWrt's `tc-tiny` 6.18, which sqm-scripts brings,
  does). The 5.4 vendor kernel has no `act_pedit`: there mu300-ttl keeps the nft rule and turns offloading off.
  matchall cannot replace a filter (`tc filter replace` answers EEXIST once one is there), so `apply` deletes its
  own (prefs 10 and 11) and adds them again; the filters belong to each sipa_eth* (all 16 get them), and
  mobile-data's bring-up calls `mu300-ttl apply`. Checked on the U30 Air (7.2.9, openwrt-luci): `set 64` put both
  filters on every sipa_eth*, the counters grew with traffic (538 packets for a 1 MB download), `flow_offloading`
  stayed 1 and no nft table was made; `set 65` changed the key to 0x41; the filters removed by hand came back with
  `ifup wan`; `off` removed them all. The VPN was on during the check, so the forwarded LAN traffic left through
  xray's own sockets rather than an offloaded flow.
* **The panel**: every page (Status, Network locks, SMS, AT terminal, Adapter settings, Device management) in a
  browser set to English, German, Turkish and Chinese on both devices: no Chinese in English, German or Turkish, no
  string of the catalogs left in English in Turkish or Chinese, German shows English. Backend refusals (a bad
  number, an over-long SMS) have Turkish and Chinese entries; a radio switch during a dial answers "busy".

  **Update 2026-10-07:** since PR #48 LuCI and the panel have a language switch. English, Turkish and Chinese are
  in the images, and 46 languages in all come with the `lang` extra (`mu300-extra install lang`, or System >
  Languages in the panel). German now comes from that extra.
* **LEDs (K38, K39, K68)**: not ported here. The F50's lamp states were measured with someone watching and are
  implemented by the f50-leds-fixes work (FINDINGS 34); the fork's boot chase, lamp switches and LED page
  follow that branch.

### 36. Power profiles: idle radios, the charging boot, the charge guard

The U30 Air ran flat in a day or two of hotspot use. Two causes, both seen before: the charger IC charged on its
power-on defaults and was never told anything (33d; the bq256xx driver of PR #55 now drives it, so the guard below has
a node to write), and a boot that Android's LK started because a charger was plugged in ("charger mode") came up as a
full hotspot with the modem dialling, in a pocket. `mu300-power` (one `/bin/sh` script, `mu300-power.service` or
`/etc/init.d/mu300-power`) answers both. Design: `docs/superpowers/specs/2026-10-06-power-profiles-design.md`.

What was built:

* **Profiles** `plugged`, `battery`, `saver`, picked automatically (saver below `SAVER_BELOW` % on battery, by the
  fuel gauge's `capacity` only) or forced with `mu300-power profile NAME`. Each has four knobs: `WIFI_IDLE` (minutes
  without a client, 0 never), `RADIO_IDLE` `keep|lte|off`, `LEDS_IDLE` `on|off`, `CPU` `full|eco`. Defaults: plugged
  `0 keep on full`, battery `10 off off full`, saver `5 off off eco`. A bad value in `/etc/mu300/power.conf` counts as
  the default and `status` names it.
* **Idle** is "no Wi-Fi station, no USB host, no key press" for `WIFI_IDLE` minutes. Then the hotspot goes down, the
  LEDs follow `LEDS_IDLE`, and the modem follows `RADIO_IDLE`: `mobile-data suspend lte` only switches EN-DC off with
  `AT+SPENDC=2` (the lock adapter's measured "off" value; no stack restart, the data connection is untouched) and
  `resume` restores `AT+SPENDC=1` only if EN-DC was on before; `suspend off` is the radio off (`AT+SFUN=5`) with data
  down, and `resume` runs `radio_on` and redials itself; `mobile-data up` refuses to dial while the modem is
  suspended `off`, except from `resume`. On OpenWrt the daemon runs with `MU300_NETIFD=1`, so `suspend off` is
  `ifdown wan` before `AT+SFUN=5` and `resume` redials with `ifup wan`: netifd keeps owning the WAN's address,
  route, firewall, DNS and IPv6. Idle wakes on a key, a computer on USB, a Wi-Fi station, or plugging in (the edge
  battery -> plugged, not being plugged: idle on the charger, a forced profile and the battery-less F50 stay idle).
  Every wake brings the hotspot up first, then the LEDs and the CPU, then the modem, whose dial can take minutes.
* **State** is kept across daemon restarts within a boot. The daemon's TERM trap wakes the radios without a dial
  (`mobile-data resume nodial`: the radio on, the watcher redials) and does nothing during a shutdown (the held
  power key and the low-battery poweroff leave `/run/mu300/power/shutdown`; Ubuntu also says `stopping`). The
  units keep a 150 s stop timeout (`TimeoutStopSec=150`, procd `term_timeout 150`) for the radio lock. A failed
  action is logged and retried by the following loops.
* **Charging boot**: `init` writes `/run/mu300/boot-mode` and, in a charger boot, `/run/mu300/charging-boot`. The
  Ubuntu hotspot and mobile-data units skip on that file; the daemon enters the charging boot only on its first start
  of a boot, and leaves it only by the Wi-Fi key (`mu300-power wake wifi`; a computer on USB or the power key does
  not). It powers the device off only unplugged (no charger online, no extcon `USB=1`, the battery not `Charging`),
  below 5 % for three loops in a row, never on one sample. OpenWrt's early radio warm-up skips a charging boot.
* **Charge guard**: charging off at battery `temp` above 45.0 C or below 0 C, on again below 40.0 C and above 3.0 C;
  with `CHARGE_TO=80` off at 80 % and on below 75 %. It writes the bq256xx charger's `charge_type` (`N/A` off,
  `Fast` on). bq256xx reads `N/A` whenever it is not charging, so `Fast` is written only when the guard itself turned
  charging off (`/run/mu300/power/charge-off`); the driver resets its switch at probe, so a marker lost with `/run`
  leaves nothing off. It logs only when that marker changes, and a failed write turns the guard off for the boot
  with one log line. No reading means no change.
* **Panel**: System -> Power on `openwrt-luci` (state, profile, knobs, charge limit), catalogs in all 31 languages.

Method for the numbers: `mu300-power log 5 /tmp/power.csv` writes `epoch,mV,mA,mW,capacity,temp,state,profile` every 5 s.
Each row is a 3-minute run unplugged, the hotspot idle (a client associated, no traffic) unless the row says
otherwise, `mu300-power set` or the verbs between runs. The fuel gauge's `current_now` is negative when
discharging; the draw is the mean of the run's mA (and W) after the first 30 s. Android's own idle figure comes from
`dumpsys battery` / the same gauge on the Android side for the target line.

| Row | What is on | Measured (mean W) | Measured on |
|---|---|---|---|
| baseline | everything, as before the profiles | pending | pending |
| LEDs off | baseline with the LEDs dark (`mu300-led idle`) | pending | pending |
| hotspot off | modem on, Wi-Fi off | pending | pending |
| LTE only | EN-DC off (`mobile-data suspend lte`), hotspot on | pending | pending |
| modem off | `AT+SFUN=5`, hotspot on | pending | pending |
| all off | idle: hotspot, modem and LEDs off, the floor | pending | pending |
| eco | `CPU=eco` on the baseline | pending | pending |
| Android idle | the stock firmware at rest (the target) | pending | pending |

What the defaults rest on: not on these numbers (there are none yet) but on the design. Radios are what drains a
hotspot with nobody connected, so `battery` and `saver` switch them off after a few minutes; `plugged` keeps
everything because the supply covers it; saver is the profile with the CPU in `eco`. The thresholds (45/40 C, 0/3 C,
5 % for three loops) follow the spec; the fuel gauge reports `capacity=100` at 3.88 V today (33d), which is why
nothing acts on the voltage. The table is filled in by the device series, with the date of each run.

Open questions for the device:

* Does `AT+SPENDC=2` without a stack restart really drop the NR leg (check `AT+SPENDC?` and the band readings), or
  only after the next attach?
* Does procd's `term_timeout` apply on this OpenWrt build (that `/etc/init.d/mu300-power stop` waits for the wake
  rather than being killed at the default timeout)?
* What the bq256xx `charge_type` node does on writes: `N/A` stops charging, `Fast` resumes it, or the driver
  rewrites it from its own state.
* The unit tests ran under dash and bash on the dev host; busybox ash (the shell on OpenWrt) has not run them there.

**The device-test incident (2026-10-07, U30 Air, OpenWrt).** A measurement script took the device down with the raw
actions while `mu300-power`'s state still said `active`: `mu300-led idle on`, `wifi down`, `mobile-data suspend lte`,
`mobile-data suspend off`. The last one never returned and the script's later steps never ran; `mu300-power log`
stopped writing at the same moment. Every key press then did nothing: `mu300-power wake` only left a flag for the
daemon, which saw `active` and had nothing to do, and `mu300-led wake` lit nothing under the idle flag. Every LED
dark, no reaction to any key, for hours - a device that looks powered off. xray meanwhile ran out of its 1024
descriptors (`accept4: too many open files`) with the modem off and needed a restart.

Why `suspend off` did not return, from the code (no device access for the analysis; the steps of `suspend off` after
`suspend lte`, as of 4e62326): `do_suspend off` first resumes `lte` (`resume` -> `under_radio_lock resume_lte_raw`),
then `down` (the script ran by hand, so without `MU300_NETIFD=1`: the systemd path, `ip`/`nft` on `sipa_eth0`
behind netifd's back), then `under_radio_lock suspend_off_raw`, then one line to stderr. Every wait in it is bounded
but long: the radio lock 120 s twice, each `mu300-at` call up to 90 s for the client lock plus `T + 31` s of budget
(`AT+SPENDC=1` 126 s, `AT+CGACT=0` 41 s with its 5 s lock wait, `AT+SFUN=5` 131 s) - about 9 minutes at worst, not
hours. What is not bounded: the direct-tty path when no AT daemon runs (the `open` and `write` of the SIPC tty block
in the driver; the drain loops of `mobile-data`'s `at()` and of `mu300-at` read for as long as the channel talks);
`ip`, `nft` and the `disable_ipv6` write, which wait on the RTNL lock behind an OpenWrt `wifi down` (it returns at
once and netifd tears the AP down afterwards; a Wi-Fi driver stuck in that teardown holds RTNL); and the write of the
final message to a terminal that is gone. The last fits all three symptoms: the script ran in an SSH session, and an
SSH session over the hotspot dies with `wifi down` (over the WAN, with `suspend off`). The server side notices only
when TCP gives up (~15 min of retransmissions with dropbear's defaults), and until then a write that fills the pty
blocks; then it hangs up, and SIGHUP stops the script and every job of the session - `log` among them - wherever they
are. A `suspend off` stopped that way leaves the mode file `off` and the "down" flag, so the watcher stands aside
for good, and nothing else ever looked. The most likely cause is therefore the dead session, with the RTNL wait as
the second candidate; which one it was can be read on the device next time (`ps` for a `mobile-data` still there,
its `/proc/PID/stack` and `wchan`; `logread` for the session's end).

What changed (the design: bootability and "a key always shows life" over everything else):

* **Keys always show life.** `mu300-buttons` runs `mu300-led wake` first on every press, before it looks at any
  state, and `mu300-power wake` after it in the background. `mu300-led wake` lights the LEDs for `LED_TIMEOUT`
  (a minute when it is 0) under the idle flag too; `sleep --if-due` puts them out again while idle. No daemon is
  involved.
* **Wake by inspection.** `mu300-power wake` restores whatever is down by looking, not by the state file, and
  needs no daemon: the AP down (no `hostapd.wlan0` on ubus / `mu300-hotspot` not active) and wanted -> up; the
  modem's mode file -> `mobile-data resume`; the LED idle flag -> `mu300-led idle off`; `cpu7` offline -> online,
  and eco's own 1.5 GHz cap on `policy4` -> `cpuinfo_max_freq` (another cap is the toolkit's or thermal-guard's and
  is left, and nothing is lifted under thermal-guard's alarm); the VPN if mu300-power stopped it; then `active`.
  The daemon's own wake is the same function. One idle entry or restore runs at a time (`/run/mu300/power/busy`,
  a dead or stale holder is taken over); a second wake while one restores returns at once. The panel's wake runs it
  in the background (rpcd ends a call at 30 s).
* **Nothing can hang.** Every external step of `mu300-power` runs under a deadline (a background job, a watchdog
  that kills the job's whole process tree, and a USR1 to the waiting shell for a child stuck in the kernel; busybox
  has no `timeout` in `/bin`): probes 5 s, LEDs 10 s, wifi/systemctl/VPN 30 s, the modem 90 s, the background LED
  sync 150 s (`MU300_POWER_*_DEADLINE`). The tree is stopped until a look finds nothing new, then every process
  any look saw is killed (one reparented between two looks too). `mobile-data suspend|resume` end within
  `MU300_SUSPEND_DEADLINE` (60 s) whatever the modem does: AT through `mu300-at` with `-t` <= 20, a 10 s
  client-lock wait and a 22 s budget (`MU300_AT_LOCK_WAIT`, `MU300_AT_BUDGET`), the radio lock 20 s, each external
  step 15 s; HUP ignored; their output goes through a file and a bounded write. On a failure or a timeout they
  leave the files consistent - no mode file, no "down" flag of their own - so the watcher restores whatever is off,
  and they exit non-zero. An `lte` step that failed (also an `AT+SPENDC=1` answered ERROR or not at all: only OK
  counts, as `mu300-at` exits 0 on ERROR) leaves `/run/mu300-mobile-data.endc-restore` (unless EN-DC was off
  before): every `resume` sends `AT+SPENDC=1` until it answers OK, and mu300-power's wake and self-check call
  `resume` while it is there; the watcher ignores it. The Wi-Fi key's toggles run in the background under a
  deadline too, and the hold's direction (is the hotspot up?) is asked within 5 s
  (`MU300_BUTTONS_PROBE_DEADLINE`): no answer counts as down, and the key turns it on. On OpenWrt they go through
  netifd (`ifdown`/`ifup wan`) also when run by hand.
* **The VPN while the modem is off.** `RADIO_IDLE=off` stops `mu300-vpn` (systemd or procd) once the modem is off,
  if it was running (`/run/mu300/power/vpn-stopped`; a suspend that keeps failing never touches it, and a Wi-Fi
  client uplink keeps it), and the wake starts it again before the modem, so a `KILL_SWITCH=0` dial is never ahead
  of it - unless the service was disabled or `ENABLE=0` meanwhile (asked through `mu300-vpn enabled`, which prints
  `ENABLE` and touches no network; a probe that fails or times out counts as wanted); a start that failed is
  retried by the self-check at most every 120 s; `lte` leaves it alone. The service stop keeps the kill switch
  (`nft table inet mu300_vpn` stays; only `ENABLE=0` and `mu300-vpn off` remove it), and the engine's routes
  go with the engine: with `KILL_SWITCH=1` nothing unmarked leaves on `sipa_eth*` or the Wi-Fi client while it is
  stopped; with `KILL_SWITCH=0` nothing holds traffic back, as on any stop, and the bearer is down anyway. Both
  service definitions raise the descriptor limit to 65536 (`LimitNOFILE`, procd `limits nofile`).
* **Self-check.** Each loop, while the state says `active`: a modem mode file, or (with `WIFI_IDLE=0`) the hotspot
  down although nobody turned it off on purpose, is logged and restored. On purpose means the Wi-Fi key's hold
  (`mu300-buttons` writes `/run/mu300/power/hotspot-off` with the hold's uptime before the wake of that press
  starts, until the next hold; a marker older than the toggle's deadline + 30 s (180 s) is dropped once the hotspot
  is seen up), UCI (`wireless.@wifi-iface[0].disabled` or `wireless.@wifi-device[0].disabled` = 1: the panel,
  `wifi-client`), the unit disabled on Ubuntu, a Wi-Fi client (`/run/mu300-wifi-client.active`) or the scan-mode
  boot. A hotspot that idle took down (`hotspot-idled`) comes back whatever a hold marker says, but not for a Wi-Fi
  client or in scan mode. The hotspot is not looked at in the first 120 s of a boot nor within 120 s of any
  `hotspot on`; one that does not stay up is retried at a doubling interval up to 30 min, logged once per step. A
  modem left with EN-DC off is resumed too, and a VPN left stopped is started (see above).

For measurements this means: the raw actions by hand are undone by the daemon's next loop (the modem) and by any key.
Use `mu300-power idle` and the profiles, or stop the daemon first, and run long measurements under `nohup` or
`setsid` with the output in a file, never through the session the hotspot carries.

### 37. System suspend

Can mainline sleep the way Android idles - the AP asleep, the modem awake? Tested on F50-B (6.18.55, Ubuntu,
USB-powered, the SIM without service: `+CEREG: 2,8`) on 2026-10-06 with the config change of branch
`suspend-spike` (`CONFIG_SUSPEND`, `PM_DEBUG`, `PM_ADVANCED_DEBUG`, `PM_SLEEP_DEBUG`, `PM_WAKELOCKS`,
`PM_AUTOSLEEP` - autosleep built, off - and the tick change below). Short answer: **yes, the firmware does it**;
what stood in the way was three drivers and one config default (all fixed below, in the follow-up).

**The firmware.** `/sys/kernel/debug/psci` on the release kernel already says `SYSTEM_SUSPEND is supported`
(PSCI v1.0 under the DT's `arm,psci-0.2`). The vendor 5.4 kernel has no platform suspend driver either; mainline's
`psci_init_system_suspend()` registers `mem`. With the options: `/sys/power/state` = `freeze mem`,
`/sys/power/mem_sleep` = `s2idle [deep]`.

**Results** (`rtcwake -s 20`; `pm_test` stages first):

| run | result |
|---|---|
| `freeze`, pm_test=freezer / `mem`, pm_test=devices | return after 5 s, everything works afterwards |
| `mem`, pm_test=processors, **periodic tick** | **panic**: hard lockup on CPU1 after the CPUs came back, board restarted by itself |
| one CPU offline/online, periodic tick, no suspend | the same panic: the CPU's timers never fire again |
| `mem` processors / core, **NO_HZ_IDLE + HIGH_RES_TIMERS** | return after 5 s |
| `freeze` (s2idle), Wi-Fi up | returns at once: the PCIe WAKE# irq calls `pm_wakeup_hard_event()` during noirq suspend |
| s2idle, Wi-Fi up, PCIe `power/wakeup` disabled | **20 s** (1.08 s, a WAKE# wakeup, back to sleep, 18.97 s), RTC wake through the PMIC irq (23); USB network, Wi-Fi client, AT, Bluetooth all fine |
| `mem` (PSCI SYSTEM_SUSPEND), Wi-Fi up | **returns after 0.43 s**: Marlin3 pulls WAKE# low right after its L2 entry; USB, Wi-Fi, AT, BT fine |
| `mem`, Wi-Fi and BT closed | **19.94 s asleep**, RTC wake (IRQ 23); USB, AT, BT fine; **Wi-Fi does not come back** |
| s2idle, Wi-Fi closed | 20 s; Wi-Fi does not come back either |

So PSCI SYSTEM_SUSPEND enters and returns, the DDR content survives, the CPUs come back, and the modem keeps
running across it (AT answers at once, `sprd-mpm` sees its channels awake, no modem restart). No callback failed
(`suspend_stats`: 0 failures in every run) and no `Call trace` outside the two panics.

**The tick.** allnoconfig leaves `HZ_PERIODIC` (250 Hz) without high-resolution timers. cpuidle's power-down
states stop the local timer, so `cpuidle_register_driver()` puts every CPU into the *periodic* broadcast once
(`tick_broadcast_mask: ff`, all `arch_sys_timer` shut down, the `sprd_timer` IPIs the tick to all eight CPUs).
`tick_broadcast_offline()` takes a CPU out of that mask and nothing puts it back when it comes online; without
`TICK_ONESHOT`, `tick_broadcast_enter()` still lets it into the power-down state, and it never gets a timer
interrupt again (`arch_timer` count frozen, `taskset -c 7 sleep 1` never returns, the buddy watchdog panics
~30 s later). Suspend takes CPUs 1-7 down and up, so it hit this every time. `NO_HZ_IDLE` + `HIGH_RES_TIMERS`
(arm64's defconfig) gives the one-shot broadcast that is armed on every idle entry: hotplug and suspend work.
It also stops waking all eight CPUs 250 times a second at idle; its effect on idle power was not measured here.

**What broke in the spike** (the PCIe WAKE#, Wi-Fi after a suspend, the PMIC watchdog) was taken apart on
branch `suspend-drivers` (2026-10-06/07, F50-B, the same kernel plus the changes below; logs in `/root/susp2/`).
Two of the spike's conclusions were wrong, and the table above reads differently with what was found:

* **WAKE# was the firmware's debug log.** wcn_bsp's `sprd_ep_resume()` sends `at+armlog=1` after every resume
  (vendor code), and its sysfs default turns the log on at every chip power-on; `wifi-start`'s `at+armlog=0` did
  not outlive the next power-on (Bluetooth's start powers the chip up again). With the log on, the firmware pulls
  WAKE# within 0-2 s of every L2 entry to push log packets. Measured with PCIe wakeup enabled and Wi-Fi up:
  log on, `mem` returned after 1.0-1.3 s (`pm_wakeup_irq` 18, the WAKE# line); `echo 0 > armlog_status`, the
  full 20 s, woken by the RTC; the next resume turned the log on again and the sleep after it returned after
  4 s. Fixed in wcn_bsp: the log is off by default and the resume leaves it as it was (`echo 1 >
  /sys/devices/virtual/misc/wcn/devices/armlog_status` turns it on for debugging). Three `mem` runs in a row
  with Wi-Fi up and PCIe wakeup enabled then slept the full 20 s.
* **"Wi-Fi does not come back after a suspend while it was closed" was a suspend while it was *open*.**
  Without a WoWLAN configuration cfg80211's `wiphy_suspend()` closes every interface (`cfg80211_leave_all`: the
  P2P device's `CMD_CLOSE`, the station's `CMD_DISCONNECT`), and the WCN PCI function, which suspends
  asynchronously, had usually taken the bus down by then: both commands were dropped (`send [CMD_CLOSE] fail
  because bus done`), the firmware kept them open, and the driver thought them closed. Wi-Fi itself reconnected
  after the resume. The *next close and open of Wi-Fi* - with or without a suspend in between - then got the
  firmware assert (`WCN Assert in mchn.c line 137 ... get_wcn_bus_ops, chn10`), after which the chip is in
  "card dump" and only a reboot helps. In the spike the Wi-Fi-up runs came first, so the closed-Wi-Fi runs got
  the blame. Reproduced on demand: a Wi-Fi-up `mem`, then `ip link set wlan0 down/up` and no second suspend:
  assert. On a chip with no Wi-Fi-up suspend since its power-on, sleeps with Wi-Fi closed (Bluetooth on) were
  fine three times out of three (`mem`, s2idle, `mem`), and so was one with the chip off (Wi-Fi and Bluetooth
  closed). `iw phy phy0 wowlan enable any` before the sleep avoided the assert, which proved the mechanism.
  Fixed in sprd_wlan_combo: WoWLAN "any" is configured when the wiphy registers, so cfg80211 leaves the
  interfaces as they are, and the firmware learns about the sleep through the PCIe channel's `power_notify`
  (`CMD_POWER_SAVE`), as before. The station stays associated across the sleep (no reconnect); a hotspot stays an
  access point. `iw phy phy0 wowlan disable` brings the old behaviour back. A device link that orders the WCN
  platform device's suspend before the PCI function's was tried first: the commands then reached the firmware,
  but the queued disconnect made `power_notify` refuse the suspend (`Q not empty suspend not allowed`, -EBUSY)
  and the next sleep ended with `CMD_SET_REGDOM` timeouts and an assert; dropped.

**Fixed, measured on F50-B** (6.18.55, these changes; each run `rtcwake`, `pm_wakeup_irq` 23 = the RTC):

| run | result |
|---|---|
| idle, release kernel (periodic tick) | arch_timer 0/s, timer broadcast IPIs **1725/s**, sprd_timer 246/s, all IRQs 2162/s (20 s, twice) |
| idle, NO_HZ_IDLE + HIGH_RES_TIMERS | arch_timer 400-520/s, broadcast IPIs **112-120/s**, sprd_timer 170/s, all IRQs **980-1125/s** |
| `cpu7` offline/online ×3, then CPUs 1-6 at once | no lockup, `taskset -c N sleep` returns on every CPU (release kernel: panic) |
| `mem` 20 s, Wi-Fi client up | woken by the modem after 11.5 s (see wake sources); Wi-Fi associated, ping fine |
| `mem` 90 s, Wi-Fi up, radio off (`AT+CFUN=4`) | **91.1 s asleep, no reset**; the PMIC watchdog counts again afterwards (CTRL 0xa, counter running) |
| `mem` 120 s, Wi-Fi up | 120.8 s, Wi-Fi associated, ping fine |
| `mem` ×2, Wi-Fi up, then wlan0 down/up | no `bus done`, no assert, Wi-Fi rejoins |
| Wi-Fi closed (BT on): `mem` and s2idle, then open | no assert, Wi-Fi rejoins, ping fine |
| s2idle 20 s, Wi-Fi up | 21.3 s, RTC |
| `mem` 20 s, hotspot (AP) up | 21.2 s; still an AP on channel 36 with hostapd running (no client was at hand to associate) |
| `mem`, Wi-Fi up, PCIe `power/wakeup` enabled | woken by WAKE# after ~1 s: with WoWLAN "any" the firmware wakes the host for traffic, as asked |

The rest:

* **The PMIC watchdog** (`ump9620-pmic-wdt`) keeps counting while the AP sleeps. It is now stopped in its
  `suspend_noirq` callback, if it was running, and loaded with a fresh count and started again in `resume_noirq`
  - what the vendor's `sprd_wdt` does for the AP watchdog. A hang in the last suspend steps or the first resume
  steps is not covered; the vendor accepts the same window.
* **pcie-sprd's WAKE#** is no longer `IRQF_NO_SUSPEND` and wake-armed for good: `pm_wakeup_hard_event()` only when
  `device_may_wakeup()`, the line is disabled for the sleep like any other and unlazily (`IRQ_DISABLE_UNLAZY`), so
  that it is masked in the EIC - PSCI SYSTEM_SUSPEND returns on any interrupt that reaches the GIC, whatever the
  kernel thinks of it - and armed (`enable_irq_wake`) only when `power/wakeup` is enabled. It is off by default:
  `echo enabled > /sys/devices/platform/soc/26100000.pcie/power/wakeup` makes Wi-Fi traffic wake the device.
  With it off the firmware's WAKE# request waits for the resume (`wake# value:1, wake down count:N` in the log).
* `ums9620-ipa-sys-pd: power off maybe failed` on every suspend, harmless; the USB gadget drops for the sleep
  (`br-lan: port usb0 disabled`) and comes back.
* The PM debug options cost nothing at runtime: `pm_print_times` and `pm_debug_messages` are 0 by default, so a
  suspend logs what it logged before; they stay (pm_test).

**Wake sources.** The RTC (PMIC irq 23) every time. **The modem wakes `mem` by itself**: the mailbox irq is
`IRQF_NO_SUSPEND`, as in the vendor 5.4 driver, and its interrupt reaches the GIC, which ends PSCI
SYSTEM_SUSPEND; no change was needed. With the radio on, the first sleeps ended after 11.5, 20 and 11.7 s on
`irq read smsg: dst=5, channel=6, type=4` (the AT channel's sbuf event): the modem's unsolicited `+CSQ`/`+CESQ`
signal reports on `stty_nr0`, every few seconds, and `mobile-data`'s registration poll (`up`, every 2 s, while
there is no service). With `AT+CFUN=4` the sleep ran to the alarm. A long sleep with the radio on needs those
reports off (what Android's RIL does on screen-off) - for `mu300-power`, not the kernel. Not tested yet (needs a
hand or a SIM with service): the power key (it shares the PMIC irq 23 with the RTC), a USB plug (a PMIC EIC
line), an incoming SMS (a `+CMTI` URC on the same channel as the reports, so it should).

**What `mu300-power` can rely on:** `mem` with Wi-Fi up, down or the chip off; Wi-Fi as it was afterwards; sleeps
longer than the PMIC watchdog's 60 s; PCIe wakeup as an opt-in. What it has to arrange: the modem's signal
reports and the mobile-data poll off before a long sleep, or the modem wakes the device every 10-20 s.

**Not measured:** power. The F50 has no battery; the U30 Air (fuel gauge) is where suspend's saving can be
measured, unplugged.

Logs of every run stayed on F50-B under `/root/susp/` (the spike: `*.log`, dmesg before/after, `/proc/interrupts`,
the two panic records) and `/root/susp2/` (the follow-up, with the scripts that ran them). F50-B was left on the
6.18.55 build of branch `suspend-drivers` (radio on, Wi-Fi client, one more 20 s `mem` checked). The 7.2.9
build of the branch compiles, kernel and all modules; it has not been booted yet.

## Users' reports

### 38. Three defects from users' reports, 2026-10-07

Three issues came in with their own measurements, two of them with the fix; what follows is what was taken from
them, checked against the code, and what the release carries.

#### 38a. A read past the end of the eMMC never returns (#43, #52, #65)

Every installer probes the free region for an existing `mu300root` with three tiny reads of its superblock:
`dd if=/dev/block/mmcblk0 bs=1 skip=$((OFF + 1080)) count=2`, where `OFF` is the first 2 MiB boundary behind
the last partition, and once more at the fixed offset of the first releases, 27762098176. On the F50 of #65 the
partition table ends 2 MiB before the end of the eMMC (61079552 sectors, the last partition ends at 61075456), so
the first boundary behind it *is* the end of the disk, the last boundary before the backup GPT lies before it,
and `region_probe`'s arithmetic gave a region of -4 MiB (the same number issue #32 had seen) whose superblock
starts 2 bytes past the last sector. The eMMC driver of this device never completes a read past its end: the
`dd` stays runnable at 100 % of one core, survives `kill -9`, and every retry adds another one - four of them
held the SoC at 97 °C in #65 until a reboot. #52 (the Magisk installer, OpenWrt to the card) showed the same
`dd` at byte 31272731704, which is that very offset; #43 had pinned the installer's silence to
`region_find_existing` without seeing why. The legacy offset is the same trap on the 32 GB variant: it lies
beyond that eMMC altogether and was read all the same.

Fixed in `tools/storage.sh` (`region_find_existing`, which `install.sh` and the Magisk installer share, and
`region_on_disk`, which the probe loops of `uninstall.sh` and `tools/reset-password.sh` call), in `install.ps1` and
in `uninstall.ps1` (`RegionOnDisk`): a region whose boundaries cross is an empty one (`SIZE=0`; the installers
then offer the card or the repartitioning, as they do for any region that is too small), and a candidate
superblock is read only when it lies on the disk. The SD-card installation of
#52 and #65 goes through without a single read past the end. `tests/test_installer.py` (`Region`) runs the
layout of #65 against the functions and checks that no `dd` crosses the disk's last byte.

Not taken from #65: a wall-clock limit around every device command in `install.ps1`, and a port of
`sd_release` to the host side. The card is released on the device, by `tools/android-install.sh`, before
anything is written to it (both installers run that script); the reads before it only look at the card. The
limit is worth having for the day another request is lost, but it is the larger change and is not needed once
nothing is read past the end.

#### 38b. RNDIS: the port kept the bridge's address (#45)

An OpenWrt system installed with NCM (the default) and switched to RNDIS later has `usb0` in its bridge section
and not `rndis0`; the LAN hook (`hotplug.d/iface/10-mu300-usb`, K9/K27) puts `rndis0` into `br-lan` on every LAN
ifup. It did that *after* the loop that takes the early server's address off the bridge's ports, and that loop
only looks at ports: `rndis0` was not one yet, kept `192.168.77.1/24`, and then became a port - the bridge and
one of its ports with the same address, two equal routes, and the device could not reach its own Wi-Fi client
nor the USB host, with the serial console the only way in. MRWOODEN measured it on an F50 (6.18, `openwrt-luci`,
Windows without `UsbNcm.sys`) and sent the fix: join first, then take the address off; and after the hook's own
re-enumeration of the gadget (K10) put the gadget netdevs back into the bridge, in case the rebind left one bare
(with a configfs gadget the netdev is made with the function and should survive an UDC rebind, so this is a
guard, not a mechanism that was seen; netifd would re-add a port it has in its configuration, `usb0`, and never
one it never had). Applied as sent, except that only a netdev that was a port before the rebind is made one
again: a user who took `usb0` out of `br-lan` for an interface of its own keeps it that way. With the regression
tests (`test_early_dhcp`: the RNDIS netdev that is not a port yet; the `usb0` that is not a port stays out). Verified on the reporter's device: `br-lan` the only holder of the address, both the Wi-Fi client and the
USB host served by the one `dnsmasq`, `rndis0` still a port after the rebind.

#### 38c. fw4 on 5.4: the boot ruleset without the LAN, and a reload that always fails (#67, #61)

AgentFan0315 took a fresh `openwrt-luci` on 5.4 (v2026.10.11) apart layer by layer: Wi-Fi and USB clients
associate, their DHCP requests enter the kernel (an ingress counter on `wlan0` climbs), and die before any rule:
the live `inet fw4` table has no `iifname "br-lan" jump input_lan` and no `srcnat_wan` jump, while `fw4 print`
renders both. Two things stack:

1. fw4 renders a zone's rules from the devices its networks have *at the time*. S19 `firewall` runs before S20
   `network`, so at boot neither `br-lan` nor the modem's `sipa_eth0` exists, and the LAN's input rules and
   the wan's masquerade are left out of the first ruleset - to be filled in by the reload that every ifup
   triggers (`hotplug.d/iface/20-firewall`). That is how plain OpenWrt works too.
2. On 5.4 that reload fails. fw4 replaces its ruleset in one transaction (`flush table inet fw4`, or `delete
   flowtable inet fw4 ft`, then the table again with its flowtable `ft`). The 5.4 kernel refuses a flowtable that
   names a device another flowtable of the same table has, and it counts the one the same transaction has just
   deleted: that one leaves the table's list only at the commit, and 5.4's `nf_tables_newflowtable` walks the
   list without regard to the pending deletion (the check skips inactive entries from 5.13 on). `flowtable ft {
   ... } Error: Resource busy`, the whole transaction is rejected, and the S19 ruleset stays. The flowtable exists
   from S19 on because the `earlyusb` zone names `usb0`, which init has made by then, and fw4 puts every zone
   device that exists into `ft` (a device without a `/sys/class/net` entry is left out, see
   `openwrt/patches/fw4-sipa-offload.patch`; that is what makes naming `br-lan` and `sipa_eth0` in the zones
   safe at S19). The first ruleset is therefore the one with the flowtable and without the LAN, and nothing
   after it can replace it. Deleting the flowtable on its own (`nft delete flowtable inet fw4 ft`), in a
   transaction that is committed before the reload, is enough: the reload then creates it afresh.

So the LAN had no DHCP, no LuCI and no NAT on every boot of a 5.4 `openwrt-luci`, which is also what #61 reports
(installed with 5.4 and the panel: detected as a USB network, "no ssh and no webui", Wi-Fi visible but nothing
connects; the serial console at `ttyGS0` is the way to `mu300-next-boot android` in that state). The mainline
kernels update a flowtable in place and were never affected, which is why the maintainer's own tests (31, 35,
on 6.18 and 7.2) did not see it.

Two fixes, both in `openwrt/overlay`:

* `uci-defaults/90-mu300` names the devices of the `lan` and `wan` zones (`br-lan`, `sipa_eth0`) next to their
  networks, once, on every system (the reporter's workaround, the pattern of the `earlyusb` zone): the S19
  ruleset is complete whatever the reloads do. Verified by the reporter across reboots.
* `hotplug.d/iface/19-mu300-fw4`, on a 5.4 kernel only, deletes the stale flowtable right before 20-firewall's
  reload, under the same conditions 20-firewall reloads on: an ifup of an interface that is in a zone. The reload
  succeeds; the offloaded flows of the moment take the ordinary path until the flowtable is back.

Not covered by those two on 5.4: a reload that is not an ifup's - the firewall saved in LuCI, `fw4 reload` or
`fw4 restart` by hand, a package's reload (PassWall2, #95), and `mu300-vpn`'s own `/etc/init.d/firewall reload`
after it adds the tunnel to the wan zone. Since #95 the flowtable is deleted from fw4's own path:
`openwrt/patches/fw4-old-kernel-flowtable.patch` makes `/sbin/fw4` delete `inet fw4 ft` in a transaction of its
own before `start`/`reload` apply the ruleset and before `restart` checks it, on kernels before 5.13 only. Turning
software flow offloading off is no longer needed for that; it would cost the fast path on the one kernel that has
none other.

#### 38d. Reports that were already fixed, or are not defects

* #20 (soft lockup in `sipa_dele`, `get pd fail ret = 1` at 149 lines a second, 6.18.54 of 2026-09-28): the
  vendor loop that retried `pm_runtime_get_sync()` every millisecond and took its `1` (already active) for a
  failure - §31f, fixed on 2026-10-05 and in v2026.10.11's 6.18 bundle.
* #64 (IPv6: relay or NAT66?): both, on purpose. The `openwrt-luci` system relays the carrier's RA and DHCPv6 to
  the LAN (clients get public addresses from the bearer's /64) *and* masquerades v6 egress through the device's
  own address (`masq6`, `91-mu300-luci`, K30), because the carrier routes one address per bearer and replies to a
  client's public address would otherwise not come back; `ndp-learn` routes the /64 to `br-lan` for the same
  reason. The `masq '1'` of the wan zone is IPv4 only (fw4's `masq6` is the v6 one). Plain OpenWrt keeps `extend`
  and neither.

#### 38e. Relay IPv6 after the carrier renumbers (#87)

Reported on a carrier that gives one /64 by RA on `sipa_eth0` (`dhcp.lan` ra and dhcpv6 relay, a second OpenWrt
relaying behind the device): after the carrier's /64 changes, LAN clients keep addresses from every earlier /64, and
IPv6 over the relayed public addresses fails (connections hang) while NAT66 from the ULA works; `ifdown`/`ifup` of wan
brings it back for a while. Read in the code, not measured on a device:

* `ndp-learn` routed one /64 to `br-lan`: the first sipa_eth0 global address `/proc/net/if_inet6` listed. A PDP
  re-activation that `mu300cell-v6.sh` rides out without an ifdown (+CGEV, `refresh_bearer`) leaves the old SLAAC
  address on `sipa_eth0` beside the new one (only setup and teardown flush; the carrier measured in `mu300cell.sh`
  gives infinite lifetimes), so after such a renumber the LAN route could stay on the old /64 while odhcpd relays the
  new RA and clients SLAAC in the new one: every NAT66 reply to them left by the bearer. A wan restart flushes the old
  address, which matches the report. Fixed: `ndp-learn` routes every /64 the bearer holds and drops the route of one
  that left.
* Nothing withdraws an old /64 from the LAN. odhcpd in relay mode forwards the upstream RA's prefix options with their
  lifetimes as they are (it only rewrites the L, A and P flags, the source link-layer address, DNS and MTU;
  `forward_router_advertisement` in `src/router.c`) and keeps no prefix state, and the carrier sends nothing for a
  prefix of a previous PDP context. Clients keep such addresses for the lifetime the carrier gave, and a client that
  picks one as its source gets no NAT66 replies once the /64 has left the bearer (no route to `br-lan`). A deprecating
  RA (preferred lifetime 0) for the old /64 would have to be sent by the device itself; there is no tool on the image
  for that today. Open, to measure on a device: `ip -6 addr show dev sipa_eth0` and `ip -6 route show dev br-lan`
  before and after a renumber (with and without a wan restart), and on the LAN `tcpdump -i br-lan -vv icmp6 and
  ip6[40]=134` for the prefix options and lifetimes the relayed RA carries.
