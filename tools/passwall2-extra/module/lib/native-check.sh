#!/bin/sh
# Called both before the APK transaction and by each native provider's pre-install.
# Never substitute a feed .ko for a module of the running MU300 kernel.
native_symbol() {
    if printf '%s\n' "$native_config" | grep -qx "$1=y"; then return 0; fi
    if [ -n "$2" ] && printf '%s\n' "$native_config" | grep -qx "$1=m"; then
        native_module=$(find "/lib/modules/$(uname -r)" -type f \( -name "$2.ko" -o -name "$2.ko.xz" -o -name "$2.ko.zst" -o -name "$2.ko.gz" \) 2>/dev/null | head -n 1)
        [ -n "$native_module" ] && modprobe "$2" && return 0
    fi
    echo "passwall2: missing native kernel capability $1; no foreign kernel module will be installed" >&2
    return 1
}
native_check() {
    native_config=$(gzip -dc /proc/config.gz 2>/dev/null) || {
        echo 'passwall2: cannot verify /proc/config.gz' >&2; return 1;
    }
    case $1 in
        kmod-tun) native_symbol CONFIG_TUN tun ;;
        kmod-inet-diag) native_symbol CONFIG_INET_DIAG inet_diag ;;
        kmod-netlink-diag) native_symbol CONFIG_NETLINK_DIAG netlink_diag ;;
        kmod-nf-conntrack-netlink)
            native_symbol CONFIG_NF_CT_NETLINK '' && native_symbol CONFIG_NF_CONNTRACK '' && native_symbol CONFIG_NETFILTER_NETLINK '' ;;
        kmod-nft-socket|kmod-nft-tproxy)
            case $1 in
                kmod-nft-socket)
                    native_symbol CONFIG_NFT_SOCKET '' && native_symbol CONFIG_NF_SOCKET_IPV4 '' && native_symbol CONFIG_NF_SOCKET_IPV6 '' || return 1
                    native_rule='meta l4proto tcp socket transparent 1' ;;
                kmod-nft-tproxy)
                    native_symbol CONFIG_NFT_TPROXY '' && native_symbol CONFIG_NF_TPROXY_IPV4 '' && native_symbol CONFIG_NF_TPROXY_IPV6 '' || return 1
                    native_rule='meta l4proto tcp tproxy to :1041' ;;
            esac
            native_table=mu300_pw2_check_$$
            printf 'add table inet %s\nadd chain inet %s pre { type filter hook prerouting priority mangle; }\nadd rule inet %s pre %s\n' \
                "$native_table" "$native_table" "$native_table" "$native_rule" | nft --check -f - ;;
        *) echo "passwall2: unknown capability $1" >&2; return 1 ;;
    esac
}
