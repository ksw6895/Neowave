# NEoWave Engine – Phase 2 Completion & Local Web Service Guide

> This document extends the previous `NEoWave_coding_agent_guide.md`.
> Your tasks are:
> 1) **Complete** and harden the NEoWave engine as a reusable Python package, and  
> 2) Build a **local web service + HTML UI** to visualize price, swings, and scenarios on `localhost`.  
> No cloud deployment is required yet, but the code must be structured so that
> a future Vercel/Render deployment can reuse it with minimal changes.

---

## 0. Reference Materials

You must treat the following as the **authoritative specification**:

- `docs/01_neowave_overview_and_scope.md`  
- `docs/02_neowave_pattern_rules_table.md`  
- `docs/04_neowave_python_architecture.md`  
- `docs/05_neowave_validation_and_limitations.md`  
- `rules/neowave_rules.json`  
- Original theoretical PDF (conceptual reference only):  
  `/mnt/data/NEoWave 이론 정량화.pdf`

Also, the previous implementation guide:

- `docs/NEoWave_coding_agent_guide.md` (Phase 1 spec)

You must keep the behavior specified in those documents unless this guide explicitly extends or refines them.

---

## 1. Current State & High-Level Goals

### 1.1. Assumed Current State (Phase 1)

We assume that Phase 1 is already implemented with:

- A reusable **`neowave_core`** package containing:
  - Data fetching from FMP for `BTCUSD` on `1hour` timeframe
  - Swing (mono-wave) detection & normalization
  - Basic pattern detection:
    - 5-wave **Impulse**
    - 3-wave **Zigzag**
    - 3-wave **Flat**
  - Scenario generation for the above patterns
  - A CLI entrypoint that prints scenarios to the console

If any of the above is missing, you must first make Phase 1 conform exactly to the previous guide, then proceed with the tasks below.

### 1.2. Phase 2–3 Overall Goals

You will now:

1. **Complete and extend the engine**, focusing on:
   - Broader NEoWave pattern coverage (triangles, complex corrections, terminal impulses, etc.).
   - Multi-pattern scenario generation and scoring.
   - Configurability and performance for future research use.

2. **Add a local web service** that:
   - exposes a JSON API for OHLCV, swings, and scenarios, and
   - serves a simple HTML/JS page on `http://localhost:<port>/` where:
     - a candlestick chart is drawn, and
     - current scenarios are listed alongside the chart.

3. **Keep the architecture web-friendly** so that:
   - a future FastAPI/Render/Vercel setup can reuse `neowave_core` **without refactoring**.

---

## 2. Repository & Package Structure

Assume or refactor to the following structure (you may adapt minor details, but keep the separation of concerns):

```text
/
├─ README.md
├─ docs/
│  ├─ 01_neowave_overview_and_scope.md
│  ├─ 02_neowave_pattern_rules_table.md
│  ├─ 04_neowave_python_architecture.md
│  ├─ 05_neowave_validation_and_limitations.md
│  ├─ NEoWave_coding_agent_guide.md
│  └─ NEoWave_engine_and_web_guide.md   # this document
├─ rules/
│  └─ neowave_rules.json
├─ src/
│  ├─ neowave_core/
│  │  ├─ __init__.py
│  │  ├─ config.py
│  │  ├─ data_loader.py
│  │  ├─ swings.py
│  │  ├─ rules_loader.py
│  │  ├─ patterns/
│  │  │  ├─ __init__.py
│  │  │  ├─ impulse.py
│  │  │  ├─ zigzag.py
│  │  │  ├─ flat.py
│  │  │  ├─ triangle.py
│  │  │  ├─ complex_corrections.py
│  │  │  ├─ terminal_impulse.py
│  │  │  └─ common_types.py
│  │  ├─ scenarios.py
│  │  └─ cli.py
│  └─ neowave_web/
│     ├─ __init__.py
│     ├─ api.py             # FastAPI or similar
│     ├─ schemas.py         # Pydantic models for API
│     └─ static/
│        ├─ index.html
│        └─ app.js
└─ tests/
   ├─ test_swings.py
   ├─ test_impulse.py
   ├─ test_triangle.py
   ├─ test_complex_corrections.py
   ├─ test_scenarios.py
   └─ test_api.py
