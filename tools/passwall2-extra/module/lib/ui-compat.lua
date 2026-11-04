-- Native kernel built-ins and shared engines do not appear at the usual paths.
local fs = require "nixio.fs"
local nixio = require "nixio"
local M = {}

function M.builtin_modules()
    local release = nixio.uname().release
    if type(release) ~= "string" or not release:match("^[%w._+%-]+$") then
        return ""
    end
    return fs.readfile("/lib/modules/" .. release .. "/modules.builtin") or ""
end

function M.global_running(tmp_path)
    local config_arg = "\0" .. tmp_path .. "/acl/acl_default.json\0"
    local pids = fs.dir("/proc")
    if not pids then return false end
    for pid in pids do
        if pid:match("^%d+$") then
            local base = "/proc/" .. pid
            local exe = fs.readlink(base .. "/exe") or ""
            local name = exe:match("([^/]+)$")
            if name == "xray" or name == "sing-box" then
                local args = fs.readfile(base .. "/cmdline") or ""
                if args:find(config_arg, 1, true) then return true end
            end
        end
    end
    return false
end

return M
