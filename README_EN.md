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
    <em>Causal chain mining · Multi-hop reasoning · do-calculus counterfactual · 12-domain classification · Incremental updates</em>
  </p>
</p>

---

## What is ChronoVisor

ChronoVisor is a **universal causal analysis engine** that discovers causal relationships from event sequences in any domain, builds causal networks, and performs counterfactual reasoning.

Use cases: industry research, policy analysis, technology trends, social phenomena, historical events, financial market causal reasoning.

---

## Core Capabilities

### 🔗 Causal Chain Mining (4-Layer Funnel)

```
Layer 1: Temporal filter — A must precede B
Layer 2: Time window — Eliminate pairs exceeding domain max transmission time
Layer 3: Graph routing — Known concept pairs → fast lane; unknown → LLM slow lane
Layer 4: LLM analysis — Transmission mechanism + similar cases
```

### ⛓️ Multi-hop Reasoning

Automatically discovers A→B→C chain transmission. Confidence auto-decays (×0.7 per hop), cycle detection, max 3 hops.

### 🔬 Counterfactual Analysis (Pearl do-calculus)

- **Graph surgery**: do(¬A) cuts all incoming edges to A, eliminating confounders
- **Truncated factorization**: Only computes probabilities from non-A independent upstream
- **Confounding detection**: Alerts when P(B|A) vs P(B|do(¬A)) differ significantly

### 🌍 12-Domain Classification

Based on Wikipedia taxonomy, ~500 keywords:

| Domain | Peak | Domain | Peak |
|--------|------|--------|------|
| Tech & Semiconductors | 60d | Commodities & Energy | 14d |
| Finance & Capital Markets | 7d | Crypto & Blockchain | 3d |
| Macroeconomics | 90d | Gaming & Entertainment | 90d |
| Enterprise & Organizations | 180d | Society & Culture | 365d |
| Policy & Governance | 365d | International Relations | 30d |
| Environment & Climate | 3650d | Healthcare | 90d |

### 📈 Incremental Updates

Only analyzes new event pairs when new events are added. 1000 old + 1 new ≈ 1000 analyses, not 500,000.

### 🧩 Plugin System

Core plugins (loaded at startup): PEST / SWOT / Cycle
Extension plugins (loaded on demand): Anomaly / Trend / Correlation / Scenario

### 💾 Persistent Storage

SQLite storage engine with multi-project isolation, time range + tag filtering.

---

## Performance

| Operation | Time |
|-----------|------|
| Create CausalGraph (lazy) | 53ms |
| First score() (loads 10967 pairs) | 363ms |
| Subsequent score() (inverted index) | **0.13ms** |
| 50-event causal discovery | 43ms |
| 100-event network (with multi-hop) | 164ms |
| do-calculus counterfactual | 0.2ms |

---

## Quick Start

```python
from src import TimelineBase, AnalyzerEngine, ReportGenerator
from src.core.counterfactual import CounterfactualAnalyzer
from datetime import datetime

# 1. Build timeline
timeline = TimelineBase(title="Research Topic")
timeline.add_event(
    timestamp=datetime(2024, 1, 1),
    data={}, source="source", tags=["tag"], summary="Event description"
)

# 2. Causal analysis (with multi-hop reasoning)
engine = AnalyzerEngine(timeline)
network = engine.build_causal_network(min_confidence=0.2, multihop=True)

# 3. Counterfactual analysis
cf = CounterfactualAnalyzer(network)
result = cf.analyze(cause_id, effect_id, method="do_calculus")
print(result.conclusion)

# 4. Generate report (auto-integrates plugin insights)
gen = ReportGenerator(timeline)
report = gen.generate(title="Research Report")
```

---

## Architecture

```
src/
├── core/           Core engine (13 modules)
│   ├── timeline         Timeline + chapter detection
│   ├── analyzer         Causal network + multi-hop + incremental
│   ├── causal_graph     Graph (79 builtin + 10882 ConceptNet)
│   ├── causal_lag       12-domain classifier + gamma prediction
│   ├── causal_mining    4-layer funnel + LLM batch
│   ├── counterfactual   do-calculus + simplified
│   ├── llm_config       LLM config center
│   ├── storage          SQLite persistence
│   └── report_generator Report generation + plugin integration
├── plugins/        Core plugins (3)
│   └── pest / swot / cycle
└── extras/         Extension modules (lazy-loaded)
    └── anomaly / trend / correlation / scenario
```

---

## Tests

```bash
python3 -m pytest tests/ -q
# 390 passed in 2.6s
```

---

## License

MIT
