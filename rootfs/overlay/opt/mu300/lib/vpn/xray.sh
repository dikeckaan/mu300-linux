# The xray driver of mu300-vpn (sourced by load_driver): a vless, vmess, trojan or ss link ($PDIR/uri), or a raw
# Xray config ($PDIR/config.json), run by Xray behind hev-socks5-tunnel.
DRV_EXTRA=vpn
# the per-profile options profile set takes (link_opt_set checks them)
DRV_KEYS='TLS_PIN_SHA256 UPSTREAM_HTTP_PROXY'
DRV_PKG=
TUN=xtun
XPID=; HPID=; DRV_GONE=

# ---- xray engine ----------------------------------------------------------------------------------------------
# Xray speaks the link's protocol; hev-socks5-tunnel owns the TUN and hands every TCP/UDP flow to Xray's
# SOCKS port on loopback. Neither installs routes, so the core does (routes_up, DRV_ROUTES=core), with the same rule
# prefs and table as sing-box's auto_route - which is what lets routing_cleanup and the kill switch serve both engines.

listening() { { ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null; } | grep -q "127.0.0.1:$1 "; }

xray_stream_json() {
    case "$TYPE" in tcp|raw) net=raw ;; ws|grpc|httpupgrade|xhttp) net=$TYPE ;;
        *) echo "transport type '$TYPE' is not supported by this helper" >&2; exit 1 ;; esac
    printf '"streamSettings":{"network":"%s"' "$net"
    case "$TYPE" in
        ws) printf ',"wsSettings":{"path":%s' "$(json_str "${WSPATH:-/}")"; [ -n "$WSHOST" ] && printf ',"host":%s' "$(json_str "$WSHOST")"; printf '}' ;;
        grpc) printf ',"grpcSettings":{"serviceName":%s}' "$(json_str "$SVC")" ;;
        httpupgrade) printf ',"httpupgradeSettings":{"path":%s' "$(json_str "${WSPATH:-/}")"; [ -n "$WSHOST" ] && printf ',"host":%s' "$(json_str "$WSHOST")"; printf '}' ;;
        xhttp) printf ',"xhttpSettings":{"path":%s' "$(json_str "${WSPATH:-/}")"; [ -n "$WSHOST" ] && printf ',"host":%s' "$(json_str "$WSHOST")"
               [ -n "$XMODE" ] && printf ',"mode":%s' "$(json_str "$XMODE")"; printf '}' ;;
    esac
    case "$SECURITY" in
        tls)
            printf ',"security":"tls","tlsSettings":{"serverName":%s' "$(json_str "${SNI:-$HOST}")"
            # Xray 26 removed allowInsecure. Its replacement pins the one certificate the server presents,
            # which is stricter: anything else is refused, including a correctly signed certificate for a
            # different host. It also skips the expiry check, so an expired certificate keeps working until
            # the server renews it - and then the pin has to change with it.
            [ -n "$PIN" ] && printf ',"pinnedPeerCertSha256":%s' "$(json_str "$PIN")"
            [ -n "$VCN" ] && printf ',"verifyPeerCertByName":%s' "$(json_str "$VCN")"
            [ -n "$ALPN" ] && printf ',"alpn":%s' "$(json_list "$ALPN")"
            [ -n "$FP" ] && printf ',"fingerprint":%s' "$(json_str "$FP")"
            printf '}' ;;
        reality)
            printf ',"security":"reality","realitySettings":{"serverName":%s,"fingerprint":%s,"publicKey":%s,"shortId":%s' \
                "$(json_str "${SNI:-$HOST}")" "$(json_str "${FP:-chrome}")" "$(json_str "$PBK")" "$(json_str "$SID")"
            [ -n "$SPX" ] && printf ',"spiderX":%s' "$(json_str "$SPX")"
            printf '}' ;;
    esac
    printf ',"sockopt":{"mark":%d}}' "$((MARK))"
}

# Xray 26 has no allowInsecure; pinnedPeerCertSha256 is its replacement. For a link that asks for allowInsecure the
# pin is managed here: fetched once when there is none, kept with the link (save_pin), and fetched again only when
# Xray reports that the server's certificate no longer matches (a renewal). A pin that came from the link (pcs) or
# was written by hand without allowInsecure is left alone.
pin_managed() { [ "$SECURITY" = tls ] && case "$INSECURE" in 1|true) true ;; *) false ;; esac; }

# SHA-256 of the leaf certificate the server presents, in the form Xray expects. Goes out directly: at start the
# tunnel's rules are not in place yet, and while it runs rule 9002 keeps the server's address off the tunnel.
fetch_pin() {
    command -v openssl >/dev/null 2>&1 || { echo "fetching the server certificate needs openssl (OpenWrt: apk add openssl-util)" >&2; return 1; }
    t=; command -v timeout >/dev/null 2>&1 && t="timeout 20"
    h=$($t openssl s_client -connect "$SERVER_IP:$PORT" -servername "${SNI:-$HOST}" </dev/null 2>/dev/null |
        openssl x509 -outform DER 2>/dev/null | sha256sum | cut -d' ' -f1)
    # the hash of nothing is what an empty pipe produces when the handshake failed
    case "$h" in ""|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855) return 1 ;; esac
    printf '%s' "$h"
}

# the pin goes where the link is: the active profile's meta, or vpn.conf when the store is not used
save_pin() {
    if [ -n "$ACTIVE" ]; then kv_set "$PDIR/meta" TLS_PIN_SHA256 "$1"; return; fi
    if grep -q '^TLS_PIN_SHA256=' "$CONF"; then sed -i "s/^TLS_PIN_SHA256=.*/TLS_PIN_SHA256=$1/" "$CONF"
    else printf '# fetched by mu300-vpn: the VPN server certificate, standing in for allowInsecure (Xray 26)\nTLS_PIN_SHA256=%s\n' "$1" >> "$CONF"; fi
}

# hev-socks5-tunnel's config: it owns the TUN and hands every flow to Xray's SOCKS inbound on loopback
xray_hev_yml() {
    cat > "$RUN/hev.yml" <<YML
tunnel:
  name: $TUN
  mtu: 8500
  multi-queue: false
  ipv4: 198.18.0.1
socks5:
  port: $SOCKS_PORT
  address: 127.0.0.1
  udp: 'udp'
misc:
  log-level: warn
YML
}

gen_xray() {
    link_need
    parse_link "$VLESS_URI" || exit 1
    ENC=$(urldecode "$(param encryption)")
    # pcs/vcn are the share-link spellings of pinnedPeerCertSha256/verifyPeerCertByName; TLS_PIN_SHA256 in
    # vpn.conf is for links written before those existed
    PIN=${TLS_PIN_SHA256:-$(urldecode "$(param pcs)")}; VCN=$(urldecode "$(param vcn)")
    # the name is looked up now and Xray is given the address, so it never has to resolve anything itself - the
    # resolver it would use sits behind the tunnel it is trying to build. The name stays as the SNI. Behind the kill
    # switch the lookup goes through the resolve window (vpn_resolve).
    # (an IPv6 address in the link is used as it is: vpn_resolve looks up IPv4 only)
    case $HOST in *:*) SERVER_IP=$HOST ;; *) SERVER_IP=$(vpn_resolve "$HOST") ;; esac
    [ -n "$SERVER_IP" ] || { echo "cannot resolve the VPN server $HOST" >&2; exit 1; }
    # allowInsecure with nothing pinned yet: take whatever certificate the server presents now and keep it
    if pin_managed && [ -z "$PIN" ]; then
        # The certificate is fetched by openssl, unmarked: behind the kill switch it cannot get out, and no window
        # is opened for it (it would have to let the device talk to any server). Closed, with what to do instead.
        if [ "$ENABLE" = 1 ] && [ "$KILL_SWITCH" = 1 ]; then
            echo "the link asks for allowInsecure, which Xray no longer has, and behind the kill switch the" \
                "server's certificate cannot be fetched to pin instead:" \
                "mu300-vpn profile set ${ACTIVE:-ID} TLS_PIN_SHA256 ..." >&2
            exit 1
        fi
        PIN=$(fetch_pin) || { echo "the link asks for allowInsecure, which Xray no longer has, and the server's" \
            "certificate could not be fetched to pin instead: mu300-vpn profile set ${ACTIVE:-ID} TLS_PIN_SHA256 ..." \
            "(or TLS_PIN_SHA256 in $CONF without a profile store)" >&2; exit 1; }
        save_pin "$PIN"
        echo "pinned the server's current certificate ($PIN)"
    fi
    mkdir -p "$RUN"; chmod 700 "$RUN"
    {
    # info, not warning: a failed outbound - including a pin mismatch - is only reported at info. drv_start's
    # reader scans every line and passes on only warnings and worse, so the system log does not fill up.
    printf '{"log":{"loglevel":"info","access":"none"},\n'
    printf '"inbounds":[{"tag":"socks-in","listen":"127.0.0.1","port":%d,"protocol":"socks","settings":{"auth":"noauth","udp":true,"ip":"127.0.0.1"}}],\n' "$SOCKS_PORT"
    # the proxy outbound in the link's protocol; every one gets the same stream settings, with the mark
    case $PROTO in
        vless)
            printf '"outbounds":[{"tag":"proxy","protocol":"vless","settings":{"vnext":[{"address":%s,"port":%s,"users":[{"id":%s,"encryption":%s' \
                "$(json_str "$SERVER_IP")" "$PORT" "$(json_str "$UUID")" "$(json_str "${ENC:-none}")"
            [ -n "$FLOW" ] && printf ',"flow":%s' "$(json_str "$FLOW")"
            printf '}]}]},' ;;
        vmess)
            printf '"outbounds":[{"tag":"proxy","protocol":"vmess","settings":{"vnext":[{"address":%s,"port":%s,"users":[{"id":%s,"alterId":%s,"security":%s}]}]},' \
                "$(json_str "$SERVER_IP")" "$PORT" "$(json_str "$UUID")" "$AID" "$(json_str "${METHOD:-auto}")" ;;
        trojan)
            printf '"outbounds":[{"tag":"proxy","protocol":"trojan","settings":{"servers":[{"address":%s,"port":%s,"password":%s}]},' \
                "$(json_str "$SERVER_IP")" "$PORT" "$(json_str "$PASSWORD")" ;;
        ss)
            printf '"outbounds":[{"tag":"proxy","protocol":"shadowsocks","settings":{"servers":[{"address":%s,"port":%s,"method":%s,"password":%s}]},' \
                "$(json_str "$SERVER_IP")" "$PORT" "$(json_str "$METHOD")" "$(json_str "$PASSWORD")" ;;
    esac
    xray_stream_json; printf '},\n'
    printf '{"tag":"direct","protocol":"freedom","streamSettings":{"sockopt":{"mark":%d}}}]}\n' "$((MARK))"
    } > "$RUN/xray.json"
    chmod 600 "$RUN/xray.json"
    xray_hev_yml
    printf '%s\n' "$SERVER_IP" > "$RUN/server-ip"
    "$XRAY" run -test -c "$RUN/xray.json" >/dev/null || { "$XRAY" run -test -c "$RUN/xray.json" >&2; exit 1; }
    echo "xray config OK ($RUN/xray.json), server $HOST -> $SERVER_IP"
}

# ---- a raw Xray config ----------------------------------------------------------------------------------------
# A config from a panel is run as it is, except for what the device cannot leave to it: its inbounds are replaced by
# our SOCKS inbound on loopback (a panel's config usually listens on 0.0.0.0, which here would be the LAN and the
# uplink), every outbound gets the mark the kill switch lets out, and the server names in vnext and servers are looked
# up by the core and replaced by their addresses, for the same reason as with a link: Xray's own resolver sits behind
# the tunnel it is building. The name stays as the TLS or REALITY serverName where the config gave none, so the
# certificate is still checked against it. There is no certificate pin management here: a raw config says itself
# what it wants verified.
#
# What a raw config may contain is a list (the spec's Security section), and the file Xray gets is a new document
# built from what the list accepts (json_rebuild): json_strict has already refused anything jq and Xray's decoder
# could read differently.
# - Top level: outbounds, routing, dns, fakedns, observatory and burstObservatory are the config's. inbounds and log
#   are ours. api, stats, metrics and policy are dropped without a word, because panels put them in nearly every
#   config they hand out: api and metrics open listeners of their own, stats and policy only matter to them (a
#   routing rule that led to the API's handler goes with it). "remarks", a subscription's name for the config, is
#   dropped too. Anything else - reverse, whose portals take connections in, transport, a key some later Xray adds -
#   refuses the config, naming the key.
# - Outbounds: each one is a NEW object, built from the shape (XRAY_JSON_SHAPE) of its protocol: the keys Xray reads,
#   named exactly, each with the type the shape says. Only the protocols the shape has settings for (compared
#   lowercased, as Xray compares them): dokodemo-door and loopback are inbound plumbing; reverse, anywhere, takes
#   connections in; freedom's redirect sends everything to an address of the config's choosing. A key the shape
#   does not have refuses the config by its path (settings.foo), a value of the wrong type by its path and the type
#   it should be, a key spelled differently from a shape key (Settings, Protocol, SockOpt is the exception below)
#   by the key it collides with: Xray matches field names without regard to case, so "Protocol" would be the
#   protocol to it, but not to these checks. A null value is left out, as Go's decoder leaves a field at null.
#   Three keys are dropped without a word wherever they sit, in any spelling: sockopt and sendThrough (they bind to
#   an interface or an address, or set a mark, and the mark is ours; panels put sockopt in every outbound), and
#   allowInsecure (Xray 26 has no such option: the engine verifies, and a server that needs a pin gets one through
#   pinnedPeerCertSha256, as the link path does). Every outbound gets sockopt {"mark": 720}, and the dialerProxy its
#   sockopt had, which only chains it through another of the config's outbounds. A WireGuard outbound gets
#   noKernelTun, or it would make an interface and ip rules of its own. Xray dials again from inside an outbound
#   (xhttp's downloadSettings is a stream configuration of its own), and that dialer gets {"mark": 720} too:
#   otherwise its connection would leave unmarked and be dropped by the kill switch, or worse, be routed by it.
#   A network of domainsocket (or ds) and dsSettings dial a unix socket of the config's choosing, so they refuse
#   the config; so does a network, a security, a TCP header type or a freedom domainStrategy it does not know.
# - proxySettings.tag, dialerProxy and every routing rule's outboundTag name an outbound the config has. A dns.servers
#   entry is a string, or an object reduced to the keys in XRAY_JSON_DNS_KEYS.
# - No key from JSON_DENY anywhere in what is kept (named as it is there: redirect, masterkeylog, keyfile...), and in
#   routing and dns no key spelled differently from one of the shape's names.
# A transport's path (ws, httpupgrade, xhttp) is a URL path, not a file, so no path is refused; no outbound type
# that is allowed writes a file.
XRAY_JSON_TEST='.outbounds | type == "array"'
XRAY_JSON_KEYS='outbounds routing dns fakedns observatory burstObservatory'
XRAY_JSON_DROPPED='inbounds log api stats metrics policy remarks'
# refused protocols a refusal names; any other is "a protocol it does not know" (a value is never printed)
XRAY_JSON_KNOWN='dokodemo-door loopback tun mtproto hysteria'
XRAY_JSON_DNS_KEYS='address port domains expectIPs skipFallback clientIP queryStrategy tag timeoutMs'
# The shape of an outbound: jq definitions, a key per field Xray reads, each value a shape of its own. "s" string,
# "n" number, "b" boolean, "a" any of the three, "h" a string or a list of strings (Xray's StringList), ["s"] a
# list of strings, [{...}] a list of objects of that shape, {...} an object of that shape, {"*": shape} a map whose
# keys are the config's own (HTTP headers). The spec's Security section summarises this; this is the list.
# Beyond what Xray itself reads, the users of vless and vmess take alterId, email, security and level, which
# v2rayN and v2rayNG write into every user (Xray ignores them); tlsSettings takes both spellings of the pin and the
# name check (the link path writes pinnedPeerCertSha256 and verifyPeerCertByName); and show (a debug print) is
# accepted next to the REALITY and TLS settings, because v2rayN writes it.
XRAY_JSON_SHAPE='
def mu_hdr: {"*": "s"};
def mu_hdrl: {"*": "h"};
def mu_tls: {"serverName": "s", "fingerprint": "s", "alpn": ["s"], "minVersion": "s", "maxVersion": "s",
  "cipherSuites": "s", "pinnedPeerCertificateChainSha256": ["s"], "pinnedPeerCertSha256": "h",
  "verifyPeerCertInNames": ["s"], "verifyPeerCertByName": "s", "curvePreferences": ["s"],
  "enableSessionResumption": "b", "echConfigList": "s", "serverNameToVerify": "s", "show": "b"};
def mu_reality: {"serverName": "s", "fingerprint": "s", "publicKey": "s", "shortId": "s", "spiderX": "s",
  "mldsa65Verify": "s", "show": "b"};
def mu_xhttp0: {"path": "s", "host": "s", "headers": mu_hdr, "mode": "s", "noGRPCHeader": "b", "noSSEHeader": "b",
  "xPaddingBytes": "s", "scMaxEachPostBytes": "a", "scMinPostsIntervalMs": "a", "scMaxBufferedPosts": "n",
  "scStreamUpServerSecs": "a",
  "xmux": {"maxConcurrency": "a", "maxConnections": "a", "cMaxReuseTimes": "a", "hMaxRequestTimes": "a",
           "hMaxReusableSecs": "a", "hKeepAlivePeriod": "n"}};
def mu_xhttp: mu_xhttp0 + {"extra": (mu_xhttp0 + {"downloadSettings": {"address": "s", "port": "n", "network": "s",
  "security": "s", "tlsSettings": mu_tls, "realitySettings": mu_reality,
  "xhttpSettings": (mu_xhttp0 + {"extra": mu_xhttp0})}})};
def mu_tcp: {"header": {"type": "s",
  "request": {"version": "s", "method": "s", "path": ["s"], "headers": mu_hdrl},
  "response": {"version": "s", "status": "s", "reason": "s", "headers": mu_hdrl}}};
def mu_stream: {"network": "s", "security": "s", "tlsSettings": mu_tls, "realitySettings": mu_reality,
  "wsSettings": {"path": "s", "host": "s", "headers": mu_hdr, "heartbeatPeriod": "n"},
  "httpupgradeSettings": {"path": "s", "host": "s", "headers": mu_hdr},
  "xhttpSettings": mu_xhttp,
  "grpcSettings": {"serviceName": "s", "authority": "s", "multiMode": "b", "user_agent": "s", "idle_timeout": "n",
                   "health_check_timeout": "n", "permit_without_stream": "b", "initial_windows_size": "n"},
  "kcpSettings": {"mtu": "n", "tti": "n", "uplinkCapacity": "n", "downlinkCapacity": "n", "congestion": "b",
                  "readBufferSize": "n", "writeBufferSize": "n", "header": {"type": "s", "domain": "s"}, "seed": "s"},
  "tcpSettings": mu_tcp, "rawSettings": mu_tcp,
  "httpSettings": {"host": ["s"], "path": "s", "method": "s", "headers": mu_hdrl, "read_idle_timeout": "n",
                   "health_check_timeout": "n"},
  "quicSettings": {"security": "s", "key": "s", "header": {"type": "s"}}};
def mu_vnext_user($u): {"vnext": [{"address": "s", "port": "n", "users": [$u]}]};
def mu_settings: {
  "vless": mu_vnext_user({"id": "s", "encryption": "s", "flow": "s", "level": "n", "email": "s", "alterId": "n",
                          "security": "s"}),
  "vmess": mu_vnext_user({"id": "s", "security": "s", "level": "n", "email": "s", "alterId": "n"}),
  "trojan": {"servers": [{"address": "s", "port": "n", "password": "s", "email": "s", "level": "n"}]},
  "shadowsocks": {"servers": [{"address": "s", "port": "n", "method": "s", "password": "s", "uot": "b",
                               "UoTVersion": "n", "email": "s", "level": "n"}]},
  "socks": {"servers": [{"address": "s", "port": "n", "users": [{"user": "s", "pass": "s", "level": "n"}]}]},
  "http": {"servers": [{"address": "s", "port": "n", "users": [{"user": "s", "pass": "s"}]}]},
  "wireguard": {"secretKey": "s", "address": ["s"],
                "peers": [{"publicKey": "s", "preSharedKey": "s", "endpoint": "s", "allowedIPs": ["s"],
                           "keepAlive": "n"}],
                "mtu": "n", "reserved": ["n"], "workers": "n", "domainStrategy": "s"},
  "freedom": {"domainStrategy": "s", "userLevel": "n",
              "fragment": {"packets": "s", "length": "s", "interval": "s"},
              "noises": [{"type": "s", "packet": "s", "delay": "s"}]},
  "blackhole": {"response": {"type": "s"}},
  "dns": {"network": "s", "address": "s", "port": "n", "nonIPQuery": "s", "blockTypes": ["n"]}};
def mu_outbound($p): {"tag": "s", "protocol": "s", "settings": mu_settings[$p], "streamSettings": mu_stream,
  "proxySettings": {"tag": "s", "transportLayer": "b"},
  "mux": {"enabled": "b", "concurrency": "n", "xudpConcurrency": "n", "xudpProxyUDP443": "s"}};
'
# the values a refusal checks beyond the shape (compared folded, as Xray compares them)
XRAY_JSON_NETWORKS='tcp raw ws websocket grpc gun httpupgrade xhttp splithttp kcp mkcp http h2 h3 quic'
XRAY_JSON_DOMAIN_STRATEGIES='asis useip useipv4 useipv6 useipv4v6 useipv6v4 forceip forceipv4 forceipv6 forceipv4v6 forceipv6v4'
XRAY_JSON_REBUILD='
($keep | split(" ")) as $keep | ($drop | split(" ")) as $drop | ($deny | split(" ") + ["reverse"]) as $deny
| ($known | split(" ")) as $known | ($dnskeys | split(" ")) as $dnskeys
| ($nets | split(" ")) as $nets | ($dstrats | split(" ")) as $dstrats
| (mu_settings | keys) as $protos
| ([mu_outbound("") | .settings = mu_settings | .. | objects | keys[] | select(. != "*")]
   + ["mark", "dialerProxy", "outboundTag", "noKernelTun", "rules"] | unique) as $names
| ["sockopt", "sendthrough", "allowinsecure"] as $dropped
| def mu_tail: explode | if length > 40 then [46, 46, 46] + .[-37:] else . end | implode;
  def mu_bad($p; $w): {"v": null, "p": ["key " + ($p | mu_tail) + " is not " + $w]};
  def mu_ok: {"v": ., "p": []};
  def mu_shape($s; $p):
    if ($s | type) == "string" then
      if $s == "s" then (if type == "string" then mu_ok else mu_bad($p; "a string") end)
      elif $s == "n" then (if type == "number" then mu_ok else mu_bad($p; "a number") end)
      elif $s == "b" then (if type == "boolean" then mu_ok else mu_bad($p; "a boolean") end)
      elif $s == "h" then (if type == "string" or (type == "array" and all(.[]; type == "string")) then mu_ok
                           else mu_bad($p; "a string or a list of strings") end)
      else (if type == "string" or type == "number" or type == "boolean" then mu_ok
            else mu_bad($p; "a string, a number or a boolean") end) end
    elif ($s | type) == "array" then
      if type != "array" then mu_bad($p; "a list")
      else . as $in | reduce range(0; $in | length) as $i ({"v": [], "p": []};
             ($in[$i] | mu_shape($s[0]; $p + "[" + ($i | tostring) + "]")) as $r | .v += [$r.v] | .p += $r.p) end
    elif type != "object" then mu_bad($p; "an object")
    else . as $in | reduce ($in | keys_unsorted[]) as $k ({"v": {}, "p": []};
           $in[$k] as $x | (if $p == "" then ($k | mu_safe) else $p + "." + ($k | mu_safe) end) as $kp
           | if $x == null then .
             elif $s | has("*") then ($x | mu_shape($s["*"]; $kp)) as $r | .v[$k] = $r.v | .p += $r.p
             elif $s | has($k) then ($x | mu_shape($s[$k]; $kp)) as $r | .v[$k] = $r.v | .p += $r.p
             elif $k | mu_fold | mu_in($dropped) then .
             else ($k | mu_fold) as $f | ([$names[] | select(mu_fold == $f and . != $k)] | .[0]) as $c
               | if $c != null then .p += ["a key spelled differently from " + $c]
                 else .p += ["key " + ($kp | mu_tail)] end end) end;
  def mu_stream_problems:
    [(.streamSettings | objects),
     (.streamSettings | objects | .xhttpSettings | objects | .extra | objects | .downloadSettings | objects)
     | (.network | strings | mu_fold
        | select((mu_in($nets) or . == "domainsocket" or . == "ds") | not) | "a network it does not know"),
       (.security | strings | mu_fold | select(mu_in(["", "none", "tls", "reality"]) | not)
        | "a security it does not know"),
       ((.tcpSettings, .rawSettings) | objects | .header | objects | .type | strings | mu_fold
        | select(. != "none" and . != "http") | "a TCP header type it does not know")];
  def mu_out_rebuild:
    if type != "object" then {"v": ., "p": ["an outbound that is not an object"]}
    else ((.streamSettings | objects | .sockopt | objects | .dialerProxy) // null) as $dp
    | mu_strip(["sockopt", "sendthrough"])
    | (.protocol | mu_type) as $t
    | if $t | mu_in($protos) | not
      then {"v": ., "p": ([if $t | mu_in($known) then "outbound protocol " + $t
                           else "an outbound protocol it does not know" end]
                          + [mu_misspelled($names)[] | "a key spelled differently from " + .])}
      else mu_shape(mu_outbound($t); "") as $r
      | ($r.v
         | if $t == "wireguard" then .settings.noKernelTun = true else . end
         | mu_marks($mark)
         | .streamSettings.sockopt = ({"mark": $mark} + (if $dp != null then {"dialerProxy": $dp} else {} end))) as $v
      | {"v": $v, "p": ($r.p + ($v | mu_stream_problems)
                        + (if $t == "freedom"
                           then [$v.settings | objects | .domainStrategy | strings | mu_fold
                                 | select(mu_in($dstrats) | not) | "a domainStrategy it does not know"]
                           else [] end))} end end;
  [keys_unsorted[] | select(mu_in($keep + $drop) | not) | "top-level key " + mu_safe] as $ptop
| ((.api | objects | .tag | strings) // null) as $api
| with_entries(select(.key | mu_in($keep)))
| if $api != null and (.routing | type) == "object" and (.routing.rules | type) == "array"
  then .routing.rules |= map(select(type != "object" or .outboundTag != $api)) else . end
| . as $src
| ($src.outbounds | if type == "array" then map(mu_out_rebuild) else [] end) as $ro
| if (.outbounds | type) == "array" then .outbounds = [$ro[].v] else . end
| if (.dns | type) == "object" and (.dns.servers | type) == "array"
  then .dns.servers |= map(if type == "object" then with_entries(select(.key | mu_in($dnskeys))) else . end) else . end
| . as $b
| ($b.outbounds | if type == "array" then . else [] end) as $outs
| [$outs[] | objects | .tag | strings] as $tags
| def known_tag: type == "string" and mu_in($tags);
  ($ptop
   + (if ($b.outbounds | type) == "array" then [] else ["no outbounds list"] end)
   + [$ro[].p[]]
   + [$src | mu_keys_in($deny)[] | "key " + .]
   + [$b | del(.outbounds) | mu_misspelled($names)[] | "a key spelled differently from " + .]
   + (if [$b | .. | objects | .network | strings | mu_fold | select(. == "domainsocket" or . == "ds")] | length > 0
      then ["network domainsocket"] else [] end)
   + [$outs[] | objects | (.proxySettings | objects | .tag), (.streamSettings | objects | .sockopt | objects | .dialerProxy)
      | select(. != null and (known_tag | not)) | "proxySettings or dialerProxy naming an outbound it does not have"]
   + [$b.routing | objects | .rules | arrays | .[] | objects | .outboundTag
      | select(. != null and (known_tag | not)) | "a routing rule whose outboundTag is not one of its outbounds"]
  ) as $p
| if ($p | length) > 0 then {"refuse": ($p | unique)}
  else {"config": ($b
    | .log = {"loglevel": "warning", "access": "none"}
    | .inbounds = [{"tag": "socks-in", "listen": "127.0.0.1", "port": $port, "protocol": "socks",
                    "settings": {"auth": "noauth", "udp": true, "ip": "127.0.0.1"}}])} end'
xray_raw() { [ -n "${PDIR:-}" ] && [ -r "$PDIR/config.json" ]; }
# xray_json_rebuild OUT: the profile's config.json, rebuilt (see above) into OUT, or a refusal
xray_json_rebuild() {
    json_rebuild "$PDIR/config.json" "$1" "the profile's Xray config" "$XRAY_JSON_SHAPE$XRAY_JSON_REBUILD" \
        --argjson port "$SOCKS_PORT" --argjson mark "$((MARK))" --arg keep "$XRAY_JSON_KEYS" \
        --arg drop "$XRAY_JSON_DROPPED" --arg deny "$JSON_DENY" --arg known "$XRAY_JSON_KNOWN" \
        --arg dnskeys "$XRAY_JSON_DNS_KEYS" --arg nets "$XRAY_JSON_NETWORKS" --arg dstrats "$XRAY_JSON_DOMAIN_STRATEGIES"
}
# xray_json_addresses FILE: every server address in a rebuilt config's vnext and servers, one per line. Names and
# addresses are told apart in the shell, not with jq's test(): OpenWrt's jq may be built without regular expressions.
xray_json_addresses() {
    jq -r '.outbounds[]? | objects | .settings | objects | (.vnext, .servers) | arrays | .[] | objects
           | .address | strings' "$1"
}
gen_xray_json() {
    command -v jq >/dev/null 2>&1 || { echo "a raw Xray config needs jq" >&2; exit 1; }
    mkdir -p "$RUN"; chmod 700 "$RUN"
    rm -f "$RUN/xray.json"
    # Everything from here on reads the rebuilt document, never the profile's file again.
    _base=$RUN/xray.base.json
    xray_json_rebuild "$_base" || exit 1
    _all=$(xray_json_addresses "$_base" 2>/dev/null) ||
        { rm -f "$_base"; echo "cannot read the servers of the profile's Xray config" >&2; exit 1; }
    # an address goes into a lookup, into JSON and into a routing rule: only what a host name or an address can be
    if printf '%s\n' "$_all" | grep -q '[^A-Za-z0-9._:-]'; then
        rm -f "$_base"; echo "a server in the profile's Xray config is not a host name or an address" >&2; exit 1
    fi
    _names=; _lits=
    for _a in $(printf '%s\n' "$_all" | sort -u); do
        case $_a in *:*) _lits="$_lits $_a" ;; *[!0-9.]*) _names="$_names $_a" ;; *) _lits="$_lits $_a" ;; esac
    done
    # Every name is resolved inside one window (behind the kill switch), and it closes before anything else runs,
    # whether a lookup failed or not.
    _map=; _ips=
    if [ -n "$_names" ]; then
        resolve_window || { resolve_close; rm -f "$_base"; echo "could not open the resolve window" >&2; exit 1; }
        for _h in $_names; do
            _ip=$(vpn_resolve "$_h") || _ip=
            [ -n "$_ip" ] || { resolve_close; rm -f "$_base"; echo "cannot resolve the VPN server $_h" >&2; exit 1; }
            _map="$_map${_map:+,}$(json_str "$_h"):$(json_str "$_ip")"; _ips="$_ips $_ip"
            echo "server $_h -> $_ip"
        done
        resolve_close || { rm -f "$_base"; echo "could not put the kill switch back after the lookups" >&2; exit 1; }
    fi
    # The names in vnext and servers become the addresses looked up; the name stays as the TLS or REALITY
    # serverName where the config gave none.
    ( umask 077; jq --argjson map "{$_map}" '
        def resolved: if type == "object" and (.address | type) == "string" and $map[.address]
                      then .address = $map[.address] else . end;
        .outbounds |= map(
            ([(.settings.vnext, .settings.servers) | arrays | .[] | objects | .address | strings
              | select($map[.])] | first) as $n
            | if (.settings.vnext | type) == "array" then .settings.vnext |= map(resolved) else . end
            | if (.settings.servers | type) == "array" then .settings.servers |= map(resolved) else . end
            | if $n and ((.streamSettings.security // "") == "tls")
                    and ((.streamSettings.tlsSettings.serverName // "") == "")
              then .streamSettings.tlsSettings.serverName = $n
              elif $n and ((.streamSettings.security // "") == "reality")
                    and ((.streamSettings.realitySettings.serverName // "") == "")
              then .streamSettings.realitySettings.serverName = $n
              else . end)' "$_base" > "$RUN/xray.json" ) 2>/dev/null ||
        { rm -f "$RUN/xray.json" "$_base"; echo "cannot rewrite the profile's Xray config" >&2; exit 1; }
    rm -f "$_base"
    chmod 600 "$RUN/xray.json"
    json_listens_loopback_only "$RUN/xray.json" ||
        { rm -f "$RUN/xray.json"; echo "the rewritten Xray config listens beyond 127.0.0.1" >&2; exit 1; }
    xray_hev_yml
    # the resolved names and the addresses the config gave: rule 9002 keeps every one of them off the tunnel
    for _a in $_ips $_lits; do printf '%s\n' "$_a"; done > "$RUN/server-ip"
    "$XRAY" run -test -c "$RUN/xray.json" >/dev/null || { "$XRAY" run -test -c "$RUN/xray.json" >&2; exit 1; }
    echo "xray config OK ($RUN/xray.json)"
}

drv_engines() { printf '%s\n' "$XRAY" "$HEV"; }
drv_engines_ok() {
    [ -x "$XRAY" ] && [ -x "$HEV" ] && return 0
    # an image built before the xray engine existed has only sing-box: a VLESS link keeps working with what is
    # there (the core runs it on the sing-box driver)
    case ${PURI:-${VLESS_URI:-}} in vless://*) [ -x "$BIN" ] ;; *) return 1 ;; esac
}
# the link takes apart and its transport is one the stream settings can express, or the raw config rebuilds and its
# servers can be read (Xray itself checks the rebuilt file in drv_gen)
drv_check() {
    if xray_raw; then
        # the rebuild gen runs, into a file of the profile's own (0700) directory that is removed again
        _chk=$PDIR/.check.$$
        xray_json_rebuild "$_chk" || return 1
        xray_json_addresses "$_chk" >/dev/null 2>&1 ||
            { rm -f "$_chk"; echo "cannot read the servers of the profile's Xray config" >&2; return 1; }
        rm -f "$_chk"; return 0
    fi
    ( link_need; parse_link "$VLESS_URI" || exit 1; PIN=; VCN=; xray_stream_json >/dev/null )
}
drv_gen() { if xray_raw; then gen_xray_json; else gen_xray; fi; }
drv_import() {
    if is_json "$1"; then json_import "$1" "$XRAY_JSON_TEST" 'an Xray config (no outbounds list)'
    else link_import "$1" 'vless vmess trojan ss'; fi
}
drv_set() { link_opt_set "$1" "$2"; }

# Two processes and the routing between them, torn down together: if either dies the service exits, the routes
# go with it and procd starts the whole thing again. Leaving rules behind with nothing at the other end is what
# made sing-box's crashes look like a dead modem (routing_cleanup), so every way out of the core's run goes through
# drv_stop and routes_down.
drv_start() {
    # Xray's output goes through a reader that passes it on and notes a pin mismatch, so a renewed server
    # certificate is noticed without polling the server
    # (every step that can fail returns 1 itself: the core runs this without set -e, see load_driver)
    rm -f "$RUN/pin-mismatch" "$RUN/xray.out"
    mkfifo "$RUN/xray.out" || { echo "cannot create $RUN/xray.out" >&2; return 1; }
    while IFS= read -r l; do
        case "$l" in *"peer cert is unrecognized (against pinnedPeerCertSha256)"*) : > "$RUN/pin-mismatch" ;; esac
        case "$l" in *"[Info]"*|*"[Debug]"*) ;; *) printf '%s\n' "$l" ;; esac
    done < "$RUN/xray.out" &
    "$XRAY" run -c "$RUN/xray.json" > "$RUN/xray.out" 2>&1 & XPID=$!
    HPID=; DRV_PIDS=$XPID
    n=0
    until listening "$SOCKS_PORT"; do
        kill -0 "$XPID" 2>/dev/null || { echo "xray exited during start" >&2; return 1; }
        n=$((n + 1)); [ "$n" -lt 15 ] || { echo "xray did not open its SOCKS port" >&2; return 1; }
        sleep 1
    done
    "$HEV" "$RUN/hev.yml" & HPID=$!
    DRV_PIDS="$XPID $HPID"
    n=0
    until ip link show "$TUN" >/dev/null 2>&1; do
        kill -0 "$HPID" 2>/dev/null || { echo "hev-socks5-tunnel exited during start" >&2; return 1; }
        n=$((n + 1)); [ "$n" -lt 15 ] || { echo "$TUN did not appear" >&2; return 1; }
        sleep 1
    done
    ip link set "$TUN" up || { echo "cannot bring $TUN up" >&2; return 1; }
    echo "tunnel up on $TUN (xray $XPID, hev $HPID)"
}
# whichever exits first ends the service
drv_alive() {
    kill -0 "$XPID" 2>/dev/null || { DRV_GONE=xray; return 1; }
    kill -0 "$HPID" 2>/dev/null || { DRV_GONE=hev-socks5-tunnel; return 1; }
}
drv_stop() {
    # (one of them has usually exited already: a kill that finds nothing must not end the teardown under set -e)
    if [ -n "$HPID" ]; then kill "$HPID" 2>/dev/null || true; fi
    if [ -n "$XPID" ]; then kill "$XPID" 2>/dev/null || true; fi
    wait 2>/dev/null || true
    XPID=; HPID=; DRV_PIDS=
    return 0
}
# every 2 s while it runs: a pin mismatch Xray reported means a renewed certificate - pinned again and restarted
drv_poll() {
    [ -e "$RUN/pin-mismatch" ] && pin_managed || return 0
    rm -f "$RUN/pin-mismatch"
    new=$(fetch_pin) || { sleep 30; return 0; }
    [ "$new" = "$PIN" ] && { sleep 30; return 0; }
    save_pin "$new"
    echo "the server's certificate changed; pinned the new one and restarting" >&2
    return 1
}
