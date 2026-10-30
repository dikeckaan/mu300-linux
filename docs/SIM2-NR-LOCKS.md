# Native SIM2 NR locks on U30 Air / M3

The OpenWrt panel can apply NR band and NR cell locks through the native SIM2
brokers on boards identified by `mu300-device` as `u30air`. M3 is covered when it uses this
same board profile; no new device identifier is introduced. F50, V50 and
custom/serial AT backends keep their existing path and protections.

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

M3 is included through the shared board profile. These measurements were made
on a U30 Air; no separate M3 hardware run is claimed. Other modem revisions,
all individual supported NR bands and a switch between two data-capable SIMs
have not been independently measured here.

`tests/test_sim2_locks.py` exercises the transaction, rejection/rollback,
per-SIM state and early recovery against a stateful fake CP. The existing
SIM cold-start, hot-switch, plugin and rpcd suites cover the integration hooks.
