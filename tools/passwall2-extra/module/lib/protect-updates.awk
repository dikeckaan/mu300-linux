# Only the pinned upstream api.lua is patched; installation verifies its hash first.
{ print }
/^local function check_path\(app_name\)$/ {
    print "\t-- mu300-passwall2: core ownership stays with the shared provider."
    print "\tlocal shared_path = get_app_path(app_name) or ''"
    print "\tif (app_name == 'xray' or app_name == 'sing-box') and (shared_path:match('/extra/passwall2/libexec/') or shared_path:match('/extra/vpn[^/]*/bin/')) then"
    print "\t\treturn {code = 1, error = i18n.translate('This core is managed by the MU300 Passwall2 extra. Update its provider instead.') }"
    print "\tend"
}
