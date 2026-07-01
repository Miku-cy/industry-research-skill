<p align="right">
  <a href="README_EN.md">English</a> | 中文
</p>

<p align="center">

![Version](https://img.shields.io/badge/version-1.3.0-blue?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10+-yellow?style=flat-square)
![Tests](https://img.shields.io/badge/tests-390%20passed-brightgreen?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

<h1 align="center">⏳ ChronoVisor · 时轴之眼</h1>
  <p align="center"><strong>通用因果分析引擎</strong></p>
  <p align="center">
    <em>因果链挖掘 · 多跳推理 · do-calculus 反事实 · 12 领域分类 · 增量更新</em>
  </p>
</p>

---

## 定位

ChronoVisor 不是投资工具，不是行业分析工具。它是一个**通用因果分析底座**，能从任意领域的事件序列中发现因果关系、构建因果网络、进行反事实推理。

适用场景：产业研究、政策分析、技术趋势、社会现象、历史事件、金融市场的因果推理。

---

## 核心能力

### 🔗 因果链挖掘（四层漏斗）

从事件序列中自动发现因果关系：

```
Layer 1: 时序过滤 — A 必须在 B 之前
Layer 2: 时间窗口 — 超出领域最大传导时间的淘汰
Layer 3: 图谱路由 — 已知概念对走快车道，未知走 LLM 慢车道
Layer 4: LLM 分析 — 传导机制 + 类似案例
```

### ⛓️ 多跳推理

自动发现 A→B→C 链式传导，置信度自动衰减（每跳 ×0.7），环检测，最大 3 跳。

### 🔬 反事实分析（Pearl do-calculus）

- **图手术**：do(¬A) 时切断 A 的所有上游边，消除混杂
- **截断因子分解**：只计算非 A 的独立上游概率
- **混杂检测**：P(B|A) vs P(B|do(¬A)) 差异大时提示混杂因素

### 🌍 12 领域自动分类

基于维基百科分类体系，~500 个关键词：

| 领域 | 峰值 | 领域 | 峰值 |
|------|------|------|------|
| 科技与半导体 | 60天 | 大宗商品与能源 | 14天 |
| 金融与资本市场 | 7天 | 加密货币与区块链 | 3天 |
| 宏观经济 | 90天 | 游戏与数字娱乐 | 90天 |
| 企业与组织 | 180天 | 社会与文化 | 365天 |
| 政策与治理 | 365天 | 国际关系与地缘 | 30天 |
| 环境与气候 | 3650天 | 医疗与健康 | 90天 |

### 📈 增量更新

新事件加入时只分析新事件对，不重新构建。1000 旧 + 1 新 ≈ 1000 次而非 500000 次。

### 🧩 插件系统

核心插件（启动加载）：PEST / SWOT / 周期识别
扩展插件（按需加载）：异常检测 / 趋势外推 / 相关性分析 / 情景分析

### 💾 持久化存储

SQLite 存储引擎，多项目隔离，支持时间范围 + 标签过滤查询。

---

## 性能

| 操作 | 耗时 |
|------|------|
| 创建 CausalGraph（懒加载） | 53ms |
| 首次 score()（含加载 10967 对） | 363ms |
| 后续 score()（倒排索引） | **0.13ms** |
| 50 事件因果发现 | 43ms |
| 100 事件因果网络（含多跳） | 164ms |
| do-calculus 反事实 | 0.2ms |

---

## 快速开始

```python
from src import TimelineBase, AnalyzerEngine, ReportGenerator
from src.core.counterfactual import CounterfactualAnalyzer
from datetime import datetime

# 1. 构建时间轴
timeline = TimelineBase(title="研究课题")
timeline.add_event(
    timestamp=datetime(2024, 1, 1),
    data={}, source="来源", tags=["标签"], summary="事件描述"
)

# 2. 因果分析（含多跳推理）
engine = AnalyzerEngine(timeline)
network = engine.build_causal_network(min_confidence=0.2, multihop=True)

# 3. 反事实分析
cf = CounterfactualAnalyzer(network)
result = cf.analyze(cause_id, effect_id, method="do_calculus")
print(result.conclusion)

# 4. 生成报告（自动集成插件洞察）
gen = ReportGenerator(timeline)
report = gen.generate(title="研究报告")
```

---

## 架构

```
src/
├── core/           核心引擎（13 模块）
│   ├── timeline         时间轴 + 章节检测
│   ├── analyzer         因果网络 + 多跳推理 + 增量更新
│   ├── causal_graph     因果图谱（79 内置 + 10882 ConceptNet）
│   ├── causal_lag       12 领域分类 + gamma 预测
│   ├── causal_mining    四层漏斗 + LLM 批量并发
│   ├── counterfactual   do-calculus + 简化版
│   ├── llm_config       LLM 配置中心
│   ├── storage          SQLite 持久化
│   └── report_generator 报告生成 + 插件集成
├── plugins/        核心插件（3 个）
│   └── pest / swot / cycle
└── extras/         扩展模块（按需加载）
    └── anomaly / trend / correlation / scenario
```

---

## 测试

```bash
python3 -m pytest tests/ -q
# 390 passed in 2.6s
```

---

## 安装

```bash
git clone https://github.com/Miku-cy/industry-research-skill.git
cd industry-research-skill
pip install -r requirements.txt  # 如有
```

---

## License

MIT
