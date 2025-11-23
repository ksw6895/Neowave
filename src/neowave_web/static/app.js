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
  if (!chart) {
    chart = LightweightCharts.createChart(chartEl, {
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
    candleSeries = chart.addCandlestickSeries({
      upColor: "#20e3b2",
      downColor: "#ff6b6b",
      borderUpColor: "#20e3b2",
      borderDownColor: "#ff6b6b",
      wickUpColor: "#20e3b2",
      wickDownColor: "#ff6b6b",
    });
  }

  const data = candles.map((c) => ({
    time: Math.floor(new Date(c.timestamp).getTime() / 1000),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
  candleSeries.setData(data);

  const markers = swings.map((swing, idx) => {
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
  });
  candleSeries.setMarkers(markers);
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
    renderChart(ohlcv.candles, swings.swings);
    renderScenarios(scenarios.scenarios);
    const lastTs =
      ohlcv.candles.length > 0
        ? fmtTime(ohlcv.candles[ohlcv.candles.length - 1].timestamp)
        : "n/a";
    hintEl.textContent = `Updated · ${lastTs} · ${ohlcv.count} candles · ${swings.count} swings`;
  } catch (err) {
    hintEl.textContent = `Failed to load data: ${err.message}`;
    scenariosEl.innerHTML = '<div class="muted" style="padding: 12px;">Refresh or check API key.</div>';
    console.error(err);
  }
}

document.getElementById("refresh").addEventListener("click", () => {
  loadDashboard();
});

loadDashboard();
