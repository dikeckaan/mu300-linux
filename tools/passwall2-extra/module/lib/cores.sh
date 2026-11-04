# Shared binaries remain owned by their original package/module. No global PATH links.
pw2_probe() (
    # The base image may not have coreutils-timeout until the APK transaction.
    "$1" version &
    pw2_worker=$!
    (sleep 5; kill -TERM "$pw2_worker" 2>/dev/null) >/dev/null 2>&1 &
    pw2_watch=$!
    trap 'kill "$pw2_worker" "$pw2_watch" 2>/dev/null || true' HUP INT TERM
    if wait "$pw2_worker"; then pw2_rc=0; else pw2_rc=$?; fi
    kill "$pw2_watch" 2>/dev/null || true
    wait "$pw2_watch" 2>/dev/null || true
    exit "$pw2_rc"
)
pw2_compatible() {
    [ -x "$1" ] || return 1
    [ "$(readlink -f "$1")" != "$(readlink -f "$d/libexec/$2")" ] || return 1
    pw2_version=$(awk -v n="$2" '$1 == n {print $2}' "$d/core-versions")
    if command -v timeout >/dev/null 2>&1; then
        pw2_output=$(timeout 5 "$1" version) || return 1
    else
        pw2_output=$(pw2_probe "$1") || return 1
    fi
    case $2 in
        xray) case $pw2_output in "Xray $pw2_version "*) return 0 ;; esac ;;
        sing-box)
            [ "$(printf '%s\n' "$pw2_output" | head -n 1)" = "sing-box version $pw2_version" ] || return 1
            pw2_tags=$(printf '%s\n' "$pw2_output" | sed -n 's/^Tags: //p' | tr ',' ' ')
            for pw2_tag in with_quic with_utls with_wireguard; do
                case " $pw2_tags " in *" $pw2_tag "*) ;; *) return 1 ;; esac
            done
            return 0 ;;
    esac
    return 1
}
pw2_pick() {
    case $1 in xray) pw2_key=xray; pw2_module=vpn-xray ;; sing-box) pw2_key=sing_box; pw2_module=vpn-singbox ;; *) return 1 ;; esac
    pw2_custom=$(uci -q get "passwall2.@global_app[0].${pw2_key}_file" 2>/dev/null || true)
    if [ "$pw2_custom" = "$d/libexec/$1" ]; then
        pw2_custom=$(uci -q get "passwall2.@global_app[0].mu300_original_${pw2_key}_file" 2>/dev/null || true)
    fi
    pw2_disk=${MU300_DISK:-/mnt/mu300-disk}
    for pw2_candidate in "$pw2_custom" "$pw2_disk/extra/$pw2_module/bin/$1" "$pw2_disk/extra/vpn/bin/$1" "/usr/bin/$1" "$d/engines/$1"; do
        case $pw2_candidate in /*) ;; *) continue ;; esac
        if pw2_compatible "$pw2_candidate" "$1"; then printf '%s\n' "$pw2_candidate"; return 0; fi
    done
    echo "passwall2: no validated $1 core; install a matching shared core or the full offline bundle (mu300-passwall2 cores)" >&2
    return 1
}
pw2_bind_cores() {
    uci -q get 'passwall2.@global_app[0]' >/dev/null || uci -q add passwall2 global_app >/dev/null
    for pw2_engine in xray sing-box; do
        case $pw2_engine in xray) pw2_key=xray ;; *) pw2_key=sing_box ;; esac
        pw2_original=$(uci -q get "passwall2.@global_app[0].${pw2_key}_file" 2>/dev/null || true)
        if [ -n "$pw2_original" ] && [ "$pw2_original" != "$d/libexec/$pw2_engine" ]; then
            uci -q set "passwall2.@global_app[0].mu300_original_${pw2_key}_file=$pw2_original" || return 1
        fi
        uci -q set "passwall2.@global_app[0].${pw2_key}_file=$d/libexec/$pw2_engine" || return 1
    done
    uci -q commit passwall2
}
