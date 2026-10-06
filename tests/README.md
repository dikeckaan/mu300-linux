# Tests

```sh
python3 -m unittest discover -s tests            # everything this machine can run
MU300_TEST_SHELLS="busybox sh" python3 -m unittest discover -s tests   # one shell only
powershell -File tests\installer.Tests.ps1        # Windows: install.ps1's functions
```

Standard library only (`lz4`, the command or `pip install lz4`, for the boot image tests). CI runs them on Ubuntu,
macOS and Windows (`.github/workflows/tests.yml`).

| file | what |
|---|---|
| `test_static.py` | every script parses under each shell that runs it; device programs are executable; rules from past bugs (no double quotes in `install.ps1`'s device commands, ASCII-only PowerShell, init looks for partitions after the modules) |
| `test_i18n.py` | `tools/i18n.sh`: every translation with every placeholder, arguments passed through untouched, answers in all three languages |
| `test_device_scripts.py` | `mu300-device`, `mu300-lan-ip`, `mu300-led` (both devices, 4G/5G, the timeout, the siren, the 5.4 LDO switches), `thermal-guard` (the heat alarm), `mu300-nfc` (a fake NFC tag: ZTE's own Wi-Fi record byte for byte, URLs, text, what `sync` leaves alone), `mu300-ttl` (stub `nft`), `mu300-wifi-band`, `mu300-buttons`, `mu300-usb` (a fake charger: never 5 V against a supply), `mu300-next-boot` and `early-recorder` on slot a and slot b (`NextBoot`, `EarlyRecorder`) |
| `test_installer.py` | which adb device the installers take: they ask whenever it is not the only one and an F50/U30 Air; the storage choice (`Storage`), the settings the installer hands to the device (`InstallEnv`), the hotspot import on a card (`ImportHotspot`), erasing the card (`SdErase`) and the free region (`Region`) |
| `test_vpn.py` | `mu300-vpn`: VLESS URI parsing, JSON, which networks stay out of the tunnel, the sing-box config, where the engines are found and how a VPN that is on gets them back, Tailscale through the tunnel (`Tailscale`: rules 5199/5200 with both engines, never doubled, gone with the routes, `TAILSCALE=0`, nothing past the kill switch) |
| `test_wifi_client.py` | `wifi-client`: the scan (iw and wpa_cli output: WPA2, WPA2/3, WPA3, UTF-8 names, no neighbour-report BSSID or hidden network), the password from stdin or a file and never on a command line, a WPA3-only network refused at once without SAE and joined with it, the uplink shared (the exact nft rules closed, shared and removed, through a join, a lost and a returning link, a failed or interrupted join and a supplicant that will not stop; nothing past the VPN's kill switch; fw4's wan zone on OpenWrt), hostile names shown as text everywhere, one validator for every way a name or passphrase comes in (the toolkit too), `disconnect` keeping the hotspot after a reboot |
| `test_extra.py` | extras: `mu300-update`'s install, adopt and update of extras (a VPN in use keeps its engines), `mu300-extra` install/remove/link against a fake release server; the lang extra (`LangExtra`: catalogs linked into LuCI and registered in `luci.languages`, enable/disable, Ubuntu refused, hostile archives refused) |
| `test_update.py` | `mu300-update`: release files per system and kernel, boot image byte helpers, whether a kernel bundle may go onto this device, the Linux slot it works on, and the boot image it builds from a device's own stock image (`FromStock`) |
| `test_boot_init.py` | `boot/init`: the card is looked for before the internal region, under any `mmcblkN`; a foreign or empty card falls back; the 300 s timer and the conditional wait; the slot init takes (`Slot`: command line, device tree, image, a mismatch) and the block it restores |
| `test_emmc_lookup.py` | every Linux-side lookup by partition name (init, `early-recorder`, `mu300-update`, `android-vendor-start`) takes the eMMC's partition, never a card's with the same GPT names, whichever of `mmcblk0`/`mmcblk1` the card is; `emmc_dev` never falls back to a card; `ueventd-perms.sh` touches no block device by number |
| `test_android_mount.py` | `tools/android-mount-mu300root.sh -u`: an unmount whose loop Android's umount already freed succeeds, a loop left attached is detached, a failed umount or detach fails |
| `test_android_install.py` | `tools/android-install.sh` on the SD card: a blank card is formatted, a foreign ext4 and an adopted or busy card are refused; the marker of an internal installation; pushed extras, and the engines a VPN in use keeps on update |
| `test_boot_image.py` | `boot/build-boot-image.py`: the generic ramdisk, the U30 Air's modules and order, the four `misc` blocks and `--linux-slot` (`SlotBlocks`) |
| `test_magisk_installer.py` | `android/magisk/installer/mu300-install.sh` on a fake device (`fakedevice.py`): `Conf` (the settings files: trusted and untrusted, validation, never run), `AndroidSide` (Android's own shell, not Magisk's busybox), `Plan` (model, slots, where Linux goes, refusals, the dry run, the example file), `WorkDirectory` (the root-only directory, nothing mounted is deleted), `Install` (what is written, verified, `misc` armed last; a failure leaves Android booting), `Password` (generated, hashed, where it is written, removed from the settings file) |
| `test_magisk_zip.py` | `customize.sh` in a fake Magisk environment (`Customize`), `tools/make-magisk-zips.sh` (`Builder`: eight zips, the allow-list, the manifest) and, with `MU300_MAGISK_ZIPS` pointing at a release's real zips, `ReleaseZips` |
| `test_magisk_switch.py` | `android/magisk/mu300-linux-switch/switch.sh`: the block goes to the slot Android is not on, with the CRC the bootloader checks; refuses a copy of Android's boot image |
| `test_android_boot_image.py` | `tools/android-boot-image.sh`: the pieces of the boot image only the device can make (the `misc` blocks, Android's files, the device segment), compared with `boot/build-boot-image.py` on the same inputs |
| `fakedevice.py` | not a test: the fake F50 the Magisk tests run on (block devices as files, a sysfs tree, stubs for Android's tools and a fake mount table) |
| `test_mu300cell.py` | `mu300cell.sh` (the OpenWrt netifd protocol), sourced with the netifd functions, `ip`, `mobile-data` stubbed: external updates, the v4 address installed by the script, v6 flush, teardown, `sleep 20` after an attach failure, the extendprefix interface; relay mode (K30, K35-K37, K64): the monitor `mu300cell-v6.sh`, `ndp-learn`, `init.d/mu300-ndp`, `91-mu300-luci`, mobile-data's `v6_relay_ra` |
| `test_atd_dash.py` | `init.d/mu300-atd-dash` (K19): two procd instances on nr6/nr7 with their own `MU300_AT_DIR` and no URC channel, START 19, mode 100755, enabled only in the luci block of `build-rootfs.sh`; the panel's collector tries `/run/mu300-at6`, `at7`, then nr1 |
| `test_early_dhcp.py` | the USB host's early DHCP lease from `boot/init` into the system (K5, K9, K11, K13, K25-K27): OpenWrt's preinit server on the system's own LAN subnet, the LAN hook that ends it and reattaches `rndis0`, the first-boot defaults (the host pinned with a broadcast lease, never the router; the `earlyusb` zone once; `rndis0` bridged only when it exists), Ubuntu's `lan-start`; under each shell |
| `test_ttl.py` | `mu300-ttl` with fake `uci`/`fw4`/`tc`/`modprobe`: the nft backend (no `act_pedit`) turns OpenWrt's flow offloading off while a TTL is set (also at boot), back on after `off`, untouched without fw4 (Ubuntu); the tc backend (`TtlTc`) puts matchall/pedit filters on every sipa_eth*, idempotently, leaves offloading alone, falls back to nft when tc fails, and `off` removes both |
| `test_luci_i18n.py` | the control panel's catalogs: every `po/<lang>` complete and in the language table, CJK only in catalogs; the pages (the Languages page too) under Node |
| `test_po2lmo.py` | `tools/po2lmo.py` against catalogs LuCI's own po2lmo produced (`tests/fixtures/po2lmo`) |
| `test_mu300dash_security.py` | the panel's rpcd backend `mu300dash` and its adapters (S1): every parameter checked against an allow-list, untrusted text only as one exact argument or on stdin, every reply JSON, the shared escaper, the ACL |
| `test_sms_pool.py` | the SMS pool (K69, D11): `mu300-sms` and `mu300-smsd` keep the SIM's and the panel's messages in `/etc/mu300/sms-pool`, through a stub `mu300-at`; the panel side runs on the real `mu300-sms` |
| `test_usb_management.py` | the panel's USB management (`device-usb`, K7, K8, D12): role switch, host mode, NIC reattachment, the USB network mode file `boot/init` applies on the next boot |
| `test_wifi.py` | `wifi-start` loads the WCN modules without `modules.dep` (K55); `mu300-hw` restarts the AP once the country is live (K15) |
| `test_early_replay_hook.py` | the early hook that replays the LuCI plugin's saved locks before the radio comes on (K65): its place in `mobile-data` |
| `test_unisoc_plugin.py` | the plugin's portable adapter boundary (K81): the custom AT backend contract, `--available` sends nothing, `boot-replay` (zero AT traffic when disabled, late replay, the early window), `lock replay early` restores every saved lock without `SFUN` |
| `installer.Tests.ps1` | `install.ps1`: `T` with every translation, `NormalizeAnswer`, `Gib` |

The device scripts run under dash (Ubuntu's `/bin/sh`), bash and busybox ash (OpenWrt); every shell test runs under
each of them that is installed. Commands that touch the device (`nft`, `ip`, `id`, `sing-box`) are stubs, and the
scripts read a fake `/` through `MU300_SYSROOT`, `MU300_DISK` and friends; `mu300-update` and `mu300-vpn` are sourced
with `MU300_LIB=1`, which defines their functions and runs nothing.
