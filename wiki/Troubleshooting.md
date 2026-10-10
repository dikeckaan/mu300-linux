# Troubleshooting

**The simple version:** most problems end the same safe way: the device goes back to Android, and you try again. Below
are the known problems, what causes them and what to do. If yours is not here, collect logs and
[open an issue](https://github.com/dikeckaan/mu300-linux/issues).

## Before anything else

* Wait **two minutes** after power-on; the first boot is slow.
* Use a **good USB cable** plugged straight into the computer.
* Make sure you use the **right address**: `192.168.77.1` (F50) or `192.168.78.1` (U30 Air).
* The USB serial console works even when networking does not: `screen /dev/cu.usbmodem* 115200` on macOS.
* After a fallback to Android, collect logs from a computer with `tools/collect-logs.sh`.

## The device does not come back after installing

Wait two minutes. If there is still nothing, unplug and replug it. Every boot that does not finish counts, and after 5
of them in a row (or the number you chose) the device starts Android. Then run `tools/collect-logs.sh` and open an
issue with the result.

## Back in Android without asking, on kernel 6.18

About one boot in 20 on one board hangs in its first seconds, and the device then falls back to Android (this can take
around 20 minutes). Start Linux again with `su -c mu300-linux` or the Magisk module's Action button. If it keeps
happening, try 7.2 or 5.4: `sudo mu300-update kernel 7.2`.
[FINDINGS 31m](https://github.com/dikeckaan/mu300-linux/blob/main/docs/FINDINGS.md#31m-hard-hangs-in-the-first-seconds-under-618-open)

## Back in Android after an update

With older boot images a single crash or reset of Linux sent the device back to Android. Start Linux again with
`su -c mu300-linux`, then update (see [Updating](Updating#coming-from-a-very-old-release)). If Linux does not start any
more, run `./install.sh` from a computer and choose **update**: it writes a fresh boot image and keeps your data.

## The computer sees the device but gets no address (macOS)

macOS does not set up a network interface it has never seen while the screen is locked. Each device has its own USB
MAC address, so the first time one is plugged in (or after an update that brought new addresses) **unlock the Mac** and
the interface appears. With an F50 and a U30 Air plugged in together, they are `192.168.77.1` and `192.168.78.1`; two of
the same kind need `/etc/mu300/lan.conf` to tell them apart.

## No internet

Check that the SIM has a **data plan**, then run `sudo mobile-data status`. A missing plan looks like a connection that
keeps dropping. Leave the APN empty unless your carrier needs one ([Mobile Data and APN](Mobile-Data-and-APN)).

## OpenWrt on kernel 5.4: no address, no web page, nothing joins the hotspot

Releases before v2026.10.13: the firewall's boot ruleset had no rules for the LAN, and on 5.4 the reload that should have
added them always failed. **Fixed from v2026.10.13 on**; update. On an affected release, log in over the USB
serial console (`ttyGS0`, a root shell) and run:

```sh
nft delete flowtable inet fw4 ft; fw4 reload
```

[FINDINGS 38c](https://github.com/dikeckaan/mu300-linux/blob/main/docs/FINDINGS.md)

## The installer prints nothing for minutes and the device gets hot

A read past the end of the internal storage never returned on devices whose partition table ends at the end of the disk
(the 32 GB variant, and an F50 with no gap behind `userdata`). **Fixed from v2026.10.13 on.** Reboot the device
to end the stuck reads, then install with the current installer (it updates itself from GitHub when it starts).
[FINDINGS 38a](https://github.com/dikeckaan/mu300-linux/blob/main/docs/FINDINGS.md)

## `--check` reports no free space

You probably have the **32 GB variant**. Use an SD card (F50), or let the installer shrink `userdata` (experimental,
erases Android's data). See [Installation](Installation#the-32-gb-variant). If the numbers look like neither a 64 GB nor
a 32 GB device, open an issue with the `--check` output.

## `--check` says the free space is "not empty"

Something has written into the unpartitioned area. Installing would overwrite it, and the installer makes you type
`overwrite`. If you are not sure what is there, stop and ask in an issue.

## I forgot the password

You do not need to log in to get out (unless Linux is [locked](Going-Back-to-Android#locked-linux)):

1. **Back to Android:** unplug the device about ten seconds after it powers on, then plug it in again, as many times in
   a row as your failed-boot count (5 by default). The device then falls back to Android.
2. **Set a new password** from your computer, without booting Linux:
   ```sh
   tools/reset-password.sh            # ubuntu, openwrt or both
   ```
   It mounts the Linux filesystem from Android and rewrites the password, keeping all your data.
3. Start Linux again with `su -c mu300-linux` (or `boot/android-boot-linux.sh work/boot-linux-slotb.img`), or reboot if
   Linux is the default.

Re-running `./install.sh` and choosing **update** also keeps your data and sets the password you type.

## Joining a Wi-Fi network fails

* WPA3-only networks cannot be joined (the driver has no SAE). Switch the router to WPA2/WPA3 mixed mode.
* While the hotspot is on, `wifi-client connect` saves the network and asks for a reboot.
See [Wi-Fi Hotspot and Client](Wi-Fi-Hotspot-and-Client).

## Kernel warnings are not in `journalctl -k`

On Ubuntu they are in `journalctl -t kernel` (warnings and errors only, from the start of each boot). Everything else is
in `dmesg`. Repeating vendor messages are filtered out by `/etc/mu300/kmsg-ignore`.

## Websites think I am in another country

The device has no GPS; websites guess from the IP address, and mobile operators and VPN servers often look like another
city.

## Downloads are slow

GitHub's CDN throttles single connections in some regions. The installer already downloads in 8 parallel chunks; set
`MU300_FETCH_JOBS` to change that, or `MU300_RELEASE_URL` to use your own mirror.

## "could not arm the Linux slot for a trial" during an update

Harmless when updating from v2026.10.14 or older: the older `mu300-next-boot` does not know `--trial`. The fallback to
Android still works.

## The U30 Air battery drains while plugged in

The mainline kernels (6.18, 7.2) of v2026.10.11 and older leave charging off. Update (charging on mainline comes from
v2026.10.12 on), or use kernel 5.4.

## The U30 Air stays dark after starting from a charger

A boot that started because a charger was plugged in stays a **charging boot** (LED blinking, hotspot and modem down)
until you press the **Wi-Fi key**.

## Things that are not bugs

* **No screen output** over USB-C and **no sound**: the hardware path is not there ([Hardware Notes](Hardware-Notes)).
* **A load average around 12 on 5.4:** vendor kernel threads waiting in D state are counted; the CPU is mostly idle.
* **About 1.4 GB of RAM:** the modem firmware reserves the rest.

## Never

* Never use OpenWrt's `sysupgrade` or flash OpenWrt firmware images.
* Never post your backup folder or logs containing your IMEI publicly.
