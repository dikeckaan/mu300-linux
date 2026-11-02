# CLI messages follow LuCI's language, with an explicit override for SSH sessions.
pw2_lang=${MU300_PASSWALL2_LANG:-$(uci -q get luci.main.lang 2>/dev/null || true)}
case $pw2_lang in ''|auto) pw2_lang=${LC_ALL:-${LANG:-en}} ;; esac
# Catalogs are data, never sourced as shell code. Unknown messages stay English.
pw2_zh() {
    awk -F '\t' -v key="$1" '
        $1 == key { print substr($0, index($0, "\t") + 1); found=1; exit }
        END { if (!found) print key }
    ' "$d/i18n/zh.tsv"
}
pw2_msg() {
    case $pw2_lang in
        zh*) pw2_zh "$1" ;;
        *) printf '%s\n' "$1" ;;
    esac
}
