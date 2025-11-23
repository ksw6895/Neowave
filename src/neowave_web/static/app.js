const chartContainer = document.getElementById("tv-chart");
const scenarioListEl = document.getElementById("scenario-list");
const lastUpdatedEl = document.getElementById("last-updated");
const scenarioCountEl = document.getElementById("scenario-count");
const chartSymbolEl = document.getElementById("chart-symbol");
const confluenceBadgeEl = document.getElementById("confluence-badge");
const timeframeButtons = document.querySelectorAll(".tf-btn");
const scaleButtons = document.querySelectorAll(".scale-pill");
const waveOverlayEl = document.getElementById("wave-overlay-layer");
const evidenceModal = document.getElementById("evidence-modal");
const evidenceBody = document.getElementById("evidence-body");
const evidenceCloseBtn = document.getElementById("evidence-close");

let chart;
let candleSeries;
let projectionSeries;
let waveSeries;
let activePriceLines = [];
let activeWaveBoxes = [];
let activeScenarioId = null;

const state = {
  symbol: "BTCUSD",
  interval: "1hour",
  scaleId: "base",
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

function toUnixSeconds(value) {
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return null;
  return Math.floor(ts / 1000);
}

function markerTimeFromNode(node) {
  const parsed = toUnixSeconds(node.end_time);
  if (Number.isFinite(parsed)) return parsed;
  const idx = Number(node.end_idx ?? node.swing_end);
  if (Number.isInteger(idx) && state.candles[idx]) return state.candles[idx].time;
  return null;
}

function flattenWaveMarkers(tree, depth = 0, markers = []) {
  if (!tree) return markers;
  const children = Array.isArray(tree.sub_waves) ? tree.sub_waves : Array.isArray(tree.children) ? tree.children : [];
  children.forEach((child) => {
    const time = markerTimeFromNode(child);
    const priceValue = Number(child.end_price ?? child.start_price ?? child.price_high ?? child.price_low);
    if (time) {
      const labelText = `${child.label} ${Number.isFinite(priceValue) ? priceValue.toFixed(2) : ""}`;
      const endVal = Number(child.end_price ?? child.start_price ?? 0);
      const startVal = Number(child.start_price ?? child.end_price ?? 0);
      if (Number.isFinite(priceValue) && Number.isFinite(endVal) && Number.isFinite(startVal)) {
        const upMove = endVal >= startVal;
        markers.push({
          time,
          position: upMove ? "belowBar" : "aboveBar",
          color: ["#00f2ff", "#9b59b6", "#f39c12", "#1abc9c"][depth % 4],
          shape: "circle",
          text: labelText,
        });
      }
    }
    flattenWaveMarkers(child, depth + 1, markers);
  });
  return markers;
}

function buildWavePath(tree) {
  if (!tree) return [];
  const points = [];
  const pushPoint = (node) => {
    const time = markerTimeFromNode(node);
    const value = Number(node.end_price ?? node.price_high ?? node.price_low ?? node.start_price);
    if (!Number.isFinite(time) || !Number.isFinite(value)) return;
    points.push({ time, value });
  };
  const walk = (node) => {
    const children = Array.isArray(node.sub_waves) ? node.sub_waves : Array.isArray(node.children) ? node.children : [];
    if (!children.length) {
      pushPoint(node);
      return;
    }
    children.forEach((child) => walk(child));
  };
  walk(tree);
  const filtered = points.filter((p) => Number.isFinite(p.time) && Number.isFinite(p.value));
  filtered.sort((a, b) => a.time - b.time);
  return filtered;
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
  waveSeries = chart.addLineSeries({
    color: "#00d1b2",
    lineWidth: 2,
    lineStyle: LightweightCharts.LineStyle.Solid,
    priceLineVisible: false,
    crossHairMarkerVisible: false,
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

function clearWaveBoxes() {
  if (!waveOverlayEl) return;
  waveOverlayEl.innerHTML = "";
  activeWaveBoxes = [];
}

function drawWaveBoxForScenario(scenario) {
  if (!chart || !waveOverlayEl || !scenario?.wave_box) return;
  const box = scenario.wave_box;
  const timeScale = chart.timeScale();
  const priceScale = candleSeries && typeof candleSeries.priceScale === "function" ? candleSeries.priceScale() : chart.priceScale("right");
  if (!priceScale || typeof priceScale.priceToCoordinate !== "function") return;

  const t1 = Math.floor(new Date(box.time_start).getTime() / 1000);
  const t2 = Math.floor(new Date(box.time_end).getTime() / 1000);
  const x1 = timeScale.timeToCoordinate(t1);
  const x2 = timeScale.timeToCoordinate(t2);
  const y1 = priceScale.priceToCoordinate(box.price_high);
  const y2 = priceScale.priceToCoordinate(box.price_low);
  if (x1 == null || x2 == null || y1 == null || y2 == null) return;

  const left = Math.min(x1, x2);
  const width = Math.abs(x2 - x1);
  const top = Math.min(y1, y2);
  const height = Math.abs(y2 - y1);

  const div = document.createElement("div");
  div.className = "wave-box";
  div.style.left = `${left}px`;
  div.style.top = `${top}px`;
  div.style.width = `${width}px`;
  div.style.height = `${height}px`;

  const label = document.createElement("div");
  label.className = "wave-box-label";
  label.textContent = scenario.pattern_type.replace(/_/g, " ").toUpperCase();
  div.appendChild(label);

  waveOverlayEl.appendChild(div);
  activeWaveBoxes.push(div);
}

function scenarioWaveLabels(count) {
  if (count === 5) return ["1", "2", "3", "4", "5"];
  if (count === 3) return ["A", "B", "C"];
  return Array.from({ length: count }, (_, i) => `S${i + 1}`);
}

function renderEvidenceTable(evidence) {
  if (!evidenceBody) return;
  if (!Array.isArray(evidence) || evidence.length === 0) {
    evidenceBody.innerHTML = '<div style="color:#888; font-size:12px;">No rule evidence available.</div>';
    return;
  }
  const rows = evidence
    .map(
      (item) => `
      <tr>
        <td>${item.key}${item.description ? `<div style="color:#888; font-size:10px;">${item.description}</div>` : ""}</td>
        <td>${item.value ?? ""}</td>
        <td>${item.expected ?? ""}</td>
        <td>${item.penalty != null ? item.penalty.toFixed(2) : ""}</td>
        <td class="${item.passed ? "badge-pass" : "badge-fail"}">${item.passed ? "PASS" : "FAIL"}</td>
      </tr>`,
    )
    .join("");
  evidenceBody.innerHTML = `
    <table class="evidence-table">
      <thead>
        <tr>
          <th>Rule</th><th>Value</th><th>Expected</th><th>Penalty</th><th>Status</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function openEvidenceModal(evidence) {
  if (!evidenceModal) return;
  renderEvidenceTable(evidence);
  evidenceModal.classList.add("open");
}

function closeEvidenceModal() {
  if (!evidenceModal) return;
  evidenceModal.classList.remove("open");
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
  const proj = scenario.details && scenario.details.projection;
  const waveTree = scenario.details && scenario.details.wave_tree;
  if (!proj || !waveTree || waveTree.end_price == null || !waveTree.end_time) {
    projectionSeries.setData([]);
    return;
  }
  const lastCandle = state.candles.length ? state.candles[state.candles.length - 1] : null;
  const lastTimeRaw = toUnixSeconds(waveTree.end_time);
  const lastTime = Number.isFinite(lastTimeRaw) ? lastTimeRaw : lastCandle ? lastCandle.time : null;
  const targetTimeRaw = proj.target_time ? toUnixSeconds(proj.target_time) : null;
  const targetTime = Number.isFinite(targetTimeRaw) ? targetTimeRaw : Number.isFinite(lastTime) ? lastTime + 7200 : null;
  const startValue = Number(waveTree.end_price);
  const targetValue = Number(proj.target_price);
  if (!Number.isFinite(lastTime) || !Number.isFinite(targetTime) || !Number.isFinite(startValue) || !Number.isFinite(targetValue)) {
    projectionSeries.setData([]);
    return;
  }
  const projection = [
    { time: lastTime, value: startValue },
    { time: targetTime, value: targetValue },
  ];
  projectionSeries.setData(projection);
}

function highlightScenario(scenario) {
  clearPriceLines();
  clearWaveBoxes();
  drawProjection(scenario);

  if (!scenario || !Array.isArray(state.swings)) {
    if (waveSeries) waveSeries.setData([]);
    renderBaseSwingMarkers();
    return;
  }

  drawWaveBoxForScenario(scenario);

  const waveTree = scenario.details && scenario.details.wave_tree;
  const hasWavePrice = waveTree && waveTree.end_price != null && waveTree.end_time;
  if (waveTree && hasWavePrice) {
    const path = buildWavePath(waveTree);
    if (waveSeries) waveSeries.setData(path);
    const markers = flattenWaveMarkers(waveTree);
    candleSeries.setMarkers(markers);
  } else {
    const [startIdx, endIdx] = scenario.swing_indices || [0, -1];
    const subset = state.swings.slice(startIdx, endIdx + 1);
    const labels = scenarioWaveLabels(subset.length);
    const labelsFromScenario = Array.isArray(scenario.wave_labels) && scenario.wave_labels.length === subset.length ? scenario.wave_labels : labels;
    const markers = subset.map((swing, idx) => ({
      time: swing.end_ts,
      position: swing.direction === "up" ? "belowBar" : "aboveBar",
      color: swing.direction === "up" ? "#00f2ff" : "#ff0055",
      shape: swing.direction === "up" ? "arrowUp" : "arrowDown",
      text: `${labelsFromScenario[idx] || labels[idx] || "S"} ${Number(swing.end_price).toFixed(2)}`,
    }));
    candleSeries.setMarkers(markers);
    const path = subset
      .map((s) => ({ time: s.end_ts, value: Number(s.end_price) }))
      .filter((p) => Number.isFinite(p.time) && Number.isFinite(p.value))
      .sort((a, b) => a.time - b.time);
    if (waveSeries) waveSeries.setData(path);
  }
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
    const activePath = Array.isArray(sc.details?.active_path) ? sc.details.active_path.join(" → ") : "";
    const invalidation = sc.invalidation_levels || {};
    const invText =
      Object.keys(invalidation).length === 0
        ? "None"
        : Object.entries(invalidation)
            .map(([k, v]) => `${k}: ${Number(v).toFixed(2)}`)
            .join(" · ");
    const hasEvidence = Array.isArray(sc.rule_evidence) && sc.rule_evidence.length > 0;
    card.innerHTML = `
      <div class="sc-header">
        <span class="sc-type">${sc.pattern_type.replace(/_/g, " ").toUpperCase()}</span>
        ${ongoing ? '<span class="sc-badge">LIVE</span>' : ""}
        <span class="sc-score ${scoreClass}">${(sc.score * 100).toFixed(0)}%</span>
      </div>
      <div class="sc-summary">${sc.textual_summary}</div>
      <div class="sc-meta">Path: ${activePath || "n/a"} | Swings ${sc.swing_indices?.[0]} ~ ${sc.swing_indices?.[1]} | Inv: ${invText}</div>
      <div class="sc-meta">Scale: ${sc.scale_id || state.scaleId} | Wave Box: ${sc.wave_box ? "yes" : "no"}</div>
      ${hasEvidence ? `<div class="sc-evidence-toggle" data-idx="${idx}">Rule X-Ray ▶</div>` : ""}
    `;
    card.addEventListener("click", () => {
      activeScenarioId = idx;
      highlightScenario(sc);
      renderScenariosList();
    });
    if (hasEvidence) {
      const toggle = card.querySelector(".sc-evidence-toggle");
      toggle.addEventListener("click", (e) => {
        e.stopPropagation();
        openEvidenceModal(sc.rule_evidence);
      });
    }
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
    const baseQuery = `symbol=${state.symbol}&interval=${state.interval}&limit=500`;
    const swingsQuery = `${baseQuery}&scale_id=${state.scaleId}`;
    const [ohlcv, swingsResp, scenariosResp] = await Promise.all([
      fetchJson(`/api/ohlcv?${baseQuery}`),
      fetchJson(`/api/swings?${swingsQuery}`),
      fetchJson(`/api/scenarios?${swingsQuery}`),
    ]);
    state.candles = parseCandles(ohlcv.candles);
    state.swings = parseSwings(swingsResp.swings);
    state.scenarios = scenariosResp.scenarios || [];

    renderCandles();
    if (waveSeries) waveSeries.setData([]);
    clearWaveBoxes();
    renderBaseSwingMarkers();
    renderScenariosList();

    const candleCount = state.candles.length;
    const lastTs = candleCount ? fmtKSTime(state.candles[candleCount - 1].time * 1000) : "n/a";
    setStatus(`Last Scan: ${lastTs} · ${candleCount} candles · ${state.swings.length} swings · scale ${state.scaleId}`);
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

function setupScales() {
  scaleButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      scaleButtons.forEach((b) => b.classList.remove("active"));
      e.currentTarget.classList.add("active");
      state.scaleId = e.currentTarget.dataset.scale;
      activeScenarioId = null;
      loadData();
    });
  });
}

function setupRefresh() {
  const btn = document.getElementById("btn-refresh");
  if (btn) btn.addEventListener("click", () => loadData());
}

function setupEvidenceModal() {
  if (evidenceCloseBtn) {
    evidenceCloseBtn.addEventListener("click", closeEvidenceModal);
  }
  if (evidenceModal) {
    evidenceModal.addEventListener("click", (e) => {
      if (e.target === evidenceModal) closeEvidenceModal();
    });
  }
}

window.addEventListener("resize", () => {
  if (!chart) return;
  const size = chartContainer.getBoundingClientRect();
  chart.resize(Math.max(320, Math.floor(size.width)), Math.max(320, Math.floor(size.height)));
});

initChart();
setupTimeframes();
setupScales();
setupRefresh();
setupEvidenceModal();
loadData();
