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
    <em>从事件序列中发现因果关系，构建因果网络，进行反事实推理</em>
  </p>
</p>

---

## 这是什么

ChronoVisor 是一个**通用因果分析引擎**。给它一组按时间排列的事件，它能自动回答：

- **哪些事件之间有因果关系？** — 因果链挖掘
- **A 通过什么路径影响了 C？** — 多跳推理（A→B→C）
- **如果 A 没发生，B 还会发生吗？** — 反事实分析（Pearl do-calculus）
- **这个事件属于什么领域？传导要多久？** — 12 领域自动分类 + 时间预测
- **新事件来了，怎么不重新分析？** — 增量更新

它不绑定任何特定领域。金融、科技、政策、社会、医疗、游戏——只要有时序事件，就能分析。

---

## 能做什么

### 🔗 因果链挖掘：从一堆事件里找出谁导致了谁

给 ChronoVisor 一组事件：

```
2024-01-01: ChatGPT 爆火，AI 算力需求激增
2024-02-01: 英伟达 H100 供不应求
2024-03-01: 英伟达市值突破 2 万亿美元
2024-04-01: SK 海力士 HBM3E 量产
2024-06-01: HBM 产能过剩担忧初现
```

它会告诉你：

```
ChatGPT爆火 → 英伟达H100供不应求 [0.35]
英伟达H100供不应求 → 英伟达市值突破2万亿 [0.30]
SK海力士HBM量产 → HBM产能过剩担忧 [0.36]
```

背后是四层漏斗：时序过滤 → 时间窗口 → 因果图谱路由（10967 条概念对） → LLM 精细分析。

### ⛓️ 多跳推理：A 不是直接导致 C，而是通过 B

不只是找 A→B，还找 A→B→C 链式传导：

```
ChatGPT爆火 → 英伟达H100供不应求 → HBM产能过剩担忧 [间接因果, 置信度 0.037]
```

置信度自动衰减（每跳 ×0.7），传导越远越不确定——这符合现实。

### 🔬 反事实分析：如果 A 没发生，B 还会发生吗？

两种方法：

**简化版**：看 B 有没有其他原因，取最强替代路径。

**do-calculus（Pearl 图手术）**：不只是观察"A 没发生时 B 怎样"，而是问"如果我强制干预让 A 不发生，B 会怎样"。区别在于：

- 简化版忽略混杂因素（C 同时导致 A 和 B）
- do-calculus 切断 A 的所有上游，消除混杂，然后重新计算 B 的概率

```
# 简化版
P(B|¬A) = 0.3  # 没有 A 时 B 还有 30% 概率

# do-calculus
P(B|do(¬A)) = 0.15  # 干预移除 A 后，B 只有 15%（因为混杂因素也被切断了）
→ 结论：A 和 B 的相关性有 50% 是混杂造成的
```

### 🌍 12 领域自动分类：这个事件属于什么领域？

不用手动标注，ChronoVisor 根据事件内容自动判断领域，每个领域有不同的传导时间：

| 领域 | 峰值传导 | 典型场景 |
|------|---------|---------|
| 科技与半导体 | 60天 | 芯片涨价→终端涨价 |
| 金融与资本市场 | 7天 | 加息→股市下跌 |
| 宏观经济 | 90天 | PMI→经济复苏 |
| 政策与治理 | 365天 | 芯片法案→产能扩张 |
| 大宗商品与能源 | 14天 | OPEC减产→油价上涨 |
| 加密货币与区块链 | 3天 | ETF获批→BTC新高 |
| 国际关系与地缘 | 30天 | 冲突→避险资产上涨 |
| 医疗与健康 | 90天 | 新药获批→药企股价上涨 |

基于维基百科分类体系，~500 个关键词覆盖各领域核心术语。

### 📈 增量更新：新事件来了，不用从头分析

传统做法：1000 个旧事件 + 1 个新事件 = 重新分析 500,000 个事件对。

ChronoVisor：只分析 1 个新事件 vs 1000 个旧事件 = 1000 次分析。快 500 倍。

### 🧩 插件系统：可扩展的分析框架

核心插件（启动加载）：
- **PEST**：政治/经济/社会/技术宏观环境分析
- **SWOT**：优势/劣势/机会/威胁态势分析
- **Cycle**：周期识别（Kitchin/利率/信贷/商品）

扩展插件（按需加载）：
- **Anomaly**：异常检测（黑天鹅/极端波动识别）
- **Trend**：趋势外推（方向/动量/转折检测）
- **Correlation**：相关性分析（标签共现/Jaccard 系数）
- **Scenario**：情景分析（乐观/基准/悲观三情景）

报告生成时自动调用插件，洞察直接写入报告。

### 💾 持久化存储：数据不丢，随时查询

SQLite 存储引擎，支持：
- 多项目隔离（不同研究课题互不干扰）
- 时间范围查询（"2024年上半年的事件"）
- 标签过滤（"所有带 AI 标签的事件"）
- 因果链/章节/滞后观测全持久化

### 🌐 Web 可视化控制台

Three.js 3D 力导向因果网络可视化，支持：
- AI 研究：输入问题，自动提取事件 + 挖掘因果
- 事件管理：增删改查
- 领域分类：实时显示事件领域
- 网络交互：点击节点查看详情

```bash
python3 console.py
# 访问 http://localhost:8765
```

---

## 性能

| 操作 | 耗时 | 说明 |
|------|------|------|
| 创建引擎 | 53ms | 懒加载，启动时不做任何耗时操作 |
| 首次因果评分 | 363ms | 加载 10967 条概念对 + 倒排索引构建 |
| 后续因果评分 | **0.13ms** | 倒排索引命中，30x 提速 |
| 50 事件因果发现 | 43ms | 1225 个事件对 |
| 100 事件完整网络 | 164ms | 含多跳推理 |
| 反事实分析 | 0.2ms | do-calculus 单次 |
| SQLite 读写 | 3ms | 100 条事件 |

---

## 快速开始

```python
from src import TimelineBase, AnalyzerEngine, ReportGenerator
from src.core.counterfactual import CounterfactualAnalyzer
from datetime import datetime

# 1. 构建时间轴
timeline = TimelineBase(title="半导体周期研究")
events = [
    ("ChatGPT爆火", "2024-01-01", ["AI", "需求"]),
    ("英伟达H100供不应求", "2024-02-01", ["英伟达", "GPU"]),
    ("存储芯片价格上涨", "2024-03-01", ["存储", "价格上涨"]),
]
for summary, date, tags in events:
    timeline.add_event(
        timestamp=datetime.strptime(date, "%Y-%m-%d"),
        data={}, source="来源", tags=tags, summary=summary,
    )

# 2. 因果分析
engine = AnalyzerEngine(timeline)
network = engine.build_causal_network(min_confidence=0.2, multihop=True)
print(f"发现 {network.chain_count} 条因果链")

# 3. 反事实分析
cf = CounterfactualAnalyzer(network)
result = cf.analyze(cause_id, effect_id, method="do_calculus")
print(result.conclusion)

# 4. 持久化
from src.core.storage import StorageEngine
with StorageEngine("data/research.db") as db:
    db.create_project("semiconductor", "半导体周期")
    db.save_events("semiconductor", timeline.timeline.get_all_events())

# 5. 生成报告（自动集成插件洞察）
gen = ReportGenerator(timeline)
report = gen.generate(title="半导体周期研究报告")
gen.export_markdown(report, "report.md")
```

---

## 架构

```
src/
├── core/                    核心引擎（13 模块，~5500 行）
│   ├── timeline.py          时间轴 + 3 种章节检测算法
│   ├── analyzer.py          因果网络 + 多跳推理 + 增量更新
│   ├── causal_graph.py      因果图谱（79 内置 + 10882 ConceptNet，懒加载 + 倒排索引）
│   ├── causal_lag.py        12 领域分类 + gamma 分布预测 + 贝叶斯更新
│   ├── causal_mining.py     四层漏斗 + LLM 批量并发
│   ├── counterfactual.py    Pearl do-calculus + 简化版反事实
│   ├── llm_config.py        LLM 配置中心（多 profile + 限速 + 并发）
│   ├── storage.py           SQLite 持久化存储
│   ├── report_generator.py  报告生成 + 插件集成
│   └── semantic.py          语义分类器
├── plugins/                 核心插件（3 个，启动加载）
│   ├── pest.py              PEST 宏观环境分析
│   ├── swot.py              SWOT 态势分析
│   └── cycle.py             周期识别
└── extras/                  扩展模块（按需加载）
    ├── anomaly.py           异常检测
    ├── trend.py             趋势外推
    ├── correlation.py       相关性分析
    └── scenario.py          情景分析
```

---

## 测试

```bash
python3 -m pytest tests/ -q
# 390 passed in 2.6s
```

覆盖：因果图谱、多跳推理、增量更新、do-calculus、存储引擎、集成测试、插件系统。

---

## 安装

```bash
git clone https://github.com/Miku-cy/industry-research-skill.git
cd industry-research-skill
```

依赖：Python 3.10+，无外部必选依赖（LLM 功能可选配置）。

---

## License

MIT
