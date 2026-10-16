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
| 24c | What the Rongyue E5 (kanoqwq/e5-linux) did, and what of it applies here | ported; untested with firmware |
| 25 | SC2355 Bluetooth on BlueZ | current |
| 31 | Ubuntu on 6.18, and what it takes | current (kernel now 6.18.56) |
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
| 31p | BTF and eBPF for dae, and the tracing that broke boots | current; the writer at ~11.5 s is open |
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
| 39 | The SMS pool: durable before the SIM lets go, long messages that never complete, forwarding | current |
| 40 | The boot chain of the Linux slot: what is loaded per slot, and what the installers copy | current; not yet run on a device whose slots differ |
| 38 | Three defects from users' reports, 2026-10-07 | current |
| 38a | A read past the end of the eMMC never returns | current (fixed) |
| 38b | RNDIS: the port kept the bridge's address | current (fixed) |
| 38c | fw4 on 5.4: the boot ruleset without the LAN, and a reload that always fails | current (fixed at boot; a reload by hand still needs the flowtable deleted first) |
| 40 | One stuck AT command wedged the control panel; a second per AT command on OpenWrt | current (fixed) |
| 41 | The vendor daemons' own account | current |
| 42 | No access point on a DFS channel (user report, 2026-10-11) | current |
| 43 | adb over USB to Linux: adbd in the gadget, and what FunctionFS does to the rest of it | current; the default (off) and who is let in (keys only): superseded by §70 |
| 44 | Network namespaces on 5.4: the vendor's fragment sysctl, torn down by the wrong namespace (#103) | current (fixed) |
| 45 | `rmmod sprd_wlan_combo` panicked in `__run_timers` (issue #146) | current (fixed) |
| 46 | SMS sends failed with IMS "Busy Everywhere" until the SMSC was written back; the panel lost slow sends (#176) | current (fixed) |
| 47 | A system the Magisk zip added beside another had a password nobody saw (#167) | current (fixed) |
| 48 | The stock virtual thermal zone on mainline (`mu300_thermal`), and thermal-guard's handoff to the kernel | current (F50-B, 7.2.10); U30 Air and 6.18 on a board untested |
| 49 | The SIM's own number in the panel: CNUM, else the IMS identity, on full rounds only | current (U30 Air, Vodafone TR: CNUM answers) |
| 50 | Three guards for the installers: the boot image read back from the medium, bounded SD-card stages, no re-run in the same boot | current; the timeout path not yet seen on a device |
| 51 | SMS delivered directly (+CMT), acknowledged only once the pool has it; the SIM path stays as the fallback | current |
| 52 | The lock reset deleted the saved locks whether or not the modem took them: a verified reset | current (fixed) |
| 53 | A carrier name shown as hex: UCS2 from a modem whose character set is not UCS2 (#174) | current (fixed; unit tests and a user's report, not measured on our boards) |
| 54 | A webhook body of the user's own for SMS forwarding: values escaped for the type, never evaluated (#171) | current (unit tests; not sent from a device to a real service) |
| 55 | Imported Android files nobody but root could read: the CP was never loaded (#127, #135, #170) | current (fixed; what differed between #170's boots is not known) |
| 56 | The VPN page showed a refused config without its reason; the engines' own defects are in the VPN module's FINDINGS 26i-26m | current (fixed; measured on the U30 Air) |
| 57 | A 64 GB unit whose partition table has `userdata` filling the disk, and no way to make room from Windows (#32) | current (fixed; the erase of Android's data superseded by §112; unit tests against a table built from #9's figures, not measured on a device) |
| 58 | A service's own error in an HTTP 200 answer to the SMS webhook: a KEY=VALUE check of the answer; a button that clears the delivery log (#171) | current (unit tests; measured on the U30 Air against a fake webhook, not against the real services) |
| 60 | `/run` takes files from every user: the daemons' directories there are checked, and a squatted name is put out of the way (review of #145/#149) | current (fixed for mu300-atd and mu300-voice, F50-B on 5.4 and 7.2.10); `/run` itself is still 1777 |
| 63 | A reused SMS reference number mixed long messages, or kept them from ever being joined; a part delivered again | current (fixed; unit tests only, not measured on a device) |
| 64 | An update dropped the panel's saved locks (`/etc/unisoc-modem`) | current (fixed; unit tests only, not reproduced on a device) |
| 65 | An APN with a user name and a password (`AT+CGPCO`), and what else kanoqwq's APN page does | current (unit tests only; never sent to a modem) |
| 66 | The OpenWrt image build tries a package download again | current (unit tests only; no image built with it) |
| 70 | adb to Linux on by default and open to every computer: the owner's decision, the exposure, and the state that decides it | current (unit tests; nothing of it measured on a device: the checklist is in the section) |
| 71 | A graphical installer that drives the text installers: an answers mode, a progress stream, a window; a beta question; where a Python with a usable Tk is found | current (run against an F50 from a Mac on 2026-10-15: check, backup, installs and uninstalls from the text installer and from the window; the U30 Air, a locked bootloader, Linux and Windows hosts not measured; Windows only by CI) |
| 72 | The web installer: adb over WebUSB, how the release files reach the device, WebUSB per platform, and what a closed tab leaves | current; run end to end on an F50 from Chrome on macOS on 2026-10-13 (docs/web-installer.md), the real release mirror from Node on 2026-10-15; Windows, a Linux host, the U30 Air, KernelSU/APatch and a download over a carrier's network not measured |
| 74 | The U30 Air's second SIM: what two units showed, and the selector built on it (PR #73/#166, #194) | current (the maintainer's U30 Air on 7.2.10 and the contributor's on 7.2.9); two working cards, kernel 5.4 and an F50 not run |
| 80 | WPA3 on the U30 Air's access point: the SC2355 firmware does SAE itself (PR #74, Snrat) | experimental, opt-in build recipe (7.2.9; 7.2.10 without a client); PMK provenance open; the WPA2 fallback measured on the U30 Air |
| 81 | An update that brought another mu300-update ended with "another mu300-update is running": the lock was held by the first half's own keep-alive | current (fixed; found on the F50 updating v2026.10.23 to v2026.10.24) |
| 82 | adb on by default, and no OpenWrt had it after a boot: the service gave up 13 s after power-on, before FunctionFS could be had | current (fixed; measured on the F50, openwrt-luci, 7.2.10) |
| 83 | An update dropped the jobs of OpenWrt's System > Scheduled Tasks (`/etc/crontabs`) | current (fixed; a user's report of the symptom, unit tests only) |
| 85 | An update keeps everything the user made: the image's manifest tells its files from the user's, one carry block for `mu300-update`, the installers and the Magisk zip, and never less protected than the user left it | current (unit tests, real release images in containers, and the device protocol on a U30 Air, openwrt-luci, and an F50, Ubuntu, 2026-10-16, with two unpublished signed releases of the branch: everything carried; two defects fixed; the Android path not run) |
| 86 | Updating from the panel: System > Update, an update from a file (a release's Magisk zip), and release signatures (`SHA256SUMS.sig`) | current (unit tests, a page test under Node, the commands in the image's container; the device protocol run on a U30 Air on openwrt-luci, 2026-10-15; F50 and Ubuntu not run) |
| 90 | The data watchdog took a modem that did not answer for a lost bearer, and redialled a working connection (after kanoqwq's 3cbf37fc) | current (fixed; measured on the U30 Air, openwrt-luci v2026.10.27, 6.18.56, 2026-10-15; the OpenWrt watchdog's messages now reach the log) |
| 91 | The relay monitor read SIM1's bearer in a dual-SIM boot on SIM2, believed any +CGCONTRDP, and dropped the hint after a burst (after kanoqwq's 3cbf37fc) | current (fixed; SIM1 measured on the U30 Air, openwrt-luci v2026.10.27, relay mode, 2026-10-15; the SIM2 choice only under the device's shell, no dual-SIM boot) |
| 92 | Three Wi-Fi TX log lines written once per frame; the AP multicast "endian fix" not taken (after kanoqwq's 3cbf37fc) | current (mainline module only; measured on the F50 with 7.2.10 and the U30 Air with 6.18.56, 2026-10-15; the multicast question not measured) |
| 93 | sdhci-sprd started ADMA transfers with relaxed MMIO: the descriptors were not ordered before the command (after kanoqwq's 0438ab01) | current (mainline kernels; eMMC soak on the F50 with 7.2.10 and the U30 Air with 6.18.56, 2026-10-15: clean, HS400ES, throughput unchanged; the SD slot not tested, no card) |
| 95 | The ZTE V50 (MU3351), experimental: how it is told apart, and what kano measured on his (f6b0668d, 0438ab01) | experimental; nothing of it measured by this project (no V50 here): unit tests, the device trees of an F50 and a U30 Air, both mainline kernels built |
| 100 | `mu300-next-boot`: the default boot written before misc was, and a re-arm that could undo a switch (kanoqwq 1f8f03fb) | current (fixed; measured on the F50, Ubuntu 24.04, and the U30 Air, openwrt-luci, both v2026.10.27, 2026-10-15) |
| 101 | The Magisk switch built its misc block under a fixed name in the adb shell user's directory | current (fixed; measured on the F50, Android with Magisk, 2026-10-15; the U30 Air's sysfs name read from Linux) |
| 102 | Mobile data TX: a full IPA FIFO pushed another Ethernet header at every retry; IRQ flags in a static (kanoqwq 149c9d2a) | current (fixed; run on the F50 with 7.2.10 and the U30 Air with 6.18.56, 2026-10-15: the busy path is every IPA resume; no difference visible on the device) |
| 103 | Wi-Fi TX on the SC2355 (mainline): a freed skb used on, AP IPv6 multicast refused in bursts, a full EDMA ring counted as failure (kanoqwq 149c9d2a) | current (fixed; measured on the F50 with 7.2.10 and the U30 Air with 6.18.56, 2026-10-15: the multicast refusals gone, the full ring backpressure; one Wi-Fi client only) |
| 110 | The web installer as a device manager: one checked entry point on the device (mu300-api), the page over it | current (unit and Node tests against the real mu300-api; the device protocol run with the page's modules over WebUSB on a U30 Air, openwrt-luci, and an F50, Ubuntu, both v2026.10.27, 2026-10-16: six defects fixed; rows 6, 9, 16 and the Android restart not run) |
| 111 | One zip, two ways in: Magisk on the device, or unpacked on a computer as the computer's installer (kano's two-entry package, `f6b0668d`); adb not bundled | current (unit and integration tests, the release's real zips built both ways and compared; no install from an unpacked zip on a device) |
| 112 | Making room by a reset, and the installation that resumes afterwards: kano's transaction, Android's recovery formats the encrypted `userdata`, the checks of the resumed run (`f6b0668d`, `0e19fe32`) | experimental; unit tests and tests against fakes (a fake eMMC); not run on a device, here or by kano |
| 120 | Data roaming: a switch of our own in the dial and its watchdog (no switch of the modem's is known), the network's word for roaming, and a test hook | current (unit tests; checklist items 1-5 run on a U30 Air, openwrt-luci, and an F50, Ubuntu, both v2026.10.27, 2026-10-15, through the test hook; no SIM that really roams) |
| 125 | Release names: the day of the release and its number (`vYYYY.MM.DD.N`), newer than every three-field tag; one comparer per language against one table; what the updaters and installers up to v2026.10.27 do with them | current (unit tests in sh, Python, JavaScript and PowerShell; the old clients read from their code, not run) |

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
     from vendor `init*.rc`), because `modem_control` drops to uid `system` (1000). (On a distribution it starts as
     the account `mu300vnd` instead and the nodes are that account's: 41.)
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
  * `install.sh` (and `install.ps1`, #57) offers it when there is no room, asks how many GiB to give Linux and
    keeps at least 4 GiB for Android and 800 MiB for Linux, and requires ERASE to be typed. `uninstall.sh` offers to grow it back, off
    by default because on the 64 GB variant that would hand the factory gap to Android.
    `tools/resize-last-partition.py` does the edit: it validates both GPT copies and every CRC first, refuses
    if the named partition is not the last one, and re-reads what it produced before handing it over. The
    backup GPT is written before the primary, so a power cut between the two leaves the old table and a device
    that still boots.
  * **It rewrites the partition table and erases everything in Android.** Take a full backup first
    (`tools/backup-device.sh`), and treat the path as experimental: it has been done by hand on one device.
  * (2026-10-15) Android's data is no longer cleared by the installer: Android's own recovery is asked to reset it,
    and the installation resumes after the reset (§112).

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
* Android's uid `system` (1000) is also Ubuntu's first user, so modem device nodes showed up as owned by `ubuntu` -
  writable by it, the modem's calibration among them. Fixed in 41: they are the vendor account's (`mu300vnd`) now.

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

**Update 2026-10-12: "Reboot to start the updated openwrt-luci" when a reboot starts Android.** A U30 Air with
Linux on slot a (Android on b) was updated v2026.10.17 -> v2026.10.20 from a Linux boot, and the reboot went to
Android. The image was fine: `/etc/mu300/default-boot` said `android` (the device had been switched to Android by
hand earlier), so that boot was itself a one-shot trial armed from Android, and the init log of it says exactly
that - `stage=misc-restored` (init writing Android's slot block back, §1) and no `stage=default-boot-linux`, with
`.mu300/boot-tries` at 0 (no backstop ever fired; the updated kernel had come up in 4.9 s). `mu300-update`'s
`--trial` is a quiet no-op in that state (`mu300-next-boot` answers "default boot is not linux, nothing to do" and
exits 0), and its last line still promised a reboot. Now `mu300-next-boot --trial` exits 3 when there is nothing to
arm and 1 when it can only write the initramfs' one-shot block (one boot, not N, §32); `mu300-update` says both, and
what it prints last after a boot image, a system or a kernel changed is how to start Linux by hand (`mu300-linux`)
instead of a reboot that goes the other way.

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

### 24c. What the Rongyue E5 (kanoqwq/e5-linux) did, and what of it applies here
kano's [e5-linux](https://github.com/kanoqwq/e5-linux) (MIT) runs Linux on the Rongyue E5, a UMS9621 handset with the
same AGDSP, VBC v4, MCDT and UMP9620 codec drivers. It started from this project's bring-up (its `e5-audio-dsp` is
`mu300-audio-dsp` adapted) and got further: the speaker plays (2026-09-25), the microphone records, and a cellular
call's downlink was heard on the receiver and the speaker (2026-10-02, e5-linux FINDINGS 55). Read against 24 and
24b, the differences fall in three groups.

**The board, which does not carry over.** The E5 has its own AGDSP image (`l_agdsp_a`, mmcblk0p26, header
`SharkL5_AUDCP_2023Y_VER_3029`) and a complete device tree (`memory-region` present), a speaker behind an aw87xxx,
an earpiece and microphones. Its audible call goes DSP -> codec DAC0 -> receiver / AO; this board has nothing on the
codec, so that output does not exist here.

**The kernel, which does.** Five of its 5.15 patches touch the same drivers this project builds for 5.4, and the
symptoms they fix are the ones in 24:
* `0013` period events from an hrtimer. The E5 measured what 24 measured - both `sprd_dma` lines at 0 for a whole
  stream, with or without the DSP - and concluded that nothing will ever call `snd_pcm_period_elapsed()`: the
  completion interrupt is the DSP's or nobody's. Its answer is the one Android's HAL gets by opening with
  `PCM_NOIRQ`: program the DMA without interrupts and tick the period from a timer.
  `kernel/patches/audio-pcm-period-timer.patch`.
* `0016` the position read only while `agdsp_can_access()` says the AGCP domain is reachable - the bus hang of 24,
  hit on the E5 after six idle hours. `audio-pcm-pointer-agcp-access.patch`.
* `0017`, `0019`, `0020` the DSP front ends limited to S16_LE where the DSP writes S16 whatever was asked, and to
  interleaved access on every MCDT front end. `audio-fe-dai-formats.patch`.
`kernel/build-audio.sh` applies all three; the 23 modules build with them (2026-10-11). Its other patches are E5
board matters (aw87xxx, a headset IMPD oops, the agdsp_pd module order of its tree, which is built in here).

Its notes also contradict one line of 24: there `agdsp_access_en` "changed nothing"; on the E5 it is the control
that turned "the DMA runs one burst and stops" into "the VBC FIFO drains" (e5-linux FINDINGS 24.2), with
`VBC DAC0 DG Set` non-zero (Linux leaves it 0, which is digital silence). With the period timer both need
re-measuring here before either reading is trusted.

**The call sequence, which does.** What the E5 changed between "both PCMs RUNNING, silence" and "heard" (`402fde1`,
`8e9b8a4`, `2c726fc`), against what `mu300-voice` did:

| | mu300-voice until now | e5-linux |
|---|---|---|
| call scene | `FE_VOICE` playback only, 16 kHz | `FE_ST_VOICE` playback **and** capture, 8 kHz mono, both prepared before either starts |
| profile select | `(mode << 24) \| (0x5e << 16)`, through amixer | `(mode << 24) \| (mode << 16) \| 5` (param id = mode, low byte the voice DAI), raw, before and after the start |
| voice volume | not set | `VBC_VOLUME` = volume + 1, raw (the control declares max -1, amixer clamps) |
| downlink mute | not touched | `VBC_DL_MUTE` enable during routing, then `VBC DAC1 DSP MDG` 0,1024 and `VBC_DL_MUTE` disable after the start - the change that made it audible |
| bandwidth | none | `/dev/audio_pipe_voice` command 0 channel 2 gives NB/WB/SWB/FB; the profile follows it |

Two of these are bugs here on their own: amixer clamps every profile select from mode 16 up - the Bluetooth modes
(BTHS, 28 and up) included - to `0x0fffffff`, and a capture-less scene leaves the DSP without an uplink, which is
the VoLTE ~20 s drop of 24b. `mu300-voice audio start` now does the E5's sequence; the undo log puts every control
back on `audio stop`.

**Bluetooth, which is the output this board has.** kano reports that the F50 under Android, with the AGDSP image of
a ZTE Voyage 41S (the donor of 24), connects a Bluetooth headset and carries calls on it. That fits: this board's
PSKey has `g_sys_sco_transmit_mode = 0`, and on the E5's identical controller mode 0 sends SCO audio over the
controller's PCM pins into VBC IIS3, not over HCI (e5-linux FINDINGS 58-59: no HCI SCO RX, nonzero samples on the
IIS3 capture once the pin matrix was switched). The vendor route (`audio_route.xml`, `bt_sco` and `btsco_p/_c`)
is `SYS_IIS0 = vbc_iis3`, `S_VOICE_P_BT` / `S_VOICE_C_BT`, `VBC_SRC_BT_DAC/ADC`, and the E5 found the BT rate must
be set again after the scene is RUNNING. Two of its findings matter here: on mainline `SYS_IIS0` was a no-op without
the pin controller (the 5.4 kernel has `pinctrl-sprd-qogirn6pro`), and BlueZ's own SCO path stays silent with this
PSKey, so the AP must not try to carry SCO audio itself.

What a call on a headset needs from the AP is therefore only the links: the DSP scene (`mu300-voice audio start bt`)
and an HFP audio gateway holding the service level connection and the SCO link. BlueZ has no AG of its own (oFono
would want the modem), so `tools/hfp` (`mu300-hfp`) is a minimal one on raw kernel sockets: it connects to the paired
headset, answers the AT setup, opens CVSD SCO when told, and turns the headset's buttons into `ATA` / `AT+CHUP`.
`mu300-voice watch` follows `AT+CLCC` and drives both. The AGDSP image stays the user's to supply:
`mu300-audio-dsp install FILE` checks size and the `AUDCP` header and records the sha256 on the device.

Not measured yet, for want of the firmware on any test board: whether the 41S image runs the BT call scene under
Linux, and whether the period timer moves `FE_VOICE_PCM_P` / `FE_VOICE_C`.

2026-10-13, against v2026.10.23: the seven audio patches apply to the pristine realme tree in `build-audio.sh`'s
order and all 23 modules build against the 5.4 tree (`sprd-dmaengine-pcm` with its `period_timer` parameter); they
were not loaded on a board - the released 5.4 kernel has no audio modules, and no test board has the firmware. On
F50-B the userspace was run on the released 5.4 and on 7.2.10: without the drivers `mu300-voice` says that this
kernel has no call audio (it used to say "run mu300-audio-dsp load", which cannot work there), `mu300-hfp` refuses
an address that is not bonded, and nothing is left running. The call itself, on a headset or through the taps, is
still unmeasured.

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

**Why the CD GPIO was out of reach, and the empty slot's log noise (issue #181).** Mainline's `gpio-eic-sprd.c`
maps at most three banks of eight lines per controller (`SPRD_EIC_MAX_BANK 3`, the SC9860's layout); the UMS9620's
sync controller lists six banks in its `reg` (`0x2000c0`, `0x2100c0` ... `0x2500c0`, Unisoc's `qogirn6pro.dtsi`),
so the chip came up with 24 lines and line 35 (the fifth bank) was rejected by `of_gpio_simple_xlate()`: the GPIO
lookup never found a chip and reported `-EPROBE_DEFER` for ever. Unisoc's 5.4 driver has `SPRD_EIC_MAX_BANK 8`
(that is the "Got CD GPIO" of the 5.4 log). The fallback above (drop `cd-gpios`, `MMC_CAP_NEEDS_POLL`) is what made
the empty slot noisy: `sdhci-sprd` has `SDHCI_QUIRK_BROKEN_CARD_DETECTION`, with which `sdhci_get_cd()` answers
"present" whenever no CD GPIO is set, so every one-second poll ran a card initialisation (CMD0, CMD8, CMD55 ...)
against nothing; a command the controller gives up on still produces a late command interrupt after the core has
finished the request, and `sdhci_cmd_irq()` logs those at error level with a register dump ("Got command interrupt
0x00000001 even though no command operation was in progress", `Cmd 0x371a` = CMD55, `0x081a` = CMD8, `Resp[0]
0xffffffff`): 19 dumps in 9 minutes on the F50 under 7.2.10, none with a card in, none on the U30 Air (no slot).
`upstream/patches/0014-gpio-eic-sprd-eight-EIC-banks.patch` raises the limit to Unisoc's 8 (nothing else in the
driver depends on it: the bank count comes from `reg`, the interrupt handler walks the banks the chip has), so
`mmc_of_parse()` finds the line at the first try, the port's fallback does not run, and the core requests the EIC
line's interrupt (both edges; the sync EIC supports `IRQ_TYPE_EDGE_BOTH`) instead of polling: an empty slot is not
touched after the one rescan at start, which `mmc_gpio_get_cd()` ends before any command. Expected on the device:
`gpiochip3` with 48 lines, no "MU300: CD GPIO deferred" line, `cd-gpios` still in `/proc/device-tree`, no "Got
command interrupt" dump, the slot's interrupt counter at rest, and a card inserted later found by the interrupt
(the stuck-busy loop of the polled slot above may or may not recur: it needs the test by hand).

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

### 31p. BTF and eBPF for dae, and the tracing that broke boots
dae (github.com/daeuniverse/dae, an eBPF transparent proxy; tested v2.1.1, linux-arm64, checksum from its
release) needs kernel 5.17 or newer, BTF and a list of BPF options. Neither mainline kernel had BTF or the BPF
JIT, and dae v2.1.1 refused to start on v2026.10.18's 7.2.9: `load eBPF objects: ... program
tproxy_lan_ingress_l2: load program: invalid argument: callbacks are not allowed in non-JITed programs`. The 5.4
kernel is too old for dae and was not changed.

Now in `mu300-mainline.config`, for both kernels: `DEBUG_INFO_DWARF5`, `DEBUG_INFO_BTF`, `DEBUG_INFO_BTF_MODULES`,
`MODULE_ALLOW_BTF_MISMATCH` (a module with bad BTF still loads), `BPF_JIT`, `BPF_STREAM_PARSER`, `NET_INGRESS`,
`NET_EGRESS` and `NETKIT` (dae's preferred `dae0` pair; it uses a veth pair without it). The DWARF is compressed
(`DEBUG_INFO_COMPRESSED_ZSTD`): vmlinux is 157 MB instead of 312 MB, and two build trees fit in one docker
volume again. The build image has `dwarves` (pahole 1.31 on Ubuntu 26.04), and `build-modules.sh` now runs
`strip --strip-debug` on the out-of-tree modules, which keeps their `.BTF`; without it every vendor module carries
megabytes of DWARF.

**Not taken: kprobes and tracing.** dae's list also has `KPROBES`, `KPROBE_EVENTS` and `BPF_EVENTS` (with
`PERF_EVENTS` and `FTRACE` under them). With them, 7.2.9 came up 14 times in a row on F50-B and failed the 15th
boot, then 21 times and failed the 22nd: 2 failures in 36 reboots. Both times the same thing at the same moment,
about 11.5 s after start, as the modem's `kbc_start_cp` ran in Trusty and the Wi-Fi card's first PCIe scan
failed as usual (`Device found, but not active`): page tables and the printk buffer overwritten (`Bad page map`
with self-referencing PTEs, faults in `vfs_read`, `jbd2_write_access_granted`, `get_data`, and in both boots a
fault at the same address `ffffffffffad82a0`), a panic, and LK's watchdog dumps until the board fell back to
Android about 20 minutes later. Without the tracing group, the same kernel came up 47 of 47 times (6.18: 16 of 16); stock
v2026.10.18 7.2.9 did 100 of 100 the day before. What writes there is not known. The tracing options change where
early allocations land rather than doing anything at 11.5 s themselves, so this looks like a DMA write (modem or
Wi-Fi) into memory the kernel owns, which another kernel layout may hit too; a kernel change that moves the early
allocations needs a reboot loop of 40 or more. What dae loses without them: `dae trace`, the kprobe that accounts
for its sockmap TCP offload (the fentry variant needs the function tracer), and `bpf_get_current_task` for
process names in cgroup programs (it logs a warning and uses `bpf_get_current_comm`).

dae on F50-B (Ubuntu 24.04, Wi-Fi client of a home network, `wan_interface: wlan0`, a shadowsocks node on the Mac
over USB LAN; the oracle-arm test server was not reachable because the Mac's tailnet was logged out): it loads in
1.2 s, creates the netkit pair `dae0`/`dae0peer` "via netlink API (performance mode)", and holds 14 `SCHED_CLS`, 4
`CGROUP_SOCK_ADDR` (connect4/6, sendmsg4/6) and 2 `CGROUP_SOCK` programs, 21 maps, tcx links on `wlan0` (ingress,
egress) and `dae0`, and 6 cgroup links. `curl https://ifconfig.me` answered 200 and the shadowsocks server logged
`established tcp tunnel ... <-> 34.160.111.145:443` for each request; 50 MB from Cloudflare came at 16.5 MB/s
through dae and the proxy, 20.0 MB/s direct once dae was stopped (`dae0` removed with it). The same test passed on
the kernel without tracing, with the warning above.

Measured (Image as built, before `wrap-image.py` adds 1.5 MiB; memory 20 s after boot on F50-B):

| | 6.18.55 v2026.10.18 | 6.18.55 BTF | 7.2.9 v2026.10.18 | 7.2.9 BTF + tracing | 7.2.9 BTF |
|---|---|---|---|---|---|
| Image (bytes) | 17 512 456 | 21 649 416 | 18 069 512 | 26 925 064 | 22 337 544 |
| of it `.BTF` | - | 4 019 543 | - | 4 875 150 | 4 104 758 |
| modules in the bundle | 20.3 MiB | 23.8 MiB | 21.9 MiB | 34.6 MiB | 25.7 MiB |
| ramdisk segment (bytes) | 1 776 099 | 1 832 495 | 1 777 340 | 1 836 866 | 1 833 918 |
| MemTotal (kB) | | 1 501 344 | 1 455 776 | 1 447 840 | 1 451 616 |
| MemAvailable (kB) | | 1 312 360-1 321 424 | 1 270 356-1 274 324 | 1 249 648-1 264 200 | 1 254 696-1 288 712 |
| kernel boot (systemd-analyze) | | | 5.25 s | 5.40 s | 5.34 s |
| reboots on F50-B | 100/100 (10-10) | 16/16 | 100/100 (10-10) | 34/36 | 47/47 |

So BTF costs about 4 MiB of RAM (it is read-only data, in `rodata`: 3028K before, 7060K after) and the boot is
0.1 s slower; the modules' own BTF is about 4.4 MB on disk. The boot image (header, wrapped 7.2 kernel 23.9 MB,
F50-B's device ramdisk 6.5 MB, generic segment 1.8 MB) is 32.3 MB: under the 48 MiB where init keeps its
persistent log in the same partition (64 MiB), with about 18 MB to spare.

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

### 32c. Packages installed on the device, and the settings they left behind (#116)

An update puts the release's image in place and keeps `/etc/config` (OpenWrt) and `/etc/mu300`. Packages added on
the device (`apk add`) were gone afterwards and their settings stayed. A user with OpenClash lost the internet: while
it runs, OpenClash points dnsmasq at itself (`dhcp.@dnsmasq[0].server=127.0.0.1#7874`, `noresolv=1`; its init
script, `change_dnsmasq`) and reverts that when it stops, but the update had copied `/etc/config/dhcp` while it was
running. The new system had dnsmasq forwarding to a port nothing listened on: no DNS. Its own `/etc/config/openclash`
was inert without the program; fw4 skips an include whose path is missing (`openclash`'s is in `/var/etc`). Argon's
theme entry in `/etc/config/luci` stayed and pointed at files that were gone.

Since then `mu300-update apply` and the installers' update write down what was added (OpenWrt: `/etc/apk/world`;
Ubuntu: dpkg's packages apt did not pull in) less the image's own list (`/etc/mu300/image-packages`, written at build
time; older systems: the new image's world and `packages.txt`), move those packages' own `etc/config` files to
`/etc/mu300/orphaned-config/` (never one the new image has), and `mu300-user-packages` installs them again at the
first boot and puts the files back. A LuCI theme whose files are not there goes off LuCI's list. The DNS leftover is
handled fail-closed (DNS privacy first; for some users the internet is only usable through the VPN): after the
reinstall step, a loopback forwarder is touched only when its port is a value in the set-aside settings of a recorded
package that is definitively absent (failed in the feeds, given up, skipped), nothing binds it over a window of
looks, the project's own settings do not name it and the VPN is off - and then only when another server stays. The
only forwarder is reported (status, the login note) and stays: `mu300-user-packages repair-dns` removes it on request
and only then lets dnsmasq use the connection's resolvers (the file as it was:
`orphaned-config/etc/config/dhcp.before-dns-repair`). Tested in a container of the openwrt-luci rootfs with real apk and uci; no device test
recorded yet.

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

### 33l. The charge limit, a Type-C source's current, and the Wi-Fi phy's address (a community build reviewed)

A community build for the U30 Air, `v2026.10.15-charge2` by oswaldxdd (github.com/oswaldxdd/mu300-linux, tag
`v2026.10.15-charge2`, commit 321f771: a snapshot of the source under `experimental/u30air-charge2/source`, the
same files as its release zip), replaced the U30 Air's 7.2 charging with its own stack: a native SGM41511 driver
with the stock JEITA tables and a kernel-enforced 0-100 % limit, a 1655-line fuel gauge with capacity learning
(records hashed to the eMMC CID), and Unisoc's whole Type-C/PD/TCPM stack (about 8800 lines of vendor code). Its
sources are GPL with their headers. What was taken, and how:

- **The charge limit**, as a feature of mu300-power rather than of a second charger driver: `CHARGE_TO` is any
  whole number 0-100. 1-99 stops charging at N % and starts it again under N-5 (at once when the limit was changed);
  0 never charges, the device runs on the charger; 100 lets go at once. The build's 0 % held the battery for good,
  but the SGM41511 still supplements a load its input does not cover from the battery, so on a 500 mA port the
  battery would drain to the cut-off while plugged in: the guard never holds it under 5 %. The temperature guard
  keeps the last word. `mu300-power charge-limit [N]`; System > Power has a number field (U30 Air only).
- **A Type-C source's current.** BC1.2 sees a hub or splitter with a charger behind it as an SDP: 500 mA. The build
  got the source's offer from the TCPM stack. Only one register of it is needed: the UMP9620's Type-C block (typec@380,
  no driver here) runs its state machine on its own, and STATUS (+0x1c) holds the state in bits 4:0 (2: attached as
  a sink) and the source's Rp in bits 7:6 (1: 1.5 A, 2: 3 A). Patch 0012 makes bq256xx take the larger of BC1.2's
  current and the Rp's (3 A taken as 2 A). On the Mac's USB-C port (an SDP) the status read 0x6082 (sink, 3 A): input
  2000 mA, the battery charging at 1.6 A instead of 0.36 A. Right after a USB role change the block was still in
  attach-wait (0x6001) when the VBUS event came, so the read waits up to 1.5 s for the attach.
- **USB host on outside power.** `mu300-usb host` refused while something powered the port. With a splitter (charger
  and a USB network adapter on one port) that is the case to support: host with the boost left off.
- **The Wi-Fi phy's address** (`/sys/class/ieee80211/phy0/macaddress`) was all zeros; it is now the factory address
  LK passes (the one wlan0 had already), on both boards.

Left out: the native charger and fuel gauge (they replace patches 0006/0009-0011, which are tested, for 7.2 only and
for every 7.2 kernel - the F50 runs the same one), capacity learning and the 0.1 % display (a full learning cycle
was not verified by its author), the TCPM stack (PD at 5 V gives nothing over the Rp read), and the build's mu300-usb,
which drops the boost and with it host mode on battery.

### 33m. The ABSSV U30 Air's charger bus under mainline, and a pin controller (issue #102)

A second U30 Air firmware variant, `U30Air_ABSSV1.0.0B14` (chip id `UMS9620-AB`; ours is `SSV1.0.0B14`): under
6.18/7.2 the charger never binds (`bq256xx-charger 6-006b: error -19: no charger: -5`, an I2C NACK on the first
register read), the battery discharges on the cable, and under Android and the project's 5.4 kernel the same unit
charges. Bus 2 (the NFC tag) works in the same boot, so the I2C subsystem is fine; bus 6 is dead to every device on
it. One trap the reporter found: `i2cget -y 6` fails on *every* kernel of this unit, Android included, while the
in-kernel charger driver works - and `i2cdetect -y 6` wedges the controller until a reboot - so userspace SMBus
reads prove nothing about this bus; only the driver's bind does.

What the two stacks do with the bus-6 pads (SCL6/SDA6, pins 188/189 of the pin controller at 0x642e0000):

- Mainline boots with the vendor DTB unchanged (upstream/README.md), so the DT the kernel sees is Unisoc's: the pin
  controller `/soc/aon/pinctrl@2e0000` (`sprd,qogirn6pro-pinctrl`) with the board's groups, and `i2c@22a0000`
  without `pinctrl-names`/`pinctrl-0`. No group names SCL6/SDA6 at all (42 groups: audio, eMMC, SIM, keypad), and
  the board's own states on the controller are hogs named `gpio_4` ... `gpio_124`, not `default`, so the vendor
  kernel applies none of them at probe either. On every kernel the pads are as LK left them.
- Mainline had no pin controller driver for this SoC (only the SC9860's), so `/sys/kernel/debug/pinctrl` was empty
  and nothing could set or even read a pad.

Patch 0013 ports Unisoc's `pinctrl-sprd-qogirn6pro.c` (GPL-2.0, 511 pins) onto mainline's pinctrl-sprd core: the
core takes the common/misc register offsets from the SoC driver (0x44/0x444 here, 0x20/0x4020 on the SC9860) and
the pin encoding grows to Unisoc's (5-bit register index). It binds to the vendor DTB's node as it is. For the
charger bus it does what a DT group would: it logs both pads' registers (the bootloader's state) and puts them on
func1 (the pad's own function, the I2C) when they are not - `pinctrl_sprd_qogirn6pro.i2c6_fixup=0` only logs.
Whether the ABSSV LK really leaves the pads elsewhere is the open question: the same LK boots 5.4 and mainline, and
5.4 does not touch them either, so the first boot of the patched kernel on that unit decides (the log line
`QOGIRN6PRO_SCL6: ctl 0x... (funcN) misc 0x..., iic_inf6_sel N`). The register addresses, for a `devmem` comparison
between 7.2 and 5.4 on the same unit: IIC_INF6_SYS_SEL = bits 27:24 of 0x642e0020 (which AP controller drives pad
pair 6; 6 on the reporter's unit under Android), SCL6/SDA6 control 0x642e0228/0x642e022c (function select in bits
5:4: 0 = func1), their misc registers 0x642e0628/0x642e062c, and the i2c6 controller at 0x222a0000.

What else differs between 5.4 and mainline on that bus, should the pads turn out identical: the vendor i2c driver
sets `I2C_NACK_EN | I2C_TRANS_EN` in I2C_CTL where mainline sets `I2C_EN | I2C_INT_EN` only, and it has a soft reset
(`RESET_AP_AHB_I2C6_SOFT_RST`) on a transfer timeout; both drivers take the same clocks (`CLK_I2C6_EB`,
`CLK_AP_I2C6` from `ext_26m`) from the same DTB.

On our (SSV) unit the pin controller must change nothing: the log shows the pads' state, and the fixup only writes
when the function select is not func1.

The reporter's boot of that kernel settled the pads: SCL6/SDA6 were on func1 already (`ctl 0x00000000 (func1) misc
0x00083088, iic_inf6_sel 6` for both), the four clients `6-0030`, `6-0034`, `6-0063`, `6-006b` exist, and the
charger still fails its first read (`no charger: -5`). So the pads are not the difference.

**What reading ZTE's charger driver gives instead: the chip may not be at 0x6b at all.** The U30 Air's 5.4 kernel
builds `drivers/vendor/common/sqc_v8/sqc_bq2560x.c` (`CONFIG_VENDOR_SQC_BQ2560X=m` in `kernel/u30air.fragment`;
its `bq2560x:bq2560x_charger_probe enter` is the line in the reporter's 5.4 log), not
`drivers/power/supply/bq2560x-charger.c`. Its `bq2560x_get_chip_vendor_id()` reads REG0B at the node's address
and, when that read fails, sets `info->client->addr = SGM41513_I2C_ADDR` (0x1a) and reads again; part 0 there is
an `sgm41513`, part 1 an `sgm41513A`. The client keeps its name, so sysfs shows `6-006b` whichever chip the board
has. For the chip at 0x1a the driver codes two fields differently (`info->client->addr == SGM41513_I2C_ADDR` in
`bq2560x_charger_set_current()` and `bq2560x_charger_set_termina_cur()`): the fast charge current in eight ranges
of eight steps (5, 10, 20, 30, 60, 60, 120, 120 mA from 0, 40, 130, 300, 540, 1020, 1500, 2460 mA) and the
termination current in sixteen steps (5 ... 240 mA, or six times each with REG0D bit 0 clear); every other
register it uses is the same for both chips.

That fits everything the reporter measured, which a dead bus does not:

- mainline gets a NACK (-5, in the log 2 ms after the I2C core's first line), not a timeout (-110): the controller
  ran the transfer and nothing acknowledged 0x6b. Patch 0009 gave up there, as it should on the F50, which has the
  node and no chip;
- `i2cget -f -y 6 0x6b 0x00` fails on Android and on 5.4 on that unit while the vendor driver charges through the
  same bus: what a driver that went on at 0x1a looks like from outside;
- the other three devices (`ptn38003a` redriver 0x30, `aw883xx` amplifier 0x34, flash 0x63) have no driver under
  mainline, and whether they answer was only ever tried with i2cget, on a unit where i2cget also fails for the
  charger that works. "Bus 6 is dead to every device" was never shown; one failed read at 0x6b was.

What is not measured: that the ABSSV unit's chip is at 0x1a. Its 5.4 log decides without any new kernel
(`dmesg | grep bq2560x_get_chip_vendor_id`: `failed to get vendor id ret=-5` followed by `chg_IC_name=sgm41513`
for a chip at 0x1a; `pn=0x2` with `chg_IC_name=sgm41511` or `bq25601` and no "failed" line for one at 0x6b).
Our SSV unit has an SGM41511 at 0x6b (part 2 in REG0B, FINDINGS 33d).

Patch 0015 does what ZTE's driver does, for the `ti,bq2560x_chg` node only: when the read at the node's address
fails, the same read at 0x1a through a client of its own (`devm_i2c_new_dummy_device`), and when that answers,
the regmap on that client, the SGM41513's two tables (Android's 1.98 A is code 52 there; the bq25601's 60 mA
steps would have written 33, which is 600 mA on that chip; the battery node's 300 mA termination current is code
6 in the times-six range), the precharge current left as the chip has it (ZTE's driver has no code for it),
`model_name` `sgm41513`, and `nothing at 0x6b (-5): the SGM41513 at 0x1a` in the log. A failure now names both
reads (`no charger: -5 (and -5 at 0x1a)`), so one boot on the ABSSV unit also says when the idea is wrong. Compiled
only (the one object, `W=1`, on 6.18.56 and 7.2.10 with the other patches applied); not booted on any device, and
no SGM41513 was available to test against. What the patch takes to be the same on that chip without ZTE's driver
showing it: OTG_CONFIG, VBUS_STAT, PG_STAT and IINDET_EN. `mu300-usb` still addresses 0x6b for host mode and would
have to follow once the chip is confirmed.

What else was compared, in case the chip is not at 0x1a either:

- `sprd-i2c 22240000.i2c: probe ... failed with error -22` is the camera's bus (i2c0, one child,
  `sensor-main@20`), not the charger's: its node says `clock-frequency = <1000000>` (read on our unit:
  `000f4240`), mainline's `i2c-sprd.c` takes 100 kHz and 400 kHz only and returns -EINVAL for anything else, the
  vendor driver also takes 1 MHz. Our SSV unit has no `i2c-0` under 7.2.10 either. Harmless for the charger.
- Clocks and supplies: the forced command line (`CONFIG_CMDLINE_FORCE`) carries `clk_ignore_unused
  pd_ignore_unused regulator_ignore_unused` on every unit, so mainline switches off nothing the bootloader left
  on; the i2c6 clocks are the same three on both units (`ext-26m` source, `i2c6-eb` enable, `ap-i2c6`, 26 MHz;
  `i2c6-eb` counts 0 on the reporter's unit only because nothing was using the bus when it was read, 1 on ours
  where the charger is polled).
- Bus timing at 400 kHz (i2c6's `clock-frequency`, `00061a80` on our unit), from the two `sprd_i2c_set_clk()`:
  mainline divides SCL 40 % high / 60 % low and writes a start hold of `6 * 26 MHz / 10^7` = 15 source clocks
  (0.58 us); ZTE's 5.4 driver has "ZTE modify 400K&100K duty 20200827", 31 % / 69 %, and a start hold of
  `18 * 26 MHz / 10^7` = 46 (1.8 us). A board with slower edges could NACK under mainline's and not under ZTE's;
  nothing measured says this unit does, and our SSV unit and the NFC bus of the ABSSV unit (also 400 kHz) work
  with mainline's. This is the next thing to try if 0x1a does not answer.
- I2C_CTL: the vendor driver also sets `I2C_NACK_EN | I2C_TRANS_EN` (bits 22, 21) and resets the controller
  (`i2c_rst`) after a transfer timeout. Mainline sets neither bit and still sees a NACK as -5 at once and not as
  a timeout on this unit, and bus 2 works on the same unit with the same driver, so these are unlikely to
  be the cause; the reset only ever runs after a timeout, which mainline did not have.

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
  with `CHARGE_TO=N` (0-100, §33l) off at N % and on below N-5. It writes the bq256xx charger's `charge_type` (`N/A` off,
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

### 39. The SMS pool: durable before the SIM lets go, long messages that never complete, forwarding

**Where a message can be lost.** This modem is told `AT+CNMI=2,1` (mu300-smsd): it stores a new message on the SIM
(or ME) and announces it with `+CMTI`, it does not hand over a `+CMT` that the host must acknowledge. The SIM is the
safe copy, and the only "acknowledgement" is the pool's `AT+CMGD` once the message is pooled. That used to follow a
global `sync`, which on this device flushes the SD card's loop image too and can stall for seconds. Now each new
message file is fsynced before its rename, and the pool directory, `next_id` and the pool's parent before the first
`AT+CMGD` (busybox's `fsync` applet on OpenWrt; coreutils `sync FILE...` elsewhere; the global sync only with
neither). `next_id` is written aside and renamed, and the highest id in the pool counts too: an id file a power cut
left empty would have restarted the ids and overwritten message 1.

**Parts that never come.** A long message waited on the SIM until all its parts were there - for ever, if one was
lost. `$POOL/partial` now remembers when each waiting message was first seen and whether it was unread then
(`AT+CMGL` marks what it lists read, §35); after `MU300_SMS_PARTIAL_WAIT` (an hour) the parts that did arrive are
pooled with `[...]` for each missing one and an `incomplete: HAVE/TOTAL` header (the panel says so under the text). A
part that turns up later is pooled at once as a message of its own. `sms watch` (every system) holds a long message
back the same way.

**Forwarding** (Cellular > SMS forwarding, `mu300-sms-forward`): driven by the pool (mu300-sms hands over new ids),
never by the modem. HTTP goes through ucode's `uclient` module in a helper that reads the whole request on stdin, so
the bot token in Telegram's URL and the webhook's headers are never in a command line; uclient sends a POST body
chunked. Found on the device: `uclient.connect()` to a refused port returns null, and calling `request()` after it
segfaults ucode, so the helper checks connect first; a timeout ends with `data_eof` and status 0. `ssl_init({verify:
true})` refused self-signed, expired and wrong-host certificates (badssl.com: errors 3 and 4).

Checked on the U30 Air (7.2.9, openwrt-luci, v2026.10.17 with these files copied over, then restored): sending to the
SIM's own number failed (`+CMS ERROR: 28`, the line has no credit, as in §35), so received messages were stored with
`AT+CMGW=<len>,0` (SMS-DELIVER PDUs, received-unread) and went through the same listing, pooling and `AT+CMGD` as a
real one. A single message: pooled, off the SIM, forwarded to a webhook on the Mac (JSON, the custom header) within the
30 s sync. With wrapped `fsync`/`sync`/`mu300-at`: fsync of the file, then of the directory and `next_id`, then
`AT+CMGR`/`AT+CMGD`, and no global sync. Parts 1 and 3 of 3: waiting (state written once), pooled with the wait
lowered as `first [...] third`, `incomplete: 2/3`; part 2 injected afterwards was pooled by the next periodic sync as
`[...]second[...]`. Webhook down: `connect, attempt 1, next in 30 s`, `attempt 2, next in 60 s`, delivered when it
came back; the queue file left `/etc` when empty. A fake Telegram token: `HTTP 401`, not retried. Every process's
command line sampled ~45 000 times during deliveries: no token, URL or header. The keyword filter skipped a message
without the keyword. The page in English and Turkish (save, a refusal translated, the test button, the log). Not
tested: e-mail (the image has no msmtp), the SMS target (no credit), a real incoming SMS from the network.

### 40. The boot chain of the Linux slot: what is loaded per slot, and what the installers copy

**The problem.** Linux boots from the slot Android does not run from, and LK boots that slot with that slot's own
bootloader chain. Linux, though, starts Android's modem: `android-vendor-start` rewrites `androidboot.slot_suffix` to
Android's slot (§5, PR #30), so `modem_control` loads `nr_modem`, `nr_phy` and `pm_sys` of Android's slot and hands
them to the Trusty TA `kernelbootcp` (`kbc_verify_all_avb2`, `SEC_KBC_START_CP`) - the Trusty of the Linux slot. On a
device that never took an OTA both slots hold the factory build and nothing differs. After an OTA Android's slot holds
the new build and the other slot still the factory one (issue #86: on a U30 Air on B18, slot a's `uboot_a`, `sml_a`,
`vbmeta_a`, `trustos_a` "belong to the factory build"), so a Linux boot runs the factory TEE against the new modem
images. kano's advice, which the maintainer took: "sync uboot, teecfg, trustos, sml across the A/B slots - copy the
partitions of Android's slot into the other slot; it solves 99% of the problems."

**What is loaded per slot**, from F50-B's `uboot_log` (16 MiB ring, 108 boots in it, read-only from Linux):

* `uboot`, `sml`, `teecfg`, `trustos`: the secure-boot images. Fastboot downloads of them log
  `uboot_verify_successful`, `sml_verify_successful`, `teecfg_verify_successful`, `trustos_verify_successful` (each
  checked against the signature chain before it is written, `download slot: trustos_b`), and at every boot LK finds
  them already in place (`fdtdec_decode_region: sml-mem@bd000000`, `tos-mem@bd020000`, `zte_tee smc get tos addr`,
  `uboot_set_root_of_trust succeeded`, `pass_chip_uid_to_tos()`): the SPL loaded the selected slot's set before LK.
  `stock/README.md` already treats `trustos` as verified together with `sml`, `uboot` and `vbmeta`, one chain per
  firmware build.
* `vbmeta`: LK's `avb_slot_verify()` reads `vbmeta_<slot>` and through it `boot`, `dtbo`, `vendor_boot`,
  `nr_modem`, `nr_phy`, `pm_sys` (`Loading vbmeta struct in footer from partition nr_modem_b`, ...) and the chained
  `vbmeta_system`, `vbmeta_vendor`, `vbmeta_product`, `vbmeta_odm`, `vbmeta_system_ext` of the booted slot; the
  device is unlocked (`allow_verification_error is 1`, `Device Status is unlock, skip boot image verify!`), so a
  mismatch is logged and booted anyway. The root of trust LK hands to Trusty comes from that verification.
* The SPL itself (`splloader`) is not a by-name partition: it is in the eMMC boot areas, `mmcblk0boot0` and
  `mmcblk0boot1` byte-identical on F50-B, and LK manages it itself (`slot 1 booted fail, rolling back spl and
  reboot into normal`, `exchange boot slot!!!`).

**What the installers copy:** `uboot`, `sml`, `teecfg`, `trustos` and `vbmeta` - the four of kano's list and the
`vbmeta` that is verified with them - from Android's slot to the Linux slot (`tools/android-bootchain.sh`; the copy
in the switch module is kept identical by a test). Nothing else, by a fixed list that also refuses any NV-like name:

* never the NV and calibration partitions (`nr_fixnv1/2`, `nr_runtimenv1/2`, `nr_deltanv`, `prodnv`, `miscdata`,
  `persist`, `calinv`, `isedata`, `ztecfg`, `ztepersist`): on F50-B `nr_fixnv1_a` and `nr_fixnv1_b` differ, each
  slot's NV belongs with that slot;
* never `boot`, `init_boot`, `vendor_boot`, `dtb`, `dtbo`, `super`, `userdata`, `misc`, and never a partition of
  Android's slot;
* not the modem images (`nr_modem`, `nr_phy`, `pm_sys`, `ch_sys`). The evidence does not ask for them: Linux runs
  Android's slot's copies already (above), and LK only reads the Linux slot's for their AVB footers, which an
  unlocked device ignores. They also sit beside the per-slot NV. If a device with a synced chain still fails at the
  handoff, they are the next thing to look at.
* not `hypervsior`, `ise`, `avbmeta_rs`, `common_rs1/2`, `logo`: nothing in the LK log loads them per slot
  (`common_rs1_a` and `_b` differ on F50-B; the others are identical there).

**How it is done** (every check before the first write; a refusal changes nothing and stops the installation):
Android's slot from `ro.boot.slot_suffix` (`_a`/`_b` only); an F50/MU300 or U30 Air by model; `getprop` must
exist and the running slot's boot partition must not hold a Linux image (never from Linux); misc's
`bootloader_control` must say Android's slot booted successfully, and the other slot may outrank it only when it
holds our Linux image (an armed trial), not an OTA waiting for its reboot; both by-name links of each image present,
two different devices, the same size. Then per image: the same sha256 on both slots - skipped; different - both
slots' images are copied into the Linux filesystem (`.mu300/bootchain/<date>/<name>_<slot>.img` and `SHA256SUMS`,
each read back against the partition), then Android's image is written to the Linux slot (`dd conv=fsync`, `sync`,
`blockdev --flushbufs` and `drop_caches` before the read-back) and its sha256 compared. A mismatch writes every
image back that was already written, verifies those too, and stops the installation before the boot image is written:
Linux is not armed, Android is untouched. The host installers also pull the backup into `work/bootchain/<date>`.
`MU300_SYNC_BOOTCHAIN=0` (`install.ps1 -NoBootchainSync`, `MU300_SYNC_BOOTCHAIN=0` in the Magisk conf) skips it, and
a device taken as an F50 although its model is not recognised is never synced. Later, from Android:
`su -c 'mu300-linux bootchain'` (what differs) and `su -c 'mu300-linux bootchain sync'` (backup in
`/data/adb/mu300-bootchain/<date>`). There is no Linux-side command: from Linux the booted slot is the one to be
written.

**On the test boards:** F50-B (B09, never updated) has `uboot`, `sml`, `teecfg`, `trustos`, `vbmeta` and every
`vbmeta_*`, the modem images, `dtb`, `dtbo`, `vendor_boot`, `hypervsior`, `ise`, `logo` identical on both slots (read
from Linux, 2026-10-11): the installers there say "identical on both slots" and write nothing. Not yet run on a
device whose slots differ (one that took an OTA); issue #105's power-off at the Trusty/modem handoff was traced to a
kernel change by its reporter, and this is not claimed as its fix.

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
  RA (preferred lifetime 0) for the old /64 has to come from the device itself. Fixed: `ndp-learn` sends one with
  `ra-deprecate` (ucode, raw ICMPv6 socket; `ucode-mod-socket` in the panel image) on br-lan, valid lifetime 2 h
  (the floor RFC 4862 lets a host apply), router lifetime what is left of the carrier's router, in three rounds 10 s
  apart. It waits until a different /64 is on the bearer: a WAN restart flushes the bearer and usually gets the same
  /64 back, which must not be deprecated. Measured on an F50 (openwrt-luci, 6.18; a macOS client on the USB LAN): a
  /64 that left the bearer was withdrawn within one round and the client marked its addresses `deprecated`
  (`ndp -p`: pltime 0, vltime 7200) while the live /64 stayed preferred and the default router stayed; a WAN restart
  that got the same /64 back withdrew nothing. Not measured: a real carrier renumber (the carrier here kept its /64
  across WAN restarts), and a second relay behind the device, which forwards the RA like any other.

### 40. One stuck AT command wedged the control panel

**Report (U30 Air, openwrt-luci, v2026.10.18):** an AT command hung on one of the panel's pages; after that the whole
panel was useless, also after a reboot, and later it came back by itself. The dashboard's battery tile, which needs no
AT at all, stayed empty. The logs of that boot were in RAM and gone.

**What could do that, measured on the U30 Air (2026-10-11):**

* **`mu300-at`'s lock wait was ten times longer than asked.** It counted 0.1 s naps with `sleep 0.1 || sleep 1`, and
  OpenWrt's `/bin/sleep` refuses a fraction (`sleep: invalid number '0.1'`), so every nap was a second:
  `MU300_AT_LOCK_WAIT=1` took 10 s on the device, the panel's 5 s wait 50 s, the 12 s of every collector and lock read
  two minutes, mobile-data's 90 s a quarter of an hour. rpcd ends a call at 30 s (`rpcd -t 30`) and the browser at 20 s
  (LuCI's `rpctimeout`), but the client went on waiting, took the lock long after nobody wanted the answer, and sent
  the command anyway. The wait is now seconds on the clock (`MU300_AT_LOCK_WAIT=0` is one try).
* **Requests that read the modem inline.** `lock_get` read eight AT commands inside the request whenever there was no
  cache - after every reboot, since the cache is in `/run`, and the home page asks at once. `signal` ran a collector
  round inside the request, and a collector waited each command's whole budget (T + 31 s) on each of four channels.
  rpcd killed the call, never its children: they ran on, held the pool slots and the nr1 lock, and the page started
  new ones. Now `lock_get` serves the cache and reads in the background (one reader at a time), and a collector round
  has a deadline (14 s for the page's live read, 12 s and 25 s in the background).
* **One slow call blanked the page.** LuCI sends the calls a page makes in the same moment as one HTTP request, and
  uhttpd answers them one after the other: the status snapshot (battery, CPU) waited behind the lock reading, and
  when the browser gave up at 20 s every call in the request failed together. uhttpd's `max_requests 3` does not apply
  to `/ubus` (measured: a fourth call was answered at once beside three slow ones). Every panel call now goes on its
  own (`nobatch`), and the polls back off after failures.
* **After a reboot** the panel asked for the lock state with no cache, while mobile-data's bring-up and the boot
  replay of saved locks (an SFUN restart) held the modem; with the ten-fold waits above that is minutes of busy
  channels, which fits "even after a reboot, then it came back by itself".

Reproduced safely: the nr1, nr6 and nr7 daemons stopped (SIGSTOP; never a restart, see 13b) for 150 s. With the fix,
`sysinfo` and `status` answered in 0.5 s throughout and the dashboard showed battery and CPU within seconds of a
reload, the AT terminal said "busy" after 3 s, `lock_get fresh` served the cache after 12 s, `signal` gave up at 14 s,
at most three collectors were alive at any time, and everything was back by itself once the daemons ran again.

**Also in the fix:** AT commands that take minutes or change the modem beyond the answer need a confirmation in the
terminal (scans run as a background job of at most three minutes; band, mode and cell locks are said to persist into
Android, #96); a client holding the AT lock past the deadline it wrote for itself (`lock/until`) is ended. The panel
keeps a log of its calls - method, time taken, outcome, never a value - in RAM, copied to
`/etc/unisoc-modem/panel-ops.log` at most every five minutes and at shutdown, with the previous boot's copy beside it
(Device page, "Recent modem operations"). Two LuCI status pages are put in front of: Channel Analysis scans as soon as
it opens and on every poll, and a scan takes this driver's access point off its channel (a Mac on the hotspot did not
rejoin), so with an access point it waits for a click; System Log reads 250 lines every 15 s instead of 1000 every 5 s
(the ~19 s AT round trips seen with it open were not reproduced: one 1000-line `log read` costs 0.02 s here).

**A second per AT command on OpenWrt (fixed).** OpenWrt's `/bin/sh` refuses a fractional `read -t` too ("read:
invalid timeout"), so `mu300-atd` drained a whole second before every command: every AT command took about a second
and the panel's fast collector round seven. The daemon now runs itself again under a shell that takes fractions when
its own does not: the static busybox next to it (`/opt/mu300/bin/busybox ash`), else bash. On Ubuntu, dash already
hands over to bash 5, which takes them, so nothing changes there. `mobile-data` and `mu300-nfc` nap through the
static busybox's `sleep` as well (bash has no `sleep` of its own, and `/bin/sleep` refuses "0.2": `mobile-data`'s lock
polls waited whole seconds, and `mu300-nfc`'s bare `sleep 0.2` did not wait at all). Measured on the U30 Air, before
and after a reboot onto the change (`mu300-at -t 2 AT+CSQ`, five in a row on each panel channel; a `cell fast` round):

| | nr1 | nr6 | nr7 | fast collector round |
|---|---|---|---|---|
| before (`/bin/sh`) | 1.04 s | 1.04 s | 1.04 s | 7.37 s |
| after (`busybox ash`) | 0.13 s | 0.13 s | 0.13 s | 1.08 s |

(The first command on each channel after the boot still takes a second: nothing has ended cleanly yet, so the first
drain is the slow one, by design.)

## Security

### 41. The vendor daemons' own account

Found on an F50 (Ubuntu 24.04, kernel 7.2.9): `/dev/disk/by-partlabel/nr_fixnv1_a` (the modem's calibration NV, which
nothing can restore) and `persist` were `ubuntu:ubuntu 0660`, so any process of the login user could overwrite them
without sudo; `/dev/data0_gnss` and `/dev/mali0` were `0666`, and so were `spipe_pm*`, `ion`, `dma_heap/*`, ...
where the kernel has them. `modem_control` and `refnotify` ran as `ubuntu` too: the login user could ptrace them
(`modem_control` keeps `CAP_CHOWN` and `CAP_BLOCK_SUSPEND`, `refnotify` `CAP_SYS_TIME`).

* Cause: `gen-ueventd-perms.py` translated Android's ids as numbers. Android's `system` is uid 1000, and uid 1000 is
  the first human account on a distribution (`ubuntu`; `alarm` on Arch). Modes were taken over as they were, `0666`
  included.
* The number is in the binaries. Both daemons begin `main` with `switchUserToSystem`: `setgroups` (1000 1001 2000
  3010), `prctl(PR_SET_KEEPCAPS)`, `setuid(0x3e8)` (an immediate in the code, `mov w0, #0x3e8`), then `capset` down to
  what they keep. They never call `setgid` (they ran with gid 0) and nothing else checks the uid (`getuid` is not
  even imported). A failed `setgroups` or `setuid` is logged (`setgroups failed`, `uidset failed`) and they carry on.
* Fix: a system account `mu300vnd` (the images: `rootfs/assemble.sh`, `arch/build-rootfs.sh`; a system without it:
  `android-vendor-start` makes it before anything else uses it). `android-run` starts the two daemons as it with
  `setpriv`: no other groups, no new privileges, and only the capabilities they keep on Android plus `CAP_SYS_CHROOT`
  for `chroot`, which their own `capset` drops - their `setuid(1000)` then fails, harmlessly. `android-vendor-start`
  starts `modem_control` through `android-run` (still an exec, so the task name stays `modem_control`).
  `cp_diskserver` never switches users on Android either and stays root.
* `ueventd-perms.sh`: `system` and `radio` become `mu300vnd` (owner `$V`, group `$VG`), `graphics` on a node Android
  gives everyone (`mali0`, `ion`, `dma_heap/*`, `sprd_dmabuf`, `pvr_sync`: `0666`) the `video` group (`root:video
  0660`), anywhere else root, as is every other Android id and every id the generator does not know. No node is left
  with bits for others, nothing is writable by everyone, a node that is root's alone is `0600`. Root's alone: input
  events, the USB serial console `ttyGS*` (getty and login hand it out as on any Linux: a serial login still works) and
  `firmware_class`'s path (whoever writes it chooses the firmware the kernel loads) - all three were `ubuntu`'s. The RTC
  stays root's but is the vendor group's: `refnotify` opens `/dev/rtc0` (`root:root 0660`), which it reached through
  gid 0 before ("RefNotify open /dev/rtc0 failed, error: Permission denied" until it was). The ids are looked up when
  the script runs, in `/etc/passwd` and `/etc/group`; without the account (OpenWrt, the initramfs: no account at
  1000 there) it is uid/gid 1000, which the daemons switch to themselves, and the GPU's group is root.
* Nobody gains anything: `tests/test_vendor_ids.py` applies the script of v2026.10.18 and the new one to every node
  they name (a glob as one name) and fails if `ubuntu`, a second login user in the usual groups (`video`, `render`,
  `input`, `dialout`, ...) or everyone else can do anything with a node they could not before. 333 of 349 nodes
  changed; the only one more open is the RTC, for the vendor group (it was not touched before).
* The generator's inputs are in `android-vendor/ueventd/` now (the `/dev` rules of the device's `ueventd.rc` and the
  `chown`/`chmod` lines of its vendor init `*.rc`), and a test checks the committed script is the generator's.
* Updates: `mu300-update` takes the new image's `/etc/passwd` and adds the old system's human accounts, so an updated
  system has the image's `mu300vnd`; the nodes are handed out by name at every boot, so its uid does not matter.
* Measured on F50-B (Ubuntu 24.04, 7.2.9, no SIM), the three files replaced on a v2026.10.18 system: the account
  made at boot (`mu300vnd` 999/991); `modem_control` and `refnotify` Uid 999, Gid 991, no groups, NoNewPrivs 1,
  CapEff `0x1000000001` and `0x2000000` (as on Android); `cp_diskserver` root; the modem booted (`modem@0..2 start
  over`), `AT` OK, `+CFUN: 1`, `+CPIN` `+CME ERROR: 10` (no SIM, as before), `AT+CGMR` answers; `nr_fixnv1_a` and
  `persist` `mu300vnd:mu300vnd 0660` and `head` on them as `ubuntu` "Permission denied"; no world-writable node in
  `/dev` besides the standard ones, nothing in `/dev` or `/sys` owned by uid 1000; `mali0` `root:video 0660` and
  `cltest` (OpenCL) passes; Wi-Fi client still connected; `ttyGS0`, `input/event0` and the firmware path `root:root
0600`, and a login on the serial console works (login gives `ttyGS0` to the user, getty takes it back); `timedatectl` reads the RTC; up past the PM watchdog's
  ~290 s. The vendor log has the same errors as before the change (no `/dev/cp_dump`, no `/proc/bootconfig`, no
  property service) plus the two logged failed switches. Not measured: the 5.4 kernel, OpenWrt (unchanged there but
  for the modes), the modem with a SIM.

### 42. No access point on a DFS channel (user report, 2026-10-11)

A user's SC2355 device on OpenWrt 25.12.5, hotspot on channel 60 (5 GHz, 80 MHz, country CN): hostapd logs
`start_dfs_cac() failed, -1`, `Interface initialization failed`, `AP-DISABLED`, and the hotspot never comes up;
channel 149 works.

* **Cause.** 52-64 and 100-144 are DFS channels in every regulatory domain (wireless-regdb flags them `DFS`, the
  kernel `radar detection`; a few countries also have 36-48 or 149-165 so). An access point there must first listen
  for radar (CAC); hostapd asks the driver through `NL80211_CMD_RADAR_DETECT`, and cfg80211 answers `-EOPNOTSUPP`
  when the driver has no `start_radar_detection` op. Neither SC2355 driver has one: not `sprd_cfg80211_ops`
  (`common/cfg80211.c`) nor the sc2355 ops (`sc2355/init.c`) of `upstream/modules/sprd_wlan_combo`, and not the
  vendor tree the 5.4 module is built from. No interface combination of the wiphy carries `radar_detect_widths`
  either. The firmware does define the commands - `CMD_RADAR_DETECT` (77) and `EVT_RADAR_DETECTED` (0xA1) are in
  `sc2355/cmdevt.h` and the API version table - but nothing in the driver sends or handles them. (The vendor tree's
  `merlion` driver, another chip, implements `start_radar_detection` over the same command number 77, in `11h.c`; a
  port to the sc2355 would need its CAC and radar events measured against real radar before it could be offered.)
  Android's SoftAP never uses these channels either: its ACS list is 36-48 and 149-165 (§23).
* **Decision.** The hotspot never goes onto a DFS channel; nothing tries to make DFS work. Every layer that picks or
  writes the channel keeps it off them, and a DFS channel is replaced, never refused, so the hotspot does not stay
  down:
  * `opt/mu300/lib/wifi-channels.sh` (shared by the tools below): the firmware's channels a country allows without
    DFS and without NO-IR, from wireless-regdb's `db.txt` - the full 36-48 + 149-165 except in about 70 countries
    (no 149-165 in TR, JP and much of Europe's neighbourhood; no 36-48 in BD, PK and a few more; no 165 in ID; none
    at all in the world domain `00` and five countries, which use 2.4 GHz). The default is 36, else 149; the width
    is 80 MHz where the block of four is allowed (36-48, 149-161), 40 for a pair, 20 for 165.
  * Ubuntu `hotspot-start`: `CHANNEL=` from `hotspot.conf` goes through it (a DFS channel becomes the default with
    one line on stderr, in the journal; `auto` is the default); when the kernel's flags (`iw list`) still refuse the
    channel it tries the country's other channels before falling back to 2.4 GHz (it used to fall back at once).
  * OpenWrt `openwrt-wifi-config`: the first configuration from `hotspot.conf` writes the resolved channel, the
    width as `VHT80/40/20`, `channels` (the country's list, hostapd's `chanlist` for ACS) and `acs_exclude_dfs 1`.
    At every later boot it rewrites a DFS channel set in LuCI to the default (the htmode narrowed to what fits),
    so LuCI shows the channel the hotspot really uses. `mu300-wifi-band 5` writes the same. The Android import keeps
    writing `CHANNEL=auto`.
  * wifi-scripts (`openwrt/patches/wifi-scripts-no-dfs.patch`, applied by `openwrt/build-rootfs.sh` with
    `--fuzz=0` like the fw4 patches, the build stops if it no longer applies): `hostapd.uc` reads the capability
    from the driver - no interface combination with `radar_detect_widths` - and for such a driver, on 5 GHz, an
    explicit channel the kernel flags `radar` becomes 36, else 149, else the first allowed one, with the width
    narrowed to what the allowed channels hold (160 becomes 80), and a `wifi-scripts: channel 60 is a DFS channel
    and this driver cannot detect radar ...` line in `logread`; `auto` gets `acs_exclude_dfs=1`. This is what
    catches a DFS channel chosen in LuCI's Network > Wireless before the next boot. Drivers that can detect radar
    are untouched.
* **Not changed.** LuCI's channel list still offers the DFS channels: `luci-mod-network` marks a channel unavailable
  only when iwinfo reports it restricted (NO-IR without radar), and iwinfo does not report radar at all; hiding them
  would mean patching LuCI's own (minified) page. The driver is not changed either: the only ways to make cfg80211
  refuse an AP there (clearing `IEEE80211_CHAN_RADAR` would let an AP start without CAC, which is not allowed;
  marking the channels disabled would cost the Wi-Fi client its DFS networks) are worse than the user-space guard.
  The Wi-Fi client (`wifi-client`) still joins networks on DFS channels: radar detection is the access point's job.
* **Tested** (`tests/test_wifi_channels.py`): the table, the replacement and its one line, `auto`, the widths, under
  dash, bash and busybox ash; `hotspot-start`'s hostapd configuration with a stub `iw`; `openwrt-wifi-config` and
  `mu300-wifi-band` with a stub `uci`, and again with the real `uci` and ash of the v2026.10.18 `openwrt-luci`
  rootfs; and, with `MU300_WRT_IMAGE` naming an OpenWrt 25.12 image, the patch applied to the feed's wifi-scripts
  (OpenWrt 25.12.5, ImmortalWrt 25.12.2 and the v2026.10.18 rootfs) and the hostapd configuration they generate for
  a fake wiphy with and without radar detection. Not yet on a device: the hotspot on 36 after LuCI was set to 60,
  and ACS (`auto` in LuCI) on this driver.

### 43. adb over USB to Linux: adbd in the gadget, and what FunctionFS does to the rest of it

`mu300-usb adb on|off` (off by default) puts AOSP's adbd into the USB gadget next to the network function and the
ACM console: `adb shell`, `push`, `pull`, `forward` from a computer, as with Android.

**Update 2026-10-13:** adb is on by default now, and adbd lets every computer in unless it is told to take keys
only (`mu300-usb adb auth open|keys`): §70. What this section says about the daemon, the gadget and FunctionFS
stands; "off by default", "`auth_required = true` on Linux, always" and "no setting that turns the check off" do not.

**Which adbd.** Ubuntu 26.04 (not 24.04) packages Debian's `adbd` 34.0.5, but Debian patches it to require no
authorisation at all on Linux (`adbd-don-t-require-authorization-on-Linux.patch`) and it listens on TCP 5555 when it
finds no FunctionFS: a root shell for anyone on the LAN and the hotspot. It is also glibc-only. Alpine's and nmeum's
`android-tools` build the host tools, not the daemon. So `tools/adbd/build.sh` builds it: the daemon's sources from
nmeum's `android-tools` 34.0.5 release tarball (AOSP with BoringSSL vendored; SHA-256 pinned), a CMakeLists of its
own for adbd alone, static against musl in Alpine 3.20: one aarch64 binary of 2.49 MB (stripped) for Ubuntu and
OpenWrt, built in under two minutes, shipped in the images (`/opt/mu300/bin/adbd`). JDWP, adb over Wi-Fi (pairing)
and mDNS are stubbed out (`stubs.cpp`), and protobuf with them. `mu300-adbd.patch`:

* `auth_required = true` on Linux, always (ro.adb.secure=1). Keys come from `/etc/mu300/adb_keys` and
  `/root/.android/adb_keys` only; Android's framework socket, through which the "allow USB debugging?" dialog
  approves a key, is never taken (it would come from the environment, `ANDROID_SOCKET_adbd`). An unknown key gets
  `unauthorized` and stays there.
* USB only: FunctionFS on Linux (Debian's patch), and no TCP or vsock listener whatever the properties or the
  environment say (`ADBD_PORT`); without FunctionFS adbd exits.
* umask 022 instead of 0, and pushed files keep the computer's mode without group/other write (Android copies the
  owner's bits to group and others: a pushed file was `rw-rw-rw-`).
* `adb shell` without a command starts the user's login shell (bash on Ubuntu, ash on OpenWrt), `TMPDIR=/tmp`.
* musl: `UsbFfsConnection::StopWorker` waited for `pthread_kill(t, 0)` to say `ESRCH`, which musl does not for a
  thread that has exited but is not joined; adbd hung for good at the end of the first USB connection (an unbind,
  a computer that goes away). The worker now says when it is done.

**The gadget.** `ffs.adb` is the third function of `configs/c.1` (`f3`): the network and the console keep their
interface numbers (macOS' NCM, Windows' RNDIS binding by MS OS descriptor for interface 0). VID/PID stay; adb finds
the interface by its class (ff/42/01). While adb is in the gadget, bcdDevice is 0x0303 (0x0304 with RNDIS), as
Windows caches MS OS descriptors per VID/PID/bcdDevice, and the descriptors are on with NCM/ECM too, so that adbd's
WINUSB compatible ID reaches Windows (not tried on Windows: the Windows host was not reachable).

boot/init makes and binds the gadget before any system runs; adbd comes later, so `mu300-adbd run` (the
`mu300-adbd` service, systemd and procd) rebinds once: it starts adbd, waits for its descriptors (`ep1` appears),
unbinds, links `f3`, binds again. FunctionFS needs the descriptors before the bind and refuses a bind without
them, so a gadget that will not bind with adb is bound without it. Two kernel behaviours shape the rest:

* `ffs_closed()` calls `unregister_gadget_item()` - the whole gadget comes off the UDC - whenever the last file of
  a bound FunctionFS instance is closed, and adbd closes and reopens its endpoints at the end of every connection.
  Android's init binds the gadget again (`sys.usb.ffs.ready`); here the loop of `mu300-adbd run` does, after five
  seconds (mu300-usb-reset and OpenWrt's LAN hook unbind on purpose and bind again themselves), not in the U30 Air's
  host role.
* adbd closes and rewrites its descriptors every second while no bind comes (`timed out while waiting for
  FUNCTIONFS_BIND`); a bind in that gap fails, so binds are retried 0.2 s apart.

Measured on F50-B (Ubuntu 24.04, 7.2.9 with `CONFIG_USB_CONFIGFS_F_FS=y`, macOS host, adb 37.0.1): `adb devices`
shows `MU300LINUX-324950664950-203d8329` (Android's adb on the same board is `324950664950`); with no key
authorised and with the key file taken away, `unauthorized` ("adb: device unauthorized"); with the key, `adb shell`
is root with a login bash on a pty, push 38.7 MB/s and pull 41.9 MB/s (20 MB, checksums equal), `adb forward`
works. `mu300-usb adb on/off`, three boots with adb on (NCM, RNDIS, NCM) - with RNDIS a Mac has no network but adb
works, a way in that does not need the network - the gadget unbound by hand (as FunctionFS does it): adb and SSH
back after 6-8 s; `mu300-usb-reset --ready`: adb stays. `adb off` leaves the gadget as boot/init made it (bcdDevice
0x0301, no MS OS descriptors, no FunctionFS mount). Not tried: OpenWrt, the vendor 5.4 kernel, a U30 Air being
unplugged and plugged again, Windows.

**How the hang showed:** `echo disconnect > /sys/class/udc/*/soft_connect` (meant to look like an unplug) ended
adbd's connection, and adbd hung in it, holding its endpoints: FunctionFS never took the gadget off the controller,
the loop saw it bound and had nothing to do, and the pulled-down gadget stayed off the bus until the board was
unplugged (its root port on the Mac cannot be power-cycled). Without adb a soft disconnect stays too, until
`echo connect`; with the fixed adbd it was not tried again.

## Network namespaces on the vendor kernel

### 44. Network namespaces on 5.4: the vendor's fragment sysctl, torn down by the wrong namespace (#103)

Reported with four boots' worth of pstore on an F50 running OpenWrt on 5.4 with Docker (two containers,
`restart=always`) and a Codex sandbox: about 25 s after boot a `WARNING` in `retire_sysctl_set` from
`cleanup_net`, then within a second a fatal exception in an unrelated process in `__kmalloc`, or on the netns
worker itself:

```text
Workqueue: netns cleanup_net
pc : count_subheaders+0x18/0x74
lr : unregister_sysctl_table+0x28/0xa8
 xfrm_sysctl_fini+0x34/0x50
 xfrm_net_exit+0x18/0x50
 cleanup_net+0x2e4/0x54c
Kernel panic - not syncing: Fatal exception
```

and, after a sandbox command finished, `kernel BUG at mm/slub.c:308` (a double free) in `kfree` from the same
`xfrm_sysctl_fini`.

**Cause**, in the vendor tree (`net/xfrm/xfrm_sysctl.c`, under `CONFIG_XFRM_FRAGMENT`, a Unisoc option - "only
for sprd" says its Kconfig; it is not upstream, and linux-5.4.y has not changed this file since 2017, so no stable
fix exists to take). The option adds a `net/core/enable_xfrm_fragment` sysctl, a global switch for fragmenting
before ESP, and registers it with a *second* `ctl_table_header` whose pointer, and its `kmemdup`'d table, live in
two `static` variables. `xfrm_sysctl_init()` runs for every network namespace and overwrites both; `xfrm_sysctl_fini()`
runs for every namespace and unregisters and frees whatever they point at, without clearing them. With one
namespace at a time the globals happen to track it. With two alive - Docker's containers, dnsmasq's, a sandbox - the
first to exit unregisters and frees the *newer* namespace's registration and leaves its own behind in a dying
namespace (`retire_sysctl_set`'s warning); the second's exit then walks a freed header (`count_subheaders`) and
frees the table again (`slub.c:308`), or the stale memory has been reused and another process's allocation goes
wrong. A failed second registration also freed the first table while leaving it registered. The entry was 0660 and,
unlike the four `xfrm_*` entries next to it, not hidden from namespaces owned by an unprivileged user namespace,
whose "root" has CAP_NET_ADMIN over them: a global kernel switch writable from `unshare -Urn`.

**Fix** (`kernel/patches/xfrm-sysctl-fragment-per-netns.patch`, the reporter's candidate taken as proposed): the
entry becomes the fifth member of `xfrm_table`, so each namespace's copy is registered and torn down with that
namespace's own `net->xfrm.sysctl_hdr`, exactly like the four upstream entries; the second header, its table and
their error path are gone. The switch stays one global `int` with default 1, `get_xfrm_fragment()` (used by the ESP
output path) is unchanged, so are the path and the mode. One visible change: the entry now follows the table's rule
and is absent in a namespace of a non-initial user namespace (`unshare -Urn` sees no `enable_xfrm_fragment`; the
host's stays 1). No struct changes, so the module bundle is unaffected.

**Reproduce** (unpatched 5.4; do it on a board you can reboot, the panic is on teardown and takes the kernel with
it): two namespaces have to be alive at once, so `for i in $(seq 200); do unshare -n true & unshare -n true; wait;
done` - or simply starting Docker with two containers - and the warning, then the panic, follow within a few
iterations after the netns worker runs. `unshare -n true` in a single-threaded loop does not trigger it (one
namespace at a time keeps the globals consistent), which is why a plain namespace test can pass on the broken
kernel. The reporter's patched kernel passed 460 lifecycles (sequential and four-way parallel) and 10 sandbox runs
on an F50 across two boots with no recurrence; our build of the patch (release config, ThinLTO) is in PR for #103,
with the loop above to run on our F50 before the release.

### 45. `rmmod sprd_wlan_combo` panicked in `__run_timers` (issue #146)

Found on the U30 Air during the #123 test (7.2.9, also on main): with Wi-Fi idle (`wifi down`, OpenWrt),
`rmmod sprd_wlan_combo` panics in `__run_timers` within a second. Not a timer that one deinit forgot: **the port's
platform remove tore nothing down.** The vendor's `sprd_wlan_remove` (`common/sprd_wlan.c`) ends in
`return sprd_iface_remove(pdev)`; the mainline port dropped that line with the SC2332/SIPC variants, so remove logged
one line and returned. The module was then freed with the recovery watchdog of PR #100 (`iface_wd.tick`, a
`delayed_work` in the module's `.bss`, on `system_wq`, rearming itself every second) still armed, and with the
wiphy, `wlan0`, the WCN reset notifier, the misc device and the inetaddr notifiers all still registered on the
freed `priv`: the watchdog's timer is the first to go off. The vendor 5.4 driver still has the call (and no
watchdog), so only the mainline module was affected.

Fix (`upstream/modules/sprd_wlan_combo`):
- `sprd_wlan_remove` calls `sprd_iface_remove()` for the PCIe variant again: watchdog stopped first, the chip
  powered on for the close commands, the notifiers, the interfaces and the wiphy unregistered, the chip powered off,
  TX/RX torn down, `priv` freed.
- `sprd_iface_remove` no longer returns on a failed WCN power-on with everything still registered: a platform
  remove cannot refuse, the device is unbound and the module freed either way. The power-on only fails from a count
  of 0 (no interface open), so the teardown goes on without the chip and skips the power-off that would have
  balanced it.
- Two timers that live in `priv` and had no owner where `priv` is freed: the scan timer
  (`timer_shutdown_sync` in `sprd_core_free`; a scan still running is reported done by `iface_deinit_vif`, which
  deleted it, but nothing did so unconditionally) and the TCP ACK timers (`sc2355_tcp_ack_deinit` used `del_timer`
  under the seqlock the callback takes, so a timeout running on another CPU could outlive the deinit; a
  `timer_shutdown_sync` pass after the lock is dropped waits for it).

Built for 6.18.56 and 7.2.10 (modules only). Device test: see the PR for #146.

### 46. SMS sends failed with IMS "Busy Everywhere" until the SMSC was written back; the panel lost slow sends (#176)

Reported on openwrt-luci v2026.10.20, China Broadnet (PLMN 46015), U30-class board (UMS9620): every send from the
panel to the carrier's service number failed, incoming messages worked. The modem's URC log had
`+SPIMSREASON: 1,512,"SMS FAILED: CODE:600 REASON:Busy Everywhere"` (the IMS stack's SIP 600 on the submission),
and the panel's operations log `sms_send - killed`. The reporter's one-shot test through the same mu300-atd, with two
changes made together, succeeded at once (`+CMGS: 1`, `OK`, and the service answered within seconds):

- `AT+CSCA?` answered `"2B38...",145` (the modem's CSCS is `"HEX"`, so the address reads as hexadecimal: `+86...`),
  and that exact string and type were written back with `AT+CSCA="2B...",145` - the same value, not another SMSC, and
  CSCS left alone. What this puts right inside the modem is not known; SMSC state after the IMS registration is the
  guess. Only `OK` counted.
- the whole send (CSCA, `AT+CMGF=0`, `AT+CMGS`) ran under one acquisition of mu300-at's client mutex
  (`/run/mu300-at/lock`). mu300-sms took it once per command, so between its commands any other client (the panel's
  collectors, mu300-smsd's sync) could run, and the modem's state between PDU mode and the submission was never
  guaranteed to be what the previous command left.

The two were changed together, so which one was decisive is not known. Both are now in mu300-sms's send:

- `at_lock`: mu300-sms takes `$ATDIR/lock` itself, the way mu300-at does (a holder that is gone is taken over, the
  wait is `MU300_AT_LOCK_WAIT` seconds of the clock, `mu300-at: busy` when it gives up, so the panel's verdict is
  unchanged), and tells the mu300-at calls under it with `MU300_AT_LOCK_HELD=<pid>`. mu300-at borrows the lock only
  when `lock/pid` names that live process; anything else and it takes the lock as before. The lock is released after
  the submission, before the pool lock (a path holding the pool lock makes no AT call, so send and sync never wait
  for each other - that rule stands).
- `smsc_refresh`: `AT+CSCA?`, the address and type parsed strictly (`"[+0-9A-Fa-f]+",[0-9]{1,3}`), written back
  unchanged. A query that fails or answers something else skips the refresh (logged on stderr), and a write the modem
  refuses is logged and the send goes on: the SMSC in use is the same either way, and the submission's own answer
  says what is wrong. Nothing ever picks another SMSC or touches CSCS.

The submission stays one write, `AT+CMGS=N<CR><PDU><Ctrl-Z>`, as before. Waiting for the modem's `> ` prompt first
would need a byte-wise read in mu300-atd (the prompt has no newline, so the daemon's line reads never see it; it is
collected with the reply), and what `read -t` leaves in its variable when it times out on a partial line is not the
same under every shell the daemon runs under (bash, busybox ash) and has not been measured on the device - in the one
process that owns the channel, where a modem left waiting at the prompt for a PDU that never comes is a wedged
channel. The reporter's successful send used the combined write too, as every send on the U30 Air has.

The panel: `mu300dash sms_send` ran mu300-sms inside the rpcd call, which rpcd ends at 30 s, while mu300-sms waits
up to 40 s for `+CMGS` (and its whole transaction longer). A slow send was killed with the call - the message gone out
or not, with no result anywhere but a `killed` line. `sms_send` now validates and starts the send detached
(`setsid mu300dash sms-job`, the at_job pattern), answering `started`; `sms_job` says `running` and then the verdict
`sms_send` used to give (`ok`/`busy`/`Sending failed` with the modem's last line) with `done:1`; the page asks every
second. A second send while one runs is `busy` (the AT channel is in use), never a second submission; a job that
died without a result says so and is not resent. The job logs how the send went in the operations log (`sms_send
result 2.31s ok`), which is what the report was missing.

Device test (a U30 Air whose line answers `mu300-sms send 7000 KALAN` with a two-part reply): the send through
`/opt/mu300/bin/mu300-sms send 7000 KALAN` must show `AT+CSCA?` and the same-value `AT+CSCA=` in the daemon's answer
files, `/run/mu300-at/lock` gone afterwards, and the reply pooled; through the panel's SMS page the toast must go
"Sending…" and then "Sent" with the operations log carrying `sms_send ... ok` and `sms_send result ... ok`.

The Ubuntu side, `sms send` (every system's SMS tool, its own send path, no pool), has the same two since: the same
`at_lock`/`at_unlock` and `smsc_refresh` (held only when the daemon's fifo is there - without it mu300-at opens the
tty itself and takes no lock either), and the submission as the same one request `AT+CMGS=N<CR><PDU><Ctrl-Z>`. It
used to send `AT+CMGS=N` as a request of its own and the PDU as another: the `> ` prompt has no line ending, so the
daemon never saw an answer to the first (its whole 10 s), counted it as a silent command and drained up to 25 s
before writing the PDU - and between the two any other client could get in. Device test (an F50-B with a registered
SIM): `sudo sms send 7000 KALAN` must answer `sent (reference N)` within seconds, with `AT+CSCA?` and the same-value
`AT+CSCA=` in the daemon's answer files, `/run/mu300-at/lock` gone afterwards, and `sudo sms list` showing the reply.

### 47. A system the Magisk zip added beside another had a password nobody saw (#167)

Reported as "cannot log in to openwrt-luci / openwrt" on a board that had Ubuntu first and the two OpenWrt systems
added later with zips (F50-B). The one-boot image's `root:::` was the first suspect and a red herring: the installer
always replaces that line. Found by mounting the board's Linux disk from Android and looking at the hashes without
reading them: each added system's `root` had a proper SHA-512 hash - of a **random 12-character password** that
`mu300-install.sh`'s `build_password` made because the install was a new system (`KEEP_PW=0`) and
`mu300-install.conf` had no `MU300_PASSWORD`. That password was written only to `/data/adb/mu300-linux-password.txt`,
a root-only file, and shown once in Magisk's output; every later zip replaced the file, so the second added system's
password was in no file at all. The `ubuntu` account still had the password the user knew, and the panel's
`mu300-os <os>` switch booted a system nobody could log in to. (`dropbear`/`rpcd` refusing *empty* passwords was not
it.) The board was recovered with `tools/reset-password.sh openwrt-luci` from Android, which works for an added
system too.

Decision (the project owner's): the zip's password for a system it installs is **fixed and well known, like the
images'** - Ubuntu's user `ubuntu` has the password `ubuntu`; OpenWrt's and openwrt-luci's `root` has no password
(the empty field stock OpenWrt ships with: dropbear and LuCI let root in until one is set with `passwd` or in LuCI,
System > Administration). No random password any more, neither for a first install nor for an added system. A
`MU300_PASSWORD` in `/data/adb/mu300-install.conf` still wins when given (hashed with the bundled busybox's
`mkpasswd` as before, for every system it installs); it is never shown or written down. An update of a system that
has accounts of its own keeps carrying them over (`KEEP_PW`), as before; an empty OpenWrt root or an Ubuntu `ubuntu`
that is still `ubuntu` counts as the images' default, not as a password to keep, so an update of such a system gets
the default again (the same thing). `MU300_PASSWORD_RESET=yes` now means "the images' own password again".

How: `build_password` hashes `ubuntu` for Ubuntu (a fresh salt each time) and leaves the hash empty for OpenWrt;
`mu300-install.env` gets one more line, `PW_SET=1`, which tells `android-install.sh` to put `PWHASH` into the
system's own account even when it is empty (OpenWrt's root without a password) - `PW_SET=0` is the update that keeps
the accounts, and the computer installer, which never writes the key, behaves as before. `android-install.sh` no
longer refuses a system whose account would be "empty or the image's default": those are the intended accounts now,
and the mark that has `mu300-update` carry some `<os>.old`'s accounts over at boot is removed whatever the path. The
plan, the closing message and the note in `/data/adb/mu300-linux-password.txt` say which account and password work
(`password for root: none yet - set one with passwd, or in LuCI (System > Administration)`; `password for ubuntu:
"ubuntu"`), in the three languages; the file keeps the other system's block as before, and holds no secret any more.
Device test: a zip install of `openwrt` on a board that has Ubuntu must end with the `root: none yet` line, the file
must note it under `user: root`, and `ssh root@192.168.77.1` into the booted OpenWrt must log in with no password;
LuCI's login on openwrt-luci likewise, and `passwd` there must take.

### 48. The stock virtual thermal zone on mainline (`mu300_thermal`), and thermal-guard's handoff to the kernel

Under 6.18 and 7.2 nothing in the kernel throttled the CPUs: the mainline port registers the 19 on-die sensors
(`sprd_thermal_r5p0`, §31) and the cpufreq cooling devices (`CONFIG_CPU_THERMAL`), but no thermal zone had a trip
point, so the two never met and `thermal-guard` capped `scaling_max_freq` from userspace (85 °C a step down, 75 °C a
step up, 105 °C power-off). kanoqwq's fork (clean-tf-7.2, 5c8c2f9) brought the kernel's own throttling back with an
out-of-tree module; the review of 2026-10-11 deferred it for coordination with the guard and a device test. This is
that work.

**What the stock device tree says** (the F50's live DTB, decompiled; mainline boots the vendor DTB unchanged, §31):

* The 19 physical zones (`lit0-3`, `mid4-6`, `big7`, `apcpu0/1`, `gpu`, `ai0/1`, `ank0-5`, …) have `polling-delay = 0`
  and no `trips`; so have the four board NTC zones (`chg`, `nr`, `pa`, `board`).
* One zone has trips: `soc-thmzone`, `polling-delay 1000` ms, `polling-delay-passive 100` ms, `sustainable-power
  3000`. Trips: `trip-point@0` passive 70 000 mC (hysteresis 1 000), `trip-point@1` passive 85 000 (hysteresis
  1 000), `soc_crit` critical 110 000 (hysteresis 2 000). Cooling maps, all on the 85 °C trip: `cpu@0` (contribution
  1024), `cpu@400` (410), `cpu@700` (410), and five vendor nodes under `/cooling-devices` (`cluster0/1/2-cooling`
  `sprd,cluster-cooling`; `gpu-cooling0` `sprd,mali-power-model`; `npu-cooling0` `sprd,npu-power-model`) that no mainline
  driver registers.
* Its sensor is `/virtual-sensor@0`, `compatible = "virtual-thermal"`, `#thermal-sensor-cells = 1`, with
  `thmzone-cells` naming eleven of the physical **zones** (not sensors): `lit0`-`lit3`, `mid4`-`mid6`, `big7`, `gpu`,
  `ai0`, `ai1`. The vendor kernel's `sprd_soc_thm` ("virtual-thermal") reports the hottest of them; that is the zone
  `sprd_cpu_cooling` binds the clusters to on 5.4 (§18).

**(a) an out-of-tree module, or (b) the device tree and the kernel config?** Mainline has nothing for (b): neither
6.18.56 nor 7.2.10 has a driver matching `virtual-thermal` or any aggregating ("hottest of") thermal sensor
(`grep -rl 'virtual-thermal\|aggregat' drivers/thermal/` is empty in both trees), and the trips cannot be moved onto a
physical zone, because the kernel boots the vendor DTB as LK hands it over (a custom DTB hung in `setup_machine_fdt`,
`upstream/README.md`). What is needed is a driver for that one sensor node; it can live in `upstream/port/` (built in,
a new `Image`) or in `upstream/modules/` (loaded from the rootfs like the vendor modules). **Chosen: the module**,
`upstream/modules/mu300_thermal` (after kanoqwq's, GPL-2.0, rewritten with the DT facts above and a probe that defers
only while a physical zone is not registered yet and fails on a wrong tree): it needs no kernel image change, so no
untested boot image on anyone's board; `build-modules.sh` builds it for both kernels and the bundles carry it; it is
tested with `insmod`/`rmmod` on the release kernel; and the seconds between boot and `extra-modules` are covered by
`thermal-guard` as before. The same source can become a built-in `port/` driver later if that ever matters. The
module is 90 lines: it looks the eleven zones up by name (`thermal_of` names a zone after its node, so the node name
is the zone type), registers itself with `devm_thermal_of_zone_register(dev, 0, ...)` and returns the hottest of the
zones that read; a zone that fails to read is left out of that round (one flaky sensor must not silence the zone
with the cooling maps bound to it), and only when none reads does `get_temp` fail - then the core logs it once,
skips the update (no trip is evaluated, the cooling devices keep their state) and the zone's sysfs `temp` read fails
too, which `thermal-guard` takes as "cap it myself" (below). Never is an unreadable sensor reported as cold. The
thermal core does the rest: the zone
with its trips, the cooling maps (the five vendor cooling nodes are ignored, `thermal_of_should_bind` only matches a
registered cooling device's node), `step_wise` on the passive trips, and `thermal_zone_device_critical` at 110 °C
(`hw_protection_action` defaults to shutdown in both kernels).

**How the kernel's cap and ours compose.** `cpufreq_cooling` lowers a cluster through a frequency QoS request
(`FREQ_QOS_MAX`); `scaling_max_freq` *shows* the resolved `policy->max` (the lowest of all requests) and *writing*
it sets only the user request. So a profile's ceiling (`mu300-cpu`, `/run/mu300/cpu-ceiling`, PR #111) holds under
the kernel's throttling without any help - the lower of the two wins, and when the kernel lifts its cap the ceiling
is what is left - while `mu300-cpu status` reads the throttled value and reports `throttling` from the cooling
devices' `cur_state`, as before. What must not happen is two controllers on one knob: `thermal-guard` stepping
`scaling_max_freq` down at 85 °C while `step_wise` lowers the QoS at the same temperature, and later lifting a cap
(ours) while the kernel still holds its own. Hence the handoff, in `thermal-guard`:

* The kernel is told by its release: every 5.x we ship is the vendor kernel, which throttles and protects itself, so
  there the guard only runs the LED alarm (as before). "A zone has trip points" no longer means "vendor": with the
  module the mainline zone has them too, and on mainline the guard's 105 °C power-off must stay.
* On mainline, every round: when an **enabled** zone with a **passive trip at or below HOT** (85 °C) has **every**
  `cpufreq-*` cooling device bound to it (`thermal_zoneN/cdevK` links against `cooling_deviceM`, compared with `test
  -ef`) and its `temp` **reads a number within 15 °C of the hottest reading** of the round (a zone whose sensors
  all fail reads nothing; a stale or zero value sits far below the die, and a kernel that sees no heat would not
  throttle), the kernel throttles and the guard only watches. On that transition it lifts the caps it set itself (a
  marker, `/run/mu300/thermal-capped`, set at HOT and cleared when nothing is below the ceiling; it outlives a
  restart, so a cap from before the module loaded does not stick for ever) back to the profile's ceiling, and leaves
  `scaling_max_freq` alone from then on. A cap that is not ours (eco's 1.5 GHz, a profile's) is left. With the zone
  gone (`rmmod`), a cluster left out of the maps, the zone disabled or its reading not to be trusted, it caps again,
  with a log line on each transition. Bindings alone are not trusted: the handoff would otherwise fail open.
* The 105 °C power-off stays on mainline in both states; the kernel's own 110 °C critical trip is the second line.
  The LED alarm is unchanged on every kernel.

`extra-modules` loads the module right after the PMIC watchdog: `modprobe mu300_thermal`, else `insmod` from the
bundle's directory (`/lib/modules/<release>/mu300_thermal.ko` on OpenWrt, `extra/` on Ubuntu, where depmod may not
have indexed a bundle yet); the vendor 5.4 kernel has no such file and nothing is tried. Tests
(`tests/test_device_scripts.py`, `ThermalGuard` and `SipaDele`): the vendor kernel by release (LED only), mainline
without the zone (caps, powers off), the handoff with the bound zone (no step at 90 °C, power-off at 105 °C still),
a zone whose `temp` is missing, not a number, stale (40 °C against 90 °C sensors) or whose passive trips lie above
HOT (all cap), a cluster left out, a disabled zone, no cooling device at all, the marker lifted on the handoff and
after a restart, capping again when the zone is gone, and the loader's
`modprobe`/`insmod`/already-loaded/failed paths; under dash, bash and (`test -ef`, `grep -qsx` on an unmatched glob
checked separately) busybox ash.

Built against the release trees: `mu300_thermal.ko` for 6.18.56 (`vermagic=6.18.56 SMP mod_unload aarch64`, 9 000
bytes with BTF) and 7.2.10 (`vermagic=7.2.10 SMP preempt mod_unload aarch64`), no warning.

**The panel.** System > CPU has a read-only "Thermal" card from standard thermal sysfs (`mu300-cpu status --json`'s
new `thermal` array: every zone's type, temperature, trip points and the cooling devices bound to it with their
states; zones with trips first). It writes nothing: the trips stay the device tree's (the fork's trip editor was not
taken).

**Device test (F50-B, Ubuntu 24.04, v2026.10.22, kernel 7.2.10, 2026-10-12).** The board had been up 5 minutes
on the release kernel; the test copies of `thermal-guard` and `mu300-cpu` were put in place (the release ones kept
and restored at the end) and `mu300_thermal.ko` (the 7.2.10 build) inserted by hand - nothing of the boot image or
kernel changed.

* Before: 19 zones, none with a trip point; cooling devices `cpufreq-cpu0` 0/9, `cpufreq-cpu4` 0/9, `cpufreq-cpu7`
  0/10, `devfreq-23140000.gpu` 0/2; hottest 39.2 °C.
* `insmod`: `mu300-virtual-thermal virtual-sensor@0: soc-thmzone: the hottest of 11 zones`; `thermal_zone19`
  `type=soc-thmzone mode=enabled policy=step_wise`, trips `0 passive 70000 hyst 1000`, `1 passive 85000 hyst 1000`,
  `2 critical 110000 hyst 2000`; `cdev0 -> cooling_device2 (cpufreq-cpu7) trip 1 weight 410`, `cdev1 -> cooling_device1
  (cpufreq-cpu4) trip 1 weight 410`, `cdev2 -> cooling_device0 (cpufreq-cpu0) trip 1 weight 1024` - the three maps of
  the 85 °C trip, with the DT's contributions; the five vendor cooling nodes left out, as expected. Three seconds
  later `thermal-guard: kernel thermal zone soc-thmzone throttles the CPUs: watching only, power-off at 105000 mC
  stays`. `mu300-cpu status --json` listed 20 zones; the soc entry: three trips, three cooling devices at state 0.
* Load, `yes >/dev/null` on all 8 cores: 38.7 → 64.1 °C in 5 s, 78.0 at 30 s, 84.4 at 50 s, 85.3 °C at 65 s; then
  the kernel throttled: cooling states `cpu0=1 cpu4=1 cpu7=1` and `scaling_max_freq` **read** 1846/2171/2041 MHz
  against the user values 2002/2301/2210 (the QoS cap shows through `policy->max`), the temperature held at
  84.4-85.3 °C, the states flapping between 0 and 1 around the trip (100 ms passive polling, 1 °C hysteresis).
  `thermal-guard` wrote nothing (its only line in that time: `too hot (SoC 85327 mC): LED alarm on`) and `mu300-cpu
  status` said `thermal throttling: active` from the cooling states. Writing `cpuinfo_max_freq` into
  `policy7/scaling_max_freq` under the cap read back 2210000 with the state at 1 a moment later - inconclusive, the
  states were flapping at that second; the cool-down sample right after showed the cap again (`policy7 cur 1703 /
  max 2041`, state 1).
* Load off: 85.3 → 60.1 °C in 5 s, states 0/0/0 and `scaling_max_freq` back to 2002/2301/2210 by itself (the user
  request was never changed), `cooled down (SoC 64103 mC): LED alarm off`.
* `rmmod`: `kernel thermal zone soc-thmzone gone: capping cpufreq again` within 5 s, no zone with trips left. The
  loader path: the `.ko` copied to `/lib/modules/7.2.10/extra/` and the new `extra-modules` run - `loaded
  mu300_thermal` (`modprobe` had no index, `insmod` by path took it), the zone back, `thermal-guard` handed over again
  5 s later. The guard alone, with the service stopped and HOT set 2 °C under the current temperature for two rounds:
  `scaling_max_freq` 2002000 2301000 2210000 → 1703000 2054000 1872000 (two steps each) and the marker
  `/run/mu300/thermal-capped` present; a cool run lifted them back to 2002000 2301000 2210000.
* End state: the release `thermal-guard` and `mu300-cpu` restored (same md5 as the backup), the service active, the
  module not loaded and no `mu300_thermal.ko` under `/lib/modules`, `/run/mu300` without thermal markers, `uname -r`
  7.2.10 - the release kernel, which was never replaced (no `mu300-update kernel`, so no `rollback-boot` needed).

Open: the U30 Air (same SoC, its own DTB) is untested; its `thmzone-cells` may name other zones, which the module
reads from the tree. Not taken, as the review decided: the fork's CPU voltage-offset driver.
### 49. The SIM's own number in the panel: CNUM, else the IMS identity, on full rounds only

The panel showed IMEI, IMSI and ICCID but not the SIM's own number (MSISDN). Ported from kanoqwq's fork
(0d93695, reviewed in `docs/superpowers/reviews/2026-10-11-kano-clean-tf-7.2.md`: "CNUM on full rounds only, never
in the fast tier"), measured so far on this machine only (unit tests; the device checks are in the PR).

* **Two sources.** `AT+CNUM` reads the number the SIM carries (`+CNUM: "","+905551234567",145`; type 145 is
  international, a "+" is put in front when the SIM left it out). Many SIMs carry none - the answer is `OK` alone or
  an empty string - and the number then comes from the IMS public identity the operator provisions, `AT+SPPAURI?`
  (what the stock RIL's `getPAU` reads): a `tel:` URI first, else a `sip:`/`sips:` URI whose user part is an
  international number. A bare numeric SIP user part is the IMSI on many networks and is **not** taken as a number.
  3 to 15 digits (E.164), nothing else, or nothing at all - the panel never guesses.
* **Where in the tiers.** The IMS identity exists only once IMS is registered, later than the SIM is read at boot, so
  the number cannot live in the 6 h identity cache (`sim.json`) the way IMEI/IMSI/ICCID do: a miss at boot would
  stay a miss for hours (kano's own regression). It is asked on **full rounds only** (`cell`, every ~5 s while the
  page is open): an empty answer is asked again on the next full round (two commands, about 0.3 s at the measured
  0.13 s per command, §40), a number found is kept in `/var/run/unisoc-modem/own-number` for the boot and not asked
  again (a SIM change goes through a reboot, the same assumption the identity cache makes). The fast tier (1.5 s)
  never sends either command, and neither does `mu300dash`'s live `signal` read.
* **Personal data.** The number reaches the browser in `status`'s `cell.msisdn` / `cell.msisdn_src` (`sim` or
  `ims`), a read-only method of the existing ACL; the home page shows it under ICCID, masked like the IMSI
  (`+905****567`) until "Show SIM identifiers", and the row is not there at all when neither source has one. It is
  never written to flash: `sim.json` stays IMEI/IMSI/ICCID, the runtime files are root's only (`umask 077`), the
  collector prints nothing, and the panel's operations log keeps its rule (method, time, outcome - no IMSI or
  numbers). Translations: `Own number` in all 31 catalogs (`tools/luci-i18n.py update`).
### 50. Three guards for the installers: the boot image read back from the medium, bounded SD-card stages, no re-run in the same boot

What #52 looked like from the outside (§38a): the Magisk installer, OpenWrt to the card, silent for good, a `dd` at
100 % of one core that `kill -9` did not end, and every retry adding another one until the board was rebooted. §38a
removed that read past the end of the eMMC, so the known trigger is gone; what stayed was that nothing in either
installer would have told the user anything if the card, or the SD host, stopped answering for another reason: a
command stuck in the kernel sits in D state, the installer waits on it forever, and `install.sh`'s `su_do` never
returns. kanoqwq's TF installer (`tf-stage.sh`, `tf-install-worker.sh`, read as a reference) has three ideas for
that, taken here in our own shape - one `android-install.sh`, no slot layout of its own, no vold scan beyond
`sd_release`:

**1. The boot image is read back from the medium, into a file.** Both installers verified `boot_<linux slot>` after
writing it - `install.sh` with `sha256sum` of the whole partition, the Magisk installer with `mu300-update`'s
`write_boot`, which hashes a `dd | head -c | sha256sum` pipeline of the first pages - and a mismatch stopped before
`misc`. Two things were weaker than they looked: a read that fails inside a pipeline leaves a short hash and no
word of why, and a read right after the write may be served from the page cache rather than the eMMC. Now every
install drops the caches (`echo 3 > /proc/sys/vm/drop_caches`) and reads back exactly the image's length in whole
4096-byte blocks with one `dd` into a file (`$T/mu300-boot.rb` for the computer installers, `$W/boot/readback` for
the zip), whose exit status counts; the sha256 of the file's first `len` bytes must be the image's. The Magisk
installer's `boot_readback` does this after `write_boot`'s own check and reads the AVB footer block back too, and
its refusal says which step failed (`dd failed`, `short read`, `sha256 differs`): `boot_b read back from the eMMC is
not the image that was written (sha256 differs); Linux was not armed: misc was not changed, so Android keeps booting`.
`install.sh` and `install.ps1` keep their message (`boot_b verify failed (slot a still active, Android keeps
booting)`). What is written where is unchanged.

**2. The long SD-card stages run bounded, in a process group of their own.** In SD mode `android-install.sh` runs
the format (`mke2fs`, 900 s), each system's unpack (`tar`, 3600 s; the vendor tarball 900 s), the removal of the old
or half-installed system (900 s) and a final flush (`sync`, 1800 s, before the OK line, where the trap used to sync
after it) through `stage_run NAME LIMIT CMD`: the command in a session of its own (`setsid`, Android's toybox has it;
without it a plain background job), its pid and its exit status in files, and the installer polling every 2 s
instead of waiting on it. A stage ends when it passes its limit, or when the card's completion counters
(`/sys/class/block/mmcblk1/stat`: reads and writes completed, sectors read and written - not the time fields, which
move while a request only waits) have not changed for 120 s. Then the group gets TERM and KILL (a process in D state
ignores both, and is never waited for), the run says what happened and what to do -
`the unpack ubuntu stage timed out (no I/O progress on mmcblk1 for 120 s) and was stopped; nothing more is written` /
`reboot Android before running the installer again` / `the card stays mounted at ..., with no sync and no unmount
(both would wait on that request)` - and exits 1 before `MU300-INSTALL-OK`, so neither installer writes the boot
image or `misc`. The EXIT trap (`sd_exit`) then flushes and unmounts nothing: a `sync` or an `umount` would hang on
the same request. On the eMMC the stages run as before (`STAGE_DISK` empty): Android keeps the eMMC's counters
moving, and it has not failed this way. When the stat file cannot be read the stall rule is off and the run says so;
the limit still applies. The counters are read from `$MU300_SYSFS`, the clock is `date +%s`, the knobs for tests are
`MU300_STAGE_STALL` and `MU300_STAGE_POLL`.

**3. No second run in the same Android boot.** A timeout writes `mu300-install.stalled` - the first line Android's
`/proc/sys/kernel/random/boot_id`, the second the stage, the time and the reason - into `MU300_LOCK_DIR`
(`/data/local/tmp` for the computer installers, `/data/adb` for the zip, whose work directory is new each run and
gone at its end). `android-install.sh` checks it before anything else; the Magisk installer checks it in `main`
right after `env_check`, before the plan: a lock of the running boot is a refusal (`an earlier run of the installer
timed out in this Android boot (stage unpack ubuntu, ...): the SD card request it waited on is still stuck in the
kernel` / `reboot Android, then run the installer again`), a lock of an earlier boot is stale and removed, and a
run that goes through removes its own. The zip also keeps the device script's output at
`/data/adb/mu300-device-install.log` (mode 600) when that script fails, and says so; `install.sh` names its
`work/device-install.log`, `install.ps1` now writes one.

Tests: `tests/test_android_install.py` (`Stages`: the stall and the deadline end a stage and its grandchild and
write the lock; progress keeps it alive; no counters means the limit only; the eMMC runs it plainly; the same-boot
re-run is refused and a stale lock removed; a clean run leaves no lock; `sd_exit` after a timeout runs no `sync` and
no unmount; under `set -e` the OK line never comes; the wiring), `tests/test_magisk_installer.py` (a `dd` whose
read-back differs or fails: `misc` unchanged, Linux not armed; the lock of this boot refused before the plan, a
stale one removed; the lock directory handed to the device script; the kept log). macOS has no `setsid` (the tests
stand one in with Python's `os.setsid`) and no `timeout`; the stages are driven by the script's own `date +%s` loop,
so nothing else is needed. In a container where the test runner is PID 1 the killed grandchild stays a zombie,
which the test counts as dead.

Not done here, for a device with a card: (a) a card installation from a computer and from a zip must still go through,
with `[device] creating ext4 mu300sd`, `installing <os>` and `MU300-INSTALL-OK` in the log, no `mu300-install.stalled`
afterwards, and `mu300-stage.*` gone from the work directory; (b) the stall path itself - pull the card during the
unpack, or hold the SD host's clock - must end the stage within about two minutes with the three lines above, leave
the lock in `/data/local/tmp` or `/data/adb`, and the next run must be refused until a reboot, after which it must
go through; (c) `cat /sys/class/block/mmcblk1/stat` must change while `tar` writes to the card (if the counters do
not move for a healthy card, the rule would end a working stage: the field numbers are the ones of the kernel's
`Documentation/admin-guide/iostats.rst`); (d) the time the format and the unpack take on a slow card against the
limits (900 s, 3600 s); (e) `setsid` present in Android's `/system/bin` (toybox), and the zip's `busybox` not in the
device script's PATH; (f) the boot image read-back on both installers: `dd` into the file, then the hash, visible
in `strace` or by the file's existence while it runs.
### 51. SMS delivered directly (+CMT), acknowledged only once the pool has it; the SIM path stays as the fallback

Until v2026.10.22 the panel's SMS pool (openwrt-luci: mu300-smsd, mu300-sms, §46) learned of a new message the
roundabout way: the modem stored it on the SIM and said `+CMTI: "SM",n` on nr0, mu300-smsd saw the line in
mu300-atd's URC log and ran `mu300-sms sync` (`AT+CMGL=4`, decode, pool, `AT+CMGD` per slot). Two writes to the SIM
per message, a listing of the whole store, and the SIM as the only safe copy until the pool had it. kanoqwq's fork
delivers directly instead (GSM 27.005 `+CNMI` with mt=2: the modem forwards the SMS-DELIVER as a `+CMT:` frame and
waits for `AT+CNMA`); this is that mechanism, ported into this tree's layout.

**Mechanism.** mu300-smsd starts as before: `AT+CNMI=2,1,0,0,0`, a first `sync` (what the SIM holds), then
`AT+CMGF=0`, `AT+CSMS=1`, `AT+CNMI=3,2,2,0,1`. If any of the three is not `OK` (or `MU300_SMS_DIRECT=0` says not to
ask), `AT+CNMI=2,1,0,0,0` is asked again and only the +CMTI path runs, exactly as before. With direct delivery on
(`/run/mu300-smsd.direct` exists) every new message comes as two lines on nr0, where +CMTI came too: `+CMT: ,<length>`
and the PDU. mu300-atd's nr0 drainer (and its drain and collect on the command channel, should a frame come there)
hands both lines to `mu300-cmt-spool` on its **stdin** - never argv, which is public - and that writes the PDU as
`$POOL/incoming/cmt-<epoch>.<random>.ready` via mktemp and rename, fsyncing the file and the directory (busybox
`fsync`, or coreutils `sync FILE`; never a global sync). The URC log gets one fixed word, `+CMT (PDU spooled)` or
`+CMT (not spooled)`: not the header, which in text mode would carry the sender, and never the second line. A frame
inside a reply is taken out of it (a client parsing `AT+CMGL` would read the PDU line as one of its own). Every 5 s
mu300-smsd pools each `*.ready` with `mu300-sms import-pdu FILE` and **only then** sends `AT+CNMA=1`; an import or an
acknowledgement that fails ends the round and is retried, three failed rounds in a row set the files aside as
`*.failed` and fall back to the SIM path. `import-pdu` refuses anything the codec makes no message of, then parks the
PDU in `$POOL/parts` (mktemp, rename, fsync) and absorbs the parked parts with the same decoding and grouping a SIM
listing goes through, so a long message's parts wait for each other there as they did on the SIM, with the same
`MU300_SMS_PARTIAL_WAIT`; the periodic sync lists the SIM and the parked parts together, so a part whose siblings
never come is pooled after the hour, and the parts of one message join across the SIM (a class 2 part) and the air.
The pool's dedupe (fingerprint, tombstones) applies: a message the modem delivers again after a lost acknowledgement
is not pooled twice, and one deleted from the pool stays deleted. The daemon exports `MU300_AT_LOCK_WAIT=8`, so a
client stuck on the AT channel cannot hold the receiver behind mu300-at's 90 s default. Everything that writes as root
into the pool (`import-pdu`, the spooler, the daemon's spool loop) refuses symbolic links and directories that are not
ours (`own_dir`/`own_file`, mu300-update's lock rule) and makes the directories mode 700.

**What the modem does (U30 Air, Vodafone TR).** `AT+CNMI=?` gives `(0-3),(0-3),(0-3),(0-2),(0-1)`, `AT+CSMS=?`
`(0-1)`. It answers `OK` to `AT+CNMI=3,2,2,0,1` and then reports `+CNMI: 3,2,1,0,1` - it keeps a bm of its own, so
the daemon's periodic check (every full sync, after which it re-applies the setting) looks at mt alone. ds=0 rather
than the fork's ds=1 on purpose: nothing here asks for status reports (no SRR bit), and a report routed to the TE
would need an acknowledgement of its own, which is the one thing that makes the modem drop the routing by itself
(27.005: no CNMA in time, mt and ds back to 0). A two-part reply from 7000 came as two frames (`+CMT: ,157` then
`+CMT: ,75`, three seconds apart), the second only after the first was acknowledged; the SIM/ME store stayed at
`"ME",0,0`. The modem held an unacknowledged message for two minutes without dropping the routing (measured by
accident: the daemon was stopped between the frame and its import, the spool kept both PDUs, the restarted daemon
imported and acknowledged them and `+CNMI?` still said `3,2,1,0,1`).

**Device test** (`mu300-sms send 7000 KALAN`, the line answers within seconds):

```
daemon.info mu300-smsd[9008]: sync: 0 new, 0 on the SIM, 42 in the pool, 0 moved off the SIM
daemon.err  mu300-smsd[9008]: mu300-smsd: direct delivery is on (+CMT frames into /etc/mu300/sms-pool/incoming)
daemon.info mu300-smsd[9008]: import: 0 new, 43 in the pool, 1 waiting for its other parts
daemon.err  mu300-smsd[9008]: mu300-smsd: pooled and acknowledged cmt-1791808049.ePLCmA.ready
daemon.info mu300-smsd[9008]: new: 000049 from 7000 2026-10-12 15:27:29
daemon.info mu300-smsd[9008]: import: 1 new, 44 in the pool
daemon.err  mu300-smsd[9008]: mu300-smsd: pooled and acknowledged cmt-1791808053.iFAgce.ready
# /run/mu300-at/urc/stty_nr0.log:   +CMT (PDU spooled)  (twice; no PDU, no header fields)
# AT+CPMS? -> +CPMS: "ME",0,0,"ME",0,0,"ME",0,0        AT+CNMI? -> +CNMI: 3,2,1,0,1
# mu300-sms show 49 -> sim index:   not on the SIM; ubus call mu300dash sms_list lists 000049 (the panel's page)
```

The fallback, forced with `MU300_SMS_DIRECT=0`: `the modem did not take direct delivery (or MU300_SMS_DIRECT=0); new
messages are stored on the SIM and announced (+CMTI)`, `+CNMI: 2,1,0,0,0`, and the same send answered through the old
path - `+CMTI: "SM",2` in the URC log, `new: 000053 from 7000`, `sync: 1 new, 1 on the SIM, 48 in the pool, 2 moved
off the SIM`, `sim index: 1,2`, the SIM empty again afterwards. The service restarted went back to direct delivery.

**Tests** (`tests/test_sms_pool.py`, `tests/test_device_scripts.py Atd`): `import-pdu` pools a message with no AT
command, is idempotent, honours tombstones, joins parts and leaves the waiting ones parked, pools a stale part by a
sync, joins a SIM part with an air part, refuses non-hex/odd/undecodable/overlong PDUs and every link (a spool entry,
the parts directory, the pool), fsyncs the parked part before the pool is touched; the spooler writes mode 600 into a
700 directory with the two fsyncs and nothing else, refuses bad frames and linked directories; the daemon (Linux
only: it tells a live holder by `/proc`) asks for direct delivery after the first sync, acknowledges after the import
and in spool order, falls back on each refusal and on `MU300_SMS_DIRECT=0` with +CMTI still working, never
acknowledges a failed import, gives up after three rounds, keeps the file when the ack is refused, puts the routing
back when `+CNMI?` says the modem dropped it, sets a linked spool entry aside; mu300-atd on a pty spools a frame from
nr0, from inside a reply (kept out of the answer), from a drain, logs the fixed word only, drops a text-mode frame
(sender and text reach nothing), and goes on without the spooler.

**Ubuntu.** mu300-atd and the spooler are on every system, so a `+CMT` frame there is spooled too and never logged -
but nothing on Ubuntu asks for direct delivery, and that is deliberate: the system's SMS tool, `sms`, has no daemon
and no pool; `sms watch` polls the store (`AT+CPMS?`/`AT+CMGL`), which cannot miss a message, and `sms list`/`read`
read the SIM. A message routed to the TE needs something running to acknowledge it, or the modem drops the routing
and stores the next ones unannounced; a daemon with a pool is what openwrt-luci has and Ubuntu does not. So on Ubuntu
the modem stays in its storage mode (the fork's smsd is openwrt-luci only here as well), and a PDU that ever lands in
`/etc/mu300/sms-pool/incoming` there (someone set `AT+CNMI` mt=2 by hand) is kept, unacknowledged, for an
`mu300-sms import-pdu` that does not exist on that system - documented rather than half-built.
### 52. The lock reset deleted the saved locks whether or not the modem took them: a verified reset

`lock reset` (PR #99; the Locks page's "Reset all to automatic", and "Reset locks and switch" before an OS switch)
sent the seven automatic values, deleted the five saved settings, restarted the stack and refreshed the cache. It never
looked at an answer: a write the modem refused, a silent channel, or a mode query that failed (the mode write carries
the modem's own slot1 and primary-SIM fields read a moment before) all ended the same way, with the saved settings
gone and the page reading back whatever the modem had. kanoqwq's fork (23361ce, reviewed in
`docs/superpowers/reviews/2026-10-11-kano-clean-tf-7.2.md`) does this properly; its version sits on an asynchronous
lock-job queue (`lock-apply.sh`, `lock-jobs.sh`) that was not wanted here. The semantics are ported onto our
synchronous tool; the job queue is not.

**What `lock reset` does now** (`openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/lock`):

1. One reset at a time, as before (the apply directory; a dead holder's directory is taken over). A tombstone an
   earlier reset left (below) is finished first.
2. `AT+SPTESTMODE?` must answer, and the two fields that go back out (slot1, primary) must be digits, or nothing is
   sent: "The modem did not answer the mode query; nothing was sent". Every other AT string of the reset is a fixed
   constant.
3. The seven writes (`SP5GRAN=1`, `SPTESTMODE=134,<m1>,<prim>`, `SPENDC=1`, `SPLBAND=1,0,0,0,0,0`, `SPLBAND=2,0,0,0,0`,
   `SPFORCEFRQ=12,4`, `SPFORCEFRQ=16,4`) each have their answer checked: an explicit `ERROR`/`+CME ERROR` stops the
   reset there ("The modem refused a write", with the command). Silence is not a failure - several vendor setters
   apply the value and omit the final OK (the boot replay already relies on that) - the read-back decides.
4. Read-back before the restart: `SPTESTMODE?` first field 134, `SP5GRAN?` 1, `SPENDC?` 1, `SPLBAND=0` an empty mask
   or the full LTE table, `SPLBAND=3` an empty mask or the full set of the NR bands SP5GCMDS lists that the SPLBAND
   codec can carry (n6 is supported and not encodable, so the capability list itself is the wrong comparison),
   `SPFORCEFRQ=12,3` and `16,3` exactly `12,3` / `16,3`. Three tries a second apart; a mismatch names the step.
5. The one stack restart (under mobile-data's radio lock, as every apply), then the same read-back again, up to ten
   tries three seconds apart: right after `SFUN=4` the modem answers `CFUN?` but not the lock reads for a few seconds
   (the guard in `do_get` exists for the same reason).
6. Only now the saved settings go: a `reset_pending` tombstone is written first, then `mode endc lte nr cell` are
   deleted, then the tombstone. A reset interrupted between the two (a kill, a reboot) leaves the tombstone, and the
   next `apply` finishes the deletion before it saves its own setting, the next `replay` (early or late) before it
   reads anything to replay - so a half-deleted set is never replayed and a fresh setting is never deleted later.
   The replay switch (`auto_apply`) stays, as before.
7. The result - `{"state":ok|failed|interrupted|running,"ts","end","pid","error","step","cmd"}` - goes to
   `/var/run/unisoc-modem/lock-reset.json` and to stdout (exit 1 on a failure). `lock get` carries it as `reset`, so
   `mu300dash lock_get` does too: the page polls that, since the reset was already started detached from the rpcd
   call (`setsid lock reset`, PR #137's budget) and now takes 8-10 s plus whatever the radio lock makes it wait. A
   result still `running` whose pid is gone is reported as `interrupted`. A failed reset keeps the saved settings,
   says why ("Reset failed: ... The saved lock settings were kept."), and refreshes the cache, because the modem may
   hold part of the automatic values by then - a partial write cannot be rolled back. The home page's "Reset locks and
   switch" stops on a failed reset instead of switching to an Android that would come up with the locks the modem
   still has.

**Measured on F50-B** (openwrt-luci v2026.10.22, kernel 7.2.10, Netgsm on LTE B1, EARFCN 100, PCI 69):

- `lock apply lte 1` (CLI, 5.3 s) and `mu300dash lock_set cell=lte:100,69` (rpcd, detached, done 6 s later) read back
  as `+SPLBAND: 0,0,0,1,0` and `+SPFORCEFRQ: 12,3,100,69`, saved as `lte=1`, `cell=lte:100,69`.
- `mu300dash lock_set reset=auto`: `lock_get` showed `reset.state=ok` 10 s after the call; the log: writes and first
  read-back in 2 s, `SFUN 5 -> 4` 7 s, the second read-back matched at its first try, `reset verified (8s)`. Read-back
  afterwards: `SPTESTMODE 134,134,0,19,3,1`, `SP5GRAN 1`, `ENDC 1`, `SPLBAND=0 -> 0,482,0,149,0`,
  `SPLBAND=3 -> 0,0,0` (a cleared NR mask reads back empty here; after a boot the same modem reported the full set
  `553,0,272` - both count as automatic), `SPFORCEFRQ 12,3` and `16,3`; the state directory empty.
- A reset killed with SIGKILL 1.5 s after its start (during the writes: the modem already had the cleared masks, no
  restart yet): the saved `lte` kept, `lock_get` -> `{"state":"interrupted","error":"The reset was interrupted"}`,
  the apply directory left with a dead pid; the next `lock reset` took it over and verified in 8 s.
- The tombstone: with `reset_pending` and a saved `lte`, `lock apply endc on` left `endc` alone in the directory;
  with `reset_pending`, `lte` and `endc`, `lock replay early` (its marker redirected) emptied the directory, wrote the
  marker and sent no AT command.
- The CLI's final `lock reset` printed `{"state":"ok",...}` in 8.4 s and left no lock in the modem.

Not measured: a modem that refuses one of the seven writes, or that answers the read-back with something else - on
this board every write took. Those paths are covered by the unit tests on a fake modem that answers each read from
what the writes so far have changed (`tests/test_unisoc_plugin.py`), including the kill between the tombstone and the
deletion (the `rm` stub kills the tool at that moment). The single `apply` paths still send their write and save the
setting unverified; only their start now finishes a pending tombstone.

Noted during the test: F50-B's openwrt-luci system has LuCI's default LAN `192.168.77.1`, the same subnet as F50 #1
on the same computer (its Ubuntu system is at `192.168.79.1`); it was reached over its USB link-local address
(`root@fe80::50:78ff:fe24:7701%en17`). The subnet-per-device rule of §33b holds only when every system of the board
is configured.

### 53. A carrier name shown as hex: UCS2 from a modem whose character set is not UCS2 (#174)

A user's panel showed `Carrier: 4E2D56FD8054901A` beside `PLMN: 46001` (F50, OpenWrt, 6.18, v2026.10.20; issue
#174). That is 中国联通 in UCS2, as hex. Not measured on our boards (no SIM whose name is outside the default
alphabet): the report, the code and unit tests.

* **Why it was not decoded.** The collector (`unisoc-modem/cell`, `cops_fragment`) read a name as UCS2 hex only when
  `AT+CSCS?` said `UCS2`. This modem says `HEX` (§46) and does not treat the operator name the way that character
  set is documented: a name that fits the default alphabet comes as text (the panel has shown `vodafone TR` since
  it asks for names), and by this report a name the SIM or the network holds in UCS2 comes as that UCS2 in hex. So
  the character set does not say how the name is written; it did not for text-mode SMS addresses (§26c) or USSD
  (§26d) either.
* **The rule now.** With character set `UCS2`: as before (any whole number of code units that is valid UTF-16 with no
  control character). With any other character set, or none read: the same decoding, but only for a text that cannot
  reasonably be a name - at least two code units (8 hex digits; `CAFE`, `BEEF` and `FACE` are words), not all decimal
  digits (a name of digits stays a name: `12345678`, `00540054`), and no private-use or non-character code point.
  Anything that fails stays the text the modem gave; with no name at all the page still names the operator from the
  PLMN (`common.js`). No carrier and no PLMN is hard-coded.
* **Nothing to clear.** What is kept per PLMN in `/var/run/unisoc-modem/operator` is the modem's own line and its
  character set, not the decoded name; `cell.json` is rewritten every full round. The runtime directory is a tmpfs,
  and an update ends in a reboot, so no old value survives the fix.

Open: a name of two or more code units that are all decimal digits (U+8054 U+9010 would be `80549010`) stays hex
under a character set other than UCS2 - the price of leaving digit names alone. Not seen in a report.
### 54. A webhook body of the user's own for SMS forwarding: values escaped for the type, never evaluated (#171)

The webhook of §39 sent one of two fixed bodies (JSON or a form with `sender`, `time`, `text`, `device`,
`message`), which no chat service accepts as it is (issue #171: Lark/Feishu, DingTalk, WeCom, Slack, Discord, Bark,
ntfy). Measured on this machine only (unit tests against the stub HTTP helper: dash and bash on macOS, busybox ash
and dash with busybox 1.37 as awk in a Debian container); not sent from a device to a real service.

* **A backslash in a template was stored bare (found here, older than the body).** The adapter wrote a template to
  its one line with `gsub(/\\/, "\\\\")`. What that replacement means differs between awks: macOS's awk writes two
  backslashes, busybox awk - the device's - writes one. So on the device a template's `\n` (two characters) was
  stored as it was and read back as a line break, and `\"` lost its backslash. Nobody reported it for the message
  template, but a JSON body is made of exactly those. `esc_tpl` now doubles backslashes with `index()` and a
  concatenation, with no replacement string; the test that pins it fails with the old code only where awk is
  busybox, which is why the macOS run never saw it.

* **What was added.** A body template of the user's own (`webhook_body` in `/etc/mu300/sms-forward.conf`, stored on
  one line like the message template) with `{sender}`, `{time}`, `{text}`, `{device}` and `{message}` (the message
  template filled in), and a third type, plain text. The type is the `Content-Type` - which stays the device's to
  set, never a header of the user's - and decides how a value is written into the body: JSON as the inside of a
  string (quote, backslash and every control character escaped; the quotes are the template's), form
  percent-encoded, text as it is. An empty body is the standard one, byte for byte what it was; for plain text that
  is the message alone.
* **Why a message cannot break out of the body.** One awk function (`fill` in `mu300-sms-forward`, which the message
  template now uses too) gets the template and the values in its environment and only copies them: no shell, no
  `eval`, no `awk -v` (which reads escapes), and one pass - a `{sender}` that arrives inside an SMS is text. The
  tests send a sender and a text made of quotes, backslashes, `","admin":true`, `$(...)`, backticks, `&d=e` and
  control characters through each type and parse what comes out.
* **Limits.** The panel takes 2000 bytes of template and no control character but newline and tab; the forwarder
  refuses a filled-in body over 64 KiB (`the webhook body is too large` in the log, not retried), so a template that
  repeats `{text}` cannot grow without bound.
* **Not a secret.** The address and the headers never come back to the page (§39); the body does, because a
  template that cannot be read cannot be edited, and an empty field has to mean "the standard body", not "keep".
  The page says so and tells the user to keep keys in the address or a header. A service that wants a key inside
  the body is the case this does not serve well.
* **Not validated.** A JSON body is not checked when it is saved: the device has no JSON parser the tests can run,
  and a check that wrongly refused a valid body would be worse than none. "Send test" sends the saved body and the
  log shows the server's status.

Open, from the same issue: a service that answers HTTP 200 with its own error inside (DingTalk `errcode`, Feishu
`code`) is logged as delivered - the HTTP helper passes on the status and nothing of the reply's body
(`sms-forward-http.uc`), so that no reply reaches a log; and the delivery log (RAM, the last 100 lines) has no clear
button. Both are §58. Section 53 is PR #195's (the carrier name); this branch does not have it.

### 55. Imported Android files nobody but root could read: the CP was never loaded (#127, #135, #170)

Three users' F50s (China Telecom SIMs, OpenWrt on an SD card, mainline 6.18 and 7.2) had no modem: `mu300-atd`
restarted every 10 s with `can't create /dev/stty_nr1: No such device`, `radio.log` repeated `no valid answer to the
RIL handshake (AT+SMMSWAP=0)`, `/sys/kernel/debug/modem/modem` said `run_state: 255`, `modem_base: 0x0`. Two of them
found the five imported trees under `/opt/mu300/android` (`dev-properties`, `vendor`, `system`, `apex`,
`linkerconfig`) `0700 root:root`, files and directories alike, and got a modem by `chmod`. PR #143 (v2026.10.20) had
changed the account the daemons run as and the device nodes, not these files; #127's reporter measured v2026.10.20
and it still failed.

**Why the modes matter.** `modem_control` and `refnotify` do not stay root: `mu300vnd` through `setpriv` where the
system has the account (§41), else their own `setuid(1000)`. They keep `CAP_CHOWN`/`CAP_BLOCK_SUSPEND` and
`CAP_SYS_TIME`, nothing that reads past a mode. `cp_diskserver` stays root and does not care.

**Where 0700 came from.** `install.sh` on macOS with its folder on FAT or exFAT. Measured on this Mac (an exFAT
image, `android-vendor/extract-subset.sh` from the F50-B, then `tools/vendor-overlay.py`): the volume shows every
file and directory as `rwx------` owned by the user, the empty `ld.config.txt` made by `: >` included; `gettarinfo`
stored that, the tool sets the owner to root, and the overlay's 390 entries were 375 `-rwx------ root`, 14
`drwx------ root` and the link. A time before 1980 is clamped there too: `linker64` (1970 on the device) came out as
`Jan  1  1980`, local time. #127's listing has the property files at `Dec 31  1979` - that moment seen in UTC from a
host east of it, as UTC+8 would be - where a system installed from an ordinary folder has `Jan  1  1970`. The
initramfs copy is not affected: `boot/build-boot-image.py` decides 0755/0644 by `os.access`, which is why such a
device still boots and only the installed system's copy is wrong. Windows (the subset comes from the device's own
archive there) and a folder on a file system that keeps modes were never affected.

**What each state looks like** (F50-B, baseband `5G_MODEM_V2_22C_W25.39.4` - the same as #170's device - release
v2026.10.22, the trees changed by hand and the board rebooted):

| imported files | system, kernel | modem_control | Trusty lines in dmesg | result |
|---|---|---|---|---|
| all five trees 0700 | openwrt-luci, 7.2.10 | runs as uid 1000 | none | `run_state: 255`, `modem_base: 0x0` (#127) |
| all five trees 0700 | Ubuntu 24.04, 7.2.10 | `chroot: failed to run command '/vendor/bin/modem_control': Permission denied`, the service restarts every 4 s | none | the same |
| `vendor/etc` alone 0700 | Ubuntu 24.04 and openwrt-luci, 7.2.10 | (Ubuntu's log) `Failed to access xml, error /vendor/etc/modem_cp_info.xml: Permission denied` (and `_sp_`, `_ch_`), `modem_head_correct_load_info: can't get modem img!`, then `open /dev/spipe_nr2 failed, error: No such device` every second | `enter SEC_KBC_GET_TEECFG_FLAG`, `g_wifionly_flag = 0`, `enter SEC_KBC_STOP_CP`, `SEC_KBC_STOP_CP() ret = 0`, `SEC_FIREWALL_UNLOCK_CP_DDR() ret = 0`, `kbc_send_response rc = 4`, `enter SEC_KBC_GET_LOAD_MODEM_FLAG` - and nothing after it | `run_state: 255` (#170's dmesg, line for line) |
| `vendor/etc` alone 0700 | openwrt-luci, **5.4.254** | - (no vendor log, see below) | the same lines, and nothing after them | the same: the kernel makes no difference |
| as installed | each of the above on 7.2.10 | - | ... `GET_LOAD_MODEM_FLAG`, one second of image loading, `kbc_verify_all_avb2() ret = 0`, `SEC_KBC_START_CP() ret = 0`, `modem run = 1!` three times | data up 31-35 s after power-on |

With the property area unreadable the daemons end earlier (`Access denied finding property
"ro.vendor.radio.modemtype"`, `can't get modem type!`: #127's log) and never call Trusty. A `dump_table() len = 0`
under `SEC_KBC_STOP_CP` is printed on a good start too; the sign is what follows `GET_LOAD_MODEM_FLAG`.

#170 reads "mainline never starts the CP, 5.4 does, same installation". Its dmesg is the third row. The F50-B, with
the same baseband, starts the CP on 7.2.10 from that release's own Magisk zip (below), and with the files unreadable
5.4 fails exactly as 7.2 does. So the kernel is not what differed between that device's boots; what did is not
known (asked in the issue: the modes of the trees, the vendor log, and how each kernel was put on - a Magisk zip
imports the files again, `mu300-update kernel` does not).

**The Magisk zip's import** was measured for that reason (`magisk --install-module
mu300-magisk-v2026.10.22-openwrt-luci-k7.2.zip` on the F50-B, Magisk 30.6): the modem started (run = 1 at 14 s, data
at 32 s), so that path does not make 0700 here - but what it installed was wrong the other way. Under `magisk
--install-module` the umask is 000, and `collect_subset` names only files, so tar made the directories itself: 16
directories `0777`, `linkerconfig/ld.config.txt` `0666`. And tar keeps Android's owners: 32 libraries (bionic, the
VNDK) owned by uid 1000, six programs, `linker64` and one directory by gid 2000. Uid 1000 is the first login
account on Ubuntu, and root's `cp_diskserver` loads that libc: a login user could become root through it. (An
install started in the Magisk app goes through the zip's `update-binary`, which sets 022; not measured. The owners
do not depend on it.) Under a umask of 077 the same code makes `vendor/etc` 0700 - the third row.

**The fix.**

* `android-vendor-start`, before anything else (block `modes`): one `find` over the five trees for anything not
  root's, a directory that is not 0755 (0711, Android's mode for the property area, is left), a file in a `bin`
  directory that is not 0755, a property file that is not 0444, any other file that is not 0644. Nothing found: no
  write, 6 ms. Else five `find ... -exec` set owner and modes (links untouched, `-xdev`), the check runs again, and
  one line says how many entries and the first - to stderr and to `/dev/kmsg`, because OpenWrt starts this service
  before its log daemon - with a `vendor-modes-repaired` (or `vendor-modes-wrong`) mark in the boot timeline. This
  is the part that repairs an installed system: `mu300-update` carries the vendor files over as they are.
* `tools/vendor-overlay.py`: `host_free_mode` - the mode of an entry from where it goes (the same rule), never
  from the host. The same exFAT volume now gives `drwxr-xr-x`, `-rwxr-xr-x` in `bin`, `-r--r--r--` properties,
  `-rw-r--r--` for the rest.
* `tools/android-boot-image.sh`: `collect_subset`, `collect_gpu`, `collect_firmware` and `vendor_overlay` run under
  umask 022 whatever the caller has (the caller's is not changed), and the overlay is `chown -hR 0:0` before it is
  packed. `mu300-install.sh` and `android-install.sh` set umask 022 at the top. On the F50-B under Magisk's busybox,
  with the caller's umask 000 and 077: 334 `-r--r--r--`, 73 `-rw-r--r--`, 7 `-rwxr-xr-x`, 19 `drwxr-xr-x`, the
  property directory `drwx--x--x`, all `root/root`.
* `android-vendor-start` makes `/var/log` before it starts `logdw`. On OpenWrt the service is S09 and `/var/log`
  is made by `boot` at S10; procd starts the script at once, and when it reached the line first the redirection
  failed and `logdw` never ran: no `/var/log/android-logcat.txt` on three of four boots here. #135 reported the
  same after a reboot ("logdw did not start"), #170 shows no vendor log at all, and #127 had one because the
  service had been restarted by hand.

**Measured on F50-B with the new script** (release v2026.10.22 otherwise):

- openwrt-luci, 7.2.10, all five trees 0700 and the mixed owners an earlier zip install had left: repaired at boot,
  `kbc_verify_all_avb2` at 13.8 s, `up on sipa_eth0` at 31.7 s, daemons uid 1000, `android-logcat.txt` written.
- openwrt-luci as the v2026.10.22 zip had just installed it: `[   12.053529] android-vendor-start: 57 imported
  Android files and directories had an owner or a mode the vendor daemons cannot work with (the first:
  /opt/mu300/android/vendor); now root's, 0755/0644/0444`; marks `vendor-start` 11.98, `vendor-modes-repaired`
  12.07; afterwards nothing world-writable, nothing not root's; `run = 1` at 14.0 s, data at 31.9 s.
- Ubuntu 24.04, 7.2.10, all five trees 0700: 427 entries repaired between 9.16 s and 9.23 s, `run = 1` at 11.5 s,
  data at 34.8 s, daemons `mu300vnd`. The boot after it: no line, no mark, the modes unchanged.

Not measured: a Magisk zip built from this branch and installed end to end (its import functions were run on the
device; the zip was not rebuilt), 6.18, the U30 Air.

### 56. The VPN page showed a refused config without its reason; the engines' own defects are in the VPN module's FINDINGS 26i-26m

"There is a problem in the VPN part, mihomo and the like" (no details, no issue): the non-default engines were run
end to end on the U30 Air (OpenWrt openwrt-luci v2026.10.22, kernel 7.2.10, VPN module v2.0.0), from the command line
and through the page's own calls (`ubus call mu300vpn ...`). What was broken is in the module, and written up there
([mu300-linux-vpn FINDINGS 26i-26m](https://github.com/dikeckaan/mu300-linux-vpn/blob/main/docs/FINDINGS.md)): on a SIM
whose carrier lets DNS through to its own resolvers only, sing-box, mihomo and dae never found their server
(`BOOTSTRAP_DNS` 1.1.1.1 did not answer); a mihomo config with GEOSITE/GEOIP rules could not start, and switching to
it took the working tunnel down; dae was stopped every 40 s by a start check that cannot pass on kernels from 6.6 on;
a raw sing-box config that says nothing about DNS left the device and the router's DNS without names; `logs
ENGINE` hid the engines' own errors, `latency` said "unreachable" for every server, and `profile check ID`, which
the page calls, did not exist.

Two defects were the page's own. Its check asked for `profile check ID`, the spec's name for a command the module
only has as `check ID`: the backend now calls `check ID`, which every module version answers (the module gets the
other name too). And `mu300-vpn` ends a refused import, edit or switch with a line that says only that
nothing was done, after the line that says why:

    the mihomo config has no proxies or proxy-providers at the top level
    profile not added

`mu300vpn`'s `cli` took the last line of stderr as the message, so every refused config read "The profile could not
be added - profile not added" (and "The config was not saved - profile t-mh not changed"), whatever was wrong with
it: a YAML without proxies, a link dae cannot take, a config mihomo rejects. `cli_message` now takes the line before
such a closing line (`profile [ID] not added|changed`, `subscription [ID] not added|refreshed`, `profile ID does not
check: ...`, `profile ID cannot run on this system: ...`), never one of the CLI's `note:` lines, and the closing line
itself when it stands alone. Measured on the device with the backend in place: the same three requests now answer
with "the mihomo config has no proxies or proxy-providers at the top level", "the link turns the server's
certificate check off (allowInsecure), and dae cannot pin the certificate ...", and "mihomo rejects the config as
this driver rebuilds it (at rules[1], as mihomo counts) ..." (the last with the module's fix).

Through the page's calls, on the fixed module: `profile_add` (a mihomo YAML as text, an ss link as dae, a vless link
as sing-box), `profile_check`, `use`, `status` with the exit address, `logs` per engine, `killswitch` on and off,
`sub_refresh` (one, due) with `job`, `latency` (one, all), `engine_remove` refused while in use, `profile_remove`:
all as the page expects. `sub_add` takes https only, which could not be served on the test link (the CLI's
`--insecure` did the subscriptions there). Not looked at in a browser: the pages themselves.

### 57. A 64 GB unit whose partition table has userdata filling the disk, and no way to make room from Windows (#32)

Reported in issue #32, in three lines and without a number from the device: on a 64 GB unit a vendor firmware image
replaced the partition table by one in which `userdata` "fills the entire disk"; `install.ps1` refused it as a layout
it does not know; and a 4096-sector alignment computation came out as -4 MiB. **Nothing here was measured on a
device.** We have no unit with that table, and the issue has no `-Check` output, no sector and no name of the image.
Not known: which image it was, where `userdata` begins in that table, whether it is the last entry, whether the other
partitions are where the factory table has them, and whether the GPT's last usable LBA is the factory one.

What the code says about it:

* **The -4 MiB is the region arithmetic, and it is what a table that ends at the end of the eMMC gives.** Both
  installers take the free region from the first 4096-sector (2 MiB) boundary behind the last partition - the next
  one even when the partition ends on one - to the last boundary but one before the backup GPT (`region_probe` in
  `tools/storage.sh`, the same two lines in `install.ps1`). With the figures of #9 (122159104 sectors, last usable
  LBA 122155007) and `userdata` up to the last usable LBA, the partitions end at sector 122155008 = 29823 x 4096:
  the start is 29824 x 4096 = 122159104, the end of the disk, and the end is 29822 x 4096 = 122150912, which is
  8192 sectors or 4 MiB before it. Any table whose last partition ends in the last 2 MiB of this eMMC gives the
  same -4 MiB, so the number fits the report and does not tell where exactly `userdata` ends.
* When the issue was written, `install.ps1` printed that number ("only -4 MiB of free space after the last
  partition: this device has a different layout") and `install.sh` went on to `offer_repartition`. Since the fix
  for #65 a crossed region is an empty one in both, so Windows said "only 0 MiB" - and still had nothing to offer.
  The arithmetic is now a function there (`FreeRegion`) with the layout above among its tests.
* **`install.ps1` had no make-room path at all**; `offer_repartition` (#9b) existed in `install.sh` only. It now has
  `OfferRepartition`, the same steps in the same order: the first 34 and the last 33 sectors of the eMMC are copied
  to `work\gpt\gpt.head` and `gpt.tail` (that copy is the backup of the table) and nothing else is read;
  `tools/resize-last-partition.py --show` checks both GPT copies and refuses when `userdata` is not the last
  partition; at least 4 GiB stay with Android and Linux gets at least 800 MiB; the questions are the same (yes/no
  with no as the default, the GiB for Linux, the word `ERASE` typed as it is); the backup GPT is written before the
  primary; the table is read back and compared; the first 32 MiB of `userdata` are cleared so that Android formats
  it; the device reboots and the installer is run again. Only those three writes exist: the two copies of the table
  and the start of `userdata`. `-Check` prints the figures and writes nothing.
* Two things the Windows path does that `install.sh` does not: it compares the SHA-256 of the two pushed files on
  the device with the ones the tool made before `dd` writes them (a push that failed or stopped halfway would be
  written as it is), and it deletes the table files of an earlier run before it reads the table, so one of them
  cannot stand in for a read that failed. Neither was seen to go wrong; both are cheap.
* A refusal now carries its figures: the eMMC's size in GiB and sectors, the sector the partitions end at, the free
  MiB behind them, the 700 MiB needed there and what is missing; the tool's own reason when it refuses the table
  ("the last partition is 'x', not 'userdata'", a CRC that does not match); and, when there is too little to
  split, `userdata`'s sectors, the 4096 + 800 MiB needed and what is missing.

What is tested, and what is not: `tests/fakegpt.py` builds the table of #9 with `userdata` extended to the last
usable LBA (the other partitions' sizes are made up; only `userdata`'s sectors and the order matter), and the real
tool edits it. `tests/test_resize_last_partition.py` checks that the edit changes `userdata`'s last sector and the
CRCs and no other byte, and what is refused; `tests/installer.Tests.ps1` runs `OfferRepartition` under Windows
PowerShell 5.1 and PowerShell 7 against three stubs for the device and checks every answer that must change
nothing, the order of the writes, and the refusals. **Not run: `install.ps1` on a Windows machine against a
device, and either installer on a unit with this table.** The shrink itself has been done on one 32 GB unit (#9b,
issue #2); whether Android formats a 64 GB `userdata` that was shrunk this way after a vendor flash is not known.
`uninstall.ps1` does not offer to grow `userdata` back; `uninstall.sh` does.

### 59. The VPN page said "the other engines stay IPv4": with the module's IPV6=auto they are asked now (#202)

Issue #202, third point: with `IPV6=auto` a sing-box tunnel stayed IPv4 whatever its server could do. That was what
auto meant, and what the VPN page says under IPv6: "Automatic: WireGuard uses the IPv6 addresses of its config, the
other engines stay IPv4." The change is in the VPN module
([mu300-linux-vpn FINDINGS 26n](https://github.com/dikeckaan/mu300-linux-vpn/blob/main/docs/FINDINGS.md)): Xray,
sing-box and mihomo are asked at every start - an HTTP request to two IPv6-only addresses through the tunnel, before
any IPv6 is routed into it - and carry IPv6 only after an answer; `mu300-vpn status --json` says who decided
(`ipv6.source`: `probe`, `setting` or `config`). Measured there on the U30 Air, both answers on all three engines.

Here only the sentence changes, in the page and in every catalog: "Automatic: WireGuard and OpenVPN use the IPv6
addresses of their config; Xray, sing-box and mihomo are asked at every start whether IPv6 works through the
tunnel, and carry it only then; dae stays IPv4." The page's two rows need nothing: "The tunnel carries IPv6" reads
`ipv6.tunnel`, which is the answer, and "IPv6 guard" stays "Active" beside a tunnel that carries IPv6 because it
was asked (the module keeps the guard up through such a run: there is no moment between "refused" and "in the
tunnel"), which is what its text says: IPv6 outside the tunnel is refused. The chip on the overview takes
`ipv6.tunnel` first, so it says "IPv6 in the tunnel".

With a module from before this (v2.0.1 and earlier) the sentence is ahead of the device: there auto leaves those
engines on IPv4, as the old sentence said. **Not looked at in a browser:** the page was not opened for this change
(one string; `tools/luci-i18n.py check` passes), and the translations of the new sentence were written with it,
not read by a speaker of each language.

### 60. `/run` takes files from every user: the daemons' directories there are checked, and a squatted name is put out of the way (review of #145/#149)

Found while reviewing the call audio and voice API branches on F50-B (2026-10-13).

* `boot/init` mounts `/run` as a plain tmpfs, which is mode 1777 - like `/tmp`, not the 0755 systemd would give it.
  Any local user (a service account, the vendor daemons' own account of 41) can make `/run/<name>` before the
  daemon that expects to own it: measured, an unprivileged user created a file there.
* `mu300-voice` moved its state from `/tmp/mu300-voice` to `/run/mu300-voice`, which was the same exposure under
  another name: pid files it kills, the mixer undo log it writes back, files root writes there. `mu300-atd` did
  `mkdir -p /run/mu300-at` and looked no further: in a stranger's directory, or behind his symlink, the command
  fifo is his to write (AT commands, as root's daemon) and every answer his to read.
* `rootfs/overlay/opt/mu300/lib/run-dir.sh`, one helper for both so the two cannot drift: `run_dir_ours` (a real
  directory, not a symlink; the daemon's own uid; not writable by group or others) and `run_dir_take`, which makes
  the directory that - a plain `mkdir`, never `mkdir -p` (through a symlink that makes the directory where it
  points). The first version of the check refused a foreign directory and stayed down until somebody removed it,
  which turned the squat into a denial of service; the second removed it with `rm -rf`, which is a race - whoever
  squatted can still write `/run`, and busybox's recursive remove walks by path. Now nothing depends on what was
  seen and nothing is deleted recursively: a non-directory goes with `rm -f --`, an empty directory with `rmdir`
  (neither follows a symlink at that name, each fails harmlessly on the other kind), a directory with contents is
  moved whole into `/run/.<name>.foreign.<pid>` (made by `mkdir`: ours and 0700, or nothing is moved) and left
  there to be looked at, and what counts in the end is the check again. A caller who is not the owner (a member
  of the voice group running `mu300-voice events`) gets the check alone and never creates the directory.
* The headset's control fifo moved from `/run/mu300-hfp.ctl` into `/run/mu300-voice`, and
  `/etc/tmpfiles.d/mu300-run.conf` makes both directories at boot.
* `/run/mu300-at/urc` is 0700 now: with caller id on (`AT+CLIP=1`, which `mu300-voice` sets) every ring writes
  the caller's number into that log, which was world-readable. Every reader is root.

Measured on F50-B as root under dash, bash and busybox ash: a directory made first by another user (with a fifo
named `cmd` in it) and a symlink to `/etc` were both put out of the way, `/etc` untouched, the second call silent;
`mu300-voice status` then answered. Open: `/run` is still 1777 - `mount -t tmpfs -o mode=755` in `boot/init` is
the real fix, and it is a boot change that wants its own device test. `/run/mu300-at/answer.<pid>` and
`/run/mu300/` are as they were.
### 58. A service's own error in an HTTP 200 answer to the SMS webhook, and a button that clears the delivery log (#171)

The two points §54 left open. The webhook counted any 2xx as "Delivered"; chat services answer 200 and put their
refusal in the body. Measured on the U30 Air (openwrt-luci v2026.10.23, kernel 7.2.10) against a fake webhook on the
LAN that answers like the services; **not sent to any real service**.

* **One rule the user sets, not a table of services.** "The answer must contain": `KEY=VALUE` (`webhook_expect` in
  `/etc/mu300/sms-forward.conf`). With it, a 2xx is a delivery only when the answer is a JSON object whose
  **top-level** `KEY` is the scalar `VALUE`. Empty (the default, and what a page from before the field sends): any
  2xx, exactly as before - the helper is not even asked for the answer then. The page's presets (`errcode=0`,
  `code=0`, `code=200`, `ok=true`) only fill the field in. A table of services in the code would be wrong the day
  one of them changes; none of the answers below needs more than a top-level key.
* **What the services answer** (read from their documentation on 2026-10-13, not from a real request):

  | Service | Answer | Rule | Source |
  |---|---|---|---|
  | WeCom group robot | `errcode` 0 is success, "judge by errcode, not errmsg"; 93000 invalid webhook, 45009 rate limit, -1 busy | `errcode=0` | developer.work.weixin.qq.com/document/path/90313 (the send page, /path/91770, shows no reply) |
  | Feishu / Lark custom bot | `{"code":0,"msg":"success","data":{}}` (`StatusCode`/`StatusMessage` kept for old clients); 9499 bad request, 19021 signature, 19022 IP, 19024 keyword, 11232 rate limit. The page gives no HTTP status | `code=0` | open.feishu.cn/document/client-docs/bot-v3/add-custom-bot |
  | Bark | `{"code":200,"message":"success","timestamp":N}`; a failure is `code` 400 or 500 **and the same HTTP status**, so the status alone already catches it. A batch push answers 200 with a code per device inside `data`, which a top-level rule cannot see | none needed (`code=200` is harmless) | bark-server `router.go` (`CommonResp`), `route_push.go` |
  | Slack incoming webhook | 200 with the plain text `ok`; errors are HTTP 400/403/404 with a word (`invalid_payload`) | none: with a rule set every delivery fails | docs.slack.dev/messaging/sending-messages-using-incoming-webhooks |
  | Slack Web API | a top-level boolean `ok`, `error` with a short code; the page gives no HTTP status | `ok=true` | docs.slack.dev/apis/web-api |
  | Telegram Bot API | `ok` (boolean), `description`, `error_code`; the page gives no HTTP status. The Telegram target here is unchanged (status only) | `ok=true` for a webhook pointed at it | core.telegram.org/bots/api, "Making requests" |
  | DingTalk custom robot | **not read from its own documentation**: open.dingtalk.com renders its pages by script and gave navigation only. Alibaba Cloud's help page quotes the reply `310000: sign not match`; `{"errcode":0,"errmsg":"ok"}` is what every third-party write-up shows | `errcode=0` | help.aliyun.com/document_detail/421895.html |

* **Where the answer is read, and what leaves that place.** `sms-forward-http.uc` still prints the status and nothing
  of the reply. Only when the caller sets `MU300_FWD_ANSWER=4096` in its environment (never the request, which the
  user writes) does it add the first 4096 bytes of a **2xx** reply's body after the status line; the rest is read and
  dropped as before. Those bytes go down a pipe into one awk (`answer_verdict` in `mu300-sms-forward`), which keeps at
  most 4096 bytes in memory and prints one line: `answer ok`, `answer differs [TOKEN]` or `answer none`. Nothing
  else of an answer exists outside that pipe: no file, no shell variable, no log.
* **Why awk and not `jsonfilter` or ucode's `json()`.** A parser refuses an answer cut at 4096 bytes, and a delivery
  wrongly called failed is sent again. `answer_verdict` walks the text once, counting brackets and skipping strings,
  so a long answer whose key comes first still gives its verdict; a value the cut may have shortened is not looked
  at. It also runs in the tests under the shells and the awk the device has, which a ucode function would not
  (no ucode on the CI runner). The key and the value reach awk in its environment and are compared as text - a
  string by its content, anything else as written, so `0` is not `0.0` and `"0"` is `0` - never as a pattern, never
  through a shell. A key that is there twice must be right both times.
* **What a panel user can learn of an answer, and why it is kept this small.** Before this, nothing of a reply came
  back: only the HTTP status. Whoever may open this page (the write ACL: the panel's administrator) could already
  make the device send a POST to any address it reaches, its own loopback and the LAN included, and see the status;
  that is unchanged, and there is no private-address blocklist, here or before - a webhook to a LAN service is a
  normal use. What is new is that a test, or a delivery, now says something about a **JSON** reply of that address.
  It is held to what a status check needs:
  * The rule: `KEY` is a name (a letter or `_`, then letters, digits, `_`; 32 at most), `VALUE` a whole number of
    16 digits at most (a `-` before it allowed) or 1 to 16 lowercase letters. The adapter and the forwarder both
    check it. Only a **top-level scalar** is compared; an object or a list under the key counts as no value.
  * The log shows the value the service put there only when it is a whole number of 16 digits at most or a bare
    `true`, `false` or `null`: `the service answered errcode=310000`. Any other value - a text, a fraction, a longer
    number - is `the service answered another errcode`, without it.
  * One message, `no errcode in the answer`, for a missing key, an object or list under it, an empty answer,
    something that is no JSON object, and a key beyond the first 4096 bytes: no length, no type, no excerpt.
  * "Send test" from the panel is refused when another was started under 5 s ago (`mu300-sms-forward test-gate`,
    asked by the adapter; the command line's own `test` is root's and is not gated). The page's other actions have
    no such limit; this one is the only way to ask about an answer at will, and one test at a time was already the
    rule (the `test` lock).

  **What remains**, for the owner to judge: an administrator of the panel can point the webhook at an address only
  the device reaches and learn, per test (one in 5 s) or per forwarded SMS, about a reply that is a JSON object:
  whether it has a given top-level key with a scalar under it; whether that scalar equals a number or a lowercase
  word of the administrator's choosing; and, when the scalar is a whole number of up to 16 digits or
  `true`/`false`/`null`, that value itself. A numeric secret at the top level of a JSON reply (a PIN, a counter)
  could be read that way; a text secret could only be guessed at, a lowercase word of up to 16 letters per try.
  Nothing of a reply that is not a JSON object, and nothing below the top level, comes back at all. The same
  administrator can already read and change every setting of the device from the same panel.
* **Retried or not.** The HTTP status decides first, as before. With a 2xx: another value under the key is the
  service saying it did not take the message, so it is retried like a 5xx (30 s, doubling, ten times) - another try
  cannot deliver twice, and rate limits (WeCom 45009, Feishu 11232) pass by themselves. No such value at all fails
  **without** a retry: nothing says the message was not taken, the rule most likely does not fit the service, and
  ten retries would then be ten copies of every SMS. A rule in the file that is not such a `KEY=VALUE` (the panel
  never writes one) sends nothing: `the answer check is not KEY=VALUE`.
* **"Send test"** goes through the same `deliver`, so it shows the same verdict.
* **Clear.** `forward_log_clear` (write ACL, no argument) -> `forward logclear` -> `mu300-sms-forward log-clear`,
  which unlinks `/run/mu300-sms-forward/log` (and `log.part`) and never opens it: a link at that name goes, what it
  points to stays. The queue and the retry state are not touched.

Measured on the device, through `ubus call mu300dash forward_set` / `forward_test` / `forward_get` (forwarding
itself left off; the device has no `timeout` command, so the helper ran without one):

| The fake service answered | Rule | Log |
|---|---|---|
| `{"errcode":310000,...}` | none | Delivered, `HTTP 200` |
| `{"errcode":0,"errmsg":"ok"}` | `errcode=0` | Delivered, `HTTP 200, errcode=0` |
| `{"errcode":310000,...}` / `{"errcode":93000,...}` | `errcode=0` | Failed, `HTTP 200, the service answered errcode=310000` / `=93000` |
| Feishu's success body | `code=0`, `StatusCode=0` | Delivered |
| `{"code":19024,...}` | `code=0` | Failed, `the service answered code=19024` |
| Bark's success / HTTP 400 failure | `code=200` | Delivered / Failed, `HTTP 400` |
| `{"ok":false,"error":"invalid_auth"}` | `ok=true` | Failed, `the service answered ok=false` |
| `{"errcode":0,"errcode":7}` | `errcode=0` | Failed, `the service answered errcode=7` |
| `errcode` the text `hunter2`; `errcode` a text of `$(touch ...)`, backticks, quotes, a line break, an escape sequence | `errcode=0` | Failed, `the service answered another errcode`; no file was made |
| `ok` as text; an HTML page; 1 MB of every byte value; the key one level down only; an object under the key; 2 MB with the key last | `ok=true`, `errcode=0` | Failed, `HTTP 200, no ok in the answer` / `no errcode in the answer` |
| HTTP 204, no body | `errcode=0` | Failed, `HTTP 204, no errcode in the answer` |
| 500 objects deep, then the key at the top; 2 MB with the key first | `errcode=0` | Delivered |
| HTTP 500, 401 with `{"errcode":0}` | `errcode=0` | Failed, `HTTP 500`, `HTTP 401` |

The page refused `errcode`, `errcode=0;id`, `errcode=$(touch ...)`, `a=b=c` and `err code=0`. A second
`forward_test` right after one was refused ("A test was started a moment ago; wait a few seconds"), a third 5 s later
started. Through the queue (the installed forwarder on a pool, configuration and log of its own, first wait 2 s): a
service that answers `errcode=-1` once and then `errcode=0` gave "Will retry", then "Delivered" after 2 s;
`errcode=310000` every time gave two retries and "gave up after 3 attempts"; a missing key gave one "Failed" and one
request. After all of it neither the answers' marker text nor `hunter2` was in any regular file under `/run`,
`/tmp`, `/var` or `/etc/mu300`, nor in `logread`. `forward_log_clear` emptied a log of 29 lines; with a link at the
log's name, the link went and its target kept its content; the next test wrote a new 0600 file. In a headless
browser (Playwright) the page showed the field, a preset filled it in, Save kept it and Clear emptied the table
(looked at before the rule and the messages were narrowed; the page's script did not change after).

Not measured: any real service; the translations on a device (the test unit ran the changed files over an image
built without them, so the page's new strings were English); what uclient does with an answer whose `Content-Length`
is wrong or that never ends (the helper's 15 s timeout is unchanged). The unit tests (`tests/test_sms_forward.py`)
ran under dash and bash on macOS and under busybox ash with busybox 1.37 as awk in a Debian container.

### 66. The OpenWrt image build tries a package download again

`openwrt/build-rootfs.sh` installs the image's packages from the OpenWrt feed inside the build container, one
`apk update`, one `apk upgrade` and a handful of `apk add`. Each was run once under `sh -e`: a mirror that cut one
connection in the middle of one package failed the whole image, and in CI the release with it.

kanoqwq's fork wraps its `apk` calls in a function that tries three times (clean-tf-7.2 `33640d01`, "retry
interrupted OpenWrt package downloads"). Taken: that idea. Ours is a function named `apk` in the container's
script, so that every call goes through it without being rewritten and a call added later cannot be forgotten;
`update`, `upgrade` and `add` are tried three times, ten seconds apart, with a line on stderr for each new try;
`del` and anything else run once. A package the feed does not have fails three times and then fails the build as
before, half a minute later.

The same fork's `0886ee00` ("create block-mount metadata directory in fresh rootfs") repairs the build of its own
patched `block-mount`, which we do not have (section 65).

Unit tests only (`tests/test_static.py` `ApkRetry`: the function cut out of the script and run under each shell
with a stub `apk` that fails a number of times), and the same function once in busybox ash with a real `apk` (Alpine in a container: update, add, del, and a package that does not exist). Not run: an image build. To check, on the build machine and not on
a device:

    sh openwrt/build-rootfs.sh ...                  # as the release does: the image builds as before
    # and once with the network cut for a few seconds during "apk add": a "trying again (2 of 3)" line, then the image
### 64. An update dropped the panel's saved locks (`/etc/unisoc-modem`)

The control panel of openwrt-luci keeps its state in `/etc/unisoc-modem`: `lock-state.d` (the network mode, band
and cell locks it applied, which `boot-replay` applies again at boot), the SIM identity cache and the operations
log. `mu300-update` builds the new system from the release's image and copies over what `keep_list` names; for
OpenWrt that was `etc/config etc/mu300 etc/dropbear etc/rc.local root`, and `tools/android-install.sh` has its own
copy of the list for an update from the computer. `/etc/unisoc-modem` was in neither, so every update left it
behind in `<os>.old`.

What that does, from reading the code (not reproduced on a device): a mode or band lock lives in the modem's NV and
stays in force (measured on an F50, #96), so after an update the modem is still locked while the panel's lock page shows
nothing saved; a cell lock does not live in the NV and is kept only by the replay at boot, so it is gone.

Found in kanoqwq's fork, whose `keep_list` has `etc/unisoc-modem` since clean-tf-7.2 `33869287` ("add voltage and
forwarding controls; fix Wi-Fi log flood"; the line is one word of that commit). Taken: that word, in both of our
lists. Nothing else of the commit.

Unit tests only (`tests/test_update.py`: `apply_one` on a fake disk carries `etc/unisoc-modem/lock-state.d` over;
the two lists are the same). To check on a device with openwrt-luci:

    # before the update: a band lock and a cell lock saved from the panel (Cellular -> Network locks)
    ls -l /etc/unisoc-modem/lock-state.d; /usr/libexec/unisoc-modem/lock get
    mu300-update apply && reboot
    # after: the same files, the lock page shows the locks, and the log has the boot replay
    ls -l /etc/unisoc-modem/lock-state.d; /usr/libexec/unisoc-modem/lock get; logread -e unisoc-modem
    # the same once from the computer: install.sh --update (tools/android-install.sh's list)

### 63. A reused SMS reference number mixed long messages, or kept them from ever being joined

The parts of a long (concatenated) message carry a reference number, a total and a part number in their user data
header. Both `sms` (every system) and `mu300-sms` (the panel's pool on openwrt-luci, the SIM path and the +CMT path
of section 51 alike) took **sender and reference number** as the identity of a message. The reference is eight bits
wide in most headers; senders count it up, draw it at random, or send every long message under the same one. So the
same sender and reference come round again, and two things went wrong, both found by reading and reproduced in unit
tests, not on a device (no device was available for this work):

- **Two messages under one reference at the same time were mixed.** A later part overwrote the earlier one with the
  same part number, the totals were merged to the larger one, and all the slots were deleted together. With `sms`
  this needs nothing unusual, since the SIM keeps messages until somebody deletes them: of two two-part messages
  from one sender under one reference, `sms list` showed one, made of the newer parts. In the pool it needed a part
  still waiting for its siblings (up to an hour) when the next message came.
- **Every later message under the reference of one pooled incomplete was never joined.** A message whose parts did
  not all come within the hour is pooled with `[...]` and a header `partial: <md5 of its key>`, so that a part
  arriving after that is pooled at once. The key was sender, reference and total, with nothing that ends its
  validity: the next long message under that reference, a day or a year later, had each of its parts pooled (and
  forwarded) the moment it arrived, as "1/3", "1/3", "1/3".

kanoqwq's fork fixed the same class of fault in its own importer (clean-tf-7.2 `a5bd3e06`, "reassemble multipart
messages before inbox and forwarding"; its importer did not reassemble at all before that, which ours did). Taken
from it are three ideas, none of its code: a group is keyed by more than the reference (it uses the reference's
width, the total, coding, PID, language tables and SMSC as well); a reference used again is told apart by the
distance between the service centre timestamps, ten minutes; and a long message remembers the PDUs of its parts so
that a part delivered again is recognised. Changed against it:

- Grouping is one place for both tools, `sms-pdu.awk -v mode=group`: decode's records in, the same records out with
  the key of their message added (`multi:SENDER:REF:TOTAL@TIMESTAMP`). Parts are one message when sender, reference
  and total agree, their timestamps are within 600 s of the first part seen, and the part number is not already
  there with another text. Coding, PID and SMSC are not part of the key: the decoder's records do not carry them,
  and two messages that agree in everything above and differ only there were not thought worth a change to a format
  two programs parse. The reference's width (8 or 16 bit) is not in it either, for the same reason.
- Two messages of one sender, reference, total and second (a sender that numbers everything 0 and sends twice in a
  second) are told apart by a part number that is taken with another text; the parts go to the messages in the order
  they came. The fork refuses such a part and does not acknowledge it. Here a refused import is never acknowledged,
  the network delivers it again, and three failed rounds make `mu300-smsd` give direct delivery up (section 51), so
  one hostile or unlucky sender could switch +CMT off; a best guess that loses nothing was preferred.
- A concatenation header that says nothing usable (part 0, part 5 of 3, no parts, an element of the wrong length or
  cut off by the header's end) makes the fork's decoder refuse the PDU. Ours now shows the text as a message of its
  own, for the reason above; before, such a part waited an hour for siblings that cannot exist, or (part beyond the
  total) lost its text.
- The key of a waiting message keeps its name while its parts come in (the waiting state is handed to the grouping
  as `known`), so a part with an earlier timestamp arriving later does not start the hour over. The state file of
  the version before (keys without a time) is understood.
- "The rest of a message pooled incomplete" is now a part with that `partial:` header **and** a timestamp within
  the same ten minutes of the pooled message's (`sms-pdu.awk -v mode=near`).
- `part_ids: <md5 of each part's PDU>` on every long message in the pool, also on one pooled incomplete, and among
  the tombstones when it is deleted. A part delivered again (the acknowledgement of the last part did not reach the
  network: `mu300-smsd` keeps the spool file and imports it once more, section 51) used to be parked alone, wait
  its hour and be pooled and forwarded as an incomplete message of its own; it is now dropped as known.
- The listings `mu300-sms` keeps in `/tmp` while it works hold message text; they are now made with umask 077 (the
  first of them always was, by mktemp; the others took the caller's umask).

What the fork does and this does not: it holds waiting parts in a directory of their own with one file per part and
never shows an incomplete message. Ours pools what arrived after an hour, marked incomplete, which is section 39's
decision (a lost part must not hold the others back for ever) and stays.

Unit tests only (`tests/test_sms_pool.py`: `Codec`, `Listing`, and in `Pool` the tests under "a reference number
used again"), under dash, bash and busybox ash, the grouping also under busybox awk in a container. Not measured:
any of it on a device with a real long message. To check on a device with openwrt-luci, with a second phone:

    logread -f | grep -i sms &                       # must never show a number or text
    # 1. a long message (three parts or more) from the phone: one message in the pool, whole
    mu300-sms list; mu300-sms show ID
    grep -c . /etc/mu300/sms-pool/partial 2>/dev/null; ls /etc/mu300/sms-pool/parts    # nothing left waiting
    sed -n '1,/^$/p' /etc/mu300/sms-pool/msg/ID      # a part_ids line with one hash per part
    # 2. the same long message twice within a minute, then again after 15 minutes: three messages, each whole
    # 3. with the panel's forwarding on: each of them forwarded once, whole
    # 4. Ubuntu, or any system: sms list  with those still on the SIM (AT+CNMI=2,1 path): each shown whole

### 65. An APN with a user name and a password (`AT+CGPCO`), and what else kanoqwq's APN page does

Until now the dial knew an APN and a PDP type and nothing else: `network.wan.apn` / `pdptype` on OpenWrt (LuCI,
Network -> Interfaces -> wan), `MU300_APN` / `MU300_PDP_TYPE` in `/etc/mu300/mobile-data.conf` on Ubuntu, both kept
across updates. An APN that asks for credentials (a private APN, some MVNOs) could not be used at all.

kanoqwq's fork added an APN page to its dashboard (clean-tf-7.2 `3826be8b`, "add persistent APN management and safe
mount discovery"): up to 32 saved profiles, a profile bound to a SIM by its ICCID, an automatic choice for a few
Chinese carriers by IMSI, credentials, an optional initial-attach setting (`AT+SPCGAPNCFG`). With it comes a note on
what ZTE's B09 RIL does (`docs/F50-ANDROID-APN-RIL-RESEARCH.zh-CN.md` there, from reading `librilcore.so`): the
ordinary data call sends the credentials **after `AT+CGDCONT` and before `AT+CGDATA`** as

    AT+CGPCO=0,"<user>","<password>",<cid>,<auth>          auth: 0 none, 1 PAP, 2 CHAP, 3 PAP or CHAP

and not with the `AT+CGAUTH` other modems use. That agrees with what this tree already sent for the F50's internal
SIM, taken from the stock RIL's trace: `AT+CGPCO=0,"","",1,0` between its `AT+CGDCONT` and `AT+CGEQREQ`.

Taken: that command and its place in the dial. Not his code: his dialer part is bash regular expressions in
`mobile-data` and a ucode profile store behind his dashboard's RPC. Ours:

- `mobile-data`'s context definition is a function of its own, `define_context`. With `MU300_APN_USER`,
  `MU300_APN_PASSWORD` and `MU300_APN_AUTH` (`none`, `pap`, `chap`, `both`; left out with a user name or a
  password: `both`, as Android does) it sends the command above after `AT+CGDCONT` and requires `OK`.
- OpenWrt: `username`, `password`, `auth` on the wan interface, on the interface's page next to the APN, for the
  external SIM (the internal one dials its own APN, and is never offered another carrier's credentials). Ubuntu:
  three lines in `mobile-data.conf`.
- Without credentials the dial sends exactly what it sent before (the external SIM: `AT+CGDCONT` alone; the internal
  one: its four commands, byte for byte, an `ERROR` to its empty form ignored as it always was).

**Where the password is, and where it is not.** Checked by the tests for every path (both systems, both cards):

| | |
|---|---|
| command lines | never. `mu300-at -` (new) takes the command on its stdin, and `mobile-data` uses that for this one command; `mu300cell.sh` hands the settings to `mobile-data` in its environment. As an argument it would be in `ps` for every user of the system. |
| environment of other processes | `mobile-data` takes the credentials out of its environment before it starts anything, so `mu300-at`, `mu300-sim`, the LED, the VPN guard inherit none. `/proc/<pid>/environ` of the services is root's. |
| logs, stderr, traces | never printed. Every refusal says what, not with what. `set -x` is off while the credentials are read and while `define_context` runs. `/tmp/mu300cell.err` and the system log get `mobile-data`'s stderr, which never holds them. |
| the AT daemon | `mu300-atd` writes its answer files mode 600 now (a modem that echoes commands would put the command there, and the file of a client that gave up stays behind), and throws a late echo (a line that starts with `AT`) away instead of appending it to the URC log. Whether this modem echoes at all is not measured. |
| settings files | `/etc/config/network` (OpenWrt) and `/etc/mu300/mobile-data.conf` (Ubuntu), written by the user, uci or LuCI, never by these scripts. One function for both, `settings_private`: before credentials are used the file is made mode 600, and unless it then is the owner's alone there is **no dial**. A link is not followed to change anything; what it leads to must be private already. OpenWrt's first boot makes `/etc/config/network` 600 (uci keeps the mode), so it is private before anybody types a password; the example file says `install -m 600`. A release tarball that holds `mobile-data.conf` is refused by `make-release.sh`. |
| who can read it on OpenWrt | root; and a LuCI login that was granted the network settings (rpcd's `uci` ACL on `network`), the same as a PPPoE password or a WireGuard key. The panel's own ACL (`luci-app-mu300`) grants `uci` on `unisoc_modem` only. `ubus call network.interface.wan status` and `ifstatus wan` show no protocol options, by reading netifd and the handler, which adds no data to them (the commands below check it on a device). A password typed into the panel's AT terminal by hand is in that terminal's history, like anything typed there. |
| the modem | holds them once given (`AT+CGPCO?` would show them to root). `/etc/mu300/apn-auth-set.sim0` (`.sim1` for the internal card), an empty file, says so: one per card, since each has its own context. |

**Nothing falls back to a dial without them, and nothing stays behind.** Credentials that cannot be used (a quote,
a control character, 65 characters, an unknown authentication), credentials without an APN, a settings file others
can read, a modem that does not answer `OK`: each ends the bring-up with a line saying which, and netifd or the
watchdog tries again. The mark is written (a new file renamed into place, so a link there is replaced and never
written through) *before* the credentials go out, and if it cannot be written they do not go out. It is removed
only when the modem has answered `OK` to the empty form. So credentials taken out of the settings, or an APN changed
to one without any, are taken back from the modem before the next dial; and a modem that does not let go of them
gets no dial, rather than one that presents the old user name and password to the new APN's network.

One fault of the old code came out on the way: `mu300-power`'s `mobile-data resume` and a `mobile-data up` run by
hand have no environment from systemd, so on Ubuntu they dialled without `MU300_APN` (the modem usually still had
the context, which hid it). With credentials that would have been a dial without them. `mobile-data` now reads what
its environment does not say from `mobile-data.conf` itself, on every run (parsed as `KEY=VALUE`, never executed).

Not taken, and why:

- Profiles, the binding to an ICCID and the carrier list: our APN is one setting per interface (and per card:
  `apn_internal`), kept across updates; nobody has asked for more. A per-SIM APN becomes worth it with dual SIM,
  which is being reworked (#166). It follows that the credentials belong to the settings, not to a card: a
  different card put into the device is offered them too, as it is offered the APN.
- `AT+SPCGAPNCFG` (the initial attach APN): off by default in his tree too; nothing here needs it.
- "An empty APN clears the modem's": his dial sends `AT+CGDCONT=1,"IP",""` whenever netifd passes no APN, so that
  removing an APN in the settings also removes it from the modem. Ours sends nothing for an empty APN, on purpose
  ("the modem keeps the context the SIM already defines"); whether a context once defined by `AT+CGDCONT` outlives
  the setting (it is in the modem's NV on other Unisoc firmware) has not been measured here. If it does, an APN
  taken out of the settings stays in force until something else defines the context. To measure before changing
  anything: `mu300-at 'AT+CGDCONT?'` before setting an APN, with it, after removing it and redialling, and after a
  reboot.
- The patched `block-mount` of the same commit (and `0886ee00`, which fixes its build): fstools' `block info`
  opens everything that matches `/dev/sd*`, which on this SoC includes the SIPC channel nodes (`sdiag_*` and the
  like), and an open and close of one of those desynchronises the channel (13b). His patch skips character devices
  that are not UBI before the probe. Our images do not ship `block-mount`, so nothing here runs `block`; a user who
  installs it (LuCI's Mount Points) would. Not taken now: it needs a package built with the OpenWrt SDK in the
  image build and a device to see both the fault and the fix, neither of which this work had. Worth doing before
  anybody documents mount points on a card. His guard header is LGPL-2.1-or-later (fstools' own licence).

Unit tests only: `tests/test_mu300cell.py` (`MobileDataContext`: the commands and their order for both cards; in
every run the password on `mu300-at`'s stdin and in no argument, no child's environment, no output and no trace;
the refusals; the settings file gate for both systems; the mark; the file read by a run without an environment;
and the protocol handler), `tests/test_device_scripts.py` (`mu300-at -`; `mu300-atd` on a pty with a modem that
echoes), `tests/test_sim_selection.py`. **No part of this has been sent to a modem**: neither that the F50/U30 Air
firmware answers `OK` to the command with credentials on the external SIM's context, nor that it answers `OK` to
the empty form there (if it does not, removing credentials ends in "did not take back the earlier APN credentials"
and no dial, until `rm /etc/mu300/apn-auth-set.sim0`), nor that a network then accepts them. To check, with a SIM whose
APN checks credentials (or any SIM: most public APNs accept any user name and password, which shows the command is
taken, not that it is used):

    # OpenWrt
    uci set network.wan.apn='<apn>'; uci set network.wan.username='<user>'; uci set network.wan.password='<password>'
    uci set network.wan.auth='chap'; uci commit network; ifup wan
    logread -e mu300cell; cat /tmp/mu300cell.err      # no "refused the APN credentials", and never the password
    ifstatus wan | grep -m1 '"address"'; ping -c 3 1.1.1.1
    ifstatus wan | grep -c '<password>'; ubus call network.interface dump | grep -c '<password>'    # 0 and 0
    grep -rl '<password>' /run /tmp /var/log 2>/dev/null     # nothing (logread | grep -c '<password>': 0)
    mu300-at 'AT+CGDCONT?'; mu300-at 'AT+CGPCO?'      # what the modem holds (CGPCO? may not be answered)
    mu300-at 'ATE?'; cat /run/mu300-at*/urc/*.log     # does the modem echo; nothing of the command in the log
    ls -l /etc/mu300/apn-auth-set.sim0 /etc/config/network # the mark; network is -rw-------
    # while it dials, from a second shell: no AT+CGPCO in any command line or environment
    while :; do grep -a -l CGPCO /proc/[0-9]*/cmdline 2>/dev/null; done
    # take them out again: the next dial sends AT+CGPCO=0,"","",1,0 once, the mark is gone, data still comes up
    uci delete network.wan.username; uci delete network.wan.password; uci delete network.wan.auth
    uci commit network; ifup wan; ls /etc/mu300/apn-auth-set.sim0; logread -e mu300cell | tail -3
    # refusals: chmod 644 /etc/config/network is put right by the dial (600 again); a user name without an APN
    #   gives "set without an APN" in the log and no address
    # a wrong password on an APN that checks it: the dial fails at the network (no address), nothing in the log
    # Ubuntu: the same three as MU300_APN_USER, MU300_APN_PASSWORD, MU300_APN_AUTH in /etc/mu300/mobile-data.conf,
    #   systemctl restart mu300-mobile-data; journalctl -u mu300-mobile-data -n 30; stat -c %a /etc/mu300/mobile-data.conf
    #   then: mu300-power's suspend and resume (or  mobile-data down; mobile-data up  by hand): the APN and the
    #   credentials are used again (AT+CGDCONT? shows the APN)
    # the F50's internal SIM (sim_slot 1) once without credentials: it dials as before
### 70. adb to Linux on by default and open to every computer: the owner's decision, the exposure, and the state that decides it

**The decision.** On 2026-10-13 the owner of the project decided that adb to the Linux systems over USB is on by
default and accepts every computer without key authorisation. The reason: a browser-based installer and manager
(WebUSB) and a GUI are being built, and they must be able to talk to a device running Linux without the user first
getting a key onto it; a browser makes its own adb key, which nobody could have authorised beforehand. Importing a
key and confirming with a button on the device were offered as alternatives; the owner chose "accept everyone". It
follows the project's standing rule: bootability and usability over lockdown, and the exposure written down
instead.

**The exposure.** With the default, anyone who can plug a USB cable into the device gets a root shell without a
password - also after passwords were set for `ubuntu` and `root` - and with it everything on the device: the
hotspot key, the VPN profiles, the SMS pool, the SSH host keys, the modem. It is the cable only: adbd has no TCP or
vsock listener in either mode (below), so nothing changes for the LAN, the hotspot's clients or the mobile network.
Before this change physical access already gave the same to someone with time (the serial console asks for a
password, but the boot image and the filesystem are not encrypted or verified); what changes is that it now takes a
cable and a second. The two commands that close it are in the README, the wiki (Installation, FAQ, Home, Glossary),
the release notes' body, the installers' question and summary, and in the output of `mu300-usb adb on|auth|status`:
`sudo mu300-usb adb auth keys` (only authorised keys) and `sudo mu300-usb adb off`.

**How adbd decides.** `mu300-adbd.patch` set `auth_required = true` on Linux unconditionally (§43). AOSP's own switch
is the property `ro.adb.secure` (0: `handle_new_connection` answers a `CNXN` with "authentication not required" and
the transport is online at once; 1: it sends an `AUTH` token and waits for a signature of an authorised key). There
are no Android properties on our systems, so the patch reads one environment variable instead:
`MU300_ADB_AUTH=open` is `ro.adb.secure=0`, and a missing variable or any other value is `ro.adb.secure=1`.
`mu300-adbd run` sets it when it starts adbd, from the state below. Nothing else in the patch assigns
`auth_required`, and the listeners are untouched: adbd still returns before `setup_adb` on Linux, the `tcpip:`
service (Android's `service.adb.tcp.port`) is inside `#if defined(__ANDROID__)` and `restart_service.cpp` is not in
`CMakeLists.txt`. Checked on the binary built from this patch (2,493,480 bytes): `strings` finds `MU300_ADB_AUTH`
and "authentication not required", and none of `service.adb.tcp.port`, `ADBD_PORT`, `adbd listening on`.

**The state, and which reading wins.** Two files in `/etc/mu300`, written by `mu300-usb`: `adb` (`on`/`off`) and
`adb_auth` (`open`/`keys`). `/etc/mu300` is part of the root filesystem, so there is no mount to wait for at boot,
and `mu300-update apply` copies the directory whole into the new system (`keep_list`, `cp -a`: owner and modes
stay), so a choice is not lost by an update; `tests/test_update.py` has `off`, `keys` and a key in the system that
is replaced. The rules (`mu300-adbd`: `adb_on`, `auth_read`):

| What is there | adb | Who is let in |
|---|---|---|
| nothing (a new installation; an update of a device that never touched adb) | on | every computer: the decision |
| `adb` = `off` | off | - |
| `adb` = `on`, no `adb_auth` (turned on under v2026.10.20-23, when on meant keys only) | on | keys |
| no `adb_auth`, a key in `adb_keys` or `/root/.android/adb_keys` (authorised then) | as `adb` says | keys |
| `adb_auth` = `open`, a regular file of root's that nobody else can write | as `adb` says | every computer |
| `adb_auth` = `keys` | as `adb` says | keys |
| `adb_auth` empty, cut short, unreadable, a symlink, writable by group or others, or any other word | as `adb` says | keys, and the log and `adb status` say why |
| `adb` there and neither `on` nor `off` (empty, cut short) | **off**, and the log says why | - |
| `/etc/mu300` missing, not root's, or writable by group or others | on | keys, and the log says why |
| keys, and no key in either file | on | **nobody** (adbd has nothing a signature could match and no socket through which a key could be approved; measured in §43: `unauthorized` with the key file taken away) |

So "open" has exactly two sources: no state at all, or the word `open` in a whole file that only root can write.
A state that somebody set and that was damaged afterwards is never read as the default.

* **Existing installations.** The old state file can tell "never set" (no file) from "set to off" (`off`), so a
  device where `mu300-usb adb off` was run stays off. A device that never touched adb turns on, and open, with the
  update: that is what the decision asks for, and the release notes must say it. A device where adb was turned on,
  or a key authorised, under v2026.10.20-23 chose keys-only adb, and keeps it: `mu300-usb` writes `adb_auth` with
  every `adb on`, `off`, `key` and `auth` since, so "no `adb_auth`, but `on` or a key" can only be such a device.
  It becomes open with `sudo mu300-usb adb auth open`.
* **Written whole.** `mu300-usb` writes both files as a new file renamed over the old one (`adb_write`): a power cut
  leaves the old word or the new one. A new file that the filesystem did not get to fill would be empty, which
  reads as keys (or off). The rename also replaces a symlink instead of writing through it; the new file is
  created with noclobber, mode 644 (anyone may read whom adb lets in), and the key file stays 600.
* **Authorising a key does not close an open device**: `adb key` writes the mode in force into `adb_auth` first.
* **The installers.** The question is now "let in only this computer's adb key instead?" (default no). Yes writes
  `keys` into `adb_auth`, then `on`, then the key: keys-only from the first boot. The Magisk zip has no question;
  its systems start open. A build of one's own (`install.sh --build`) builds adbd always.

**Where adb cannot be on.** A mainline kernel from before v2026.10.20 (no `CONFIG_USB_CONFIGFS_F_FS`; a system
updated without its kernel: `mu300-update kernel` brings one); an image without `/opt/mu300/bin/adbd` (built without
`tools/adbd/adbd`, or older than v2026.10.20); the U30 Air while its port is a USB host (`mu300-usb host`: there is
no gadget, `mu300-adbd` leaves it alone and binds again in the device role); and the seconds before the system's
`mu300-adbd` service starts (boot/init makes the gadget without adb, so the fallback to Android and init's own
recovery shell are as they were). In each case the network and the console are untouched and `mu300-usb adb
status` says which it is. The vendor 5.4 kernel has FunctionFS (`CONFIG_USB_CONFIGFS_F_FS=y` in the stock config),
so adb is expected to work there; it has not been tried (§43).

**What the default-on changes for a computer, from what §43 measured and what it did not.** Every boot now rebinds
the gadget once, early (before the LAN's DHCP server): the computer sees a replug. The network function and the
console keep their interface numbers and the VID:PID stays; `bcdDevice` goes from 0x0301 to 0x0303 (0x0302 to
0x0304 with RNDIS), which is what makes Windows ask for the MS OS descriptors again, and the MS OS descriptors are
then on with NCM too. On macOS (measured in §43, F50-B, 7.2): NCM and the console came back after the rebind, adb
worked next to them, and with RNDIS a Mac has no network but has adb. A Mac keeps the interface it knows (the MAC
address does not change), which matters while its screen is locked. A host without adb sees one more vendor
interface and ignores it. **Not measured: any Windows host** - whether Windows re-installs the drivers of the
network and serial interfaces once for the new `bcdDevice`, whether the adb interface gets WinUSB by itself, and
whether NCM is disturbed by the descriptors being on. Until that is measured, default-on is a change every Windows
user meets at the first boot after the update, and `sudo mu300-usb adb off` is the way back to the gadget as
boot/init makes it.

**The installers meet a device in Linux in `adb devices` now.** Its shell is root, so `su -c 'id -u'` says 0 there
too: nothing but the installer's own check keeps it from being taken for a rooted Android (read from the code, not seen happen: it would wait two
minutes for `sys.boot_completed`, ask "this does not look like an F50, continue?" and go on after a yes). Now
(`tools/linux-mode.sh`, shared by `install.sh`, `uninstall.sh` and `tools/reset-password.sh`; the same in
`install.ps1` and `uninstall.ps1`): a serial that starts with `MU300LINUX` (boot/init) is a device in Linux; it is
never on the list of devices to choose from, never the answer to "is an Android up", and `ANDROID_SERIAL` naming it
is dropped. The installer says "The device is running MU300 Linux, not Android" and offers to reboot it into
Android: over adb where the device lets the computer in (`/opt/mu300/bin/mu300-next-boot android && sync &&
reboot`, after checking that `mu300-next-boot` is there; no password, and it works where SSH does not, e.g. RNDIS
on a Mac), else over SSH as before; with neither (keys-only adb, no USB network) it stops with the two commands to
run on the device. After a device was selected, `ls -d /opt/mu300/bin` on it must print nothing, whatever its serial
says. `tools/backup-device.sh` refuses a `MU300LINUX` serial. `backup-full.sh`, `collect-logs.sh` and
`boot/android-boot-linux.sh` take the device adb gives them and were not changed: the first two only read, the
third compares `boot_b` first and stops.

**For tools:** `adb shell /opt/mu300/bin/mu300-device --json`, one line with the device, the system, its release,
the kernel, whether the caller is root and what adb does; the contract is `docs/ADB-INTERFACE.md`.

**Tested** (`tests/test_adb.py`, `test_installer.py`, `test_device_scripts.py`, `test_android_install.py`,
`test_update.py`, `installer.Tests.ps1`; dash and bash here, busybox ash in CI): the patch's one switch and that
nothing else assigns `auth_required` or reads the environment; every row of the table above; the state written
whole and not through a symlink; the fake gadget joined with `MU300_ADB_AUTH` as the state says; the installers'
device selection with a device in Linux alone, next to an F50 in Android, next to a tablet, in keys mode, with and
without SSH, with a reboot that does not happen, and a Linux behind an Android-looking serial; the JSON line
parsed, with values that try to break out of their quotes. The patched adbd was built (`tools/adbd/build.sh`,
Alpine 3.20, arm64) and its strings checked; it was not run, because it needs FunctionFS.

**Not measured on a device** (all test boards were in use; this is the checklist, to be run before a release
carries the change). `S` is the device's serial in `adb devices`, the computer a Mac unless it says Windows:

1. *Fresh boot, each of Ubuntu 24.04 and OpenWrt (`openwrt-luci`) on 5.4, 6.18 and 7.2, with no `/etc/mu300/adb*`
   files:* `adb devices` shows `MU300LINUX-... device` within a minute of power-on. On the device
   `mu300-usb adb status` prints `adb: on`, `auth: open (...)`, `gadget: adb is in it (25100000.dwc3)`;
   `cat /sys/kernel/config/usb_gadget/linux/bcdDevice` is `0x0303`; `journalctl -u mu300-adbd` (OpenWrt: `logread
   -e mu300-adbd`) has `auth open: every computer on the USB cable gets a root shell` and `gadget bound on ... with
   adb`. On 5.4 this is the first run of adbd on that kernel at all: if `adb devices` stays empty, the status line
   `adbd: cannot run: ...` or the log says why, and the network must be up regardless.
2. *A root shell from a Mac whose key was never on the device* (`mv ~/.android ~/.android.bak; adb kill-server`
   first): `adb -s S shell id -u` prints `0`; `adb -s S shell /opt/mu300/bin/mu300-device --json` prints one line
   such as `{"mu300":1,"device":"f50","system":"ubuntu","version_id":"24.04","release":"v...","kernel":"7.2.10","root":true,"adb":"open"}`;
   `adb -s S push` and `pull` of a 20 MB file, checksums equal.
3. *No network listener:* on the device `ss -ltnp | grep -c adbd` (OpenWrt: `netstat -ltnp | grep -c adbd`) prints
   `0`; from the computer `adb connect 192.168.77.1:5555` says `Connection refused`; `adb -s S tcpip 5555` does not
   make it listen (the same `0` afterwards).
4. *Keys:* `sudo mu300-usb adb auth keys` (prints `no key is authorised yet` on a device without keys); after the
   replug `adb devices` shows `S unauthorized` and `adb -s S shell id` says `device unauthorized`, for as long as
   one waits. `adb auth keys` with `/etc/mu300/adb_keys` deleted: the same. Then `scp ~/.android/adbkey.pub` to the
   device, `sudo mu300-usb adb key adbkey.pub`: `adb -s S shell id -u` prints `0` without a replug (after
   `adb kill-server` at most). A second computer, or the first with a new key (`rm ~/.android/adbkey*; adb
   kill-server`): `unauthorized`. `sudo mu300-usb adb auth open`: both get in.
5. *Damaged state:* `: > /etc/mu300/adb_auth; reboot` - `mu300-usb adb status` says `auth: keys (...; ... is
   empty, unreadable or says neither open nor keys)` and the computer sees `unauthorized`. `chmod 666
   /etc/mu300/adb_auth` with `open` in it: keys as well. `: > /etc/mu300/adb; reboot`: no adb device, `adb: off
   (... says neither on nor off)`.
6. *Off:* `sudo mu300-usb adb off` - the device leaves `adb devices`, `bcdDevice` is `0x0301` again, SSH and the
   console come back. Still off after `reboot`, and after `mu300-update apply` and the reboot into the new system
   (`cat /etc/mu300/adb` prints `off`). The same for `adb auth keys` with a key: after an update, still `keys`,
   the key still gets in, another computer does not.
7. *An existing installation:* a device on v2026.10.23 that never touched adb, `mu300-update apply`, reboot: as 1.
   A device where `mu300-usb adb on` was run with a key under v2026.10.23, updated: `auth: keys (...; adb was turned
   on when it took keys only ...)`, the key gets in, another computer sees `unauthorized`.
8. *The USB network next to it, macOS:* with adb in the gadget, `ifconfig` shows the device's interface with an
   address in 192.168.77.0/24 (U30 Air: .78), `ping 192.168.77.1` and `ssh` work, `ls /dev/cu.usbmodem*` has the
   console; the same when the Mac's screen was locked during the device's boot; the same after ten `adb shell true`
   in a row (each ends a connection: FunctionFS unbinds the gadget and the loop binds it again after 5 s - the
   network is away for 6-8 s each time, §43; count them).
9. *The USB network next to it, Windows 10 and 11, NCM (the default) and RNDIS (`MU300_USBNET`):* after the first
   boot with adb, Device Manager shows the network adapter and the COM port working, and "ADB Interface" under
   WinUSB devices without a driver having been installed by hand; `ping 192.168.77.1`; `adb devices` lists the
   device. Note whether Windows shows "setting up a device" for the network or the COM port again (the new
   `bcdDevice`), and whether it does so at every boot or once.
10. *The U30 Air's host role:* `sudo mu300-usb host` with adb on, a flash drive on an OTG adapter mounts; `sudo
    mu300-usb device`: network, console and adb are back within ten seconds.
11. *The boot fallback:* a trial boot image that does not reach `mu300-boot-ok` falls back to Android as before
    (adb plays no part before the system's service starts).
12. *The installers:* with the device in Linux and adb open, `./install.sh --check` says "The device is running
    MU300 Linux, not Android", asks, prints `asking it over adb (MU300LINUX-...)`, and goes on once Android is up;
    the same with `install.ps1 -Check` on Windows. With `adb auth keys` and no key of that computer: over SSH as
    before.

### 81. An update that brought another mu300-update ended with "another mu300-update is running"

Found on the first device update to the v2026.10.24 pre-release (F50, Ubuntu 24.04, v2026.10.23 installed):

    $ sudo mu300-update apply
    another mu300-update is running (pid 33187)

and nothing was updated. No other run existed, and 33187 was the run itself. `apply` takes the release's own
`mu300-update` when it differs from the installed one, replaces the installed file and execs the new one: the same
process, which then takes the lock again (`exec 9>>lock; flock -n 9`). The descriptor it replaces was the lock's
holder, so that should succeed - but the dispatch starts the keep-alive after `lock_take`, a background loop of
`ping` and `sleep 3` that inherits descriptor 9, and `keepalive_stop` ends the loop's shell, not the ping or sleep it
is waiting for. For up to three seconds one of them still holds the lock, and the continued run's `flock -n` fails
with its own process id in the message. It is a race: an update whose release has the same updater never execs
(v2026.10.22 to v2026.10.23 on the same device went through), and one that does can win it. A second `mu300-update
apply` always works, because the installed updater is the release's by then.

The updater that leaves the stragglers behind is the installed one, which no release can change; the one that
meets them is the release's. So the fix is in what meets them: when `flock` fails in a run that was continued
(`MU300_SELF_UPDATED`) and the lock file names this process, the lock is this run's; it waits up to ten seconds for
the descriptor to come free and goes on either way. Any other holder is refused as before. And the keep-alive now
runs without the lock's descriptor (`9>&-`), so no later updater leaves this behind. Measured: the tests reproduce
the failure with the old lock code under dash, bash and busybox sh on Linux (macOS has no `flock`; the pid-directory
lock always knew a continued run by its pid). Devices that took the v2026.10.24 pre-release's updater are not
affected by it again: their next update meets the fixed one.

### 82. adb on by default, and no OpenWrt had it after a boot

The v2026.10.24 pre-release on an F50, openwrt-luci, kernel 7.2.10: `mu300-usb adb status` said `adb: on`, `auth:
open`, and `gadget: without adb`; no adbd ran, and the computer saw no adb device. `/etc/init.d/mu300-adbd start` by
hand brought it up at once. On Ubuntu, same device and kernel, adb was there after every boot (section 70).

The service's own trace at boot (its command wrapped in `sh -x` into a file, because the log ring had already
turned over): it ran 13 s after power-on (S19), FunctionFS was not in `/proc/filesystems`, not built in, and
`mkdir functions/ffs.adb` failed - which the script takes for "this kernel has no FunctionFS", logs, and exits 0.
procd does not start a service again that ended by itself. Some seconds later the same `mkdir` works (the module
is loaded on demand then; what is not ready at second 13 was not looked into). Under systemd the unit starts later
and never met this. Until adb was on by default nobody saw it: `mu300-usb adb on` starts the service long after
the boot, and the 5.4 kernel has FunctionFS built in.

`mu300-adbd run` now asks again once a second for a minute (`MU300_ADB_WAIT`) before it believes the no and logs
it. Measured after the change: adb in `adb devices` 38 s after power-on, `mu300-device --json` answering over it,
mobile data up. Not measured: OpenWrt on 6.18 and on 5.4, the U30 Air.

### 86. Updating from the panel: System > Update, an update from a file, and release signatures

A third party's panel plugin for a fork has a "System > F50 system upgrade" page: upload a signed update file, see
the target version and the space it needs, "keep configuration" ticked, a progress bar, a reboot, and afterwards
"roll back to the previous version". This is the same thing in the project's own panel (`openwrt-luci`, System >
Update), over the project's own updater. It was designed while both test devices were in use; what follows is the
design, what the tests on a computer show, the protocol for the device, and what the protocol showed on a U30 Air
(2026-10-15, at the end of the section).

**One updater.** The page is not a second update engine. Every action is one `mu300-update` command, and the
command's own lock decides whether it may run. What was added to `mu300-update` is one marked block ("for a panel")
and the few lines that call it; `apply`, `apply_one`, the keep lists, the accounts, the packages and the boot image
are untouched, so the work on what an update keeps (the `lossless-update` branch) merges beside it:

| command | what it gives |
|---|---|
| `mu300-update status [--sizes]` | one JSON object, no network: the systems and their releases, the copy kept for a rollback (its release; its size only with `--sizes`, adding up a system takes seconds), the kernel (running, the choice, which choices are refused and why), the boot image and the kept one, the default boot and the number of failed boots before Android, free space and the room `apply` wants, who holds the lock, the note of a newer release, whether this system has a release key |
| `mu300-update releases` | one JSON object: the newest release and - only when one is newer than it - the newest pre-release, each with what this device would download (the root filesystem of every system that is not that release yet, the kernel of its choice, the installed extras, the updater), the sizes, and whether the release is signed |
| `mu300-update inspect FILE\|DIR` | one JSON object about an offline source: its SHA-256, the release, system and kernel it says it is, whether its files match their checksums, whether it is for this device, how its signature checks. Changes nothing |
| `mu300-update apply --from FILE\|DIR [--unsigned] [--downgrade]` | the same update from a file instead of GitHub |

Every string of that JSON goes through `jv`, which lets letters, digits and `._+:,()@ /-` through and nothing
else: a version file with a quote, a backslash or `$(...)` in it cannot break the object, so nothing needs escaping
and no JSON tool is needed (Ubuntu has none). GitHub's list of releases is read the same way, line by line, after
every `,"` and `{"` is given a line of its own - which the escaped quotes inside a release's notes never are, so
notes that contain `"tag_name": "v2099.01.01"` change nothing (tested with GitHub's pretty and compact forms).

The functions of the block, by name, because a merge will ask: `jv`, `jstr`, `jnum`, `mtime`, `tag_ok`, `tag_key`, `newer` (§125),
`space_needed`, `source_conf`, `key_state`, `sig_raw`, `sig_state`, `stage_private`, `tag_sha`, `sums_trusted`,
`sums_verdict`, `apply_targets`, `downgrade_ok`, `boot_downgrade_ok`, `zip_p`, `man_val`,
`from_open`, `from_read`, `payload_is`, `from_close`, `from_member`, `from_fits`, `from_installed`, `apply_options`,
`from_begin`,
`from_verified`, `from_handover`, `inspect_json`, `lock_holder`, `size_kb`, `status_json`, `release_json`,
`releases_json`, `progress` (a test holds the list to the code). The lines outside it: `fetch_verified` (five: the
file being fetched, the offline source, `stage_private`, the signature twice), `latest_release` and the download
address (a mirror, below), `apply` (five: `from_begin`, `downgrade_ok`, `payload_is`, a zip's one system,
`from_handover` before it continues with the release's own updater), `kernel_cmd` and the `boot` command (`boot_downgrade_ok`), `check`'s
last line (it names `--downgrade`), the dispatch (`apply_options`, the three commands, `source_conf`) and the help
text. `space_needed` is
`apply`'s own rule (1 GB, and 1 GB for every system to update) written a second time so that the page can show it:
when the free-space check changes, the two must change together.

**The task.** An update takes minutes, rpcd ends a call after 30 s and the page may be closed, so the adapter
(`/usr/libexec/unisoc-modem/update`, behind mu300dash's `update_get`, `update_job`, `update_act`) starts the command
with `setsid` as a task of its own, as the SMS send and the VPN pages do (§46: "sms_send - killed"). Its files are in
the runtime directory (`/var/run/unisoc-modem/update-job`: kind, arguments, pid, log, exit status), which only root
can enter. It therefore outlives the request, the page, the session and a restart of rpcd, and any browser that
opens the page sees it. It does not outlive a reboot (the directory is in RAM); after one the page shows what is
installed, and "restart needed" while the running system is the kept copy. One task at a time; and before anything
that takes the updater's lock the adapter asks `status` who holds it and names that process and its pid. That look
never tries the lock itself (`lock_holder` reads the pid the holder wrote and checks that it is a mu300-update that
changes things): a probe that held the lock for an instant could turn a real run away. The lock stays the authority:
a run that loses the race ends with the updater's own "another mu300-update is running", in the task's log.

What the page shows of a running task: the step, from the last `==> ...` line of the output (a line it does not
know is shown as it is, so new steps need no change here); for a download, the file `fetch_verified` named
(`MU300_PROGRESS`, one `file NAME` line a file) with its size on the partition against the size GitHub gave; the
log, collapsed. A finished task says whether the device wants a restart by comparing each system's release, the boot
image and the kernel choice with what they were before it started.

**Online.** "Check" runs `releases` as a task (two requests to GitHub's API, which answers 60 an hour to one
address without a login; behind a carrier's NAT that may be used up by others, and the page then says what it says
when the device has no internet: GitHub could not be reached, update from a file). "Update" takes the tag the page
showed and only a tag the last check offered - the newest release or the pre-release - so what is installed is what
was shown, whatever became the newest meanwhile. The pre-release is offered only behind a tick that is off.

**From a file.** The format is the release's own Magisk zip (`mu300-magisk-TAG-SYSTEM-kKERNEL.zip`,
`tools/make-magisk-zips.sh`): it is already published for every release, it is one file, and it holds exactly what an
update of one system needs - `payload/` with the root filesystem and the kernel bundle of one system and one kernel,
`mu300/manifest` naming them with their hashes, and the updater. `apply --from ZIP` reads the manifest (each field
must be one of the values a release makes, and the two file names must be the ones those values give - a manifest
cannot name a path), then lets `apply` run as it always does with `fetch_verified` reading from the zip: each member
is read to a pipe by a name this code made (`unzip -p`), never unpacked to a path the zip names. `apply --from DIR`
takes a directory with a release's files and their `SHA256SUMS`, for a memory stick or `scp`; the page offers only
the zip. What a zip does not have, the update leaves as it is: the language pack (the installed one stays, as with a
release that has none), the VPN module (the installed one stays; `mu300-update`'s own offline route for it is
unchanged), the other systems of the device. It is refused, before anything is changed, when its system is not
installed, when it is the other Ubuntu release, when its kernel does not run on this model (`./devices` of the
bundle), when its kernel is not the one the device uses (a system and the boot image of two releases is what this
updater otherwise only has for one reboot), when it is older than what is installed (unless said: `--downgrade`),
and when a payload does not match its checksum. A release's updater continues the run only when it knows what a file
is (`from_handover`): an older one would go to GitHub for the release.

The upload goes through LuCI's own endpoint (cgi-io, with the session and the ACL's one path,
`/mnt/mu300-disk/.mu300-upload/update.zip`), into a directory on the Linux partition that the adapter makes with
mode 700 and refuses when it is a link, someone else's or writable by others. Before the upload the adapter is told
the size and checks the room: the partition must hold the file beside what `apply` wants, and `/tmp` must hold the
file too, because **cgi-io keeps an upload in `/tmp` until it is complete** and only then moves it to its path
(read from its source, not measured here: the largest zip, Ubuntu's, is a few hundred MB of RAM for the minute the
upload takes). After the upload the file is renamed to a name the ACL does not let the panel write, and only that
file is looked at and used; a link at the upload's path is removed, not followed. It is deleted when the update has
run, however it went, and by "Remove the file".

**Whom an uploaded file is trusted by.** A release from GitHub is trusted because it came over TLS from the
project's repository and every file matches the `SHA256SUMS` that came the same way. An uploaded file has no such
origin: its manifest and its checksums are its own, and say only that it is whole. So the page shows the file's
SHA-256 and what it says it is before anything, and installing it takes a tick with these words: nothing proves
that it comes from the project. The real answer is a signature:

* The release workflow signs `SHA256SUMS` (`tools/sign-release.sh`, from `make-release.sh`) with the key in the
  repository secret `MU300_RELEASE_KEY` and publishes `SHA256SUMS.sig`. The format is that of OpenWrt's `usign` and
  OpenBSD's `signify` (Ed25519). The signer uses openssl, so the runner needs no usign; what it writes was compared
  with what `usign -S` writes for the same key and file in the 25.12.5 image: the same bytes, and `usign -V` accepts
  it.
* The public key is part of the system: `/opt/mu300/lib/release.pub`, from `rootfs/overlay/` like the updater
  itself, so both systems get it. Not `/etc/mu300/release.pub`, as first planned: an update carries `/etc/mu300`
  over from the old system as a whole, so a device would never receive the key, nor a later one.
* `mu300-update` checks the signature where the system has the key: with `usign` on OpenWrt (it is in the image, 20
  KB, no new package) and with `openssl` on Ubuntu (`sig_state`; openssl 3 is in both Ubuntu releases). Without the
  key file nothing is checked and everything is as it was.
* The Magisk zips carry the release's `SHA256SUMS` and, for a signed release, `SHA256SUMS.sig` (from the release
  that brings this on): the signature covers the checksums, the checksums the two files of the payload. The zips of
  v2026.10.25 and older have neither and can never be more than "not signed".

| the source | signature | what happens |
|---|---|---|
| any | does not match the key | refused, always; no option takes it |
| any | the key file is not root's own regular file (a link, writable by others, empty) | refused, always: that is not "no key" |
| any | the checksums name another release than the one asked for, or are signed and name none | refused, always |
| GitHub or a mirror | valid | used |
| GitHub or a mirror, the system has no key | - | used, as before signing: there is nothing to check with |
| GitHub or a mirror, the system has a key | none, or nothing here can check one | refused, newer or older; `MU300_ALLOW_UNSIGNED=1` (`apply --unsigned`) takes it |
| a file or a directory | valid | used; the page asks for no extra tick |
| a file or a directory | none, or the system has no key or no tool | refused without `--unsigned`; the page's tick is that option |

**The rule, after the security review of this change** (it found two ways in: an update applied although no
signature had positively checked, and an old signed release accepted as it came). Only "valid" says the files are
the project's. Everything short of it is one of two things: a system that has no key and takes a release from
GitHub or a mirror, which is exactly what every system did before signing and cannot be made better without a key;
or a refusal that only the owner's word lifts, given per run and by name. A first version of this let a system
*with* a key take an unsigned release silently when it was older than the installed one ("from before signing"):
that made taking the signature away a way to put an old release back, and is gone. What was checked, point by
point:

* *Missing signature, key or tool.* No signature and no tool are "not signed" and need the word; a key file that
  is not root's own is refused outright (`key_state`: a link, a file others can write or an empty one would
  otherwise have read as "no key" and let everything through).
* *usign's verdict.* Its exit status is tested directly (`if usign -V ...`), not through a pipe; the openssl path
  says "valid" only when `pkeyutl -verify` succeeded on a key and a signature of the right sizes and the same key
  number.
* *Check, then use.* The checksums are judged once and pinned by their SHA-256 (`SUMS_PIN`, `FROM_PIN`): every
  later look at them is at those bytes or the run stops, so other checksums put in their place after the check -
  with a payload that matches them - are not taken (tested for a download and for a file). The staging directory
  is made root's own with mode 700, and refused when it is a link or someone else's, before anything is put into it
  or checked in it (`stage_private`): the verified file is the one unpacked minutes later. A file is taken only
  after `from_begin` judged it; `from_verified` gives nothing otherwise.
* *Where the key comes from.* One path, the installed system's `/opt/mu300/lib/release.pub`; the code names
  `release.pub` in that one place (a test counts). A zip that brings a key and is signed with it is judged by the
  system's key, or is "no key" on a system without one. The review asked for `/etc/mu300/release.pub`; it stays
  where it is for the reason above (an update carries `/etc/mu300` over, so the key would be the old system's for
  ever) - what matters is that it is the image's file, root's, not writable by others and not a link, and that is
  checked.
* *The release's own updater.* `apply` continues with it only after the release it came with passed all of the
  above (`fetch_verified` judges the checksums before it hands out any file, the updater included), and after the
  downgrade rule below. An unsigned file taken on the owner's word brings its updater with it: that is what the
  word means, and the page says so.
* *What the panel can switch off.* Nothing by the environment: the adapter clears every variable that names a
  key, a source or a waiver before it runs the updater. `--unsigned` and `--downgrade` come only from the `flags`
  of `update_act` (a fixed set of words, in the write grant), only for `apply_file`, and only when the file that
  was shown is unsigned or older.

**Old releases.** A release older than what is installed is taken only when asked for by name
(`apply --downgrade`, `MU300_ALLOW_DOWNGRADE=1`), from every source: GitHub, a mirror (`MU300_RELEASE`,
`MU300_RELEASE_URL`, the update-source file), a file. `downgrade_ok` runs before the release's own updater is
fetched, so an old updater cannot skip it; `boot` and `kernel` have the same rule for a kernel taken alone
(`boot_downgrade_ok`). `rollback` is not a downgrade in this sense: it puts back the copy the device itself kept.
This changes `mu300-update`: until now `MU300_RELEASE=<older> mu300-update apply` went back without a word.
And the tag that is compared is inside what is signed: `make-release.sh` publishes `mu300-release` (the tag and a
newline) and lists it in `SHA256SUMS`, so the signature covers which release the checksums are of. The updater
needs no download for that - it compares the listed hash with the hash of the tag it was asked for (`tag_sha`). A
signed `SHA256SUMS` of v2026.10.01 handed out as v2026.11.02, by a mirror or in a zip whose manifest says the newer
tag, is refused; signed checksums that name no release are not taken as signed.

**A second review** (three findings; all three were in this change's own lines) and what it led to:

* *The gate judged one value and the action used another.* Three places. (a) Every gate - signature, downgrade
  rule, what the page showed - judged a *name*: the tag asked for, or the tag an unsigned zip's manifest gives
  itself. What is installed is the files, and nothing compared the two, so an unsigned zip calling itself
  v2026.12.24 with the system of v2026.09.01 passed the downgrade rule by its name. Now the root filesystem staged
  for each system must say in its own `etc/mu300/image-version` that it is the release that was judged
  (`payload_is`, before anything is changed, for every source); with signed checksums the name was bound already.
  (b) The downgrade rule looked at the systems, and the update also writes the kernel and the boot image: after a
  `rollback` of a system, a release between the two would have taken the boot image back without a word. The rule
  now includes the boot image's release. (c) The page's yes was for the file `inspect` had hashed, and the updater
  was handed a path: the adapter now passes that hash (`apply --from FILE --sha256=HASH`) and the updater takes
  the file only if it still has it.
* *Files more open than they need be.* Nothing was opened for the page - it reads through the adapter, as root -
  but several files were made with whatever umask the caller had: the adapter's task files, the kept answers of
  `releases` and `inspect`, and what the updater writes of an offline source into the staging directory. The
  adapter now runs with umask 077 (and starts the updater under 022, which it needs: it makes the directories of
  the new system), the upload is 600, and what `from_open` and `from_verified` write is 600 under any umask. The
  staging directory was 755 before this change and is 700 now; one found writable by others is emptied before
  use, since a name in it could be a link someone left.
* *Anything else loosened.* Read again for that: `MU300_FROM_SHA` and the two waivers are this run's own words
  (reset when the options are read, cleared by the adapter), no lock, link check or refusal of the old code was
  removed, and the commands that take no lock (`status`, `releases`, `inspect`) write nothing but `inspect`'s own
  temporary directory.

The row that refuses unsigned releases is the one that can lock devices out, so the release side guards it: when
the tree has the public key and the build has no secret key, `make-release.sh` refuses to publish; and
`sign-release.sh` checks its own signature against the tree's public key and refuses to sign with a key that is not
that one.

**What the owner does to switch signing on** (nothing in this PR makes or holds a key): on any OpenWrt system, or
in the image's container,

    usign -G -c 'mu300-linux release key' -s release.sec -p release.pub
    gh secret set MU300_RELEASE_KEY -R dikeckaan/mu300-linux < release.sec     # then keep release.sec offline, or delete it
    cp release.pub rootfs/overlay/opt/mu300/lib/release.pub                    # commit this file

(`signify-openbsd -G -n -c ... -s release.sec -p release.pub` on Debian or Ubuntu makes the same two files.) From
the next release on, the release is signed and its images check. The secret alone signs releases that no device
checks yet; the committed key alone stops the next release from being published. A device starts checking with the
first system that has the key, so the update *to* that system is the last one trusted the old way.

What the signature does not cover: the VPN module (its own repository and `SHA256SUMS`); `SHA256SUMS-magisk`, the
checksums of the zips themselves, which is why the page shows a zip's SHA-256 only as something to compare by hand
and relies on the signed checksums inside it; Magisk, which installs a zip without knowing any of this; and a
device where someone already is root (the key is a file of the system).

**Another source.** `/etc/mu300/update-source` (root's own file, not writable by others, not a link) can name a
mirror: `MU300_API_URL=` in place of `https://api.github.com/repos/dikeckaan/mu300-linux` and
`MU300_DOWNLOAD_URL=` in place of `https://github.com/dikeckaan/mu300-linux/releases/download`, plain http(s) URLs
only; the command and the panel read the same file. It exists for the device test below and for places where GitHub
cannot be reached. Without a release key a mirror is trusted as much as whoever runs it; with one it cannot change
a file. The file is in `/etc/mu300`, so it survives updates: whoever could write it was root. (Since the panel's
Update page gained the same setting - a *Mirror (release files)* field, written through one `mu300-update source`
command - an account that may use that page's write access can change the source as well, and its read access is what
shows the address in force.)

**What a browser may ask for.** Reading (`update_get`, `update_job`) is in the ACL's read grant, every change
(`update_act`) in the write grant, and the upload path is the one file path added. Nothing starts by a GET: LuCI's
ubus endpoint takes POSTs with a session. Every parameter is a fixed word, a release tag
(`v[0-9]{4}\.[0-9]{2}\.[0-9]{2}`, and since §125 `vYYYY.MM.DD.N` too), one of the three systems, one of the three kernels, a size or a SHA-256; mu300dash
refuses anything else before the adapter runs, and the adapter checks again. Everything that changes the device
also wants the word of its operation (`confirm`), so a stray call does nothing; on the page each of those is a
dialog that says what will happen, and going back or deleting the kept version takes a tick first. The log and the
update report are shown redacted: every URL reduced to its scheme (a mirror's address can hold a token), what
follows a password, key, token or secret word, numbers of 15 to 20 digits (IMSI, ICCID, IMEI) and phone numbers
(`+` and digits, or ten to fourteen digits after a 0). Sizes, dates and checksums stay.

**For Ubuntu's page.** Cockpit's MU300 page (`rootfs/panel`, out of scope here) can be given the same section with
the same four commands: `status`, `releases` and `inspect` are plain JSON on stdout, and `apply --from` takes a path.
What it would need of its own is the task (there `systemd-run` in place of `setsid` and the runtime directory) and
the upload (Cockpit writes files through its own channel, as root, with no `/tmp` in between).

**Tested** (no device): `tests/test_update_page.py` - the updater's additions under dash, bash and busybox sh
(status and releases as JSON whatever the files hold; a zip and a directory as sources, what is refused and why, a
whole `apply --from` on a fake partition with the network stubbed to fail; signatures with a key made in the test,
a signature made by real usign, a mirror that changes a file with and without its signature; a key file that is a link or writable
by others; a zip that brings its own key; checksums swapped after the check; an old release from each source; a
signed release under another's name; the release signer and the zip builder end to end), the adapter against a stand-in updater (what each operation needs before it starts
anything, the task's states, the lock, the staging directory with links and wrong modes and no room, the redaction),
and the page under Node with a small DOM (what it shows for a state, what each button sends, that no backend text
is markup). `tests/test_mu300dash_security.py` has the three methods in every table (hostile values in every
field, the arguments as the adapter gets them, the ACL).

**Run in the image, not on a device** (the `openwrt-luci` root filesystem of v2026.10.18 as a container on a
computer, so its busybox ash, busybox awk, uclient-fetch, usign and the static busybox, but no rpcd, no eMMC and
another kernel): `mu300-update status --sizes`; `releases` against a static mirror laid out as in the protocol below
(uclient-fetch follows the server's redirect for `releases?per_page=10`, busybox awk reads the list); `inspect` of
three small zips - unsigned, signed with a throwaway key, and signed with another key - which the static busybox's
`unzip -p` read and the image's own `usign` judged `valid` and `bad` as they should be.

**Not measured on a device** (before the U30 Air run below): that a task started by rpcd's child with `setsid`
outlives a restart of rpcd on this image (the SMS job is started by the same call, §46); cgi-io's use of `/tmp`
for a zip of real size and what the device does when it does not fit; `unzip -p` on a 100 to 400 MB stored member,
and how long `inspect` then takes (it hashes the whole zip and both payloads; it is a task for that reason);
GitHub's real answer and its rate limit from a carrier's address; the download progress against uclient-fetch's
real behaviour (it writes the file as it goes, which is all the page reads); a whole `apply`, online or from a
file, with a real boot image; the page in a real browser with the Aurora theme; the texts in 29 languages, which
are machine translations like the rest of those catalogs. Still not measured: the F50, Ubuntu, a carrier's
rate limit, the 29 machine-translated catalogs, and "Start Android at the next restart" (a U30 Air in Android
cannot be brought back without hands).

**The device protocol** (an F50 or U30 Air on `openwrt-luci`, with a previous release installed; `PC` is the
computer's address as the device sees it, `DEV` the device's):

    # 0. the build under test, onto the device (or an image built from the branch)
    A=openwrt/luci-app-mu300
    scp rootfs/overlay/opt/mu300/bin/mu300-update root@$DEV:/opt/mu300/bin/mu300-update
    scp $A/root/usr/libexec/unisoc-modem/update $A/root/usr/libexec/unisoc-modem/dashboard-info root@$DEV:/usr/libexec/unisoc-modem/
    scp $A/root/usr/libexec/rpcd/mu300dash root@$DEV:/usr/libexec/rpcd/
    scp $A/root/usr/share/rpcd/acl.d/luci-app-mu300.json root@$DEV:/usr/share/rpcd/acl.d/
    scp $A/root/usr/share/luci/menu.d/luci-app-mu300.json root@$DEV:/usr/share/luci/menu.d/
    scp $A/htdocs/luci-static/resources/view/mu300/update.js $A/htdocs/luci-static/resources/view/mu300/home.js root@$DEV:/www/luci-static/resources/view/mu300/
    scp $A/htdocs/luci-static/resources/mu300/common.js root@$DEV:/www/luci-static/resources/mu300/
    ssh root@$DEV 'chmod 755 /usr/libexec/unisoc-modem/update; rm -f /tmp/luci-indexcache*; /etc/init.d/rpcd restart'
    ssh root@$DEV 'mu300-update status --sizes; mu300-update releases'        # both one line of JSON

    # 1. a mirror with two real releases (OLD installed on the device, NEW the one to update to)
    OLD=v2026.10.24 NEW=v2026.10.25 R=dikeckaan/mu300-linux
    mkdir -p mirror/api/releases
    for t in $OLD $NEW; do gh release download $t -R $R -D mirror/download/$t -p SHA256SUMS -p 'mu300-*.tar.gz' -p mu300-update; done
    gh api "repos/$R/releases?per_page=10" > mirror/api/releases/index.html     # /api/releases?per_page=10 is served this
    gh api "repos/$R/releases/tags/$NEW" > mirror/api/releases/latest
    python3 -m http.server 8000 -d mirror &
    ssh root@$DEV "printf 'MU300_API_URL=http://$PC:8000/api\nMU300_DOWNLOAD_URL=http://$PC:8000/download\n' > /etc/mu300/update-source; chmod 600 /etc/mu300/update-source"

    # 2. online: System > Update > Check (NEW is offered, with the download size and the room), Update, confirm.
    #    While it downloads: close the browser, open the page from a phone - the task is there, with the file and
    #    its percentage. During the unpacking: ssh root@$DEV /etc/init.d/rpcd restart - the task goes on, the page
    #    finds it again. At the end: "Restart now"; after the restart the page shows NEW and the previous version.
    ssh root@$DEV 'mu300-update status' ; ssh root@$DEV 'cat /var/run/unisoc-modem/update-job/log | tail -5'

    # 3. one at a time: start an update on the page and, while it runs,
    ssh root@$DEV 'mu300-update clean'            # "another mu300-update is running (pid N)"
    #    and the other way round: start "mu300-update apply" in ssh, open the page - it names that run and its
    #    pid, and every button is off.

    # 4. going back and cleaning: "Back to the previous version" (tick, confirm), restart, the page shows OLD;
    #    update again; "Back to the previous boot image"; then "Remove the previous version" and
    ssh root@$DEV 'ls /mnt/mu300-disk; df -h /mnt/mu300-disk'

    # 5. the pre-release: the mirror says OLD is the newest and NEW is a pre-release
    gh api "repos/$R/releases/tags/$OLD" > mirror/api/releases/latest
    gh api "repos/$R/releases?per_page=10" | jq --arg t $NEW 'map(if .tag_name == $t then .prerelease = true else . end)' > mirror/api/releases/index.html
    #    with OLD installed: Check says "Up to date" and offers "Also offer the pre-release NEW" behind a tick

    # 6. no internet: stop the mirror (kill %1), Check - the page says GitHub could not be reached, in words,
    #    within a minute; then with mobile data off and no update-source file the same against GitHub itself
    ssh root@$DEV 'rm -f /etc/mu300/update-source'

    # 7. from a file, the real Magisk zip of NEW for this system and kernel, with OLD installed
    gh release download $NEW -R $R -p "mu300-magisk-$NEW-openwrt-luci-k5.4.zip" -p SHA256SUMS-magisk
    #    upload it on the page; watch /tmp and the partition meanwhile
    ssh root@$DEV 'while :; do df -k /tmp /mnt/mu300-disk | tail -2; ls -la /mnt/mu300-disk/.mu300-upload /tmp/luci-upload* 2>/dev/null; sleep 2; done'
    #    the page shows the SHA-256 (the one in SHA256SUMS-magisk), NEW, the system, the kernel, "not signed";
    #    tick, update, restart. Then: the zip of another kernel (refused: kernel), of Ubuntu on a device without it
    #    (refused: system), a zip with one byte changed in the payload (refused: damaged), OLD's zip with NEW
    #    installed (the downgrade tick), and from the command line
    ssh root@$DEV 'mu300-update inspect /root/x.zip; mu300-update apply --from /root/x.zip --unsigned'

    # 8. a full partition: fill it until less than 2 GB are free, then Check/Update online (apply stops at "not
    #    enough free space", the page shows the failed task and "Nothing was changed") and an upload (refused
    #    before it starts); the same with /tmp nearly full (refused: memory)
    ssh root@$DEV 'dd if=/dev/zero of=/mnt/mu300-disk/fill bs=1M count=4000; df -h /mnt/mu300-disk'
    ssh root@$DEV 'rm -f /mnt/mu300-disk/fill'

    # 9. the kernel: change to 6.18 on the page (confirm), restart, uname -r; back to 5.4; "Start Android at the
    #    next restart", restart, and back with the Magisk module's Action button
    ssh root@$DEV 'uname -r; mu300-update kernel'

    # 10. signatures, with a throwaway key (never the project's): sign the mirror's SHA256SUMS, give the device
    #     the public key, update online (the log says "signed with the project's release key"); remove the .sig
    #     from the mirror (refused); change one byte of a tarball and its line in SHA256SUMS (refused)
    #     (a release from before this change does not name itself in its SHA256SUMS: add the line a new one has)
    usign -G -s lab.sec -p lab.pub
    printf '%s  mu300-release\n' "$(printf '%s\n' $NEW | sha256sum | cut -d' ' -f1)" >> mirror/download/$NEW/SHA256SUMS
    MU300_RELEASE_KEY_FILE=lab.sec sh tools/sign-release.sh mirror/download/$NEW/SHA256SUMS lab.pub
    scp lab.pub root@$DEV:/opt/mu300/lib/release.pub
    #     then: the signed SHA256SUMS and .sig of NEW copied to mirror/download/v2099.01.01/ with NEW's files, and
    #     "latest" edited to that tag (refused: the checksums of another release); chmod 666 on the device's key
    #     (refused: not root's own); OLD from the mirror with NEW installed (refused without --downgrade):
    ssh root@$DEV "MU300_RELEASE=$OLD mu300-update apply; MU300_RELEASE=$OLD mu300-update apply --downgrade"
    #     afterwards: ssh root@$DEV 'rm -f /etc/mu300/update-source', and the image's own release.pub back (the
    #     project's key is part of the image since it was committed; an update puts it back as well)

**Measured on a U30 Air** (2026-10-15, `openwrt-luci`, kernel 6.18 and 7.2, the owner's sing-box VPN with its kill
switch on throughout; test releases built from this branch: v2026.10.28 and v2026.10.30 signed with the project's
key by `make-release.sh` through `MU300_RELEASE_KEY_FILE`, v2026.10.29 unsigned, v2026.10.31 unsigned - made from
v2026.10.30 with its root filesystems relabelled, because docker's disk was full; served by a mirror on the
computer through `/etc/mu300/update-source`, throttled to 300-700 kB/s so a download could be watched):

* **Signed, end to end, from the page:** v2026.10.28 to v2026.10.30 online - Check, "Update to", confirm, the
  release's own updater taking over ("continuing with the mu300-update of v2026.10.30", "signed with the project's
  release key" before each download), *Restart now* from the page, up on v2026.10.30 after about 40 s.
* **The task outlives the page and rpcd:** the page closed during the download; `/etc/init.d/rpcd restart` during
  "keeping your settings" - the apply went on (its pid unchanged), and the page opened afresh (a new login: the
  restart ends LuCI's sessions) showed the finished task with its log and *Restart now*.
* **One at a time, both ways:** with the page's update running, `mu300-update clean` in ssh said "another
  mu300-update is running (pid N)"; with `mu300-update apply --downgrade` started in ssh, the page said "Another
  update is running on the device: sh .../mu300-update apply (pid N)", every button off, and `update_act` answered
  `busy`.
* **Unsigned:** online, v2026.10.29 and v2026.10.31 on a system with the key are not offered (the page says why,
  in words; `mu300-update apply` refuses with "nothing was changed"). From a file, the page shows "not signed",
  the SHA-256 (the one in `SHA256SUMS-magisk`) and the tick with its words; *Update from this file* without the
  tick is refused on the page ("Tick the confirmations above first") and by the adapter ("This file is not signed:
  that needs confirmation"); with it, v2026.10.30 to v2026.10.31 installed and started.
* **Downgrade:** a signed v2026.10.28 zip over v2026.10.29 and a signed v2026.10.30 zip over v2026.10.31, each
  with the page's tick, installed and started (the second one also wrote a boot image, read back and booted);
  online `MU300_RELEASE=<older> mu300-update apply` refused without `--downgrade` and went through with it.
* **Refused files:** a zip cut at 20 MB ("not a release file of this project"), one byte changed in the payload
  ("damaged: its contents do not match their checksums"), the zip for kernel 7.2 on 6.18 ("another kernel ...
  take the zip for kernel 6.18"), the Ubuntu 24.04 zip ("its system is not installed"). A 112 MB zip reached the
  partition in about 3 s over USB; `inspect` of a 42 MB zip took about 10 s.
* **Full /tmp and partition:** /tmp with 34 MB free: "Upload failed: Not enough memory for this upload" before
  anything was sent. The partition with 1.4 GB free: the upload is refused ("Not enough free space on the Linux
  partition") and `apply` stops at "not enough free space" before any download.
* **Rollback, rollback-boot, clean** from the page, each with its tick and dialog, each restart came up on what
  the page said (rollback v2026.10.30 to v2026.10.31; the boot image back to the installer's; the kept system
  deleted, and the copy a rollback leaves with it).
* **Kernel:** 6.18 to 7.2 from the page (the kernel of the newest release, signed), restart, 7.2.10 with USB,
  the VPN and its kill switch; back to 6.18 with `mu300-update kernel 6.18`, restart, 6.18.56. With an unsigned
  newest release the kernel change is refused and the choice stays.
* **No internet:** the mirror refusing connections: the page said "GitHub could not be reached" after 14 s; an
  address that never answers: `releases` says offline after 32 s. GitHub itself (no `update-source`, through the
  VPN) answered in 3 s.
* **Signatures with the project's key on the device:** `release.pub` made writable by others: "not a file of
  root's own: nothing is trusted with it, and nothing is updated"; v2026.10.30's signed checksums under the tag
  v2026.11.01: "these are the checksums of another release than v2026.11.01: not used".

Found and fixed on the way (each with a test):

* `apply --unsigned` and `--downgrade` did not reach the release's own updater: apply hands over with the options
  taken out, and the two words were shell variables that were not exported - the next updater refused what the
  owner had allowed ("not signed ... not used" after "continuing with the mu300-update of ..."). They are exported.
* The page offered an online update it could only fail (an unsigned release on a system with the key, the task
  then ending with a hint at mobile data): it says why instead, and `fetch_verified` tells a refused release (3)
  from a download to continue, so `apply` no longer suggests a network fault.
* After every update that did not change the kernel the boot image kept the older release's name, so `check`
  said "the boot image may not be" and the page offered the release just installed again: an image found up to
  date is now named after the release that found it.
* After a rollback, before the restart, the page named the running system "openwrt" on an `openwrt-luci` device
  and showed no pending restart: `running_os` did not know `<os>.broken`.
* The note "compare the SHA-256 ... the only proof of where an unsigned file comes from" showed for a signed file;
  the reinstall tick showed without an Update button; offline took two rounds of retries (24 s and 64 s before).
* **`/dev/mmcblk0p38` a plain file.** After one boot the U30 Air's boot_b node was a 50 MB regular file in RAM:
  OpenWrt's procd mounts a new, empty tmpfs on /dev once preinit is over (`procd_coldplug`) and fills it from the
  kernel's events, and the early recorder - started in preinit, writing for 420 s - ran its `dd` in that moment
  and created the file; the node was never made again. `boot_update` refused it only because the file had no
  header ("boot_b does not hold a boot image header v4"); `rollback-boot` would have written into RAM, read it
  back as written and reported success. The recorder now writes only to a block device and replaces a plain file
  with the node (`mknod` from sysfs); `boot_update` and `rollback_boot` take only a block device (`boot_dev`). It
  happened in one boot, the one before this run; in the ten boots of the run the node stayed a block device.
* Not changed: a rollback leaves `<os>.broken` (271 MB) until the next `apply` or `clean`, and the page offers
  *Remove the previous version* only when there is a `<os>.old`; the log of a GitHub download shows the signed
  redirect URL of the asset (it expires within the hour; the page's log redaction reduces URLs to their scheme).

## The web installer

### 72. The web installer: adb over WebUSB, how the release files reach the device, WebUSB per platform, and what a closed tab leaves

`site/web-installer/` installs, manages and removes Linux from Chrome or Edge over USB, with nothing on the computer
but the browser. The design is in `docs/web-installer.md`; this section is what was measured for it. On 2026-10-13
it was **run from start to finish on an F50** (64 GB, Android 13 `F50_FLYMODEM_ZYV1.0.0B09`, Magisk 30.6, release
v2026.10.25) from a Mac: the page's own modules from Node over the `usb` package's WebUSB object, and the real page
in Chrome 155 (headless, a throwaway profile). The table of what ran is in that document; what the run found is
here, marked *measured on the F50*. **Not measured:** Windows, Linux as the computer's system, a U30 Air, an SD
card as the target, KernelSU/APatch, an Android that is not rooted, a download over a carrier's network.

**1. The adb client: our own, about 900 lines, no dependency.** The candidate was ya-webadb / Tango (`@yume-chan/adb`
2.6.4 with `adb-daemon-webusb`, MIT, maintained). It is TypeScript in a dozen packages with bare imports
(`@yume-chan/async`, `event`, `struct`, `no-data-view`, `stream-extra`; 609 kB unpacked for `adb` alone), so the site
would need a bundler in CI or a vendored bundle to keep in step by hand, on a page that writes to boot partitions.
What we need of adb is small and fixed: the handshake with RSA authentication, shell v2 with exit codes, sync push,
pull and stat, reboot. `site/assets/web-installer/adb/` is that, as plain ES modules the browser and Node load as
they are. Two things were taken from reading ya-webadb's WebUSB backend and AOSP's `usb_linux.cpp` (facts, no code):
adbd sends a packet as two USB transfers, so the header is read with a request of one endpoint packet and the payload
with a request of exactly its length; and a write whose length is a whole number of endpoint packets must be
followed by a zero-length packet.
* *The signature.* adb signs the device's 20-byte token as if it were a SHA-1 digest (PKCS#1 v1.5). WebCrypto's
  `sign()` always hashes first and cannot make that signature, so the key is generated with WebCrypto, exported, and
  the private operation is a BigInt `modPow` (about 10 ms for RSA-2048 in Node 26). The key therefore lives as
  numbers in IndexedDB, not as a non-extractable CryptoKey; it is not constant time. Checked: the public key line
  our code derives from a key made by `adb keygen` (platform-tools 37) is byte for byte the `adbkey.pub` adb wrote
  for it, and Node's OpenSSL accepts the signature as adbd would (`tests/web/adb.test.mjs`).
* *Against a real adbd over TCP.* Ubuntu 26.04's `adbd` package (AOSP 34.0.5) in a container: handshake and
  features, shell v2, stdin, timeouts, push/pull/stat of 0 to 5 MB with equal SHA-256, refused files, an aborted
  push (`tests/web/interop.test.mjs`, run by hand: `MU300_ADBD_TCP=host:port`). Stock adbd gives a pushed file the
  owner's mode bits for group and others too (0644 arrived as 0666, on the F50 as well): the page never relies on
  the mode of a pushed file, and a password does not travel in a file (below).
* *Over USB, measured on the F50.* The transport, framing and sync work as written: connected in 2 to 100 ms, the
  device scripts staged in 60 ms, a 41 MiB zip pushed at 20 to 27 MiB/s and a 112 MiB one at 20 MiB/s (including the
  device's SHA-256), a 78 MiB backup read back in 14 s (as base64 through the shell, 5.5 MiB/s; 9 MiB/s with adb's
  file service, which root's directory rules out, below) with every file's checksum equal to the device's.
* *Android's adbd on the F50 asks for no key.* `ro.adb.secure` is 1 and `/data/misc/adb` is empty, yet a key the
  device had never seen got `CNXN` at once: no `AUTH` packet, no question (there is no screen to ask on). So a
  browser's own key needs nothing there. The adbd of MU300 Linux does authenticate when it is set to keys: after an
  installation with "only this browser" the page's key was accepted by its signature (`AUTH` once, then `CNXN`),
  and the Mac's own adb was `unauthorized`.
* *The first packet of a session can be lost, and the device then waits for a host that waits for the device.*
  Seen from Chrome after a session that ended without a goodbye (the browser quit, a tab closed or reloaded): the
  next connection sent `CNXN` and heard nothing, for as long as it waited, and every later attempt the same. A probe
  at the transfer level showed why: when the two ends of the bulk IN endpoint are out of step, exactly one transfer
  is dropped - the 24-byte header of the device's answer - and its 303-byte payload arrives alone. `clearHalt()` on
  the endpoints, which adb's own client does on macOS, makes this happen every time on this device (the host's side
  goes back to its first packet, the device's does not: header lost on 3 of 3 tries, 0 of 6 without), so the page
  does not call it. The client now takes a payload-without-header during the handshake, followed by 0.7 s of
  nothing, as "the header was lost" and sends `CNXN` once more (adbd answers a second `CNXN` like the first); what
  an earlier session left in the pipe looks the same for a moment but is followed by the real answer, and then
  nothing is asked twice (a second `CNXN` to a device with keys makes it issue a new challenge every time). On top
  of that the page tries a handshake up to three times and gives a silent device six seconds. After the change: 18
  of 18 connections after a quit browser, a closed tab and a reload (6 each); before it the page hung at "Opening
  the device" with no message.
* *Just after a start* Android sets its USB functions up a second time, and a connection made in those seconds is
  cut (`LIBUSB_TRANSFER_ERROR` in Node, "the connection to the device ended" in the page). The page waits 2.5 s
  before it reconnects to a device that came back, and says "connect again" otherwise.

**2. How the release files reach the device: the device downloads; or the browser, from a mirror; or the user.**
A page cannot read a release asset. Measured with `curl -H 'Origin: https://kaandikec.com'`, again on 2026-10-13:

| request | answer | CORS |
|---|---|---|
| `github.com/.../releases/download/<tag>/<file>` | 302 to `release-assets.githubusercontent.com` | no `Access-Control-Allow-Origin` on the 302 |
| the redirect target | 200 (206 for a range), `application/octet-stream` | none |
| `api.github.com/repos/.../releases` | 200 | `Access-Control-Allow-Origin: *` (60 requests an hour without an account) |
| `api.github.com/repos/.../releases/assets/ID` with `Accept: application/octet-stream` | 302 with `Access-Control-Allow-Origin: *` | the target it redirects to has none, so `fetch()` fails at the second hop |
| `raw.githubusercontent.com/<owner>/<repo>/<ref>/<file>` | 200, 206 for a range | `Access-Control-Allow-Origin: *`; a preflight (`OPTIONS`) is answered 403, so only requests that need none: a plain `GET` without a `Range` header |
| a GitHub Pages site | 200 | `*` (and this site is the page's own origin) |
| `api.github.com/repos/.../git/blobs/SHA` or `/contents/PATH` with `Accept: application/vnd.github.raw` | 200 | `*`, but every request counts against the 60 an hour, and 100 MB per blob |
| `media.githubusercontent.com` (LFS) | - | `*`, but LFS has a bandwidth quota (1 GB a month free) |
| `codeload.github.com` (archives) | 200 | `Access-Control-Allow-Origin: https://render.githubusercontent.com` only |
| `ghcr.io` (the token endpoint, `/v2/`) | 403 / 401 | none |

So `fetch()` gets the release *list* and nothing of the files, and the list is enough for integrity: the API gives
every asset a `digest` (`sha256:...`). The files themselves can only come to a page from a *repository*
(`raw.githubusercontent.com`, at most 100 MB a file) or a Pages site (1 GB a site); one release's 11 zips are
890 MB, 39 to 124 MB each.
* *First: the device downloads the zip itself* (`android-web.sh net`, `run fetch NAME SIZE`), from an address the
  script builds from the zip's name (this project's release of the tag in the name; the page cannot name another).
  *Measured on the F50:* Android has no `curl`, no `openssl` and no `wget` of its own (toybox has `nc` only); the
  root manager's busybox (1.36.1; every Magisk zip carries a busybox too) has `wget` with TLS and follows GitHub's
  302 to the object store - and prints `wget: note: TLS certificate validation not implemented`. It took
  `self-signed.badssl.com` and `wrong.host.badssl.com` without a word. There is no verifying downloader on these
  devices and the project builds none, so the download is not trusted for what it is: the file must have exactly
  the size the release names; it is used only with the SHA-256 that the *browser* read from GitHub's API over its
  own verified TLS, computed on the device over the file only root can change; and since `wget` follows redirects
  by itself, what it prints is watched (`Connecting to HOST (ADDRESS:PORT)`): a connection to anything but
  `github.com` or `*.githubusercontent.com` on port 443 ends the download and nothing is kept. A man in the middle
  can make a download fail and can see which public file is asked for; he cannot get a file installed.
  **Accepted by the owner (2026-10-13):** the device downloads over a transport that cannot verify certificates,
  because integrity is by the pinned digest, not by the transport - the SHA-256 comes from `api.github.com` over the
  browser's verified TLS and is checked on the device, over the file only root can change, before anything is
  used, with the size and host limits above. `wget -c`
  continues a broken download: cut after 15 MB of 41.4, the second run fetched the other 28.5 MB and the checksum
  was the release's. A try that brings nothing ends with "no connection" (exit status 10 of the job; 11 another
  host, 12 failed, 13 not the release's size); a try that brought something is continued up to five times, and the
  start of a file is kept for the next run.
  - *The uplink, measured on the F50:* this unit's Android had **none**. Its SIM was registered (LTE, in service)
    with mobile data on, but no data bearer (`mDataConnectionState=-1`, "Active default network: none"), and
    Android on an F50 has no Wi-Fi client (it is the hotspot). `wget` there says `bad address 'github.com'`, the
    probe answers `{"ok":0,"why":"no-network"}` in under a second, and the page says so and proposes the next way.
    To measure the downloader all the same, the device's name lookups were pointed at the test computer, where a
    relay read only the server name of each TLS hello and connected to that host (TLS end to end between busybox
    and GitHub): 41 MiB in about 4 s and 112 MiB in about 8 s, which is the cable's and the relay's speed, not a
    carrier's. *Not measured:* a real bearer - its speed, what a carrier's proxy or sign-in page does, and the
    words `dumpsys connectivity` uses for an active network (the script reads `CELLULAR`/`WIFI`/`ETHERNET` from the
    line of the default network, as Android 13 prints it; on this unit there was no such line to read).
  - *A defect this found:* the script took the tag out of the zip's name with a `sed` whose basic expression used
    `\|`. Busybox built for Android uses bionic's regex, which has no `\|` there, so on a device **every** release
    zip was "not the name of a release zip" (`bad-name`), while the tests, under a computer's busybox, passed. The
    name is now taken apart with the shell's own patterns. And a directory `in/` that root made for the download
    in the adb user's directory refused the page's next push ("couldn't create file: Permission denied"): the
    download now goes to root's own directory.
* *Second: the browser downloads the zip from a mirror* (`mirror.js`; on since 2026-10-13, the repository is
  `dikeckaan/mu300-linux-mirror`): a branch `<tag>` of that repository with every zip in parts of at most 45 MiB and
  a manifest (`tools/make-release-mirror.sh`; the last step of `magisk.yml` pushes it with a deploy key of the
  mirror repository, over ssh to GitHub's published host keys, no token), read from `raw.githubusercontent.com` with plain
  `GET`s (`redirect: "error"`, no credentials). A part must have the manifest's size and SHA-256, the parts must add
  up to the size the release names, and the whole must have the release's checksum - the mirror's word counts for
  nothing. *Measured on the F50, in Chrome, against a stand-in server for that host:* a device without internet was
  told apart and this way proposed; a part cut after 5 MB gave "the download broke off", and the second try
  downloaded 41 MiB, pushed it and got the device's plan. *Measured against the real host on 2026-10-15* (the
  page's modules from Node, F50-B in Android with no internet, the Mac on a home connection): the device's own
  probe said `no-network` ("bad address 'github.com'"), so the page proposes the mirror; the manifest of branch
  `v2026.10.27` of `dikeckaan/mu300-linux-mirror` came in 370 ms with 11 zips, the one for Ubuntu 24.04 on 7.2 with
  the release's size and SHA-256; its 3 parts (119,429,644 bytes) came in 32.4 s (3.5 MiB/s), each and the whole
  checked; the push and the device's own check took 7 s; the plan (`dry_run=1`, `format=0 update=1` over the
  installed Ubuntu) ended with status 3, nothing written, the device's files cleaned up. *Not measured:* GitHub's
  limits on such use (no throttling was seen in that one download), and a mirror branch that is missing or
  incomplete for a release on the real host (the stand-in server's cases above).
* *Last: the user downloads the zip* (an ordinary download, which no CORS rule stops) and picks it; the page reads
  the zip's directory and `mu300/manifest` in the browser and refuses a wrong one before anything is sent.
* The Magisk zip is the unit, not the separate assets: it holds the installer of its own release, and its payload is
  stored uncompressed, so nothing is unpacked twice. Two systems are two zips, one after the other, as in the Magisk
  app (measured: Ubuntu 24.04 and OpenWrt with the panel, two downloads and two runs, 92 s).

**3. WebUSB per platform.** Chromium only (Chrome, Edge, Opera, Brave; not Firefox, not Safari), on https or
localhost. The page runs under its Content-Security-Policy with no violation; `fetch()` to another host than
`api.github.com` is refused by that policy (checked).
* *Any system:* one program at a time can claim the adb interface. A running adb server has it, and so has a second
  browser window or tab with the page connected - during the run the owner's own Chrome had the page open, and
  every other client failed. `claimInterface` fails (`NetworkError` in Chrome, `LIBUSB_ERROR_ACCESS` in Node), which
  the page reports as "another program is using the device's adb interface: an adb server, or another browser
  window" within 0.3 s (measured in Chrome with an adb server running).
* *macOS:* nothing to install (measured: Chrome 155). Chrome's device chooser cannot be driven by a script: the
  DevTools protocol's `DeviceAccess` domain raised no event for `navigator.usb.requestDevice`, headful or headless.
  A permission a profile holds is in its `Preferences` (`usb_chooser_data`) and can be written there for a test;
  `navigator.usb.getDevices()` then returns the device, and the page offers it as "Connect to F50" without a
  chooser - the same way a user's second visit goes. The chooser lists the unit as "F50" in Android (`19d2:1353`)
  and as "MU300 Linux USB Ethernet" in Linux (`0525:a4a1`): two devices to the browser, each allowed once.
* *Windows:* WebUSB needs the interface bound to WinUSB. AOSP's adbd carries the Microsoft OS descriptor that asks
  for it (compatible ID `WINUSB` in its FunctionFS descriptors), and our Linux adbd announces the same (§43), so a
  stock Windows 10/11 should bind it without a driver. **Unknown:** whether ZTE's firmware leaves OS descriptors on
  in its gadget, and whether a ZTE driver package claims the interface first; no Windows host was used.
  Google's USB driver is WinUSB and works with WebUSB; Zadig can bind WinUSB to the one interface. `open()` then
  fails with `SecurityError`/`NetworkError`, which the page explains per platform.
* *Linux:* the device node is root's unless a udev rule says otherwise (distributions' `android-udev` rules cover
  known vendor ids, not necessarily this one). The page shows a rule that matches the adb interface by class
  (ff/42) with `uaccess`. A snap or flatpak browser may need its own USB permission. Not measured.
* *Android Chrome* has WebUSB as well, so a phone with an OTG adapter could run the page. Not built for and not
  tried: the phone would have to power a battery-less F50 for the whole installation.
* *The bootloader's word, measured on the F50:* `ro.boot.verifiedbootstate=orange`, `ro.boot.flash.locked=0`,
  `ro.boot.vbmeta.device_state=unlocked`: the page shows "unlocked". Whether a U30 Air sets them is not known: the
  page shows "not reported" when none is set. **A locked bootloader is not an obstacle** (the owner's correction,
  2026-10-13): a device with a patched TrustOS starts the modified image with the bootloader locked. The page showed
  "locked" in red; it now shows it in the warning colour with the question "Did you patch TrustOS?" (with it Linux
  boots; without it the device goes back to Android by itself after the install), beside the device's facts and
  beside the plan, and blocks nothing. Not measured: a locked device (the test unit is unlocked).
* *Root on a device without a screen, measured on the F50:* with Magisk's grant for "Shell" (uid 2000) in place,
  `su -c 'id -u'` answers in 50 ms. With the grant taken away, Magisk asks on a screen nobody sees, waits 10 s and
  says "Permission denied"; the page then shows "not granted" and how to allow Shell (the Magisk app through scrcpy,
  which needs adb, so `adb kill-server` afterwards). Magisk keeps its last answer for a uid for about three seconds
  *from the last request*: asking again every 3 s got the old "no" for a minute after the grant was back, so the
  page says to wait a few seconds before "Try again". Not rooted at all (no `su`): reasoned from the code only.

**4. What a closed tab or a pulled cable leaves.** The installation is not the page's: it is the Magisk zip's own
installer (`mu300/install.sh`), started by `tools/android-web.sh` as a job in a session of its own (`setsid`, output
to a file, HUP ignored). The page only watches (`follow`), and a watcher that goes away - tab closed, cable pulled on
a U30 Air, computer asleep - changes nothing; a new connection reads the same log from its start. *Measured on the
F50, under Magisk's `su`:* the Node client ended (nothing closed) 4 s into "systems" of an OpenWrt installation,
and 5 s into it for Ubuntu; in Chrome the tab was closed during "Collecting the Wi-Fi and modem files". Each time
the job went on: a new connection found it `running` at step 6 and followed it to the end, or found it `done` with
status 0, and the log was there from its first line (`MU300-INSTALL-OK`, "Writing and verifying boot_b"). The device
then started the installed Linux. On an F50 a pulled cable is a power cut, as it is for the installer for
computers. What is left, by stage (the installer prints the stage, `MU300-STEP n/9 name`, and the page shows this
sentence beside it):

| stage | written so far | the device then |
|---|---|---|
| check, unpack, plan, vendor, image | nothing on the eMMC or the card (files in `/data/adb` only) | boots Android; `clean` removes the files |
| systems | the Linux filesystem, unfinished | boots Android: boot partitions and misc untouched. Run it again |
| boot | the Linux slot's boot partition, never Android's | boots Android: the image is written, read back from the medium (`boot_readback`, §50) and only then is misc armed |
| arm | 32 bytes of misc, read back; the old block is written back when they do not verify | Android's block or the trial block |
| done | Linux armed for a trial | a Linux that does not finish starting falls back to Android (§17) |

The order and the checks are the Magisk installer's, unchanged; the page adds no write of its own to a block
device (it composes no `dd`: `tests/test_web_installer.py`). Cancelling is offered only before "systems". The
uninstaller (`android-web.sh`, in uninstall.sh's order: misc, then the boot partition, then the erase) is safe to
cut anywhere for the same reason (measured: a quick uninstall, 7 steps in 5 s, `boot_b` a copy of `boot_a`).
* *Two systems and a closed tab.* The second zip is the page's to send, so a page closed during the first run
  leaves one system installed, completely. The first run is started with `more`, and a page that finds the job
  says "the second system was not installed" instead of only "Linux is installed".
* *A finished run nobody watched* is shown once at the next connection (its log, then "Linux is installed" with the
  restart button), and its files (the zip in `zips/`, 39 to 124 MB, with `x/` and `job/`) are removed then.
* *Not measured:* the stall guards of §50 through this path, a cable pulled from a U30 Air, a power cut.

**Where root writes on Android, and how much.** `android-web.sh` runs as root and is handed files by the adb
user, in `/data/local/tmp/mu300-web`. The first version wrote there as root too: the download (`wget -O`), the
copies of a backup (`out/`, made readable for adb's file service), `rm -rf` of both, a `chown`. Whoever can write a
directory can put a link at any name in it, and root then writes, truncates, chmods or deletes the link's target.
Now root touches nothing there. A pushed file is moved into `/data/adb/mu300-web` (mode 700, root's; a rename takes
the name as it is and follows no link) and judged there, where nobody else can change it: a regular file, not a
link, not larger than its kind can be, with the checksum that was asked for. The download, the backup's copies, the
answers, logs and the job's state live in root's directory only; the page reads a copy of the backup as base64
from `android-web.sh cat NAME` and removes what it pushed itself, unprivileged. The uninstaller, which tidies
`/data/local/tmp` after the installer for computers, removes single names (a link goes as a link) and walks no
tree. *Measured on the F50 after the change:* a backup (ten files, checksums equal), a plan from a pushed zip and
one from a zip the device downloaded, and nothing owned by root in the adb user's directory afterwards. What
stays: the device scripts are run from that directory (the page checks them against the site's checksums before it
pushes them); the adb user is the one who asks `su` for root, so this is its own power.
* *Bounds.* `/data` is Android's own; a full `/data` can stop Android from starting. The first version checked a
  download's size after `wget` had ended, so a server that sent more, or never stopped, filled the storage first.
  Now: nothing starts unless the rest of the file leaves 512 MiB free (the reserve the Magisk installer insists
  on); the downloader runs under a file size limit of the release's size (`ulimit -f`: the kernel refuses the
  write that would cross it) and a watch that ends it when the file is larger; it ends after an hour whatever the
  other end does, and the question "can you reach GitHub" after 30 s; a pushed zip may have 300 MiB, an extra 100,
  the answers 64 KiB; a zip is unpacked only when the files it is asked for say they hold at most 64 MiB and leave
  the reserve; a job's log stops growing at 8 MiB while the job goes on. Tested with a downloader that writes 5 MB
  for a file of 100 000 bytes (the file stopped at that size rounded up to a block), one that never ends, one that stalls, and a full
  storage (`tests/test_android_web.py`, `Bounds`; the links: `Links`).

**The device side, for a caller that is not Magisk** (in every zip from v2026.10.24 on): `MU300_ANSWERS=FILE`
(the settings of the run from that file alone, which must be root's), `MU300_PROGRESS=1` (`MU300-STEP`, `MU300-PLAN
key=value`), `mu300/extras/` (the VPN module), `MU300_ADB_KEY` (trusted only). Zips of v2026.10.23 and older do not
have them, and the page refuses those releases. *Measured on the F50:* a password given on the stdin of
`su -c '... android-web.sh password'` arrived (the plan said `password=given`, root's entry in the installed
OpenWrt's `shadow` held a hash) and was in no line of the log; without one, Ubuntu has `ubuntu` and OpenWrt's root
none. For Linux the page needs no key since §70 (adb on and open by default); it reads `mu300-device --json`
(docs/ADB-INTERFACE.md) and offers "only this browser" as a choice, off by default, which sets the installed
system to authorised keys with the browser's key (per system: a second system added without the choice was open).
* *"Restart into Android" is `mu300-next-boot android`*, which makes Android the default boot from then on, not
  for one start. The page said "the next system to start"; it now says what it does and has "Make Linux the default
  again" (`mu300-next-boot linux`) in its Linux view, and the wizard proposes Linux as the default every time
  instead of taking over an "Android" that only the way to the wizard had set.

**Privacy.** The page reads ten named properties and never a serial number property; serials come from the USB
descriptor and are shown masked. Every line a device prints is masked where it enters the page (`device.js`,
`privacy.js`: serials, 14-20 digit numbers, phone numbers, MAC addresses, values named password/PSK/SSID/IMEI,
password hashes, keys), on screen and in the saved log. *Measured on the F50:* 508 lines of kernel and system log
read through the page had no MAC address and no 14-20 digit number left; the page's log of an installation (160 to
290 lines) had the serial masked. The backup takes the Linux slot's boot image and boot chain, misc and the
partition table (measured: ten files, none of them an NV, calibration or identity partition; `partitions.txt`
holds their names only); `android-web.sh` refuses those partitions by name. A password goes to the device on the
stdin of a root command, never in a command line or a file the adb user can read. The page's policy (CSP) allows
connections to this site and `api.github.com` only (and `raw.githubusercontent.com` once a mirror is configured),
and it loads no web fonts. The device's own download goes from the device to GitHub.
* **Tested** (no device): `tests/web/*.test.mjs` (the adb client against a scripted adbd with garbled packets,
  refused files, a pulled cable and a lost header; the wizard's rules; the device classes with a device that
  prints serials, IMEIs and passwords, and with hostile names; the mirror with changed, short and missing parts, a
  hostile manifest and a redirect), `tests/test_android_web.py` (android-web.sh on the fake device under busybox:
  the download with a `wget` that breaks, is sent elsewhere, brings another size or has no network; and the page's
  code end to end through a scripted adbd), `tests/test_magisk_installer.py` (`WebCaller`),
  `tests/test_web_installer.py` (strings in three languages, the pages' policy and the mirror's switch, the staged
  site, the mirror tool and the page's reader on the same files). In a browser without a device: the three pages
  and the whole wizard with made-up answers (`?demo=android`, `installed`, `small`, `linux`).

### 74. The U30 Air's second SIM: what two units showed, and the selector built on it (PR #73/#166, issue #194)

PR #73 (Snrat) brought a cold start of either card and a live switch between them, worked out on one U30 Air with
two cards (OpenWrt 25.12.5, Linux 7.2.9; its SIM1 without data service, its SIM2 working). #166 is that work with
the review's fixes, merged with #72's shared selector. On 2026-10-13 it ran on the maintainer's U30 Air (OpenWrt
25.12.5, v2026.10.23, Linux 7.2.10), which turned out to have a second card too, the other way round: SIM1 with
data, and in position 2 a card that registers for emergency service only. `docs/U30AIR-SIM2.md` is the user's
page; this section is what was measured and what was decided from it. Not run on kernel 5.4, on an F50 or on an M3.

**What the modem does**

| | maintainer's unit (7.2.10) | contributor's unit (7.2.9) |
|---|---|---|
| channels | slot 0: nr0 (URCs) / nr1 (commands) / nr2 (data), bearer `sipa_eth0`; slot 1: nr3 / nr4 / nr5, `sipa_eth8`; nr6/nr7 belong to slot 0's panel pool | the same |
| the second group's ttys | exist before they work: `spipe_open` gives `ENODEV` until `/dev/sipc_sbuf` (the driver's seqfile) shows `sbuf_5_006, state: 1,`. All four owners wait for that line, inside their procd instances | found there |
| `AT+CPIN?` on nr4 at a cold boot | `+CME ERROR: 10`, at every boot, for ten seconds of asking. One second after `AT+SPACTCARD=1;+SFUN=2` (the card's SIM power): `+CPIN: READY`, a CCID of its own, an IMSI. With SIM1's data up meanwhile: SIM1 noticed nothing (`+CFUN: 1`, both contexts active). `AT+SPACTCARD=1;+SFUN=3` puts the position back to `+CME ERROR: 10` | `READY` at once |
| what `+CME ERROR: 10` therefore means | "no card, **or SIM power off**". The modem seems to power at boot the cards Android had in use; this unit only ever used SIM1 | (after `SFUN=5`/`3` an inserted card says the same there) |
| `AT+SPACTCARD` | `AT+SPACTCARD?` answers the channel's own card: 0 on nr1/nr2, 1 on nr4/nr5. `AT+SPACTCARD=<n>;+<command>` addresses the command of that line. A line with `AT+SPACTCARD=0` or `=1` alone changes nothing: the answer to `?` stays, and so does the card the channel reads (compared by CCID, never printed) | sent `AT+SPACTCARD=0` alone "to reset the channel" |
| work modes | `+SPTESTMODE: 134,134,0,19,3,1` (mode of slot 0, of slot 1, primary). The Locks page writes the first | assumed `134,134` |
| the data route | `AT+SPSWDATA` on a card's data channel gives it the packet-data route, `AT+SPSWDATA?` answers `+SPSWDATA: 0` or `1`. After a SIM2 boot (route 1) and a Linux restart into SIM1 it read 0 again: this firmware does not keep it over a restart | not read |
| cold start of SIM2 | 16.2 s `AT+SMMSWAP=0`, 20.8 s SIM power, 22.3 s `AT+SPTESTMODEM=134,134`, 23.3 s `AT+SPSWDATA` (read back: SIM2), 23.6 s `AT+SFUN=4`, **24.2 s `+CFUN: 1`**. Then `+CEREG: 2,8` (emergency service only), `+CGATT: 0`, no bearer | CFUN=1 at about 21 s, WAN on `sipa_eth8` |
| cold start of SIM1 through the same path (live switching on) | `+CFUN: 1` at 21.2 s, data at 26.5 s | at about 22 s |
| live switch, the target's radio on first (the factory's order, the PR's first sequence) | **does not work**: `AT+SPACTCARD=1;+SFUN=2` OK, then `AT+SFUN=4` on nr4 never answered (8, 12 and 30 s waited), SIM1 lost its radio meanwhile (`+CFUN: 0` on nr1), and after the way back nr4 did not read `+CFUN: 0`, so the result could not be verified | worked in both directions |
| live switch, the card in use off first | works, both directions, every command answered within a second: `AT+SPACTCARD=0;+SFUN=5`, `;+SFUN=3` (SIM1 off, 1 s), `AT+SPACTCARD=1;+SFUN=2`, `AT+SPSWDATA` on nr5, `AT+SFUN=4` on nr5 (SIM2 `+CFUN: 1` 3 s after the start); the same back, SIM1 registered 5 s later, `ifup wan` up in 2 s | not tried |

**What was decided**

* **One model: one card's radio on at a time.** kanoqwq's fork (clean-tf-7.2 `25f8d0ce`: `mu300-dual-radio`,
  `mu300-data-sim`) powers both stacks at boot and moves only the data route (`AT+SPSWDATA`, about 1.4 s, no
  restart). Its boot step fails when the second card is absent or locked, and then neither card gets a radio; its
  own test unit's SIM2 was unpaid, so data over `sipa_eth8` that way is unproven; here the second radio would not
  even come on beside the first. Taken from it: the read-back of `AT+SPSWDATA?` as the verification of the route,
  the work modes read and written back instead of invented, a card named in every command
  (`AT+SPACTCARD=<n>;+...`), and the three commands kept out of the panel's AT terminal (below).
* **The live switch is "the card in use off, then the other one on".** It is the cold start's situation, one card
  coming on while the other is off, which both units have shown; the factory's order needs something this unit
  does not have. On the contributor's unit the new order has not been run.
* **`+CME ERROR: 10` is not believed before the SIM power has been on.** The cold start and the live switch both
  switch it on to ask (`AT+SPACTCARD=<n>;+SFUN=2`), and off again (`;+SFUN=3`) when no card answers or it is locked.
  The live switch asks before it touches the connection in use: an empty or locked target is refused in a second,
  the WAN never down.
* **The work modes are the modem's own**, read (`AT+SPTESTMODE?`) and written back as they are
  (`AT+SPTESTMODEM=<m0>,<m1>`): a network mode locked on the Locks page is not replaced by a start. `134,134` only
  when the modem does not say.
* **Every failure ends on SIM1 with AT, by itself.** The table below. Two of the ways out are a restart of the
  device, because nothing else brings the data back: a radio that was told to start the other card and did not, and
  a radio left in an unknown state. A restart lands on the saved boot default, which no failure ever leaves on the
  card that failed. `network.wan.sim_restart '0'` turns the restarts off (the state then says "reboot required").
* **A second card has to show data once.** The first time SIM2 is the boot's card it gets
  `network.wan.sim_data_wait` seconds (300; `0`: no check) from the radio coming on to have an address on
  `sipa_eth8`. With data it is written to `/etc/mu300/sim-data-seen` and never checked again: an outage is not the
  card's failure. Without, the settings go back to SIM1 (reason `no-data`) and the device restarts. Whether SIM1
  has data is not asked. The reason: a card chosen over the device's own mobile data (ours is reached through a VPN
  over it) that registers and gets no data would keep the device off the network until somebody walked up to it;
  and a user whose SIM1 has no data either is at the device, reads the reason on the page, and loses a restart.
  No verdict on a card nobody was dialling: the wan taken down by hand, switched off in the settings, or suspended
  by the power profile. "Taken down" is netifd's word (`autostart: false`), not `mobile-data`'s marker
  `/run/mu300-mobile-data-down`: every failed dial goes through a teardown that leaves that marker for a moment, and
  a check that looked in that moment kept a card without data (measured, on the second of two identical boots).
* **Issue #194's unit** (two built-in cards, SIM1 China Telecom registered without a data plan, SIM2 China Mobile
  working, kernel 5.4). "SIM1 is there" is never taken for "SIM1 is usable": a boot with SIM2 chosen does not touch
  SIM1's stack at all, a SIM2 that gets data is remembered and from then on kept through any outage, and nothing
  ever moves the device to SIM1 because SIM2 "has no data right now". In the live switch the same distinction is
  made at the moment of switching: a target without data sends the radio back only when the card in use *had* data;
  when it had none either, the target stays (`no_data_kept`), netifd keeps dialling it, and the boot default is not
  saved on a card that showed no data. Our unit is that unit mirrored, and both branches ran on it.
* **A dial that waits for a card the radio is leaving ends at once** (`wait_registered` looks at the switch
  marker). Measured before: it held the bring-up lock for its 60 s, and the card the radio went back to stayed
  without data for 32 s after the switch was over. And netifd's first dial of a dual-SIM boot **waits for the cold
  start** instead of failing and coming back 20 s later (data 39 s into the boot before, 26.5 s after).

**Failures, and where the device ends** (U: measured on the maintainer's unit; T: unit tests only)

| what goes wrong | reason on the page | where it ends | |
|---|---|---|---|
| the settings cannot be read, the marker cannot be written, bash is missing | `invalid-*`, `not-startable` | a SIM1 boot, at once: `init.d/mu300-atd` never returns without AT owners | T |
| the readiness line never appears (another kernel's seqfile) | `brokers-missing` | this boot: gives up at 104 s, the AT service starts over as SIM1's, radio on at 127 s, data at 132 s | U (the line's text changed by hand) |
| no card answers with its SIM power on; a PIN; a card that is not the recorded one | `no-sim`, `sim-pin`, `wrong-card` | this boot: SIM1's ordinary warm-up through the owner of nr1 that is already there (10 s later than a plain boot) | T; U with the earlier rule, which took the unpowered card for none |
| the radio was told to start SIM2 and does not come on | `no-radio`, `data-route`, `modem-refused` | restart into SIM1 (not before 120 s of uptime, so that the boot was marked good) | T |
| the cold start dies, the device loses power in it | `unconfirmed` | the next boot is SIM1's (the pending marker) | T |
| SIM2's radio is on, no data within the time, never had any | `no-data` | restart into SIM1: with 150 s set, 174 s into the boot (with 60 s: decided at 86 s, restarted at 120 s); SIM1's data 31.4 to 31.8 s into the next one, the VPN's exit address back | U, twice |
| the same, but the connection was off (taken down, suspended, disabled) | - | nothing: no verdict on a card nobody was dialling | T; netifd's flag read by hand on the unit |
| live: the target has no data, the card in use had | result `no_data` | back on the card in use: 3.5 s to switch, 60 s of waiting, 4 s back, WAN up 2 s later; default unchanged | U |
| live: no data on either | `no_data_kept` | stays on the target; its data came 6 s later by itself; default unchanged until `switch` is asked again | U |
| live: a command is refused half way | `rolled_back` | back on the card in use | T |
| live: the channel or the radio lock is busy | `failed` | nothing was sent; WAN up again | T |
| live: the way back cannot be verified, the modem is silent, the deadline (300 s) | `restarting` | restart into the saved default, 20 s later: data back about 75 s after the failed switch | U (with the first sequence) |
| live: the controller is killed (`SIGKILL`) | `restarting` | its guard declares the radio unknown within 5 s; restart; data 26.5 s into the next boot | U |

**Who else talks to the modem meanwhile.** The switch holds a kernel `flock` on `/run/mu300/sim-control.lock`
(gone with its holder: no stale lock; a second request answers "SIM control is busy" at once), runs its commands
under `mobile-data`'s radio lock (the dial's radio-on, the watchdog, the Locks page's SFUN restart), and while they
run `mu300-at` tells every other client "busy" in the words they already handle (SMS, USSD, the panel's terminal
and collectors): `/run/mu300/sim-sequence`, believed only while the lock is held, so a killed switch closes nothing
(measured: `AT` answered 5 s after the kill). Lock writes, the modem reset and suspend are refused in a dual-SIM
boot. Nothing from a caller reaches an AT command: the arguments are one of six fixed pairs, and every command is
built from the two slot numbers; the work modes read from the modem go back out only as two numbers of at most
three digits.

**The panel's AT terminal** refuses `AT+SPACTCARD=`, `AT+SMMSWAP=` and `AT+SPSWDATA` (its `?` forms pass), on every
device and in any spelling, as kanoqwq's does: they move the data route under a connection that then answers
`CONNECT` and loses every packet. `AT+SPTESTMODEM=` asks for confirmation like `AT+SPTESTMODE=`.

**What is written into the modem.** Nothing else is sent.

| command | what it changes | kept by the modem | put back |
|---|---|---|---|
| `AT+SMMSWAP=0` (nr1) | the RIL handshake | the same command every boot sends on the SIM1 path | nothing to put back |
| `AT+SPTESTMODEM=<m0>,<m1>` (the card's data channel, cold start only) | the two work modes: the values just read, so nothing; `134,134` only when they cannot be read | yes (NV) | not needed; with unreadable modes the earlier ones are not known |
| `AT+SPSWDATA` (the card's data channel) | which card carries packet data | not over a restart (measured) | by the cold start or switch for SIM1; and a plain SIM1 dial asks `AT+SPSWDATA?` and takes it back while `/etc/mu300/sim-data-route-2` exists (left when the route was given to SIM2). Without that mark nothing is asked |
| `AT+SPACTCARD=<n>;+SFUN=2` / `3` / `5`, `AT+SFUN=4` | SIM power and radio of one card | no | by the next boot; the switch and the cold start switch off what they switched on and could not use |

Nothing writes a PIN, an IMSI, a band or a cell lock. A dual-SIM boot does not replay the Locks page's settings
(they stay in the modem's NV; only the replay's own restart is left out).

**Nobody who does not use it.** `init.d/mu300-atd` reads the settings on a U30 Air only; with the default (slot 0,
live switching off) it starts the same three instances as before, and a boot with the branch's files had the
handshake at 24.6 s and data at 31.7 s (24.1 and 31.2 before). `mu300-sim active`, which every AT client asks
before every command, answers a pinned 0 from one file read again (2.8 ms; with the library and the device's name
read first it was 6.7 ms). `mobile-data` asks the modem for the data route only where the mark is. `mu300-at`'s gate
is one file test. The WAN's teardown now takes the bearer's name from netifd (`ifdown`/`ifup` on SIM1: address gone,
up again in 5 s).

**Privacy.** The cold start reads the CCID to compare it with `/etc/mu300/sim2-iccid` (a file only the owner
creates) and never prints it; the logs (`/run/mu300/sim2-cold-start.log`, `sim-switch.log`, mode 600) hold the
commands sent and no answer; status, the page and the fallback reason carry words from a fixed list.
`/etc/mu300/sim-data-seen` holds slot numbers.

**Not verified.** Data on `sipa_eth8` under this tree's dial on our hardware (our second card has no service; the
contributor saw it on his unit with the earlier revision). The new switch order on a unit with two working cards.
Kernel 5.4, which issue #194's unit runs: whether its `/dev/sipc_sbuf` reads the same line (the same vendor driver;
if not, the `brokers-missing` row above is what happens). A truly empty position and a PIN-locked card with the
current rule, on hardware. The restart after `no-radio` (the `no-data` restart, which is the same code, ran). The
F50: unit tests, and the default path on the U30 Air. An M3.

### 85. An update keeps everything the user made

The owner's requirement: people must be able to update to a new release without losing any data, in any way - by
`mu300-update apply`, by the computer installers' **update**, and by a Magisk zip installed over what is there.
Until v2026.10.27 an update kept a list of places (`keep_list`: `/etc/mu300`, `/etc/ssh`, home directories,
`/usr/local`, OpenWrt's `/etc/config`, a few more), the accounts, and the packages added on the device (installed
again at the first boot, §32c); the image replaced everything else. **Measured in
containers only: no device was free for this work.** The protocol for a device is docs/update-device-test.md.

**What was lost, measured.** `tests/update-experiment` installs a published image into an ext4 filesystem, plants
user state in it (67 kinds on Ubuntu, 52 on OpenWrt: files in every place, odd names, owners, extended attributes,
hard links, a sparse file, image files changed, deleted and of another kind, accounts, a package), updates it by
the real code - the installed system's own `mu300-update apply` run inside that system (chroot), which fetches the
new release's updater from a local server as on a device, and the install loop of `tools/android-install.sh` under
mksh with toybox's commands and the one true awk first on `PATH`, as on Android - and compares every attribute.
The two columns "before" are v2026.10.23 updated to v2026.10.25, both as published; the two columns "after" are
the same old system updated with this change (what the new release is there: see "After the change" below). A row
is *lost* when what the user had is nowhere in the new system, *changed* when it is there with another attribute
or is back after a deletion, *set aside* when it is not in its place but saved. Ubuntu 24.04:

| item | before: `mu300-update apply` | before: installer, Magisk zip | **after:** `mu300-update apply` | **after:** installer, Magisk zip |
|---|---|---|---|---|
| files with odd names (space, newline, leading dash, UTF-8, backslash, glob characters, 250 characters, quotes, $(...), tab) | kept | kept | kept | kept |
| modes and owners: 0000, setuid 4755, a sticky 1777 directory, a 0700 directory of uid 1000, a file of an id no account has (4242:4343) | kept | kept | kept | kept |
| extended attributes: user.*, a file capability (cap_net_bind_service), a POSIX ACL on a directory, trusted.overlay.opaque on a directory (a container layer) | kept | changed: extended attributes gone | kept | kept |
| three names of one file (hard links), two of them in one directory | kept | changed: hard link broken | kept | kept |
| a sparse file (256 MiB long, one block of data) | kept | changed: no longer sparse | kept | kept |
| symbolic links: relative, absolute, dangling, to a directory; one with its own date | kept | kept | kept | kept |
| a FIFO and a character device node | kept | kept | kept | kept |
| a socket file (a program makes it again when it starts) | kept | kept | not carried, by design | not carried, by design |
| modification times: a file (with nanoseconds) and its directory, from 2001 | kept | kept | kept | kept |
| 2000 small files in 20 directories | kept | kept | kept | kept |
| read-only files (a git object, mode 0444) | kept | kept | kept | kept |
| a swap file (/swapfile, 8 MiB, mode 0600) | lost: gone | lost: gone | kept | kept |
| /tmp and /var/tmp | not carried, by design | not carried, by design | not carried, by design | not carried, by design |
| the mount point of another filesystem (/mnt/usb): the directory | lost: gone | lost: gone | kept | kept |
| what is on that other filesystem (it stays there) | not carried, by design | - | not carried, by design | - |
| /etc/mu300: hotspot and VPN settings | kept | kept | kept | kept |
| /etc/hosts with a line added (an image file, modified) | lost: the image's file instead | lost: the image's file instead | kept | kept |
| one of the project's own programs, edited (/opt/mu300/bin/mu300-wifi): the new release's must win, the edited one must not be thrown away | lost: gone | lost: gone | kept | kept |
| /etc/netplan/60-user.yaml | lost: gone | lost: gone | kept | kept |
| /etc/wireguard/wg0.conf (0600, in a 0700 directory) | lost: gone | lost: gone | kept | kept |
| a hand-written systemd unit, enabled | lost: gone | lost: gone | kept | kept |
| a drop-in for an image unit (/etc/systemd/system/ssh.service.d/override.conf) | lost: gone | lost: gone | kept | kept |
| a masked unit (a link to /dev/null in /etc/systemd/system) | lost: gone | lost: gone | kept | kept |
| an image service the user disabled (mu300-telnetd) | changed: back | changed: back | kept | kept |
| an apt source and its key (/etc/apt/sources.list.d, /etc/apt/keyrings) | kept | kept | kept | kept |
| a user's crontab (/var/spool/cron/crontabs/ubuntu, 0600) | lost: gone | lost: gone | kept | kept |
| /etc/cron.d/backup | lost: gone | lost: gone | kept | kept |
| a service's data directory (/var/lib/docker: a layer, a volume, a database file) | lost: gone | lost: gone | kept | kept |
| /var/www/html/index.html | lost: gone | lost: gone | kept | kept |
| software in /opt (/opt/myapp, a program and its data) | lost: gone | lost: gone | kept | kept |
| /etc/ssh/sshd_config with a line changed | kept | kept | kept | kept |
| /etc/ssh/sshd_config.d/10-user.conf | kept | kept | kept | kept |
| SSH host keys | kept | kept | kept | kept |
| ~/.ssh/authorized_keys (0600, in a 0700 directory) | kept | kept | kept | kept |
| shell history (~/.bash_history of ubuntu and of root) | kept | kept | kept | kept |
| ~/.bashrc with a line added (an image file, modified) | kept | kept | kept | kept |
| /etc/sysctl.d/99-user.conf | lost: gone | lost: gone | kept | kept |
| /etc/sysctl.conf with a line added (an image file, modified) | lost: the image's file instead | lost: the image's file instead | kept | kept |
| /etc/update-motd.d/10-help-text deleted (an image file the user removed) | changed: back | changed: back | kept | kept |
| /etc/issue.net made a directory (the image has a file) | lost: gone, the image's kind of file instead | lost: gone, the image's kind of file instead | kept | kept |
| /etc/resolv.conf made a file (the image has a symbolic link) | lost: the image's kind of file instead | lost: the image's kind of file instead | kept | kept |
| /etc/skel made a symbolic link (the image has a directory) | lost: the image's kind of file instead | lost: the image's kind of file instead | kept | kept |
| /var/log/myapp/app.log | lost: gone | lost: gone | kept | kept |
| /var/log/wtmp and dpkg.log with entries (image files that grew) | lost: the image's file instead | lost: the image's file instead | kept | kept |
| the journal (/var/log/journal/<machine-id>/system.journal) | lost: gone | lost: gone | kept | kept |
| /etc/machine-id (written at the first boot; the image has an empty file) | lost: the image's file instead | lost: the image's file instead | kept | kept |
| /usr/local/bin/mytool and /usr/local/lib | kept | kept | kept | kept |
| /usr/lib/systemd/system/ssh.service edited in place (an image file outside /etc: the release's must win, the edit must not be thrown away) | lost: the image's file instead | lost: the image's file instead | set aside: in /etc/mu300/update-kept, in the report | set aside: in /etc/mu300/update-kept, in the report |
| a file added under /usr (/usr/share/myfonts/x.ttf) | lost: gone | lost: gone | kept | kept |
| /etc/fstab with a line added | kept | kept | kept | kept |
| /etc/hostname | kept | kept | kept | kept |
| /var/lib/bluetooth (paired devices) | kept | kept | kept | kept |
| /etc/sudoers.d/90-kaan (0440) | lost: gone | lost: gone | kept | kept |
| /etc/environment modified, /etc/profile.d/my.sh, /etc/rc.local | lost: gone, the image's file instead | lost: gone, the image's file instead | kept | kept |
| /etc/systemd/network/50-user.network and /etc/systemd/resolved.conf.d/dns.conf | lost: gone | lost: gone | kept | kept |
| a private key (/etc/ssl/private/my.key, 0640) and a CA of the user (/usr/local/share/ca-certificates) | lost: gone | lost: gone | kept | kept |
| /etc/docker/daemon.json | lost: gone | lost: gone | kept | kept |
| root's files (/root/.config/app/settings, /root/notes.txt) | kept | kept | kept | kept |
| /srv/files/document.pdf | kept | kept | kept | kept |
| data of the user's own service (/var/lib/myapp/db.sqlite, owned by a system account the user added) | lost: gone | lost: gone | kept | kept |
| ubuntu's password changed | kept | kept | kept | kept |
| a user added on the device (kaan, uid 1001) with a password and a home directory | kept | kept | kept | kept |
| a system account added on the device (myapp, uid 777: its data is owned by it) | lost: the account is gone | lost: the account is gone | kept | kept |
| /var/cache (downloaded packages) | not carried, by design | not carried, by design | not carried, by design | not carried, by design |
| a package installed on the device: its program and files (/usr/bin/userpkg, /usr/share/userpkg): installed again at the first boot | installed again at the first boot | installed again at the first boot | installed again at the first boot | installed again at the first boot |
| that package's configuration, changed by the user (/etc/userpkg/userpkg.conf) | lost: gone | lost: gone | kept | kept |
| that package's data (/var/lib/userpkg/state.db) | lost: gone | lost: gone | kept | kept |

* before, `mu300-update apply`: 3 by design, 2 changed, 27 kept, 34 lost, 1 reinstall
* before, installer, Magisk zip: 2 by design, 5 changed, 24 kept, 34 lost, 1 not planted, 1 reinstall
* after, `mu300-update apply`: 4 by design, 1 held, 61 kept, 1 reinstall
* after, installer, Magisk zip: 3 by design, 1 held, 61 kept, 1 not planted, 1 reinstall

OpenWrt:

| item | before: `mu300-update apply` | before: installer, Magisk zip | **after:** `mu300-update apply` | **after:** installer, Magisk zip |
|---|---|---|---|---|
| files with odd names (space, newline, leading dash, UTF-8, backslash, glob characters, 250 characters, quotes, $(...), tab) | changed: time to the second only | kept | kept | kept |
| modes and owners: 0000, setuid 4755, a sticky 1777 directory, a 0700 directory of uid 1000, a file of an id no account has (4242:4343) | changed: time to the second only | kept | kept | kept |
| extended attributes: user.*, a file capability (cap_net_bind_service), a POSIX ACL on a directory, trusted.overlay.opaque on a directory (a container layer) | changed: time to the second only, extended attributes gone | changed: extended attributes gone | kept | kept |
| three names of one file (hard links), two of them in one directory | changed: time to the second only | changed: hard link broken | kept | kept |
| a sparse file (256 MiB long, one block of data) | changed: time to the second only, no longer sparse | changed: no longer sparse | kept | kept |
| symbolic links: relative, absolute, dangling, to a directory; one with its own date | changed: time | kept | kept | kept |
| a FIFO and a character device node | changed: time to the second only | kept | kept | kept |
| a socket file (a program makes it again when it starts) | kept | kept | not carried, by design | not carried, by design |
| modification times: a file (with nanoseconds) and its directory, from 2001 | changed: time to the second only | kept | kept | kept |
| 2000 small files in 20 directories | changed: time to the second only | kept | kept | kept |
| read-only files (a git object, mode 0444) | changed: time to the second only | kept | kept | kept |
| a swap file (/swapfile, 8 MiB, mode 0600) | lost: gone | lost: gone | kept | kept |
| /tmp and /var/tmp | not carried, by design | not carried, by design | not carried, by design | not carried, by design |
| the mount point of another filesystem (/mnt/usb): the directory | lost: gone | lost: gone | kept | kept |
| what is on that other filesystem (it stays there) | not carried, by design | - | not carried, by design | - |
| /etc/mu300: hotspot and VPN settings | changed: time to the second only | kept | kept | kept |
| /etc/hosts with a line added (an image file, modified) | lost: the image's file instead | lost: the image's file instead | kept | kept |
| one of the project's own programs, edited (/opt/mu300/bin/mu300-wifi): the new release's must win, the edited one must not be thrown away | lost: gone | lost: gone | kept | kept |
| /etc/config/network changed | changed: time to the second only | kept | kept | kept |
| /etc/config/custom (a UCI file of the user) | changed: time to the second only | kept | kept | kept |
| /www/mysite/index.html | lost: gone | lost: gone | kept | kept |
| /www/index.html edited (an image file outside /etc: the release's must win, the edit must not be thrown away) | lost: the image's file instead | lost: the image's file instead | set aside: in /etc/mu300/update-kept, in the report | set aside: in /etc/mu300/update-kept, in the report |
| /etc/crontabs/root | lost: gone | lost: gone | kept | kept |
| /etc/hotplug.d/iface/99-user | lost: gone | lost: gone | kept | kept |
| /etc/sysctl.conf with a line added (an image file, modified) | lost: the image's file instead | lost: the image's file instead | kept | kept |
| /etc/sysctl.d/99-user.conf | lost: gone | lost: gone | kept | kept |
| /usr/share/myapp/data (added under /usr/share) | lost: gone | lost: gone | kept | kept |
| an init script of the user's own, enabled (/etc/init.d/myservice, /etc/rc.d/S99myservice) | lost: gone | lost: gone | kept | kept |
| SSH host key and authorized_keys (/etc/dropbear) | changed: time to the second only | kept | kept | kept |
| root's files (/root/.ash_history, /root/notes.txt, /root/.ssh/id_ed25519) | changed: time to the second only | kept | kept | kept |
| /etc/rc.local changed | changed: time to the second only | kept | kept | kept |
| /etc/firewall.user and /etc/nftables.d/10-user.nft | lost: gone | lost: gone | kept | kept |
| /etc/dnsmasq.conf with a line added, /etc/ethers | lost: the image's file instead | lost: the image's file instead | kept | kept |
| /etc/openvpn/client.ovpn (0600) | lost: gone | lost: gone | kept | kept |
| software in /opt (/opt/user/tool) | lost: gone | lost: gone | kept | kept |
| /etc/uci-defaults/99-user, /etc/profile.d/x.sh | lost: gone | lost: gone | kept | kept |
| /etc/sysupgrade.conf with a line added | lost: the image's file instead | lost: the image's file instead | kept | kept |
| the panel's saved locks (/etc/unisoc-modem/lock-state.d) | changed: time to the second only | kept | kept | kept |
| /etc/banner deleted (an image file the user removed) | changed: back | changed: back | kept | kept |
| /etc/banner.failsafe made a directory (the image has a file) | lost: gone, the image's kind of file instead | lost: gone, the image's kind of file instead | kept | kept |
| /etc/TZ made a file (the image has a symbolic link) | lost: the image's kind of file instead | lost: the image's kind of file instead | kept | kept |
| /usr/lib/lua/user.lua (added in a directory of packages) | lost: gone | lost: gone | kept | kept |
| /etc/apk/repositories.d/customfeeds.list changed, a key added to /etc/apk/keys | lost: gone, the image's file instead | lost: gone, the image's file instead | kept | kept |
| a kernel module built by hand (/lib/modules/6.99.0/hand.ko) and firmware (/lib/firmware/user.bin) | changed: time to the second only | lost: gone | kept | kept |
| /etc/ssl/certs/user.crt | lost: gone | lost: gone | kept | kept |
| an image service the user disabled (/etc/rc.d/S50cron removed) | changed: back | changed: back | kept | kept |
| a user added on the device (kaan, uid 1001) with a password and a home directory | lost: gone | lost: gone | kept | kept |
| root's password changed | kept | kept | kept | kept |
| a package installed on the device: its program and init script (/usr/bin/userpkg, /etc/init.d/userpkg): installed again at the first boot | installed again at the first boot | installed again at the first boot | installed again at the first boot | installed again at the first boot |
| that package's UCI settings (/etc/config/userpkg): set aside until the package is back, so that they cannot act without it | set aside: in /etc/mu300/orphaned-config | set aside: in /etc/mu300/orphaned-config | set aside: in /etc/mu300/orphaned-config, in the report | set aside: in /etc/mu300/orphaned-config, in the report |
| that package's other settings, changed by the user (/etc/userpkg/settings.yaml) | lost: gone | lost: gone | kept | kept |
| that package's data (/etc/userpkg/cache/rules.db, /usr/share/userpkg-data/geo.dat: made at run time, in no package) | lost: gone | lost: gone | kept | kept |

* before, `mu300-update apply`: 2 by design, 20 changed, 1 held, 2 kept, 26 lost, 1 reinstall
* before, installer, Magisk zip: 1 by design, 5 changed, 1 held, 16 kept, 27 lost, 1 not planted, 1 reinstall
* after, `mu300-update apply`: 3 by design, 2 held, 46 kept, 1 reinstall
* after, installer, Magisk zip: 2 by design, 2 held, 46 kept, 1 not planted, 1 reinstall

Besides the lost files, the copies themselves were not faithful where `cp -a` was not GNU's. Measured in the
container (the images' static busybox 1.36.1, Ubuntu 24.04's coreutils 9.4, Ubuntu's toybox 0.8.9 - not Android's
own build of toybox, which was not at hand):

| `cp -a` of | a sparse file (64 MiB, 8 blocks) | two names of one file | `user.*` attribute, file capability | time, fraction of the second | time of a symbolic link |
|---|---|---|---|---|---|
| GNU coreutils | sparse | one file | kept | kept | kept |
| busybox 1.36.1 | dense: 131080 blocks | one file (within one run) | both gone | cut to the second | not kept |
| toybox 0.8.9 | dense | two files | both gone (`--preserve=all`: the `user.*` one kept, the capability gone) | kept | kept |

So on OpenWrt (busybox) every kept file lost the fraction of its second and its attributes, and a sparse file was
written out in full; from Android hard links were broken as well. And the installers' update did not keep the
system it replaced at all: `rm -rf` of the old one, then the rename of the new - a run that died in between left
the kept files only in `<os>.new`, which the next run deletes first.

**The change: the question is asked the other way round.** Not "which places are the user's" but "which files came
with the image". Every image now carries the manifest of its own files, `etc/mu300/image-manifest.gz`: one line per
file, `TYPE MODE UID GID SIZE SHA256 PATH` (the hash of a link is that of its target; `tools/image-manifest.py` has the
format). With the manifest of the *old* image, everything in the old system that is not on it was made by the user
(or by software they installed), and what is on it with other content was changed by them. The new system is the
new image, plus all of that, by these rules (`mu300-update`, the block between `# --- carry begin` and `end`):

| in the old system | goes |
|---|---|
| not the image's | to its place. Where the new image has a file of that name: under `/etc /var /home /root /srv /usr/local /opt /mnt /media` the user's is used and the release's is set aside; elsewhere, and where the release has a directory, the release's is used and the user's set aside |
| the image's, changed, under those directories | the user's is used. When the new release changed that file too (a three-way conflict), the release's version is set aside for comparison. Under `/var` (logs, state) silently |
| the image's, changed, elsewhere (`/usr /bin /lib /www`: programs) | the release's is used, the user's set aside. The same for the project's own programs wherever they are (`opt/mu300`, `usr/libexec/unisoc-modem`, the `mu300-*` units and init scripts, the commands linked into `/usr/local/bin`), for a package's script in `/etc/init.d` or `/etc/hotplug.d`, for `/etc/pam.d/common-*` (pam-auth-update writes them for the packages that are there: a line for a module of a package not installed yet would lock every login out) and for the image's own apt sources |
| the image's, only owner or mode changed | given to the new image's file under the user's directories; elsewhere a mode the user narrowed is kept, and anything else is a line of the report |
| the image's, deleted | under `/etc /home /root /srv /usr/local /opt /mnt /media` it stays deleted, and so does a service's enable link (`rc.d`, `*.wants`). Back, with a line of the report: the project's own programs, a script in `/etc/init.d` or `/etc/hotplug.d`, a file whose package the old system no longer lists (it went with a package upgrade), the files of a package that was removed and is part of the image. Never touched: `/etc/uci-defaults` (the scripts remove themselves when they ran, and must run again) |
| the package manager's: its databases, `/etc/alternatives`, the files of packages | never file by file. Packages added on the device are installed again at the first boot, as before; a package's configuration file is carried as the user's, and its data, which is in no package, like everything else - nothing waits for the package but OpenWrt's UCI file, which is set aside as before so that it cannot act without its program (#116). A file that differs from the manifest because a package upgrade replaced it (dpkg's md5sums, apk's `Z:` sums say so) is not the user's and is not set aside |
| below `/proc /sys /dev /run /tmp /var/tmp /var/cache`, sockets, Ubuntu's kernel modules, `/etc/ld.so.cache`, Python's caches under `/usr` | not carried |
| on another filesystem | not carried: `mu300-carry` never leaves the filesystem of the system (by device number), and the mount point is carried as the directory it is. Through `/mnt/mu300-disk/<os>`, where the updater reads the system, nothing is mounted anyway |
| accounts and owners | `merge_accounts` as before (users from 1000 on, passwords, groups), and the rule below |

**Never less protected than the user left it.** Putting the release's file in place of the user's must not open
what the user closed. The settings that protect the device are all in the user's directories and stay the user's:
adb (`/etc/mu300/adb`, `adb_auth`, `adb_keys`: `off` or `keys` cannot become open), `sshd_config` and the project's
own drop-in beside it, dropbear, host keys and `authorized_keys`, the firewall (`/etc/config/firewall`,
`/etc/mu300/firewall.nft`, `nftables.d`), `vpn.conf` with its kill switch, `mobile-data.conf`, sudoers, sysctl, the
panel's `rpcd` and `uhttpd` settings - with their modes (0600 stays 0600: `mu300-carry` copies the mode). Beyond that:
* a service the user turned off stays off. An enable link that is gone stays gone (`*.wants`, `rc.d`), for the
  project's own services too; a mask (a link to `/dev/null` in `/etc/systemd/system`) is the user's even over the
  project's own unit; and a package the user removed, which is back because the image has it, comes back with its
  services not enabled;
* a mode the user narrowed is put on the new image's file also where the release's content is the one in use (a
  program edited and made 0700, a script made non-executable);
* an account of the new image that the old system did not have - the user deleted it, or the release added it - is
  locked, so that it cannot come with the image's well-known password; `merge_accounts` keeps a locked account
  locked, as before;
* where the release's version does end up in use (a program file, a project unit, an init script,
  `pam.d/common-*`), the report names the file.
Without a manifest (below) the same holds, by deciding for the tighter side what cannot be told: besides the places
of `keep_list`, `/etc/config`, sudoers, `sysctl`, `nftables`, `pam.d`, `modprobe.d`, `/etc/ssl/private`, the units and
links in `/etc/systemd/system` and `/etc/rc.d`, crontabs and `rc.local` are the old system's; an enable link of the
new image for a service the old system had and did not enable is removed, and so is a file in `/etc/sudoers.d` that
the old system did not have - each with a line of the report. `tests/test_carry.py` (`NeverLessProtected`) plants
each of these and looks at the new system, with a manifest and without. Found by a review of this change: an
earlier draft counted every file the project's overlay puts under `/etc` as the project's own, which would have put
the release's `sshd_config.d/10-mu300.conf` over one the user had tightened.

**A file belongs to an account, not to a number.** The numbers differ between images (Ubuntu 24.04 and 26.04 number
`messagebus`, `sshd`, `bluetooth`, `crontab` and others differently), and a wrong owner is a security fault: a
service's private file in a login user's hands, a set-user-id program under another owner. So
(`carry_accounts_plan`, before the plan and before a file is carried):
* an owner the old system has a name for is carried by that name, under the number the name has in the new
  system: the new image's when it has the account; else the old number when the new system does not use it; else
  a free one (a system account added on the device: the highest below 1000; a user `merge_accounts` brings: the
  lowest from 1000 on, with its group). Two accounts never end up with one number;
* a number the old system has no name for stays the number - unless an account of the new system has that number:
  the file would become that account's, so it is not put in place but set aside under `update-kept/.../user/`
  (root's alone), with a line of the report. It never falls to root or to "whoever has the number now";
* what gives a file the rights of its owner does not go to another number: the set-user-id and set-group-id bits
  and a file capability are taken off a file whose owner's number changes, and the report names the file. With
  the same number everything stays (bits, capabilities, ACLs);
* names of one file and directories are treated the same; by link (`--no-rollback`, the installers) a file whose
  owner's number changes is copied, so the old system's file is not touched;
* after the accounts are written, every account of the old system is held against the plan the files were carried
  for; a difference fails the update with nothing put in place.
`tests/test_carry.py` (`Owners`): a system account the new image numbers differently, the same number, an account
added on the device whose number the new image took (user and system), a number without a name that an account of
the new image has, one that is free, and a passwd that does not match the plan. A third review asked for exactly
this: the first draft mapped the accounts both images have and the system accounts added on the device, but let a
user from 1000 on share a number the new image had given away, let a number without a name become the new
account's, and kept set-id bits across the change.

What is set aside goes to `/etc/mu300/update-kept/<old release>/user/<path>` (the user's version) or
`.../image/<path>` (the release's), mode 700 - not beside the file as `name.mu300-new`: OpenWrt runs every file in
`/etc/hotplug.d` and `/etc/uci-defaults`, whatever it is called. Every such decision is a line of
`/etc/mu300/update-report`, which the update prints, `mu300-update report` shows again and a line at the next login
points to (once; Ubuntu's motd, OpenWrt's `/etc/profile.d`); earlier reports stay below the new one.

**Files are carried by a helper, not by `cp`.** `tools/carry/mu300-carry.c` (static, in every image as
`opt/mu300/bin/mu300-carry`): `scan` (one line per entry, never leaving the filesystem), `sum` (sha256), `manifest`,
and `copy`/`link`, which make a path in the new system what it is in the old one - content with its holes, owner,
mode, every extended attribute, times to the nanosecond, names of one file as one file - and never write through a
symbolic link of the new system (each directory on the way is opened without following links). The rules are shell
and awk; hashing is done only where it decides something: a file of the manifest with the same size is hashed, one
with another size is changed without it, and nothing is ever taken for the image's on its size or time alone.

**One implementation for the three paths: the new image brings it.** `mu300-update apply` and
`tools/android-install.sh` both run `busybox sh NEW/opt/mu300/bin/mu300-update carry OLD NEW OS MODE` - the new
image's own carry block, by the new image's static busybox (the same binary in all four images: `usr/bin/busybox`
on Ubuntu, `opt/mu300/bin/busybox` on OpenWrt; it prefers its own applets, so the commands are the same on Ubuntu,
OpenWrt and Android) and its `mu300-carry`. Nothing of it is copied into `android-install.sh`, and none of
Android's tools take part: what is needed there is a shell that can start a static program on the Linux
filesystem. The run must end by leaving `NEW/.mu300-carried`; a run that ends without it failed, whatever its
status (found by a test: with `MU300_LIB` in the environment the script defined its functions, left with status 0,
and the caller took that for done). An image that does not bring these parts (built by hand without the helper) is
updated the old way, with a line that says so; `MU300_UPDATE_KEEP=list` asks for the old way (kept for one release:
`mu300-update`'s environment, the zip's `/data/adb/mu300-install.conf`, the environment of `android-install.sh`).

**The old image's manifest.** A system from the first release with a four-field tag on has its own (taken only when its first line names the
release the system says it is). For the releases before that, the new image has them:
`opt/mu300/lib/image-manifests/<image>.gz`, made from the published images of v2026.09.21 to v2026.10.27 (36
releases; `tools/image-manifest.py legacy` and `union`). Two releases of one image differ in a few dozen lines, so
each file holds every distinct line once, with the releases that have it in front: 97 kB (openwrt), 101 kB
(openwrt-luci), 480 kB (ubuntu-24.04), 599 kB (ubuntu-26.04), where the manifests one by one are 30 MB. An image has
those of its own system (Ubuntu: both releases, for `MU300_UBUNTU`). They are part of the image, so they are checked
with it (the release's `SHA256SUMS`, the zip's manifest), an update needs no download for them, and a zip works
offline. Nothing has to be published for the old releases; for the record their manifests can be attached to them
(commands below). The repacked images are larger by 0.6 MB (OpenWrt) to 2.0 MB (Ubuntu): the helper (0.7 MB, static), the image's own manifest (73 to 561 kB), the older ones.
What is checked is what is used: the release the old system says it is is read once and picks the manifest; the
file is copied once into the working directory and only that copy is checked and read; a manifest whose first line
names another image or release, that is a link, or that has one line which is no manifest line (a path with `..`)
is refused whole, and the update goes on as without one. A second review of this change found the first draft
reading the old system's manifest three times (check, header, use), and three things more open than they should
be, all closed: the working directory with the lists of the user's files (now 0700), the update report (0600 from
the moment it exists; it names files under `/root` and `/home`), `update-kept` (0700 and root's, also when it came
along from an earlier update with another mode; a file in it keeps its own mode and owner), and the installers'
copy of the block's output, which was written to `/data/local/tmp` - the shell user's directory, where a planted
link would have made root write through it - and is now on the Linux filesystem.
The releases v2026.09.17 to v2026.09.20 have no `etc/mu300/image-version`, so a system installed from them does
not say what it is.

**Without a manifest** (those four releases, an image built by hand, a test build): everything the new image does
not have is carried (but the files of packages, and the project's own, which are set aside), the places of
`keep_list` and what protects the device (above) are the user's, and every other file that differs from the new image's is set aside under
`update-kept/.../user/` - the old release's own files and the user's changes alike, they cannot be told apart
(on OpenWrt v2026.10.23 that was 27 files of the old release beside the planted ones). When there is no room for
them the update goes on without, and the report says they are in the previous system. A deletion cannot be told
either: what the user deleted of the image is back (but services and sudo rules, above).

**Room, and the previous system.** `apply` keeps the old system whole as `<os>.old` for `rollback`, so the user's
files are copied, and there must be room: what is to be written plus 5 % and 32 MB against `df`. When there is
not, it says how much is needed and how much is free, removes `<os>.new` and changes nothing; `apply --no-rollback`
then carries by link - the files become second names of the old system's, no data is copied, 8 MB of margin - and
the old system goes aside as `<os>.broken`, which `rollback` does not offer and the next `apply` or `clean` removes
once it is not the running system. Never is anything of the user's deleted to make room. The installers' update
has never kept the old system; it now carries by link (no room needed) and swaps safely: old to `<os>.broken`,
new into place, then the removal, and a run that finds `<os>.broken` without `<os>` puts it back first.
`rollback` is unchanged and returns the old system exactly (below). `apply` does not go to an *older* release by
itself (`apply --downgrade`, the rule of the panel's update, §86; the zip: `MU300_DOWNGRADE=yes` from `/data/adb`
only): the update is done by the release it installs, and one from before the first release with a four-field tag keeps the list only.

**The Magisk zip.** Update was its default already (`MU300_MODE=update` when it finds a filesystem). Its plan now
says what that means - `update: <os> <old> -> <new>: everything you added to it or changed in it is kept ...`, `not
touched: <the other systems> and the extras` - and the example settings file says what `wipe` erases. The zip
carries one system and one kernel: the other systems and `extra/` are not touched (measured in the installers' runs:
every file of another system, of `extra/vpn` and of `.mu300` with its attributes before and after), the password
stays the device's (tests, as before), an older zip over a newer system is refused, and nothing is downloaded.

**After the change**, the same experiment; the new release is v2026.10.25's images repacked as v2026.10.26 with
this branch's updater, helper and manifests (`tests/update-experiment/repack.sh`: no release was built - what a
release build changes beyond that is not in these runs). The columns "after" of the two tables above: no row is
lost, and none is changed. What is set aside is the program file edited in place (the rule) and, on OpenWrt, the
package's UCI file (the rule of §32c); each is in the report. Ubuntu 26.04 and OpenWrt with the panel were run the
same way and gave the same rows as these two (in the run without a manifest the one changed row is the deleted image file, which is back). In every `mu300-update apply` run the system kept for a rollback (`<os>.old`) was compared
too: every planted item exactly as planted.

The updates that are not the plain one (`tests/update-experiment/scenarios.sh`):

| the update | the planted items |
|---|---|
| `apply --no-rollback` (OpenWrt): by link, the old system left as `openwrt.broken` | 46 kept, 2 set aside, 1 installed again, 3 not carried by design |
| Ubuntu 24.04 moved to 26.04 (`MU300_UBUNTU=26.04`): owners follow the accounts' new numbers | 61 kept, 1 set aside, 1 installed again, 4 not carried by design |
| an old system no manifest is known of (it says `dev`), `mu300-update apply` | 38 kept, 9 set aside, 1 installed again, 3 not carried by design, 1 changed |
| the same, the installers' update (Ubuntu) | 52 kept, 9 set aside, 1 installed again, 3 not carried by design, 1 changed |
| 2.5 GB of the user's where a copy does not fit: stopped, nothing changed (the old system verified) | 52 kept |
| the same with `--no-rollback` | 46 kept, 2 set aside, 1 installed again, 3 not carried by design |
| updated twice (to v2026.10.26, "rebooted", to v2026.10.27): the second update reads the first one's own manifest | 46 kept, 2 set aside, 1 installed again, 3 not carried by design |
| `MU300_UPDATE_KEEP=list`: the update as it was | 27 kept, 1 installed again, 3 not carried by design, 2 changed, 34 lost |

**On the devices (2026-10-16, `docs/update-device-test.md`).** Two releases built from this branch and never
published, v2026.10.40 (T1) and v2026.10.41 (T2): `tools/make-release.sh` with the mainline kernels built at the
branch's commit, signed with the project's key (`SHA256SUMS.sig`), the Magisk zips of T2 by `make-magisk-zips.sh`.
The mirror was on each device (busybox `uhttpd` on 127.0.0.1 on the U30 Air, `file://` on the F50: no server on the
computer), with the API files of §86 for the page's *Check*. A U30 Air (openwrt-luci, kernel 6.18.56, the owner's
VPN with its kill switch over SIM1) and an F50 (Ubuntu 24.04, kernel 7.2.10; its carrier passed no traffic without a
VPN that day, so python3, hello and tree came from files: a standalone CPython in the test directory, the two .deb
by `dpkg -i`), both on v2026.10.27, `experiment.py plant / KIND sys.json --live` (63 items on Ubuntu, 46 on OpenWrt).

| step | U30 Air (openwrt-luci) | F50 (Ubuntu) |
|---|---|---|
| 2. v2026.10.27 -> T1, terminal | "continuing with the mu300-update of T1", no "no list of the files"; carried 3456 files, 257 MB in 36 s (the whole apply); set aside: `/www/index.html` (held), `/etc/banner.failsafe` (image's in use), `/etc/banner` deleted again; python3 listed for the first boot. **The boot image was not written**: `/dev/mmcblk0p38` was a regular file of 50 MB in that boot (something had written to the path before this test; a restart makes /dev anew), and the updater refused to write to it and said so | 2588 files, 225 MB in 31 s; `/usr/lib/systemd/system/ssh.service` held, `/etc/issue.net` and `/etc/skel` (the user's in use), hello and tree listed; boot image T1 |
| 2. verify | the copy for the rollback: every item kept; the new system before the restart: 42 kept, 1 held, 3 by design | 58 kept, 1 held, 4 by design |
| 2. after the restart | 41 kept; `/etc/uci-defaults/99-user` gone (OpenWrt runs and deletes it at boot: by design); the VPN up on the same exit address; extras changed (below) | 55 kept; 3 "lost" that the booted system rewrote itself: `/etc/resolv.conf` (a link again), `/var/log/wtmp`, the planted journal file (journald set it aside as corrupt) - not the update's |
| 3. T1 -> T2 | through the panel's backend (`ubus call mu300dash update_get/update_act/update_job`, what the page calls): *Check* offered T2 with "Free space needed" 2308456 KB (planted: 257 MB), the update "signed with the project's release key", 3460 files carried, the report on the page (`report_new` 1, then 0 after `mu300-update report`); again **from a file** (the zip put where `upload_begin` said, `upload_done` inspected it: T2, openwrt-luci, k6.18, signature valid, the SHA-256 of `SHA256SUMS-magisk`) | `inspect` of the zip (signature valid, fits), `apply --from` the zip with mobile data stopped: "signed with the project's release key", no download, 2593 files, 233 MB in 51 s |
| 3. first boot | **python3 was not installed again** (below, fixed) | hello and tree wait for the internet (state offline: this F50 had none) |
| 4. rollback + rollback-boot | T1 again, everything kept but the uci-defaults script | T1 again, as in part 2 |
| 5. older release | T1 with T2 installed: refused (also with `MU300_DOWNGRADE=1`), nothing downloaded; `--downgrade`: through, everything kept | the same |
| 6. no room, `--no-rollback` | - | a 27 GB file in /srv: refused before any download ("30722 MB needed, 2559 MB free", naming clean and --no-rollback); `--no-rollback`: through, `ubuntu.broken`, rollback "no previous version kept"; after the restart the file is there, verify as before, `clean` removed `ubuntu.broken` |
| end | v2026.10.27 by `apply --downgrade --unsigned` (refused without each flag), then the system as it was before the plant | the same |

Found and fixed on this branch:
* **One dead feed kept every package from coming back on OpenWrt.** The planted `customfeeds.list` names
  `example.invalid`; `apk update` then fails as a whole ("1 unavailable", exit 1) although every other feed answered,
  `mu300-user-packages` took that for "offline", waited 300 s between tries and would give up after five boots:
  python3 never came back on the U30 Air. Ubuntu had `apt_sources_check` for the same case; apk now counts as
  online when fewer feeds were unavailable than are configured (`apk_update`; offline every feed is unavailable).
  With it, python3 was installed again at once (`test_a_dead_feed_of_the_users_is_not_offline`).
* **`experiment.py --live` replaced what the device needs**: the VPN's and the hotspot's settings (`ENABLE=0`: the
  owner's VPN off after the restart), the SSH host keys and `PasswordAuthentication no`, root's crontab (a daily
  reboot), the panel's saved band locks (applied at the next boot), and disabled cron or sysctl. With `--live` a
  file the device has gets a line of the user's, host keys and saved locks are written down as they are, and no image
  service is disabled.

Seen, not changed here:
* **The VPN module is brought to "latest" even when the installed one is newer**: v2.0.3 (a pre-release, installed
  by hand) became v2.0.1 at the first update (`module_download` compares hashes, not versions; v2026.10.27's updater
  does the same). Put back by hand afterwards.
* The report's time on OpenWrt is UTC (22:19 for 01:19 local); on Ubuntu it is local.
* When T1's and T2's boot images are the same bytes the second update says "boot: already up to date (T2)", and
  `rollback-boot` then goes back to the image before T1.
* `Deleted again` on the F50 listed `/etc/rc[2-5].d/S01ssh`: a real change on that unit (an earlier test had disabled
  `ssh.service`), not a false line.

**Part 7: the Magisk zip from Android and the computer installer (2026-10-16, a third F50).** Two more releases
built from this branch and never published, v2026.10.16.90 (T1) and v2026.10.16.91 (T2; four-field tags of the day,
#249), the same way (mainline kernels built at the branch's commit, signed, the Magisk zips of both). The F50 had a
plain OpenWrt v2026.10.27 on kernel 6.18 in its internal region (804 MiB, 613 MiB free; installed by the make-room
resume the day before), the carrier's data working without a VPN, no SD card. Planted with `experiment.py plant /
openwrt sys.json --live` (45 items; python3 from Alpine, musl, run by its own loader from the test directory, so
nothing of it is a package of the system) after `apk add nano` (a package the update has to install again).

| step | how | result |
|---|---|---|
| v2026.10.27 -> T1 | T1's `mu300-magisk-...-openwrt-k6.18.zip` by `magisk --install-module` from Android (first `MU300_DRY_RUN=1`: the plan said "update: openwrt v2026.10.27 -> T1: everything you added ... is kept") | "carrying everything of yours ... over", 2515 files, 44 MB, by link (no copy kept: 438 MiB free after); set aside `/www/index.html`, `/etc/banner.failsafe`, `/etc/banner` deleted again, nano listed. After the restart: T1, kernel 6.18.56, verify 32 kept, 1 held, 3 by design, 1 lost (`/etc/uci-defaults/99-user`, run and deleted by OpenWrt at boot), 8 changed (below); nano installed again at the first boot ("1 of 1 ... are back") |
| T1 -> T2 | `install.sh` of T2's unpacked zip (`MU300_PACKAGE`, answers mode, `MU300_ANS_EXISTING=update`) | 2082 files, 16 MB; the same verify; both reports in `mu300-update report` |
| T2 -> T1, the zip | T1's zip over T2 | refused: "The installed openwrt is T2, and this zip is T1, an older release", nothing written |
| T2 -> T1, the computer | T1's package by `install.sh` | **went through without a word** (below, fixed); with the fix: refused on the device before anything was written, "boot_b and misc were not changed"; with `MU300_DOWNGRADE=yes`: through, everything carried |

Every way kept the planted state as `mu300-update apply` does (part 2), with two differences that come from Android,
not from the carry block:
* **The 8 "changed" items** are directories, symbolic links and a FIFO the carry makes anew (only files go by link):
  made from Android, each gets `security.selinux` = `u:object_r:unlabeled:s0` from Android's kernel. Nothing of the
  user's is lost or altered (the ACL, the capability, the user attribute are all there); every file the installers
  ever unpacked from Android carries the same label, and OpenWrt and Ubuntu here do not use SELinux.
* **The password.** The zip does not keep a well-known one (`default_hash`, since issue #167): root's `ubuntu`, set by
  the computer installer, became the image's own, none ("root's password is the images' own again: none, until one
  is set"; the plan says so before). `mu300-update` keeps the hash, and `install.sh` sets the one it asks for. By
  decision, not changed here; a zip update over a device with `ubuntu` leaves root without a password.

Found and fixed on this branch:
* **`install.sh` (and `install.ps1`) took an older release.** `android-install.sh` had no downgrade check: only
  `mu300-update` and the Magisk installer had one, so the computer's installers put T1 over T2 without asking. It now
  reads each image's `etc/mu300/image-version` from its tarball (Android's toybox `tar -xzOf`, measured) and refuses
  an older release than the installed system (the release-tag order) before it writes anything; `MU300_DOWNGRADE=yes`
  in front of `install.sh` / `install.ps1` allows it, and the Magisk installer passes on its own decision
  (`DOWNGRADE` in the env file). Tests: `test_android_install.Downgrade`.
* The update texts of `install.sh`, `install.ps1` and the window still said "settings and data (/etc/mu300, users and
  home directories, SSH host keys, UCI)"; they now say that everything added or changed is kept (en, tr, zh).

Seen, not changed: run seconds after Android had booted, with `ANDROID_SERIAL` naming it, `install.sh` once found
no Android answering and, because two other boards on the computer were in Linux, offered to reboot "the device" out
of Linux (answers mode stopped at that question; a minute later the same run found Android). Answered yes it would
have stopped too: `linux-mode.sh` reboots nothing over SSH while more than one board is in Linux.

**Not run**: the page in a browser (its backend was driven), the 5.4 kernel, an SD card, Ubuntu through the zip or the
computer installer.

**Not measured, or not on a device.**
* Before 2026-10-16 nothing of this ran on an F50 or a U30 Air: not the helper on the devices' kernels (5.4 vendor, mainline) and
  under Android (a static aarch64 program started from the Linux filesystem by Magisk's root), not the time the
  scan and the hashing take on the eMMC or an SD card, not a boot of an updated system. In the containers the
  updated systems were only asked what can be asked without booting (`dpkg --audit` empty, `sshd -t`, `visudo -c`,
  no unit that does not load, the accounts; OpenWrt: `uci show` without an error, every enabled service has its
  script). The carry step of an Ubuntu system with 22 000 files and 1.3 GB of the user's took 13 s by copy and 7 s by link in the container (an Apple M-series host, measured before the last two reviews' changes); the scan of the old system alone 0.04 s, hashing a whole image 15 s. On the device's storage it will be slower, by how much is not known.
* A system that has run differs from its image in ways an unpacked image does not: files the system writes or
  removes by itself. Known and handled: uci-defaults, the package databases, `ld.so.cache`, `pam.d/common-*`,
  accounts. Others would show as lines of the report nobody caused (`Back, though you had deleted them`, `Yours is
  in use where the new release has another version`); the device test looks for them.
* No release was built. `rootfs/assemble.sh` and `openwrt/build-rootfs.sh` were run as `tools/make-release.sh` runs them, for Ubuntu 24.04 and OpenWrt, with the kernel outputs of the main checkout: both images came out with the helper, their manifest (the same as `tools/image-manifest.py` makes from the tarball) and the older manifests of their own system, and v2026.10.23 updated to these two built images gave the rows of the tables above by both paths. `make-release.sh` itself (its audit, the manifests as assets, `SHA256SUMS`), the 26.04 and panel images and `install.sh`'s source build did not run.
* What an update still does not keep, by decision: a package that cannot be installed again (not in a feed) -
  its files stay in `<os>.old`, `mu300-user-packages status` says so, as before; choices in `/etc/alternatives`; a
  kernel module built by hand on Ubuntu (OpenWrt's `lib/modules` is kept as before); what the running system
  changes between `apply` and the reboot stays in the previous system (`apply` says: reboot soon).
* Android's own toybox was not measured (Ubuntu's 0.8.9 was); it is not used for carrying any more.

**With the panel's update (§86).** Both changes rewrote `apply`; they are one now. *Every source* - GitHub, a mirror,
`apply --from` a Magisk zip or a release directory, a downgrade - ends in `apply_one`, which runs the new image's
carry block, so what is said here holds for each (measured below for online and `--from`). *One word for an older
release:* §86's `downgrade_ok` and `--downgrade` (`MU300_ALLOW_DOWNGRADE`); this change's own `MU300_DOWNGRADE`
variable of `mu300-update` is gone before it was ever released (the zip's `MU300_DOWNGRADE=yes` setting stays the
zip's), and the refusal now says why it matters: the older release's updater may not carry everything over. *One
rule for room:* `space_needed N [CARRY_KB]` is what `apply` refuses with before it downloads and what the page shows
(`status --sizes`, `releases`); `carry_need` adds the copy of the user's files kept for a rollback - the old system
less its image's files as its manifest has them, with the carry's margin - and nothing for `--no-rollback` or for a
system whose image's manifest is not there before the new image is (every release up to v2026.10.27: the first
update to a release with this is counted only by the carry block's exact check after the unpack, which changes
nothing when it fails - measured below). *The report on the page:* System > Update shows `/etc/mu300/update-report`
as the carry block writes it, the newest update on top, cut at 6000 bytes with where the rest is, open while it is
new. The manifests of v2026.10.26 and v2026.10.27, published while this waited, were added (36 releases of each
image); one published before this is merged needs the same (`tools/image-manifest.py legacy`, `union`).

**On a release build** (2026-10-15: `tools/make-release.sh` from the branch under a three-field test tag after v2026.10.27, not published, signed with
the project's key; 5.4 and the mainline kernels of v2026.10.27; the Magisk zips by `tools/make-magisk-zips.sh`).
The experiment from v2026.10.27 as published, now with a third path - the old system offline, given the new
updater as a user of a release before `apply --from` does it, then `mu300-update apply --from` the release's zip of
its system (`--unsigned`: v2026.10.27 has no key to check with) - `tests/update-experiment/results/built-*.md`:

| image | `mu300-update apply` | installer, Magisk zip | `apply --from` the zip |
|---|---|---|---|
| Ubuntu 24.04 | 61 kept, 1 set aside, 1 installed again, 4 by design, **0 lost** | 61, 1, 1, 3, **0 lost** | 61, 1, 1, 4, **0 lost** |
| Ubuntu 26.04 | 61, 1, 1, 4, **0 lost** | 61, 1, 1, 3, **0 lost** | 61, 1, 1, 4, **0 lost** |
| OpenWrt | 46 kept, 2 set aside, 1 installed again, 3 by design, **0 lost** | 46, 2, 1, 2, **0 lost** | 46, 2, 1, 3, **0 lost** |
| OpenWrt with the panel | 46, 2, 1, 3, **0 lost** | 46, 2, 1, 2, **0 lost** | 46, 2, 1, 3, **0 lost** |

Nothing *changed*; the copy kept for a rollback (`<os>.old`) was the old system in every planted item, by both
device paths; the other system and the extras beside it untouched. On OpenWrt, `--no-rollback` the same; 2.5 GB of
the user's with 2.3 GB free: "not enough room to carry your files over beside the previous system: 2673 MB needed,
2214 MB free", nothing changed, and through with `--no-rollback`; `MU300_UPDATE_KEEP=list` loses what it always did
(34 of 67 on Ubuntu), as it says.

**A test that failed now and then** (`test_magisk_installer...test_payload_replaced_after_verification_is_not_installed`,
"checksum mismatch", about 1 run in 20 on this branch): the test made a zip, then the corrupt one, and the fake
release's `tar_gz` put the time into the gzip header - when a second boundary fell between the two, the manifest
the installer read was the second zip's and the payload the first's. No race in the installer (it checks a copy of
the payload and uses only that copy). Made deterministic: 2 failures in 100 runs before, 0 in 200 after.

**Manifests of the old releases, for the record** (optional: no updater reads them from there). For each tag from
v2026.09.21 to v2026.10.27, with the tag's four images in `release/<tag>` as published:

```sh
python3 tools/image-manifest.py assets release/<tag> manifests/<tag>
gh release upload <tag> -R dikeckaan/mu300-linux manifests/<tag>/*.manifest.gz
```

`rootfs/overlay/opt/mu300/lib/image-manifests/` was made from the same manifests (`tools/image-manifest.py legacy`,
then `union`), each image downloaded and checked against its release's `SHA256SUMS` first.

### 71. A graphical installer that drives the text installers: an answers mode, a progress stream, a window; a beta question; where a Python with a usable Tk is found

Written against an `adb` that is a Python program (`tests/fakeadb.py`) and a fake installer; then run against an F50
(F50-B) from one Mac on 2026-10-15 - what that showed, and what it found, is under "What a device showed" at the
end. On Windows only what CI runs.

**Why.** A user showed a third party's Windows program for this project: a form with a device list, six buttons
and a few tabs, which carries its own copy of what the installer does. A copy drifts: the installer has gained the
slot rule, the boot chain sync, the read-back of the boot image and the bounded SD stages (§33a, §50, #86) since
any such copy could have been made. So the window here has no install logic at all. It asks the questions, hands
the answers to `install.sh` / `install.ps1`, and shows what they report.

**The answers mode** (`tools/answers.sh`, `tools/answers.ps1`; `docs/INSTALLER-AUTOMATION.md` is the reference).
Each question has one variable, the last argument of its `ask`. Four rules carry the safety:

* A question whose variable is not set stops the run and names the variable. It is never defaulted and nothing is
  read from standard input in its place. Tested for every question up to the first pull, under dash, bash and
  busybox ash, and for `install.ps1` under Windows PowerShell 5.1 and PowerShell 7.
* A variable set to nothing takes the default, and no default is the destructive answer: `INSTALL`, `ERASE`,
  `overwrite`, `internal` and `UNINSTALL` have to be given.
* A question that comes back stops. The kernel question and the make-room size repeat until they like the answer;
  the same variable would answer for ever. The second time is an error ("the answer in MU300_ANS_KERNEL was not
  accepted: 5.4").
* `@stdin` as a value puts the question on the stream and reads one line. That is what lets the window show the
  installer's **own** summary - made after the download and the build, from what is really there - before
  `INSTALL` is sent. A window that composed a summary of its own from the choices would be showing a guess.

**The progress stream** is lines `@@mu300 {json}` next to the text for people: stages with a percentage, questions
and answers, the facts of the device, a download's bytes once a second, the sha256 results, errors. The last event
of a run is `done` or `error` whatever ends it (an `EXIT` trap in the shell scripts, a `trap` in PowerShell): a
reader must never wait for more. The facts of `--check` are what the window draws the device from, so the window
and the text check cannot disagree about a device; among them are things the text does not print - the bootloader's
lock and verified-boot state, read with plain `getprop` **before** the check for root, so a device without root
still says what it is.

**What went wrong on the way, and is fixed:**

* *PowerShell does not tell `$Ans` from `$ans`.* `tools/answers.ps1` is dot-sourced, so its script variables share
  `install.ps1`'s scope. The dictionary of answers was `$script:Ans`; `install.ps1`'s own `$ans = Ask ...` (the
  storage question) replaced it with a string, and the first whole run on Windows stopped with "[System.String]
  does not contain a method named 'ContainsKey'". `-NonInteractive` was lost the same way: the file set a variable
  of the parameter's name to `$false` after the parameter had been bound. Every variable of the file has the prefix
  `Mu` now, and `tests/test_answers.py` checks that the installers use none of those names. Found by CI's first run
  of `tests/answers.Tests.ps1`, not by reading.
* *A secret given in the environment was inherited by everything.* `MU300_ANS_PASSWORD` from an answers file was
  never exported, but one given in the environment stayed there for adb, curl and python to inherit; an answers
  file was accepted whatever its permissions; a malformed line of it was echoed. Now: one table of secrets, whose
  values are never printed, never in an event and never in an error; a secret in the environment is taken out of
  it before anything is started (and put back for the one restart after a self-update); the file must be the
  user's alone (no link, owned by the user, no permission for group or others - `install.sh`, `uninstall.sh`;
  Windows has no such check); a bad line is reported by its number. The fake adb records the answer variables it
  was started with, and the tests look for the password in every output stream, in adb's environment, in the
  fake's log and in the work directory.
* *The parts of a parallel download count twice for a moment.* While they are joined both the parts and the whole
  file exist; the byte count on the stream is capped at the length.
* *`install.ps1` waited two minutes on a device without root* before it said so: it asked for `sys.boot_completed`
  through `su`. It asks through plain adb now, as `install.sh` does.
* *A boot image that could not be pulled was a PowerShell exception* (`Get-Item` on a file that is not there), not
  the installer's message.

**The beta question.** The installers took `releases/latest`. They now read the list of releases and offer a
prerelease only when it was published after the newest full release (`tools/release_pick.py`, one file for both
installers and the window). No token; when the list does not come - offline, the API's rate limit, a proxy's page -
the newest release is looked up as before and nothing is asked. The release is resolved before the questions now,
so a GitHub that does not answer stops the run before the password, not after the pulls. `install.ps1 -Answers`
(one answer per line, in order) never gets the question: it would shift every answer behind it.

**Where a Python that can draw the window is found.** Measured on this Mac, the one fact of this section that came
from a real machine:

* macOS's own Python - `/usr/bin/python3`, the Command Line Tools' 3.9.6 - has tkinter with **Tk 8.5**. On macOS
  26.6 its window opens and stays black: no widget is ever drawn. Homebrew's Python 3.13 on the same machine had no
  tkinter at all; `brew install python-tk@3.13` brought Tk 9.1, and with it the window draws.
* So a Python counts only when its Tk is 8.6 or newer, an older one is named as such ("its Tk is older than 8.6"),
  and among the Pythons without a usable tkinter the one a fix is known for is the one offered
  (`brew install python-tk@X.Y`), not the first found. The window itself refuses an older Tk with exit status 3,
  on which the installers go on in text.
* `/usr/bin/python3` without the Command Line Tools is a stub whose only effect is the dialog that offers to
  install them. It is run only when `xcode-select -p` succeeds (tested with a stub that records being run).
* On Windows the Microsoft Store's alias is a `python.exe` that prints nothing and fails; every candidate is run
  with a real argument, so it is never taken for a Python and the Store is never opened. A Python installed a
  moment ago by winget is not on the process's `PATH`; the installation directories find it.
* Not measured: any Linux desktop, any Windows machine with a person at it.

**The window** (`gui/`, tkinter and the standard library only). Model, runner and controller have no window in
them and are tested without a display; the widgets are built once per page from the controller's state.

* The device, root and the bootloader are shown separately. Only a missing root blocks an installation.
* **A locked bootloader is a warning, never a refusal - the owner's decision of 2026-10-13.** The bootloader does
  not have to be unlocked: a device with a patched TrustOS boots a modified boot image with the bootloader locked,
  and that is enough. No property says whether TrustOS is patched, so nothing can be decided from the lock. Both
  text installers (in the checks and again in the plan before `INSTALL`) and the window (in the warning colour on
  the device page and above the summary, never red) say: "The bootloader is locked. Did you patch TrustOS? With a
  patched TrustOS Linux boots on a locked bootloader; without it the device goes back to Android by itself after
  the install." There is no extra confirmation. Issue #156 asked for an early refusal on a locked bootloader; this
  supersedes it. Locked is `ro.boot.flash.locked=1` or `ro.boot.vbmeta.device_state=locked`, unlocked is `0` or
  `unlocked`, anything else is "not reported"; the verified-boot colour is shown and not interpreted. **What an F50
  or a U30 Air really reports in these properties - unlocked, locked, locked with a patched TrustOS - is still not
  measured**: the rule is written from the properties' meaning in Android, not from a device. The window does not
  root, unlock or patch anything and links to no guide for it.
* Stop is offered while nothing has been written to the device (up to and including the copy to
  `/data/local/tmp`) and not from `android-install.sh` on; closing the window is refused there too. Closing the
  summary dialog answers no.
* The make-room path (§9b, §57) is there with its figures and wants `ERASE` typed into the window, which is then
  the installer's own `MU300_ANS_ERASE_ANDROID`. **It has never been run from the window against a device.**
* "Back up now" is `install.sh --backup`: Android's boot image and the first block of `misc`, compared with the
  device by sha256. The NV and calibration partitions are not read by it, by the installers or by the window; the
  full backup of those stays `tools/backup-device.sh`, which the window names and does not run.
* A device in our Linux is recognised by its serial number (`MU300LINUX-...`, §70) and asked with
  `mu300-device --json`; update, kernel switch, restart and back to Android then go over adb as the project's own
  commands. Without adb to it the window shows the commands and opens an SSH session in the system's terminal.
* Every line of a run is masked when it comes in: the serial numbers of the attached devices, 15-digit numbers
  standing alone (IMEI, IMSI), ICCIDs, passwords and their hashes, Wi-Fi passphrases, adb keys, MAC addresses, the
  home directory's name. Nothing unmasked is kept, so the log on the screen, the copied and the saved log and the
  diagnostics report cannot differ in that. The masking is by pattern: a secret in a shape nobody thought of is
  not caught, which is why the report says to read it before posting.

**What a device showed** (2026-10-15; F50-B: 64 GB, Android 13 `F50_FLYMODEM_ZYV1.0.0B09`, Magisk 30.6, bootloader
unlocked; a Mac with macOS 26.6 and Homebrew's Python 3.13 / Tk 9.1; release v2026.10.27; next to it a U30 Air in
Linux on the same adb, and for part of the day a Pixel 7. Every run with `MU300_PROGRESS=1`, each stream checked:
every `@@mu300` line JSON with string values at the start of a line, the steps in order, the last event `done` or
`error`.)

* *`--check` from a device in Linux*, named by `ANDROID_SERIAL=MU300LINUX-...`: asked over adb, rebooted, came back as
  Android, 35 events, `done ok`. The facts are `install.sh`'s text: eMMC 122159104 sectors, partitions ending at
  54218752, the region at 27762098176 with 34779168768 bytes, `existing`, slots a/b, the boot chain identical.
* *The bootloader's properties on this unlocked unit:* `ro.boot.flash.locked=0`, `ro.boot.vbmeta.device_state=unlocked`,
  `ro.boot.verifiedbootstate=orange`, so `bootloader.state=unlocked` and no warning. Seen once by accident on a Pixel
  7 with a locked bootloader (see the first fault below): `1` / `locked` / `green`. A locked F50 or U30 Air, with or
  without a patched TrustOS, is still not measured.
* *`--backup`:* `boot_a.img` (64 MiB) and `misc-head.bin` (4 KiB), the sha256 of the boot image the same as the
  device's, nothing written.
* *Installations in answers mode*, the summary on `@stdin` and `INSTALL` sent when it waited: Ubuntu 24.04 on 7.2 over
  the existing filesystem (`update`, 14 questions, `/etc/mu300/lan.conf` kept); OpenWrt with the panel on 7.2 with the
  filesystem wiped; a fresh Ubuntu after a quick uninstall, where the region still held data and
  `MU300_ANS_OVERWRITE=overwrite` was asked for. Each `done ok` with the release, kernel and system, and the device
  booted Linux. The sha256 results were `ok` for downloaded files and `cached` for kept ones.
* *The beta question:* asked ("A beta is out: v2026.10.27 ... Install the beta v2026.10.27 instead of v2026.10.25?")
  while v2026.10.27 was a prerelease newer than the release v2026.10.25, and answered yes from the file; not asked
  once v2026.10.27 had become the release (v2026.10.26, an older prerelease, does not count), and a `MU300_ANS_BETA`
  in the file then stays unused.
* *Uninstallations in answers mode*: `quick` from a device in Linux (named by its Linux serial, rebooted over adb), and
  `keep` from the window; both `done ok`, `boot_b` a copy of `boot_a`, the Magisk module marked for removal.
* *The window* (driven from its own Tk thread, the screen locked part of the time, so screenshots only from the
  morning's runs): the device page in Android, in Linux and with two boards to choose from; the storage bar against
  the real table; Choose; an installation from the window (update, Ubuntu on 7.2) through the installer's own
  summary to the Finish page; the uninstaller from the window with `keep`; Manage on a device in Linux:
  `mu300-device --json`, the update check, back to Android; the kernel box showing the running kernel.
* *The question "Use the graphical installer?"* at a terminal (a pty): the default `yes` (macOS, no SSH), `no` went
  on in text, `yes` started the window with `/opt/homebrew/bin/python3.13`. The search found `/usr/bin/python3` (3.9,
  Tk 8.5: too old) and Homebrew's 3.13 with Tk 9.1, and took the second.
* *The web installer's mirror* (FINDINGS 72) was run on the same day with the same unit.

Faults the device found, all fixed with tests:

* *While the F50 rebooted, a Pixel next to it was the only adb device*, and `install.sh --check` went on with the
  Pixel ("su: inaccessible or not found"; nothing written). Waiting for Android now takes only the board that was
  rebooted (our Linux's serial is `MU300LINUX-<Android's serial>-<eMMC id>`), or the one F50/U30 Air, never
  another device. `install.ps1` / `uninstall.ps1` had the same wait and have the same fix.
* *Two boards in Linux on adb* (the F50 named by `ANDROID_SERIAL`, a U30 Air): the named board was dropped, none of
  the two was rebooted over adb, and the SSH fallback went to 192.168.77.1/.78.1 - where the U30 Air answered. Now
  the named board is the one rebooted, and without adb to it no address is guessed while another board in Linux is
  on adb (unless `MU300_IP` names it). Measured afterwards: only the F50 was rebooted. Also in the PowerShell scripts.
* *The window went on with the other board.* While the F50 restarted after an installation from the window, the
  U30 Air in Linux was the only adb device left and the window took it (and asked it for `mu300-device --json`); its
  Manage page would have restarted or updated that board. The window now follows the board it worked on through a
  restart, in whichever system it comes back, and takes none while it is away. Measured afterwards: during the
  restart into Android nothing was selected, then the F50 in Android, checked by itself.
* *The kernel box of Manage said 6.18* on a device running 7.2.10; it shows the running kernel now.
* *An answers file with mode 644* stopped `install.sh` before the stream existed, with no event at all; a program
  that asked for the stream now gets the `error` event (the text, never the file's content).
* *The uninstaller's clean-up said "rm: /data/local/tmp/mu300-web: Is a directory"*: the web installer's directory
  matched `mu300-*`. Only files are removed now (`uninstall.sh`, `uninstall.ps1`).

Seen and left as they are:

* The first check after Android came back failed once with "could not read the partition table": about 8 s after it
  first showed up the F50 left adb for 2 s and came back (Android's USB set-up after the boot). The window checks
  again when the device comes back, and that check passed. A text run started in that moment can fail the same way;
  starting it again is the remedy.
* A password that is also a word of the installer's output is masked there too: with `ubuntu` as the password the
  window's log and summary say "systems: <password> (Ubuntu 24.04)". That is the masking working, and it tells a
  reader of the log that the password is `ubuntu`; a password that is no such word avoids both.
* The end of an installation names 192.168.77.1 for SSH whatever `/etc/mu300/lan.conf` on the device says (an update
  keeps that file).

**What is still to be shown:**

1. `.\install.ps1 -Check`, any run of the PowerShell scripts against a device, and the window on Windows (CI runs
   them against the fake adb only); by hand the question and the search for Python on a machine with only the
   Store alias, and `[Console]::OutputEncoding` under a window with no console (the Turkish and Chinese text).
2. A U30 Air, and what `bootloader.locked` / `bootloader.verified` say on a locked F50 or U30 Air, with and without a
   patched TrustOS.
3. The window on a Linux desktop; from the window: a device that is unauthorised, Stop during the download, the
   SSH button.
4. The make-room path from the window, last, on a unit that may lose its Android data.

### 83. An update dropped the jobs of OpenWrt's System > Scheduled Tasks (`/etc/crontabs`)

LuCI's System > Scheduled Tasks page writes `/etc/crontabs/root`, and busybox `crond` runs it (`init.d/cron`,
START 50). `etc/crontabs` was in neither copy of the keep list - `keep_list` in `mu300-update` nor the one in
`tools/android-install.sh` - so an update built the new system from the release's image and left the jobs behind
in `<os>.old`. Two things follow, and the second is worse than the lost line: the page comes up empty after the
reboot, and the image's own `/etc/crontabs` is an **empty directory**, while OpenWrt's `init.d/cron` begins with

    [ -z "$(ls /etc/crontabs/)" ] && return 1

so `crond` does not run at all in the updated system: every job, present or added later by hand, is dead until
somebody notices.

Reported by a user (U30 Air, openwrt-luci): the Scheduled Tasks page was empty after an update. The symptom is
the report's; the cause is read from the code and from the release image (`mu300-openwrt-luci-rootfs.tar.gz`
carries an empty `./etc/crontabs/`), not reproduced on a board here. OpenWrt's own `sysupgrade` keeps the
directory - it is what this list means to mirror - and the two lists are kept equal by a test, which is why both
changed together.

Fixed: `etc/crontabs` added to the OpenWrt branch of both lists. Not touched: the Ubuntu branch, whose images
carry no cron package (scheduled work there is systemd timers, and a user's own unit files in
`/etc/systemd/system` are still dropped by an update - a separate gap, and a design decision about which of
`*.service`, `*.timer` and `*.d/` drop-ins to carry).

Unit tests only (`tests/test_update.py`: `keep_list openwrt-luci` names it, the two lists are equal, and
`apply_one` on a fake disk carries `etc/crontabs/root` over an image whose own directory is empty). To check on a
device with openwrt-luci:

    # before the update: a job saved in System > Scheduled Tasks
    cat /etc/crontabs/root; ps | grep crond
    mu300-update apply && reboot
    # after: the same job, and crond running
    cat /etc/crontabs/root; ps | grep crond
### 80. WPA3 on the U30 Air's access point: the SC2355 firmware does SAE itself (PR #74, Snrat)
The AP side of 14b's station finding. `docs/U30AIR-SAE.md` has the recipe and the open question; what the hardware
showed, on one U30 Air (OpenWrt 25.12.5, Linux 7.2.9):

* **Stock hostapd cannot do SAE on this driver.** The SME is in the firmware (`iw phy`: `connect`, no
  `authenticate`), so hostapd never sees the SAE frames: a WPA3-only BSS comes up, a client finishes SAE with the
  firmware and then fails association or the 4-way handshake (macOS: `-3912`).
* **Two vendor interfaces make it work.** hostapd hands the passphrase to the firmware with vendor command OUI
  `0x001374`, subcommand 43, nested attributes 8 (passphrase), 6 (group, 19) and 7 (ACT, `0xffffffff`); the
  firmware answers each association with the derived PMK and PMKID as a trailing vendor element in the
  `NEW_STATION` IE buffer: EID 221, length 52, prefix `40:45:da:04`, then 32 + 16 bytes. Hunting-and-pecking,
  group 19 only; H2E-only clients and other groups untested.
* **Only the passphrase reaches the firmware.** `vendor_set_sae_password` (`sc2355/vendor.c`) stores the group and
  never increments `group_count`, so `vendor_softap_convert_para` writes no group TLV; and it writes the ACT TLV only
  when `setting->act != -1`, which `0xffffffff` is not. `CMD_SET_SAE_PARAM` therefore carries the entry, the
  passphrase and the end marker: group 19 and the anti-clogging threshold are the firmware's defaults, and hostapd's
  `sae_groups` and `sae_anti_clogging_threshold` do nothing in this mode. Left as it is: sending a group list the
  firmware has never been given is a change nobody has measured.
* **The gate is the option and a firmware capability, not the device.** The driver answers the vendor command with
  `-ENOTSUPP` unless the firmware reports `SPRD_EXTEND_SOATAP_WPA3`. The F50 has the same chip and driver; what its
  firmware reports is not known. The command exists in the 5.4 vendor driver as well as in the mainline port;
  only 7.2.9 has run it.
* **The PMK arrives in a client-controlled buffer.** The driver passes `evt_new_station.ie` straight through as
  `assoc_req_ies` (`sc2355/cmdevt.c` -> `common/report.c`), the same bytes that carry the station's own IEs. The
  parser accepts exactly one trailing element and rejects any second marker, which only holds if the firmware
  always appends its own; nothing proves it refuses an association without a completed SAE exchange. Open.
* **The stock driver printed secrets at `L_DBG`**: the SAE passphrase (`pwd is :%s`, `vendor.c`), a station PSK
  (`cfg80211.c`, `%s` on a buffer that is not NUL-terminated), every TX command and up to 400 bytes of every RX
  message on PCIe (`pcie.c`, `sdio.c`), the `NEW_STATION` event (`cmdevt.c`). The default level is `L_INFO` and this
  kernel exposes no debugfs node for it, so none leaked by default; the removals are unconditional now. Confirmed
  on the device with the rebuilt 7.2.9 module: `dmesg` and `logread` through a boot, a WPA2 association and a
  package swap hold none of the patterns (the only `EVENT:` matches are `reorder_wlan_delba_event`).
* **Option off is the stock path.** With the patched `wpad-basic-openssl` r8 installed and the WPA2-PSK hotspot
  untouched, the generated `hostapd-phy0.conf` has no `sae`/`u30_sae` key, a WPA2 client is back 32 s after the
  package swap, the VPN stays up. The mode needs pure SAE, `ieee80211w=2`, `sae_pwe=0` and PMKSA caching, and a
  BSS with the option and any other mode fails closed (`Failed to set beacon parameters`, AP-DISABLED).
  In the patch every new path starts from `u30_sae_offload` (the configuration check, the firmware request, the
  key import); the one line that is not behind it replaces hostapd's debug hex dump of the association IEs with their
  length. OpenWrt's wifi-scripts turn the documented UCI settings into `wpa_key_mgmt=SAE`, `ieee80211w=2`,
  `sae_pwe=0`, `u30_sae_offload=1` and `wpa_passphrase` (no `sae_password`, which the patch refuses), checked with
  the 25.12.5 scripts in a container.
* **A second BSS with the option, added live, took the radio down (2026-10-12).** `wifi reload` with a new
  `wifi-iface` (`encryption sae`, `ieee80211w 2`, `sae_pwe 0`, `u30_sae_offload=1`) next to the WPA2 hotspot: both
  SSIDs disappeared and did not come back within ten minutes. The device could only be reached over that hotspot,
  so the cause is not known yet (hostapd gives the whole phy up when one BSS fails to set up; the earlier maintainer
  test used a separate BSS with r6 and a full `wifi down/up`). Enable the option on a device you can reach another
  way, and with a full `wifi down; wifi up`, never `wifi reload`.
  Snrat's r9 refuses a second BSS when the configuration is loaded (`U30 SAE: supports a single BSS only`); on his
  device, with `logread -f` over USB, the refusal still took the running WPA2 BSS down with it through netifd's
  reload. The cause of the r8 outage itself was never captured.
* **A hotspot that could not start stayed down at every boot; now it goes back to WPA2 (2026-10-13).** Three roads
  to it: `mu300-update` keeps `/etc/config` and replaces the packages, and the stock wpad refuses a configuration with
  a key it does not know; the firmware refuses the vendor command; the patch rejects the mode.
  `openwrt-wifi-sae-guard` (does nothing without the option) looks before the first `wifi up` whether the installed
  hostapd has the option, and about two minutes after boot whether the access point is `ENABLED`; if not, the BSS
  becomes `psk2` with the same passphrase, the file as it was is kept in `/etc/mu300/wireless.sae-offload`, and
  `mu300-wifi` logs one error line. WPA2 because hostapd's own SAE cannot work on this driver (first point).
* **Measured on the U30 Air, 2026-10-13** (OpenWrt 25.12.5, 7.2.10, r9 built with the helper, this branch's
  `sprd_wlan_combo.ko`; no Wi-Fi client at hand, so no association with SAE was tried):
  * Without the option the guard changes nothing: `AP-ENABLED` at 40.1 / 41.5 / 43.3 / 43.4 s before, 41.2 / 41.3 /
    43.3 s with it; silent, the configuration byte-identical, a WPA2 client back by itself.
  * netifd starts the radio once before `mu300-hw` does (15 to 23 s after power-on; `AP-DISABLED` under the world
    regulatory domain). So the stock hostapd does see the option once and logs `unknown configuration item`; the
    guard acts before `mu300-hw`'s `wifi down; wifi up` at about 37 s, and the hotspot was up as WPA2 at 39.9 s, the
    configuration byte-identical to the one before the opt-in, the saved file mode 600.
  * A mode r9 refuses (`sae-mixed`; a second BSS): fallback 136 s after power-on, `AP-ENABLED` at 139.5 and 139.7 s.
    Off on purpose (the key's marker, interface or radio disabled): untouched.
  * **The log loses the guard's line.** 128 KiB, about 1300 lines, and one Wi-Fi restart writes hundreds: 135 s
    after the fallback the line was gone. It is now also in `/etc/mu300/wireless.sae-offload.why`, with its time.
  * r9 with the option: `U30 SAE: firmware runtime parameters configured`, `vendor_set_sae_password type : 8/6/7`,
    no `firmware not support softap wpa3`, `AP-ENABLED` 5 s after `wifi up`, 41.6 s after power-on; the generated
    file has `wpa_key_mgmt=SAE`, `ieee80211w=2`, `sae_pwe=0`, `u30_sae_offload=1`. A synthetic passphrase, as text
    and as hex: 0 lines in `dmesg` and `logread`; none of the removed prints. Option off again: `WPA-PSK`, no line.
  * The module with the removals booted and ran every step above (its `wcn_bsp` is section-identical to the
    installed one; `sprd_wlan_combo` 352 bytes of code shorter). The module in v2026.10.25 prints the passphrase
    with `pr_info`, not at `L_DBG` as the point above says: it holds the four format strings. It was not run with
    the option, so that print was not seen in a log.
  * `apk add` of the r9 pair next to `wpad-basic-mbedtls` is refused (conflict): `apk del` the stock one first.
    This `iw` prints no "Supported commands", and `iw dev wlan0 station dump` on this driver prints no station
    fields, so neither can serve as a check.
  * Not measured: any client (WPA3 join, WPA2 refused on the SAE BSS, wrong passphrase, throughput, the PMK
    probe), kernel 5.4, the F50. After the SAE steps and the original WPA2 configuration back, the WPA2 client that
    had rejoined earlier did not come back within 4 minutes, nor after the device was all stock again: it had
    most likely left, and a WPA2 join after SAE in one boot is not shown.
* **Built, 2026-10-13:** `sprd_wlan_combo` with these removals for 7.2.10 and 6.18.56 (with `wcn_bsp`; the five touched
  files warn only where the vendor's code always did, none of the removed format strings is in the module);
  for 5.4 the twelve `wlan_combo-*.patch` apply in the build's order on the pristine vendor driver and all 69 objects
  compile (the module was not linked: ThinLTO wants to write next to the kernel's objects). The hostapd patch applies
  with GNU patch after OpenWrt 25.12.5's own patches on `ca266cc2` (BSD patch rejects the `ap_config.c` hunk, which
  has no leading context: build in the SDK, not on macOS).

## ZTE V50 (MU3351)

### 95. The ZTE V50 (MU3351), experimental: how it is told apart, and what kano measured on his

**Status: experimental. Nothing in this section was measured by this project: nobody here has a V50.** What follows
separates what kano (kanoqwq) says he read and measured on his V50, in his line of this project (branch
`clean-tf-7.2`, MIT like this one), from what was checked here. The owner's word (2026-10-15): "if kano did V50
support, bring it over". Nothing of his tree was run here and no binary of it was taken; the code below is ported
into this tree's structure.

**kano's commits about the V50.** `f6b0668d` (2026-10-14, "add desktop deployment and isolate F50/V50 profiles"):
the identity, the device-tree test, the AW9523B LED driver, the LED mapping, dual SIM, NFC, CPU voltage, his notes
(`docs/V50-MU3351-20261014.zh-CN.md`). `0438ab01` (2026-10-14): the shared eMMC policy that replaced his V50-only
one, and a changelog. Later ones mention the V50 in passing: `2d3b6f3f` (the F50 and the V50 have no battery: their
fuel gauge is not one), `e114999d` and `8d3d29e6` (updates and installs on his V50 with his desktop installer),
`0e19fe32` and `53ef7b1a` (his GUI and docs); `cd4fb28b` (2026-10-01) took a boot-time change from "V50 boot speed
research".

**What kano says he read or measured (his notes, 2026-10-14; not repeated here).**
* Identity: `ro.product.model` V50, `ro.product.device` MU3351, platform `ums9620`, board `ums9620_2h10_feimao`, T760:
  the F50's kernel platform; the same CPU frequency tables, the SC2355 Wi-Fi on PCIe, the same A/B partition names.
  ZTE's support page calls the V50 MU3351 (not the Blade V50 phone). Android 13, file-based encryption on his unit.
* Its LEDs: an AW9523B at 0x5b on I2C3 (`/soc/ap-ahb/i2c@2270000/aw9523b_led@5b`), not in the F50's device tree. The
  DT `idx` values are GPIO pins, not DIM registers (from `aw9523b_brightness_work` in ZTE's Android driver); the
  current limit is the low two bits of `default_imax` (`aw9523b_set_led_imax`); three lamps, NET1, NET2 and Wi-Fi,
  each with two white emitters and blue and red ones (from `groupcolor_store`, and lit one group at a time on the
  unit). The PMIC's `sc27xx:*` LEDs exist there as well, and older scripts picked those.
* No battery (his power-supply code treats the F50 and the V50 alike: their fuel gauge is synthetic).
* NFC: I2C2 0x57, reset on AP GPIO189 (the U30 Air's is 190); the tag read and written back.
* Dual SIM: with only SIM 2 in, `CPIN READY`, `CFUN=1` and both stacks up; registration answered `CEREG=8` (the card
  was out of credit). Two cards at once: not measured, in his words.
* eMMC: under mainline ext4 reported `deleted inode referenced` after normal reboots, again after an offline fsck.
  With the eMMC host's runtime PM forbidden at probe (kernel 7.2.8 "#17") a marker, the configuration and scripts
  survived a sync and a reboot with their SHA-256, `errors_count` 0: "an improvement, not proof that runtime PM alone
  caused it". Writing `power/control` "on" from the initramfs hung the boot before the mount. He later replaced it
  with a policy for every board (FUA emulated with flushes, ordered MMIO in `sdhci-sprd`, the eMMC never powered off
  at system suspend), which he says was not yet measured on the V50.
* His V50 booted Linux from slot b with misc's boot control (32 bytes), his boot chain check read the five images
  alike on both slots, and it ran OpenWrt with the 6.18.54/7.2.8 kernels he built with his AW9523B driver.
  His installers refuse kernel 5.4 on the V50.

**What was checked here (2026-10-15).**
* The F50's stock device tree (`vendor_boot`, the live FDT and `dtbo` of an F50, read with `dtc`): no AW9523B, no
  `charger_policy_service`; its `i2c@2270000` is `sprd,sc9860-i2c`, disabled and empty. The U30 Air's `vendor_boot`
  (a backup of 2026-09-27): no AW9523B; `charger_policy_service` present. So the node tells the V50 from both.
* Both mainline kernels (6.18.56, 7.2.10) build with the driver and patch 0017; no warning from either file.
* Unit tests for every decision below, on dash, bash and busybox sh.

**What was ported, and how a V50 is told apart.**
* `mu300-device` and `boot/init` (one rule, the same code; a test holds them to it): the label (`/etc/mu300-device`,
  `/run/mu300/device`) as before, except that **f50** on a device tree with the AW9523B node and without the charger
  policy service is a **v50** (an older installer took a V50 for an F50 when the user said yes), and **v50** on a
  device tree without that node is what the tree says (u30air with the charger policy service, else f50). The F50
  and the U30 Air: no node, so the answer is the one of before in every case (`test_mu300_device_three_boards`,
  `tests/test_boot_init.py` `Device`).
* Installers (`install.sh`, `install.ps1`, the Magisk zip, `tools/android-web.sh` for the web installer, the boot
  chain scripts): exactly `V50 / MU3351` on `ums9620` is a v50, with one line saying it is experimental; a model V50
  with another device, or a device MU3351 under another model, or another platform is refused, never offered as an
  F50; `MU300_DEVICE` cannot make a V50 another device (`f50`/`u30air` only, as before). Kernel: mainline only
  (`install.sh --build`, the 5.4 choice, a zip whose kernel does not name the V50 and the web installer's 5.4 are
  refused with the way out).
* Kernel bundles: a mainline bundle names `v50` in `devices` only when its kernel has `CONFIG_LEDS_AW9523B=y`; the 5.4
  bundle never does, so `mu300-update` never puts 5.4 or an older kernel on a V50.
* `leds-aw9523b` (kano's driver, `upstream/port/drivers/leds/`, built in): binds only `awinic,aw9523b` with ZTE's
  binding (`led_enable` 1, `gpio_enable` 0), checks the whole binding and the chip ID 0x23 before it touches the chip;
  registers the DT groups, each wired pin (`aw9523b:pinN`) and, for exactly the V50's binding, the lamps
  (`v50:net1:white` ...). `mu300-led`: NET1 is the network lamp (blue 4G, white 5G, red no service), the Wi-Fi lamp
  white on 5 GHz and blue on 2.4 GHz, NET2 dark; the PMIC's LEDs are never written on a V50.
* Patch 0017 (`sdhci-sprd`): the eMMC host's runtime PM forbidden at probe where the AW9523B node is, his measured
  fix, not the later shared policy (that one changes every board, and nothing measured it on the V50 either). On the
  F50 and the U30 Air it is a lookup that finds nothing.
* No battery: `mu300-power`, the dashboard's power tile and the USB role setter take the V50 as an F50.
* The charger at 0x1a (patch 0016, issue #225): bound only with `/charger_policy_service`; the V50 has none (kano's
  init tests for that node before the AW9523B and still took his unit for a v50; and he says it has no battery), so
  nothing is bound there, as on the F50.
* USB network `192.168.79.1` (kano kept the F50's `192.168.77.1`, which collides with an F50 on one computer).

**What does not work yet.** The second SIM (the dual-SIM code is the U30 Air's, §74, and kano's evidence is one card
in SIM 2 that did not register); NFC (`mu300-nfc` says so; another reset line than the U30 Air's); SIM selection;
kernel 5.4; kano's CPU voltage whitelist entry for the V50's SML (this tree has no such list); his NET2/Wi-Fi LuCI LED
page and his OpenWrt LED events for two SIMs.

**Risks.** A V50 that does not boot falls back to Android after the usual attempts (misc's trial). The LED driver and
patch 0017 do nothing without the node. A V50 installed earlier as an F50 becomes a v50 with the next update: its
address moves to `192.168.79.1` (Ubuntu without `lan.conf`; OpenWrt keeps the LAN it was set up with) and its kernel
is updated only to a mainline one that names it (`mu300-update kernel 6.18`). The eMMC trouble kano saw may have
another cause than runtime PM.

**Checklist for a V50 owner (report in an issue).**
1. Android: `getprop ro.product.model`, `ro.product.device`, `ro.board.platform` say V50, MU3351, ums9620.
2. Install with kernel 6.18 (or 7.2) of a release that names the V50; the installer says "ZTE V50: EXPERIMENTAL".
3. In Linux: `mu300-device` says `v50`; `ssh` to `192.168.79.1` works; `dmesg | grep -i -e aw9523b -e 'kept awake'`
   shows "4 LED groups, pin mask 0xffff" and "MU300: ZTE V50, eMMC host kept awake".
4. `ls /sys/class/leds` has `v50:net1:*`, `v50:wifi:*`; `sudo mu300-led test` lights each lamp in turn.
5. Mobile data on SIM 1, the hotspot on 5 GHz and 2.4 GHz (the Wi-Fi lamp white, then blue).
6. Several reboots, then `sudo dumpe2fs -h` of the Linux filesystem: `FS Error count` absent or 0, files kept.

## The device manager

### 110. The web installer as a device manager: one checked entry point on the device (mu300-api), the page over it

**What was asked.** The owner, 2026-10-15: the web installer should also manage a device that runs our Linux - the
Wi-Fi name, the VPN and so on, everything about the device - over the same WebUSB connection. Until then it had a
small view (status, update check, kernel, restart, back to Android, logs) made of single shell commands.

**The design.** The page composes no command and reimplements nothing. The device has one entry point,
`/opt/mu300/bin/mu300-api METHOD`, with a fixed list of methods and the request as one JSON object on stdin; it answers
one JSON object. Its interface is documented as stable in `docs/ADB-INTERFACE.md` (field `api`, now `1`).

* **Reading the request** without jq (Ubuntu has it, OpenWrt does not) or jsonfilter (the reverse): `lib/json.awk`, one
  program for busybox awk, mawk and gawk. A request is a flat object of strings, numbers, booleans and null, keys
  `[a-z][a-z0-9_]{0,31}`; a nested value, a key twice, a raw control character, `\u0000` (or any control character
  other than tab, newline and CR, escaped or not), a lone surrogate, trailing text or more than 64 KiB is
  `bad-request` before any method runs. The same program re-serialises a tool's JSON answer (`mode=check`) before it
  is put into a reply, so a tool cannot break the reply it is part of; a tool's answer that is not JSON is `null` or
  `failed`, never pasted in.
* **Every field by its own rule**, an unknown field refused: fixed words, numbers in ranges, an SSID by hostapd's and
  wifi-client's rule (1-32 bytes, no control character, no space first or last), a WPA2 passphrase (8-63 printable
  ASCII), an APN by 3GPP's characters and credentials by `mobile-data.conf`'s own rule (FINDINGS 65: printable ASCII,
  no quote or backslash, at most 64), a channel from `lib/wifi-channels.sh` for the band and the country (never DFS,
  FINDINGS 42), a LAN address private and at `.1`, a host name by RFC 1123, a time zone that exists in the zoneinfo,
  a VPN link by the scheme list `mu300vpn` uses, an `https://` URL, an adb public key by its shape.
* **Values reach a tool** as one argument that a pattern has already kept from starting with `-`, or on its stdin. The
  secrets only ever on stdin or in the file they belong in: the hotspot password into `hotspot.conf` (0600) or UCI
  through `uci batch` on stdin, the APN password into `mobile-data.conf` (0600) or UCI the same way, a VPN link or
  config on `mu300-vpn profile import -`'s stdin (a here-document: the variable is expanded once and never read
  again), a VPN URL and a Wi-Fi password into a 0600 file of the root-only job directory that the job opens as its
  stdin and removes before the command runs, the login password on `chpasswd`'s stdin (Ubuntu) or the static
  busybox's `chpasswd -c sha512` (OpenWrt, whose own busybox has none). Nothing secret is read back: `password_set`
  says whether there is one.
* **Shared code paths.** The CLIs of `/opt/mu300/bin` are the shared layer: `mu300-wifi-band` for a band change on
  OpenWrt, `wifi-client`, `mu300-sim`, `mu300-traffic`, `sms`, `mu300-usb`, `mu300-next-boot`, `mu300-os`,
  `mu300-update`, `mu300-extra`, and the VPN module's `mu300-vpn` (the same machine-readable CLI the LuCI pages reach
  through `mu300vpn` and Cockpit calls directly). Mobile data on and off is mu300-traffic's own way (`ifup/ifdown wan`,
  `systemctl start/stop mu300-mobile-data.service`). What only the OpenWrt control panel has - band and cell locks,
  the SMS pool, SMS forwarding - is delegated on openwrt-luci to its backend, called as rpcd calls it
  (`/usr/libexec/rpcd/mu300dash call METHOD` with the request on stdin: no `ubus call` with a secret in its argv), with
  the same field rules applied first; elsewhere those methods are `unsupported`. The overview's radio, battery and
  temperature readings are those of `mu300-panel info` (Cockpit's page); the panel extra keeps its own copy for
  systems that have no mu300-api - a release-independent extra cannot rely on it yet.
* **Long work is the job**: `update.check`, `update.apply`, `kernel.set`, `extra.install/remove`, `vpn.install`,
  `vpn.engine_install`, `vpn.add_url`, `vpn.sub_add`, `vpn.sub_refresh`, `wificlient.join/leave`. One at a time
  (flock, and the state), started with `setsid` so that adbd's SIGHUP at the end of the shell, a closed tab or a pulled
  cable does not reach it; its output in `/run/mu300-api/job/log`, its status in `rc`. `job.status {from: N}` gives the
  lines from N (whole lines while it runs, at most 400, each cut at 400 bytes, an address's path and query replaced by
  `...`). `hello` names the job, so a page that connects later follows it from the start. An update, a kernel or an
  extra's removal cannot be cancelled half way.
* **WPA3 (FINDINGS 80)** is never switched on: the option needs a patched hostapd and a full `wifi down; wifi up`, and
  a live change took a U30 Air's radio down. A hotspot already set to SAE by hand is shown as such and kept; a change
  of its password restarts it with `wifi down; wifi up`, never `wifi reload`. An open hotspot gets `psk2` with its
  first password.
* **Hidden SSID on Ubuntu** is new in `hotspot-start` (`HIDDEN=1` -> `ignore_broadcast_ssid=1`).
* **adb's keys mode** (FINDINGS 70) is only switched on together with the page's own key (`adb.auth {mode: keys, key}`:
  the key goes to `mu300-usb adb key -` first; a key that is refused leaves the mode alone), and every change of adb,
  the USB role, the LAN, the hotspot, mobile data and a restart runs two seconds after the answer (`setsid`), so the
  answer reaches the page first.

**The page.** `manager.js`: tabs Overview, Wi-Fi, Mobile data, VPN, SMS, USB and LAN, System. Every action whose
consequence reaches the page's own connection or the device's uplink asks first, saying what happens and how to get
back (the USB host role and adb's mode end the connection; a restart; mobile data off when it is the only uplink; a
kill switch; the LAN address, which does not touch adb). Secret fields start empty ("unchanged"), are shown only
while "show" is ticked, are emptied once saved and are added to the page's masker. The overview, the job and the
log are masked as everything else on the page; the diagnostics file leaves out SSIDs, user names, addresses and
message texts. A release without mu300-api (hello prints the marker) gets the earlier small view with a note to
update.

**Tested**: `tests/test_api.py` (every method's validation and its calls into stub tools, hostile values, the
secrets in no argv, reply or file but their own, the job; dash, bash and busybox sh, busybox's awk where there is
busybox), `tests/web/manager.test.mjs` (the page's adapter and the Manager against a fake adbd whose shell runs the
real mu300-api), the strings test across en/tr/zh.

**On the devices (2026-10-16).** The protocol of `docs/web-installer.md` ran with the page's own modules from Node over
WebUSB (the `usb` package; device.js `LinuxDevice`, manager.js `Manager`, the device picked by its full serial; no
browser) on a U30 Air (openwrt-luci, OpenWrt 25.12.5, v2026.10.27, kernel 6.18.56, the owner's VPN up with its kill
switch) and an F50 (Ubuntu 24.04, v2026.10.27, kernel 7.2.10), with this branch's mu300-api, json.awk, path-commands
and hotspot-start copied over the release (and #248's data roaming files, which data.get reads). Every setting
changed was set back afterwards from a copy taken first.

| # | U30 Air (openwrt-luci) | F50 (Ubuntu) |
|---|---|---|
| 1-2 | hello, every tab read; the overview, locks, VPN (the owner's profile, kill switch, engine), SMS pool and forwarding summary as LuCI has them | every tab read; locks `unsupported` (as designed) |
| 3 | SSID `Test "1" $(x) it's` and a password with a quote, a double quote, `$( )`, a backtick, a semicolon, a pipe, an ampersand and a backslash: **two defects** (below), fixed; then uci and hostapd byte for byte as sent, encryption psk2 kept; 2.4 GHz ch 11 (**a defect**, fixed), 5 GHz back on 36/VHT80, ch 44 and back | the same values byte for byte in hotspot.conf (0600) and hostapd.conf; 2.4 ch 11, 5 back (`iw dev`); **"off" for 20 s after each change** (fixed) |
| 4 | hidden: `ignore_broadcast_ssid=1`, back to 0 | the same (`HIDDEN=1`; hostapd.conf rewritten about 7 s after the answer) |
| 5 | `wireless.radio0.disabled=1`, no interface; on again | `mu300-hotspot` disabled and stopped; enabled and running again |
| 6 | - | scan refused in AP mode by wifi-client (this driver): the reason was its last hint line, now the whole message (fixed); no join (no network whose password was at hand) |
| 7 | `ifdown`/`ifup wan` (autostart false/true), the VPN back on the same exit address | the service stopped (no address) and started (address back) |
| 8 | APN `internet`, PAP, a user and a password with `$`, a backtick, a semicolon, a pipe, an ampersand and spaces: uci byte for byte (after the fix), the page shows the user, never the password; cleared again (`apn` empty deletes the option) | the same in mobile-data.conf (0600), the dial restarted with it; credentials cleared; bad APN/user/password values refused |
| 9-10 | sim.get; lock.get; lock.set LTE `1,3` (the owner's own setting, set again: queued and applied) - the bands were not changed | sim.get; lock.get `unsupported` |
| 12 | a made-up VLESS link beside the owner's profile: added, renamed (quotes), listed, removed; the owner's profile active throughout | the module installed by the job (v2.0.1 with vpn-xray), a made-up link added, renamed, removed; a link with `-o` and an `http://` one refused; the extras removed again |
| 13 | `7000 KALAN` through the panel's pool: sent, the carrier's answer arrived | the same through `sms`; the answer deleted by id |
| 14 | 192.168.90.1 and back: **the page lost the device** (below) | 192.168.90.1 and back: **the old address stayed on br-lan** (fixed); the Mac kept its old lease (no new address without reconnecting) |
| 15 | keys only with the page's key: the connection dropped, came back signed with it, `auth: keys`, one key; open again (the key file removed by hand) | the same |
| 16 | not run: the host role would take the USB connection away, and this unit must not be reached any other way | - |
| 17 | hostname and back; a time zone is refused as `unsupported` ("zoneinfo for ...", even the current one: OpenWrt has no zoneinfo, as designed); the same password set again and SSH login with it; SSH off (refused) and on | hostname, time zone Europe/Berlin and back; the same password again, SSH login; SSH off (refused) and on; /etc/shadow restored afterwards |
| 18 | update.check: "Up to date." | the same |
| 19 | not run (this unit must not fall back to Android) | 6.18 by the job and a restart: 6.18.56; 7.2 by the job failed with the job's "could not reach GitHub" (the carrier passed no traffic without the VPN by then) and was put back from the release's files by hand |
| 20 | `lang` installed and removed by the job | not run (the panel extra installs Cockpit from the archive) |
| 21 | logs read | logs read; the page's log never had a password |
| 22 | Android as the default and Linux again (no restart: this unit must stay in Linux) | the same (no restart) |

Defects found and fixed on this branch:
* **busybox awk (OpenWrt 25.12, busybox 1.37) and gsub**: json.awk's `gsub(/\\/, "\\\\")` gave one backslash there, so a
  string's quote came out unescaped and a backslash was lost. On the U30 Air every answer with an SSID holding a quote
  was no JSON (`wifi.get`: `bad-answer`), `\n` in a tool's text became `n`, and a request's backslash vanished on the
  way to uci (a hotspot password stored without it). json.awk now replaces literally (`rep`); a static test keeps
  backslashes out of every gsub replacement in json.awk and mu300-api (the unit tests use busybox only where the
  machine has one, and an older one at that).
* **A band with a channel on OpenWrt**: the channel was dropped (mu300-wifi-band puts a new band on auto): "2.4 GHz,
  channel 11" came up on 6. The channel is set after the band now.
* **Ubuntu's hotspot "off" right after a change**: `systemctl is-active` says `activating` for about 20 s (its
  ExecStartPost checks); `activating` counts as on.
* **lan-start kept the old LAN address** on br-lan (`ip addr replace` adds): both until the next boot. The old one is
  removed now. Clients keep their lease until they reconnect: the page's note says so now.
* **OpenWrt re-enumerates the USB gadget on every LAN ifup** (`hotplug.d/iface/10-mu300-usb`, for macOS's DHCP), so a
  LAN change ends the page's connection there: the page asks with its own text for OpenWrt and expects to lose the
  device (`leaves`), as for adb's mode.
* **A tool's refusal** was its last line only; it is the last message with its indented lines now.

Seen and left: the job box shows curl's progress meter as lines (`mu300-extra`, `mu300-update`); `wificlient.status`'s
text named the old SSID on OpenWrt after a change (wifi-client's own reading). **Not run**: a Wi-Fi join (6), the SIM
switch (9: the U30's second card registers for emergency only, the F50's needs a restart), the USB host role (16),
Update now (18: the update itself is #224's test), the restart into Android (22), the real page in Chrome (the
chooser and the folder picker are browser UI), plain OpenWrt and a V50.

## Data roaming

### 120. Data roaming: a switch of our own in the dial and its watchdog, the network's word for roaming, and a test hook

**What was missing.** Mobile data dialled whatever network the card registered on. Data roaming was always on and no
front end could turn it off; the panels showed "Registered (roaming)" and nothing else. Android has "allow data
roaming" per SIM; this is that.

**How "roaming" is known.** From the card's registration, which the modem reports on the card's own AT channels (§74:
the dial's channel, nr2 for slot 0 and nr5 for the U30 Air's SIM2 or the F50's internal card, answers for its card
alone, so no `AT+SPACTCARD=<n>;` prefix is needed and none is sent; the panel's terminal refuses that form anyway).
`<stat>` of `AT+CEREG?` (query form `+CEREG: <n>,<stat>[,...]`), and of `AT+C5GREG?` only when LTE's says neither
home nor roaming (5G SA). 3GPP TS 27.007: 1 registered home, 5 registered roaming, 9 and 10 the same two for "CSFB not
preferred" (EPS); 6/7 (SMS only) and 8 (emergency only) are not counted as either. The dashboard's table shows 10 as
"Registered" (it is roaming): left as it is, the data decision does not use that table. No `AT+CREG?`/`AT+CGREG?`: the
modem's data registration on LTE and NR is CEREG/C5GREG, and those are the ones measured answering on this modem (the
dial waits on CEREG since the beginning, the panel's collector reads both every 1.5 s).

**"Roaming" at home.** Stat 5 is the network's word. An MVNO on a host operator's network, or national roaming,
reports 5 in its own country. So the setting is the user's answer, never a guess of ours, and every front end says
"some SIMs report roaming at home (an MVNO, national roaming)".

**A switch of the modem's own: none known.** Looked for and not found: the repository has no RIL binaries
(`android-vendor/` holds the extraction lists; the extracted vendor subsets on the build host carry the GPU and
modem-control files, no `libril*`), no Unisoc AT reference names one, the AT commands seen from this modem (`AT+SP*`
in every log and script here) have none, and a web search for `SPDATAROAM`/`SPROAM`/Unisoc RIL data roaming found
nothing. On Android the decision is the framework's (its data network controller checks the service state's data
roaming flag against the user's setting before it asks the RIL for a data call); the RIL only gets the call, with the
APN's roaming protocol. So nothing new is sent to the modem: the switch is the policy of `mobile-data`'s dial and its
watchdog.

**The default: allowed.** Every release so far used data while roaming; an update must not take anybody's data away
(think of an MVNO SIM at home). Turning it off is one switch.

**Where it is stored.** OpenWrt: `network.wan.roaming` for slot 0 (the external card / SIM1), `network.wan.
roaming_internal` for slot 1 (the F50's internal card, the U30 Air's SIM2): per card, as the APN is (`apn`,
`apn_internal`), since the second card is often the travel SIM that is meant to roam. Ubuntu: `MU300_DATA_ROAMING` in
`/etc/mu300/mobile-data.conf`, one for both cards, as Ubuntu has one APN. Values 1/on/yes/true and 0/off/no/false;
unset or anything else is allowed (`mobile-data roaming` says when a stored value is neither). The file is read as
KEY=VALUE lines, never executed. The value is read again at every decision: a front end writes it, nothing is
restarted, and the dial or the watchdog acts on it within half a minute (the watchdog's interval). The one writer is
`mobile-data roaming on|off [--slot 0|1]`: on Ubuntu the file is rewritten with its other lines kept, root's alone
(it may hold the APN password), a new file renamed over the old one; on OpenWrt `uci set` and `uci commit network`
(no reload: netifd is not restarted by it).

**Enforcement.**

* The dial (`up`), after the registration and before anything of a data context (the IPA delegate, `AT+CGDCONT`,
  `AT+CGACT`): with data roaming off it asks the registration once. Roaming: no context; `$ROAM_HELD`
  (`/run/mu300/data-roaming-held`, its line the slot) is written, one line goes to `radio.log`, syslog and stderr -
  only when the hold begins - and the "down on purpose" marker (`/run/mu300-mobile-data-down`) is set, so the data
  cap's count of "data is up" stays right. Under netifd it exits 4: `mu300cell` reports `DATA_ROAMING` and netifd
  tries again after 60 s (`MU300_ROAM_RETRY`), which is how data comes back at home; a held try costs the radio-on
  check, `AT+CAVIMS=1` and two registration reads, and activates nothing. On Ubuntu it returns 0 (the service is not
  "failed" and systemd does not restart it every 30 s), and the watchdog brings data back. Home, or allowed: the hold
  ends (one line) and the dial goes on. The registration unreadable with data roaming off: a failed dial ("could not
  tell"), retried like any other, and no hold.
* The watchdog, while held: no reconnect and no "mobile data lost". OpenWrt: nothing is dialled (netifd's retries
  own it); a wan somebody took down (netifd's `autostart` false: `ifdown`, the panel's button, the data cap) ends the
  hold. Ubuntu: one `AT+CEREG?` a round; home or allowed ends the hold and dials once. `mobile-data down` (the service
  stopped by hand, from Cockpit, by the data cap) ends the hold first, so data that somebody turned off is not
  brought back. While mu300-power holds the modem down (suspend) the round does nothing.
* The watchdog, a live connection: with data roaming off it asks the registration once a round (one more AT
  command; with the default nothing more is asked than before). Roaming: the hold begins and the data goes down once
  - OpenWrt `ifup wan` (netifd's own teardown, then its dial holds), Ubuntu the `down` path (`AT+CGACT=0`, routes,
  NAT). The next rounds see the hold: no loop.
* The U30 Air's first-data check for SIM2 (§74, `sim_data_wait`) gives no verdict while data is held for roaming
  (registered, no data on purpose), so a roaming SIM2 is not sent back to SIM1 with a restart.
* Not touched: the radio, the registration, `AT+CAVIMS=1` (IMS, sent before the gate), SMS, USSD, calls, emergency.

**Status.** `mobile-data roaming`: the setting, the network (home, roaming, unknown; asks the modem) and "mobile data
held back: roaming, and data roaming is off". `mobile-data roaming --json`: `{"allowed","held","slot","per_sim",
"slots":[slot 0, slot 1]}`, files only. `mobile-data status` adds "roaming: yes, data not allowed while roaming".

**Front ends.** OpenWrt panel: the dashboard's Data roaming row (Allowed / Off / "Off: data held back while
roaming"), a Data roaming button in Quick controls (the card in use; `mu300dash act roaming on|off`, nothing else
accepted, which runs `mobile-data roaming`), and LuCI's wan page (one flag per card next to its APN). Ubuntu: Cockpit's
MU300 page (Mobile data card: the row and a button, `mobile-data roaming on|off` through Cockpit's administrative
access, argument by argument). Both: `mu300-toolkit` -> Network -> Mobile data: data roaming. The web device manager
(PR #244) reads and writes the same command.

**Test hook (device tests only).** A regular file `/run/mu300/roaming-test`, owned by the user `mobile-data` runs
as (root), not a link, whose line is `home-as-roaming`, makes stat 1 and 9 count as roaming. `/run` is RAM, so it is
gone at the next boot. No front end writes it and nothing a front end sends reaches the name.

**Device checklist** (items 1-5 run on 2026-10-15, below; item 6 not yet):

1. A home SIM, nothing set: `sudo mobile-data roaming` says "data roaming allowed", "network home"; data as before.
2. `sudo mobile-data roaming off`: with the home SIM the data stays up (the watchdog asks CEREG and finds 1); the
   dashboard says Off.
3. Force the roaming branch: `echo home-as-roaming | sudo tee /run/mu300/roaming-test`. Within 30 s: one line
   "registered on a roaming network and data roaming is off" in `/run/mu300/radio.log` and the log, data down
   (OpenWrt: the wan shows `DATA_ROAMING` and retries each minute; Ubuntu: `systemctl is-active mu300-mobile-data`
   still active), the dashboard "Off: data held back while roaming", SMS still send and arrive. No second line in
   five minutes.
4. `sudo mobile-data roaming on` (or remove the hook file): data back within a minute, one line "mobile data comes
   back". Then `off` again with the hook and `sudo rm /run/mu300/roaming-test`: data back at "home" the same way.
5. While held: `ifdown wan` / `systemctl stop mu300-mobile-data`, then remove the hook: data stays down (somebody
   turned it off). U30 Air: the same on SIM2, with `roaming_internal`.
6. Abroad, or with a SIM that really roams: the network row says roaming; off holds, on dials.

**On the devices (2026-10-15).** The branch's `mobile-data`, `mu300cell.sh`, `mu300dash`, the dashboard's
`action`/`dashboard-info`, `mu300cell.js`, `mu300-sim2-warmup` and `mu300-toolkit` copied over v2026.10.27 on a U30
Air (OpenWrt 25.12.5, kernel 6.18.56, SIM1 in use with data, the VPN up over it) and the Ubuntu files on an F50
(Ubuntu 24.04, kernel 7.2.10, its card with data); the watchdog restarted on each.

| item | U30 Air (OpenWrt) | F50 (Ubuntu) |
|---|---|---|
| 1. nothing set | "data roaming allowed", "network home"; `--json` `per_sim: true`, slots `[true,true]`; data and the VPN as before | the same, `per_sim: false`; no `mobile-data.conf` was there |
| 2. `off` | `network.wan.roaming='0'`; the wan stays up (45 s, the watchdog's rounds asking CEREG); the dashboard's `wan.roaming` `{"allowed":0,"held":0}`; the exit IP through the VPN unchanged from the Mac | the file `MU300_DATA_ROAMING=0`, mode 600; data stays up |
| 3. the hook | the line in `radio.log` and syslog 6 s after the hook; the wan `DATA_ROAMING`, pending, set up again every 60 s by netifd; the dashboard `{"allowed":0,"held":1}`; `mu300-sms send 7000 KALAN` sent and the carrier's answer arrived while held; one line in 4.5 min (5 netifd retries) | the line 6 s after the hook; no default route, no address; `mu300-mobile-data` still active, 0 restarts; `mobile-data status` "roaming: yes, data not allowed..."; no second hold in 7 min |
| 4. `on`; `off` + hook, then the hook removed | wan up 21 s after `on` ("allowed, mobile data comes back"); with `off` down in 15 s; the hook removed: up in 64 s ("on the home network, mobile data comes back"), VPN exit IP back | up 28 s after `on`; down 36 s after `off`; up 33 s after the hook went ("on the home network") |
| 5. taken down while held | `ifdown wan`, hook removed: 100 s later still down, `autostart: false`, the hold file gone, no "comes back"; `ifup wan` brought it back | `systemctl stop mu300-mobile-data`, hook removed: 100 s later no default route, the service inactive, the down marker there |

The panel's action through ubus: `act roaming off` / `on` wrote `network.wan.roaming`, `act roaming bogus` was
refused ("Invalid argument for this op"). `mobile-data roaming off|on --slot 1` wrote `roaming_internal` alone and
`--json` showed it per slot. Everything set was unset again afterwards (`uci delete`, the F50's file removed).

One defect, fixed: on Ubuntu the hold's line was twice in the journal (logger's, and the same line on stderr of the
watchdog, whose stderr is the journal). stderr now gets it only when `JOURNAL_STREAM` is not set (a dial by hand);
`test_the_hold_is_said_once_in_the_journal`.

**Not verified.** Item 6: no SIM that really roams was at hand, so whether this modem reports 5 for national roaming
or an MVNO at home is not known; the roaming branch was reached only through the test hook (stat 1 read as 5). The
U30 Air's SIM2: its card in this unit registers for emergency service only (stat 8, §74) and never gets data, so
the hold on SIM2 and `sim_data_wait`'s "no verdict while held" were not run (a switch to it goes back to SIM1 by
design); only its setting (`roaming_internal`) was. Cockpit's MU300 page (the panel extra was not installed on the
F50) and LuCI's wan page were not opened; the panel's backend was driven through ubus.

## A Magisk zip on a computer

### 111. One zip, two ways in: Magisk on the device, or unpacked on a computer as the computer's installer

**Status: current; unit and integration tests only - no device was used (other work had the devices).** The owner
asked for kano's two-entry package for this project's zips: kano (kanoqwq, branch `clean-tf-7.2`, MIT) ships one ZIP
that Magisk installs and that, unpacked, is a desktop installer (`f6b0668d` "add desktop deployment", `53ef7b1a`,
`1f8f03fb`, `0e19fe32`). His was read, none of it run, no binary of it taken.

**What a zip is now.** Everything it held stays where it was, byte for byte, with the same zip modes (checked: the 11
zips of v2026.10.27 built with `tools/make-magisk-zips.sh` of `main` and of this change differ in the new entries and
in `mu300/i18n/*.tsv`, which gained this change's translations, and in nothing else). Added at the top:
`START-HERE.md` (the zip's system, kernel and release written in; English, Turkish, Chinese), `start.sh`/`start.cmd`,
`start-gui.sh`/`start-gui.cmd`, `uninstall-linux.sh`/`.cmd`, and `computer/`: the project's installers for a computer
(`android/magisk/computer/files.txt`: `install.sh`, `install.ps1`, the uninstallers, their `tools/`, `boot/init` and
`build-boot-image.py`, the vendor extractors, `i18n/`, `gui/`, the switch module) with `computer/.mu300-package`.
68 files, 0.99 MB unpacked, **0.33 MB** more per zip (v2026.10.27: 331 412 to 331 422 bytes). The payload is in a
zip once: the computer's installer reads `payload/` where it is.

**Why Magisk cannot see it.** `customize.sh` sets `SKIPUNZIP=1` and unpacks exactly `mu300/*`, `module.prop`,
`action.sh`, `switch.sh`, `bootchain.sh` and `system/*`; nothing added is under those names. A test runs
`customize.sh` in a fake Magisk environment on a zip built with the computer's side and on the same zip without it -
a dry run and a whole installation on the fake device - and compares the output, `boot_a`, `misc`, what `boot_b`
holds and the module: equal (`tests/test_magisk_zip.py`, `MagiskPathUnchanged`). The release's real zips, both
builds, also pass `ReleaseZips` (each zip's own installer, a dry run). The web installer's `zip.js` reads the central
directory only for `mu300/manifest` and `mu300/install.sh`: a test reads the 11 built zips with it.

**How the computer's side installs that zip's system and kernel.** `tools/package.sh` (and the same in `install.ps1`,
and `gui/mu300gui/package.py` for the window): the package is `MU300_PACKAGE`, `--package DIR` / `-Package DIR`, or
the folder above `computer/` when `.mu300-package` is there (the launchers set `MU300_PACKAGE` to their own folder
and put `platform-tools/` on the PATH when it is there). Its `mu300/manifest` is read as the zip's own installer reads
it (only its nine keys, never sourced, every value exactly one a release has - they become file names; Ubuntu 26.04
with 5.4 refused). Then: no self-update (the installer that came with the files is the one that knows them), the
release is the manifest's tag, and the questions of the system, Ubuntu, kernel, release, beta and web panel are not
put. At the `download` step both payload files must have the checksum the manifest names **and** the one the
release's `mu300/SHA256SUMS` names (`verify` events; a mismatch or a missing file stops the run before anything is
written). The VPN module stays a download when it is asked for; the web panel is a release file, not a zip's. A
V50 with a 5.4 zip is refused at the choices, with the zip to take.

**The boot image without the 5.4 bundle.** `install.sh` always unpacked `mu300-kernel.tar.gz` for the first ramdisk
segment's busybox, logdw and 5.4 modules, even with a mainline kernel - and a 6.18 or 7.2 zip has no 5.4 bundle (it
would add 27 MB to 8 zips). Under a mainline kernel those three are dead weight: the kernel's generic segment is
unpacked after the first and brings its own `bin/busybox`, `bin/logdw`, `etc/module-order`, modules and `init`
(this checkout's `init` goes behind both, as before). The zip's own Magisk installer never put them in (its device
segment plus the bundle's generic one). So `build-boot-image.py` now takes `--busybox`, `--logdw` and `--modules`
as optional **only with `--append-ramdisk`**, and then decompresses that segment and refuses when it lacks any of
`bin/busybox`, `bin/logdw`, `etc/module-order`, `init`. A package with a mainline kernel builds the image that way;
everything else (every copy of the project, a 5.4 package) builds it exactly as before. Checked with the real 7.2
bundle of v2026.10.27: built, 1 879 018 bytes of ramdisk, no 5.4 module in it.

**adb: not bundled.** Google's platform-tools come under the Android Software Development Kit License Agreement
(https://developer.android.com/studio/terms), section 3.4: "you may not copy (except for backup purposes), modify,
adapt, redistribute, decompile, reverse engineer, disassemble, or create derivative works of the SDK or any part of
the SDK", except "to the extent required by applicable third party licenses"; 3.5 leaves the open-source components
to their own licences. adb's source is Apache-2.0, but the prebuilt binaries and the Windows USB DLLs are Google's
SDK distribution - not clearly allowed, so not bundled. kano's GUI release does bundle `adb.exe` and its two DLLs
with an `ADB-NOTICE.txt` (`installer/platform-tools.json` pins platform-tools r37.0.1). Here `START-HERE.md` says
where to download them and to unpack them into the zip's folder; `find_adb` / `FindAdb` and the launchers find
`platform-tools/adb` there.

**kano's and this one.** His package moves the original Magisk files into `payload/` and wraps them with a
path-switching `customize.sh`; his desktop installer (`desktop/installer.py`, an EXE when built) is a deployment of
its own - TF card, a userdata image, a GPT partition, offline shrink in a desktop initramfs, reset and resume, SSH
updates - for OpenWrt only, with a filtered copy of the rootfs prepared on the computer. Here the Magisk files stay
where they are, and the computer's side is this project's installers, which already handle every system, the SD
card, the free region, the boot chain and the GUI, pointed at the zip's payload: nothing of the install logic is
duplicated. Not taken: his EXE, his own deployment modes, the bundled adb (above); his reset-and-resume flow is
§112's subject.

**Tests.** `tests/test_magisk_zip.py` (the computer's side: files, CRLF launchers, exec bits, `START-HERE.md`, no
platform-tools, the list covers every file the installers name; `MagiskPathUnchanged`), `tests/test_package.py`
(`tools/package.sh`; `computer/install.sh` of real built zips against the fake adb, as far as the first pull: no
question about the system or kernel, the facts, a V50 and a 5.4 zip, a damaged manifest, `--build`, `start.sh`; the
window's choices and answers), `tests/test_boot_image.py` (the image without the 5.4 bundle, and the refusals),
`tests/web/logic.test.mjs` and `tests/test_web_installer.py` (zip.js), `tests/installer.Tests.ps1` and
`tests/answers.Tests.ps1` (the PowerShell side).

**Not measured.** An install from an unpacked zip on a device, on any platform; Windows Explorer's unpacking (the
launchers are CRLF and need no exec bit there; macOS and Linux keep the bits, and `sh start.sh` needs none).

## Making room on an encrypted Android

### 112. Making room by a reset, and the installation that resumes afterwards (EXPERIMENTAL; kano's flow, ported)

**Status: experimental. Run end to end once, on one F50 (2026-10-15/16, below): prepare, reset, resume, boot. kano
has not run its reset part (below).** The owner asked for kano's reset-and-resume flow (kanoqwq,
branch `clean-tf-7.2`, MIT; commits `f6b0668d` 2026-10-14 "add desktop deployment", which brought
`desktop/installer.py`'s transaction, `validate_resume`, `resume_payload_id` and `desktop/boot/part-prepare.sh`, and
`0e19fe32` 2026-10-15, which added the GUI's journal around it). The owner's word (2026-10-15): "if kano did it, we
don't need to test it, take it." kano's code was read; none of it was run here and no binary of it was taken.

**Why the make-room path changed.** It used to shrink `userdata` from the running Android, then zero the first
32 MiB of it so that Android would "format /data cleanly on the next boot" (§9b, §57). These devices keep `/data`
with file-based and metadata encryption (§9: `dm-default-key`, the key in `/metadata`). A raw filesystem zeroed from
outside then decrypts to noise under the old key, so Android cannot mount it. It reboots into recovery with
`--prompt_and_wipe_data`, and that prompt waits for a person at a screen. The F50, U30 Air and V50 have no screen.
kano's answer is to ask recovery itself for the reset. That is AOSP's bootloader message in the first 2 KiB of
`misc`: `boot-recovery` at 0 and `recovery\n--wipe_data\n` at 0x40. Recovery formats `userdata` at its new size and
resets the encryption with it. His `part-prepare.sh` says "the vendor flashing tool's erase-userdata writes the same
block, zeroed in full". That is the one piece of device evidence he gives for the mechanism.

**What his flow does, and what this port does.**

| kano (`desktop/installer.py`, `part-prepare.sh`) | here (`tools/resume.sh`, `tools/resume.py`, `install.ps1`) |
|---|---|
| backup on the computer in `~/mu300-backups/<date>-<cid>`: both GPT copies, misc, boot and the boot chain of both slots, `SHA256SUMS` | the same, each file checked against `sha256sum` on the device; the NV and calibration partitions are never read |
| `transaction.json` saved before the first write (`prepared-request`); serial, slot, `storage` (CID, node, start, size, disk), target, need, token, payload identity | the same fields, written atomically by `resume.py new`; `prepared` once everything is written |
| stage one in a desktop initramfs on the Linux slot: checks the request against the device, carves `userdata` and a `mu300root` GPT partition, writes the token to its first sector, writes the BCB and Android's slot to misc, reboots | from the running Android, as this project's make-room path always did: the new table (the backup copy first, both read back, resize-last-partition.py checks both and every CRC), the token in the first 4 KiB of the region behind `userdata` (read back), the BCB (read back, and the A/B block behind it unchanged). No GPT partition: this project's Linux region stays unpartitioned (§9) |
| recovery formats the smaller `userdata`; Android starts as new; the user sets it up, enables USB debugging and restores root | the same; the installer says so, and that Magisk's app and grants were in the erased data |
| `resume-internal-install`: the newest transaction under `~/mu300-backups`, or `--transaction` | found by itself on the next run (newest waiting for this serial and CID), or `--resume` / `--transaction FILE`; `--no-resume` ignores it |
| `validate_resume`: CID, node, start, slot, serial; userdata size equal to the target; root geometry; the marker `MU300-PART-PREPARED-V2 <token>` unless the record says installed | the same, plus the table read back (both copies, every CRC; its first, end and usable end), the region by `FreeRegion`/`region_probe`'s arithmetic, and the BCB: a reset that has not run yet (misc still asks for it) is said as such, before anything else |
| `resume_payload_id`: the checksums of his boot image, rootfs, filesystem tools and kernel family, not of prompts or paths | the checksums of the tools that decide what a resumed install writes where: `resize-last-partition.py`, `storage.sh`, `android-install.sh`, `android-mount-mu300root.sh`, `boot/init` (and, from an unpacked zip, its two payload files: §111). The installer does not update itself while a transaction waits |
| state `installed` after the boot image is written | the same, after `write_linux_boot` |
| `encrypted()`: encrypted state or type, or `/data` on dm, is encrypted; `unencrypted` with an F2FS/ext4 magic is not; anything else raises | the same rule (`resume.py encrypted`); an unknown state stops the make-room path, nothing changed |

What kano has that is not ported: the preserving offline shrink for an unencrypted `userdata`. This project's
make-room path always erases. Also not ported: his desktop initramfs and its tools, the free-GPT-gap install into a
new partition, and the userdata image. Where this differs on purpose: the token. kano writes it offline, with nothing
mounted. Here it is written while Android still has the old, larger `userdata` mounted. f2fs may write into its old
tail until the restart and overwrite the token. That is unlikely (the token is one 4 KiB block at a 2 MiB boundary,
written right before the restart), and if it happens the resume refuses with "token mismatch" and writes nothing.
`--no-resume` then installs into the region as into any space that holds data (`overwrite` typed). It is the same
failure his flow stops on, without its cause.

**What survives the reset, and where the transaction lives.** The reset formats `userdata`, and with FBE its keys
in `/metadata`. `/sdcard` (`/data/media`) and `/data/local/tmp` are in it. So nothing the installer could put in
Android's storage survives, and the transaction lives on the computer, as with kano. On the device, the reset leaves
what lies outside `userdata`: the new partition table, the token at the start of the region (outside every
partition from then on), `boot_a`/`boot_b` (Magisk's patched boot included), the boot chain and the A/B block in
`misc`. Recovery clears the BCB once it has run.

**What kano says he measured** (his notes, `docs/DESKTOP-INSTALLER-PORT.zh-CN.md` and `desktop/README.md` of
`f6b0668d`, `installer/VERIFICATION.md` of `0e19fe32`; translated from Chinese where marked):

* 2026-10-13: "MU300 实机缩容、原厂 recovery 重置/续装、完整部署后的重启和更新仍待验证" (translated: shrinking on a
  real MU300, the stock-recovery reset and resume, and the reboot and update after a full deployment still need
  verification).
* 2026-10-14, on a V50: "新版 EXE 对旧记录进行只读续装预检，通过 8.00 GiB 分区、身份、令牌及载荷校验。没有再次缩容或
  写独立分区" (translated: the new EXE ran a read-only resume pre-check against the old record and passed the
  8.00 GiB partition, identity, token and payload checks; no second shrink, no write to the independent partition).
  The same notes say a first stage existed on that V50 ("现有 8 GiB 分区可继续续装", translated: the existing 8 GiB
  partition can still be resumed into). They do not say how the reset went there.
* `desktop/README.md`: "Hardware installation, especially stock-recovery reset/resume, still needs real MU300
  validation before a release."
* 2026-10-15: "No connected-device installation, formatting, GPT mutation, userdata reset/shrink, boot-chain
  synchronization, misc write, live SSH upgrade or Magisk flash was performed."

**Tests.** `tests/test_resume.py`:
* the transaction: kano's wrong-device/geometry/marker cases, plus this project's own checks; the identity; `find`;
  the BCB and the marker; kano's encryption rule.
* `install.sh` as a whole against `tests/fakeadb.py` in its new `emmc` mode, real storage in a directory
  (`tests/fakeemmc.py`). The prepare is checked on what it wrote: only `userdata`'s end moved, then the token, the
  BCB with the A/B block unchanged, the order of the writes, the backup, and that no NV partition was read.
* the run before the reset (refused: "reset not run yet"), the reset (the kernel's view, recovery's format), the
  resumed run (no storage or overwrite question, the region as prepared), `--check`, `--no-resume`, `--resume`
  without a record, and a slot, token, geometry or identity that changed (each refused, nothing written).
* `tests/installer.Tests.ps1`: `install.ps1`'s `OfferRepartition` with the same writes on its own fake.
* `tests/test_gui.py`: the window's texts.

**Before this is used on a device.**
1. The vendor's recovery honours `--wipe_data` from the BCB without a prompt (kano's evidence is the vendor tool's
   block, not a run).
2. The bootloader starts recovery from the BCB on a plain reboot.
3. Android starts after the reset with `userdata` at its new size.
4. Magisk's root can be brought back on a screenless unit (the Magisk app over adb, the Shell grant through scrcpy).
5. The token is still there after the restart.

Until then the path stays EXPERIMENTAL, and an SD card remains the way that erases nothing.

**A first device run, 2026-10-15 (an F50 the owner gave up for it): not done, the unit has room.** Read only, from
the SD card's Linux on it: the eMMC is 122159104 sectors (58.2 GiB), `userdata` (`mmcblk0p75`, the last partition)
runs from 12275712 for 41943040 sectors (20 GiB, ends at 54218751), and 32.4 GiB behind it belong to no partition,
the 64 GB layout of section 9. The region starts at 54222848 and already holds a `mu300root` ext4. The make-room path
only starts below 700 MiB of free region and without an SD card chosen, so it cannot run here without making a
32 GB layout by hand, which was not done. **None of the five checks above was done**; they still need a 32 GB unit
(or one whose layout is changed on purpose). What the unit did show, for the checks:
* No `recovery` partition; `boot_a` is a version 4 boot image with a ramdisk (Magisk's patch is there), `init_boot_a`
  is empty. So recovery is the `vendor_boot` ramdisk's, reached through the patched `boot` ramdisk (check 1 and 2
  run through Magisk's init on this unit).
* `misc` begins with a leftover bootloader message, `bootonce-bootloader`, and the unit boots normally with it on
  every start: this bootloader does not act on at least that command (check 2 stays open; `boot-recovery` may still
  be read). `resume.py`'s prepare replaces the first 2 KiB whole, and its "reset not run yet" test looks for its own
  message only, so the leftover changes nothing for it.
* Over USB, in Linux, the unit is `MU300LINUX-324950664950-2128e853` on the computer's adb list; a second F50 cloned
  from the same unit shows `MU300LINUX-324950664950-203d8329`, and in Android both would be `324950664950`. A
  resume on one computer with both in Android cannot tell them apart by serial; the eMMC CID in the transaction does.

**The same F50, the same day: the layout made by hand, the prepare, and the reset (checks 1 and 2).** The owner
decided to make the 32 GB situation on this unit: a full image of the eMMC first (kept on his computer only, the
sha256 taken on the device and matched against the file's; 58.25 GiB read in 698 s over SSH, 16.2 GB as zstd -1),
then `userdata` grown to the end of the usable area with `tools/resize-last-partition.py --fill`, as a vendor flash
leaves it (§57, issue #32): 12275712..122155007 (52.39 GiB), written from the SD card's Linux, the backup copy first,
both read back. Android started on it without a word: `/data` stayed a 20 GiB f2fs on a 52.39 GiB partition (its
fstab has no `resize`), `ro.crypto.state=encrypted`, `ro.crypto.type=file`, FBE v2 with metadata encryption
(`fileencryption=aes-256-xts:aes-256-cts:v2+inlinecrypt_optimized`, `keydirectory=/metadata/vold/metadata_encryption`,
`formattable`), `/data` on `dm-39`; Magisk 30.7; bootloader locked, verified boot green; build
`F50_FLYMODEM_ZYV1.0.0B09`.

Then `install.sh` in answers mode (`MU300_STORAGE=internal`, the card's word `internal`, `MU300_ANS_MAKE_ROOM=yes`,
`MU300_ANS_LINUX_GIB=0.79`, `ERASE`, `MU300_ANS_REBOOT=no`): 27 seconds from start to `done` with `repartitioned=yes`,
`resume=pending`. The `makeroom.crypto` facts said `yes encrypted file`; the plan said that Android's own recovery
resets Android (a factory reset). The backup in `~/mu300-backups/<date>-<cid tail>` (the table, the misc header and
both slots' boot, uboot, sml, teecfg, trustos, vbmeta, each checked), the transaction saved before the first write,
userdata 12275712..120500223 (51.61 GiB), the region 120504320..122150912 (804 MiB), the token at its start and the
bootloader message in misc, all read back by hand afterwards as well: `boot-recovery` at 0, `recovery\n--wipe_data\n
--reason=mu300-make-room\n` at 0x40, the A/B block at 2048 as it was.

The reset, seen from the computer (USB location of the unit, once a second, after `adb reboot`):

| after | on USB |
|---|---|
| 0 s | `F50` 19d2:1353 (Android, adb) |
| 15 s | nothing |
| 28 s | `Unisoc Phone` 1782:4021, 13 s |
| 41 s | nothing |
| 58 s | `F50` 1782:4024 |
| 81 s | `F50` 19d2:1353, ECM and MTP, **no adb interface**; the stock web page at 192.168.0.1 answers |

Nobody touched the unit. So **check 2 holds** (the bootloader went to recovery from the message in misc on a plain
reboot: the 13 seconds as `Unisoc Phone` are recovery's; the leftover `bootonce-bootloader` above was not honoured,
`boot-recovery` is), and **check 1 holds as far as a screenless unit shows it**: recovery did not wait for a person, it
restarted into Android by itself within a minute and a half, and Android came up without USB debugging, which is what
a cleared `/data` (its persistent properties) looks like. Checks 3 to 5 (the new size of `/data`, root back, the
token) need USB debugging and Magisk back, by hand; the resumed run then reads them.

What the run showed in the installer (fixed with tests in the same change as this text):
* "userdata now" printed userdata's sectors as bytes ("0.1 GiB" for 52.4 GiB).
* "Android's data" printed `./install.sh: command substitution: line 490: syntax error` and the raw text: a `case`
  inside `$(...)`, which macOS's `/bin/bash` 3.2 cuts at the first `)`.
* The region came out smaller than the answer: userdata ended `lin` sectors before the usable end, and the region
  the installers find behind it starts one 2 MiB block after userdata and stops one block short of the disk's end.
  0.79 GiB gave 804 MiB here (enough for OpenWrt's 800), but the smallest answer the question took, 0.78125, would have
  left 796 MiB, and the resumed run would have refused OpenWrt after Android was already reset; 1.6 for Ubuntu the
  same. Now userdata ends where that region is exactly the answer, and an answer whose region is below 800 MiB is
  refused before anything is written (`install.sh`, `install.ps1`).
* `--check` with a usable SD card in the slot ends at "the installer will offer the SD card" and never shows the
  make-room figures; a real run with `MU300_STORAGE=internal` goes on to them. Not changed.

Two things of the unit on the way, not of this path: the SD card left its slot for a moment while Linux ran from it
(the kernel log: `mmc1: card aaaa removed`, `EXT4-fs (mmcblk1p1): shut down requested`), after which nothing could be
started (every exec `I/O error`, even the SSH password check). A reboot through adb's sync service (`b` to
`/proc/sysrq-trigger`) brought it back, but on that boot the eMMC did not come up (`mmc_select_hs400es failed, error
-84`, `Failed to initialize a non-removable card`); a normal `reboot` after it did. And while Linux runs from the card,
`boot_b` and the two `runtimenv` partitions are written now and then (the boot log, the modem's NV server), so an
image taken from a running Linux is consistent everywhere but there.

**The same F50, 2026-10-16: checks 3 to 5, the resumed run and the first boot (the installer of 70a21b24, the
commit that prepared it).** The owner turned USB debugging on again and gave the shell Magisk's root by hand (check
4: it can be done; how, on a screenless unit, is his). Then, read from Android as root:
* **Check 3 holds.** `mmcblk0p75` starts at 12275712 and is 108224512 sectors (ends at 120500223, the prepared end),
  `/data` is a new f2fs on `dm-39` of 51.6 GiB (13527552 blocks of 4 KiB; it was a 20 GiB f2fs on the grown partition
  the day before), `ro.crypto.state=encrypted`, `ro.crypto.type=file`, `sys.boot_completed=1`, the eMMC CID the
  transaction's.
* **Check 5 holds.** The 4 KiB at sector 120504320 are `MU300-PREPARED-V1 <the transaction's token>` and zeros.
* misc: recovery cleared the first 2 KiB in full (zeros; the leftover `bootonce-bootloader` went with them), and the
  A/B block at 2048 is byte for byte the one of the prepare's backup (sha256 of 2048..4095 the same).

`install.sh --check` (`ANDROID_SERIAL`, the SD card still in): "A prepared installation is waiting", `resume.check`
`RESUME-OK`, region 61698211840 (sector 120504320), 843055104 bytes, `verdict.code` `resume`, nothing written.

**The resumed run** (answers: OpenWrt plain, kernel 6.18, Android by default, the confirmation `@stdin` to read the
summary first). It found the transaction by serial and CID by itself, asked no storage or overwrite question, said
"this device has 0.8 GiB: only OpenWrt fits" and took release v2026.10.27. The first try stopped at "Building the
boot image": `TypeError: object of type 'PosixPath' has no len()` in `boot/build-boot-image.py`. That is not of this
path: the boot image's manifest (`edb57d80`, 2026-10-15) counts `len(order)`, and the U30 Air's `--device-modules`
loop reuses `order` for its order file's path, so **every install from a computer since that commit stopped there**
(`install.sh` and `install.ps1` pass `--device-modules` whenever the 5.4 bundle has `modules-u30air`, and the
release's always does). Nothing had been written; the transaction stayed `prepared`. Fixed with a test
(`tests/test_boot_image.py`), the fix put on the 70a21b24 checkout (the file is not one the transaction is bound to),
and the run again: the summary said `writes: Linux region at offset 61698211840, boot_b, 32 bytes of misc (boot_a, GPT
and userdata are not touched)`; then `mke2fs` of an 804 MiB `mu300root`, OpenWrt with the hotspot's name imported,
`MU300-INSTALL-OK`, boot_b written and read back (the sha256 the image's), slot b armed for one boot, the Magisk
switch, `done result ok`, the transaction `installed`. The events in order: `hello` (prebuilt), `preflight`,
`storage`, `resume.transaction`, `resume.check RESUME-OK`, `storage internal`, `verdict.code resume`, `release`,
`choices` and the questions, `pull`, the downloads and `verify ok` x3, `vendor`, `bootimage`, `confirm` (`waiting`,
then `INSTALL`), `copy`, `device`, `boot`, `switch`, `done`. The ext4 superblock now covers the token (it is gone, as
it should be after the install).

**The first boot.** The installer's reboot, with the card still in: boot_b's new image (6.18.56) started and took
the SD card's OpenWrt as root (`stage=sd-root dev=/dev/mmcblk1p1`), as it prefers the card; misc went back to
Android's slot. The owner then took the card out, and from Android `su -c mu300-linux`: 22 s later the unit was
`MU300LINUX-324950664950-2128e853` on USB, 192.168.77.1 answered, `/etc/mu300/image-version` v2026.10.27, OpenWrt
25.12.5, kernel 6.18.56, `/run/mu300-root-dev` `mmcblk0@61698211840`, `/` on `loop0` (775 MiB, 18 % used), no
`mmcblk1`, SSH as root with the password of the answers. `mu300-next-boot android` and `reboot`: Android back, adb
`324950664950`, root.

**What the copies of the transaction showed** (`--transaction` on copies, the real file and the copies unchanged
afterwards, sha256 before and after):
* the CID changed: refused, "the device or its slot differs from the saved transaction (cid)";
* the slot changed, a real run: refused, the `error` event, stopped after `storage`: nothing written;
* `target` 2048 sectors smaller, a real run: "the prepared partition geometry differs (userdata is 108224512 sectors,
  the transaction made it 108222464)";
* the state put back to `prepared`, a real run: "preparation token mismatch; refusing to overwrite the region" (the
  ext4 has the token's place): a resume cannot run twice;
* a `prepared` copy in `MU300_BACKUP_DIR`: `--check` finds it and refuses it (token), `--check --no-resume` ignores
  it and says "a MU300 Linux installation is already present";
* an `installed` copy, unchanged: `RESUME-OK` (kano's rule: an installed record is not asked for its token), and the
  same copy with the installer of current `main`: "this installer's tools or the package differ from the ones that
  prepared the installation", because `tools/android-install.sh` changed since (the release-tag block). That is the
  design: a transaction is resumed with the installer that prepared it, and the installer does not update itself
  while one waits; one prepared before an update of these tools has to be finished with the old checkout.

**One more defect, of every installer, found on the way.** During one `--check --no-resume` another session
restarted adb's server; every read of the region came back empty, and the installer said "existing mu300root
filesystem: no", "data check:  of 16 samples", `[: : integer expression expected`, and "OK: free and empty" for a
region that held the Linux just installed. A real run would have skipped the update-or-wipe question and the
overwrite one. `region_find_existing` and `region_dirty` (and `install.ps1`'s copy) now take no answer for no
answer and stop ("no answer from the device"), with a test. `tools/storage.sh` is one of the files a transaction is
bound to, so this fix, too, refuses a transaction prepared before it.

Not changed, noted: `--check` reports a refused transaction and goes on to the ordinary verdict (`exit 0`); only a
real run stops on it. The systems question offers "3" as its default where only OpenWrt fits.

### 90. The data watchdog took a modem that did not answer for a lost bearer, and redialled a working connection

`mobile-data watch` asks `AT+CGACT?` every 30 s and reconnects after two rounds without our context active. Before
this change the test was `at "AT+CGACT?" | grep -q "+CGACT:1,1"`, so a round in which the modem gave no final
result code within 4 s, the client lock was busy, or the answer was `ERROR` counted exactly like a context the
network had taken down: two such rounds and the watchdog ran `up` (Ubuntu) or `ifup wan` (OpenWrt), which tears
down the bearer that was still carrying traffic. Nothing measured shows it happening on our boards; the case is
read from the code. It is the situation kanoqwq describes for a device on the move in clean-tf-7.2 `3cbf37fc`
("fix: improve cellular mobility"): AT owners can be busy while the modem moves between cells, and a timeout is
not a detach.

**Taken from 3cbf37fc:** the distinction itself - only an answer is evidence. **Changed:**

* His watchdog never escalates a silent modem and also treats "OK with no line for the context" as unknown. Ours
  keeps both of the old repairs: "OK" with `<cid>,0` or with no line for the context at all (what a firmware
  reset leaves, the reason the watchdog exists) is *inactive* and reconnects in two rounds as before; and a modem
  that stays silent for `MU300_WATCH_UNKNOWN_ROUNDS` rounds (4: about two minutes when every command fails
  at once, about 4.5 minutes when the daemon hangs, measured below) goes the old way (radio check,
  then a reconnect a round later), so a channel that only a radio-on would wake up is still woken. An answer in
  between starts the count over.
* Not taken: his switch of the radio only on an explicit `+CFUN: 0` (`radio_on` reads `AT+CFUN?` itself and does
  nothing to a radio that is on, so the old check costs a handshake, not a connection), and his `ubus ... renew`
  for an active context whose address changed: here only the relay monitor (`mu300cell-v6.sh`, relay mode) acts
  on a renew; in every other mode nothing would, so a changed address keeps the measured reconnect.

`watch_context` returns `active`, `inactive` or `unknown`; `+CGACT: 1,1` with a space and a CR are read too, and
`+CGACT:11,1` or `1,10` are not taken for context 1. Unit tests: `tests/test_device_scripts.py`
(`MobileData.test_watch_context_states`, `..._leaves_the_bearer_alone_while_the_modem_does_not_answer`,
`..._still_reconnects_a_modem_that_stays_silent`, `..._an_answer_between_silent_rounds_starts_the_count_over`,
`..._an_answered_lost_context_still_reconnects_in_two_rounds`).

**Measured on the U30 Air** (openwrt-luci v2026.10.27, kernel 6.18.56, SIM1, relay mode, the owner's VPN with its
kill switch on; 2026-10-15), with this branch's `mobile-data` in place of the release's:

* **No log on OpenWrt at all.** procd kept none of the watchdog's stderr (`mu300-post`'s `cellwatch` instance had
  no `procd_set_param stderr 1`, which every other long-running instance of ours has), so "mobile data lost ...
  reconnecting" never reached `logread` - not with this change, not before it. The device run below used a
  watchdog started by hand with its stderr in a file; the instance now sets `stderr 1`
  (`MobileData.test_the_openwrt_watchdog_logs`).
* **A silent channel.** The nr2 daemon (`MU300_AT_DIR=/run/mu300-at2`) stopped with `SIGSTOP` for 80, 85, 165 and
  200 s: no reconnect, the bearer's address unchanged, nothing in the log. One unanswered command takes about 35 s,
  not the 4 s asked for: `mu300-at -t 4` waits for a daemon that does not take the command off its fifo (measured:
  "no answer from the daemon" after 35 s, an answered `AT+CGACT?` in under 1 s). So a round of a silent channel is
  about 65 s, and the four rounds before the old repair take about **4.5 minutes**, not two. Stopped for 290 s:
  `no answer about the data context for 4 rounds`, then the radio check (`radio was off, switching it on`: the
  silent channel did not answer `AT+CFUN?` either), and the next round, answered again, started the count over -
  no redial.
* **A lost context** (`AT+CGACT=0,1` on the panel's channel nr6): `mobile data lost (modem reset or detached),
  reconnecting` 58 s later, `ifup wan`, the same address back, data through the tunnel again.
* **Airplane** (`AT+CFUN=0` on nr6): `radio was off, switching it on`, then reconnects - but on this U30 Air (dual
  SIM managed, FINDINGS 74) `+CFUN: 1` came back with the SIM's power off (`AT+CPIN?` `+CME ERROR: 10`, `+CEREG:
  2,8`, emergency only), and every attach failed ("not registered on the network") until `AT+SPACTCARD=0;+SFUN=2`
  and `AT+SFUN=4` by hand. `radio_on` returns early when `/run/mu300/sim-managed` exists, so the watchdog's repair
  cannot power a card back on there. Unchanged code (`radio_on` is the release's); left for the dual-SIM work.
* Not this change, seen on the way: on Ubuntu (F50), stopping the watchdog logs `wlock: unbound variable` (the
  `EXIT`/`TERM` trap names a `local` of `watch()`); on OpenWrt a `TERM` is caught by that trap and the watchdog runs
  on without its lock. Both are the release's.

Device checklist (either board, either system):

    # 1. normal: data up, then watch the log for five minutes - no "reconnecting"
    logread -f | grep mobile-data     # OpenWrt (with stderr 1);  journalctl -fu mu300-mobile-data-watch  on Ubuntu
    # 2. a silent channel: kill -STOP the nr2 daemon (MU300_AT_DIR=/run/mu300-at2 in its environment), kill -CONT it
    #    after under 4 min - no reconnect, the address unchanged; after 5 min the radio check, as above
    # 3. a lost context: AT+CGACT=0,1 on the panel's AT terminal - "mobile data lost ... reconnecting" within ~60 s,
    #    data back as before
    # 4. airplane: AT+CFUN=0 - "radio was off, switching it on" and data back, as before
### 91. The relay monitor read SIM1's bearer in a dual-SIM boot on SIM2, believed any +CGCONTRDP, and dropped the hint after a burst

`mu300cell-v6.sh` is relay mode's event monitor (openwrt-luci, `option ipv6 'relay'`): it reports the RA's IPv6
to netifd and, on a `+CGEV`, reads `AT+CGCONTRDP=1` once and moves the bearer's IPv4 address and DNS in place,
without a redial. kanoqwq reworked his copy for mobility in clean-tf-7.2 `3cbf37fc`; comparing it with ours showed
one defect his commit does not name and three he does. All four are read from the code; none was seen on a device.

* **The wrong card (ours alone).** The monitor read the bearer on `/run/mu300-at6`, `at7`, `at` and the URCs from
  `/run/mu300-at/urc/stty_nr<slot*3>.log`, whatever the card. In a dual-SIM boot on SIM2 (`/run/mu300-radio-freeze`,
  FINDINGS 74) `/run/mu300-at` is SIM1's nr1 and SIM2's owner is `/run/mu300-at4`, whose URC log is
  `/run/mu300-at4/urc/stty_nr3.log`. So the monitor asked SIM1 (radio off: no bearer, "keeping the last state")
  and waited for a log that never appears: on SIM2, an address change was never followed, and the watchdog's
  reconnect was the only repair. It now picks the channels and the log the way `mobile-data` and the panel's
  collector do: SIM1 nr6/nr7/nr1 and `stty_nr0.log`; SIM2 pinned at boot `/run/mu300-at` (its nr4 then) and
  `stty_nr3.log` there; SIM2 in a dual-SIM boot `/run/mu300-at4`. A slot `mu300-sim` cannot name ends the monitor.
  No `AT+SPACTCARD=` prefix is added: each of these channels already belongs to the card it is used for.
* **What is believed (from 3cbf37fc).** The address must be four 0-255 parts without leading zeros and not
  `0.0.0.0`, the mask contiguous (the old `mask2prefix` turned anything unknown into /32), CR and blanks are
  removed, and a DNS of `0.0.0.0` (no second server) or one that is not an address is left out. Nothing else of
  the answer reaches `ip` or netifd.
* **A failed install keeps the old snapshot (from 3cbf37fc).** The new address and the route go in first; when
  one fails, the previous address/DNS stay the monitor's state, nothing is reported, and the next hint or renew
  tries again (before, the new values were taken as current and the next read said "unchanged"). The old address
  goes only after the new one holds, and then the new one is put in once more (the old primary takes a secondary
  of its subnet with it: no `promote_secondaries`, as in `mu300cell.sh`'s setup). An unchanged bearer whose
  address the kernel lost is put back.
* **Hints (from 3cbf37fc).** `+CGEV` ACT/DEACT (the short `NW ACT` forms) and DETACH and Unisoc's `+SPPCODATA`
  now ask for a read besides PDN and MODIFY. A hint in the 2 s after a read used to be dropped - possibly the last
  of a burst, the one after which the new address is readable; it now waits out the rest of the 2 s. One queued
  read covers a burst: the producer sends a hint only when it creates `/run/mu300cell-<config>.events.pdp` (a
  directory: `mkdir` is atomic and never follows a symlink), the reader removes it just before its AT read.

**Not taken from 3cbf37fc:** the monitor for an IPv4-only context (relay mode is dual-stack only here; an IPv4-only
bearer keeps the watchdog's measured reconnect), the exit to netifd after three readings of an inactive context
(the watchdog owns that repair: FINDINGS 90), `proto_set_keep 0`, and his watchdog's `ubus ... renew`.

Unit tests: `tests/test_mu300cell.py` class `RelayMonitorBearer` (the monitor sourced with `MU300CELL_V6_LIB=1`):
the channels and log per slot and dual-SIM state, `mask2prefix`, `valid_ipv4`, `read_bearer`, add-before-delete,
failure and retry, the lost kernel address, the hint patterns. Under dash and bash locally, busybox sh in CI.

**Measured on the U30 Air** (openwrt-luci v2026.10.27, kernel 6.18.56, SIM1, `option ipv6 'relay'`, 2026-10-15),
this branch's monitor in place of the release's and `ifup wan` to start it:

* The monitor tails `/run/mu300-at/urc/stty_nr0.log`. `ubus call network.interface.wan renew`: `manual-renew:
  bearer unchanged`. `ip -4 addr flush dev sipa_eth0 scope global` and a renew: `manual-renew: bearer updated to
  <the same address>/8`, the address and the default route back, no ifdown, no redial.
* **The checklist's `AT+CGACT` cycle on the panel's terminal does not reach the monitor**, on this branch or the
  release's: the `+CGEV: ME PDN DEACT/ACT` of a command sent on nr6 are answered on nr6 only (they came back with
  the command's own reply) and never reach nr0's URC log, which only has what the modem announces there. So the
  hint path was driven by appending lines to that log: six hints at once (`NW PDN DEACT`, `NW DETACH`, `NW PDN
  ACT`, `+SPPCODATA`, `NW MODIFY`, `ME PDN ACT 1,0`) gave one read (`cgev: bearer unchanged`); a hint and another
  2 s later gave two reads, 2 and 5 s after the first (the release's monitor drops the second); lines that are not
  hints, none.
* **SIM2 not run as a boot:** this unit's second card registers for emergency service only (§74), so a boot on it
  has no bearer, `mu300cell` never connects and the monitor never starts. The choice of channels and log was run
  under the device's own busybox sh instead (a copy of the monitor, `mu300-sim` stubbed, the freeze flag a file):
  slot 0 `/run/mu300-at6 /run/mu300-at7 /run/mu300-at` + `stty_nr0.log` with or without the flag; slot 1 without it
  `/run/mu300-at` + `stty_nr3.log`; slot 1 with it `/run/mu300-at4` + `/run/mu300-at4/urc/stty_nr3.log`.
* Seen on the way, not this change: after the WAN was redialled several times by these tests, the VPN's sing-box
  logged `network: missing default interface` and stayed without an exit until `/etc/init.d/mu300-vpn restart`.

Device checklist (openwrt-luci, relay mode):

    # 1. F50 or U30 Air on SIM1: the monitor runs and follows a change
    ps w | grep [m]u300cell-v6; logread -f | grep mu300cell-renew
    #    a network-side change (or URC lines appended to /run/mu300-at/urc/stty_nr0.log): one "bearer updated"/
    #    "unchanged" line per burst, no ifdown. AT+CGACT on the panel's terminal (nr6) is answered on nr6 only.
    ubus call network.interface.wan renew        # "manual-renew: bearer unchanged"
    # 2. U30 Air, a dual-SIM boot on SIM2: the monitor's tail is on /run/mu300-at4/urc/stty_nr3.log and its reads
    #    go to /run/mu300-at4 (ps w | grep 'tail -n 0 -F'); the same AT+CGACT cycle on SIM2
    # 3. a lost address: ip -4 addr flush dev sipa_eth0 scope global; ubus call network.interface.wan renew
    #    - the address is back without a redial
### 92. Three Wi-Fi TX log lines written once per frame; the AP multicast "endian fix" not taken

kanoqwq's clean-tf-7.2 `3cbf37fc` brought two Wi-Fi changes from his T551M work to the SC2355 driver. Both were
compared with our `upstream/modules/sprd_wlan_combo` (the mainline kernels' module) and with what our bridge does.

**Taken: per-frame logs bounded.** In AP mode the TX path wrote, for every frame, `pr_info("... group
lut_index=...")` when a group-addressed frame found its LUT entry (every broadcast and multicast frame sent), and
`pr_err("... sta disconn, no data tx!")` for each frame still queued for a client that has left; every frame
`sprd_send_data` refused was `netdev_err(... drop msg due to TX Err)` on top. The first two are now
`pr_debug_ratelimited` (as the module's other per-frame lines already are, `pcie.c` `free_num`, `tx.c` "no
credit"), the third is under `net_ratelimit()`. Nothing else changes: the frame is still refused with `-EPERM`,
still freed with its message (`dev_kfree_skb`, `sprd_chip_free_msg`), the same return values. Both `pcie.c` and
`sdio.c` (only the PCIe path runs on the F50 and the U30 Air). Not measured: how much of the kernel log these lines
filled on our boards (no report of it); kanoqwq's concern is the CPU a burst of them costs when a busy client
drops off. The 5.4 driver (`kernel/patches/wlan_combo-*`) is not changed here: his 5.4 patch was written against
the realme source, which is not in this repository to check that it applies, and a hunk that fails stops the
release build.

**Not taken: the AP/GO multicast "endian fix".** In `sc2355/rx.c` the AP's receive path compares `eth->h_proto`
(big endian) with `ETH_P_IP`/`ETH_P_IPV6` (host order), so on this CPU the "not IP" test is always true and every
group frame a client sends is copied back to the BSS by the driver *and* handed to the stack. His fix (`htons()`)
makes IP multicast go to the stack only. That is a behaviour change, not a bug fix, for us: a Linux bridge never
sends a frame back out of the port it came from unless that port has hairpin mode, and nothing in this tree sets
hairpin on `wlan0`. Without the driver's copy, mDNS, SSDP, LLMNR, IPv4 broadcasts and IPv6 ND multicast from one
Wi-Fi client would no longer reach the other clients of the same radio (a phone casting to a TV on the same
hotspot). Where hairpin *is* on (OpenWrt's netifd turns it on for a wireless port with `multicast_to_unicast`), the
present code gives a duplicate, which is harmless for these protocols. A comment at the branch says so, so it is
not "fixed" blindly. Measure before changing it:

    cat /sys/class/net/wlan0/brport/hairpin_mode /sys/class/net/wlan0/brport/multicast_to_unicast 2>/dev/null
    # two phones on the same band: mDNS between them (e.g. a Chromecast/AirPlay target, or `avahi-browse -a`),
    # tcpdump -ni wlan0 udp port 5353 on the device: one copy or two per query

Device checklist for the taken part (either board, 6.18 or 7.2):

    dmesg -C; # a busy client (a download) on Wi-Fi, then switch its Wi-Fi off
    dmesg | grep -c 'sta disconn'              # 0 (debug only) - before: one line per queued frame
    dmesg | grep -c 'group lut_index'          # 0 - before: one line per broadcast/multicast frame
    echo 'module sprd_wlan_combo +p' > /sys/kernel/debug/dynamic_debug/control   # the lines are there, bounded
    # the hotspot keeps working: a second client, ping and a download

**Measured** (2026-10-15) on a test kernel with §92, §93, §102 and §103 together (main of that day plus the four
branches): the F50 on Ubuntu 24.04 with 7.2.10, the U30 Air on openwrt-luci with 6.18.56, a MacBook on the 5 GHz
hotspot (802.11ac, 80 MHz) as the client; against the release kernels of v2026.10.27 on the same devices. The
device sent to the Mac (bash `/dev/tcp`) and the Mac's Wi-Fi was switched off 4 s into it; the log then:

| | release kernel | test kernel |
|---|---|---|
| F50, `sta disconn, no data tx!` | 13 (error level, one per frame) | 0 |
| F50, `drop msg due to TX Err` | 13 | 12, with `net_ratelimit: 1 callbacks suppressed` |
| U30 Air, the same two | 10 and 10 | 0 and 12 (rate limited) |
| `group lut_index` | 0 | 0 |

`group lut_index` never appeared in any run on either kernel, so the first of the three lines is not one our
boards write in these tests. The hotspot carried on as before: TX to the Mac 300-590 Mbit/s on the F50 and 210-500
on the U30 Air on both kernels (two clusters, about 320 and 570, on both: the Mac, not the kernel), 6 GiB in one
stream at 594 Mbit/s on the F50, IPv6 multicast (`ping ff02::1`) answered by the Mac over Wi-Fi. The hairpin
measurement above needs two Wi-Fi clients and was not made.
### 93. sdhci-sprd started ADMA transfers with relaxed MMIO: the descriptors were not ordered before the command

Mainline `drivers/mmc/host/sdhci-sprd.c` (both of our mainline kernels; the eMMC and the SD card slot) overrides
the SDHCI register accessors to handle its reserved registers - `SDHCI_MAX_CURRENT`, the read-only
`SDHCI_BLOCK_COUNT`, the interrupt mask, the hardware-reset bit - and then does the access with `readl_relaxed`,
`writel_relaxed`, `writew_relaxed`, `writeb_relaxed`. The SDHCI core relies on its accessors being the ordered
ones: it writes the ADMA descriptor table into DMA memory and then starts the transfer with a register write
(`SDHCI_COMMAND`, through `writew`). A relaxed MMIO write is not ordered after earlier stores to memory (Linux's
"device-io" rules; on arm64 `writel` is `__iowmb()` and then the store), so the controller can be told to fetch a
descriptor whose last store is not yet visible to it - a transfer from or to the wrong place. The vendor's 5.4
driver is not changed here (its source is fetched at build time and has not been read for this).

kanoqwq found this in clean-tf-7.2 `0438ab01` while chasing ext4 corruption on other Unisoc boards, and his
evidence is from there, not from ours: on an E5 (his other project), a directory block held the complete content of
an inode-table block, and file writes logged `mmc0: ADMA error: 0x02000002` with no CRC errors; after the change,
896 MiB written and read back with `O_DIRECT`, 3584 metadata updates and two offline `e2fsck -fn` were clean, at
HS400 with runtime PM on. He says himself that it is not proven to be the only cause. **We have no report of
corruption on an F50 or a U30 Air** (FINDINGS has none), so this is taken as the correct ordering by the kernel's
own rules, not as the fix of a symptom of ours.

**Taken:** the four accessors' final access becomes `readl`/`writel`/`writew`/`writeb`; every special case stays
(the reset bit's read in `writeb` keeps its relaxed read: it orders nothing against DMA memory, and the write after
it is the ordered one). **Changed:** his edit lives in his `emmc.py`; here it is `upstream/port/sdhci_order.py`,
called from `install.py` next to the other sdhci-sprd edits, idempotent, and the port stops (`port: ...`) when the
four lines are not exactly where they were - a kernel that changes them must be looked at again, as with the
other anchors. Not taken: his 5.4 patch (`kernel/patches/sdhci-sprd-dma-ordering.patch`), his eMMC power and
reliable-write changes (V50-specific, unproven by his own account), his CI C check.

Cost: one barrier (`dmb oshst` / `dmb oshld`) per register access of these two hosts; a transfer takes a handful.
Not measured.

**Unit tests:** `tests/test_sdhci_order.py` against a copy of mainline's accessor block (the edit, the kept special
cases, idempotence, a changed driver stops the port). The real tree is checked by the Mainline kernel build
workflow, dispatched on the branch. **Not run on a device. Hold the merge for a soak on each board:**

    # on the new kernel (both boards; 6.18 and 7.2)
    dmesg | grep -iE 'mmc[01]|ADMA|EXT4-fs (error|warning)'      # nothing new; HS400 as before:
    cat /sys/kernel/debug/mmc0/ios                                # timing spec: mmc HS400 enhanced strobe
    # throughput, before and after (same board, same free space): within noise
    dd if=/dev/zero of=/var/tmp/t bs=1M count=512 oflag=direct; dd if=/var/tmp/t of=/dev/null bs=1M iflag=direct
    # a soak: write/verify a few GiB, reboot ten times, e2fsck -fn on the root from Android or the initramfs
    # the SD card slot (FINDINGS 31j-31l): a card is seen, mounted, read and written; hot-plug still detected

**Measured** (2026-10-15) on a test kernel with §92, §93, §102 and §103 together (main of that day plus the four
branches), against the release kernels of v2026.10.27 on the same devices:

* **F50, Ubuntu 24.04, 7.2.10.** `mmc0` HS400 enhanced strobe at 200 MHz, as before. 3 GiB of random data in
  twelve files on the root filesystem (a loop over `mmcblk0` at the Linux region's offset, so every write goes to
  the eMMC), checksums, read back uncached: all right after writing and after each of five boots of the test kernel
  and one of the release kernel. `dumpe2fs`: clean. Then from Android, `e2fsck -fn` of the region through a
  read-only loop: no error (12318 files). No ADMA error, no `EXT4-fs error`, no I/O error in any boot.
* **U30 Air, openwrt-luci, 6.18.56.** HS400 enhanced strobe. The same 3 GiB soak on the Linux disk, checked after
  writing, after each of three boots of the test kernel and after the release kernel's boot: all right;
  `errors_count` 0.
* **Throughput** (256 MiB `dd` with `oflag=direct`/`iflag=direct` on the F50, three runs each; 1 GiB on the U30 Air
  in whole seconds): F50 file writes 179-195 MB/s on the test kernel and 189-217 on the release (the same spread
  on both when repeated), file reads 272-302 and 269-317, the raw `mmcblk0` read 264-267 and 203-264; U30 Air 1 GiB
  raw read 3-4 s, write with `fsync` 4 s, read back 3-4 s on both. No difference beyond the spread of runs.
* **The empty SD slot** (`mmc1`, F50): in one of the seven boots of the test kernel the probe's one rescan logged
  `Got command interrupt 0x00000001 even though no command operation was in progress` with a register dump (`Cmd
  0x371a`, CMD55; §31j has the cause); none in the four boots of the release kernel this session. Too few boots to
  tell a difference, and it is the slot without a card, not a transfer.
* **Not tested:** a card in the slot and hot-plug (none here; the U30 Air has no slot).
### 100. `mu300-next-boot`: the default boot written before misc was, and a re-arm that could undo a switch

From kanoqwq's clean-tf-7.2 `1f8f03fb` ("misc-only trial boot, protect switch flow"): his desktop installer's
"Boot OpenWrt once" changes the 32-byte `bootloader_control` block in misc and nothing else, and says so. Our Magisk
switch (`mu300-linux`, `switch.sh`) already works that way: it never mounts the Linux disk and never touches its
`default-boot`. The Linux side did not, which an earlier review of ours had flagged:

* **The file before misc.** `mu300-next-boot android|linux|lock` wrote `/etc/mu300/default-boot` first and misc
  second. The initramfs reads that file (§ default boot, `boot/init`): `linux` makes it skip restoring Android's
  slot. A misc write that failed (or read back wrong) left the file saying what misc did not.
* **No lock.** `mu300-boot-ok.service` runs `--rearm` at every boot: it reads the file, then writes the Linux slot's
  block. A `mu300-next-boot android` (the panel's Switch to Android, a shell) between the read and the write was
  overwritten by the re-arm: the next boot went to Linux again, with the file saying `android` (the initramfs then
  restores Android's slot, so the boot after that one was Android: one boot late, never stranded).

Changed (ours; nothing of his code, his change was to his desktop installer only):

* The file is written only after misc has been written and read back (`write_bc`; `PENDING_CONF` names the word
  that goes with the block). A failed `dd` now says `writing misc failed` instead of ending silently under `set -e`.
  The degraded arm of §32 (the initramfs' one-shot block, exit 1) still records `linux`, as before: misc was written.
* The file is written whole and never through a symlink: a new file next to it (`umask 022`, `set -C`), renamed
  over it.
* Every command but `status` holds `flock` on `/run/mu300/next-boot.lock` (fd 9) from its first read to its last
  write, waiting up to 60 s (`MU300_NEXT_BOOT_WAIT`) and then failing without writing anything. Without `flock(1)`
  (or without `/run/mu300`), or where the lock file is a symlink, nothing is serialised, as before. Ubuntu has
  util-linux's, OpenWrt busybox's applet.

**Bootability.** Every failure path leaves misc as LK last saw it or as it was verified, and the file as it was: a
failed `android` leaves Linux armed (the countdown or the next re-arm as before); a failed `linux` leaves the trial
mode, whose fallback is Android. A file that cannot be written after misc was is reported (exit 1): for `android`
misc already points at Android; for `linux` the initramfs keeps restoring Android's slot (one-shot trial). A lock
that is never released (a hung `mu300-next-boot`) costs one boot's re-arm; the slot still has its remaining tries.

**Unit tests** (`tests/test_device_scripts.py`
`NextBoot`): misc unwritable or the Android block missing, the file untouched; the file through a symlink; the
degraded arm; a stub `flock` that stays busy (refused after the wait, misc and the file untouched; `status` never
waits; a symlinked lock file not opened); and the real `flock(1)` holding off a second writer (Linux only; run in
the `mu300-unit` container).

**Measured on both boards** (2026-10-15), this branch's `mu300-next-boot` in place of the release's: the F50 on
Ubuntu 24.04 (util-linux `flock`), the U30 Air on openwrt-luci (busybox `flock`), both v2026.10.27, and boots of
the release and of a test kernel:

* `android`, then `linux`: the file says `android`/`linux` after each, misc `...9f001e...` (Android's block) and
  `...9e006f...` (slot b, tries 6) read back; no `.default-boot.*` left; `/run/mu300/next-boot.lock` there, root's.
* **The lock.** `flock /run/mu300/next-boot.lock sleep 10` held, then `android`: went through after 9 s. Held for
  100 s with `MU300_NEXT_BOOT_WAIT=5`: `another mu300-next-boot is still running`, exit 1 after 4 s, misc and the
  file as they were (`android`); `status` did not wait. The same on both boards.
* **The re-arm at boot** (F50: `mu300-boot-ok`, after its 30 s): with the lock held from 20 s into the boot until
  45 s, the service finished at 48 s with `slot b armed: 5 failed boot(s)` (tries back to 6). On the U30 Air
  (`mu300-post`'s `bootok`) the re-arm left `boots since the last good one: 0` and tries 6 after each of three boots; the F50
  came back to Linux at each of its nine boots under this script.
* `mu300-update kernel` (which runs `--trial`) under this script on both boards, then the boot of that kernel: armed
  and re-armed as before.
* F50: `mu300-next-boot android` and a reboot: Android; the Magisk switch back: Linux (`android` in the file, the
  initramfs restored Android's block: the one-shot trial); `mu300-next-boot linux` made Linux the default again.
* Small things: the wait is `MU300_NEXT_BOOT_WAIT` minus one seconds (59 by default, 4 for 5); the renamed file
  loses the SELinux label the old one carried on the F50 (`ls -l` showed `-rw-r--r--.` before, no dot after), which
  nothing reads on Linux.

**Device checklist (before merge; F50 or U30 Air, Ubuntu and OpenWrt, any kernel):**

    sudo mu300-next-boot status                       # note the misc block
    sudo mu300-next-boot android; cat /etc/mu300/default-boot   # android; status shows Android's block
    sudo mu300-next-boot linux;   cat /etc/mu300/default-boot   # linux; slot armed (tries N+1)
    ls -l /etc/mu300/default-boot /run/mu300/next-boot.lock     # a regular file, root's; the lock file exists
    # the race: hold the lock and switch; the switch waits, then goes through
    sudo flock /run/mu300/next-boot.lock sleep 10 & sleep 1; time sudo mu300-next-boot android   # ~9 s
    sudo mu300-next-boot linux; sudo reboot           # comes back to Linux; systemctl status mu300-boot-ok: success
    # OpenWrt: the panel's Switch to Android, then reboot: Android; mu300-linux from Android: Linux again
### 101. The Magisk switch built its misc block under a fixed name in the adb shell user's directory

Found while comparing our switch with kanoqwq's clean-tf-7.2 `1f8f03fb` (his one-time boot changes misc only; ours
does too, §100), and narrowed by a security review of the first version of this fix. `mu300-linux`
(`android/magisk/mu300-linux-switch/switch.sh`, run as root) wrote the 32-byte block to
`${TMPDIR:-/data/local/tmp}/mu300-bc.bin`, checked its size, then `dd`'d it into misc. `/data/local/tmp` belongs to
the adb `shell` user (2000, mode 0771, no sticky bit): that user, without root, could plant `mu300-bc.bin` as a
symlink (root's `printf >` follows it and overwrites the target) or replace the file between the size check and
`dd` (and so choose the bytes that go into misc; the read-back then fails, with misc already changed). A private
`mktemp -d` directory there (the first version) is not enough: without the sticky bit the shell user can rename it
away and put a directory of their own in its place between `mktemp` and the write. Apps cannot write there; the
user at the adb shell can, and on a device where Magisk grants root only to chosen apps that is less than root.

Changed:

* **No file on the way.** The 64 hex digits are checked (hex only), the bytes `printf` makes are counted (32), and
  `printf` goes straight into `dd ... bs=1 count=32 conv=notrunc`. Nothing is created in any directory.
* **misc resolved once.** `by-name/misc` is followed once (`readlink -f`); the result has to be a block device under
  `/dev/block` whose sysfs entry (`/sys/class/block/<name>/uevent`, written by nobody but the kernel) says
  `PARTNAME=misc`. That one path is read (the live block), written and read back. A link that leads anywhere else
  (another partition, a file) is refused before anything is written. (`MU300_SYSFS`, tests only, stands for `/sys`
  and lets a regular file stand for the device.)

**Bootability:** unchanged when misc is what by-name says: the same block, written and read back as before; every
refusal exits before `dd`, and misc stays as it was (Android boots).

**Unit tests:** `tests/test_magisk_switch.py` (real, non-dry runs against files standing in for
the partitions): a symlink planted at the old name (it and its target untouched, nothing new in `TMPDIR`, the block
in misc, 4096 bytes still); `by-name/misc` a link to a partition sysfs calls `boot_a`, then one with no sysfs entry
(refused, the target unchanged), then one sysfs calls `misc` (written there, through the link resolved once);
without the test switch, a regular file is refused (`outside /dev/block`). `test_android_web.BootLinux` gives its
fake device the sysfs entry. Run in the `mu300-unit` container (busybox, as root).

**Device checklist (before merge; Android with Magisk, Linux installed):**

    su -c 'readlink -f /dev/block/by-name/misc; grep PARTNAME /sys/class/block/$(basename $(readlink -f /dev/block/by-name/misc))/uevent'
    # PARTNAME=misc - if not, this change refuses to switch on that device: report it
    su -c 'mu300-linux --dry-run'        # the block; nothing written
    # the Action button or su -c mu300-linux: reboots into Linux; ls /data/local/tmp has nothing new
    # the web installer's "Boot Linux" (android-web.sh boot-linux) the same

**Measured on the F50** (Android with Magisk, the module of v2026.10.27 with this branch's `switch.sh`, 2026-10-15):

* `by-name/misc` -> `/dev/block/mmcblk0p3`, whose `uevent` says `PARTNAME=misc`. The U30 Air was not taken to
  Android (it cannot be brought back from there without a hand on it); under Linux its `mmcblk0p3` is `misc` too
  (`/sys/class/block/mmcblk0p3/uevent`, the same GPT), as on the F50 under Linux.
* `--dry-run` under Android's `sh` (the Magisk path) and under Magisk's busybox with `ASH_STANDALONE=1` (the web
  installer's): the same block (`...9e002f...`, slot b with one try), nothing written. The web installer's own entry,
  `android-web.sh boot-linux dry` with this `switch.sh` in its stage: the same.
* With `MU300_BY_NAME` pointing at a directory of links: `misc` -> the `boot_a` partition: refused (`/dev/block/
  mmcblk0p37 is not the misc partition (sysfs PARTNAME)`); `misc` -> a regular file: refused (`misc resolves
  outside /dev/block`); `misc` -> `/dev/block/by-name/misc` (a second link): taken.
* The real switch, `su -c mu300-linux`: `slot b armed for one boot`, rebooted into Linux; no `mu300-bc.bin` in
  `/data/local/tmp`. The initramfs then restored Android's block, as for every one-shot trial.
### 102. Mobile data TX: a full IPA FIFO pushed another Ethernet header at every retry

From kanoqwq's clean-tf-7.2 `149c9d2a` ("preserve TX retries"), checked against our `upstream/modules/sprd_modem/
sipa_v3` (mainline kernels' modem stack; the 5.4 build uses the vendor tree and is not changed). Three defects in
`sipa_eth_start_xmit()`, the transmit function of the `sipa_eth` interfaces that carry mobile data:

* **Every retry one more header.** The device is raw IP: a packet arrives with `mac_header == network_header`, and
  the function `skb_push`es 14 bytes for the IPA's Ethernet framing. When the IPA's send FIFO is full,
  `sipa_nic_tx()` returns `-EAGAIN` and keeps nothing (`sipa_skb_sender_send_data()` unmaps and returns without
  taking the skb), and the function returns `NETDEV_TX_BUSY`: the qdisc sends the same skb again later. The push
  does not move `mac_header`, so the test is true again and every retry pushed another 14 bytes in front of the
  packet: what finally went out was the packet behind 14·(retries+1) bytes of stale header. For a
  `CHECKSUM_PARTIAL` TCP/UDP packet the checksum field (the pseudo-header seed) had also been zeroed for the IPA,
  and stayed zero for the retry.
* **The IRQ flags in one static variable.** `spin_lock_irqsave(&queue_lock, queue_lock_flags)` with a file-scope
  `queue_lock_flags`, shared by the TX path and the flow-control wake-up on every CPU: a second CPU taking the lock
  overwrites the holder's saved interrupt state, and the holder then restores the other CPU's.
* **A freed skb reported as not sent.** When `skb_linearize()` fails the skb is freed and the function returned the
  `-ENOMEM` as its `netdev_tx_t`, which the stack does not take as "consumed".

Changed (ours, the same three fixes as his): the push is undone and the seed put back before `NETDEV_TX_BUSY`; the
flags are a local of each function; a failed linearize returns `NETDEV_TX_OK`. The "fail to send" line is rate
limited (it fires on every retry under backpressure). Not taken from the same commit here: his Wi-Fi changes (§103),
and nothing about `sipa overflow ... err=2`, which his own notes leave unexplained.

**When it bites:** whenever `sipa_nic_tx()` says busy. Read from the code this was a full IPA FIFO only, but on
the devices it is above all **the IPA's resume**: the resource manager answers `-EINPROGRESS` (`sipa_nic_rm_res_
request()`, before anything is sent: the skb is not taken either) for the first packet after the IPA went to
sleep. Measured on the F50 (7.2.10): after 25 s without traffic, every first packet met it (`sipa_eth: fail to
send, ret -115`, six rounds out of six, on the release kernel and on this one); the U30 Air (6.18.56) logged the
same at boot. A packet retried this way was sent behind the stale header on the release kernel.

**Measured:** built for 7.2.10 and 6.18.56 (`sipa_eth.ko`, no new warnings; built from a copy against the
`mu300-mainline` volume's trees). `tests/test_sipa_eth_xmit.py` compiles the function from the source with
stand-ins for the kernel calls (ASan/UBSan where the compiler has them): 1, 3 and 50 busy answers in a row, then
the packet goes out with exactly one header (54 bytes for 40), unchanged between retries, the seed back, the lock
released; a failed linearize says `NETDEV_TX_OK` with the skb freed. The previous source does not compile in the
harness (the static flags), so the test is no negative control of the retry itself. Nothing run on a device.

**Device checklist (before merge; F50 or U30 Air, 6.18 or 7.2, mobile data up):**

    iperf3 -c <server> -t 60 -P 8                    # uplink as hard as the link goes (or a large upload)
    dmesg | grep -c 'fail to send'                   # retries happened (rate-limited lines) - the case under test
    # TCP throughput is not worse than before; ping -s 1400 and a download keep working; no oops in dmesg;
    # ip -s link show sipa_eth0: tx_errors counts the busy answers, no climbing tx_dropped

**Measured** (2026-10-15) on a test kernel with §92, §93, §102 and §103 together (main of that day plus the four
branches): the F50 (Ubuntu 24.04, 7.2.10) and the U30 Air (openwrt-luci, 6.18.56, the owner's VPN over it), against
the v2026.10.27 kernels:

* **The first packet after an idle period:** six rounds of 25 s without traffic, then one `ping -I sipa_eth0
  1.1.1.1`: every round one busy answer (`ret -115`, the IPA resuming) and the ping answered, 6/6 on this kernel and
  6/6 on the release kernel. So the device did not show the stale header doing harm: either the retried packet
  survives it somewhere between the IPA and the network, or the busy answer met another packet than the ping. The
  fix stays what the netdev contract asks (a `NETDEV_TX_BUSY` skb comes back unchanged); no measurement here proves
  a user-visible effect of the old behaviour.
* **Uplink under load:** eight parallel uploads (12 MiB each) over the F50's mobile data: `tx_errors` +1 (one busy
  answer, `fail to send` logged once), no `tx_dropped`, no oops; `ping -s 1400` and a download worked after it.
  The SIM was throttled to about 1.9 Mbit/s in both directions by then, so throughput says little: an A/B in the
  same conditions (the release's `sipa_eth.ko` loaded into the test kernel, then this one) gave the same speeds and
  retransmissions. Unloading and loading `sipa_eth` a second time restarted the F50 (the vendor module is not made
  to be reloaded; its first reload had already logged `probe ... failed with error -17`): not a test to repeat.
* The U30 Air carried its VPN over this kernel for three boots; the F50 had mobile data in all of its seven.
### 103. Wi-Fi TX on the SC2355 (mainline): a freed skb used on, AP IPv6 multicast refused in bursts, a full EDMA ring counted as failure

From kanoqwq's clean-tf-7.2 `149c9d2a`. His notes (`docs/WIFI-TX-RETRY-20261015.zh-CN.md` there) are measurements on
an F50 with OpenWrt 25.12.5 and 7.2.8, with kprobes on the command path; our `upstream/modules/sprd_wlan_combo`
and `wcn_bsp` have the same code at each point. Ported in our own words; his tests, docs and his 5.4 patches not
taken (the 5.4 driver is built from `kernel/patches/wlan_combo-*`, against a vendor tree, as in §92).

* **A freed skb used on (both transports).** `sc2355_pcie_hif_fill_msdu_dscr()` / `sc2355_hif_fill_msdu_dscr()`,
  when the headroom was short, replaced the skb with `skb_realloc_headroom()` and `kfree_skb()`'d the original - but
  only their own copy of the pointer changed: `sc2355_send_data()` and `sprd_xmit_data2cmd_wq()` then filled the
  message from, or copied and freed, the freed skb (and on an allocation failure freed it a second time). The
  descriptor was also written into a header shared with clones (a bridge flooding a frame to several ports clones
  it). Now `skb_cow_head()` (also when `skb_header_cloned()`), sized with the `offset` the push adds; the skb stays
  the caller's, a failure returns `-ENOMEM` and the caller frees as before; `ethhdr` is read again afterwards (the
  checksum-offload branch uses it). How often the short-headroom case happens on our boards is not known.
* **The group TID never set on PCIe.** `sprd_xmit_data2cmd_wq()` sends a frame as a firmware command and, for an
  AP's group frames, sets the BK TID "to avoid FW hang". It read the descriptor at `skb->data`; on PCIe that is the
  5-byte address prefix the fill puts in front, so the "LUT index" it tested was the descriptor's offset byte (11)
  and the branch never ran (kanoqwq's probe: `off=11, lut=4, tid=0`). The descriptor is now taken behind the prefix,
  before SDIO's flag is pushed (as his E5 SDIO driver does); the per-frame `pr_info` is a rate-limited debug line.
* **AP IPv6 multicast through the command path.** `tx_mc_pkt()` sent every IPv6 multicast frame of the access point
  (neighbour discovery, router advertisements, mDNS) as `CMD_TX_DATA`. kanoqwq replayed bursts of eight 12-byte mDNS
  queries (`ff02::fb`, one burst a second, six bursts) from the USB side of an F50: in each burst the first six
  were answered OK and the last two `SPRD_CMD_STATUS_ERROR` (-6), twelve in all, identical bytes succeeding and
  failing; the command worker had already given the frame up. On PCIe these frames now take the data queue, as IPv4
  multicast always has (firmware credits, EDMA backpressure, the group LUT entry); `tx_filter_ip_pkt()` after it still
  sends DHCPv6, DNS and VoWiFi by command, EAPOL never comes here. His check after the change: 112 replayed frames all
  on the data path, no command error, a phone's IPv6 neighbour entry learnt again over multicast ND and its IPv6
  ping answered. SDIO (no board of ours) keeps the vendor's path.
  This is the TX side. §92 (the AP RX "endian fix", not taken) is about frames *from* a client being copied back to
  the BSS; nothing here changes that, and mDNS/ND between clients keeps working the way §92 describes.
* **A full EDMA pending ring.** The PCIe TX data channel queues at most three submissions behind the running one
  (`edma_pending_q_buffer`, four slots); a fourth was refused with `ERROR` (-1), counted by the WLAN side like a hard
  push failure (`pushfail_count`: more than 100 in a row flushed the frames waiting; `failcount`: more than 50), and
  nothing woke the TX thread when room came back. Now the ring returns `-EAGAIN` (nothing was taken; every other
  user of `mchn_push_link` - Bluetooth, the RX refill - only tests for non-zero), the WLAN side keeps the frames
  without counting, and both TX data channels register a `tx_complete` callback that wakes the TX thread when the
  bus finishes a transfer; the wait flag is armed before the submission, since the completion can come before the
  push returns. His F50 run afterwards: 128 refusals in 30 min, all `-EAGAIN`, TX kept growing (up to 40.8 Mbit/s in
  5 s samples), no `tx return err`, no flush, no firmware assert.

`wcn_bsp` and `sprd_wlan_combo` change together (the new return value): the release builds both from this tree.

**Measured here:** built for 7.2.10 and 6.18.56 (`wcn_bsp`, `sprd_wlan_combo`) against the `mu300-mainline`
volume's trees, compared with the same build of `main`: no new warning. `tests/test_wifi_tx_path.py` reads the source
for each point. Nothing run on a device (both test devices were in use); his measurements above are on his F50.

**Device checklist (before merge; F50 and U30 Air, 6.18 and 7.2, the hotspot on 5 GHz):**

    # before/after: dmesg -C; a phone on the hotspot
    ping6 -c3 ff02::1%br-lan            # (OpenWrt; Ubuntu: the hotspot bridge) every client answers
    # from a computer on USB, a burst of mDNS: for i in $(seq 8); do avahi-resolve -n x$i.local & done
    dmesg | grep -i 'CMD_TX_DATA' | grep -ci err      # 0 after (before: errors in bursts)
    dmesg | grep -c 'push link fail'                         # may be > 0 (rate limited); no 'tx return err'
    # a long download and upload on the phone (iperf3 -R and normal), 10 min: no 'tx return err', no flush,
    # no firmware assert, throughput not lower than before; IPv4 and IPv6 browsing, AirPlay/Chromecast between
    # two phones still found (mDNS between clients, §92); a second client joins and gets DHCPv4 and an IPv6 address

**Measured on both boards** (2026-10-15) on a test kernel with §92, §93, §102 and §103 together (main of that day
plus the four branches): the F50 (Ubuntu 24.04, 7.2.10) and the U30 Air (openwrt-luci, 6.18.56), a MacBook on the
5 GHz hotspot (802.11ac, 80 MHz) as the one Wi-Fi client and on the USB side as the sender of the replay; against
the v2026.10.27 kernels on the same devices.

* **kanoqwq's replay:** six bursts of eight 12-byte mDNS queries to `ff02::fb`, one burst a second, sent by the
  Mac on its USB link to the device, which bridges them to the Wi-Fi client:

  | | release kernel | test kernel |
  |---|---|---|
  | F50: `CMD_TX_DATA ... SPRD_CMD_STATUS_ERROR` | 8 | 0 |
  | F50: wlan0 `tx_packets` during the replay | +13 | +50 |
  | U30 Air: `CMD_TX_DATA ... SPRD_CMD_STATUS_ERROR` | 12 (two per burst of eight, as he saw) | 0 |
  | U30 Air: wlan0 `tx_packets` during the replay | +3 | +59 |

  (On the release kernel the command path does not count in `tx_packets`; on this one the 48 frames are data.)
* `ping ff02::1` on the bridge: the Mac's Wi-Fi address answered (4 of 5; its USB address the same, the first
  one lost to neighbour discovery) on both boards.
* **A full EDMA ring:** under 300 MiB transfers to the Mac, `edma_pending_q_buffer(10) full` with `push link fail:
  -11` (rate limited) 140-170 times on the F50 and 80 on the U30 Air; `tx return err` 0 (the U30 Air's release
  kernel had logged 8738 of them in its two hours before the test), no flush of queued frames (the only `flush`
  lines are a client leaving), no firmware assert, no oops. TX to the Mac 300-590 Mbit/s on the F50 and 210-500 on
  the U30 Air, the same spread as on the release kernels; 6 GiB in one stream at 594 Mbit/s on the F50.
* **The client leaving during a transfer:** no oops, no use-after-free report (the kernel has no KASAN), the
  hotspot took the Mac back (§92 has the log lines).
* Not covered: two Wi-Fi clients (mDNS between them, a second client's DHCPv6), an SDIO board, and the skb
  short-headroom path, which no log line shows; nothing here proves the use-after-free case was reached.

### 125. Release names: the day of the release and its number (vYYYY.MM.DD.N)

**Status: current** (unit tests in sh, Python, JavaScript and PowerShell against one table; the old clients' behaviour
read from their code at the tags v2026.10.25, v2026.10.26 and v2026.10.27; nothing run on a device).

**What was wrong.** The release tags were `vYYYY.MM.DD`, but the "day" was used as a counter: v2026.10.27 was
published on 2026-10-15 (UTC), twelve days ahead of the calendar. The owner's decision (2026-10-15): the tag says the
real day of the release, then a number for the releases of that day.

**The scheme.** A new release is `vYYYY.MM.DD.N`: YYYY.MM.DD the UTC date it is built, N = 1, 2, 3, ... for the
releases of that day. N has no leading zero and is at most 99 (Magisk's `versionCode` below); the month is 01..12, the
day 01..31. `tools/make-release.sh --next-tag` prints the next one: today's date and one more than the highest N of
today's tags among GitHub's releases (`gh release list`, drafts and prereleases included) and the tags (local and
`git ls-remote origin`); without GitHub's answer it prints nothing and fails rather than guess. `make-release.sh TAG`
takes only the four-field form for a new release and refuses a TAG whose date is not today unless `--any-date` is
given. The Release workflow takes the tag input empty (then `--next-tag`) or checks a given one (`--check-tag`) at its
start, and passes `--any-date` to the build hours later, which may end on the next day.

**The order (the transition rule).** Every four-field tag is newer than every three-field tag, whatever the dates:
v2026.10.16.1 > v2026.10.27. Four-field tags compare by the date, then by N, as numbers: v2026.10.16.2 >
v2026.10.16.1, v2026.10.16.10 > v2026.10.16.9, v2026.10.17.1 > v2026.10.16.99. Three-field tags keep their old order
among themselves. Anything else - `test-issue-102`, `v2026.10.16.0`, `v2026.10.16.01`, `v2026.13.01.1`,
`v2026.10.27-fix1`, a trailing newline or space, digits of another script - is no release tag: neither newer nor older
than anything. As a key: `1YYYYMMDD00` for vYYYY.MM.DD, `2YYYYMMDDNN` for vYYYY.MM.DD.N.

**One comparer per language, one table.** `tests/fixtures/release-tags.tsv` lists the tags that are release tags, the
ones that are not, and 31 pairs with their order; every implementation is tested against it:

| language | where | used by |
|---|---|---|
| sh | the `release-tag` block (`tag_ok`, `tag_key`, `newer`) of `tools/releases.sh`, word for word also in `mu300-update` and `tools/android-install.sh` (a test compares the three) | install.sh (the slot-a check), make-release.sh, make-magisk-zips.sh (`versionCode`), mu300-update (`notice`, `check`, `downgrade_ok`, `boot_downgrade_ok`, `--from`, `releases`, a module's `requires`), android-install.sh (for an update's downgrade check) |
| Python | `tools/release_pick.py`: `tag_key`, `tag_ok`, `newer` | the installers' release and beta decision (install.sh, install.ps1, the graphical installer) |
| JavaScript | `site/assets/web-installer/version.js`: `releaseKey`, `newerTag`, word for word also in the panel's `update.js` | the web installer (`loadReleases`, `releaseSupportsWeb`), System > Update |
| PowerShell | `install.ps1`: `TagKey`, `TagNewer` (tested in `tests/installer.Tests.ps1`) | install.ps1's slot-a check |

The sh block uses only the shell's own patterns (no grep, no locale) and compares the key in two parts (the era and
the date, nine digits; then N without its leading zero): an 11-digit number would overflow a shell with 32-bit
integers, and `08` must not be read as octal. .NET's `\d` takes any script's digits and its `$` lets a final newline
through, so the PowerShell expressions use `[0-9]` and `\z`. The device programs that only check a tag (the panel's
rpcd `update_act`, the update adapter, `dashboard-info`'s note of a newer release) use one extended regular expression,
`v[0-9]{4}\.[0-9]{2}\.[0-9]{2}|v[0-9]{4}\.(0[1-9]|1[0-2])\.(0[1-9]|[12][0-9]|3[01])\.[1-9][0-9]?`, which a test holds
to the table too. The installers' beta is now also newer by its tag than the release when both are release tags
(published later alone is not enough), as `mu300-update releases` decided already. Magisk's `versionCode` of a
four-field release is YYYYMMDDNN (2026101602: ten digits, above every three-field release's eight, below 2^31 until
the year 2147). What only checks the form `v[0-9]` and plain characters (the zips' manifest, the mirror, the
workflows' `startsWith(tag, 'v')`, the Telegram announcement) takes the new tags as they are.

**What the clients released before this do with a four-field release** (read from their code at v2026.10.25-27; the
three have the same logic in these places):

* `mu300-update apply`: no tag is validated or compared. It reads `releases/latest`, fetches that release's
  `mu300-update` (checked against its `SHA256SUMS`), and when it differs `exec`s it with `MU300_RELEASE=<tag>`
  before it changes anything; the new updater then runs `downgrade_ok` with the new rule (v2026.10.16.1 is not older
  than v2026.10.27) and does the update. **An update works; no bridge release is needed for it.**
* `mu300-update notice` (the login note, `mu300-toolkit`) and `check` compare with `sort` as text. Against a three-field
  installed tag, a four-field one sorts after it only when its date is 2026.10.27 or later (v2026.10.27.1 >
  v2026.10.27 as text: the shorter one is a prefix). For releases dated 2026-10-15 to 2026-10-26 a device on v2026.10.25,
  .26 or .27 shows **no note**, and `check` says "This is newer than the newest release (a test release);
  mu300-update apply would go back to vYYYY.MM.DD.N" - wrong in its words, while `apply` goes forward. From the first
  release dated 2026-10-27 or later their text order agrees with the rule again (a date's digits sort as text). Making
  the note right before then would take a three-field release after v2026.10.27 (it would have to be `v2026.10.28`,
  carrying the new updater), which the new scheme rules out: the gap is documented instead (wiki Updating, "Release
  names", and the site's update page).
* `mu300-update`'s module check (`version_ok`): the VPN module needs `mu300-linux v2026.10.16`, compared with the
  old text order against the three-field tag of the old system - unchanged. After an update the new updater compares.
* The control panel of those releases has no update page and no note of a newer release (they came after v2026.10.27).
* `install.sh` and `install.ps1` of those releases take `releases/latest` (GitHub's "latest", any tag); their slot-a
  check (`v2026.10.10` or newer) compares as text and lets every four-field tag through, which is right.
* Their Magisk zips check only their own manifest's tag (`v[0-9]` and plain characters) and look at no release list.
* The web installer is not in users' hands: the site serves main's. Before this change its `releaseSupportsWeb`
  compared the first eleven characters with v2026.10.23, so v2026.10.16.1 counted as "too old for the web installer":
  this change must be on the site before the first four-field release. Its choice of the newest release went by the
  time of publishing and was right.
* The graphical installer and the installers' beta question are newer than v2026.10.27 (`tools/release_pick.py` is
  not in those tags); they go by the time of publishing too, now with the tag order on top.
