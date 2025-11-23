const chartEl = document.getElementById("chart");
const scenariosEl = document.getElementById("scenarios");
const hintEl = document.getElementById("chart-hint");
let chart;
let candleSeries;

const fmtTime = (value) => new Date(value).toLocaleString();

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return res.json();
}

function renderChart(candles, swings) {
  if (!Array.isArray(candles)) {
    if (hintEl) hintEl.textContent = "No candle data available.";
    return;
  }
  const normalizedCandles = candles
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

  if (normalizedCandles.length === 0) {
    if (hintEl) hintEl.textContent = "Candle data empty after normalization.";
    return;
  }

  if (!window.LightweightCharts || typeof LightweightCharts.createChart !== "function") {
    if (hintEl) hintEl.textContent = "Chart library failed to load.";
    return;
  }

  const size = chartEl.getBoundingClientRect();
  let width = Math.max(320, Math.floor(size.width || 800));
  let height = Math.max(320, Math.floor(size.height || 520));
  chartEl.style.minHeight = `${height}px`;
  chartEl.style.width = "100%";
  if (!chart) {
    const chartApi = LightweightCharts.createChart(chartEl, {
      layout: {
        background: { color: "transparent" },
        textColor: "#c6d2ee",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      timeScale: { borderColor: "rgba(255,255,255,0.08)" },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });
    if (!chartApi || typeof chartApi.addCandlestickSeries !== "function") {
      if (hintEl) hintEl.textContent = "Chart API unavailable.";
      return;
    }
    chart = chartApi;
    chart.applyOptions({ width, height });
    candleSeries = chart.addCandlestickSeries({
      upColor: "#20e3b2",
      downColor: "#ff6b6b",
      borderUpColor: "#20e3b2",
      borderDownColor: "#ff6b6b",
      wickUpColor: "#20e3b2",
      wickDownColor: "#ff6b6b",
    });
  }
  if (!candleSeries) {
    candleSeries = typeof chart.addCandlestickSeries === "function" ? chart.addCandlestickSeries() : null;
  }
  if (!candleSeries) {
    if (hintEl) hintEl.textContent = "Failed to init candlestick series.";
    return;
  }

  const data = candles.map((c) => ({
    time: Math.floor(new Date(c.timestamp).getTime() / 1000),
    open: Number(c.open),
    high: Number(c.high),
    low: Number(c.low),
    close: Number(c.close),
  }));
  if (typeof candleSeries.setData === "function") {
    candleSeries.setData(normalizedCandles);
    if (chart && typeof chart.timeScale === "function") {
      chart.timeScale().fitContent();
    }
    // Ensure chart has a non-zero size (some layouts render with 0 width initially).
    const newSize = chartEl.getBoundingClientRect();
    const nextWidth = Math.max(320, Math.floor(newSize.width));
    const nextHeight = Math.max(260, Math.floor(newSize.height));
    if (nextWidth && nextHeight && chart && typeof chart.resize === "function") {
      chart.resize(nextWidth, nextHeight);
    }
    console.debug("Set chart data", normalizedCandles.length, {
      first: normalizedCandles[0],
      last: normalizedCandles[normalizedCandles.length - 1],
      size: { width: nextWidth, height: nextHeight },
    });
  } else {
    if (hintEl) hintEl.textContent = "Chart series not ready.";
    return;
  }

  const markers =
    Array.isArray(swings) && swings.length > 0
      ? swings.map((swing, idx) => {
          const time = Math.floor(new Date(swing.end_time).getTime() / 1000);
          const position = swing.direction === "up" ? "belowBar" : "aboveBar";
          const color = swing.direction === "up" ? "#20e3b2" : "#ff7b7b";
          return {
            time,
            position,
            color,
            shape: swing.direction === "up" ? "arrowUp" : "arrowDown",
            text: `S${idx + 1} ${swing.end_price.toFixed(2)}`,
          };
        })
      : [];
  if (typeof candleSeries.setMarkers === "function") {
    candleSeries.setMarkers(markers);
  }
}

function renderScenarios(scenarios) {
  if (!Array.isArray(scenarios) || scenarios.length === 0) {
    scenariosEl.innerHTML =
      '<div class="muted" style="padding: 12px;">No scenarios detected for the current swings.</div>';
    return;
  }
  const cards = scenarios
    .map((scenario) => {
      const invalidation = scenario.invalidation_levels || {};
      const invText =
        Object.keys(invalidation).length === 0
          ? "None specified"
          : Object.entries(invalidation)
              .map(([k, v]) => `${k}: ${Number(v).toFixed(2)}`)
              .join(" · ");
      return `
        <div class="scenario-card">
          <div class="scenario-head">
            <span>${scenario.pattern_type}</span>
            <span class="scenario-score">${(scenario.score * 100).toFixed(0)}%</span>
          </div>
          <div class="scenario-body">${scenario.textual_summary}</div>
          <div class="scenario-meta">Invalidation: ${invText}</div>
        </div>
      `;
    })
    .join("");
  scenariosEl.innerHTML = cards;
}

async function loadDashboard() {
  hintEl.textContent = "Loading latest data…";
  scenariosEl.innerHTML = "";
  try {
    const [ohlcv, swings, scenarios] = await Promise.all([
      fetchJson("/api/ohlcv?limit=200"),
      fetchJson("/api/swings?limit=200"),
      fetchJson("/api/scenarios?limit=200"),
    ]);
    renderChart(ohlcv && ohlcv.candles, swings && swings.swings);
    renderScenarios(scenarios.scenarios);
    const candleCount = ohlcv && Array.isArray(ohlcv.candles) ? ohlcv.candles.length : 0;
    const lastTs =
      candleCount > 0 ? fmtTime(ohlcv.candles[candleCount - 1].timestamp) : "n/a";
    hintEl.textContent = `Updated · ${lastTs} · ${candleCount} candles · ${
      swings && swings.count ? swings.count : 0
    } swings`;
    console.debug("Candles:", candleCount, "Swings:", swings && swings.count);
  } catch (err) {
    hintEl.textContent = `Failed to load data: ${err.message}`;
    scenariosEl.innerHTML = '<div class="muted" style="padding: 12px;">Refresh or check API key.</div>';
    console.error(err);
  }
}

document.getElementById("refresh").addEventListener("click", () => {
  loadDashboard();
});

window.addEventListener("resize", () => {
  if (!chart) return;
  const size = chartEl.getBoundingClientRect();
  if (size.width && size.height && typeof chart.resize === "function") {
    chart.resize(Math.floor(size.width), Math.floor(size.height));
  }
});

loadDashboard();
