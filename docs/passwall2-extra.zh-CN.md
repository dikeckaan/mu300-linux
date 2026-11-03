# MU300 Passwall2 extra — 独立插件、按条件共享核心

v2026.11.02.2。对接当前 main `e8258b024da1b3d3ab525c3bfc5d5ee9ca36da54` 的自定义 extra 接口，适用 OpenWrt 25.12.x / aarch64_generic。插件保留自己的界面、UCI 配置、服务及多语言，不要求启用作者的 VPN 服务。

## 选择安装包

- **passwall2.tar.gz（复用版，推荐已有兼容核心时使用）**：不含 sing-box/Xray 二进制或它们的 APK。复用现有路径中的兼容核心。没有兼容核心时明确拒绝安装，不能把它称为完全自包含的离线包。
- **passwall2-full.tar.gz（离线完整版）**：同样优先共享；另在 `extra/passwall2/engines` 放一份经校验的后备二进制。核心不再同时作为压缩 APK 留存并解包到系统，减少重复。其他 APK 依赖仍离线携带。

两个文件属于同一个 passwall2 extra。替换安装包会更新该 extra，不需要同时安装两份。

将选择的文件及 `SHA256SUMS` 复制到设备，使用实际文件名运行：

```sh
mu300-extra install passwall2 --from /tmp/passwall2.tar.gz
# 或使用离线完整版
mu300-extra install passwall2 --from /tmp/passwall2-full.tar.gz
mu300-passwall2 cores
mu300-passwall2 status
```

入口：LuCI → 服务 → Passwall2。新装不自动开启代理；已有服务的开机启用/禁用状态会保留。不会启动作者的 VPN 服务，也不会修改其配置和核心文件。

## 复用规则与升级责任

每次启动核心时按下列顺序寻找兼容程序：

1. 用户已有的自定义核心路径。
2. 作者新分拆的 `extra/vpn-xray/bin/xray`、`extra/vpn-singbox/bin/sing-box`。
3. 旧模块 `extra/vpn/bin/`。
4. 系统 `/usr/bin/xray`、`/usr/bin/sing-box`。
5. 离线完整版自己的 `extra/passwall2/engines/`。

当前已验证的核心接口固定为 Xray **26.10.21**、sing-box **1.14.4**；sing-box 还检查 QUIC、uTLS、WireGuard 编译特性。不同版本不直接视为兼容，后续须更新插件的验证范围。作者组件升级/移除后，下次启动重新探测；有后备则使用后备，没有则清楚报错，不悄悄安装新程序。正在运行的核心进程不会由这个探测器重启。

Passwall2 的两个核心路径改为插件自己的 `libexec` 入口；原自定义路径保存在同一 global_app 节的 `mu300_original_xray_file` / `mu300_original_sing_box_file`。节点、订阅、规则与其他配置保留。不会往全局 PATH 放 sing-box/Xray 链接，也不占用原模块的名称。

共享核心由其原组件管理升级。针对锁定的 Passwall2 API 文件增加有哈希约束的更新保护，阻止其内置核心更新器写入共享核心或覆盖分派入口。已有自定义 API 修改时拒绝覆盖。私有后备核心随插件升级；共享核心随原模块或原软件包升级。

不自动删除现有核心软件包或作者组件，因为它们可能被其他服务使用。单纯检测到两个同名文件不构成删除依据。

## 配置、依赖与系统更新

插件数据在 `/mnt/mu300-disk/extra/passwall2`，系统更新保留它，运行中的 OpenWrt 再由挂钩安装依赖。非运行系统的挂钩不执行当前系统的 apk。

安装前离线模拟全部 APK 依赖；缺依赖或缺兼容核心时拒绝。标准 post-install 脚本运行，保留 nohup/base64/timeout 的命令链接。DNS 使用带 nftset 的 dnsmasq-full，替换基础 dnsmasq 时 DHCP/DNS 可能短暂重启。

安装前备份 `/etc/config/dhcp`、`passwall2`、`passwall2_server` 到设备私有目录 `/etc/mu300/passwall2-extra-backups`。失败时恢复这些文件；成功时只新增/调整上述核心路径字段。先应用或撤销尚未保存的 Passwall2 编辑，再安装插件。

内核能力声明包不包含其他内核的 .ko。检查 `/proc/config.gz`、匹配的原生模块及 nft --check；能力不足则拒绝。不同 OpenWrt 大版本需要重新锁定和验证依赖。

插件本身不包含设备备份、订阅、节点、密码或遥测逻辑。自定义 extra 不会由上游自动下载/升级，需要显式提供新版文件。

## 多语言

英文原文，简体中文、繁体中文、俄语、波斯语的官方翻译包默认全部携带；可精简选择。显示跟随 LuCI，不强制改变当前语言。注册缺少的语言选项时，不提交用户其他尚未保存的 LuCI 修改。翻译只覆盖 Passwall2，其他页面的完整翻译可安装系统 lang extra。CLI 的通用提示支持中英文，底层工具输出保留原文。

## 移除

只移除共享版 extra 时，挂钩先将 Passwall2 路径切回已验证的外部核心，避免删除入口后应用无法启动；保留应用、配置、DNS 和共享组件。如果应用仍依赖该 extra 唯一的私有后备核心，拒绝直接移除，需先提供兼容外部核心或先卸载应用。

```sh
# 移除应用后再移除插件，不删除其他服务的核心或共享 DNS
mu300-passwall2 remove
mu300-extra remove passwall2
```

## 构建

Python3.11+，Linux 主机，带 mkpkg 的 apk-tools v3，以及目标原生内核配置。

```sh
python3 fetch.py cache
python3 build.py --cache cache --apk /path/to/apk.static --config /path/to/kernel.config --output dist/passwall2.tar.gz
python3 build.py --cache cache --apk /path/to/apk.static --config /path/to/kernel.config --engines bundled --output dist/passwall2-full.tar.gz
# 可选：--languages en,zh-cn
```

下载直连 HTTPS、验证证书、固定 TLS1.2。官方 GitHub 发布资产摘要与已签名 OpenWrt 索引绑定的包哈希记录在 `packages.lock.json`；APK 保留各自许可证。核心从锁定 APK 提取，不使用来自设备的程序或私有配置。整个 extra 的 manifest 覆盖所有其他文件。

基础测试：

```sh
MU300_FRAMEWORK=/path/to/main MU300_PASSWALL2_BUNDLE=/path/to/passwall2.tar.gz python3 -m unittest discover -s tests -v
```

验收范围见随包 `VALIDATION.txt`；隔离 ARM64 测试不等于真实路由器上的协议/联网验收。

## 安装器入口

桌面 GUI、Linux/macOS 命令行和 Windows PowerShell 安装器现在提供 Passwall2 选项，默认不勾选，仅 OpenWrt 可用，基础 rootfs 不预装。打包时设置 `MU300_PASSWALL2_EXTRA` 指向已构建的离线扩展，OpenWrt ZIP 会携带一份归档及 SHA256SUMS，供桌面和 Magisk 共用；Ubuntu ZIP 不携带。源码安装也可以用相同变量指定文件及同目录校验文件，`MU300_ANS_PASSWALL2=yes` 回答安装问题。

直接使用 Magisk 安装 ZIP 时，在 `mu300-install.conf` 设置 `MU300_PASSWALL2=yes` 才安装，默认 `no`；文件缺失、校验失败或非 OpenWrt 会明确报错。安装选项不会自动开启代理；首次安装保持关闭，更新保留原服务启用状态。首次启动安装失败可以执行 `mu300-passwall2 install` 重试。

共享核心归档为 12,099,190 字节（11.54 MiB）；含备用核心的完整归档为 42,247,086 字节（40.29 MiB）。备用核心文件展开后合计 85,333,520 字节（81.38 MiB），另外还需要应用、依赖和保留 APK 的空间。这不等于总安装占用或设备节省的空间；仍优先复用兼容的现有核心。
