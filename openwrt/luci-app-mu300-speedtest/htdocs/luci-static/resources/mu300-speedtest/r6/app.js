"use strict";

const preview = document.documentElement.dataset.mode !== "live";
const historyKey = "u30-speedtest:history:v1";
const unitKey = "u30-speedtest:unit:v1";
const languageKey = "u30-speedtest:language:v1";
const historyLimit = 10;
const tiers = [10, 20, 50, 100, 200, 300, 500, 1000, 2000];
const nodes = [
  {
    id: "mfcyun", name: "mfcyunName", detail: "mfcyunDetail",
    settings: {
      url_dl: "https://speedtest.mfcyun.com/backend/garbage.php?cors=true",
      url_ul: "https://speedtest.mfcyun.com/backend/empty.php?cors=true",
      url_ping: "https://speedtest.mfcyun.com/backend/empty.php?cors=true",
      garbagePhp_chunkSize: 4,
    },
  },
  {
    id: "shanghai", name: "shanghaiName", detail: "shanghaiDetail",
    settings: {
      url_dl: "https://speedtest1.online.sh.cn:8080/download?nocache=1&size=10485760",
      url_ul: "https://speedtest1.online.sh.cn:8080/upload?nocache=1",
      url_ping: "https://speedtest1.online.sh.cn:8080/hi?nocache=1",
    },
  },
  {
    id: "hong-kong", name: "hkName", detail: "hkDetail",
    settings: {
      url_dl: "https://www.speedtest.hk/speedtest/download.php?bytes=10485760",
      url_ul: "https://www.speedtest.hk/speedtest/upload.php",
      url_ping: "https://www.speedtest.hk/speedtest/ping.php",
    },
  },
  {
    id: "los-angeles", name: "losAngelesName", detail: "losAngelesDetail",
    settings: {
      url_dl: "https://la.speedtest.clouvider.net/backend/garbage.php?cors=true",
      url_ul: "https://la.speedtest.clouvider.net/backend/empty.php?cors=true",
      url_ping: "https://la.speedtest.clouvider.net/backend/empty.php?cors=true",
      garbagePhp_chunkSize: 4,
    },
  },
];

const copy = {
  zh: typeof speedtestZh === "object" ? speedtestZh : undefined,
  en: {
    brand: "SpeedTest",
    languageLabel: "Language", nodeLabel: "Test server", unitLabel: "Speed unit",
    resultsTitle: "Test results", download: "Download", upload: "Upload", ping: "Ping latency",
    equivalentLabel: "Equivalent broadband", equivalentPrefix: "About", equivalentSuffix: "broadband",
    uploadEquivalent: "Upload equivalent",
    publicEstimate: "Estimated from your internet measurements.",
    historyTitle: "Last 10 tests", historyLabel: "Test history", time: "Time", node: "Server",
    historyEmpty: "Your first result will appear here after the test.", historyCount: (count) => `${count} saved ${count === 1 ? "test" : "tests"}`,
    demo: "Sample data", localName: "U30 Air · Local", hkName: "Speedtest.hk · Hong Kong, China",
    hkDetail: "Measures internet speed to Hong Kong and uses internet data.",
    shanghaiName: "China Telecom · Shanghai", shanghaiDetail: "Measures internet speed to Shanghai and uses internet data.",
    mfcyunName: "MFCYun · Guangdong Mobile", mfcyunDetail: "Measures internet speed to MFCYun over Guangdong Mobile and uses internet data.",
    losAngelesName: "Clouvider · Los Angeles, US", losAngelesDetail: "Measures internet speed to Los Angeles, US, and uses internet data.",
    start: "Start test", stop: "Stop test", ready: "Ready", connecting: "Connecting to test server",
    testingPing: "Measuring latency", testingDownload: "Measuring download speed", testingUpload: "Measuring upload speed",
    complete: "Test complete", demoComplete: "Demo complete", unsaved: "Test complete. This browser could not save the result.",
    canceled: "Test stopped.", incomplete: "The test did not finish. Check your connection or choose another server.",
    unavailable: "The test engine could not start. Refresh the page and try again.",
    tier: (value) => `${value} Mbps`, lowTier: "Under 10 Mbps", highTier: "2000+ Mbps",
  },
};

const byId = (id) => document.getElementById(id);
const nodeSelect = byId("node-select");
const startButton = byId("start-test");
const status = byId("test-status");
const languageSelect = byId("language-select");
const unitButtons = [...byId("unit-select").querySelectorAll("[data-unit]")];
const samples = {
  shanghai: { download: 478.40, upload: 48.32, ping: 21.56 },
  mfcyun: { download: 256.40, upload: 38.16, ping: 29.18 },
  "hong-kong": { download: 285.64, upload: 42.68, ping: 31.22 },
  "los-angeles": { download: 84.72, upload: 15.36, ping: 171.45 },
};
const examples = [
  { ...samples.mfcyun, node: "mfcyun", time: Date.now() - 240000 },
  { ...samples.shanghai, node: "shanghai", time: Date.now() - 7200000 },
  { ...samples["hong-kong"], node: "hong-kong", time: Date.now() - 86400000 },
];

function readStorage(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function isResult(result) {
  return result && (result.node === "local" || nodes.some((node) => node.id === result.node))
    && Number.isFinite(result.time) && Number.isFinite(new Date(result.time).valueOf())
    && Number.isFinite(result.download) && result.download > 0
    && Number.isFinite(result.upload) && result.upload > 0
    && Number.isFinite(result.ping) && result.ping >= 0;
}

function readHistory() {
  if (preview) return examples;
  try {
    const records = JSON.parse(readStorage(historyKey));
    return Array.isArray(records) ? records.filter(isResult).slice(0, historyLimit) : [];
  } catch {
    return [];
  }
}

let history = readHistory();
let unit = !preview && readStorage(unitKey) === "Mbps" ? "Mbps" : "MB/s";
const savedLanguage = readStorage(languageKey);
let language = !copy.zh ? "en"
  : savedLanguage === "zh" || savedLanguage === "en" ? savedLanguage
  : /^zh\b/i.test(navigator.languages?.[0] || navigator.language || "zh") ? "zh" : "en";
let result;
let cancelTest = null;
let statusKey = "ready";
let dateFormat;

function setStatus(key) {
  statusKey = key;
  const text = copy[language][key];
  if (status.textContent !== text) status.textContent = text;
}

function formatSpeed(mbps) {
  if (!Number.isFinite(mbps)) return "";
  return (unit === "MB/s" ? mbps / 8 : mbps).toFixed(2);
}

function formatPing(ms) {
  return Number.isFinite(ms) ? String(Math.round(ms)) : "";
}

function estimateTier(mbps) {
  if (!Number.isFinite(mbps)) return "";
  if (mbps < tiers[0] / 2) return copy[language].lowTier;
  if (mbps > tiers[tiers.length - 1]) return copy[language].highTier;
  const nearest = tiers.reduce((best, tier) => (
    Math.abs(tier - mbps) < Math.abs(best - mbps) ? tier : best
  ));
  return copy[language].tier(nearest);
}

function renderReading(id, text) {
  const value = byId(id);
  value.textContent = text;
  value.parentElement.hidden = text === "";
}

function renderGauge(direction, mbps) {
  renderReading(`${direction}-value`, formatSpeed(mbps));
  // Use the reference meter's scale so low and high speeds remain legible on the same arc.
  const fill = Number.isFinite(mbps) && mbps > 0
    ? 100 * (1 - 1 / Math.pow(1.3, Math.sqrt(mbps))) : 0;
  byId(`${direction}-gauge`).setAttribute("stroke-dasharray", `${fill} 100`);
}

function renderResult() {
  renderReading("ping-value", formatPing(result?.ping));
  renderGauge("download", result?.download);
  renderGauge("upload", result?.upload);
  const completed = Number.isFinite(result?.time);
  byId("plan-main").hidden = !completed;
  byId("plan-detail").hidden = !completed;
  byId("plan-download").textContent = estimateTier(completed ? result.download : undefined);
  byId("plan-upload").textContent = estimateTier(completed ? result.upload : undefined);
}

function renderHistory() {
  const strings = copy[language];
  const labels = [strings.time, strings.node, strings.ping, strings.download, strings.upload, strings.equivalentLabel];
  byId("history-body").replaceChildren(...history.map((entry) => {
    const row = document.createElement("tr");
    row.setAttribute("role", "row");
    const node = nodes.find((item) => item.id === entry.node);
    const values = [dateFormat.format(entry.time), strings[node?.name ?? "localName"], `${formatPing(entry.ping)} ms`,
      `${formatSpeed(entry.download)} ${unit}`, `${formatSpeed(entry.upload)} ${unit}`,
      estimateTier(entry.download)];
    values.forEach((value, index) => {
      const cell = row.insertCell();
      cell.setAttribute("role", "cell");
      cell.dataset.label = labels[index];
      cell.textContent = value;
    });
    return row;
  }));
  byId("history-empty").hidden = history.length > 0;
  const count = byId("history-count");
  count.textContent = `${history.length} / ${historyLimit}`;
  count.setAttribute("aria-label", strings.historyCount(history.length));
}

function renderUnits() {
  for (const button of unitButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.unit === unit));
  }
  for (const label of document.querySelectorAll(".speed-unit")) label.textContent = unit;
  renderResult();
  renderHistory();
}

function renderNode() {
  const node = nodes.find((entry) => entry.id === nodeSelect.value);
  byId("node-description").textContent = copy[language][node.detail];
  byId("plan-detail").textContent = copy[language].publicEstimate;
}

function showNode() {
  const node = nodes.find((entry) => entry.id === nodeSelect.value);
  result = history.find((entry) => entry.node === node.id);
  setStatus("ready");
  renderNode();
  renderResult();
}

function renderLanguage() {
  const strings = copy[language];
  const locale = language === "zh" ? "zh-CN" : "en";
  document.documentElement.lang = locale;
  document.title = strings.brand;
  dateFormat = new Intl.DateTimeFormat(locale, {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  languageSelect.value = language;
  const chineseOption = byId("language-option-zh");
  chineseOption.textContent = copy.zh?.languageName || "Chinese";
  chineseOption.lang = copy.zh ? "zh-CN" : "en";
  chineseOption.disabled = !copy.zh;
  for (const label of document.querySelectorAll("[data-i18n]")) label.textContent = strings[label.dataset.i18n];
  for (const label of document.querySelectorAll("[data-i18n-label]")) {
    label.setAttribute("aria-label", strings[label.dataset.i18nLabel]);
  }
  nodes.forEach((node, index) => { nodeSelect.options[index].textContent = strings[node.name]; });
  const demoBadge = byId("mode-badge");
  demoBadge.hidden = !preview;
  demoBadge.textContent = strings.demo;
  startButton.textContent = strings[cancelTest ? "stop" : "start"];
  setStatus(statusKey);
  renderNode();
  renderUnits();
}

function runPreview(node, update, complete) {
  const demo = samples[node.id];
  let step = 0;
  const interval = setInterval(() => {
    step += 1;
    update({
      download: step > 2 ? demo.download * Math.min(1, (step - 2) / 4) : undefined,
      upload: step > 6 ? demo.upload * Math.min(1, (step - 6) / 4) : undefined,
      ping: demo.ping,
    }, step < 3 ? "testingPing" : step < 7 ? "testingDownload" : "testingUpload");
    if (step === 10) {
      clearInterval(interval);
      complete(demo);
    }
  }, 180);
  return () => clearInterval(interval);
}

function runLive(node, update, complete) {
  const engine = new window.Speedtest();
  engine.setParameter("telemetry_level", 0);
  engine.setParameter("test_order", "P_D_U");
  engine.setParameter("xhr_ignoreErrors", 0);
  engine.setParameter("time_dl_max", 10);
  engine.setParameter("time_ul_max", 10);
  engine.setParameter("time_auto", false);
  engine.setParameter("xhr_dlMultistream", 3);
  engine.setParameter("xhr_ulMultistream", 3);
  for (const [key, value] of Object.entries(node.settings)) engine.setParameter(key, value);
  let latest;
  let timer;
  function stopWorker() {
    clearTimeout(timer);
    clearInterval(engine.updater);
    engine.worker?.terminate();
  }
  function measuredValue(status) {
    const value = Number.parseFloat(status);
    return Number.isFinite(value) && value > 0 ? value : undefined;
  }
  engine.onupdate = (data) => {
    latest = {
      download: measuredValue(data.dlStatus),
      upload: measuredValue(data.ulStatus),
      ping: measuredValue(data.pingStatus),
    };
    const label = { 1: "testingDownload", 2: "testingPing", 3: "testingUpload" }[data.testState] || "connecting";
    update(latest, label);
  };
  engine.onend = (aborted) => {
    stopWorker();
    complete(aborted ? undefined : latest);
  };
  engine.start();
  engine.worker.onerror = () => {
    stopWorker();
    complete();
  };
  timer = setTimeout(engine.worker.onerror, 55000);
  return stopWorker;
}

function finishTest(node, values, failure) {
  cancelTest = null;
  startButton.textContent = copy[language].start;
  startButton.removeAttribute("aria-busy");
  nodeSelect.disabled = false;
  const completed = values && { ...values, node: node.id, time: Date.now() };
  if (isResult(completed)) {
    result = completed;
    history = [completed, ...history].slice(0, historyLimit);
    const saved = preview || writeStorage(historyKey, JSON.stringify(history));
    setStatus(preview ? "demoComplete" : saved ? "complete" : "unsaved");
    renderHistory();
  } else {
    if (failure === "canceled") {
      result = history.find((entry) => entry.node === node.id);
    }
    setStatus(failure || "incomplete");
  }
  renderResult();
}

startButton.addEventListener("click", () => {
  const node = nodes.find((entry) => entry.id === nodeSelect.value);
  if (cancelTest) {
    cancelTest();
    finishTest(node, undefined, "canceled");
    return;
  }
  result = undefined;
  renderResult();
  nodeSelect.disabled = true;
  startButton.textContent = copy[language].stop;
  startButton.setAttribute("aria-busy", "true");
  setStatus("connecting");
  const update = (values, label) => {
    result = values;
    renderResult();
    setStatus(label);
  };
  const complete = (values) => finishTest(node, values);
  try {
    cancelTest = preview ? runPreview(node, update, complete) : runLive(node, update, complete);
  } catch {
    finishTest(node, undefined, "unavailable");
  }
});

for (const button of unitButtons) {
  button.addEventListener("click", () => {
    unit = button.dataset.unit;
    if (!preview) writeStorage(unitKey, unit);
    renderUnits();
  });
}

languageSelect.addEventListener("change", () => {
  language = languageSelect.value;
  writeStorage(languageKey, language);
  renderLanguage();
});
nodeSelect.replaceChildren(...nodes.map((node) => new Option(copy[language][node.name], node.id)));
nodeSelect.value = nodes[0].id;
nodeSelect.addEventListener("change", showNode);
renderLanguage();
showNode();
