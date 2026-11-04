# Preserve the upstream checks, adding only built-in metadata and shared engines.
{ lines[NR] = $0; if (index($0, "require(\"luci.passwall2.mu300_compat\")")) patched++ }
END {
    if (patched) { for (i=1; i<=NR; i++) print lines[i]; exit }
    for (i=1; i<=NR; i++) {
        if (kind == "components" && lines[i] == "---- Check the transparent proxy component") block++
        if (kind == "components" && block && lines[i] == "end") { at=i; count++; block=0 }
        if (kind == "status" && lines[i] ~ /^[\t ]*e\["global_status"\] = luci.sys.call\(.*top -bn1/) { at=i; count++ }
    }
    if (count != 1) { print "passwall2: unsupported UI detection layout; original file retained" > "/dev/stderr"; exit 1 }
    for (i=1; i<=NR; i++) {
        if (i == at && kind == "status") {
            print "\te[\"global_status\"] = require(\"luci.passwall2.mu300_compat\").global_running(api.TMP_PATH) or"
            sub(/^[\t ]*e\["global_status"\] = /, "\t\t", lines[i])
        }
        print lines[i]
        if (i == at && kind == "components") print "mods = mods .. \"\\n\" .. require(\"luci.passwall2.mu300_compat\").builtin_modules()"
    }
}
