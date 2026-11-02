# Register only catalogs present in this bundle; retain the user's chosen language.
# Use a private package name too: -t alone still reads the default UCI delta path.
pw2_languages() {
    pw2_uci=$(mktemp -d /tmp/mu300-pw2-i18n.XXXXXX) || return 1
    pw2_package=pw2luci$$
    pw2_before=$(sha256sum /etc/config/luci) || { rm -rf "$pw2_uci"; return 1; }
    cp -p /etc/config/luci "$pw2_uci/$pw2_package" || { rm -rf "$pw2_uci"; return 1; }
    mkdir "$pw2_uci/delta" "$pw2_uci/override" || { rm -rf "$pw2_uci"; return 1; }
    pw2_changed=no
    while IFS= read -r pw2_l; do
        case $pw2_l in
            zh-cn) pw2_key=zh_cn; pw2_label='简体中文 (Simplified Chinese)' ;;
            zh-tw) pw2_key=zh_tw; pw2_label='繁體中文 (Traditional Chinese)' ;;
            ru) pw2_key=ru; pw2_label='Русский (Russian)' ;;
            fa) pw2_key=fa; pw2_label='فارسی (Persian)' ;;
            en) continue ;;
            *) rm -rf "$pw2_uci"; return 1 ;;
        esac
        if ! uci -q -c "$pw2_uci" -C "$pw2_uci/override" -t "$pw2_uci/delta" get "$pw2_package.languages.$pw2_key" >/dev/null; then
            uci -q -c "$pw2_uci" -C "$pw2_uci/override" -t "$pw2_uci/delta" set "$pw2_package.languages.$pw2_key=$pw2_label" || { rm -rf "$pw2_uci"; return 1; }
            pw2_changed=yes
        fi
    done < "$1"
    if [ "$pw2_changed" = yes ]; then
        uci -q -c "$pw2_uci" -C "$pw2_uci/override" -t "$pw2_uci/delta" commit "$pw2_package" || { rm -rf "$pw2_uci"; return 1; }
        # If another process saved this file meanwhile, retry instead of replacing it.
        [ "$pw2_before" = "$(sha256sum /etc/config/luci)" ] || { rm -rf "$pw2_uci"; return 1; }
        cp -p "$pw2_uci/$pw2_package" "/etc/config/.luci-passwall2-$$" &&
            mv "/etc/config/.luci-passwall2-$$" /etc/config/luci || { rm -rf "$pw2_uci"; return 1; }
    fi
    rm -rf "$pw2_uci"
}
