# The WireGuard driver of mu300-vpn (sourced by load_driver): a wg-quick config ($PDIR/wg.conf), run by the kernel's
# own WireGuard, configured with wg (package wireguard-tools). There is no process to keep: the interface is the
# tunnel. The core installs the routing (DRV_ROUTES=core), and the only thing that must be done here for the kill
# switch is to mark WireGuard's own UDP packets with 0x2d0 (wg set ... fwmark), which rule 9000 keeps off the tunnel.
#
# No private or preshared key is ever printed, logged or put on a command line: they stay in wg.conf (0600) and in
# the file wg setconf reads, and every message below names the problem, never the value.
DRV_EXTRA=
DRV_PKG=wireguard-tools
DRV_KEYS=
TUN=wg-mu300

# Overridable for the tests: the directory a loaded WireGuard module shows in sysfs.
WG_SYSMOD=${MU300_WG_SYSMOD:-/sys/module/wireguard}

# ---- reading a wg-quick file ----------------------------------------------------------------------------------
# Keys are case-insensitive, white space around "=" is allowed, "#" starts a comment. The awk programs below are
# the only things that ever look at the keys' values.

# wg_get FILE SECTION KEY: the values of KEY in SECTION (interface or peer), one per line, a comma-separated value
# split into its items. Never called for a key.
wg_get() {
    awk -v want="$2" -v key="$3" '
    function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
    { sub(/\r$/, ""); sub(/#.*/, ""); l = trim($0)
      if (l ~ /^\[.*\]$/) { sec = tolower(trim(substr(l, 2, length(l) - 2))); next }
      eq = index(l, "="); if (!eq) next
      if (sec == want && tolower(trim(substr(l, 1, eq - 1))) == key) {
          n = split(substr(l, eq + 1), a, ",")
          for (i = 1; i <= n; i++) { x = trim(a[i]); if (x != "") print x }
      } }' "$1"
}

# wg_validate FILE: whether FILE is a config this driver can run, with what is wrong said on stdout (the caller sends
# it to stderr) and a warning when the peers do not take the default route. Values are never repeated.
wg_validate() {
    awk '
    function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
    function bad(m) { print "the WireGuard config " m; err = 1 }
    function keyok(v) { return length(v) == 44 && v ~ "^[A-Za-z0-9+/]+=$" }
    # HOST:PORT, or [IPv6]:PORT; a name may not start with "-" (it ends up as an argument)
    function epok(v,    h, p, c, i) {
        if (substr(v, 1, 1) == "[") {
            c = index(v, "]:"); if (!c) return 0
            h = substr(v, 2, c - 2); p = substr(v, c + 2)
            if (h !~ "^[0-9A-Fa-f:.]+$") return 0
        } else {
            c = 0; for (i = length(v); i > 0; i--) if (substr(v, i, 1) == ":") { c = i; break }
            if (!c) return 0
            h = substr(v, 1, c - 1); p = substr(v, c + 1)
            if (h !~ "^[A-Za-z0-9_][A-Za-z0-9._-]*$") return 0
        }
        return p ~ "^[0-9]+$" && p + 0 >= 1 && p + 0 <= 65535
    }
    { sub(/\r$/, ""); sub(/#.*/, ""); l = trim($0)
      if (l == "") next
      if (l ~ /^\[.*\]$/) {
          sec = tolower(trim(substr(l, 2, length(l) - 2)))
          if (sec == "interface") ni++
          else if (sec == "peer") np++
          else { bad("has a section that is neither [Interface] nor [Peer]"); sec = "" }
          next
      }
      eq = index(l, "=")
      if (eq == 0 || sec == "") { bad("has a line that is outside a section or is not KEY = VALUE"); next }
      k = tolower(trim(substr(l, 1, eq - 1))); v = trim(substr(l, eq + 1))
      if (sec == "interface") {
          if (k == "privatekey") { if (keyok(v)) priv = 1; else bad("has a PrivateKey that is not a WireGuard key (44 characters of base64)") }
          else if (k == "mtu") { if (v !~ "^[0-9]+$" || v + 0 < 576 || v + 0 > 9000) bad("has an MTU that is not a number from 576 to 9000") }
          else if (k == "address") {
              n = split(v, a, ",")
              for (i = 1; i <= n; i++) {
                  x = trim(a[i])
                  if (x !~ "^[0-9A-Fa-f:.]+(/[0-9]+)?$") bad("has an Address that is not an IP address with a prefix")
                  else hasaddr = 1
              }
          }
      } else {
          if (k == "publickey") { if (keyok(v)) pk[np] = 1; else bad("has a PublicKey that is not a WireGuard key (44 characters of base64)") }
          else if (k == "presharedkey") { if (!keyok(v)) bad("has a PresharedKey that is not a WireGuard key (44 characters of base64)") }
          else if (k == "endpoint") { if (epok(v)) ep[np] = 1; else bad("has an Endpoint that is not HOST:PORT or [IPv6]:PORT") }
          else if (k == "allowedips") {
              n = split(v, a, ",")
              for (i = 1; i <= n; i++) if (trim(a[i]) == "0.0.0.0/0") def4 = 1
          }
      } }
    END {
        if (!ni) bad("has no [Interface] section")
        else if (ni > 1) bad("has more than one [Interface] section")
        if (ni && !priv) bad("has no PrivateKey in [Interface]")
        if (!np) bad("has no [Peer] section")
        for (i = 1; i <= np; i++) {
            if (!pk[i]) bad("has a [Peer] (number " i ") without a PublicKey")
            if (!ep[i]) bad("has a [Peer] (number " i ") without an Endpoint")
        }
        if (err) exit 1
        if (!def4) print "warning: no peer has 0.0.0.0/0 in AllowedIPs: WireGuard drops whatever is outside AllowedIPs, so other traffic is blocked, not sent around the tunnel"
        if (!hasaddr) print "warning: [Interface] has no Address: the tunnel will have no address of its own"
    }' "$1"
}

# wg_filter MAP FILE: FILE for wg setconf. The wg-quick keys (it does not know them, and PreUp, PostUp and the like
# are commands) are left out, as are ListenPort (a config opens no port on this device) and FwMark (the mark is
# ours, set by wg set after setconf); comments go, and an Endpoint's name is replaced by the address MAP
# (name=address pairs separated by spaces) holds for it; a literal address stays.
wg_filter() {
    awk -v map="$1" '
    function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
    BEGIN { n = split(map, t, " "); for (i = 1; i <= n; i++) { j = index(t[i], "="); m[substr(t[i], 1, j - 1)] = substr(t[i], j + 1) }
            split("address dns mtu table preup postup predown postdown saveconfig listenport fwmark", d, " "); for (i in d) drop[d[i]] = 1 }
    { sub(/\r$/, ""); sub(/#.*/, ""); l = trim($0)
      if (l == "") next
      if (l ~ /^\[.*\]$/) { print l; next }
      eq = index(l, "="); k = trim(substr(l, 1, eq - 1)); v = trim(substr(l, eq + 1))
      if (tolower(k) in drop) next
      if (tolower(k) == "endpoint") {
          if (substr(v, 1, 1) == "[") { print k " = " v; next }
          c = 0; for (i = length(v); i > 0; i--) if (substr(v, i, 1) == ":") { c = i; break }
          h = substr(v, 1, c - 1); if (h in m) v = m[h] substr(v, c)
      }
      print k " = " v
    }' "$2"
}

# wg_endhost ENDPOINT: the host of HOST:PORT or [IPv6]:PORT, without the brackets
wg_endhost() {
    case $1 in
        \[*) _wh=${1%%]*}; _wh=${_wh#\[} ;;
        *) _wh=${1%:*} ;;
    esac
    printf '%s' "$_wh"
}

# ---- the kernel -----------------------------------------------------------------------------------------------
# The mainline kernels have WireGuard; the 5.4 vendor kernel does not. Either the module is there, or our interface
# already exists (the tunnel is running), or the kernel creates one of the type, which is tried with a name of its
# own and removed again.
wg_kernel_ok() {
    ip link show "$TUN" >/dev/null 2>&1 && return 0
    [ -d "$WG_SYSMOD" ] && return 0
    if ip link add "$TUN-t" type wireguard >/dev/null 2>&1; then
        ip link del "$TUN-t" >/dev/null 2>&1
        return 0
    fi
    return 1
}

# ---- the contract ---------------------------------------------------------------------------------------------
drv_engines() { engine_path wg; }
drv_engines_ok() { [ -x "$(engine_path wg)" ] && wg_kernel_ok; }

# The config is complete, and (once wg is installed, so the probe can tell) the kernel has WireGuard.
drv_check() {
    [ -n "${PDIR:-}" ] && [ -r "$PDIR/wg.conf" ] || { echo "the profile has no wg.conf" >&2; return 1; }
    wg_validate "$PDIR/wg.conf" >&2 || return 1
    if [ -x "$(engine_path wg)" ] && ! wg_kernel_ok; then
        echo "this kernel has no WireGuard (the 5.4 vendor kernel does not; the mainline one does)" >&2
        return 1
    fi
    return 0
}

drv_gen() {
    drv_check || exit 1
    _wf=$PDIR/wg.conf
    mkdir -p "$RUN"; chmod 700 "$RUN"
    # Endpoint names: looked up now, before the tunnel exists, and wg setconf gets addresses (it would resolve them
    # itself, on a socket the kill switch does not know). One resolve window around all the lookups.
    _names=
    _eps=$(wg_get "$_wf" peer endpoint)
    while IFS= read -r _e; do
        [ -n "$_e" ] || continue
        _h=$(wg_endhost "$_e")
        if ip4_ok "$_h" || ip6_ok "$_h"; then continue; fi
        case " $_names " in *" $_h "*) ;; *) _names="$_names $_h" ;; esac
    done <<EOF
$_eps
EOF
    _map=
    if [ -n "$_names" ]; then
        resolve_window || { resolve_close; echo "could not open the resolve window" >&2; exit 1; }
        for _h in $_names; do
            _ip=$(vpn_resolve "$_h") || _ip=
            [ -n "$_ip" ] || { resolve_close; echo "cannot resolve the VPN server $_h" >&2; exit 1; }
            _map="$_map $_h=$_ip"
            echo "server $_h -> $_ip"
        done
        resolve_close || { echo "could not put the kill switch back after the lookups" >&2; exit 1; }
    fi
    rm -f "$RUN/wg.conf" "$RUN/wg.addr" "$RUN/wg.mtu" "$RUN/dns" "$RUN/server-ip"
    ( umask 077; wg_filter "$_map" "$_wf" > "$RUN/wg.conf" ) || { rm -f "$RUN/wg.conf"; echo "cannot write $RUN/wg.conf" >&2; exit 1; }
    # the addresses to keep off the tunnel, one per line: whatever the config now says (names are addresses by now)
    : > "$RUN/server-ip"
    _eps=$(wg_get "$RUN/wg.conf" peer endpoint)
    while IFS= read -r _e; do
        [ -n "$_e" ] && printf '%s\n' "$(wg_endhost "$_e")" >> "$RUN/server-ip"
    done <<EOF
$_eps
EOF
    wg_get "$_wf" interface address > "$RUN/wg.addr"
    _m=$(wg_get "$_wf" interface mtu | tail -n1)
    printf '%s\n' "${_m:-1420}" > "$RUN/wg.mtu"
    # the first DNS entry that is an address (the others may be search domains); the core points the device's own
    # lookups at it through the tunnel
    _dns=$(wg_get "$_wf" interface dns)
    while IFS= read -r _d; do
        if ip4_ok "$_d" || ip6_ok "$_d"; then printf '%s\n' "$_d" > "$RUN/dns"; break; fi
    done <<EOF
$_dns
EOF
    echo "wireguard config OK ($RUN/wg.conf)"
}

# The core runs this without set -e: every step whose failure leaves half a tunnel returns 1 itself. wg's own
# message is not shown for setconf, because it quotes the key it dislikes; drv_check has already looked at them.
drv_start() {
    ip link del "$TUN" 2>/dev/null
    ip link add "$TUN" type wireguard || { echo "cannot create $TUN (does the kernel have WireGuard?)" >&2; return 1; }
    wg setconf "$TUN" "$RUN/wg.conf" 2>/dev/null || { echo "wg setconf rejected the config of $TUN" >&2; return 1; }
    wg set "$TUN" fwmark "$MARK" || { echo "cannot mark $TUN's packets" >&2; return 1; }
    while IFS= read -r _a; do
        [ -n "$_a" ] || continue
        # IPv6 through the tunnel only when the setting asks for it (as sing-box's TUN does): an address of its own
        # with no route into it would only make programs prefer a path that does not exist
        case $_a in *:*) [ "${IPV6:-0}" = 1 ] || continue ;; esac
        ip addr add "$_a" dev "$TUN" || { echo "cannot add the address $_a to $TUN" >&2; return 1; }
    done < "$RUN/wg.addr"
    _m=$(cat "$RUN/wg.mtu")
    ip link set "$TUN" mtu "${_m:-1420}" up || { echo "cannot bring $TUN up" >&2; return 1; }
    echo "tunnel up on $TUN"
}
drv_alive() { ip link show "$TUN" >/dev/null 2>&1; }
# the interface goes, and with it the tunnel; the runtime copy of the config (it holds the private key) as well
drv_stop() {
    ip link del "$TUN" 2>/dev/null || true
    rm -f "$RUN/wg.conf"
    return 0
}

# The latest handshake of any peer and the bytes moved, from wg's own counters; wg prints each peer's public key
# first on these lines and that is dropped here.
drv_status() {
    wg show "$TUN" latest-handshakes 2>/dev/null | awk -v now="$(date +%s)" '
        $2 + 0 > t { t = $2 + 0 }
        END { if (NR) { if (t > 0) printf "handshake: %ds ago\n", (now > t ? now - t : 0); else print "handshake: none yet" } }'
    wg show "$TUN" transfer 2>/dev/null | awk '
        { rx += $2; tx += $3 }
        END { if (NR) printf "transfer: %.0f bytes received, %.0f bytes sent\n", rx, tx }'
}

# a wg-quick file, as it is: checked first, so that nothing is written for one that cannot run
drv_import() {
    [ -n "${PDIR:-}" ] && [ -d "$PDIR" ] || { echo "no profile to import into" >&2; return 1; }
    [ -f "$1" ] && [ -r "$1" ] || { echo "a WireGuard profile is a config file (wg-quick format)" >&2; return 1; }
    wg_validate "$1" >&2 || return 1
    ( umask 077; cat "$1" > "$PDIR/wg.conf.new.$$" ) && mv "$PDIR/wg.conf.new.$$" "$PDIR/wg.conf" && return 0
    rm -f "$PDIR/wg.conf.new.$$"; return 1
}
