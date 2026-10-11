# U30 Air SC2355 firmware SAE offload (opt-in)

The tested U30 Air firmware performs AP SAE authentication in firmware, but
the standard hostapd AP setup neither supplies the vendor runtime password
request nor consumes the firmware's PMK handoff. A client can finish SAE and
then fail association/the WPA four-way handshake. Advertising SAE capability
alone does not implement those two vendor interfaces.

This patch is an explicit opt-in for the observed firmware, not a new default
for F50, other chipsets, WPA2/WPA3 transition mode, or OWE. The firmware uses
hunting-and-pecking with group 19. H2E-only clients and other SAE groups are not
covered by the measured result.

## Protocol integration

After a successful AP setup, hostapd sends OUI `0x001374`, subcommand `43` with
nested vendor data containing the passphrase (attribute 8), group 19 (6), and
ACT `0xffffffff` (7). This sets runtime firmware state and does not flash WCN
firmware. Configuration requires pure SAE, mandatory PMF, `sae_pwe=0`, firmware
AP SME, and one 8–63 byte passphrase. Per-station SAE passwords are unsupported.

The SC2355 firmware reports the derived 32-byte PMK and 16-byte PMKID in a
kernel NEW_STATION event as a trailing vendor IE: EID 221, length 52, prefix
`40:45:da:04`. Only one complete trailing element is accepted, only when the
opt-in is enabled and firmware setup succeeded on a pure SAE/fullmac BSS.
Malformed/duplicate/truncated metadata is rejected by a length-bounded parser.
The key goes to the normal PMKSA/authenticator path; normal RSN validation,
four-way handshake MIC checks and required PMF remain in place. The metadata
must be trusted kernel/firmware output, never an over-the-air management frame.

The driver previously printed SAE passphrases and command/event bytes. The
module changes and vendor-kernel patch remove password logging and suppress
key-bearing command/NEW_STATION dumps. hostapd also avoids dumping the entire
NEW_STATION IE payload. Rebuild/install the matching Wi-Fi module to get that
log protection; an existing stock module still contains the original logging.

## Build and opt in

Use a dedicated [official OpenWrt 25.12.5 armsr/armv8 SDK](https://downloads.openwrt.org/releases/25.12.5/targets/armsr/armv8/).
Verify its checksum before extracting. Use an ASCII-only SDK path: the SDK's
package stripping scripts failed with a non-ASCII build path on the test host.
Install the SDK's pinned base feed before running the helper:

```sh
cd /absolute/path/to/sdk
./scripts/feeds update base
./scripts/feeds install -p base hostapd
```

The package recipe must have source
`ca266cc24d8705eb1a2a0857ad326e48b1408b20`, revision 1 (the official SDK's
pinned feed) or 5 (the previously recorded release feed). Other sources and
revisions are refused. The helper finds the SDK feed recipe, applies the patch
after OpenWrt's existing patches, bumps revision to 6, replaces the dedicated
SDK's `.config`, and builds the OpenSSL variant with its normal dependencies:

```sh
sh openwrt/build-u30-sae.sh /absolute/path/to/sdk /absolute/path/to/u30-sae-apks
```

The output must contain a matching `hostapd-common` and `wpad-basic-openssl`
pair. The image builder accepts that directory on the tested release:

```sh
MU300_SYSTEM=openwrt-luci MU300_SAE_APK_DIR=/absolute/path/to/u30-sae-apks \
  sh openwrt/build-rootfs.sh
```

Normal image builds keep `wpad-basic-mbedtls`. Supplying the APK directory
includes the patched OpenSSL package but still does not enable the vendor path
automatically. Enable it only on the tested U30 Air interface in LuCI/UCI:

```text
option encryption 'sae'
option ieee80211w '2'
option sae_pwe '0'
list hostapd_bss_options 'u30_sae_offload=1'
```

Set your own passphrase with OpenWrt's existing wireless settings. Inspect the
generated hostapd configuration locally and confirm `wpa_key_mgmt=SAE`,
`ieee80211w=2`, `sae_pwe=0` and `u30_sae_offload=1`. Do not publish that file.
The firmware request uses group 19 even if the generator lists more groups.

## Installation and rollback

Keep USB management access and back up the wireless configuration, installed
Wi-Fi packages/files and original `sprd_wlan_combo.ko` before installation.
On current mainline sources, also back up `wcn_bsp.ko`. Build/install the
matching WCN and WLAN module pair against the target kernel: the WLAN recovery
path added in #100 calls `wcn_mu300_recover`, exported by the updated WCN BSP.
Do not install a new WLAN module over an older BSP without that export.
The OpenSSL variant also requires `libopenssl-legacy`; let APK resolve that
from the official release feed, or download it locally for an offline install.
Install the matching `hostapd-common` and `wpad-basic-openssl` pair together.
Do not leave an earlier standalone `hostapd` binary in front of the package's
`hostapd -> wpad` symlink. Trust only packages you built or whose origin and
checksums you verified; locally built APKs are not signed by OpenWrt's release
key. This is an opt-in build recipe, not an official OpenWrt binary release.

When replacing packages, take Wi-Fi down, stop wpad and wait for all hostapd
processes to exit before removing the old wpad variant. After installation,
start wpad and bring Wi-Fi up. Do not unload/reload the WLAN module live:
a trial on this device panicked in bridge teardown when hostapd was still
operating an old netdev callback after module unload. Install the matching
module file and use a complete Linux reboot instead. For a module trial, an
early-boot restore guard must run before `mu300-hw` (START=12); keep the original
module available until both USB and fresh SAE client access are confirmed.
Restore packages, configuration and module from the backup, then reboot, if
the trial fails. No Android firmware/partition change is needed.

A plain reload after changing from OWE once left the tested firmware timing
out the four-way handshake (reason 15); a complete wpad restart restored it.
Same-configuration `wifi reload` passed with the final packages. Switching
between security modes and changing passwords through hot reconfiguration
have not been exhaustively validated; use a complete Wi-Fi/wpad restart for
those operations. APK replacement after a later upgrade needs revalidation.

## Validation and limits

The review update rebases this branch onto main `9d21c77`, including #100's
Wi-Fi recovery/backoff and rate-limited logging changes. Those changes are
retained; the SAE hostapd patch and driver privacy filters are unchanged.
After rebasing, the SAE tests passed again (9, with required UBSan), Wi-Fi
bring-up passed (5), Wi-Fi client regressions passed (59), and static checks
passed (40). The rebased `cmdevt.c`, `vendor.c`, `common/iface.c` and WCN
`platform/wcn_procfs.c` also compiled against the prepared Linux 7.2.9 tree.
This was an object compilation check, not a complete kernel/module build or
a hardware test of the new recovery path. The device results below were
obtained before this rebase, from revision `4d61379`; the updated module pair
has not been installed on that device. Independent testing of the rebased
sources is still pending.

The hardware-tested patch was built through the official OpenWrt 25.12.5 armsr/armv8 SDK
(GCC 14.3/musl), producing revision 6 `hostapd-common` and
`wpad-basic-openssl` APKs. The official SDK's base feed is pinned at
`f0a60eee2fe051741c643ea6118718aae1ef17fb`. SDK download SHA-256:
`1b0316604a3e820b2b008a1baff3f9dac6716af942bef800930e58c7de98c98b`.
These packages, plus the official `libopenssl-legacy` dependency, were installed
on one U30 Air with OpenWrt 25.12.5 and Linux 7.2.9. The private-log-suppressed
WLAN module was rebuilt against the matching prepared kernel/configuration and
successfully loaded through a complete Linux reboot. No module versioning was
enabled on the tested kernel; this local module is not interchangeable with a
module for another kernel build. Both mainline module sources and the vendor
kernel's equivalent patch are included; the vendor-kernel variant was not
hardware-tested in this run.

A Linux NetworkManager client on an independent interface, using a fresh MAC
and required PMF, completed pure SAE, the WPA four-way handshake and DHCP.
Router HTTP returned 200 and external HTTPS returned 200 with certificate
verification (direct curl, no proxy, TLS 1.2). An incorrect password never
established a connection within the 25-second test window; the correct password
connected afterwards. Same-configuration Wi-Fi reload, a complete wpad service restart, and fresh
reconnection passed. External connectivity had transient timeouts; repeated checks over
Wi-Fi and a router-local comparison returned 200. Original password-log
markers were absent after the new module boot. Raw device/client logs and
credentials are not part of this contribution.

Other phones/clients, H2E-only clients, alternate SAE groups and the final Docker
rootfs assembly have not been independently verified. Delivery here is the
SDK-built package pair and a tested existing-device installation, rather than
a flashed replacement image. Full rootfs assembly remains an optional image
builder path. No claim is made about OWE or SAE client/station mode.

Before the review rebase, the SAE/parser/SDK tests passed (9 cases), Wi-Fi
bring-up passed (5), Wi-Fi client regressions passed (58), and static tests
passed (40). A broad desktop run
executed 1056 tests with 86 skips and two pre-existing VPN test failures: the
host has a real `/usr/bin/mihomo`, and its `ls` appends the SELinux mode suffix.
The SAE branch does not modify either VPN test or implementation. The SAE tests also passed with `MU300_TEST_UBSAN=1`. This desktop initially
lacked the UBSan runtime; the matching signature-verified Fedora library was
extracted into a private build directory and used without a system installation.
The Linux CI job now requires a successful UBSan run rather than silently
falling back. These local results
are not a claim that all CI checks pass.

`tests/test_u30_sae.py` compiles the actual parser from the patch and exercises
every truncation, exact/duplicate/non-trailing elements and 500 deterministic
malformed inputs. UBSan is used when its compiler/runtime is available; require
it in CI with `MU300_TEST_UBSAN=1`. The tests also check the official SDK feed layout/revision, missing-feed diagnostics,
recipe pinning, matching package collection, and refusal to overwrite a
conflicting patch.

OWE remains unresolved: two independent tests reached association status 43
even with current userspace support. This SAE fix is not evidence of an OWE
fix, and does not alter regulatory/DFS behavior or any Android partition.
