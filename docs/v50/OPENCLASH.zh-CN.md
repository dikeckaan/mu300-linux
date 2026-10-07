# 可选 OpenClash

公开镜像不包含 OpenClash、Mihomo 和个人订阅。原设备验证过 OpenClash 0.47.156、
Mihomo 1.19.32 ARM64；这不是其他版本或新内核的兼容性保证。

先备份配置，准备官方 APK、已解压的 Mihomo ARM64 核心及两个文件的可信 SHA256。
在设备上安装前必须准备 dnsmasq-full 和与运行内核匹配的依赖。该设备使用自定义
内核，OpenWrt 默认 feed 的 kmod 可能对应另一内核，不能直接安装。

原 6.18.55 设备将 kmod-tun 和 kmod-nf-conntrack-netlink 替换为说明性元数据包，
其功能已实测内置。新内核必须重新检查内核配置和实际功能，不能复制旧版本声明。
安装工具不自动生成这些声明包，也不强制移除 dnsmasq。

```sh
sh openclash-install.sh /path/openclash.apk APK_SHA256 /path/clash_meta CORE_SHA256
```

该入口验证输入哈希及 TUN 实际创建能力，检查 dnsmasq-full 和内核依赖记录，安装后
关闭代理。它是受控的安装最后一步；依赖准备不正确时会停止。

## 内置 TUN 的 init 兼容补丁

在电脑获取当前 /etc/init.d/openclash，保留原版，通过以下命令生成补丁版本：

```powershell
python tools/v50/patch-openclash.py private/openclash.init.original private/openclash.init.patched
```

工具仅识别已知 check_mod 函数开头，在调用参数为 tun 且 /dev/net/tun 存在时通过。
未知结构会拒绝。先实际创建/删除 TUN 接口，再部署补丁并用 sh -n 检查。
OpenClash 自身升级后需要重新核对。

## 恢复与启用

安装完兼容软件包和核心后，在电脑执行：

```powershell
python tools/v50/maintain.py restore --directory private/before-update
```

恢复只涵盖 /etc/config/openclash、/etc/openclash 中的普通配置文件和 LED 策略。
不复制旧核心、初始化脚本、库、软件包数据库或全套网络配置，恢复后代理仍禁用。
网络/防火墙配置保留在备份中，必要时审阅并手动迁移。

在 LuCI 检查 firewall include、DNS、TUN、局域网直连及节点可用性后再启用。
测试时不要依赖电脑上其他代理的成功结果。DNS 上游应选择设备实际能访问的服务；
原设备曾因不可达的 Google/Cloudflare 直连回退出现断网。
