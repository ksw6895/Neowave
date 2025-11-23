const state = {
  symbol: "BTCUSD",
  interval: "1hour",
  targetWaves: 40,
  retracePrice: 0.236,
  retraceTime: 0.2,
  similarity: 0.33,
  candles: [],
  monowaves: [],
  scenarios: [],
  chart: null,
  candleSeries: null,
  waveLine: null,
};

const elements = {
  chartContainer: document.getElementById("tv-chart"),
  scenarioList: document.getElementById("scenario-list"),
  statusText: document.getElementById("status-text"),
  monoCount: document.getElementById("mono-count"),
  scenarioCount: document.getElementById("scenario-count"),
  targetInput: document.getElementById("input-target"),
  targetLabel: document.getElementById("target-label"),
  symbolInput: document.getElementById("input-symbol"),
  intervalInput: document.getElementById("input-interval"),
  retracePriceInput: document.getElementById("input-retrace-price"),
  retraceTimeInput: document.getElementById("input-retrace-time"),
  similarityInput: document.getElementById("input-similarity"),
  refreshBtn: document.getElementById("btn-refresh"),
  tooltip: document.getElementById("rule-tooltip"),
};

function setStatus(text) {
  elements.statusText.textContent = text;
}

function toUnix(value) {
  return Math.floor(new Date(value).getTime() / 1000);
}

function buildChart() {
  if (!elements.chartContainer) return;
  state.chart = LightweightCharts.createChart(elements.chartContainer, {
    layout: { background: { color: "#0a0e16" }, textColor: "#dfe7ff" },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false },
    grid: {
      vertLines: { color: "rgba(255,255,255,0.04)" },
      horzLines: { color: "rgba(255,255,255,0.04)" },
    },
  });
  state.candleSeries = state.chart.addCandlestickSeries({
    upColor: "#38f0c4",
    downColor: "#ff7f50",
    borderDownColor: "#ff7f50",
    borderUpColor: "#38f0c4",
    wickDownColor: "#ff7f50",
    wickUpColor: "#38f0c4",
  });
  state.waveLine = state.chart.addLineSeries({
    color: "#26c9f7",
    lineWidth: 2,
  });
}

async function fetchJSON(url, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const target = qs ? `${url}?${qs}` : url;
  const res = await fetch(target);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadCandles() {
  const data = await fetchJSON("/api/ohlcv", {
    symbol: state.symbol,
    interval: state.interval,
    limit: 600,
  });
  state.candles = (data.candles || []).map((c) => ({
    time: toUnix(c.timestamp),
    open: Number(c.open),
    high: Number(c.high),
    low: Number(c.low),
    close: Number(c.close),
  }));
  if (state.candleSeries) state.candleSeries.setData(state.candles);
}

async function loadMonowaves() {
  const data = await fetchJSON("/api/monowaves", {
    symbol: state.symbol,
    interval: state.interval,
    retrace_price: state.retracePrice,
    retrace_time: state.retraceTime,
    similarity_threshold: state.similarity,
    limit: 600,
  });
  state.monowaves = data.monowaves || [];
  elements.monoCount.textContent = state.monowaves.length;
}

function renderMonowavePath() {
  if (!state.waveLine) return;
  const points = [];
  state.monowaves.forEach((mw) => {
    const start = toUnix(mw.start_time);
    const end = toUnix(mw.end_time);
    if (Number.isFinite(start) && Number.isFinite(end)) {
      points.push({ time: start, value: Number(mw.start_price) });
      points.push({ time: end, value: Number(mw.end_price) });
    }
  });
  // Deduplicate by time
  const unique = Array.from(new Map(points.map((p) => [p.time, p.value])).entries())
    .map(([time, value]) => ({ time, value }))
    .sort((a, b) => a.time - b.time);
  state.waveLine.setData(unique);
}

async function loadScenarios() {
  const data = await fetchJSON("/api/scenarios", {
    symbol: state.symbol,
    interval: state.interval,
    target_wave_count: state.targetWaves,
  });
  state.scenarios = data.scenarios || [];
  elements.scenarioCount.textContent = state.scenarios.length;
}

function renderScenarioCard(scenario) {
  const rootLabel = scenario.roots?.map((r) => r.pattern_type || "Monowave").join(" · ") || "n/a";
  const violations = scenario.invalidation_reasons || [];
  const card = document.createElement("div");
  card.className = "scenario-card";
  card.innerHTML = `
    <h3>${rootLabel}</h3>
    <small>Score ${scenario.global_score.toFixed(3)} · Level ${scenario.view_level}</small>
    <div style="margin-top:8px;">${(scenario.view_nodes || [])
      .slice(0, 6)
      .map((node) => `<span class="badge" data-wave="${node.id}">${node.pattern_type || "Monowave"} #${node.id}</span>`)
      .join("")}</div>
    <div class="validation">${violations.length ? `Invalidation: ${violations.join(", ")}` : "Top-down checks passed"}</div>
  `;
  card.querySelectorAll(".badge").forEach((el) => {
    el.addEventListener("click", () => showRuleXRay(Number(el.dataset.wave)));
  });
  return card;
}

function renderScenarios() {
  elements.scenarioList.innerHTML = "";
  if (!state.scenarios.length) {
    elements.scenarioList.innerHTML = "<div class='pill'>No scenarios found. Adjust thresholds.</div>";
    return;
  }
  state.scenarios.forEach((sc) => {
    elements.scenarioList.appendChild(renderScenarioCard(sc));
  });
}

async function showRuleXRay(waveId) {
  try {
    const data = await fetchJSON(`/api/waves/${waveId}/rules`, {
      symbol: state.symbol,
      interval: state.interval,
    });
    const tooltip = elements.tooltip;
    if (!tooltip) return;
    tooltip.style.display = "block";
    const validation = data.validation || {};
    const violations = (validation.violated_soft_rules || []).concat(validation.violated_hard_rules || []);
    tooltip.innerHTML = `
      <strong>Wave ${waveId}</strong><br/>
      ${data.pattern_type || "N/A"} ${data.pattern_subtype || ""}<br/>
      Soft score: ${validation.soft_score ?? "-"}<br/>
      ${violations.length ? `<div style="margin-top:6px;color:#ff7f50;">${violations.join("<br/>")}</div>` : "All core rules satisfied"}
    `;
    setTimeout(() => {
      tooltip.style.display = "none";
    }, 5000);
  } catch (err) {
    console.error(err);
  }
}

async function runAnalysis() {
  setStatus("분석 중...");
  state.symbol = elements.symbolInput.value || state.symbol;
  state.interval = elements.intervalInput.value || state.interval;
  state.targetWaves = Number(elements.targetInput.value) || state.targetWaves;
  state.retracePrice = Number(elements.retracePriceInput.value) || state.retracePrice;
  state.retraceTime = Number(elements.retraceTimeInput.value) || state.retraceTime;
  state.similarity = Number(elements.similarityInput.value) || state.similarity;

  await loadCandles();
  await loadMonowaves();
  await loadScenarios();

  renderMonowavePath();
  renderScenarios();
  setStatus("Updated");
}

function bindEvents() {
  elements.targetInput.addEventListener("input", (e) => {
    const value = Number(e.target.value);
    elements.targetLabel.textContent = value;
  });
  elements.refreshBtn.addEventListener("click", () => runAnalysis().catch(console.error));
}

async function init() {
  buildChart();
  bindEvents();
  await runAnalysis();
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch((err) => {
    console.error(err);
    setStatus("Error");
  });
});
