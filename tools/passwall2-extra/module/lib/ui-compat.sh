# Only changes LuCI detection; never changes proxy settings, rules or services.
pw2_ui_files='usr/lib/lua/luci/model/cbi/passwall2/client/global.lua
usr/lib/lua/luci/model/cbi/passwall2/client/other.lua
usr/lib/lua/luci/controller/passwall2.lua'
pw2_ui_helper=usr/lib/lua/luci/passwall2/mu300_compat.lua
pw2_ui_complete() {
    local root=${1:-} file
    cmp -s "$d/lib/ui-compat.lua" "$root/$pw2_ui_helper" || return 1
    for file in $pw2_ui_files; do
        grep -Fq 'require("luci.passwall2.mu300_compat")' "$root/$file" || return 1
    done
}
pw2_ui_install() {
    local root=${1:-} file kind ok=1
    pw2_ui_complete "$root" && return 0
    # Stage and parse all three files before replacing any of them.
    for file in $pw2_ui_files; do
        case $file in */controller/*) kind=status ;; *) kind=components ;; esac
        if ! awk -v kind="$kind" -f "$d/lib/ui-compat.awk" "$root/$file" > "$root/$file.mu300-new" ||
            ! PW2_UI_CHECK="$root/$file.mu300-new" lua -e 'assert(loadfile(os.getenv("PW2_UI_CHECK")))'; then
            ok=0
            break
        fi
    done
    if [ "$ok" != 1 ]; then
        for file in $pw2_ui_files; do rm -f "$root/$file.mu300-new"; done
        return 1
    fi
    cp "$d/lib/ui-compat.lua" "$root/$pw2_ui_helper.mu300-new" || return 1
    chmod 644 "$root/$pw2_ui_helper.mu300-new" || return 1
    mv -f "$root/$pw2_ui_helper.mu300-new" "$root/$pw2_ui_helper" || return 1
    for file in $pw2_ui_files; do
        chmod 644 "$root/$file.mu300-new" && mv -f "$root/$file.mu300-new" "$root/$file" || return 1
    done
}
