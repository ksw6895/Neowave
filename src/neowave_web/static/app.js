const chartContainer = document.getElementById("tv-chart");
const scenarioListEl = document.getElementById("scenario-list");
const lastUpdatedEl = document.getElementById("last-updated");
const scenarioCountEl = document.getElementById("scenario-count");
const chartSymbolEl = document.getElementById("chart-symbol");
const confluenceBadgeEl = document.getElementById("confluence-badge");
const timeframeButtons = document.querySelectorAll(".tf-btn");

let chart;
let candleSeries;
let projectionSeries;
let activePriceLines = [];
let activeScenarioId = null;

const state = {
  symbol: "BTCUSD",
  interval: "1hour",
  candles: [],
  swings: [],
  scenarios: [],
};

const fmtKSTime = (value) => new Date(value).toLocaleString();

function parseCandles(candles) {
  return (candles || [])
    .map((c) => ({
      time: Math.floor(new Date(c.timestamp).getTime() / 1000),
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
    }))
    .filter(
      (c) =>
        Number.isFinite(c.time) &&
        Number.isFinite(c.open) &&
        Number.isFinite(c.high) &&
        Number.isFinite(c.low) &&
        Number.isFinite(c.close),
    )
    .sort((a, b) => a.time - b.time);
}

function parseSwings(swings) {
  return (swings || []).map((swing) => ({
    ...swing,
    end_ts: Math.floor(new Date(swing.end_time).getTime() / 1000),
    start_ts: Math.floor(new Date(swing.start_time).getTime() / 1000),
  }));
}

function initChart() {
  if (!window.LightweightCharts || typeof LightweightCharts.createChart !== "function") {
    console.error("LightweightCharts not available");
    return;
  }
  const size = chartContainer.getBoundingClientRect();
  const width = Math.max(320, Math.floor(size.width || 800));
  const height = Math.max(320, Math.floor(size.height || 520));
  chart = LightweightCharts.createChart(chartContainer, {
    width,
    height,
    layout: {
      background: { color: "#050505" },
      textColor: "#808080",
    },
    grid: {
      vertLines: { color: "rgba(255,255,255,0.03)" },
      horzLines: { color: "rgba(255,255,255,0.03)" },
    },
    timeScale: {
      borderColor: "rgba(255, 255, 255, 0.1)",
      timeVisible: true,
    },
    rightPriceScale: {
      borderColor: "rgba(255, 255, 255, 0.1)",
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#00f2ff",
    downColor: "#ff0055",
    borderUpColor: "#00f2ff",
    borderDownColor: "#ff0055",
    wickUpColor: "#00f2ff",
    wickDownColor: "#ff0055",
  });
  projectionSeries = chart.addLineSeries({
    color: "rgba(0, 242, 255, 0.8)",
    lineWidth: 2,
    lineStyle: LightweightCharts.LineStyle.Dashed,
  });
}

function setStatus(text) {
  if (lastUpdatedEl) lastUpdatedEl.textContent = text;
}

function renderCandles() {
  if (!candleSeries) return;
  candleSeries.setData(state.candles);
  chart.timeScale().fitContent();
}

function renderBaseSwingMarkers() {
  if (!candleSeries) return;
  if (!Array.isArray(state.swings) || state.swings.length === 0) {
    candleSeries.setMarkers([]);
    return;
  }
  const markers = state.swings.map((swing, idx) => ({
    time: swing.end_ts,
    position: swing.direction === "up" ? "belowBar" : "aboveBar",
    color: swing.direction === "up" ? "#00f2ff" : "#ff0055",
    shape: swing.direction === "up" ? "arrowUp" : "arrowDown",
    text: `S${idx + 1}`,
  }));
  candleSeries.setMarkers(markers);
}

function scenarioWaveLabels(count) {
  if (count === 5) return ["1", "2", "3", "4", "5"];
  if (count === 3) return ["A", "B", "C"];
  return Array.from({ length: count }, (_, i) => `S${i + 1}`);
}

function clearPriceLines() {
  if (!candleSeries) return;
  activePriceLines.forEach((line) => candleSeries.removePriceLine(line));
  activePriceLines = [];
}

function drawInvalidations(levels) {
  if (!candleSeries || !levels) return;
  Object.entries(levels).forEach(([label, price]) => {
    if (!Number.isFinite(Number(price))) return;
    const priceLine = candleSeries.createPriceLine({
      price: Number(price),
      color: label.includes("below") ? "#ff0055" : "#00f2ff",
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dotted,
      axisLabelVisible: true,
      title: `Invalidation: ${label}`,
    });
    activePriceLines.push(priceLine);
  });
}

function drawProjection(scenario) {
  if (!projectionSeries) return;
  if (!scenario) {
    projectionSeries.setData([]);
    return;
  }
  const swings = state.swings;
  if (!swings || !swings.length) {
    projectionSeries.setData([]);
    return;
  }
  const [startIdx, endIdx] = scenario.swing_indices || [0, -1];
  const targetSwing = swings[endIdx] || swings[swings.length - 1];
  if (!targetSwing) return;

  const lastPrice = Number(targetSwing.end_price);
  const lastTime = targetSwing.end_ts;
  const direction =
    (scenario.details && scenario.details.direction === "down") ||
    scenario.pattern_type.includes("down")
      ? -1
      : 1;
  const waveLengths = scenario.details && Array.isArray(scenario.details.wave_lengths) ? scenario.details.wave_lengths : [];
  const avgSwing = waveLengths.length
    ? waveLengths.reduce((sum, v) => sum + Math.abs(v || 0), 0) / waveLengths.length
    : Math.abs(targetSwing.end_price - targetSwing.start_price);
  const stepPrice = Math.max(avgSwing * 0.4, (Math.abs(lastPrice) || 1) * 0.002);

  const candles = state.candles;
  const stepTime =
    candles.length >= 2 ? (candles[candles.length - 1].time - candles[candles.length - 2].time) : 3600;

  const projection = [
    { time: lastTime, value: lastPrice },
    { time: lastTime + stepTime * 2, value: lastPrice + direction * stepPrice },
  ];
  projectionSeries.setData(projection);
}

function highlightScenario(scenario) {
  clearPriceLines();
  drawProjection(scenario);

  if (!scenario || !Array.isArray(state.swings)) {
    renderBaseSwingMarkers();
    return;
  }

  const [startIdx, endIdx] = scenario.swing_indices || [0, -1];
  const subset = state.swings.slice(startIdx, endIdx + 1);
  if (!subset.length) {
    renderBaseSwingMarkers();
    return;
  }
  const labels = scenarioWaveLabels(subset.length);
  const markers = subset.map((swing, idx) => ({
    time: swing.end_ts,
    position: swing.direction === "up" ? "belowBar" : "aboveBar",
    color: swing.direction === "up" ? "#00f2ff" : "#ff0055",
    shape: swing.direction === "up" ? "arrowUp" : "arrowDown",
    text: `${labels[idx] || "S"} ${Number(swing.end_price).toFixed(2)}`,
  }));
  candleSeries.setMarkers(markers);
  drawInvalidations(scenario.invalidation_levels);
}

function renderScenariosList() {
  scenarioListEl.innerHTML = "";
  scenarioCountEl.textContent = state.scenarios.length;
  if (!state.scenarios.length) {
    scenarioListEl.innerHTML = '<div style="padding:20px; color:#555; text-align:center;">No patterns detected.</div>';
    confluenceBadgeEl.style.display = "none";
    return;
  }

  confluenceBadgeEl.style.display = state.scenarios.some((s) => s.score >= 0.85) ? "inline" : "none";

  state.scenarios.forEach((sc, idx) => {
    const card = document.createElement("div");
    const ongoing = Boolean(sc.in_progress);
    card.className = `scenario-card${activeScenarioId === idx ? " active" : ""}${ongoing ? " ongoing" : ""}`;
    const scoreClass = sc.score > 0.8 ? "high" : "";
    const invalidation = sc.invalidation_levels || {};
    const invText =
      Object.keys(invalidation).length === 0
        ? "None"
        : Object.entries(invalidation)
            .map(([k, v]) => `${k}: ${Number(v).toFixed(2)}`)
            .join(" · ");
    card.innerHTML = `
      <div class="sc-header">
        <span class="sc-type">${sc.pattern_type.replace(/_/g, " ").toUpperCase()}</span>
        ${ongoing ? '<span class="sc-badge">LIVE</span>' : ""}
        <span class="sc-score ${scoreClass}">${(sc.score * 100).toFixed(0)}%</span>
      </div>
      <div class="sc-summary">${sc.textual_summary}</div>
      <div class="sc-meta">Swings ${sc.swing_indices?.[0]} ~ ${sc.swing_indices?.[1]} | Inv: ${invText}</div>
    `;
    card.addEventListener("click", () => {
      activeScenarioId = idx;
      highlightScenario(sc);
      renderScenariosList();
    });
    scenarioListEl.appendChild(card);
  });
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return res.json();
}

async function loadData() {
  setStatus("Loading...");
  try {
    const query = `symbol=${state.symbol}&interval=${state.interval}&limit=500`;
    const [ohlcv, swingsResp, scenariosResp] = await Promise.all([
      fetchJson(`/api/ohlcv?${query}`),
      fetchJson(`/api/swings?${query}`),
      fetchJson(`/api/scenarios?${query}`),
    ]);
    state.candles = parseCandles(ohlcv.candles);
    state.swings = parseSwings(swingsResp.swings);
    state.scenarios = scenariosResp.scenarios || [];

    renderCandles();
    renderBaseSwingMarkers();
    renderScenariosList();

    const candleCount = state.candles.length;
    const lastTs = candleCount ? fmtKSTime(state.candles[candleCount - 1].time * 1000) : "n/a";
    setStatus(`Last Scan: ${lastTs} · ${candleCount} candles · ${state.swings.length} swings`);
    chartSymbolEl.textContent = `${state.symbol} / ${state.interval.toUpperCase()}`;
  } catch (err) {
    console.error(err);
    setStatus(`Load failed: ${err.message}`);
    scenarioListEl.innerHTML = '<div style="padding:20px; color:#c0392b;">데이터 로드 실패</div>';
  }
}

function setupTimeframes() {
  timeframeButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      timeframeButtons.forEach((b) => b.classList.remove("active"));
      e.currentTarget.classList.add("active");
      state.interval = e.currentTarget.dataset.tf;
      activeScenarioId = null;
      loadData();
    });
  });
}

function setupRefresh() {
  const btn = document.getElementById("btn-refresh");
  if (btn) btn.addEventListener("click", () => loadData());
}

window.addEventListener("resize", () => {
  if (!chart) return;
  const size = chartContainer.getBoundingClientRect();
  chart.resize(Math.max(320, Math.floor(size.width)), Math.max(320, Math.floor(size.height)));
});

initChart();
setupTimeframes();
setupRefresh();
loadData();
