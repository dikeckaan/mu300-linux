# The sing-box driver of mu300-vpn (sourced by load_driver): a VLESS link ($PDIR/uri) or a raw sing-box config
# ($PDIR/config.json), run by sing-box with its own TUN inbound (gvisor stack, see FINDINGS 26b). sing-box installs
# its policy routing itself (auto_route: rule prefs 9000-9010 and table 2022, exactly what the core's routes_up does
# for the other drivers), so DRV_ROUTES=self for both forms; and it is exec'd in the foreground, as the service always
# ran it (DRV_FOREGROUND=1).
DRV_EXTRA=vpn
DRV_PKG=
# (sing-box has no certificate pin: TLS_PIN_SHA256 is the xray driver's)
DRV_KEYS=UPSTREAM_HTTP_PROXY
DRV_ROUTES=self
DRV_FOREGROUND=1
TUN=sbtun

drv_engines() { printf '%s\n' "$BIN"; }
drv_engines_ok() { [ -x "$BIN" ]; }
# the link takes apart (parse_uri exits on a bad one, hence the subshell), or the raw config rebuilds; sing-box
# itself checks the rebuilt file in drv_gen
drv_check() {
    if singbox_raw; then
        # the rebuild gen runs, into a file of the profile's own (0700) directory that is removed again
        singbox_json_rebuild "$PDIR/.check.$$" || return 1
        rm -f "$PDIR/.check.$$"; return 0
    fi
    ( link_need; parse_uri )
}
drv_gen() { if singbox_raw; then gen_singbox_json; else gen_singbox; fi; }
drv_start() { exec "$BIN" run -c "$RUN/config.json"; }
drv_alive() { ip link show "$TUN" >/dev/null 2>&1; }
# exec'd: nothing of its own is left to stop here, and it removes its TUN when it exits
drv_stop() { :; }
drv_import() {
    if is_json "$1"; then json_import "$1" "$SING_BOX_JSON_TEST" 'a sing-box config (no outbound with a type)'
    else link_import "$1"; fi
}
drv_set() { link_opt_set "$1" "$2"; }

outbound_json() {
    printf '{"type":"vless","tag":"proxy","server":%s,"server_port":%s,"uuid":%s' "$(json_str "$HOST")" "$PORT" "$(json_str "$UUID")"
    [ -n "$FLOW" ] && printf ',"flow":%s' "$(json_str "$FLOW")"
    printf ',"packet_encoding":"xudp","domain_resolver":"bootstrap"'
    [ -n "$UPSTREAM_HTTP_PROXY" ] && printf ',"detour":"upstream"'
    case "$SECURITY" in
        tls|reality)
            printf ',"tls":{"enabled":true,"server_name":%s' "$(json_str "${SNI:-$HOST}")"
            case "$INSECURE" in 1|true) printf ',"insecure":true' ;; esac
            # h3 (QUIC) does not apply to VLESS over TCP
            ALPN=$(printf '%s' "$ALPN" | awk -F, '{n = 0; for (i = 1; i <= NF; i++) if ($i != "h3") printf "%s%s", (n++ ? "," : ""), $i}')
            [ -n "$ALPN" ] && printf ',"alpn":%s' "$(json_list "$ALPN")"
            [ -n "$FP" ] && printf ',"utls":{"enabled":true,"fingerprint":%s}' "$(json_str "$FP")"
            [ "$SECURITY" = reality ] && printf ',"reality":{"enabled":true,"public_key":%s,"short_id":%s}' "$(json_str "$PBK")" "$(json_str "$SID")"
            printf '}' ;;
    esac
    case "$TYPE" in
        ws) printf ',"transport":{"type":"ws","path":%s' "$(json_str "${WSPATH:-/}")"; [ -n "$WSHOST" ] && printf ',"headers":{"Host":%s}' "$(json_str "$WSHOST")"; printf '}' ;;
        grpc) printf ',"transport":{"type":"grpc","service_name":%s}' "$(json_str "$SVC")" ;;
        httpupgrade) printf ',"transport":{"type":"httpupgrade","path":%s' "$(json_str "${WSPATH:-/}")"; [ -n "$WSHOST" ] && printf ',"host":%s' "$(json_str "$WSHOST")"; printf '}' ;;
        tcp|raw) ;;
        *) echo "transport type '$TYPE' is not supported by this helper" >&2; exit 1 ;;
    esac
    printf '}'
}

# The TUN's addresses: IPv6 through the tunnel only when the server side has it. Otherwise programs prefer the
# (dead) IPv6 route and every connection to a dual-stack host fails first.
singbox_addrs() {
    if [ "$IPV6" = 1 ]; then printf '"172.19.0.1/30","fdfe:dcba:9876::1/126"'; else printf '"172.19.0.1/30"'; fi
}

gen_singbox() {
    link_need
    parse_uri
    mkdir -p "$RUN"; chmod 700 "$RUN"
    excl=$(json_list "$LAN_CIDRS")
    {
    printf '{"log":{"level":"warn","timestamp":false},\n'
    printf '"dns":{"servers":[{"type":"tcp","tag":"remote","server":%s,"detour":"proxy"},' "$(json_str "$REMOTE_DNS")"
    # the VPN server name is looked up via BOOTSTRAP_DNS (directly, or over TCP through UPSTREAM_HTTP_PROXY)
    if [ -n "$UPSTREAM_HTTP_PROXY" ]; then
        printf '{"type":"tcp","tag":"bootstrap","server":%s,"detour":"upstream"}],' "$(json_str "$BOOTSTRAP_DNS")"
    else
        printf '{"type":"udp","tag":"bootstrap","server":%s}],' "$(json_str "$BOOTSTRAP_DNS")"
    fi
    # IPv6 through the tunnel only when the server side has it: otherwise programs prefer the (dead) IPv6 route and
    # every connection to a dual-stack host fails first, so DNS answers only A records and the TUN gets no IPv6 address
    if [ "$IPV6" = 1 ]; then strategy=prefer_ipv4; else strategy=ipv4_only; fi
    addrs=$(singbox_addrs)
    printf '"final":"remote","strategy":"%s"},\n' "$strategy"
    # "stack":"gvisor", not the default system stack. On this device's 5.4 vendor kernel the system stack
    # takes the connection off the tun and then drops it: sing-box logs one "router: pre-match => sniff" and
    # nothing more, the client gets an RST ("Connection refused", or uclient-fetch's "Operation not permitted")
    # and not a single packet reaches an outbound. DNS still worked, which is what made it look like a routing
    # or firewall problem for so long. The warning it prints on startup is the same story from the other end:
    # "inbound/tun[tun-in]: enable offload: set udp offload: TUNSETOFFLOAD: invalid argument" - the kernel does
    # not have what that stack expects. gvisor carries its own TCP/IP and does not care.
    printf '"inbounds":[{"type":"tun","tag":"tun-in","stack":"gvisor","interface_name":"%s","address":[%s],"mtu":1400,' "$TUN" "$addrs"
    printf '"auto_route":true,"strict_route":true,"route_exclude_address":%s}],\n' "$excl"
    printf '"outbounds":['; outbound_json
    [ -n "$UPSTREAM_HTTP_PROXY" ] && printf ',{"type":"http","tag":"upstream","server":%s,"server_port":%s}' "$(json_str "${UPSTREAM_HTTP_PROXY%:*}")" "${UPSTREAM_HTTP_PROXY##*:}"
    printf ',{"type":"direct","tag":"direct"}],\n'
    # A LAN client's packet to a private address is refused rather than sent "direct": direct leaves outside the
    # tunnel, onto the uplink's own network (the Wi-Fi client's home LAN; wifi-client keeps LAN clients off it
    # when the VPN is off too). The LAN itself never comes in here (route_exclude_address).
    printf '"route":{"rules":[{"action":"sniff"},{"protocol":"dns","action":"hijack-dns"},{"source_ip_cidr":%s,"ip_is_private":true,"action":"reject"},{"ip_is_private":true,"outbound":"direct"}],' "$excl"
    printf '"final":"proxy","auto_detect_interface":true,"default_mark":%d,"default_domain_resolver":"bootstrap"}}\n' "$MARK"
    } > "$RUN/config.json"
    chmod 600 "$RUN/config.json"
    "$BIN" check -c "$RUN/config.json"
}

# ---- a raw sing-box config ------------------------------------------------------------------------------------
# A config from a panel keeps its outbounds, DNS and route rules. What the device needs is put over it: its inbounds
# are replaced by our TUN, as gen_singbox writes it (a panel's mixed or socks inbound on 0.0.0.0 would listen on the
# LAN and the uplink), every connection sing-box makes carries the mark the kill switch lets out (default_mark), it
# leaves on whichever uplink is up (auto_detect_interface), and a UDP server at BOOTSTRAP_DNS resolves the server
# names, unless the config names a default_domain_resolver of its own. sing-box looks them up itself, on its marked
# socket, so no resolve window is needed. A mu300-bootstrap server the config already has (one rewritten before,
# copied from $RUN) is replaced, not doubled: sing-box refuses two servers with one tag.
#
# What a raw config may contain is a list (the spec's Security section), not whatever sing-box accepts: sing-box adds
# features that listen (services such as ssm-api and derp, the clash and v2ray APIs, the debug server) faster than a
# denylist would follow. The file sing-box gets is a new document built from what the list accepts (json_rebuild),
# after json_strict has refused anything jq and sing-box's decoder could read differently.
# - Top level: dns, outbounds, route and endpoints are the config's; log is ours (warn, stdout only: an output path
#   from the config would be a file written as root); inbounds and experimental are dropped (experimental holds the
#   control APIs and a cache file path); any other key refuses the config. In route: rules, rule_set, final and
#   default_domain_resolver are the config's, default_mark and auto_detect_interface ours, default_interface is
#   dropped (the uplink is auto-detected), and any other key refuses the config.
# - Outbounds: only the types in SING_BOX_JSON_TYPES. tor runs a program; a type not listed may be one a later
#   sing-box adds. Endpoints: only WireGuard, with system false and without listen_port and the interface name, so
#   it neither makes an interface nor listens; a Tailscale endpoint would join a tailnet whose members could reach
#   the device. Connections arriving through an endpoint are rejected by a first route rule of ours: the peer is the
#   config author's, and must not reach the LAN or the device. DNS servers: only the types in SING_BOX_JSON_DNS
#   (tailscale, resolved and dhcp hang on what is not ours), and only in the format of sing-box 1.12 and later.
# - The dial fields in SING_BOX_JSON_DIAL are removed wherever they sit in an outbound, endpoint or DNS server: they
#   bind to an interface or an address, or set a mark, and the mark is ours.
# - Every detour (and a rule set's download_detour), a selector's or urltest's outbounds and default, a route rule's
#   outbound and route.final name an outbound or endpoint the config has; a DNS server's domain_resolver names one
#   of its DNS servers.
# - No key from JSON_DENY anywhere in what is kept, and no key spelled differently from a name the checks read
#   (SING_BOX_JSON_NAMES). A local rule set's path names a file sing-box reads; no type that is allowed writes one,
#   so no path is refused.
SING_BOX_JSON_TEST='.outbounds[0].type | type == "string"'
SING_BOX_JSON_KEYS='dns outbounds route endpoints'
SING_BOX_JSON_DROPPED='log inbounds experimental'
SING_BOX_ROUTE_KEYS='rules rule_set final default_domain_resolver'
SING_BOX_ROUTE_DROPPED='default_mark auto_detect_interface default_interface'
SING_BOX_JSON_TYPES='direct block socks http shadowsocks vmess vless trojan hysteria hysteria2 tuic shadowtls anytls ssh selector urltest dns'
# refused types a refusal names; any other is "a type it does not know" (a value is never printed)
SING_BOX_JSON_KNOWN='tor wireguard naive tailscale'
SING_BOX_JSON_DNS='local udp tcp tls https quic h3 hosts fakeip'
SING_BOX_JSON_DNS_KNOWN='tailscale resolved dhcp'
SING_BOX_JSON_DIAL='routing_mark bind_interface inet4_bind_address inet6_bind_address reuse_addr netns protect_path udp_fragment tcp_fast_open tcp_multi_path'
SING_BOX_JSON_NAMES='type tag detour download_detour outbound outbounds default server servers domain_resolver inbound rules rule_set final system'
SING_BOX_JSON_REBUILD='
($keep | split(" ")) as $keep | ($drop | split(" ")) as $drop | ($rkeep | split(" ")) as $rkeep
| ($rdrop | split(" ")) as $rdrop | ($deny | split(" ")) as $deny | ($types | split(" ")) as $types
| ($known | split(" ")) as $known | ($dnst | split(" ")) as $dnst | ($dnsknown | split(" ")) as $dnsknown
| ($dial | split(" ")) as $dial | ($names | split(" ")) as $names
| ([keys_unsorted[] | select(mu_in($keep + $drop) | not) | "top-level key " + mu_safe]
   + [.route | objects | keys_unsorted[] | select(mu_in($rkeep + $rdrop) | not) | "route key " + mu_safe]) as $ptop
| with_entries(select(.key | mu_in($keep)))
| if (.route | type) == "object" then .route |= with_entries(select(.key | mu_in($rkeep))) else . end
| if (.outbounds | type) == "array" then .outbounds |= map(mu_strip($dial)) else . end
| if (.endpoints | type) == "array" then .endpoints |= map(if type == "object" then
      with_entries(select(.key | mu_fold | mu_in(["listen_port", "name", "interface_name", "system"]) | not))
      | mu_strip($dial) | .system = false else . end) else . end
| if (.dns | type) == "object" and (.dns.servers | type) == "array" then .dns.servers |= map(mu_strip($dial)) else . end
| . as $b
| ($b.outbounds | if type == "array" then . else [] end) as $outs
| ($b.endpoints | if type == "array" then . else [] end) as $eps
| (($b.dns | objects | .servers | arrays) // []) as $dnss
| [($outs + $eps)[] | objects | .tag | strings] as $tags
| ([$dnss[] | objects | .tag | strings] + ["mu300-bootstrap"]) as $dnstags
| def known_tag: type == "string" and mu_in($tags);
  ($ptop
   + (if ($b.outbounds | type) == "array" then [] else ["no outbounds list"] end)
   + [$outs[] | if type != "object" then "an outbound that is not an object"
                else (.type | mu_type) as $t
                | if $t | mu_in($types) then empty
                  elif $t | mu_in($known) then "outbound type " + $t
                  else "an outbound type it does not know" end end]
   + (if $b.endpoints == null or ($b.endpoints | type) == "array" then [] else ["endpoints that are not a list"] end)
   + [$eps[] | if type == "object" and (.type | mu_type) == "wireguard"
               then (if (.tag | type) == "string" then empty else "an endpoint without a tag" end)
               elif type == "object" and ((.type | mu_type) | mu_in($known))
               then "an endpoint that is not WireGuard (" + (.type | mu_type) + ")"
               else "an endpoint that is not WireGuard" end]
   + [$dnss[] | if type != "object" then "a DNS server that is not an object"
                elif .type == null then "a DNS server without a type (the format before sing-box 1.12)"
                else (.type | mu_type) as $t
                | if $t | mu_in($dnst) then empty
                  elif $t | mu_in($dnsknown) then "DNS server type " + $t
                  else "a DNS server type it does not know" end end]
   + [$b | mu_keys_in($deny)[] | "key " + .]
   + [$b | mu_misspelled($names)[] | "a key spelled differently from " + .]
   + [($outs + $eps + $dnss)[] | objects | .. | objects | .detour | select(. != null and (known_tag | not))
      | "a detour to a tag that is none of its outbounds"]
   + [$b.route | objects | .rule_set | arrays | .[] | objects | .download_detour
      | select(. != null and (known_tag | not)) | "a rule set download_detour to a tag that is none of its outbounds"]
   + [$outs[] | objects | select((.type | mu_type) | mu_in(["selector", "urltest"]))
      | ((.outbounds | arrays | .[]), .default) | select(. != null and (known_tag | not))
      | "a selector or urltest naming a tag that is none of its outbounds"]
   + [$b.route | objects | (.rules | arrays | .. | objects | .outbound), .final
      | select(. != null and (known_tag | not)) | "a route rule or final naming a tag that is none of its outbounds"]
   + [$dnss[] | objects | .domain_resolver | select(. != null) | (if type == "object" then .server else . end)
      | select((type == "string" and mu_in($dnstags)) | not)
      | "a DNS server domain_resolver that is none of its DNS servers"]
  ) as $p
| if ($p | length) > 0 then {"refuse": ($p | unique)}
  else {"config": ($b
    | .log = {"level": "warn", "timestamp": false}
    | .inbounds = [{"type": "tun", "tag": "tun-in", "stack": "gvisor", "interface_name": $tun, "address": $addrs,
                    "mtu": 1400, "auto_route": true, "strict_route": true, "route_exclude_address": $excl}]
    | .route = (.route // {})
    | ([$eps[] | .tag]) as $eptags
    | if ($eptags | length) > 0
      then .route.rules = [{"inbound": $eptags, "action": "reject"}] + (.route.rules // []) else . end
    | .route.default_mark = $mark | .route.auto_detect_interface = true
    | .dns.servers = ((.dns.servers // []) | map(select(type != "object" or .tag != "mu300-bootstrap"))
                      | . + [{"type": "udp", "tag": "mu300-bootstrap", "server": $boot}])
    | .route.default_domain_resolver = (.route.default_domain_resolver // "mu300-bootstrap"))} end'
singbox_raw() { [ -n "${PDIR:-}" ] && [ -r "$PDIR/config.json" ]; }
# singbox_json_rebuild OUT: the profile's config.json, rebuilt (see above) into OUT, or a refusal
singbox_json_rebuild() {
    json_rebuild "$PDIR/config.json" "$1" "the profile's sing-box config" "$SING_BOX_JSON_REBUILD" \
        --arg tun "$TUN" --argjson addrs "[$(singbox_addrs)]" --argjson excl "$(json_list "$LAN_CIDRS")" \
        --argjson mark "$((MARK))" --arg boot "$BOOTSTRAP_DNS" --arg keep "$SING_BOX_JSON_KEYS" \
        --arg drop "$SING_BOX_JSON_DROPPED" --arg rkeep "$SING_BOX_ROUTE_KEYS" --arg rdrop "$SING_BOX_ROUTE_DROPPED" \
        --arg deny "$JSON_DENY" --arg types "$SING_BOX_JSON_TYPES" --arg known "$SING_BOX_JSON_KNOWN" \
        --arg dnst "$SING_BOX_JSON_DNS" --arg dnsknown "$SING_BOX_JSON_DNS_KNOWN" --arg dial "$SING_BOX_JSON_DIAL" \
        --arg names "$SING_BOX_JSON_NAMES"
}
gen_singbox_json() {
    command -v jq >/dev/null 2>&1 || { echo "a raw sing-box config needs jq" >&2; exit 1; }
    mkdir -p "$RUN"; chmod 700 "$RUN"
    singbox_json_rebuild "$RUN/config.json" || exit 1
    json_listens_loopback_only "$RUN/config.json" ||
        { rm -f "$RUN/config.json"; echo "the rewritten sing-box config listens beyond 127.0.0.1" >&2; exit 1; }
    # sing-box checks the rebuilt file, the one it will run; the profile's own file is never given to it
    "$BIN" check -c "$RUN/config.json"
}
