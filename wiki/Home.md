# MU300 Linux wiki

**In one sentence:** this project puts a real Linux system (Ubuntu or OpenWrt) on the ZTE F50 / MU300 and the ZTE
U30 Air pocket 5G hotspots, next to Android, so the little box becomes a Linux router and server with its own 5G
modem.

![Android and Linux side by side on one device](https://kaandikec.com/mu300-linux/assets/img/two-systems.svg)

## The simple version

Your hotspot is a tiny computer. Out of the box it runs Android, hidden behind a web page, and does one job: share
mobile internet. This project adds a second system, Linux, in a part of the storage Android does not use. When the
device starts, it starts Linux. If Linux ever fails to start a few times in a row, the device quietly goes back to
Android on its own. Android is never removed, and one command brings it back for good.

Think of it as a Raspberry Pi that already has a 5G modem, a Wi-Fi access point and 32 GB of storage inside.

## Where to start

| If you want to… | Read |
|---|---|
| understand what you need and install it | [Installation](Installation) |
| pick between Ubuntu, OpenWrt and OpenWrt with the control panel | [Choosing a System](Choosing-a-System) |
| pick a kernel (5.4, 6.18 or 7.2) | [Kernels](Kernels) |
| get mobile data working, set an APN | [Mobile Data and APN](Mobile-Data-and-APN) |
| change the hotspot, or join another Wi-Fi | [Wi-Fi Hotspot and Client](Wi-Fi-Hotspot-and-Client) |
| read and send text messages | [SMS](SMS) |
| route everything through a VPN | [VPN](VPN) |
| use the web control panel | [Control Panel (LuCI)](Control-Panel-(LuCI)) |
| update, or roll an update back | [Updating](Updating) |
| go back to Android, or remove Linux | [Going Back to Android](Going-Back-to-Android) |
| fix something | [Troubleshooting](Troubleshooting) and [FAQ](FAQ) |
| look up a word | [Glossary](Glossary) |
| know how the hardware behaves | [Hardware Notes](Hardware-Notes) |
| build it yourself or help out | [Building from Source](Building-from-Source), [Contributing](Contributing) |

There is also an illustrated website with the same information for beginners, in English, Turkish and Chinese:
**https://kaandikec.com/mu300-linux/**

## Supported devices

| | ZTE F50 / MU300 | ZTE U30 Air |
|---|---|---|
| Chip | Unisoc T760 (UMS9620), board `ums9620_2h10_feimao` | the same |
| Power | USB only | battery (4050 mAh) |
| USB network address | `192.168.77.1` | `192.168.78.1` |
| SD card | yes: Linux can live on the card | no card slot |

The installer recognises which device it is talking to. The **U30 Pro** is a different chip (UMS9632) and is
**not** supported. More in [Hardware Notes](Hardware-Notes).

## What you get, and what you give up

**You get:** Ubuntu 24.04 or 26.04 LTS, or OpenWrt 25.12 (plain or with a control panel for the modem); three
kernels to choose from; 5G/LTE internet shared over Wi-Fi and USB; SSH; Bluetooth; SMS and USSD; an optional VPN
module; a `raspi-config`-like menu called `mu300-toolkit`; automatic fallback to Android; updates on the device.

**You give up:** only one system runs at a time (a reboot switches); there is no screen output and no sound; about
1.4 GB of the 2 GB RAM is usable, because the modem keeps the rest.

## A hobby project, at your own risk

This is an experimental hobby project. It is not a product, it has no support line and it comes with **no
warranty of any kind**. Rooting and unlocking the device are **not** part of this project and are done at your own
risk. Writing to a phone-class device can leave it unusable; keep a backup and do not install on a device you cannot
afford to lose. Nothing here is endorsed by ZTE, Unisoc or any operator. Read the
[full notice in the README](https://github.com/dikeckaan/mu300-linux#a-hobby-project-at-your-own-risk).

## Links

* Source code and README: https://github.com/dikeckaan/mu300-linux
* Releases (prebuilt images): https://github.com/dikeckaan/mu300-linux/releases
* VPN module: https://github.com/dikeckaan/mu300-linux-vpn
* Deep technical notes: [docs/FINDINGS.md](https://github.com/dikeckaan/mu300-linux/blob/main/docs/FINDINGS.md)
* Issues: https://github.com/dikeckaan/mu300-linux/issues
