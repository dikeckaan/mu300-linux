# SIM2 NR locks: U30 Air / M3 and experimental F50 / V50

The OpenWrt panel can apply NR band and NR cell locks through the native SIM2
brokers on boards identified by `mu300-device` as `u30air`. M3 is covered when it uses this
same board profile; no new device identifier is introduced. F50 and V50 have a
separate, default-off experimental profile described below. Custom/serial AT
backends keep their existing path and protections.

This covers NR bands the existing mask codec can encode (n1, n5, n8, n28,
n41, n78), a specified/current NR cell, and NR unlock. LTE, network mode,
EN-DC and reset-all remain guarded on SIM2. A live change requires an online
SIM2 bearer on sipa_eth8; applying locks to an offline SIM2 is not covered.

The panel's existing lock jobs queue the operation. The platform controller
holds the SIM-control lock, stops the configured data interface, then takes
mobile-data's radio lock. Each command explicitly selects card 1 (the public
SIM2) on its own broker; it never opens a modem TTY directly. RF-off uses the
SIM2 main broker and RF-on its data broker. It does not power-cycle either SIM
or move the packet-data route.

Replies and lock read-backs are checked before and after RF restart. The
previous NR values are journalled before the first write. A refused command,
read-back mismatch or missing bearer fails the job and attempts restoration;
only a verified change with the bearer back is committed. A missing bearer
does not trigger a reboot. If restoration cannot finish, the journal is kept
for recovery in the next native SIM2 startup.

Saved values live under `sim2-native/` in the panel's validated `state_dir`,
separate from SIM1's files. The native cold/live SIM2 sequence replays them
before RF-on, respecting the existing Apply at startup switch. Pending rollback
recovery runs even when that switch is off. The active/default SIM selection,
hot-switch preference and boot-fallback policy are not changed by locking.

## Validation

Hardware testing is limited to **U30 Air and M3**. The detailed recorded run
below is from the U30 Air; the owner also confirmed successful M3 SIM2 band
and cell locking on 2026-11-01. No F50/V50 hardware validation is claimed.

2026-10-30, U30 Air, modem W25.24.1, OpenWrt 25.12.6 / kernel 7.2.11:

- SIM2 n41 write/read-back, RF restart and bearer recovery.
- Current NR cell write/read-back, RF restart and bearer recovery.
- A full reboot: n41 and the cell lock retained; native SIM2 startup, default
  SIM2 and hot-switch preference retained, bearer up.
- Both NR unlock operations completed; final NR mask automatic, no NR cell lock.
- Preliminary card-scoped probes left SIM1's NR settings unchanged.

The platform controller passed a second full reboot with both locks retained.
A final consecutive n41 / NR-cell unlock / automatic-NR run also passed. Cleanup
does not call ifup again after success: doing that restarted the restored
netifd bearer and made the next job see an offline card.

M3 uses the same board profile. The M3 hardware result is owner-confirmed;
no separate M3 firmware/version matrix was supplied. Other modem revisions,
all individual supported NR bands and a switch between two data-capable SIMs
have not been independently measured here.

`tests/test_sim2_locks.py` exercises the transaction, rejection/rollback,
per-SIM state and early recovery against a stateful fake CP. The existing
SIM cold-start, hot-switch, plugin and rpcd suites cover the integration hooks.

## Experimental F50 / V50 profile (simulation only)

This extends **NR bands and NR cells only** to the existing boot-pinned SIM2
path. It does not add LTE writes, mode/EN-DC changes, reset-all, a new hot-switch
implementation or support for another manufacturer's modem. There is no F50 or
V50 hardware lock result for this implementation. The startup switch defaults
on for U30 Air/M3 and off for other models; the native sequence stays separate.

### Model-based startup switch

In LuCI **Cellular > Adapter settings**, **SIM2 NR locks at startup** offers
Model default, Enabled and Disabled. Model default enables U30 Air/M3 and
disables F50/V50 (and unsupported models). M3 dispatches through the shared
`u30air` hardware profile. Save and reboot to apply a changed choice.

For F50/V50 testers, select Enabled. The UCI equivalent is:

```sh
uci set unisoc_modem.main.sim2_nr_locks='1'
uci commit unisoc_modem
```

This is an installation-wide opt-in for the detected F50 or V50, not a claim
that its modem revision has been tested. The option defaults to `auto` on new
installs; an absent option has the same model-based default. `0` explicitly
disables it on any model and `1` enables a supported profile. The AT init service
calls `mu300-sim2-lock boot-config` before starting owners or RF; it latches
`off`, `u30air`, `f50` or `v50` in `/run/mu300/sim2-nr-locks` once per boot.
Saving the form, reloading the page or restarting AT services cannot activate
the feature mid-boot. Selecting Disabled and rebooting disables the profile.
The switch does not clear modem NV: unlock NR bands/cells before disabling it.

SIM2 must already be selected and online through the ordinary boot selector;
this switch does not change the active/default SIM, APNs or boot OS. On an F50
without an installed, usable internal card it does not create one. On a V50,
choose the desired physical card with the existing card selector and reboot.
`mu300-sim2-lock status` reports the enabled profile and `experimental: true`.

### Addressing, capability checks and persistence

* F50/V50 logical SIM2 uses nr4/nr5 and `sipa_eth8`, but the boot-pinned daemon
  directories are `/run/mu300-at` and `/run/mu300-at2`. The native U30 Air still
  uses `/run/mu300-at4` and `/run/mu300-at5` with explicit card prefixes.
* Boot-pinned commands do not change the card selector. Before writes, both
  command and data brokers must report `SPACTCARD: 1`. Owners must already exist; no TTY
  is opened or reopened. F50/V50 may report RF-off as CFUN 0 or 2.
* A requested NR band must be both encodable by the existing six-band codec
  and present in this card's `SP5GCMDS` capability reply. A missing, malformed
  or incompatible reply refuses the request before taking down WAN. There is
  no U30 Air capability fallback for another board.
* F50 state is `state_dir/sim2-f50/`. V50 state is
  `state_dir/sim2-v50-boardN-cardM/`: M is physical card 1 or 2 (ZTE's zero-based
  card IDs), obtained from the actual GPIO switch and validated against the
  board table. Saved next-boot selection is never used as the current identity.
* Recovery journals under `/etc/mu300/` use the same profile key. If a physical
  card changes while a transaction waits or reconnects, the worker refuses
  further commands and retains any journal for the original card. It never
  restores one card's journal onto another. Firmware NV can still be shared
  between cards on a stack: separate files prevent software replay leakage,
  not physical modem NV isolation.
* An apply verifies replies and lock read-backs before/after RF restart **and
  after bearer recovery**, before persisting. Failure attempts rollback and
  leaves unverified recovery data intact. No automatic reboot is introduced.

The ordinary `mobile-data radio_on` calls experimental replay under its radio
lock, before the first dial, even when LK left CFUN=1. It replays once per boot
profile and restores interrupted writes even if Apply at startup is off. Saved
values are validated before replay writes; a failure ends that radio-on round
without enabling RF or dialling past an unknown lock write. The ordinary radio
watchdog may retry. An active live transaction holds SIM-control throughout
reconnection: the replay worker skips it nonblockingly, so an `ifup` cannot
mistake its uncommitted journal for a crashed boot or deadlock on reversed locks.

### Tester checklist

Use a known working SIM2 connection, record device/model, board ID on V50, modem
firmware, OpenWrt/kernel version and selected physical card. Do not post SIM
identifiers. Test NR automatic -> one advertised band -> automatic; one NR
cell -> NR unlock; verify actual read-backs and traffic after each. Repeat a
normal reboot and a power-off/on with saved locks. Check SIM1 saved state is
unchanged. On V50, test each available SIM2 physical card separately and check
the state/recovery files do not cross over. Keep LTE/mode/reset tests outside
this profile. Report failures as experimental results, not verified support.

The stateful fake CP tests cover F50/V50 broker routing, default-off boot
latching, capability rejection, CFUN 2, cell/band apply and rollback, read-back
after reconnect, early replay/recovery, live `ifup` re-entry and physical-card
state isolation. These are simulated transactions; they do not establish RF
behaviour, over-the-air cell residency or power-loss durability on those boards.
