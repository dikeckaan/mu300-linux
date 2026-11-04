local builtin, release, processes = "", "7.3.1", {}
package.loaded["nixio"] = {uname = function() return {release=release} end}
package.loaded["nixio.fs"] = {
    readfile = function(path)
        if path == "/lib/modules/7.3.1/modules.builtin" then return builtin end
        local id = path:match("^/proc/(%d+)/cmdline$")
        return id and processes[id] and processes[id].args or nil
    end,
    readlink = function(path)
        local id = path:match("^/proc/(%d+)/exe$")
        return id and processes[id] and processes[id].exe or nil
    end,
    dir = function()
        local k
        return function() k=next(processes,k); return k end
    end
}
local compat = assert(loadfile(arg[1]))()
assert(compat.builtin_modules() == "")
builtin = "kernel/net/netfilter/nft_redir.ko\nkernel/net/netfilter/nft_tproxy.ko\n"
assert(compat.builtin_modules():find("nft_tproxy",1,true))
release = "../../wrong"
assert(compat.builtin_modules() == "")
release = "7.3.1"
assert(not compat.global_running("/tmp/etc/passwall2"))
processes["12"] = {exe="/mnt/mu300-disk/extra/vpn/bin/sing-box",args="sing-box\0run\0-c\0/tmp/etc/passwall2/acl/acl_default.json\0"}
assert(compat.global_running("/tmp/etc/passwall2"))
processes["12"].exe = "/other/unrelated"
assert(not compat.global_running("/tmp/etc/passwall2"))
processes["12"].exe = "/provider/xray"
assert(compat.global_running("/tmp/etc/passwall2"))
processes["12"].args = "xray\0-c\0/tmp/etc/passwall2/acl/acl_default.json.other\0"
assert(not compat.global_running("/tmp/etc/passwall2"))
processes["12"].args = "xray\0-c\0/other/acl_default.json\0"
assert(not compat.global_running("/tmp/etc/passwall2"))
print("PASS: built-in detection, absent/invalid metadata, shared engines, unrelated processes and exact config arguments")
