# luci-app-mu300

A self-contained LuCI application for Unisoc cellular devices. It provides the
dashboard, live radio readings, persistent network/band/cell/EN-DC locks, a
guarded AT terminal and an SMS UI.

The dashboard follows LuCI's selected language (English, Turkish, or Simplified
Chinese) without an extra language package. Its colors follow Aurora's existing
tokens when present, or the official Bootstrap theme's light/dark tokens.
The package also ships native LuCI menu catalogs (`lmo/`), so its top-level
menu and submenu remain translated on unrelated LuCI pages where the dashboard
JavaScript is not loaded. The corresponding editable source is in `po/`.

The package does not start or own the modem. Platform-specific access is behind
small command adapters, so the LuCI and RPC code does not need to change for a
different Unisoc OpenWrt firmware.

## AT adapters

Configure `/etc/config/unisoc_modem`:

- `at_backend=mu300` uses an existing `mu300-at` daemon and keeps its locking.
- `at_backend=atinout` uses the configured `at_port` and a package-local lock.
  Use this only when no other process reads that tty.
- `at_backend=custom` runs the executable in `at_command`. It receives
  `TIMEOUT` and the complete `AT COMMAND` as its two arguments. A platform that
  already has a RIL/AT daemon should expose it through this adapter so every
  client shares that daemon's lock.
- `at_backend=auto` prefers `mu300-at`, then `atinout`, then the custom command.

The SMS page uses `sms_command`, whose CLI contract is the existing
`mu300-sms` interface: `list`, `show`, `send`, `delete` and `sync`. This keeps
SIM storage details out of LuCI and lets each firmware supply its own adapter.

Network interface and state paths are also configured in the same UCI section;
none of the web code requires `sipa_eth0`, `wan`, `br-lan` or `/opt/mu300` from
the host firmware.

## Persistent locks

The package owns `/etc/init.d/unisoc-modem-ui`. It starts a non-blocking procd
worker at boot only when saved locks exist and automatic application is enabled.
The worker probes the selected AT adapter every two seconds and replays the
settings immediately when it becomes ready. It never delays OpenWrt startup and
stops after `replay_timeout` seconds instead of polling forever. A platform
with a pre-radio hook may create `/run/unisoc-modem-early-hook-pending` before
AT startup. While that file exists, this worker sends no AT probes, preserving
the platform's first-command handshake. The platform removes it after its
radio-on attempt; if early replay did not create the completion marker, the
worker falls back to the normal late replay.

The portable worker activates saved mode/band/cell settings with one bounded
SFUN restart and raises the configured data interface afterwards. An EN-DC-only
replay needs no stack restart and is applied immediately. A platform with a
deliberate pre-radio integration may call
`/usr/libexec/unisoc-modem/lock replay early` from that hook after the AT
handshake and while the radio is off. Early replay reads back the saved fields
before writing its completion marker. A failed readback leaves late replay
available; a successful marker prevents duplicate application. `early` is
deliberately not a user-selectable setting because it is only safe at that exact
point in the platform radio sequence.

## Build

Copy this directory alone to `package/luci-app-mu300` in any compatible OpenWrt
buildroot, select `LuCI -> Applications -> luci-app-mu300`, and build normally.
No file outside this directory is copied into the package; platform-specific AT
and SMS implementations are discovered only through the documented adapters at
runtime.

For a source-tree hot install (without an `.ipk`/`.apk`), copy `root/` to `/`,
`htdocs/` to `/www/`, and `lmo/` to `/usr/lib/lua/luci/i18n/`; then
enable/start `unisoc-modem-ui` and
restart `rpcd`. Copying only `root/` leaves the LuCI menu visible but makes
`/luci-static/resources/view/mu300/*.js` return HTTP 404. Normal package
installation performs both copies through this package's `install` recipe.
