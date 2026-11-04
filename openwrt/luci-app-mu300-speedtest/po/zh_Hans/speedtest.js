"use strict";

const speedtestZh = {
  brand: "SpeedTest", languageName: "中文",
  languageLabel: "语言", nodeLabel: "测速节点", unitLabel: "速率单位",
  resultsTitle: "测速结果", download: "下载", upload: "上传", ping: "Ping 延迟",
  equivalentLabel: "等效宽带", equivalentPrefix: "约", equivalentSuffix: "宽带",
  uploadEquivalent: "上传等效",
  publicEstimate: "按公网实测速率估算。",
  historyTitle: "最近 10 次测速", historyLabel: "测速历史", time: "时间", node: "节点",
  historyEmpty: "完成第一次测速后，结果会显示在这里。", historyCount: (count) => `已记录 ${count} 次`,
  demo: "演示数据", localName: "U30 Air · 本地", hkName: "Speedtest.hk · 中国香港",
  hkDetail: "测量到中国香港节点的公网速度，会使用上网流量。",
  shanghaiName: "上海电信 · 上海", shanghaiDetail: "测量到上海电信节点的公网速度，会使用上网流量。",
  mfcyunName: "梦飞云 · 广东移动", mfcyunDetail: "测量到梦飞云广东移动节点的公网速度，会使用上网流量。",
  losAngelesName: "Clouvider · 美国洛杉矶", losAngelesDetail: "测量到美国洛杉矶节点的公网速度，会使用上网流量。",
  start: "开始测速", stop: "停止测速", ready: "准备就绪", connecting: "正在连接测速节点",
  testingPing: "正在测量延迟", testingDownload: "正在测量下载速度", testingUpload: "正在测量上传速度",
  complete: "测速完成", demoComplete: "演示完成", unsaved: "测速完成。此浏览器无法保存历史。",
  canceled: "已停止测速。", incomplete: "本次未取得完整结果，请检查网络或切换节点。",
  unavailable: "测速模块未启动，请刷新页面后重试。",
  tier: (value) => `${value}M`, lowTier: "低于 10M", highTier: "2000M+",
};
