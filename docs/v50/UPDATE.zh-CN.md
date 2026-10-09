# 更新 V50

## 同步上游源码

推荐 Fork 原仓库，保留完整 Git 历史。origin 指向自己的 Fork，upstream 指向原仓库。
若本机是浅克隆，首次发布前执行 git fetch --unshallow upstream。

```sh
git status --short
git fetch upstream
git diff --stat HEAD...upstream/main
git merge upstream/main
```

先提交自己的改动，再合并。不要 reset --hard、clean -fd 或用完整旧文件覆盖合并后的
文件。重点审查安装识别、boot/init、更新器、LED、构建脚本以及模块加载顺序。
源码合并不会直接更新设备。每次构建记录上游来源及输入 SHA256。

## 解决面板目录（po）冲突

面板的 31 个 `openwrt/luci-app-mu300/po/*/mu300.po` 合并冲突不用手工解。策略只有一条：
只有 `zh_Hans` 是真翻译，其余 30 种语言的 catalog 都放英文 msgid（LuCI 于是显示英文）。

```sh
git checkout --ours -- openwrt/luci-app-mu300/po   # 任取一侧即可，内容随后由工具重写
python3 tools/v50/i18n-policy.py                   # 清 stale、补缺失、除 zh_Hans 外填英文 msgid
python3 tools/v50/i18n-policy.py check             # 干净则退出 0；zh_Hans 待译消息会在这里列出
```

`apply`（默认动作）会列出仍需人工翻译的 `zh_Hans` 消息，有则退出码 1；补齐译文后 `check` 即干净。


## 更新设备

先在电脑创建当前备份；系统 OpenSSH 会询问未知主机指纹和登录密码，工具不保存密码：

```powershell
python tools/v50/maintain.py --host root@192.168.77.1 backup --directory private/before-update
python tools/v50/maintain.py --host root@192.168.77.1 check
```

备份目录不能重复使用。归档包含密码、订阅和节点，应保存在私有存储中。
额外保留 Android 及不可再生分区的既有备份；本工具不负责重新备份这些分区。

在设备 /etc/mu300/update.conf 写入 REPO=你的账号/你的V50仓库；配置按文本解析，不执行。
V50 发布包已写入构建时指定的仓库。检查目标 Release 是否包含 6.18 内核和
mu300-openwrt-luci-rootfs.tar.gz，再在 SSH 会话中更新指定版本：

```sh
mu300-update check
MU300_RELEASE=YOUR_V50_TAG mu300-update apply openwrt-luci
```

有 OpenClash 时，更新器拒绝直接更新。先完成备份、准备新版兼容软件包、停止并禁用代理：

```sh
uci set openclash.config.enable=0
uci commit openclash
/etc/init.d/openclash stop
/etc/init.d/openclash disable
MU300_V50_MIGRATION_READY=1 MU300_RELEASE=YOUR_V50_TAG mu300-update apply openwrt-luci
```

环境开关仅表示操作者已经准备迁移，并不自动安装软件包。新系统位于
/mnt/mu300-disk/openwrt-luci，更新后当前会话仍运行旧目录。
新镜像使用原版 dnsmasq，应先移除新系统中的 OpenClash 防火墙 include，防止引用缺失脚本：

```sh
uci -c /mnt/mu300-disk/openwrt-luci/etc/config -q delete firewall.openclash
uci -c /mnt/mu300-disk/openwrt-luci/etc/config commit firewall
```

确认新镜像包含熄灯服务、profile 和 update.conf，且代理不会在缺少核心时启动，再重启。
登录新系统后按 OPENCLASH.zh-CN.md 重新安装兼容包和核心，从电脑恢复设置。
不要把旧 /lib/apk、/etc/apk/world、/usr/lib 或内核模块目录直接覆盖进新系统。

新系统的 etc/config、etc/mu300、SSH 密钥和账号由上游流程保留；OpenClash 文件及
额外软件包不自动迁移。恢复工具仅恢复代理配置和 LED 策略，不恢复旧初始化脚本。

## 验收

测试 SSH、LuCI、USB 网卡、热点、移动数据、DNS、国内 HTTPS、代理 HTTPS、UDP、
电池读数和 LED。至少验证一次重启恢复。mu300-v50-check 只是检查接口和文件，
不能代替联网实测。成功后才允许清理旧版本；再次更新可能覆盖上一次回退副本。
