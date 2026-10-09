# 构建与发布

## 可在 Windows 执行的定制打包

tools/v50/release.py 复用上游已构建的通用 OpenWrt rootfs、5.4 helper bundle 和
6.18 内核。它校验 SHA256SUMS，审查设备私有内容，加入当前源码的 V50 文件，
重新构建两个通用 ramdisk；Image 和与其匹配的模块保持原样。
它不重新编译 Linux，也不重新安装 rootfs 软件包。

输入目录必须是通用 Release，不能是从设备导出的系统。SHA256SUMS 要从可信的
上游 Release 获取；单纯把恶意输入和对应校验表放在一起不是来源认证。

```powershell
python tools/v50/release.py --base work/release/BASE_TAG --output release/YOUR_V50_TAG --tag YOUR_V50_TAG --repo YOUR_ACCOUNT/YOUR_REPOSITORY
python tools/v50/verify-release.py --base work/release/BASE_TAG --output release/YOUR_V50_TAG
```

tag 格式示例为 v2026.10.07-v50.1。输出目录必须不存在，需要 Python 3.12 和 lz4。
先提交本次源代码，再生成正式产物；BUILD-MANIFEST.json 会记录源码提交、dirty 状态、
输入哈希、复用的内核版本以及 device_tested=false。构建失败的目录不要发布。

产物沿用安装器要求的三个资源名，并附 mu300-update、BUILD-MANIFEST.json、SHA256SUMS。
只提供 OpenWrt LuCI、6.18 方案；5.4 bundle 是安装器仍需要的基础资源。
不能宣称这是完整的多系统上游 Release。

## 重新编译

Linux + Docker 环境执行：

```sh
sh tools/v50/build-kernel.sh 6.18.55
upstream/make-bundle.sh work/mu300-kernel-6.18.tar.gz /path/to/verified/mu300-kernel.tar.gz
```

确认 Docker 能运行 ARM64 OpenWrt 容器，再使用现有 openwrt/build-rootfs.sh 构建通用
rootfs。准备 out/modules、busybox、logdw 等输入；不要把设备 vendor 输入交给公开构建。
所有新 Image 必须使用同次构建模块。新增 V50 专属驱动需要适配主线 API、设备树和
模块顺序；本仓库只服务 V50，厂商 5.4 构建里的设备专属配置片段不能直接套用到 6.18。

上游 rootfs feed 软件包未完全锁定。复用校验过的通用 rootfs 可以固定实际输入；
从头构建目前只能记录实际 packages.txt，不能承诺跨时间完全相同的包版本。

## GitHub

运行 python tools/v50/audit.py，检查 git diff --cached 和发布包。备份、个人密码、订阅、
IMEI/NV、SSH 私钥、vendor overlay、安装后的设备启动镜像不进入 Git 或 Releases。
保留原 MIT LICENSE；内核和第三方模块遵循各自许可证，发布二进制时提供对应源码版本。

第一次上传后，手动运行 V50 CI。重型内核构建由 workflow_dispatch 触发，默认不定时运行。
Prepare V50 release assets 工作流输入上游 tag 和 V50 tag，生成经过校验的下载产物，
将更新仓库写为当前 Fork；它不会公开创建 Release，也不需要写入仓库的权限。
首次产物发布为预发布，实机验收后再提升版本。打包和 CI 均不会自动创建公开 Release。
origin 的上传目标尚未配置时，不执行 git push。
