# Installing over rooted wireless/TCP adb

The desktop installer can use an already enabled, authorized **rooted TCP adb** endpoint as an explicit transport.
This adds connection management to the existing installation; it does not enable root, open an adb port, perform
Android's pairing-code setup, or change a device's hardware profile. Use a trusted network. M3 recognition remains
the separate change in [#456](https://github.com/dikeckaan/mu300-linux/pull/456).

Connect the computer to the device's hotspot, or another network that can reach Android's adb endpoint. Wi-Fi
does not supply power: **connect a stable charger and keep it connected during installation**. Wireless mode reads
battery/charging telemetry, recommends charging when running on battery, and gives an additional warning at 30%
or less. Unknown telemetry is not treated as a charged battery. These are warnings, not a request to interrupt
an active filesystem or boot write.

## Start the normal installer

Windows PowerShell (Python is found/installed by the existing installer):

```powershell
.\install.ps1 -AdbAddress 192.168.0.1:5555 -Check
.\install.ps1 -AdbAddress 192.168.0.1:5555
```

Linux/macOS (Python 3.8+ required):

```sh
./install.sh --adb-address 192.168.0.1:5555 --check
./install.sh --adb-address 192.168.0.1:5555
```

Use Android's actual address; the examples are not discovery defaults. The option accepts a literal IPv4 address
and port. `MU300_ADB_ADDRESS` is the equivalent environment/answers-file setting; `MU300_ADB_TIMEOUT` sets the
connection wait window (1..600 seconds, default 120). The explicit endpoint is also exported as `ANDROID_SERIAL`
for child tools. Existing USB invocations and backup/reset/resume rules stay the same. Wireless mode uses the
text installer and skips self-update during the session so the source and transport helper stay together.

The host records Android's serial, eMMC CID and Android slot, then checks them after reconnection and before
commands. It never falls back to a phone, emulator or another router at the same IP. Each run gets a private
staging directory; existing image, boot verification and backup code uses that directory without renaming commands,
modules, services or device profiles. Keep the normal backups; this transport feature does not replace them.

## Wi-Fi changes and lost connections

Where the host exposes its current Wi-Fi name, a change generates an explicit warning with the old/new names.
Changes noticed by quiet probes are also shown at visible pre-write checkpoints. Check that the computer joined
the intended hotspot and that the adb address is still correct. SSID detection is best effort (netsh on Windows,
nmcli/iwgetid where available on Linux); on hosts where it is unavailable the installer says so, and connection
failures explicitly tell the user to check Wi-Fi and the endpoint. It does not change Wi-Fi automatically.

Connection checks and temporary file transfers can retry, always against the same identity. An ordinary shell
command whose completion reply was lost is **never automatically replayed**: it might already have written data.
The session stops for review. This includes boot-image/slot commands; reconnecting is not permission to repeat them.

The long device-side installation runs as a root-owned detached worker, with its own log/result and a single-start
marker. It survives loss of the host connection. A device-wide worker lock prevents two wireless workers; SD-card
stall protection keeps its existing per-boot lock under `/data/adb` across wireless sessions.

After rejoining the network, inspect the same job without starting another installation:

```powershell
.\install.ps1 -AdbAddress 192.168.0.1:5555 -AdbStatus
```

```sh
./install.sh --adb-address 192.168.0.1:5555 --adb-status
```

If the address changed, supply the new address; the same saved device identity must still match. `-AdbStatus` /
`--adb-status` can omit the address to use the saved endpoint. It reports status only: it does not arm the Linux
slot or resume the remaining host steps automatically.

After reviewing a **finished** device job, `-AdbRestart` / `--adb-restart` explicitly starts the normal installer
again with fresh checks and the normal existing-system questions. For an unknown foreground command, manually
reboot back into Android first so the old process cannot still be running. Do not reboot an active worker merely
because Wi-Fi disconnected. Do not delete session/lock files to bypass these checks. Use one work directory per
device, and retain `work/wireless-install.json`, its history, device logs and the existing backups for recovery.

Android's TCP adb endpoint and Linux's SSH/LuCI address can differ. After successful installation, rejoin the
Linux hotspot and use the address the installer printed. Android adb need not be available in Linux. Returning
to Android later still requires its wireless adb setup to be enabled. The existing factory-reset make-room route
can erase that setup; [preserving-data preparation](PRESERVE-DATA-INSTALL.md) is a separate optional function for
the matching U30 Air/M3 layout, not a silent replacement for reset.

## Validation

Rooted wireless adb installation and preserving-data shrink were used successfully on one M3/B18 on 2026-10-29.
This change adds reusable main-installer options, identity/connection guards, Wi-Fi/power notices and detached jobs
with fake-device and real local POSIX-worker tests. Those new options have not been used to repeat an installation
on the already-installed M3. U30 Air uses the same transport path; no new U30 Air hardware test is claimed.
