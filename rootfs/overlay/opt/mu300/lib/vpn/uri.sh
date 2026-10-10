# mu300-vpn's link parsing and JSON helpers, sourced by mu300-vpn when it loads (tests call parse_uri and json_str
# straight after sourcing it). Nothing here runs anything: it only takes a link apart, writes JSON strings, and
# stores a link or a JSON config in a profile.

# json_str VALUE : JSON string literal
json_str() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }
# json_list "a,b,c" : JSON array of strings
json_list() { printf '%s' "$1" | awk -F, '{printf "["; for (i = 1; i <= NF; i++) { gsub(/"/, "\\\"", $i); printf "%s\"%s\"", (i > 1 ? "," : ""), $i } printf "]"}'; }
hex2dec() { printf '%d' "0x$1"; }
# busybox awk has no hex string conversion: decode %XX with printf instead
urldecode() {
    rest=$1; out=
    while :; do
        case "$rest" in
            *%[0-9A-Fa-f][0-9A-Fa-f]*)
                pre=${rest%%%*}; tail=${rest#*%}; hh=$(printf '%s' "$tail" | cut -c1-2); rest=$(printf '%s' "$tail" | cut -c3-)
                out="$out$pre$(printf "\\$(printf '%03o' "$(hex2dec "$hh")")")" ;;
            *) out="$out$rest"; break ;;
        esac
    done
    printf '%s' "$out"
}
param() { printf '%s' "$QUERY" | tr '&' '\n' | sed -n "s/^$1=//p" | head -n1; }

# b64d TEXT: TEXT base64-decoded, standard or URL-safe, with or without its padding (share links use all four).
# jq does the decoding because busybox's base64 applet is optional in OpenWrt's builds, and jq is in every image.
b64d() {
    command -v jq >/dev/null 2>&1 || { echo "reading this link needs jq" >&2; return 1; }
    _b=$(printf '%s' "$1" | tr -d ' \t\r\n' | tr '_-' '/+')
    case $(( ${#_b} % 4 )) in 1) return 1 ;; 2) _b="$_b==" ;; 3) _b="$_b=" ;; esac
    printf '%s\n' "$_b" | jq -Rr '@base64d' 2>/dev/null
}

# The fields every link sets (empty when it does not have them); PROTO is vless, vmess, trojan or ss. METHOD is the
# cipher: vmess's scy, Shadowsocks' method. QUERY is the link's query string, for param.
LINK_FIELDS='PROTO UUID HOST PORT TYPE SECURITY SNI FP ALPN FLOW INSECURE PBK SID WSPATH WSHOST SVC XMODE SPX PASSWORD METHOD AID QUERY'

# link_hostport HOST:PORT: HOST and PORT, from host:port, [v6]:port, or a host alone (port 443). The host goes
# into JSON and into lookups, and the port into JSON as a number, so both are checked here.
link_hostport() {
    _hp=${1%/}
    case $_hp in
        \[*\]:*) HOST=${_hp#\[}; HOST=${HOST%%\]*}; PORT=${_hp##*:} ;;
        \[*\]) HOST=${_hp#\[}; HOST=${HOST%\]}; PORT=443 ;;
        *:*) HOST=${_hp%:*}; PORT=${_hp##*:} ;;
        *) HOST=$_hp; PORT=443 ;;
    esac
    case $HOST in ''|*[!A-Za-z0-9._:-]*) return 1 ;; esac
    case $PORT in ''|*[!0-9]*|??????*) return 1 ;; esac
    [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ]
}
# the transport and TLS fields of a link's query string (vless, trojan): the share-link names Xray's clients use
link_query() {
    TYPE=$(param type); SECURITY=$(param security)
    SNI=$(urldecode "$(param sni)"); [ -n "$SNI" ] || SNI=$(urldecode "$(param peer)")
    FP=$(param fp); ALPN=$(urldecode "$(param alpn)"); FLOW=$(param flow)
    INSECURE=$(param allowInsecure); PBK=$(param pbk); SID=$(param sid)
    WSPATH=$(urldecode "$(param path)"); WSHOST=$(urldecode "$(param host)"); SVC=$(urldecode "$(param serviceName)")
    XMODE=$(param mode); SPX=$(urldecode "$(param spx)")
}
# vmess_field KEY: a key of the vmess link's JSON ($_vm) as text, with control characters dropped (a value is put
# into JSON and into one-line files). No regular expressions: OpenWrt's jq may be built without them.
vmess_field() {
    printf '%s' "$_vm" | jq -r --arg k "$1" '.[$k] // empty | tostring | explode | map(select(. >= 32)) | implode'
}

# parse_link URI: a vless, vmess, trojan or ss (Shadowsocks) share link taken apart into LINK_FIELDS. Returns 1
# with a message on a link it cannot use; the message never repeats the link, which carries the credentials.
parse_link() {
    for _f in $LINK_FIELDS; do eval "$_f="; done
    _u=$1
    _cr=$(printf '\r')
    case $_u in *'
'*|*"$_cr"*) echo "a link is one line" >&2; return 1 ;; esac
    _u=${_u%%#*}
    case $_u in
        vless://*)
            PROTO=vless; _u=${_u#vless://}
            case $_u in *\?*) QUERY=${_u#*\?}; _u=${_u%%\?*} ;; esac
            case $_u in *@*) ;; *) echo "cannot parse the vless link" >&2; return 1 ;; esac
            UUID=$(urldecode "${_u%%@*}")
            link_hostport "${_u#*@}" || { echo "cannot parse the vless link's server" >&2; return 1; }
            link_query
            [ -n "$UUID" ] || { echo "the vless link has no id" >&2; return 1; } ;;
        trojan://*)
            PROTO=trojan; _u=${_u#trojan://}
            case $_u in *\?*) QUERY=${_u#*\?}; _u=${_u%%\?*} ;; esac
            case $_u in *@*) ;; *) echo "cannot parse the trojan link" >&2; return 1 ;; esac
            # the password is everything before the last @ (an @ in it should be %40, but is not always)
            PASSWORD=$(urldecode "${_u%@*}")
            link_hostport "${_u##*@}" || { echo "cannot parse the trojan link's server" >&2; return 1; }
            link_query
            SECURITY=${SECURITY:-tls}
            [ -n "$PASSWORD" ] || { echo "the trojan link has no password" >&2; return 1; } ;;
        vmess://*)
            # v2rayN's format: base64 of a JSON object
            PROTO=vmess
            _vm=$(b64d "${_u#vmess://}") || _vm=
            printf '%s' "$_vm" | jq -e 'type == "object"' >/dev/null 2>&1 ||
                { echo "cannot read the vmess link (base64 JSON)" >&2; return 1; }
            UUID=$(vmess_field id); AID=$(vmess_field aid); METHOD=$(vmess_field scy)
            _h=$(vmess_field add); _p=$(vmess_field port)
            case $_h in *:*) _h="[$_h]" ;; esac
            link_hostport "$_h:$_p" || { echo "cannot parse the vmess link's server" >&2; return 1; }
            TYPE=$(vmess_field net); _ht=$(vmess_field type)
            WSHOST=$(vmess_field host); WSPATH=$(vmess_field path)
            # gRPC's service name travels in path
            [ "$TYPE" != grpc ] || SVC=$WSPATH
            case $(vmess_field tls) in tls) SECURITY=tls ;; reality) SECURITY=reality ;; *) SECURITY=none ;; esac
            SNI=$(vmess_field sni); ALPN=$(vmess_field alpn); FP=$(vmess_field fp)
            PBK=$(vmess_field pbk); SID=$(vmess_field sid)
            _vm=
            case ${TYPE:-tcp}:$_ht in tcp:|tcp:none|raw:|raw:none|ws:*|grpc:*|httpupgrade:*|xhttp:*) ;;
                tcp:*|raw:*) echo "vmess over TCP with a '$_ht' header is not supported" >&2; return 1 ;;
            esac
            AID=${AID:-0}
            case $AID in *[!0-9]*) echo "the vmess link's alterId is not a number" >&2; return 1 ;; esac
            [ -n "$UUID" ] || { echo "the vmess link has no id" >&2; return 1; } ;;
        ss://*)
            PROTO=ss; SECURITY=none; TYPE=tcp; _u=${_u#ss://}
            case $_u in *\?*) QUERY=${_u#*\?}; _u=${_u%%\?*} ;; esac
            # obfs and v2ray plugins are separate programs Xray does not run
            [ -z "$(param plugin)" ] || { echo "ss plugins are not supported" >&2; return 1; }
            _u=${_u%/}
            case $_u in
                *@*)
                    # SIP002: userinfo@host:port, the userinfo base64 of method:password, or (2022 ciphers)
                    # method:password URL-encoded. Base64 has no ":", so a ":" tells the two apart.
                    _d=$(urldecode "${_u%@*}")
                    case $_d in *:*) ;; *) _d=$(b64d "$_d") || _d= ;; esac
                    _hp=${_u##*@} ;;
                *)
                    # the legacy form: base64 of method:password@host:port
                    _d=$(b64d "$_u") || _d=
                    case $_d in *@*) ;; *) echo "cannot read the ss link" >&2; return 1 ;; esac
                    _hp=${_d##*@}; _d=${_d%@*} ;;
            esac
            case $_d in *:*) ;; *) echo "cannot read the ss link's method and password" >&2; return 1 ;; esac
            METHOD=${_d%%:*}; PASSWORD=${_d#*:}
            case $METHOD in ''|*[!A-Za-z0-9-]*) echo "the ss link's method is not one Xray knows" >&2; return 1 ;; esac
            link_hostport "$_hp" || { echo "cannot parse the ss link's server" >&2; return 1; }
            case $METHOD in none|plain) ;; *) [ -n "$PASSWORD" ] || { echo "the ss link has no password" >&2; return 1; } ;; esac ;;
        *) echo "not a vless, vmess, trojan or ss link" >&2; return 1 ;;
    esac
    TYPE=${TYPE:-tcp}; SECURITY=${SECURITY:-none}
    return 0
}
# link_tag URI: the name a link gives itself (the #fragment, vmess's ps), for a profile imported without one
link_tag() {
    case $1 in
        vmess://*) _vm=$(b64d "${1#vmess://}") || _vm=; _t=$(vmess_field ps 2>/dev/null) || _t=; _vm= ;;
        *\#*) _t=$(urldecode "${1#*\#}") ;;
        *) _t= ;;
    esac
    printf '%s' "$_t" | tr -d '\000-\037\177'
}

# parse_uri: the VLESS-only entry point the sing-box driver and the tests use; exits on a link it cannot use
parse_uri() {
    case "$VLESS_URI" in vless://*) ;; *) echo "VLESS_URI must start with vless://" >&2; exit 1 ;; esac
    parse_link "$VLESS_URI" || exit 1
}

# link_need: VLESS_URI set to the link the drivers work from - the active profile's (PURI), or vpn.conf's where the
# store is not used; the run ends when there is none. Only the profile's id is named, never the link.
link_need() {
    VLESS_URI=${PURI:-${VLESS_URI:-}}
    [ -n "$VLESS_URI" ] && return 0
    if [ -n "${ACTIVE:-}" ]; then echo "profile $ACTIVE has no link" >&2
    else echo "VLESS_URI is not set in $CONF" >&2; fi
    exit 1
}
# link_import SRC [SCHEMES]: a link into the profile ($PDIR/uri, 0600, through a temporary file and mv), after it
# has been taken apart once. SCHEMES (default: vless) are the kinds the driver runs; anything else is refused.
link_import() {
    [ -n "${PDIR:-}" ] && [ -d "$PDIR" ] || { echo "no profile to import into" >&2; return 1; }
    _ok=${2:-vless}
    case $1 in *'
'*) echo "a link is one line" >&2; return 1 ;; esac
    case $1 in *://*) _s=${1%%://*} ;; *) _s= ;; esac
    case " $_ok " in *" ${_s:-none} "*) ;; *)
        echo "not a link this profile type takes (it takes: $_ok)" >&2; return 1 ;; esac
    ( parse_link "$1" ) >/dev/null || return 1
    ( umask 077; printf '%s\n' "$1" > "$PDIR/uri.new.$$" ) && mv "$PDIR/uri.new.$$" "$PDIR/uri" && return 0
    rm -f "$PDIR/uri.new.$$"; return 1
}
# is_json FILE: the file's first character that is not white space is "{" (a JSON config rather than a link or
# some other kind of file)
# The size is checked first: the sniff reads the whole file, and nothing may read a file before the cap has said
# it is small enough.
is_json() { [ -f "$1" ] && [ -r "$1" ] && json_size_ok "$1" && [ "$(tr -d ' \t\r\n' < "$1" | cut -c1)" = '{' ]; }

# ---- raw JSON configs: hostile input --------------------------------------------------------------------------
# A raw Xray or sing-box config comes from a user, a panel or a subscription, and the engine runs it as root. It is
# parsed once, strictly (json_strict), and a new document is built from what an allowlist accepts (json_rebuild with
# the driver's program); the engine only ever reads that document. Nothing here uses jq's regular expressions
# (test, match, sub and the rest): OpenWrt's jq may be built without them. jq's own error output is never shown,
# because it quotes pieces of the file, and the file holds the credentials.
#
# mu_fold is how Go's encoding/json, which both engines use, compares a key with a field name: without regard to
# case. ascii_downcase alone is not quite that, since Go also folds two non-ASCII letters onto ASCII ones (U+017F,
# the long s, onto "s", and U+212A, the Kelvin sign, onto "k"), so "liſten" would reach the engine as "listen". Both
# are mapped first. mu_safe is a name as a refusal may print it: letters, digits, "_", "." and "-", at most 40 of
# them, everything else "?". mu_strip removes every key whose folded name is in a list, at any depth. mu_keys_in
# gives the listed names that occur as a key anywhere, and mu_misspelled the listed names that occur spelled some
# other way (a lone "Protocol" is the engine's "protocol", but not the "protocol" the checks here read).
JQ_LIB='
def mu_fold: explode | map(if . == 383 then 115 elif . == 8490 then 107 else . end) | implode | ascii_downcase;
def mu_safe: explode | map(if (. >= 48 and . <= 57) or (. >= 65 and . <= 90) or (. >= 97 and . <= 122)
                           or . == 95 or . == 46 or . == 45 then . else 63 end) | .[:40] | implode;
def mu_in($l): . as $x | any($l[]; . == $x);
def mu_strip($l): if type == "object" then with_entries(select(.key | mu_fold | mu_in($l) | not) | .value |= mu_strip($l))
                  elif type == "array" then map(mu_strip($l)) else . end;
def mu_keys_in($l): [.. | objects | keys_unsorted[] | mu_fold | select(mu_in($l))] | unique;
def mu_misspelled($l): [.. | objects | keys_unsorted[] | . as $k | mu_fold as $f
                        | $l[] | select(mu_fold == $f and . != $k)] | unique;
def mu_type: if type == "string" then mu_fold else "" end;
def mu_marks($m): if type == "object"
                  then with_entries(.value |= mu_marks($m))
                       | if (.streamSettings | type) == "object" then .streamSettings.sockopt = {"mark": $m} else . end
                       | if (.downloadSettings | type) == "object" then .downloadSettings.sockopt = {"mark": $m} else . end
                  elif type == "array" then map(mu_marks($m)) else . end;
'
# Keys no raw config may have anywhere in what is kept of it, compared folded. listen, listen_port and
# external_controller open ports; executable_path, data_directory, torrc and extra_args start programs or name
# directories the engine writes; redirect (Xray's freedom) and override_address/override_port (sing-box's direct and
# route options) send a connection somewhere other than where the config's own routing says. masterkeylog (Xray's
# tlsSettings and realitySettings) makes the engine write the TLS session keys to a file, as root. private_key_path
# and client_key_path (sing-box), keyfile and certificatefile (Xray's certificates) read a key from a path of the
# config's choosing: panels put keys inline, so a path is refused. dssettings is Xray's unix-socket transport. A
# refusal names the key from this list, never the value.
JSON_DENY='listen listen_port external_controller executable_path data_directory torrc extra_args redirect override_address override_port masterkeylog private_key_path client_key_path keyfile certificatefile dssettings'

# json_size_ok FILE: at most 1 MiB, checked before jq reads the file at all
json_size_ok() {
    _js=$(wc -c < "$1" 2>/dev/null | tr -d ' \t') || return 1
    [ -n "$_js" ] && [ "$_js" -le 1048576 ]
}
# json_strict FILE WHAT: FILE is one JSON object that every reader reads the same way, or a message and 1. jq reads
# things that are not JSON (nan, infinity) and keeps the last of two equal keys without a word, where Go's decoder
# keeps the last too but matches field names without regard to case: {"type":"x","Type":"y"} is "x" to jq and "y" to
# the engine. So: the size first; then exactly one document, an object; no number that is not finite; no key twice
# in one object (jq's event stream of the file has one event more for every value a later equal key replaced, so it
# is longer than the stream of what jq kept); and no two keys of one object that fold to the same name.
json_strict() {
    [ -f "$1" ] && [ -r "$1" ] || { echo "cannot read $2" >&2; return 1; }
    command -v jq >/dev/null 2>&1 || { echo "reading a JSON config needs jq" >&2; return 1; }
    json_size_ok "$1" || { echo "$2 is larger than 1 MiB" >&2; return 1; }
    jq -n -e '[inputs] | length == 1 and (.[0] | type == "object")' "$1" >/dev/null 2>&1 ||
        { echo "$2 is not one JSON object (comments, trailing commas and a second document are not JSON)" >&2; return 1; }
    jq -e '[.. | numbers | select(isnan or isinfinite)] | length == 0' "$1" >/dev/null 2>&1 ||
        { echo "$2 has a number that is not a JSON number" >&2; return 1; }
    _ja=$(jq -c --stream . "$1" 2>/dev/null | wc -l) && _jb=$(jq -c tostream "$1" 2>/dev/null | wc -l) &&
        [ "$_ja" -eq "$_jb" ] ||
        { echo "$2 has a key twice in one object (jq and the engine would read different values)" >&2; return 1; }
    _jk=$(jq -r "$JQ_LIB"'[.. | objects | keys_unsorted | map(mu_fold) | group_by(.)[] | select(length > 1) | .[0]
                          | mu_safe] | unique | .[:8] | join(" ")' "$1" 2>/dev/null) ||
        { echo "cannot read $2" >&2; return 1; }
    [ -z "$_jk" ] || { echo "$2 has keys that differ only in case: $_jk" >&2; return 1; }
}
# json_rebuild SRC OUT WHAT PROGRAM [JQ ARGS...]: SRC checked by json_strict, then PROGRAM (a driver's) run on it with
# JQ_LIB and the arguments. PROGRAM gives {"refuse":[reasons]} or {"config":DOC}; DOC goes to OUT (0600, written
# under umask 077), a refusal to stderr as "WHAT is refused: ...", at most 8 reasons. The reasons are the program's
# own words and names (mu_safe, or names from its lists), never a value from the file; they are reduced to
# printable characters once more here all the same. OUT is not left behind when anything fails.
json_rebuild() {
    _jr_src=$1; _jr_out=$2; _jr_what=$3; _jr_prog=$4; shift 4
    rm -f "$_jr_out"
    json_strict "$_jr_src" "$_jr_what" || return 1
    if ! ( umask 077; jq "$@" "$JQ_LIB$_jr_prog" "$_jr_src" > "$_jr_out.r" ) 2>/dev/null; then
        rm -f "$_jr_out.r"; echo "cannot read $_jr_what" >&2; return 1
    fi
    _jr_p=$(jq -r '.refuse // empty | .[]' "$_jr_out.r" 2>/dev/null) || _jr_p='?'
    if [ -n "$_jr_p" ]; then
        rm -f "$_jr_out.r"
        # (the brackets are a list index in a key path, "users[0].bar"; a lone "[" is literal to every tr)
        _jr_p=$(printf '%s\n' "$_jr_p" | tr -c "A-Za-z0-9_.,'() []\n-" '?' | head -n 8 | tr '\n' ';' | sed 's/;$//; s/;/; /g')
        echo "$_jr_what is refused: $_jr_p (change it and import the config again)" >&2
        return 1
    fi
    if ! ( umask 077; jq '.config' "$_jr_out.r" > "$_jr_out" ) 2>/dev/null; then
        rm -f "$_jr_out" "$_jr_out.r"; echo "cannot read $_jr_what" >&2; return 1
    fi
    rm -f "$_jr_out.r"; chmod 600 "$_jr_out"
}
# json_import SRC TEST WHAT: a JSON config file into the profile ($PDIR/config.json, 0600, through a temporary file
# and mv) when it is strict JSON and jq says TEST of it is true. The file is stored as it came, so that profile
# export gives it back; what the engine gets is rebuilt from it at every start, and drv_check runs the same rebuild
# right after the import. WHAT names the kind of config in the refusal; the file itself is never repeated.
json_import() {
    [ -n "${PDIR:-}" ] && [ -d "$PDIR" ] || { echo "no profile to import into" >&2; return 1; }
    json_strict "$1" "the config" || return 1
    jq -e "$2" "$1" >/dev/null 2>&1 || { echo "not $3" >&2; return 1; }
    ( umask 077; cat "$1" > "$PDIR/config.json.new.$$" ) && mv "$PDIR/config.json.new.$$" "$PDIR/config.json" && return 0
    rm -f "$PDIR/config.json.new.$$"; return 1
}
# json_listens_loopback_only FILE: the check behind every rebuild, on the file the engine gets. No listen_port and
# no external_controller at all, and every listen address 127.0.0.1, wherever they sit and however their keys are
# spelled (folded as the engines fold them). The rebuilds already leave nothing else; a later change to one that let
# a listener through fails closed here instead of opening a port on the LAN or the uplink.
json_listens_loopback_only() {
    jq -e "$JQ_LIB"'[.. | objects | to_entries[] | select(.key | mu_fold | mu_in(["listen", "listen_port", "external_controller"]))]
           | all((.key | mu_fold) == "listen" and .value == "127.0.0.1")' "$1" >/dev/null 2>&1
}
# link_opt_set KEY VALUE: an option of a link profile (profile set), checked, into its meta; empty removes it.
# Both go into generated configs, the proxy's port as a JSON number.
link_opt_set() {
    case $1 in
        TLS_PIN_SHA256) case $2 in *[!0-9A-Fa-f:,]*) echo "TLS_PIN_SHA256 is a SHA-256 in hex" >&2; return 2 ;; esac ;;
        UPSTREAM_HTTP_PROXY)
            [ -z "$2" ] || ( link_hostport "$2" && case $2 in *:*) true ;; *) false ;; esac ) ||
                { echo "UPSTREAM_HTTP_PROXY is HOST:PORT" >&2; return 2; } ;;
        *) return 2 ;;
    esac
    if [ -n "$2" ]; then kv_set "$PDIR/meta" "$1" "$2"; else kv_del "$PDIR/meta" "$1"; fi
}
