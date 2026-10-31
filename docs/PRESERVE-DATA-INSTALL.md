# Rooted TCP adb and preserving Android data while making room (experimental)

The desktop installers have an explicit [wireless installation mode](WIRELESS-ADB-INSTALL.md) with connection,
identity, job-status and Wi-Fi/power handling. Independently of that new mode, they can already use an authorized
TCP adb device: run
`adb connect <Android-IP>:5555` first and select that target with `ANDROID_SERIAL`. This does not enable adb or
root the device. The hotspot and adb address can change when switching between Android and Linux. On Linux,
use its SSH/LuCI address; do not assume that Android's TCP adb daemon is available there.

The normal make-room workflow can reset Android. `tools/preserve-space.py` is a separate, opt-in preparation
tool for the shared U30 Air/M3 software, using the data-preserving workflow measured on an M3. It leaves the existing USB backup/install,
reset/resume, command names and hardware handling unchanged. M3 recognition in the normal installer is a separate
change ([PR #456](https://github.com/dikeckaan/mu300-linux/pull/456)); this tool does not require that PR to prepare
space, but an installer without M3 recognition will still refuse the later M3 installation.

## Exact scope

The shared path accepts `MU5352 / MU5352` and U30 Air (`U30Air`, `U30_Air` or `U30 Air` with device `U30Air`)
on `ums9620`, with an Android `5.4.254-android12-9-*` kernel and the measured 32 GB layout. Model and firmware
names alone do not establish support: the device-side helper checks the live `/data` mapper, F2FS geometry and
both GPT copies again. It discovers the mapper by the mounted device number, not a hardcoded `dm-45`.
The mapper must directly back onto `mmcblk0p75`. Ext4, another kernel series, a multi-device userdata mapping, another encryption
mapping, existing Linux space or another partition layout are refused. F50/V50 paths are not changed. U30 Air
support uses the same checks and code; the resize has so far been measured on M3/B18 only.

This first version makes **4 GiB** only. It uses the kernel's `F2FS_IOC_RESIZE_FS` on mounted, decrypted `/data`,
checks both F2FS superblocks, then changes only userdata's ending LBA and the GPT CRCs. The encrypted userdata
mapping and metadata partition are not recreated. The backup GPT is flushed/read back before the primary entries
and header; the protective MBR is preserved. It never formats, erases Android, changes a boot slot, requests a
recovery reset, rereads the live partition table, or reboots automatically.

An online shrink and GPT update are not an atomic transaction. Power loss, storage failure or a kernel bug can
still destroy data. Have an independent complete backup and a working recovery method, keep stable power where
possible, and start with at least 80% battery. The tool saves and hashes GPT, boot, TrustOS, metadata and misc
recovery copies on the computer; these **do not back up userdata or all Root files**. Never publish the state
directory: its recovery copies and eMMC identity are private.

## Use before installing, from rooted Android

Requires host Python 3.8+, adb, and the static aarch64 helper. Build it with Docker (including arm64 execution
support) on Linux/WSL: `sh tools/preserve-space/build.sh /path/to/preserve-space`. Alternatively compile the source
with an aarch64 Linux musl cross-compiler and `-std=c11 -Os -Wall -Wextra -Werror -static`. No binary is downloaded
or included in the regular releases by this change.

The following commands work in PowerShell too with `python` in place of `python3`. The address is an example;
use the already enabled Android adb endpoint. `--serial SERIAL` can be used instead for USB adb. Every adb call
is pinned to that explicit target, including after `adb connect`.

```sh
python3 tools/preserve-space.py --adb-address 192.168.0.1:5555 --state backup/m3-space plan --helper /path/to/preserve-space
# Inspect plan.json and the recovery copies; plan has not resized anything.
python3 tools/preserve-space.py --adb-address 192.168.0.1:5555 --state backup/m3-space apply --backup-confirmed
python3 tools/preserve-space.py --adb-address 192.168.0.1:5555 --state backup/m3-space status
```

`apply` launches a root-owned worker independent of the adb connection. Do not launch another apply because Wi-Fi
disconnected or a host command timed out: reconnect and use `status`. An atomic start marker refuses repeated
launches; a device-wide lock prevents two plans resizing concurrently. An unsuccessful result or interrupted GPT
write requires inspecting the log and both GPT copies before recovery; deleting markers is not a recovery procedure.
An unsupported/failed shrink does not fall back to a reset or a raw filesystem edit.

Wait for `EXIT=0` and `BOTH_GPT_COPIES_FLUSHED_AND_VERIFIED_REBOOT_REQUIRED`. Then manually reboot **Android**
(not Linux), reconnect to its Wi-Fi/adb endpoint, and run:

```sh
python3 tools/preserve-space.py --adb-address 192.168.0.1:5555 --state backup/m3-space verify
```

Binary recovery copies use device-side staging and `adb pull`, following the existing backup transfer logic;
`su` stdout is used for text only. The original backup and USB installation logic is retained.

Verification checks root adb access, the same eMMC, the kernel's new userdata size, both F2FS superblocks, both
planned GPT copies, and unchanged boot/TrustOS hashes. Only after this succeeds use the regular installer; its
existing free-region probe finds the prepared 4 GiB. Do not accept a reset/make-room prompt in place of successful
verification. Keep the private recovery files after installation. The tool deliberately provides no grow-back
operation or automatic retry after failure.

## Evidence and limits

On 2026-10-29 the two-stage method was run on one MU5352/B18 over rooted TCP adb: F2FS shrank from 6,099,968 to
5,050,368 4 KiB blocks, userdata ended at LBA 52,678,655, and the installer found 4 GiB starting at byte
26,973,569,024. Android rebooted with Root and wireless adb retained. OpenWrt was then installed and an
Android/Linux roundtrip worked. The previously installed Root/TCP adb setup was retained by keeping userdata;
this does not establish that every Root method survives every firmware's shrink.

This contribution packages that method with stricter checks, detached execution and offline/fake-device regression
tests. The packaged tool has **not** been run through another destructive resize on that now-installed device.
Its host/native GPT planners are compared on synthetic tables, including refusal and interrupted-write cases.
The original device run is evidence for the method, not a claim that this package or another model was flashed.
