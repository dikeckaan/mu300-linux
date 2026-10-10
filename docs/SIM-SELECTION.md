# F50 internal and external SIM selection

The default remains the external card (slot 0). Some F50 units also have an internal
SIM exposed as slot 1. Selecting slot 1 does not provision an eSIM or write any SIM
identifier. It requires a device already fitted with an active internal SIM.

| Source | Event / command / data TTY | CID 1 interface |
| --- | --- | --- |
| External (0, default) | nr0 / nr1 / nr2 | sipa_eth0 |
| Internal (1) | nr3 / nr4 / nr5 | sipa_eth8 |

## OpenWrt

In Network → Interfaces → WAN, choose **SIM source** and set that card's APN and
PDP type. Save the configuration, then reboot the device into Linux. Each source
retains its own APN/PDP settings; changing the selector does not erase the other
profile. Only one cellular interface named `wan` is supported by this selector.

The equivalent commands for the tested China Mobile internal card are:

```sh
uci set network.wan.apn_internal='cmnet'
uci set network.wan.pdptype_internal='IPV4V6'
mu300-sim select internal
mu300-sim status
```

For callers that share the dual-SIM command vocabulary, `mu300-sim default 1`
selects the external card and `mu300-sim default 2` selects the internal card.
`mu300-sim status --json` reports physical card numbers (`active` and `default`)
and whether the detected device supports slot 1 (`slot1_supported`), along with
`hot: 0` and `available: 0`; F50 selection is boot-time only. The
`hot` and `switch` commands fail explicitly instead of attempting a live SIPC
channel switch.

`mu300-sim select external` restores slot 0 on the next Linux boot. The external
profile uses the existing `network.wan.apn` and `network.wan.pdptype` options.
Use that card's carrier APN, not necessarily `cmnet` (`ctnet` was used for the
China Telecom comparison card). Selection does not change the default boot OS.

The active slot is recorded atomically in `/run/mu300/sim-slot` when modem userspace
first starts. All callers use that value until reboot, including teardown after
the next-boot selection has changed. Do not delete this file or restart TTY owners
to attempt a live switch: closing and reopening SIPC TTYs can wedge the channels.
The existing OpenWrt automatic WAN setup uses the selected card after reboot.

On systemd installations, `mu300-sim select` stores the choice in
`/etc/mu300/sim-slot`; configure the selected carrier in the existing
`/etc/mu300/mobile-data.conf`. The two-profile LuCI editor is OpenWrt-specific.

## Why the data-route command is needed

On the tested F50, the internal card registered, received a PDP address, and
returned `CONNECT` to `AT+CGDATA="M-ETHER",1`, yet DNS, TCP and IPv6 router
solicitations received no reply. The SIPA delegate was loaded and responding.
Selecting the packet-data route with `AT+SPSWDATA` immediately restored replies
and IPv6 router advertisements. The command is used by the stock RIL's preferred
data-modem path. This patch sends it only for the opt-in slot 1 path and requires
an `OK` response before reporting a successful dial.

The slot 1 context definition and PCO/QoS setup follow the observed stock RIL.
The original slot 0 sequence is retained. Stock Android requests `cmnet/IPV4V6`
on this card but reports `cmiot5g` in `CGCONTRDP` after a successful connection;
that difference alone is not evidence of a wrong configured APN.

The dashboard shares slot 1's general command daemon; it must not fall back to
the slot 0-only nr6/nr7 pool. Its persistent identity cache is separate per slot.
The IPv6 monitor and USSD listener use the selected event stream. Empty LTE
neighbor data is also handled without aborting the rest of the dashboard.

## Validation status

The slot 1 routing sequence and dashboard fixes were exercised on an existing
OpenWrt 25.12.5 installation with Linux 5.4.254. DNS, HTTP 200, growing RX counts,
IPv4/IPv6 assignment and rebooted automatic startup were observed. Android/Linux
identity comparisons matched; no identity writes were used.

The generalized selector in this branch still requires a clean-flash hardware
regression. In particular, test external → internal → external across reboots
with both cards present, checking the active identity, APN, interface, DNS/TCP,
old interface cleanup, and dashboard data each time. Do not claim live switching
or mainline-kernel hardware validation from the existing 5.4 results. No device
identifiers, identity hashes, SSH keys or raw private traces are in this patch.
