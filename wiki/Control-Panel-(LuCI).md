# Control Panel (LuCI)

**In one sentence:** on OpenWrt you manage the device from a web page; the `openwrt-luci` system adds the **MU300
control panel**, a dashboard for the 5G modem, SIM, SMS and battery.

**The simple version:** LuCI is the router settings page you may know from home routers. The MU300 panel is an extra
set of pages made for this device: how strong the signal is, which bands it uses, your text messages, the battery.

## Open it

In a browser on a computer or phone connected to the device (USB or its Wi-Fi):

* F50 / MU300: **http://192.168.77.1**
* U30 Air: **http://192.168.78.1**

Log in as `root` with the password you chose at install.

## Plain OpenWrt vs. the control panel

| | OpenWrt (`openwrt`) | OpenWrt with the panel (`openwrt-luci`) |
|---|---|---|
| LuCI (network, wireless, firewall, packages) | yes | yes |
| MU300 pages (dashboard, Cellular, Power, CPU, Languages) | - | yes |
| Theme | LuCI's default | Aurora (Bootstrap stays installed) |
| IPv6 from the carrier | prefix extension | relayed (router advertisements and NAT66) |
| Magisk zip | yes | yes (since v2026.10.18) |

Pick it at install ("Which OpenWrt?" -> 2, or `MU300_OPENWRT=luci`), or switch an installed device with
`sudo mu300-os openwrt-luci` and reboot (the system must be installed).

## The panel's pages

* **Status dashboard:** live radio readings (signal, bands, cells, temperatures), the operator's name, the mobile
  data state and the current download and upload speed, every second; on the U30
  Air also the battery: level, whether it charges, and the power in watts. The home page also has **Switch to
  Android** and **Lock Linux** (see [Going Back to Android](Going-Back-to-Android)).
* **Cellular > Network locks:** network mode, band, cell and EN-DC locks that persist across reboots and are replayed
  at boot. **Reset all to automatic** clears them. Locks live in the modem, so they also apply in Android.
* **Cellular > SMS:** read, send and delete messages (see [SMS](SMS) for the one rule to remember).
* **Cellular > SMS forwarding:** pass incoming messages on to a webhook, a Telegram chat or another phone (see
  [SMS](SMS#sms-forwarding)).
* **Cellular > Data usage:** mobile data per day and per billing cycle, with a reset day and a monthly cap
  (`mu300-traffic`, see [Mobile Data and APN](Mobile-Data-and-APN#data-usage)).
* **Cellular > AT terminal:** guarded AT commands over the same channel the system uses.
* **Cellular > TTL:** a fixed TTL for mobile data (`mu300-ttl`).
* **Cellular > Device management:** USB role (device or host), the USB network mode (NCM, ECM or RNDIS, applied at the
  next boot), and host-mode adapters that can join the LAN bridge.
* **Cellular > Adapter settings:** how the panel reaches the modem (AT backend, serial port, custom adapter).
* **System > Languages:** interface language, and the lang extra.
* **System > Power:** the active power profile and why, battery and power source, the idle settings of the three
  profiles, the saver threshold and the charge limit (100 or 80 %).
* **System > CPU:** the CPU profile: saving, balanced (the default) or performance (`mu300-cpu`). It never touches
  the voltage, and the thermal protection stays in charge in every profile.

## Languages

Both OpenWrt systems speak **English, Turkish and Simplified Chinese** out of the box. The interface starts in
English: switch under System -> System -> Language and Style, or on `openwrt-luci` under System -> Languages. An update
keeps your choice.

The **lang extra** (about 2 MB) adds LuCI in 40 more languages and the panel in 29 of them:

```sh
mu300-extra install lang                                               # from the release of this system
MU300_EXTRA_FILE=/tmp/mu300-extra-lang.tar.gz mu300-extra install lang  # from a file, offline
mu300-extra lang                                                       # which languages are offered
mu300-extra remove lang
```

The panel's translations other than Turkish and Chinese are machine (AI) translations; corrections are welcome (see
[Contributing](Contributing)).

## Credits

The panel is the work of kanoqwq ([kanoqwq/mu300-linux](https://github.com/kanoqwq/mu300-linux), branch
`clean-tf-7.2`), ported here with the translations rewritten as standard LuCI catalogs. The theme is
[Aurora](https://github.com/eamonxg/luci-theme-aurora) by eamonxg. The app's own notes:
[openwrt/luci-app-mu300/README.md](https://github.com/dikeckaan/mu300-linux/blob/main/openwrt/luci-app-mu300/README.md).

## OpenWrt reminders

* Never `sysupgrade` or flash OpenWrt firmware images.
* `apk upgrade` is fine, except the `kernel` and `kmod-*` packages.
* On kernel 5.4, a firewall change saved in LuCI may need `nft delete flowtable inet fw4 ft; fw4 reload` (or a reboot)
  on older releases; v2026.10.17 fixed `fw4 reload`/`restart` with flow offloading on 5.4.
