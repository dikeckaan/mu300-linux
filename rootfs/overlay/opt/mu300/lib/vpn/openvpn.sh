# The OpenVPN driver of mu300-vpn (sourced by load_driver): an .ovpn file ($PDIR/client.ovpn) run by the openvpn
# package, with our own routing, our own up script and its sockets marked 0x2d0 so that rule 9000 keeps them off the
# tunnel and the kill switch lets them out. The core installs the routing (DRV_ROUTES=core); openvpn only makes the
# tun device and brings the session up (--route-noexec).
#
# An .ovpn is a program for openvpn, which runs as root, so openvpn never reads the user's file. The file is parsed
# here with openvpn's own lexical rules, held to an allowlist of directives (each argument checked), and openvpn reads
# only the config this driver writes from what was accepted: normalised directive lines, the resolved remotes and the
# inline key blocks. Anything the allowlist does not name is refused, never silently passed on, because every openvpn
# release adds directives faster than a denylist would follow. Keys, certificates and passwords are never printed,
# logged or put on a command line: they stay in client.ovpn and auth.txt (0600) and in the runtime copies (0600), and
# every message names the line and the directive, never an argument.
DRV_EXTRA=
# the package is openvpn-openssl on OpenWrt (apk), openvpn elsewhere
DRV_PKG=openvpn
[ ! -e "${MU300_OPENWRT_RELEASE:-/etc/openwrt_release}" ] || DRV_PKG=openvpn-openssl
DRV_KEYS='OVPN_USER OVPN_PASS'
TUN=tun-mu300

OVPN_PID=

# The binary: the OPENVPN setting when there is one, else the package's.
ovpn_bin() { if [ -n "${_openvpn:-}" ]; then printf '%s\n' "$_openvpn"; else engine_path openvpn; fi; }

# ---- reading an .ovpn -----------------------------------------------------------------------------------------
# ovpn_read MODE MAP HASAUTH FILE. One parser does all the reading, in four modes, so that what is checked, what is
# looked up and what is written can never disagree:
#   check    what is wrong (stdout, exit 1), notes and warnings
#   hosts    the remote names that are not addresses, one per line
#   remotes  every remote host, one per line (run on the config we wrote, which must parse too)
#   gen      the config that runs: the accepted directives as we write them, names replaced by the addresses in MAP
#            (name=address pairs, space separated), and the inline blocks
# Every mode refuses the same files; only check says why, and hosts and gen print nothing for a refused file.
ovpn_read() {
    # The byte-level rules come first, before awk sees the file: awk implementations differ on NUL, and openvpn
    # counts \v and \f as white space where our parser would not.
    _sz=$(wc -c < "$4" | tr -d ' \t') || return 1
    if [ "$((_sz))" -gt 262144 ]; then
        [ "$1" != check ] || echo "the OpenVPN config is larger than 256 KiB"
        return 1
    fi
    # what is left after removing TAB, LF, CR, printable ASCII and the bytes from 0x80 is a control character or NUL
    _cc=$(LC_ALL=C tr -d '\011\012\015\040-\176\200-\377' < "$4" | wc -c | tr -d ' \t') || return 1
    if [ "$((_cc))" -ne 0 ]; then
        [ "$1" != check ] || echo "the OpenVPN config has a control character (NUL, vertical tab, form feed, escape ...), which it may not contain"
        return 1
    fi
    LC_ALL=C awk -v mode="$1" -v map="$2" -v hasauth="$3" '
    function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
    # Only check mode speaks. A message carries the line number and words of our own vocabulary: never an argument,
    # and never a word of the file that is not a directive name we know (a stray password line would be one).
    function bad(m) { if (mode == "check") print "the OpenVPN config, line " NR ": " m; err = 1 }
    function badall(m) { if (mode == "check") print "the OpenVPN config " m; err = 1 }
    function emit(s) { out[++no] = s; isdir[no] = 1 }
    function isnum(s) { return s ~ /^[0-9]+$/ && length(s) <= 9 }
    function isport(s) { return isnum(s) && s + 0 >= 1 && s + 0 <= 65535 }
    function isproto(s) { return s ~ /^(udp|tcp)[46]?$/ || s == "tcp-client" }
    function ip4(s,    a, i) {
        if (s !~ /^[0-9]+[.][0-9]+[.][0-9]+[.][0-9]+$/) return 0
        split(s, a, ".")
        # no leading zeros: some parsers read them as octal
        for (i = 1; i <= 4; i++) if (length(a[i]) > 3 || a[i] + 0 > 255 || a[i] ~ /^0[0-9]/) return 0
        return 1
    }
    # the number of 16-bit groups in a colon list without "::" (an IPv4 tail counts two), or -1
    function groups(s, v4ok,    a, n, i, c) {
        if (s == "") return 0
        n = split(s, a, ":"); c = 0
        for (i = 1; i <= n; i++) {
            if (v4ok && i == n && index(a[i], ".")) { if (!ip4(a[i])) return -1; c += 2 }
            else if (a[i] ~ /^[0-9A-Fa-f]+$/ && length(a[i]) <= 4) c++
            else return -1
        }
        return c
    }
    function ip6(s,    i, l, r, cl, cr) {
        if (s !~ /^[0-9A-Fa-f:.]+$/ || !index(s, ":")) return 0
        i = index(s, "::")
        if (!i) return groups(s, 1) == 8
        l = substr(s, 1, i - 1); r = substr(s, i + 2)
        if (index(r, "::") || index(l, ".")) return 0
        cl = groups(l, 0); cr = groups(r, 1)
        return cl >= 0 && cr >= 0 && cl + cr <= 7
    }
    function isaddr(s) { return ip4(s) || ip6(s) }
    # A name for the resolver: letters, digits, dots and dashes, not starting with "-" (it becomes an argument of
    # the lookup), and digits and dots only when they make an address.
    function ishost(s) {
        if (isaddr(s)) return 1
        return length(s) <= 253 && s ~ /^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$/ && s !~ /^[0-9.]+$/
    }
    function isword(s, re, max) { return s ~ re && length(s) <= max }
    # a value we write in double quotes (an X.509 name, an extended key usage): printable, no quote of either kind
    function istext(s) { return s ~ /^[ -~]+$/ && length(s) <= 128 && !index(s, "\"") && !index(s, "\047") }
    function isver(s) { return s ~ /^1[.][0-3]$/ }

    # Splits l into tok[1..nt] the way openvpn does, and refuses what openvpn could read differently: a word starts
    # at a character that is not white space; "#" or ";" there starts a comment; double or single quotes group a word
    # (no escapes: a backslash was refused already) and must be followed by white space or the end of the line; a
    # quote inside an unquoted word, an empty quoted word and an unclosed quote are refused.
    function lex(l,    i, c, q, w, n) {
        nt = 0; n = length(l); i = 1
        while (i <= n) {
            c = substr(l, i, 1)
            if (c == " " || c == "\t") { i++; continue }
            if (c == "#" || c == ";") break
            if (c == "\"" || c == "\047") {
                q = c; w = ""; i++
                while (i <= n && substr(l, i, 1) != q) { w = w substr(l, i, 1); i++ }
                if (i > n) { bad("has a quote that is not closed"); return -1 }
                i++
                if (i <= n && substr(l, i, 1) != " " && substr(l, i, 1) != "\t") { bad("has a quoted word followed by more text without a space"); return -1 }
                if (w == "") { bad("has an empty quoted word"); return -1 }
                tok[++nt] = w; continue
            }
            w = ""
            while (i <= n) {
                c = substr(l, i, 1)
                if (c == " " || c == "\t") break
                if (c == "\"" || c == "\047") { bad("has a quote inside a word"); return -1 }
                w = w c; i++
            }
            tok[++nt] = w
        }
        return nt
    }

    # One line of an inline block (raw as it is, t trimmed). The PEM armour, the base64 inside it, and for the static
    # keys of tls-auth/tls-crypt the "#" comment lines openvpn writes, are kept byte for byte. In a certificate or key
    # block the text outside the armour (the dump easy-rsa writes before a certificate) is left out: OpenSSL skips it,
    # and nothing that is not PEM reaches openvpn.
    function body(raw, t,    lab) {
        if (t == "") { out[++no] = raw; return }
        if (t ~ /^-----BEGIN [A-Za-z0-9 -]+-----$/) {
            if (arm != "") { bad("has a PEM BEGIN inside another one in <" op ">"); return }
            arm = substr(t, 12, length(t) - 16); narm++; out[++no] = raw; return
        }
        if (t ~ /^-----END [A-Za-z0-9 -]+-----$/) {
            lab = substr(t, 10, length(t) - 14)
            if (arm == "" || lab != arm) { bad("has a PEM END that does not match its BEGIN in <" op ">"); return }
            arm = ""; out[++no] = raw; return
        }
        if (arm != "" || op == "pkcs12") {
            if (t ~ "^[A-Za-z0-9+/=]+$") { nb64++; out[++no] = raw; return }
            if (t ~ /^(Proc-Type|DEK-Info):/) { bad("has an encrypted private key in <" op ">, which needs a passphrase this driver does not take"); return }
            bad("has a line in <" op "> that is not PEM"); return
        }
        if (op == "tls-auth" || op == "tls-crypt") {
            if (t ~ /^#[ -~]*$/) { out[++no] = raw; return }
            bad("has a line in <" op "> that is not part of an OpenVPN static key"); return
        }
        if (t ~ /^[ -~]+$/) { textgone = 1; return }
        bad("has a line in <" op "> that is not PEM")
    }

    BEGIN {
        split("ca cert key tls-auth tls-crypt tls-crypt-v2 dh extra-certs pkcs12", t, " ")
        for (i in t) blocktag[t[i]] = 1
        # directives that take no argument and are written as they are
        split("client tls-client pull remote-random nobind float persist-key persist-tun auth-nocache " \
              "mute-replay-warnings", t, " ")
        for (i in t) flag[t[i]] = 1
        # directives that take one number
        split("tun-mtu ping ping-restart server-poll-timeout connect-retry-max connect-timeout hand-window sndbuf " \
              "rcvbuf txqueuelen", t, " ")
        for (i in t) num1[t[i]] = 1
        # accepted and left out, with a note: our routing and our up script do this
        split("route-nopull redirect-gateway route route-ipv6 dhcp-option block-outside-dns register-dns", t, " ")
        for (i in t) noted[t[i]] = 1
        # The DNS helpers that panel and easy-rsa exports name in up/down. They would rewrite the system resolver,
        # which our up script and the core do instead; a file whose only scripts are these runs without them.
        split("/etc/openvpn/update-resolv-conf /etc/openvpn/update-systemd-resolved " \
              "/etc/openvpn/scripts/update-systemd-resolved", t, " ")
        for (i in t) dnshelper[t[i]] = 1
        # The words a message may repeat: our allowlist and the directives and tags we know to refuse. Any other first
        # word of a line is "a directive this driver does not know", so that a stray secret is never echoed.
        split("client tls-client pull remote remote-random proto port dev dev-type resolv-retry nobind float " \
              "persist-key persist-tun cipher data-ciphers data-ciphers-fallback auth tls-version-min " \
              "tls-version-max tls-cipher tls-ciphersuites tls-groups remote-cert-tls remote-cert-eku remote-cert-ku " \
              "verify-x509-name key-direction compress comp-lzo tun-mtu mssfix fragment ping ping-restart keepalive " \
              "explicit-exit-notify server-poll-timeout connect-retry connect-retry-max connect-timeout hand-window " \
              "auth-user-pass auth-nocache auth-retry reneg-sec sndbuf rcvbuf txqueuelen mute-replay-warnings verb " \
              "mute route-nopull redirect-gateway route route-ipv6 dhcp-option block-outside-dns register-dns " \
              "up down script-security plugin route-up route-pre-down ipchange tls-verify auth-user-pass-verify " \
              "learn-address client-connect client-disconnect client-crresponse up-restart up-delay down-pre " \
              "dev-node ca cert key tls-auth tls-crypt tls-crypt-v2 dh extra-certs pkcs12 crl-verify askpass " \
              "secret config cd chroot user group log log-append status status-version writepid tmp-dir " \
              "management providers engine dns-updown dns setenv setenv-safe push push-reset push-peer-info " \
              "pull-filter socks-proxy http-proxy http-proxy-option http-proxy-user-pass mode server server-bridge " \
              "tls-server ifconfig ifconfig-ipv6 ifconfig-noexec ifconfig-nowarn iproute daemon syslog " \
              "ignore-unknown-option inetd genkey mktun rmtun test-crypto memstats allow-compression " \
              "allow-recursive-routing connection mark local lport rport bind lladdr route-delay route-metric " \
              "route-gateway route-noexec peer-fingerprint pkcs11-providers pkcs11-id tls-export-cert " \
              "capath verify-hash ns-cert-type x509-track x509-username-field ncp-ciphers ncp-disable " \
              "auth-gen-token static-challenge", t, " ")
        for (i in t) vocab[t[i]] = 1
        n = split(map, t, " ")
        for (i = 1; i <= n; i++) { j = index(t[i], "="); m[substr(t[i], 1, j - 1)] = substr(t[i], j + 1) }
    }

    {
        raw = $0; sub(/\r$/, "", raw)
        # a UTF-8 BOM on the first line (a Windows export) is not part of the first word
        if (NR == 1 && substr(raw, 1, 3) == "\357\273\277") raw = substr(raw, 4)
        if (index(raw, "\r")) { bad("has a carriage return inside the line"); next }
        if (length(raw) > 1024) { bad("is longer than 1024 bytes"); next }
        l = trim(raw)

        # Inside a block we refused nothing is read until it closes: it may hold credentials (<auth-user-pass>).
        if (skip != "") { if (substr(l, 1, length(skip) + 3) == "</" skip ">") skip = ""; next }

        # Inside an inline block. openvpn ends a block at any line that STARTS with its closing tag, so every line
        # that starts with "</" and is not exactly the closing tag is refused rather than read differently.
        if (op != "") {
            if (l == "</" op ">") {
                if (arm != "") bad("has a PEM block in <" op "> that is not ended")
                else if (op == "pkcs12" && !nb64) bad("has an empty <pkcs12> block")
                else if (op != "pkcs12" && !narm) bad("has no PEM block in <" op ">")
                out[++no] = l; op = ""; next
            }
            if (substr(l, 1, 2) == "</") { bad("has a closing tag inside <" op "> that is not exactly </" op ">"); next }
            body(raw, l); next
        }

        if (index(raw, "\\")) { bad("has a backslash, which this driver does not take outside the key blocks"); next }
        if (l == "" || l ~ /^[#;]/) next

        # A block opens only on a line that is exactly <NAME>, for the key and certificate blocks; any other line
        # starting with "<" is refused (openvpn would read "<ca> # x" as <ca>, and "<up>" as a script).
        if (substr(l, 1, 1) == "<") {
            tag = l; sub(/^<\/?/, "", tag); sub(/>.*/, "", tag)
            if (l ~ /^<[a-z0-9-]+>$/ && (tag in blocktag)) {
                if (tag in seenblock) { bad("has a second <" tag "> block"); skip = tag; next }
                seenblock[tag] = 1; op = tag; arm = ""; narm = 0; nb64 = 0
                out[++no] = l; next
            }
            if (l == "<connection>") { bad("has <connection> blocks, which this driver does not take: list the servers as remote lines at the top level"); skip = tag; next }
            if (l ~ /^<[a-z0-9-]+>$/) {
                bad((tag in vocab) ? "has an inline block <" tag "> that this driver does not take" : "has an inline block this driver does not know")
                skip = tag; next
            }
            bad("has a line starting with \"<\" that is not exactly one of the inline blocks this driver takes"); next
        }

        if (lex(l) < 1) next
        k = tok[1]; sub(/^--/, "", k); na = nt - 1
        # (tok still holds the words of an earlier, longer line: only the words of this one are used)
        a1 = (nt >= 2) ? tok[2] : ""; a2 = (nt >= 3) ? tok[3] : ""; a3 = (nt >= 4) ? tok[4] : ""

        if (k in flag) {
            if (na) { bad(k " takes no argument here"); next }
            emit(k)
            if (k == "client" || k == "tls-client") isclient = 1
            next
        }
        if (k in num1) {
            if (na != 1 || !isnum(a1)) { bad(k " takes one number"); next }
            emit(k " " a1); next
        }
        if (k in noted) { gone[k] = 1; next }
        if (k == "remote") {
            if (na < 1 || na > 3 || !ishost(a1)) { bad("has a remote that is not a plain HOST [PORT] [PROTO]"); next }
            if (na >= 2 && !isport(a2)) { bad("has a remote with a port that is not a number from 1 to 65535"); next }
            if (na == 3 && !isproto(a3)) { bad("has a remote with a protocol that is not udp or tcp (tcp-client, 4, 6)"); next }
            nrem++
            lit = isaddr(a1)
            if (mode == "hosts" && !lit && !(a1 in seen)) { seen[a1] = 1; hosts[++nh] = a1 }
            if (mode == "remotes" && !(a1 in seen)) { seen[a1] = 1; hosts[++nh] = a1 }
            h = a1
            if (mode == "gen" && !lit) {
                if (!(a1 in m) || !isaddr(m[a1])) { err = 1; next }
                h = m[a1]
            }
            s = "remote " h; if (na >= 2) s = s " " a2; if (na == 3) s = s " " a3
            emit(s); next
        }
        if (k == "proto") { if (na != 1 || !isproto(a1)) { bad("proto takes udp or tcp (tcp-client, 4, 6)"); next } emit(k " " a1); next }
        if (k == "port") { if (na != 1 || !isport(a1)) { bad("port takes a number from 1 to 65535"); next } emit(k " " a1); next }
        if (k == "dev" || k == "dev-type") {
            # The device is ours (--dev tun-mu300 --dev-type tun); a tap profile bridges, which this driver cannot run.
            if (na == 1 && a1 ~ /^tap/) { bad("is a tap (bridged) profile, which this driver does not run: the tunnel is a tun device"); next }
            if (na != 1 || (k == "dev" && a1 !~ /^tun[A-Za-z0-9_-]*$/) || (k == "dev-type" && a1 != "tun")) { bad(k " takes only a tun device here"); next }
            next
        }
        if (k == "verb" || k == "mute") { if (na != 1 || !isnum(a1)) { bad(k " takes one number"); next } next }
        if (k == "resolv-retry") { if (na != 1 || (a1 != "infinite" && !isnum(a1))) { bad(k " takes a number or infinite"); next } emit(k " " a1); next }
        if (k == "cipher" || k == "data-ciphers-fallback" || k == "auth") {
            if (na != 1 || !isword(a1, "^[A-Za-z0-9_-]+$", 64)) { bad(k " takes one algorithm name"); next }
            emit(k " " a1); next
        }
        if (k == "data-ciphers") {
            if (na != 1 || !isword(a1, "^[A-Za-z0-9:_?-]+$", 200)) { bad(k " takes one list of cipher names"); next }
            emit(k " " a1); next
        }
        if (k == "tls-cipher" || k == "tls-ciphersuites") {
            if (na != 1 || !isword(a1, "^[A-Za-z0-9:_+.!@=-]+$", 200)) { bad(k " takes one cipher list"); next }
            emit(k " " a1); next
        }
        if (k == "tls-groups") {
            if (na != 1 || !isword(a1, "^[A-Za-z0-9:_-]+$", 200)) { bad(k " takes one list of group names"); next }
            emit(k " " a1); next
        }
        if (k == "tls-version-min") {
            if (na < 1 || na > 2 || !isver(a1) || (na == 2 && a2 != "or-highest")) { bad(k " takes a TLS version [or-highest]"); next }
            emit(k " " a1 (na == 2 ? " or-highest" : "")); next
        }
        if (k == "tls-version-max") { if (na != 1 || !isver(a1)) { bad(k " takes a TLS version"); next } emit(k " " a1); next }
        if (k == "remote-cert-tls") { if (na != 1 || a1 != "server") { bad(k " takes only server here"); next } emit(k " server"); next }
        if (k == "remote-cert-eku") { if (na != 1 || !istext(a1)) { bad(k " takes one name or OID"); next } emit(k " \"" a1 "\""); next }
        if (k == "remote-cert-ku") {
            if (na < 1 || na > 8) { bad(k " takes one to eight hex values"); next }
            s = k
            for (i = 2; i <= nt; i++) {
                if (!isword(tok[i], "^[0-9A-Fa-f]+$", 4)) { bad(k " takes one to eight hex values"); s = ""; break }
                s = s " " tok[i]
            }
            if (s != "") emit(s)
            next
        }
        if (k == "verify-x509-name") {
            if (na < 1 || na > 2 || !istext(a1) || (na == 2 && a2 !~ /^(subject|name|name-prefix)$/)) { bad(k " takes a name [subject|name|name-prefix]"); next }
            emit(k " \"" a1 "\"" (na == 2 ? " " a2 : "")); next
        }
        if (k == "key-direction") { if (na != 1 || (a1 != "0" && a1 != "1")) { bad(k " takes 0 or 1"); next } emit(k " " a1); next }
        if (k == "compress") {
            if (na > 1 || (na == 1 && a1 !~ /^(lz4-v2|stub-v2|lz4|stub)$/)) { bad(k " takes nothing, lz4-v2, stub-v2, lz4 or stub"); next }
            emit(na ? k " " a1 : k); next
        }
        if (k == "keepalive") { if (na != 2 || !isnum(a1) || !isnum(a2)) { bad(k " takes two numbers"); next } emit(k " " a1 " " a2); next }
        if (k == "connect-retry" || k == "reneg-sec") {
            if (na < 1 || na > 2 || !isnum(a1) || (na == 2 && !isnum(a2))) { bad(k " takes one or two numbers"); next }
            emit(k " " a1 (na == 2 ? " " a2 : "")); next
        }
        if (k == "explicit-exit-notify") {
            if (na > 1 || (na == 1 && !isnum(a1))) { bad(k " takes at most one number"); next }
            emit(na ? k " " a1 : k); next
        }
        if (k == "mssfix") {
            if (na > 2 || (na >= 1 && !isnum(a1)) || (na == 2 && a2 != "mtu" && a2 != "fixed")) { bad(k " takes [number [mtu|fixed]]"); next }
            emit(k (na >= 1 ? " " a1 : "") (na == 2 ? " " a2 : "")); next
        }
        if (k == "fragment") {
            if (na < 1 || na > 2 || !isnum(a1) || (na == 2 && a2 != "mtu")) { bad(k " takes a number [mtu]"); next }
            emit(k " " a1 (na == 2 ? " mtu" : "")); next
        }
        if (k == "auth-user-pass") {
            # The credentials are always ours (auth.txt, given on the command line); a file named here is not read.
            if (na) { bad("auth-user-pass names a file, which this driver does not read: mu300-vpn profile set ID OVPN_USER / OVPN_PASS"); next }
            needauth = 1; next
        }
        if (k == "auth-retry") {
            # "interact" would ask on a terminal openvpn does not have
            if (na != 1 || (a1 != "none" && a1 != "nointeract")) { bad(k " takes none or nointeract here"); next }
            emit(k " " a1); next
        }
        # A file that wants to run scripts is not run here, with one exception: the well-known DNS helpers, which
        # our up script replaces, are left out with a note.
        if (k == "up" || k == "down") {
            if (na == 1 && (a1 in dnshelper)) { helper = 1; gone[k] = 1; next }
            bad(k " runs a script, which this driver does not allow (it runs only its own)"); next
        }
        if (k == "script-security") {
            if (na == 1 && (a1 == "1" || a1 == "2")) { sslevel = 1; gone[k] = 1; next }
            bad(k " is set by this driver"); next
        }
        if (k == "comp-lzo") { bad("comp-lzo is not taken (OpenVPN 2.6 refuses it by default): use compress, or no compression on the server"); next }
        bad((k in vocab) ? k " is not a directive this driver takes" : "has a directive this driver does not know")
    }

    END {
        if (op != "") badall("has a block (<" op ">) that is never closed")
        if (skip != "") badall("has a refused block that is never closed")
        if (!nrem) badall("has no remote server")
        if (!isclient) badall("is not a client profile (client or tls-client)")
        if (!(("ca" in seenblock) || ("pkcs12" in seenblock))) badall("has no inline <ca> (or <pkcs12>) block")
        # script-security is only taken along with a DNS helper: a file that just turns scripts on is refused
        if (sslevel && !helper) badall("has script-security without one of the known DNS helper scripts")
        # openvpn reads a config line into 256 bytes, so every directive line we write must fit
        for (i = 1; i <= no; i++) if (isdir[i] && length(out[i]) > 250) { badall("has a directive that is too long"); break }
        if (err) exit 1
        if (mode == "hosts" || mode == "remotes") { for (i = 1; i <= nh; i++) print hosts[i]; exit 0 }
        if (mode == "gen") { for (i = 1; i <= no; i++) print out[i]; exit 0 }
        s = ""; for (k in gone) s = s " " k
        if (s != "") print "note: directives of the file that are not used (this driver runs its own up script and routing):" s
        if (textgone) print "note: the text around the PEM blocks of the certificates was left out"
        if (needauth && hasauth != 1) print "warning: the profile asks for a user name and password: mu300-vpn profile set ID OVPN_USER NAME, then mu300-vpn profile set ID OVPN_PASS - (the password is read from stdin)"
    }' "$4"
}

# ---- the contract ---------------------------------------------------------------------------------------------
drv_engines() { ovpn_bin; }
drv_engines_ok() { [ -x "$(ovpn_bin)" ]; }

drv_check() {
    [ -n "${PDIR:-}" ] && [ -r "$PDIR/client.ovpn" ] || { echo "the profile has no client.ovpn" >&2; return 1; }
    _ha=0; [ -r "$PDIR/auth.txt" ] && _ha=1
    ovpn_read check '' "$_ha" "$PDIR/client.ovpn" >&2
}

drv_gen() {
    drv_check || exit 1
    _of=$PDIR/client.ovpn
    mkdir -p "$RUN"; chmod 700 "$RUN"
    # The remote names are looked up now, before the tunnel exists: openvpn's own lookups would go out on a socket
    # the kill switch does not know. One window around all of them; every remote of the file is kept, each resolved.
    _names=$(ovpn_read hosts '' 0 "$_of") || { echo "the OpenVPN config cannot be read" >&2; exit 1; }
    _map=
    if [ -n "$_names" ]; then
        resolve_window || { resolve_close; echo "could not open the resolve window" >&2; exit 1; }
        while IFS= read -r _h; do
            [ -n "$_h" ] || continue
            _ip=$(vpn_resolve "$_h") || _ip=
            [ -n "$_ip" ] || { resolve_close; echo "cannot resolve the VPN server $_h" >&2; exit 1; }
            _map="$_map $_h=$_ip"
            echo "server $_h -> $_ip"
        done <<EOF
$_names
EOF
        resolve_close || { echo "could not put the kill switch back after the lookups" >&2; exit 1; }
    fi
    rm -f "$RUN/openvpn.conf" "$RUN/ovpn.auth" "$RUN/server-ip" "$RUN/dns" "$RUN/ovpn-up"
    ( umask 077; ovpn_read gen "$_map" 0 "$_of" > "$RUN/openvpn.conf" ) || { rm -f "$RUN/openvpn.conf"; echo "cannot write $RUN/openvpn.conf" >&2; exit 1; }
    # The config we wrote is read back by the same parser, so what openvpn reads is held to the same rules.
    ( umask 077; ovpn_read remotes '' 0 "$RUN/openvpn.conf" > "$RUN/server-ip" ) || { rm -f "$RUN/openvpn.conf" "$RUN/server-ip"; echo "cannot write $RUN/server-ip" >&2; exit 1; }
    echo "openvpn config OK ($RUN/openvpn.conf)"
}

# The core runs this without set -e: every step whose failure leaves half a tunnel returns 1 itself, and openvpn is
# stopped again when it does not come up. The up script is the signal that it did.
drv_start() {
    OVPN_PID=; DRV_PIDS=
    rm -f "$RUN/ovpn-up" "$RUN/dns" "$RUN/ovpn.auth"
    # Our options come after --config, so that they win over anything a config could say. --route-nopull is not
    # used: it would also drop the pushed "dhcp-option DNS" our up script reads. --route-noexec keeps openvpn off the
    # routing table. What the server pushes is held to an accept list (a prefix match, first filter wins: the
    # accepts first, then ignore "" for everything else): the session's addresses and topology, the DNS our up script
    # reads ("dhcp-option DNS" also takes DNS6), the keepalive, and what the data-channel negotiation the client
    # announced decided (peer-id, cipher, auth-token, protocol-flags, key-derivation, tun-mtu: dropping those while
    # the server applies them leaves a data channel that cannot be decrypted or a wrong MTU). Nothing accepted runs
    # anything or names a file; a route, redirect-gateway, setenv, compress, dns, client-nat, block-outside-dns and
    # every other dhcp-option are ignored. --dns-updown is not given: OpenVPN 2.6 (the images' version) does not
    # know it and would not start; on 2.7 our --up script suppresses the built-in dns-updown by itself.
    set -- "$(ovpn_bin)" --config "$RUN/openvpn.conf" --dev "$TUN" --dev-type tun --route-noexec \
        --pull-filter accept ifconfig --pull-filter accept ifconfig-ipv6 --pull-filter accept topology \
        --pull-filter accept "dhcp-option DNS" --pull-filter accept ping --pull-filter accept ping-restart \
        --pull-filter accept peer-id --pull-filter accept cipher --pull-filter accept auth-token \
        --pull-filter accept route-gateway --pull-filter accept protocol-flags --pull-filter accept key-derivation \
        --pull-filter accept tun-mtu --pull-filter ignore "" \
        --mark "$((MARK))" --script-security 2 --up "$LIB/openvpn-up" \
        --setenv MU300_VPN_RUN "$RUN" --auth-nocache --verb 3
    # The credentials are copied into the runtime directory for this one run, and go with it.
    if [ -r "$PDIR/auth.txt" ]; then
        ( umask 077; cat "$PDIR/auth.txt" > "$RUN/ovpn.auth" ) || { rm -f "$RUN/ovpn.auth"; echo "cannot write $RUN/ovpn.auth" >&2; return 1; }
        set -- "$@" --auth-user-pass "$RUN/ovpn.auth"
    fi
    "$@" < /dev/null &
    OVPN_PID=$!; DRV_PIDS=$OVPN_PID
    _n=0
    until [ -e "$RUN/ovpn-up" ]; do
        if ! kill -0 "$OVPN_PID" 2>/dev/null; then
            echo "openvpn exited during start" >&2
            OVPN_PID=; DRV_PIDS=
            rm -f "$RUN/openvpn.conf" "$RUN/ovpn.auth"
            return 1
        fi
        _n=$((_n + 1))
        if [ "$_n" -gt 60 ]; then
            echo "openvpn did not bring the tunnel up within 60 s" >&2
            drv_stop
            return 1
        fi
        sleep 1
    done
    echo "tunnel up on $TUN"
}
drv_alive() {
    [ -n "$OVPN_PID" ] && kill -0 "$OVPN_PID" 2>/dev/null || { DRV_GONE=openvpn; return 1; }
    ip link show "$TUN" >/dev/null 2>&1 || { DRV_GONE=openvpn; return 1; }
}
# TERM lets openvpn close the session and take its device away; KILL after 5 s for one that does not. The runtime
# config holds the keys and ovpn.auth the password, so they go too.
drv_stop() {
    if [ -n "$OVPN_PID" ]; then
        kill "$OVPN_PID" 2>/dev/null || true
        _n=0
        while kill -0 "$OVPN_PID" 2>/dev/null && [ "$_n" -lt 5 ]; do sleep 1; _n=$((_n + 1)); done
        if kill -0 "$OVPN_PID" 2>/dev/null; then kill -9 "$OVPN_PID" 2>/dev/null || true; fi
        wait "$OVPN_PID" 2>/dev/null || true
    fi
    OVPN_PID=; DRV_PIDS=
    rm -f "$RUN/openvpn.conf" "$RUN/ovpn.auth" "$RUN/ovpn-up"
    return 0
}

# an .ovpn, as it is: checked first, so that nothing is written for one that cannot run
drv_import() {
    [ -n "${PDIR:-}" ] && [ -d "$PDIR" ] || { echo "no profile to import into" >&2; return 1; }
    [ -f "$1" ] && [ -r "$1" ] || { echo "an OpenVPN profile is a config file (.ovpn)" >&2; return 1; }
    ovpn_read check '' 0 "$1" >&2 || return 1
    ( umask 077; cat "$1" > "$PDIR/client.ovpn.new.$$" ) && mv "$PDIR/client.ovpn.new.$$" "$PDIR/client.ovpn" && return 0
    rm -f "$PDIR/client.ovpn.new.$$"; return 1
}

# profile set ID OVPN_USER NAME / OVPN_PASS SECRET: auth.txt, two lines, for openvpn's --auth-user-pass. The
# password is better given as "-", which reads it from stdin and keeps it out of the process list. An empty value
# clears that line, and a file with neither goes away. Values are never printed.
drv_set() {
    # The key is checked first, so that stdin is not read for a key this driver does not have.
    case $1 in OVPN_USER|OVPN_PASS) ;; *) return 2 ;; esac
    [ -n "${PDIR:-}" ] && [ -d "$PDIR" ] || return 1
    _v=$2
    if [ "$_v" = - ]; then IFS= read -r _v || :; fi
    _nl='
'
    case $_v in
        *"$_nl"*|*"$(printf '\r')"*) echo "$1 cannot hold a line break" >&2; return 2 ;;
    esac
    _u=; _p=
    if [ -r "$PDIR/auth.txt" ]; then { IFS= read -r _u || :; IFS= read -r _p || :; } < "$PDIR/auth.txt"; fi
    case $1 in OVPN_USER) _u=$_v ;; *) _p=$_v ;; esac
    if [ -z "$_u" ] && [ -z "$_p" ]; then rm -f "$PDIR/auth.txt"; return 0; fi
    ( umask 077; printf '%s\n%s\n' "$_u" "$_p" > "$PDIR/auth.txt.new.$$" ) && mv "$PDIR/auth.txt.new.$$" "$PDIR/auth.txt" && return 0
    rm -f "$PDIR/auth.txt.new.$$"; return 1
}
