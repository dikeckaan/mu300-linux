# luci-app-mu300

A self-contained LuCI application for Unisoc cellular devices. It provides the
dashboard, live radio readings, persistent network/band/cell/EN-DC locks, a
guarded AT terminal and an SMS UI.
The Device Management page controls USB role and gadget network policy, and
lists host-side USB network adapters for optional attachment to the LAN bridge.

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

## USB device management

USB role defaults to device at every boot. The page can switch it immediately;
checking host auto-apply asks the package's boot worker to reapply host mode
at every boot. On the battery-less F50, the plugin writes the requested role
to sysfs directly: USB management disappears and an attached adapter may need
an externally powered hub. U30 Air uses `mu300-usb` and its charger boost/VBUS
checks. Other hardware can use the sysfs fallback or configure
`unisoc_modem.usb.role_command` with a platform-specific executable that
accepts `host` or `device`. The plugin must not bypass a known platform's
power-safety checks.

NCM/ECM/RNDIS selection is stored in `/etc/unisoc-modem/usb-boot.conf` only
when "Enable selected protocol" is checked. The optional TF-platform hook in `boot/init`
reads that file from the mounted TF root before gadget enumeration; other OpenWrt builds can
implement the same two-line `mode=...`/`scope=...` contract at their own early
gadget setup point. The plugin itself owns the policy and UI, not the kernel
or gadget. `once` is consumed after a successful boot only if initramfs
recorded that it applied the selection; subsequent boots use the platform's
default NCM. Selecting persistent host mode automatically disables USB
network auto-apply. While the current role is host, network-mode controls are
disabled. The backend validates the same rules regardless of UI state.
The TF boot implementation exposes RNDIS as a single USB configuration with
the ACM console; Windows does not bind a composite RNDIS adapter when the
device offers both RNDIS and NCM configurations. On LAN handoff, the temporary
initramfs IPv4 address is removed from `rndis0` so only `br-lan` owns it.

USB adapter discovery uses the USB sysfs parent of each network device. On
refresh it attempts to bring discovered devices up. “Add to LAN” adds only a
verified USB adapter to the configured LAN bridge device's UCI port list,
commits `network`, and reloads networking. The selected port is reattached
on USB netdev hotplug and LAN ifup, without a polling daemon or another
network reload. The action is idempotent and only available in host mode.

## Build

Copy this directory alone to `package/luci-app-mu300` in any compatible OpenWrt
buildroot, select `LuCI -> Applications -> luci-app-mu300`, and build normally.
No file outside this directory is copied into the package; platform-specific AT
and SMS implementations are discovered only through the documented adapters at
runtime.

For a source-tree hot install (without an `.ipk`/`.apk`), copy `root/` to `/`,
`htdocs/` to `/www/`, and `lmo/` to `/usr/lib/lua/luci/i18n/`; then
make `/etc/init.d/unisoc-modem-ui`, `/usr/libexec/rpcd/mu300dash` and the
`/usr/libexec/unisoc-modem/*` adapters executable; then
enable/start `unisoc-modem-ui` and
restart `rpcd`. Copying only `root/` leaves the LuCI menu visible but makes
`/luci-static/resources/view/mu300/*.js` return HTTP 404. Normal package
installation performs both copies through this package's `install` recipe.
