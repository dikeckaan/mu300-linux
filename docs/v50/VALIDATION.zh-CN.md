# 本地验证记录

日期：2026-10-07。环境：Windows、Python 3.12、Git for Windows 的 dash/bash/sh。

- 原始 5 个补丁已单独提交，保留上游完整历史。
- PowerShell 安装器函数检查：714 项通过。
- 启动镜像构建测试：10 项通过。
- 新增 V50 测试：Windows 可运行 11 项；rootfs 原子替换测试需要 POSIX 符号链接权限。
- shell 语法检查：现有脚本以及新增维护脚本通过。
- MU3351/V50 单设备选择检查通过。
- OpenClash 原版 0.47.156 init 的补丁生成及 shell 语法检查通过。
- 待提交源码的敏感文件/凭据模式扫描通过。
- 使用本机已缓存的上游 v2026.10.10 通用资源完成定制打包演练，重建了两个通用 ramdisk。

缓存版本号来自现有资源目录，不表示客户端日期或已经发布的本分支版本。
演练产物使用 example/v50-linux 作为占位仓库，不应刷写或公开发布。

Windows 全量 Python 测试未通过：许多测试需要 Linux 文件模式、符号链接、
busybox/cpio 和其他 POSIX 工具；部分既有测试假定 Unix 换行及 POSIX stdin。
这些失败不能当作全量回归通过，也不能仅靠跳过来认定代码正确。
Linux 全量 CI 和新产物实机验证仍待执行。

本轮未修改设备、未上传 GitHub、未运行云端 CI；没有 Docker，未重新编译内核。
NFC/SAR/呼吸灯内核驱动仍未验证，OpenClash 新安装入口尚未在设备执行。
