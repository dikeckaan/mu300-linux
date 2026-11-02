# CLI messages follow LuCI's language, with an explicit override for SSH sessions.
pw2_lang=${MU300_PASSWALL2_LANG:-$(uci -q get luci.main.lang 2>/dev/null || true)}
case $pw2_lang in ''|auto) pw2_lang=${LC_ALL:-${LANG:-en}} ;; esac
pw2_msg() {
    pw2_text=$1
    case $pw2_lang in
        zh*)
            case $1 in
                'OpenWrt only') pw2_text='仅支持 OpenWrt' ;;
                'run as root') pw2_text='请以 root 身份运行' ;;
                'this bundle needs aarch64_generic') pw2_text='此插件包需要 aarch64_generic 架构' ;;
                'this bundle targets OpenWrt 25.12.x; build a bundle for this release first') pw2_text='此插件包适用于 OpenWrt 25.12.x；请为当前系统重新制作匹配的包' ;;
                'bundle manifest check failed') pw2_text='插件文件校验失败' ;;
                'native kernel validation failed') pw2_text='原生内核能力检查失败' ;;
                'offline dependency resolution failed; no packages were changed') pw2_text='离线依赖检查失败，尚未改动软件包' ;;
                'flock is required') pw2_text='需要 flock 命令' ;;
                'another installation is running; retry later') pw2_text='另一个安装任务正在运行，请稍后重试' ;;
                'already installed') pw2_text='此插件版本已安装' ;;
                'installed; LuCI > Services > Passwall2') pw2_text='已安装；入口：LuCI > 服务 > Passwall2' ;;
                'bundle applied') pw2_text='插件包已应用' ;;
                'bundle pending (mu300-passwall2 install)') pw2_text='插件包待应用，请运行 mu300-passwall2 install' ;;
                'not installed (mu300-passwall2 install)') pw2_text='尚未安装，请运行 mu300-passwall2 install' ;;
                'could not register LuCI languages; retry installation') pw2_text='无法注册 LuCI 语言选项，请重试安装' ;;
            esac ;;
    esac
    printf '%s\n' "$pw2_text"
}
