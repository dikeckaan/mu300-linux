# The mihomo driver of mu300-vpn (sourced by load_driver): a Clash/mihomo YAML ($PDIR/config.yaml, a subscription
# as a panel gives it) run by mihomo (Clash.Meta, the vpn-mihomo extra) with its own TUN. The core installs the
# routing (DRV_ROUTES=core): mihomo's auto-route is off, and the kill switch lets its connections out because every
# socket it opens carries our mark (routing-mark: 720). It resolves the servers' names itself, over those marked
# sockets, through BOOTSTRAP_DNS (proxy-server-nameserver), so there is no resolve window and no server-ip to keep off
# the tunnel.
#
# The YAML is hostile input (the spec's Security section) and mihomo runs as root, so mihomo never reads the
# profile's file: the driver reads it once, line by line (awk; there is no YAML parser on the device, and the rules
# below are about lines, see mihomo_read), keeps the top-level blocks of an allowlist, removes the rest (Clash files
# carry many harmless keys, so an unknown key is dropped, not refused), takes interface-name and routing-mark out of
# every proxy and group, appends what is ours last (the mark, allow-lan, bind-address, tun, dns; no controller or
# API of any kind: the TUN is the only thing that listens, and nothing can ask for more), checks the written file
# once more (mihomo_written_ok), and only then lets mihomo check (-t) and run it. The
# profile keeps the file as imported (profile export gives it back). A refusal names a key of our own lists or a
# rule, never a value or a line of the file, and mihomo's own messages are not repeated (its YAML errors quote values).
DRV_EXTRA=vpn-mihomo
DRV_PKG=
DRV_KEYS=MIHOMO_STACK
TUN=mh-mu300
MHPID=; DRV_GONE=

# mihomo reads SAFE_PATHS (directories a provider's path or external-ui may name outside its home) and
# SKIP_SAFE_PATH_CHECK from its environment: neither is ever passed on, so everything it reads or writes stays in
# its home directory
unset SAFE_PATHS SKIP_SAFE_PATH_CHECK

# the top-level keys of the file that survive, as the spec's Security section lists them; every other one is removed
MIHOMO_KEYS='proxies proxy-groups proxy-providers rules rule-providers sub-rules hosts mode log-level ipv6 geodata-mode geodata-loader geox-url profile sniffer'
# the top-level keys this driver writes, and the only ones besides the kept list that the written file may have:
# external-controller (and -tls, -unix, -pipe, -cors), external-ui*, external-doh-server, secret and tls are not
# among them, so no control API of the file's or of a setting's ever reaches mihomo
MIHOMO_OURS='routing-mark allow-lan bind-address tun dns'

# The binary: the MIHOMO setting when there is one, else the extra's (or /opt/mu300/bin, or PATH).
mihomo_bin() { if [ -n "${_mihomo:-}" ]; then printf '%s\n' "$_mihomo"; else engine_path mihomo vpn-mihomo; fi; }
# mihomo's home: its cache (cache.db), the geodata and providers it downloads; under the store, so they survive a
# reboot, and only root's
MH_HOME=$VPN_DIR/cache/mihomo
mihomo_home() {
    { mkdir -p "$MH_HOME" && chmod 700 "$MH_HOME"; } || { echo "cannot create $MH_HOME" >&2; return 1; }
}

# ---- reading a Clash/mihomo YAML -------------------------------------------------------------------------------
# mihomo_read MODE FILE: one reader, two modes, so that what is checked and what is written cannot disagree:
#   check  what is wrong (stdout, exit 1), and a note naming the top-level keys that are not used
#   gen    the kept blocks, reduced, as they go into the file mihomo gets (nothing for a refused file)
# The rules are about lines, since awk reads lines: a top-level entry is a line at column 0 "KEY:" (KEY of
# [A-Za-z0-9_-], then optional blanks, the colon, then a blank or the end), and its block runs to the next such line;
# blank lines and "#" lines belong to the block they follow (a top-level value's text is always indented, and a flow
# collection continued at column 0 is refused below, so YAML reads the same top-level keys as these rules do). A
# dropped block that defines an anchor is kept inert under a name of ours (flush_dropped). A kept block is copied as
# it is, except that
# - a line "^[ \t-]*interface-name:" or "routing-mark:" (any case) goes, with the lines indented deeper than the key
#   (a multi-line value); a "-" before it stays as a line of its own, so the list item keeps its place;
# - in a flow mapping or sequence ({...}, [...]) the "KEY: value" segment of either key goes with one comma: the
#   value is a quoted scalar, or everything up to the next "," or closing bracket, brackets nested.
# After that, the text interface-name or routing-mark anywhere outside a "#" line - a quoted key, an anchor, a
# trailing comment, a form these rules did not undo - refuses the file, naming the key. Refused as well, naming the
# rule: a second document ("---" after the first line, "..."), a "%" directive, a TAB at the start of a line (YAML
# does not indent with tabs; mihomo's reader refuses it too), a line over 4096 bytes, a line break inside a line
# (a lone CR, NEL, LS or PS: yaml.v3 ends a line there, awk does not, so one line here would be several to mihomo),
# an explicit key ("? ", one way a key can span lines), a tag ("!": !!binary spells a key without its text), a
# line ending in a backslash and a quoted scalar not closed on its line (the other ways a key can span lines), a
# hex escape (\x, \u, \U: the one way a key can be spelled without its text on one line), a column-0 line that is
# not "KEY:" (a quoted key, a list item, a merge key, an anchor, a flow collection continued at column 0), a kept
# key given twice (mihomo's reader refuses it anyway), a top-level key that is a kept name or one of ours in another
# spelling (another case, _ for -: mihomo's reader would not read it, and the JSON drivers refuse a misspelled
# shape key the same way; the refusal names the name it collides with, not the file's key), a key of the driver's
# own reserved names (mu300-anchor-N) and a file with neither proxies nor proxy-providers. A first line "---", a
# BOM and CRLF line ends are taken. The size cap comes first (before the control-byte count, which is the shell's,
# and before awk sees a line), as in the JSON drivers.
mihomo_read() {
    json_size_ok "$2" || { [ "$1" != check ] || echo "the mihomo config is larger than 1 MiB"; return 1; }
    # what is left after removing TAB, LF, CR, printable ASCII and the bytes from 0x80 is a control character or NUL
    _cc=$(LC_ALL=C tr -d '\011\012\015\040-\176\200-\377' < "$2" | wc -c | tr -d ' \t') || return 1
    if [ "$((_cc))" -ne 0 ]; then
        [ "$1" != check ] || echo "the mihomo config has a control character (NUL, escape, form feed ...), which it may not contain"
        return 1
    fi
    LC_ALL=C awk -v mode="$1" -v keep="$MIHOMO_KEYS" -v ours="$MIHOMO_OURS" '
    function bad(m) { if (mode == "check") print "the mihomo config " m; err = 1 }
    function atline(m) { bad("(line " NR ") " m) }
    function emit(s) { out[++no] = s }
    function indent(s,    i) { i = 0; while (substr(s, i + 1, 1) == " ") i++; return i }
    # openq(l): whether L ends inside a quoted scalar. A quote opens one where a node can start (the line start,
    # or after a blank, "[", "{" or ","); inside double quotes a backslash escapes the next character, inside
    # single quotes a doubled quote is one; a blank "#" outside quotes starts a comment, which closes nothing.
    # A quote elsewhere (a"b) is text, as YAML reads it.
    function openq(l,    i, n, c, p, q) {
        q = ""; n = length(l)
        for (i = 1; i <= n; i++) {
            c = substr(l, i, 1)
            if (q == "\"") { if (c == "\\") i++; else if (c == "\"") q = "" }
            else if (q == "\047") { if (c == "\047") { if (substr(l, i + 1, 1) == "\047") i++; else q = "" } }
            else {
                p = (i > 1) ? substr(l, i - 1, 1) : " "
                if (p ~ /[[{, \t]/) { if (c == "\"" || c == "\047") q = c; else if (c == "#") break }
            }
        }
        return q != ""
    }
    # flowkey(lo): the position in LO (the line, lowercased) of the first "KEY:" of the two keys that sits in a
    # flow collection - after "{", "[" or "," and blanks, followed by a blank, ",", a closing bracket or the end -
    # with fk the key; 0 when there is none
    function flowkey(lo,    n, q, s, e, c, a) {
        for (n = 1; n <= 2; n++) {
            q = 1
            while ((s = index(substr(lo, q), dk[n] ":")) > 0) {
                s += q - 1
                e = s - 1; while (e > 0 && substr(lo, e, 1) == " ") e--
                c = (e > 0) ? substr(lo, e, 1) : ""
                a = substr(lo, s + length(dk[n]) + 1, 1)
                if ((c == "{" || c == "[" || c == ",") && (a == " " || a == "," || a == "}" || a == "]" || a == "")) { fk = dk[n]; return s }
                q = s + 1
            }
        }
        return 0
    }
    # strip_flow(l): every "KEY: value" of the two keys in a flow collection of L removed, each with one comma
    function strip_flow(l,    p, v, e, c, d, ch, pre, rest) {
        while ((p = flowkey(tolower(l))) > 0) {
            v = p + length(fk) + 1
            while (substr(l, v, 1) == " ") v++
            c = substr(l, v, 1)
            if (c == "\047") {
                e = v + 1
                while (1) {
                    ch = substr(l, e, 1)
                    if (ch == "") { e = length(l); break }
                    if (ch == "\047") { if (substr(l, e + 1, 1) == "\047") { e += 2; continue } break }
                    e++
                }
            } else if (c == "\"") {
                e = v + 1
                while (1) {
                    ch = substr(l, e, 1)
                    if (ch == "") { e = length(l); break }
                    if (ch == "\\") { e += 2; continue }
                    if (ch == "\"") break
                    e++
                }
            } else {
                d = 0; e = v - 1
                while (1) {
                    ch = substr(l, e + 1, 1)
                    if (ch == "") break
                    if (ch == "[" || ch == "{") d++
                    else if (ch == "]" || ch == "}") { if (d == 0) break; d-- }
                    else if (ch == "," && d == 0) break
                    e++
                }
            }
            pre = substr(l, 1, p - 1); rest = substr(l, e + 1)
            if (rest ~ /^ *,/) sub(/^ *, */, "", rest)
            else if (pre ~ /, *$/) sub(/, *$/, "", pre)
            l = pre rest
        }
        return l
    }
    # inner(l): a line of a kept block, below its key line: a block-style line of either key goes (and dropto marks
    # the column its continuation lines are deeper than), anything else is emitted without its flow segments
    function inner(l,    lo, i, pre) {
        lo = tolower(l)
        if (match(lo, "^[ \t-]*(interface-name|routing-mark)[ \t]*:([ \t]|$)")) {
            i = 1; while (substr(l, i, 1) ~ /[ \t-]/) i++
            dropto = i - 1
            pre = substr(l, 1, i - 1)
            if (index(pre, "-")) { sub(/[ \t]+$/, "", pre); emit(pre) }
            return
        }
        emit(strip_flow(l))
    }
    # body(l): a line below a key line, kept unless it continues a removed key (see inner)
    function body(l) {
        if (dropto >= 0) {
            if (l ~ /^[ \t]*$/) { emit(l); return }
            if (indent(l) > dropto) return
            dropto = -1
        }
        inner(l)
    }
    # flush_dropped(): the block of a dropped key has ended. It goes - unless it defines an anchor (&name) that a
    # kept block may merge or alias (subscription templates and the example in the mihomo wiki put the defaults of
    # their providers and groups under keys of their own, "p: &p {type: http, ...}", and say "<<: *p" below): then it is
    # kept, inert, under a name of ours that mihomo does not read (it ignores a top-level key it does not know),
    # through the same removals and the same text check as a kept block, so that nothing it anchors can bring the
    # two keys in, and the file still parses.
    function flush_dropped(    i, has, l) {
        if (!dropping) return
        dropping = 0
        has = 0
        for (i = 1; i <= npend; i++) if (pend[i] ~ /(^|[[{, \t])&[A-Za-z0-9_-]+([] \t,}]|$)/) { has = 1; break }
        if (!has) return
        nanch++
        anchored = anchored " " substr(dkey, 1, 40)
        l = pend[1]; sub(/^[A-Za-z0-9_-]+/, "mu300-anchor-" nanch, l)
        emit(strip_flow(l))
        dropto = -1
        for (i = 2; i <= npend; i++) body(pend[i])
    }
    # fold(k): a key as a case-insensitive reader with - for _ would see it; foldk maps the folds of the kept names
    # and ours back to the name, so a key spelled otherwise is caught by the name it collides with
    function fold(k) { k = tolower(k); gsub(/_/, "-", k); return k }
    BEGIN {
        n = split(keep, a, " "); for (i = 1; i <= n; i++) { keepk[a[i]] = 1; foldk[fold(a[i])] = a[i] }
        n = split(ours, a, " "); for (i = 1; i <= n; i++) foldk[fold(a[i])] = a[i]
        dk[1] = "interface-name"; dk[2] = "routing-mark"
        dropto = -1; keeping = 0; dropping = 0; ngone = 0; nanch = 0
    }
    { if (NR == 1 && substr($0, 1, 3) == "\357\273\277") $0 = substr($0, 4)
      sub(/\r$/, "") }
    # yaml.v3 ends a line at a lone CR, NEL (U+0085), LS (U+2028) and PS (U+2029) as well as at LF: a line holding
    # one is one line to these rules and several to mihomo, so it is refused (as openvpn.sh refuses a lone CR)
    index($0, "\r") || index($0, "\302\205") || index($0, "\342\200\250") || index($0, "\342\200\251") {
        atline("has a line break inside a line (a lone CR, NEL, LS or PS), which YAML reads as a line end"); next }
    length($0) > 4096 { atline("has a line over 4096 bytes"); next }
    /^\t/ { if ($0 ~ /[^ \t]/) { atline("has a TAB at the start of a line (YAML does not indent with tabs)"); next } }
    /^%/ { atline("has a YAML directive (%)"); next }
    /^---([ \t]|$)/ { if (NR == 1 && $0 ~ /^---[ \t]*$/) next; atline("has a second YAML document (---)"); next }
    /^\.\.\.[ \t]*$/ { atline("has a document end marker (...)"); next }
    /(^|[[{, \t])\?([ \t]|$)/ { atline("has an explicit key (?), which this driver does not read"); next }
    /\\[xuU][0-9A-Fa-f]/ { atline("has a hex escape (\\x, \\u, \\U), which could spell a key"); next }
    # a tag (!!binary spells a key without its text), a line continued on the next by a backslash and a quoted
    # scalar left open on its line (the two ways a quoted key can span lines) are refused; not on a comment line,
    # which is only a comment. A "!" or a quote in the middle of a value belongs to the value and stays.
    !/^[ \t]*#/ {
        if ($0 ~ /(^|[[{, \t])!/) { atline("has a tag (!), which this driver does not read"); next }
        if ($0 ~ /\\$/) { atline("has a line ending in a backslash (a scalar continued on the next line)"); next }
        if (openq($0)) { atline("has a quoted scalar that is not closed on its line"); next }
    }
    # indented, blank and comment lines: the current block
    /^[ \t]/ || /^#/ || /^$/ {
        if (keeping) body($0)
        else if (dropping) pend[++npend] = $0
        next
    }
    # a top-level line
    {
        flush_dropped()
        dropto = -1
        if (!match($0, /^[A-Za-z0-9_-]+[ \t]*:([ \t]|$)/)) {
            atline("has a top-level line that is not KEY: (a quoted key, a list item, a merge key, an anchor, or a flow collection continued at column 0)")
            keeping = 0; next
        }
        k = $0; sub(/[ \t]*:.*/, "", k)
        f = fold(k)
        if (f ~ /^mu300-anchor-[0-9]+$/) { atline("has the top-level key mu300-anchor-N, a name reserved for this driver"); keeping = 0; next }
        if ((f in foldk) && k != foldk[f]) {
            atline("has a top-level key spelled differently from " foldk[f] " (another case, or _ for -)"); keeping = 0; next
        }
        if (k in keepk) {
            if (k in seen) bad("has the top-level key " k " twice")
            seen[k] = 1; keeping = 1
            emit(strip_flow($0))
        } else {
            keeping = 0
            dropping = 1; npend = 0; pend[++npend] = $0; dkey = k
            if (!(k in gone)) { gone[k] = 1; if (++ngone <= 40) gonelist = gonelist " " substr(k, 1, 40) }
        }
        next
    }
    END {
        flush_dropped()
        if (!("proxies" in seen) && !("proxy-providers" in seen)) bad("has no proxies or proxy-providers at the top level")
        # the two keys in any form the rules above did not take out
        for (i = 1; i <= no; i++) {
            lo = tolower(out[i])
            if (lo ~ /^[ \t]*#/) continue
            for (n = 1; n <= 2; n++) if (index(lo, dk[n]) && !(dk[n] in said)) {
                said[dk[n]] = 1
                bad("has " dk[n] " in a form this driver cannot remove (quoted, an anchor, a comment after a value ...) and is refused: take it out")
            }
        }
        if (err) exit 1
        if (mode == "gen") { for (i = 1; i <= no; i++) print out[i]; exit 0 }
        if (gonelist != "") print "note: top-level keys of the file that are not used (this driver writes its own tun and dns; nothing listens but the TUN):" gonelist (ngone > 40 ? " ..." : "")
        if (anchored != "") print "note: kept for the anchors (&name) they define, under names mihomo does not read:" anchored
    }' "$2"
}

# mihomo_ours STACK: the top-level keys this driver writes, after the file's own (the last wins in no reader; they
# are the only ones, see mihomo_written_ok). The TUN is the only inbound (no port of any kind, no controller or
# API, and allow-lan off with the bind address on loopback should one ever be written); auto-route and
# auto-detect-interface are off (the core routes, the kernel picks the uplink); DNS: the server names through
# BOOTSTRAP_DNS over mihomo's own marked sockets, everything else through REMOTE_DNS behind the rules.
mihomo_ours() {
    cat <<EOF
routing-mark: $((MARK))
allow-lan: false
bind-address: '127.0.0.1'
tun:
  enable: true
  device: $TUN
  stack: $1
  auto-route: false
  auto-redirect: false
  auto-detect-interface: false
  dns-hijack: []
  mtu: 1400
  inet4-address: [198.18.8.1/30]
dns:
  enable: true
  ipv6: false
  respect-rules: true
  default-nameserver: ['$BOOTSTRAP_DNS']
  proxy-server-nameserver: ['$BOOTSTRAP_DNS']
  nameserver: ['$REMOTE_DNS']
EOF
}

# mihomo_written_ok FILE: the guard behind the rebuild, on the file mihomo gets: no line break but LF (yaml.v3's
# line is the guard's line), every column-0 line a "KEY:" line whose key is one of the kept list, ours or an anchor
# holder of ours (mu300-anchor-N, see flush_dropped) - so no external-*, secret, tls, port or listener in any
# spelling - tun and dns exactly once, routing-mark 720 and allow-lan false (once each), bind-address once. A later
# change to the reduction that let something through fails closed here instead of reaching mihomo.
mihomo_written_ok() {
    LC_ALL=C awk -v keep="$MIHOMO_KEYS" -v ours="$MIHOMO_OURS" -v mark="$((MARK))" '
    BEGIN { n = split(keep " " ours, a, " "); for (i = 1; i <= n; i++) ok[a[i]] = 1 }
    # the line model is that of yaml.v3: a CR, NEL, LS or PS anywhere is a line end to mihomo, so a line holding one
    # fails the file (the reduction writes none: a CRLF end is stripped, a break inside a line refused)
    index($0, "\r") || index($0, "\302\205") || index($0, "\342\200\250") || index($0, "\342\200\251") { bad = 1; exit }
    /^[ \t#]/ || /^$/ { next }
    { if (!match($0, /^[A-Za-z0-9_-]+[ \t]*:([ \t]|$)/)) { bad = 1; exit }
      k = $0; sub(/[ \t]*:.*/, "", k)
      if (!(k in ok) && k !~ /^mu300-anchor-[0-9]+$/) { bad = 1; exit }
      c[k]++
      if (k == "allow-lan" && $0 != "allow-lan: false") bad = 1
      if (k == "routing-mark" && $0 != "routing-mark: " mark) bad = 1
      if (k == "bind-address" && $0 != "bind-address: \047127.0.0.1\047") bad = 1
      if (bad) exit }
    END { if (bad) exit 1
          if (c["tun"] != 1 || c["dns"] != 1 || c["routing-mark"] != 1 || c["allow-lan"] != 1 || c["bind-address"] != 1) exit 1 }' "$1"
}

# mihomo_rebuild SRC OUT: SRC reduced (mihomo_read) with ours appended, into OUT (0600), or a refusal on stderr and
# no OUT. The stack is the profile's MIHOMO_STACK (gvisor unless it says system or mixed); the two resolvers are
# checked once more here: where the store is not used they come from vpn.conf, which nothing validated.
mihomo_rebuild() {
    _src=$1; _out=$2
    rm -f "$_out"
    mihomo_read check "$_src" >&2 || return 1
    _stack=; kv_var _stack "$PDIR/meta" MIHOMO_STACK
    case $_stack in gvisor|system|mixed) ;; *) _stack=gvisor ;; esac
    { ip4_ok "$REMOTE_DNS" || ip6_ok "$REMOTE_DNS"; } && { ip4_ok "$BOOTSTRAP_DNS" || ip6_ok "$BOOTSTRAP_DNS"; } ||
        { echo "REMOTE_DNS and BOOTSTRAP_DNS must be IP addresses" >&2; return 1; }
    if ! ( umask 077; { mihomo_read gen "$_src" && mihomo_ours "$_stack"; } > "$_out.r" ); then
        rm -f "$_out.r"; echo "cannot write $_out" >&2; return 1
    fi
    if ! mihomo_written_ok "$_out.r"; then
        rm -f "$_out.r"; echo "the rebuilt mihomo config is not what this driver writes: refused" >&2; return 1
    fi
    mv "$_out.r" "$_out" && chmod 600 "$_out" && return 0
    rm -f "$_out.r" "$_out"; echo "cannot write $_out" >&2; return 1
}

# ---- the contract ---------------------------------------------------------------------------------------------
drv_engines() { mihomo_bin; }
drv_engines_ok() { [ -x "$(mihomo_bin)" ]; }

# the rebuild runs, into a file of the profile's own (0700) directory that is removed again; mihomo itself checks
# the rebuilt file in drv_gen
drv_check() {
    [ -n "${PDIR:-}" ] && [ -r "$PDIR/config.yaml" ] || { echo "the profile has no config.yaml" >&2; return 1; }
    _chk=$PDIR/.check.$$
    mihomo_rebuild "$PDIR/config.yaml" "$_chk" || { rm -f "$_chk"; return 1; }
    rm -f "$_chk"; return 0
}

drv_gen() {
    [ -n "${PDIR:-}" ] && [ -r "$PDIR/config.yaml" ] || { echo "the profile has no config.yaml" >&2; exit 1; }
    mkdir -p "$RUN"; chmod 700 "$RUN"
    rm -f "$RUN/mihomo.yaml" "$RUN/server-ip"
    mihomo_rebuild "$PDIR/config.yaml" "$RUN/mihomo.yaml" || exit 1
    # no address to keep off the tunnel: mihomo marks its own sockets, and looks the servers up over them
    : > "$RUN/server-ip"
    mihomo_home || exit 1
    # mihomo checks the rebuilt file, the one it will run; the profile's own file is never given to it. Its output
    # is not shown (its YAML errors quote values); the file is root's, 0600, so the command can be run by hand.
    "$(mihomo_bin)" -t -d "$MH_HOME" -f "$RUN/mihomo.yaml" >/dev/null 2>&1 ||
        { echo "mihomo rejects the rebuilt config: $(mihomo_bin) -t -d $MH_HOME -f $RUN/mihomo.yaml says why" >&2; exit 1; }
    echo "mihomo config OK ($RUN/mihomo.yaml)"
}

# The core runs this without set -e: every step whose failure leaves half a tunnel returns 1 itself, and mihomo is
# stopped again when its TUN does not come up. Its output goes through, as the service log.
drv_start() {
    MHPID=; DRV_PIDS=
    mihomo_home || return 1
    "$(mihomo_bin)" -d "$MH_HOME" -f "$RUN/mihomo.yaml" < /dev/null &
    MHPID=$!; DRV_PIDS=$MHPID
    _n=0
    until ip link show "$TUN" >/dev/null 2>&1; do
        if ! kill -0 "$MHPID" 2>/dev/null; then
            wait "$MHPID" 2>/dev/null || true
            echo "mihomo exited during start" >&2
            MHPID=; DRV_PIDS=
            return 1
        fi
        _n=$((_n + 1))
        if [ "$_n" -ge 20 ]; then
            echo "mihomo did not bring $TUN up within 20 s" >&2
            drv_stop
            return 1
        fi
        sleep 1
    done
    ip link set "$TUN" up || { echo "cannot bring $TUN up" >&2; drv_stop; return 1; }
    echo "tunnel up on $TUN (mihomo $MHPID)"
}
drv_alive() {
    [ -n "$MHPID" ] && kill -0 "$MHPID" 2>/dev/null || { DRV_GONE=mihomo; return 1; }
    ip link show "$TUN" >/dev/null 2>&1 || { DRV_GONE=mihomo; return 1; }
}
# TERM lets mihomo close its TUN; KILL after 5 s for one that does not. The runtime copy of the config holds the
# credentials, so it goes too.
drv_stop() {
    if [ -n "$MHPID" ]; then
        kill "$MHPID" 2>/dev/null || true
        _n=0
        while kill -0 "$MHPID" 2>/dev/null && [ "$_n" -lt 5 ]; do sleep 1; _n=$((_n + 1)); done
        if kill -0 "$MHPID" 2>/dev/null; then kill -9 "$MHPID" 2>/dev/null || true; fi
        wait "$MHPID" 2>/dev/null || true
    fi
    MHPID=; DRV_PIDS=
    rm -f "$RUN/mihomo.yaml"
    return 0
}

# the mode and the number of proxies of the running config, from the rebuilt file: nothing of a proxy itself
drv_status() {
    [ -r "$RUN/mihomo.yaml" ] || return 0
    LC_ALL=C awk '
        /^mode:[ \t]*[a-z]+[ \t]*$/ { m = $2 }
        /^proxies:/ { inp = 1; next }
        /^[^ \t#]/ { inp = 0 }
        inp && /^[ \t]*- / { n++ }
        END { if (m != "") print "mode: " m; if (n) print "proxies: " n }' "$RUN/mihomo.yaml"
}

# a Clash/mihomo YAML, as it is: read once first, so that nothing is written for one that cannot run (profile import
# runs drv_check on it after this, too)
drv_import() {
    [ -n "${PDIR:-}" ] && [ -d "$PDIR" ] || { echo "no profile to import into" >&2; return 1; }
    [ -f "$1" ] && [ -r "$1" ] || { echo "a mihomo profile is a Clash/mihomo YAML config file" >&2; return 1; }
    json_size_ok "$1" || { echo "the mihomo config is larger than 1 MiB" >&2; return 1; }
    if is_json "$1"; then echo "not a mihomo config: a JSON file (an Xray or sing-box config?)" >&2; return 1; fi
    mihomo_read check "$1" >&2 || return 1
    ( umask 077; cat "$1" > "$PDIR/config.yaml.new.$$" ) && mv "$PDIR/config.yaml.new.$$" "$PDIR/config.yaml" && return 0
    rm -f "$PDIR/config.yaml.new.$$"; return 1
}

# profile set ID MIHOMO_STACK gvisor|system|mixed: the TUN stack (gvisor by default: the system stack does not work
# on the 5.4 vendor kernel, see gen_singbox); empty puts the default back
drv_set() {
    case $1 in MIHOMO_STACK) ;; *) return 2 ;; esac
    case $2 in ''|gvisor|system|mixed) ;; *) echo "MIHOMO_STACK is gvisor, system or mixed" >&2; return 2 ;; esac
    drv_set_default "$1" "$2"
}
