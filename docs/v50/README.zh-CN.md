# ZTE V50 / MU3351

本分支基于 [dikeckaan/mu300-linux](https://github.com/dikeckaan/mu300-linux)，
为 ZTE V50（MU3351、ums9620_2h10_feimao）整理安装识别、熄灯和维护功能。
保留上游目录、许可证及其他机型的代码。

源码仓库：[tri-dev3/mu300-linux](https://github.com/tri-dev3/mu300-linux)。
当前发布的是维护源码，尚无经过实机验证的 V50 Release。不要直接刷写本机预览产物。

## 支持范围

| 项目 | 状态 |
|---|---|
| 兼容内核类型 | f50，6.18 系列；配置身份另记为 v50 |
| 原设备验证 | OpenWrt 25.12.5、6.18.55：USB 网卡、SSH、LuCI、热点、移动数据、电池 |
| Android / Linux | 原设备 Android A 槽、Linux B 槽；5 次失败后回退 |
| 熄灯 | 状态灯关闭，AW9523B 自主灯效复位，保留 PMIC 温度报警 |
| OpenClash | 可选安装；个人订阅、节点和密码不包含在镜像中 |
| NFC / SAR / AW9523B 内核驱动 | 未移植验证，不能宣称已支持 |
| 本分支新生成的镜像 | 每个发布版本必须另行实机验证 |

硬件判断和 I2C 写入仅在 LED_DISABLED=1、兼容串匹配、无驱动绑定、芯片 ID
正确时发生。新驱动接管后，脚本跳过直接 I2C 操作。

## 安装

从本分支下载源码，在 rooted Android 下运行安装器。先执行只读检查：

```powershell
.\install.ps1 -Check -Lang en -NoSelfUpdate
$env:MU300_OPENWRT='luci'
.\install.ps1 -Repo tri-dev3/mu300-linux -Release YOUR_VALIDATED_V50_TAG -Lang en -NoSelfUpdate
```

选择 OpenWrt LuCI、6.18 内核；已有 Linux 时选 update。安装仍需要从你自己的
设备提取 vendor 文件。不要上传安装后生成的镜像和 vendor overlay。

本分支关闭安装器自动替换源码，以免 ZIP 安装时失去 V50 补丁。
省略 -Repo/-Release 会使用上游默认 Release；这不会获得 V50 定制镜像。
通用 f50 启动身份继续保留，不直接改成 v50。

## 维护入口

- [更新和同步上游](UPDATE.zh-CN.md)
- [构建和发布](BUILD.zh-CN.md)
- [OpenClash](OPENCLASH.zh-CN.md)
- [恢复](RECOVERY.zh-CN.md)
- [本地验证记录](VALIDATION.zh-CN.md)

旧设备的私人备份、历史日志和一次性脚本保留在本机，不属于公开源码。
本分支没有修改手机分区布局，也没有为未验证硬件功能增加内核选项。
