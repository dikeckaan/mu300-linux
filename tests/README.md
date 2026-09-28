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
| `test_device_scripts.py` | `mu300-device`, `mu300-lan-ip`, `mu300-led` (both devices, 4G/5G, the timeout, the siren, the 5.4 LDO switches), `thermal-guard` (the heat alarm), `mu300-nfc` (a fake NFC tag: ZTE's own Wi-Fi record byte for byte, URLs, text, what `sync` leaves alone), `mu300-ttl` (stub `nft`), `mu300-wifi-band`, `mu300-buttons`, `mu300-usb` (a fake charger: never 5 V against a supply) |
| `test_installer.py` | which adb device the installers take: they ask whenever it is not the only one and an F50/U30 Air |
| `test_vpn.py` | `mu300-vpn`: VLESS URI parsing, JSON, which networks stay out of the tunnel, the sing-box config |
| `test_update.py` | `mu300-update`: release files per system and kernel, boot image byte helpers, whether a kernel bundle may go onto this device |
| `test_boot_image.py` | `boot/build-boot-image.py`: the generic ramdisk, the U30 Air's modules and order |
| `installer.Tests.ps1` | `install.ps1`: `T` with every translation, `NormalizeAnswer`, `Gib` |

The device scripts run under dash (Ubuntu's `/bin/sh`), bash and busybox ash (OpenWrt); every shell test runs under
each of them that is installed. Commands that touch the device (`nft`, `ip`, `id`, `sing-box`) are stubs, and the
scripts read a fake `/` through `MU300_SYSROOT`, `MU300_DISK` and friends; `mu300-update` and `mu300-vpn` are sourced
with `MU300_LIB=1`, which defines their functions and runs nothing.
