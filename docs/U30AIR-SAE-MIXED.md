# U30 Air mixed WPA2-PSK / WPA3-SAE experiment

This is a downstream-tested SC2355 AP-SME integration, ported onto upstream
main for review. It is not enabled by the normal image builder. It does not
add WPA3 station support or establish that other Unisoc firmware is compatible.

## Failure and repair

On U30 Air with OpenWrt 25.12.5 and `7.2.9-u30air-charge2`, the AP advertised
mixed PSK/SAE but clients could not authenticate. An iPhone reported an incorrect
password even with the same password that worked in the WPA2 control test.
The firmware owns SAE authentication, but the standard Linux/hostapd path did
not deliver its password or consume its authentication result correctly.

* Advertise SAE AP offload only when the firmware advertises AP-SME and SoftAP
  WPA3. Convert the standard cfg80211 SAE password to the existing firmware
  command/TLV format, with bounded lengths and group 19.
* With explicit `U30AIR_SAE_OFFLOAD=pmk-first-v1` and AP-offload capability,
  hostapd imports the single terminal `40:45:da:04` PMK/PMKID result for SAE with
  PMF. It validates framing, RSN and any supplied PMKID; rejects missing results
  without a valid PMKSA; clears stale SAE context on transitions; and still
  requires the normal four-way handshake. FT-SAE is not imported.
* Select HnP (`sae_pwe=0`) before generating AP configuration and omit
  `WPA-PSK-SHA256`, retaining PSK/SAE and normal PMF negotiation. This compatibility
  patch deliberately checks the exact tested kernel string and PHY module.
  It does not activate on newer upstream kernels without further validation.
* Handle on-channel AP management TX with an omitted channel without a NULL
  dereference, and accept seven-byte leave events before reading an IE length.
* Remove four vendor plaintext password prints and hide the association dump
  behind hostapd's key-debug control. This is not a complete driver logging audit.

## Security and relationship to existing work

Related: [#74](https://github.com/dikeckaan/mu300-linux/pull/74) and
[#165](https://github.com/dikeckaan/mu300-linux/pull/165). Those proposals limit
the opt-in to SAE-only/required PMF. This alternative carries the downstream
mixed-mode implementation and its fixtures; it does not supersede their
security review or their broader private-log suppression.

**PMK provenance remains unresolved.** The result is carried in the association
IE buffer. A single terminal marker, RSN matching and a successful four-way
handshake do not prove the PMK was produced by firmware rather than supplied
by a malicious peer. A malicious Linux client provenance test and a trustworthy
firmware-result transport are required before general enablement. Do not treat
these synthetic fixtures or successful normal clients as proof against bypass.

Do not combine this hostapd patch with the other SAE bridge patches: they modify
the same authentication state. The SDK recipe opts the hostapd service into this
bridge; installing its APKs is an explicit experimental choice. Ordinary image
defaults and package selection are unchanged.

## Reproducible package inputs

`openwrt/sae-offload/inputs.json`, `sdk.config` and `sdk-patches.sha256` pin the
OpenWrt SDK archive, base feed, original recipe/init, 63 stock hostapd patches,
custom patch, and resulting r6 APK hashes. The SDK must already be extracted,
configured with this `sdk.config`, and have the clean `feeds/base_root` checkout
at the pinned commit. On Linux, with the SDK's build dependencies installed:

```sh
python3 openwrt/build-u30air-mixed-sae.py \
  --sdk-root /path/to/prepared-sdk \
  --sdk-archive /path/to/original-sdk.tar.zst \
  --out /path/to/new-package-output --jobs 8
```

The script refuses changed inputs, restores the SDK recipe/init in `finally`,
and outputs both APKs and provenance. Raw SDK `wpad` retains debug information;
its hash intentionally differs from the sstripped APK payload hash. No APK,
firmware blob, credentials, device backup or network configuration is committed.

This PR does not install the APKs or apply `ap-uc-sae-compat.patch` automatically.
The latter is a rootfs-relative patch (`patch -p1` from a matching rootfs) for
the tested OpenWrt `usr/share/ucode/wifi/ap.uc`; check its original hash first.
Rebuild the driver for the actual target kernel; never reuse a module across
kernel ABIs. The driver/kernel hashes under `downstream_reference` record the
released downstream build, not binaries built from this upstream port.

## Validation boundary

The downstream repair was tested on U30 Air: iPhone 17 joined during temporary
testing; Windows negotiated WPA3/CCMP, reconnected after reboot and reached HTTP.
An original-driver WPA2 control worked on iPhone. The final additional SAE-only
PWE guard was covered by regression tests, not a repeated iPhone run. The exact
r3 complete firmware ZIP was archive-verified, not flashed as a whole.

The port to current upstream main has no device boot/client validation and no
new-kernel build claim. It needs both before promotion to normal images.

```sh
python3 tests/sae-offload/run-fixtures.py
python3 -m unittest discover -s tests -p test_sae_offload_fixtures.py -v
```

The fixtures extract the actual patch code, compile with warnings-as-errors,
ASan and UBSan, and check 11 parser boundaries and 12 bridge states. An old
unconditional PWE guard is a negative control: PSK with residual PWE2 must not
be rejected by the SAE-only guard. These tests need a Linux C compiler and
sanitizer runtimes; they are not radio, firmware or adversarial-client tests.
