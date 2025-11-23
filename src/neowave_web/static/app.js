const chartContainer = document.getElementById("tv-chart");
const scenarioListEl = document.getElementById("scenario-list");
const lastUpdatedEl = document.getElementById("last-updated");
const scenarioCountEl = document.getElementById("scenario-count");
const chartSymbolEl = document.getElementById("chart-symbol");
const confluenceBadgeEl = document.getElementById("confluence-badge");
const timeframeButtons = document.querySelectorAll(".tf-btn");
const scaleButtons = document.querySelectorAll(".scale-pill");
const waveOverlayEl = document.getElementById("wave-overlay-layer");
const rangeToggleBtn = document.getElementById("btn-range-toggle");
const rangeResetBtn = document.getElementById("btn-range-reset");
const rangeSelectionEl = document.getElementById("range-selection");
const rangeHintEl = document.getElementById("range-hint");
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
  rangeMode: false,
  selectedRange: null, // {startTs, endTs}
  rangeAnchors: [],
  isCustomRange: false,
};

const rangeDrag = {
  active: false,
  startX: null,
  endX: null,
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

function parseAnchors(anchors) {
  return (anchors || []).map((anchor) => ({
    ...anchor,
    ts: toUnixSeconds(anchor.start_time),
  }));
}

function toUnixSeconds(value) {
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return null;
  return Math.floor(ts / 1000);
}

function chartTimeToTs(raw) {
  if (raw == null) return null;
  if (typeof raw === "number") return Math.floor(raw);
  if (typeof raw === "object" && "year" in raw && "month" in raw && "day" in raw) {
    const { year, month, day } = raw;
    const ts = new Date(Date.UTC(year, month - 1, day)).getTime();
    return Number.isFinite(ts) ? Math.floor(ts / 1000) : null;
  }
  const ts = new Date(raw).getTime();
  return Number.isFinite(ts) ? Math.floor(ts / 1000) : null;
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
      const labelText = `${child.label}${Number.isFinite(priceValue) ? ` ${priceValue.toFixed(2)}` : ""}`;
      const endVal = Number(child.end_price ?? child.start_price ?? 0);
      const startVal = Number(child.start_price ?? child.end_price ?? 0);
      if (Number.isFinite(priceValue) && Number.isFinite(endVal) && Number.isFinite(startVal)) {
        const upMove = endVal >= startVal;
        markers.push({
          time,
          value: priceValue,
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

function buildPathFromWaveTree(tree) {
  if (!tree) return [];
  const points = [];
  const startTime = toUnixSeconds(tree.start_time);
  const startPrice = Number(tree.start_price);
  if (Number.isFinite(startTime) && Number.isFinite(startPrice)) {
    points.push({ time: startTime, value: startPrice });
  }
  const endTime = toUnixSeconds(tree.end_time);
  const endPrice = Number(tree.end_price);
  const children = Array.isArray(tree.sub_waves) ? tree.sub_waves : Array.isArray(tree.children) ? tree.children : [];
  children.forEach((child) => {
    const t = markerTimeFromNode(child);
    const v = Number(child.end_price ?? child.price_high ?? child.price_low ?? child.start_price);
    if (Number.isFinite(t) && Number.isFinite(v)) {
      points.push({ time: t, value: v });
    }
  });
  if (Number.isFinite(endTime) && Number.isFinite(endPrice)) {
    points.push({ time: endTime, value: endPrice });
  }
  const dedup = new Map();
  points.forEach((p) => {
    dedup.set(p.time, p.value);
  });
  return Array.from(dedup.entries())
    .map(([time, value]) => ({ time, value }))
    .sort((a, b) => a.time - b.time);
}

function clearRangeOverlay() {
  if (!rangeSelectionEl) return;
  rangeSelectionEl.style.display = "none";
  rangeSelectionEl.style.width = "0px";
  rangeSelectionEl.style.left = "0px";
}

function renderSelectedRange() {
  if (!rangeSelectionEl || !chart || !state.selectedRange) {
    clearRangeOverlay();
    return;
  }
  const timeScale = chart.timeScale();
  const startCoord = timeScale.timeToCoordinate(state.selectedRange.startTs);
  const endCoord = timeScale.timeToCoordinate(state.selectedRange.endTs);
  if (startCoord == null || endCoord == null) {
    clearRangeOverlay();
    return;
  }
  const left = Math.min(startCoord, endCoord);
  const width = Math.abs(endCoord - startCoord);
  rangeSelectionEl.style.display = "block";
  rangeSelectionEl.style.left = `${left}px`;
  rangeSelectionEl.style.width = `${width}px`;
}

function buildPathFromSwings(swings, labels) {
  if (!Array.isArray(swings) || !swings.length) return [];
  const path = [];
  const first = swings[0];
  const startTime = Number(first.start_ts);
  const startPrice = Number(first.start_price);
  if (Number.isFinite(startTime) && Number.isFinite(startPrice)) {
    path.push({ time: startTime, value: startPrice });
  }
  swings.forEach((swing) => {
    const t = Number(swing.end_ts);
    const v = Number(swing.end_price);
    if (Number.isFinite(t) && Number.isFinite(v)) {
      path.push({ time: t, value: v });
    }
  });
  const dedup = new Map();
  path.forEach((p) => dedup.set(p.time, p.value));
  return Array.from(dedup.entries())
    .map(([time, value]) => ({ time, value }))
    .sort((a, b) => a.time - b.time);
}

function buildMarkersFromNodes(nodes) {
  if (!Array.isArray(nodes)) return [];
  return nodes
    .map((node, idx) => {
      const time = markerTimeFromNode(node);
      const priceValue = Number(node.end_price ?? node.start_price ?? node.price_high ?? node.price_low);
      if (!Number.isFinite(time) || !Number.isFinite(priceValue)) return null;
      const startVal = Number(node.start_price ?? node.end_price ?? priceValue);
      const upMove = Number.isFinite(startVal) ? priceValue >= startVal : true;
      return {
        time,
        value: priceValue,
        position: upMove ? "belowBar" : "aboveBar",
        color: ["#00f2ff", "#9b59b6", "#f39c12", "#1abc9c"][idx % 4],
        shape: "circle",
        text: `${node.label} ${priceValue.toFixed(2)}`,
      };
    })
    .filter(Boolean);
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
  const dedupByTime = new Map();
  filtered.forEach((p) => {
    // keep the last value for a given timestamp to avoid duplicates that break lightweight-charts
    dedupByTime.set(p.time, p.value);
  });
  const deduped = Array.from(dedupByTime.entries())
    .map(([time, value]) => ({ time, value }))
    .sort((a, b) => a.time - b.time);
  return deduped;
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

function setRangeMode(active) {
  state.rangeMode = active;
  if (rangeToggleBtn) rangeToggleBtn.classList.toggle("active", active);
  if (rangeHintEl) rangeHintEl.textContent = active ? "차트 드래그로 분석 범위 지정" : "드래그로 구간 지정";
  if (!active) {
    rangeDrag.active = false;
    clearRangeOverlay();
  }
}

function resetCustomRange() {
  state.isCustomRange = false;
  state.selectedRange = null;
  state.rangeAnchors = [];
  clearRangeOverlay();
}

function drawRangeDragOverlay() {
  if (!rangeSelectionEl || !chart || !rangeDrag.active) return;
  const left = Math.min(rangeDrag.startX, rangeDrag.endX);
  const width = Math.abs(rangeDrag.endX - rangeDrag.startX);
  rangeSelectionEl.style.display = "block";
  rangeSelectionEl.style.left = `${left}px`;
  rangeSelectionEl.style.width = `${width}px`;
}

function finalizeRangeSelection() {
  if (!chart) return;
  const timeScale = chart.timeScale();
  const startTime = chartTimeToTs(timeScale.coordinateToTime(rangeDrag.startX));
  const endTime = chartTimeToTs(timeScale.coordinateToTime(rangeDrag.endX));
  rangeDrag.active = false;
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || startTime === endTime) {
    clearRangeOverlay();
    return;
  }
  const startTs = Math.min(startTime, endTime);
  const endTs = Math.max(startTime, endTime);
  state.selectedRange = { startTs, endTs };
  renderSelectedRange();
  analyzeCustomRange(startTs, endTs);
}

function handleRangeMouseDown(event) {
  if (!state.rangeMode || !chart) return;
  rangeDrag.active = true;
  rangeDrag.startX = event.offsetX;
  rangeDrag.endX = event.offsetX;
  drawRangeDragOverlay();
}

function handleRangeMouseMove(event) {
  if (!rangeDrag.active) return;
  rangeDrag.endX = event.offsetX;
  drawRangeDragOverlay();
}

function handleRangeMouseUp() {
  if (!rangeDrag.active) return;
  finalizeRangeSelection();
}

function renderCandles() {
  if (!candleSeries) return;
  candleSeries.setData(state.candles);
  chart.timeScale().fitContent();
  renderSelectedRange();
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
  const anchorMarkers = (state.rangeAnchors || [])
    .map((anchor) => {
      if (!anchor || anchor.ts == null || anchor.start_price == null) return null;
      return {
        time: anchor.ts,
        position: "aboveBar",
        color: "#f1c40f",
        shape: "star",
        text: `A${anchor.idx}`,
      };
    })
    .filter(Boolean);
  candleSeries.setMarkers([...markers, ...anchorMarkers]);
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
  activePriceLines.forEach((line) => {
    if (line && typeof candleSeries.removePriceLine === "function") {
      try {
        candleSeries.removePriceLine(line);
      } catch (err) {
        console.warn("Failed to remove price line", err);
      }
    }
  });
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
    if (priceLine) activePriceLines.push(priceLine);
  });
}

function drawProjection(scenario) {
  if (!projectionSeries) return;
  if (!scenario) {
    projectionSeries.setData([]);
    return;
  }
  if (!scenario.details || !scenario.details.projection || !scenario.details.wave_tree) {
    projectionSeries.setData([]);
    return;
  }
  const proj = scenario.details.projection;
  const waveTree = scenario.details.wave_tree;
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
    const directChildren = Array.isArray(waveTree.sub_waves) ? waveTree.sub_waves : Array.isArray(waveTree.children) ? waveTree.children : [];
    let markers = buildMarkersFromNodes(directChildren);
    if (!markers.length) {
      markers = flattenWaveMarkers(waveTree);
    }
    const path = buildPathFromWaveTree(waveTree);
    if (waveSeries) waveSeries.setData(path);
    candleSeries.setMarkers(markers);
  } else {
    const [startIdx, endIdx] = scenario.swing_indices || [0, -1];
    const subset = state.swings.slice(startIdx, endIdx + 1);
    const labels = scenarioWaveLabels(subset.length);
    const labelsFromScenario = Array.isArray(scenario.wave_labels) && scenario.wave_labels.length === subset.length ? scenario.wave_labels : labels;
    const markers = subset
      .map((swing, idx) => ({
        time: swing.end_ts,
        value: Number(swing.end_price),
        position: swing.direction === "up" ? "belowBar" : "aboveBar",
        color: swing.direction === "up" ? "#00f2ff" : "#ff0055",
        shape: swing.direction === "up" ? "arrowUp" : "arrowDown",
        text: `${labelsFromScenario[idx] || labels[idx] || "S"} ${Number(swing.end_price).toFixed(2)}`,
      }))
      .filter((m) => Number.isFinite(m.time) && Number.isFinite(m.value));
    candleSeries.setMarkers(markers);
    const path = buildPathFromSwings(subset, labelsFromScenario);
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
    const anchorText = sc.anchor_idx != null ? `Anchor #${sc.anchor_idx}` : "Anchor auto";
    const violationText =
      Array.isArray(sc.violations) && sc.violations.length ? sc.violations.slice(0, 2).join(" · ") : "None";
    const hasEvidence = Array.isArray(sc.rule_evidence) && sc.rule_evidence.length > 0;
    card.innerHTML = `
      <div class="sc-header">
        <span class="sc-type">${sc.pattern_type.replace(/_/g, " ").toUpperCase()}</span>
        ${ongoing ? '<span class="sc-badge">LIVE</span>' : ""}
        <span class="sc-score ${scoreClass}">${(sc.score * 100).toFixed(0)}%</span>
      </div>
      <div class="sc-summary">${sc.textual_summary}</div>
      <div class="sc-meta">Path: ${activePath || "n/a"} | Swings ${sc.swing_indices?.[0]} ~ ${sc.swing_indices?.[1]} | Inv: ${invText}</div>
      <div class="sc-meta">Scale: ${sc.scale_id || state.scaleId} | ${anchorText} | Violations: ${violationText}</div>
      <div class="sc-meta">Wave Box: ${sc.wave_box ? "yes" : "no"} | Score W: ${(sc.weighted_score ?? sc.score).toFixed(2)}</div>
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

async function analyzeCustomRange(startTs, endTs) {
  setStatus("Custom range 분석 중...");
  try {
    const payload = {
      symbol: state.symbol,
      interval: state.interval,
      start_ts: startTs,
      end_ts: endTs,
      max_pivots: 5,
      max_scenarios: 5,
    };
    const res = await fetch("/api/analyze/custom-range", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail || "Request failed");
    }
    const data = await res.json();
    state.candles = parseCandles(data.candles || []);
    state.swings = parseSwings(data.swings || []);
    state.scenarios = data.scenarios || [];
    state.rangeAnchors = parseAnchors(data.anchor_candidates || []);
    state.isCustomRange = true;
    activeScenarioId = null;
    renderCandles();
    if (waveSeries) waveSeries.setData([]);
    if (projectionSeries) projectionSeries.setData([]);
    clearWaveBoxes();
    renderBaseSwingMarkers();
    renderScenariosList();
    renderSelectedRange();
    const candleCount = state.candles.length;
    const rangeText = `${fmtKSTime(startTs * 1000)} ~ ${fmtKSTime(endTs * 1000)}`;
    setStatus(`Custom range: ${rangeText} · ${candleCount} candles · ${state.swings.length} swings`);
  } catch (err) {
    console.error(err);
    setStatus(`Custom 분석 실패: ${err.message}`);
    state.selectedRange = null;
    state.rangeAnchors = [];
    clearRangeOverlay();
  }
}

async function loadData() {
  resetCustomRange();
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
    if (projectionSeries) projectionSeries.setData([]);
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
      setRangeMode(false);
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
      setRangeMode(false);
      loadData();
    });
  });
}

function setupRefresh() {
  const btn = document.getElementById("btn-refresh");
  if (btn) btn.addEventListener("click", () => {
    resetCustomRange();
    setRangeMode(false);
    loadData();
  });
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

function setupRangeSelection() {
  if (rangeToggleBtn) {
    rangeToggleBtn.addEventListener("click", () => setRangeMode(!state.rangeMode));
  }
  if (rangeResetBtn) {
    rangeResetBtn.addEventListener("click", () => {
      setRangeMode(false);
      resetCustomRange();
      loadData();
    });
  }
  if (chartContainer) {
    chartContainer.addEventListener("mousedown", handleRangeMouseDown);
    chartContainer.addEventListener("mousemove", handleRangeMouseMove);
  }
  document.addEventListener("mouseup", handleRangeMouseUp);
  document.addEventListener("mousemove", handleRangeMouseMove);
}

window.addEventListener("resize", () => {
  if (!chart) return;
  const size = chartContainer.getBoundingClientRect();
  chart.resize(Math.max(320, Math.floor(size.width)), Math.max(320, Math.floor(size.height)));
  renderSelectedRange();
});

initChart();
setupTimeframes();
setupScales();
setupRefresh();
setupEvidenceModal();
setupRangeSelection();
loadData();
