<p align="right">
  English | <a href="README.md">中文</a>
</p>

<p align="center">

![Version](https://img.shields.io/badge/version-1.3.0-blue?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10+-yellow?style=flat-square)
![Tests](https://img.shields.io/badge/tests-390%20passed-brightgreen?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

<h1 align="center">⏳ ChronoVisor</h1>
  <p align="center"><strong>Universal Causal Analysis Engine</strong></p>
  <p align="center">
    <em>Discover causal relationships from event sequences, build causal networks, perform counterfactual reasoning</em>
  </p>
</p>

---

## What is this

ChronoVisor is a **universal causal analysis engine**. Give it a sequence of time-ordered events, and it can automatically answer:

- **Which events have causal relationships?** — Causal chain mining
- **How did A influence C through B?** — Multi-hop reasoning (A→B→C)
- **If A hadn't happened, would B still occur?** — Counterfactual analysis (Pearl do-calculus)
- **What domain does this event belong to? How long is the transmission?** — 12-domain auto-classification + time prediction
- **New event arrived, how to avoid re-analyzing everything?** — Incremental updates

It's not tied to any specific domain. Finance, tech, policy, society, healthcare, gaming — if there are time-ordered events, it can analyze them.

---

## Capabilities

### 🔗 Causal Chain Mining: Find who caused what

Give ChronoVisor a set of events, and it identifies causal relationships using a 4-layer funnel:

```
Layer 1: Temporal filter — A must precede B
Layer 2: Time window — Eliminate pairs exceeding domain max transmission time
Layer 3: Graph routing — 10,967 concept pairs for fast-lane matching
Layer 4: LLM analysis — Transmission mechanism + similar cases
```

### ⛓️ Multi-hop Reasoning: A affects C through B

Not just A→B, but A→B→C chain transmission with auto-decaying confidence (×0.7 per hop).

### 🔬 Counterfactual Analysis: What if A didn't happen?

Two methods:

- **Simplified**: Estimates based on alternative causal paths
- **do-calculus (Pearl graph surgery)**: Cuts all incoming edges to A (eliminating confounders), then recomputes P(B). Detects when observed correlation is partially caused by confounders.

### 🌍 12-Domain Auto-Classification

Based on Wikipedia taxonomy with ~500 keywords. Each domain has different transmission characteristics:

| Domain | Peak | Domain | Peak |
|--------|------|--------|------|
| Tech & Semiconductors | 60d | Commodities & Energy | 14d |
| Finance & Capital Markets | 7d | Crypto & Blockchain | 3d |
| Macroeconomics | 90d | Gaming & Entertainment | 90d |
| Enterprise & Organizations | 180d | Society & Culture | 365d |
| Policy & Governance | 365d | International Relations | 30d |
| Environment & Climate | 3650d | Healthcare | 90d |

### 📈 Incremental Updates

1000 old events + 1 new event = 1000 analyses, not 500,000. 500x faster.

### 🧩 Plugin System

Core plugins (loaded at startup): PEST / SWOT / Cycle identification
Extension plugins (loaded on demand): Anomaly detection / Trend extrapolation / Correlation analysis / Scenario analysis

### 💾 Persistent Storage

SQLite with multi-project isolation, time range + tag filtering.

### 🌐 Web Visualization Console

Three.js 3D force-directed causal network visualization with AI-powered research.

---

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Create engine | 53ms | Lazy loading |
| First score() | 363ms | Loads 10,967 concept pairs + builds index |
| Subsequent score() | **0.13ms** | Inverted index hit, 30x speedup |
| 50-event causal discovery | 43ms | 1,225 event pairs |
| 100-event full network | 164ms | With multi-hop reasoning |
| do-calculus counterfactual | 0.2ms | Per analysis |
| SQLite read/write | 3ms | 100 events |

---

## Quick Start

```python
from src import TimelineBase, AnalyzerEngine, ReportGenerator
from src.core.counterfactual import CounterfactualAnalyzer
from datetime import datetime

# 1. Build timeline
timeline = TimelineBase(title="Semiconductor Cycle Research")
events = [
    ("ChatGPT goes viral", "2024-01-01", ["AI", "demand"]),
    ("NVIDIA H100 supply shortage", "2024-02-01", ["NVIDIA", "GPU"]),
    ("Memory chip prices rise", "2024-03-01", ["memory", "price"]),
]
for summary, date, tags in events:
    timeline.add_event(
        timestamp=datetime.strptime(date, "%Y-%m-%d"),
        data={}, source="source", tags=tags, summary=summary,
    )

# 2. Causal analysis
engine = AnalyzerEngine(timeline)
network = engine.build_causal_network(min_confidence=0.2, multihop=True)

# 3. Counterfactual analysis
cf = CounterfactualAnalyzer(network)
result = cf.analyze(cause_id, effect_id, method="do_calculus")

# 4. Generate report
gen = ReportGenerator(timeline)
report = gen.generate(title="Research Report")
```

---

## Architecture

```
src/
├── core/                    Core engine (13 modules, ~5500 lines)
│   ├── timeline.py          Timeline + 3 chapter detection algorithms
│   ├── analyzer.py          Causal network + multi-hop + incremental
│   ├── causal_graph.py      Graph (79 builtin + 10,882 ConceptNet, lazy + indexed)
│   ├── causal_lag.py        12-domain classifier + gamma prediction + Bayesian
│   ├── causal_mining.py     4-layer funnel + LLM batch concurrency
│   ├── counterfactual.py    Pearl do-calculus + simplified
│   ├── llm_config.py        LLM config center (multi-profile + rate limiting)
│   ├── storage.py           SQLite persistent storage
│   ├── report_generator.py  Report generation + plugin integration
│   └── semantic.py          Semantic classifier
├── plugins/                 Core plugins (3, loaded at startup)
│   ├── pest.py / swot.py / cycle.py
└── extras/                  Extension modules (lazy-loaded)
    ├── anomaly.py / trend.py / correlation.py / scenario.py
```

---

## Tests

```bash
python3 -m pytest tests/ -q
# 390 passed in 2.6s
```

---

## Install

```bash
git clone https://github.com/Miku-cy/industry-research-skill.git
cd industry-research-skill
```

Requires: Python 3.10+. No mandatory external dependencies (LLM features are optional).

---

## License

MIT
