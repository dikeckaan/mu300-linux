# 恢复

保留原设备不可再生分区备份。不要在公网共享 IMEI、NV、设备镜像或订阅。

## Linux 可以登录

系统和启动镜像分别回退，完成后重启：

```sh
mu300-update rollback openwrt-luci
mu300-update rollback-boot
reboot
```

运行 mu300-update check 确认存在回退副本。不要在验证新版本前运行 clean。
回退恢复前一个系统目录及前一个启动镜像，不负责恢复之前没备份的数据。

## 只能进入 Android

当前设备使用 A 槽 Android、B 槽 Linux。若启动镜像可用，尝试 su -c mu300-linux。
不能进入 Linux 时，在 rooted Android 运行本分支安装器，选择 update、OpenWrt LuCI、
6.18 内核。指定已验证的 V50 Release。不要选择 wipe，也不要刷普通路由器固件。

## 只需恢复直连

```sh
uci set openclash.config.enable=0
uci commit openclash
/etc/init.d/openclash stop
/etc/init.d/openclash disable
/etc/init.d/dnsmasq restart
```

检查 DHCP、DNS、防火墙及 WAN。不能把其他设备的网络配置直接恢复到本机。
