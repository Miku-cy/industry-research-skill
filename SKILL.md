---
name: chronovisor
description: |
  ChronoVisor · 时轴之眼：通用因果分析引擎。支持因果链挖掘、多跳推理、反事实分析(do-calculus)、12领域自动分类、增量更新。当用户要求分析因果关系、研究产业趋势、做深度研究、时间线梳理、反事实推理时使用。
version: 1.3.0
---

# ChronoVisor · 时轴之眼

**通用因果分析引擎 — 让因果推理可计算**

## 定位

ChronoVisor 不是投资工具，不是行业分析工具。它是一个**通用因果分析底座**，能从任意领域的事件序列中发现因果关系、构建因果网络、进行反事实推理。

适用场景：产业研究、政策分析、技术趋势、社会现象、历史事件、金融市场的因果推理。

## 核心能力

### 1. 因果链挖掘（四层漏斗）

从事件序列中自动发现因果关系：

```
Layer 1: 时序过滤 — A 必须在 B 之前
Layer 2: 时间窗口 — 超出领域最大传导时间的淘汰
Layer 3: 图谱路由 — 已知概念对走快车道，未知走 LLM 慢车道
Layer 4: LLM 分析 — 传导机制 + 类似案例
```

```python
from src import TimelineBase, AnalyzerEngine

timeline = TimelineBase(title="研究课题")
timeline.add_event(
    timestamp=datetime(2024, 1, 1),
    data={}, source="来源",
    tags=["标签1", "标签2"],
    summary="事件描述"
)

engine = AnalyzerEngine(timeline)
network = engine.build_causal_network(min_confidence=0.2, multihop=True)
```

### 2. 多跳推理

自动发现 A→B→C 链式传导：

```python
# network 已包含多跳链（build_causal_network 默认开启）
for effects in network._downstream.values():
    for chain in effects.values():
        if "[间接因果]" in chain.description:
            print(f"{chain.description} 置信度={chain.confidence:.3f}")
```

- 置信度自动衰减（每跳 ×0.7）
- 环检测 + 时间顺序保证
- 最大支持 3 跳（A→B→C→D）

### 3. 反事实分析（Pearl do-calculus）

支持两种方法：

```python
from src.core.counterfactual import CounterfactualAnalyzer

analyzer = CounterfactualAnalyzer(network)

# do-calculus（默认，基于 Pearl 图手术）
result = analyzer.analyze(cause_id, effect_id, method="do_calculus")
print(result.conclusion)     # 结论
print(result.paths_cut)      # 被切断的路径
print(result.causal_effect)  # 因果效应

# 简化版（基于替代路径估计，向后兼容）
result = analyzer.analyze(cause_id, effect_id, method="simple")

# 通过摘要查找
result = analyzer.analyze_by_summary("加息", "股市下跌")
```

do-calculus 核心机制：
- **图手术**：do(¬A) 时切断 A 的所有上游边
- **截断因子分解**：只计算非 A 的独立上游概率
- **混杂检测**：P(B|A) vs P(B|do(¬A)) 差异大时提示混杂

### 4. 因果图谱

10,967 条概念对（79 内置 + 10,882 ConceptNet），懒加载，倒排索引加速：

```python
from src.core.causal_graph import CausalGraph

graph = CausalGraph()  # 53ms 创建，首次 score() 时才加载数据
result = graph.score("OPEC减产", "油价上涨")
# → known=True, score=0.35, source="builtin"

# 自动学习新概念对
graph.learn_from_chain(
    cause_summary="事件A", effect_summary="事件B",
    cause_tags=["标签"], effect_tags=["标签"],
    confidence=0.8
)
```

**倒排索引**：score() 从 O(N) 暴力遍历优化为 O(k) 候选查找，**30x 提速**。

### 5. 12 领域自动分类

基于维基百科分类体系，~500 个关键词：

| 领域 | 峰值传导 | 覆盖范围 |
|------|---------|---------|
| 科技与半导体 | 60天 | 芯片/AI/软件/硬件 |
| 金融与资本市场 | 7天 | 股票/债券/基金 |
| 宏观经济 | 90天 | GDP/CPI/就业 |
| 企业与组织 | 180天 | 战略/运营/人事 |
| 政策与治理 | 365天 | 法规/监管/国际协议 |
| 大宗商品与能源 | 14天 | 原油/金属/农产品 |
| 加密货币与区块链 | 3天 | BTC/ETH/DeFi |
| 游戏与数字娱乐 | 90天 | 游戏/影视/流媒体 |
| 社会与文化 | 365天 | 人口/教育/舆论 |
| 国际关系与地缘 | 30天 | 冲突/制裁/外交 |
| 环境与气候 | 3650天 | 碳排放/新能源 |
| 医疗与健康 | 90天 | 疾病/药物/基因 |

```python
from src.core.causal_lag import CausalLagModel

lag = CausalLagModel()
domain = lag.classify_domain(["芯片", "AI"], "半导体价格上涨")
# → "科技与半导体"

pred = lag.predict_lag(["芯片"], "半导体价格上涨")
# → peak_days=60, ci_90=[19, 101], prob_within={"30天": 0.12}
```

### 6. 增量更新

新事件加入时只分析新事件对，不重新构建：

```python
network = engine.build_causal_network(min_confidence=0.2)
# ... 后续新事件 ...
engine.update_incremental(network, new_events, min_confidence=0.2)
# 只分析新事件 vs 已有事件，1000旧+1新 ≈ 1000次而非500000次
```

### 7. 插件系统

核心插件（启动加载）：
- **PEST**：政治/经济/社会/技术宏观分析
- **SWOT**：优势/劣势/机会/威胁态势分析
- **Cycle**：周期识别（Kitchin/利率/信贷/商品）

扩展插件（按需加载）：
- **Anomaly**：异常检测（黑天鹅/极端波动）
- **Trend**：趋势外推（方向/动量/转折）
- **Correlation**：相关性分析（标签共现/Jaccard）
- **Scenario**：情景分析（乐观/基准/悲观）

```python
from src.plugins import plugin_registry

# 核心插件直接使用
result = plugin_registry.run("pest", events)
print(result.insights)

# 扩展插件按需加载
plugin_registry.load_extras()
result = plugin_registry.run("anomaly", events, threshold=0.5)
```

### 8. 持久化存储

SQLite 存储引擎，支持多项目隔离：

```python
from src.core.storage import StorageEngine

with StorageEngine("data/my_project.db") as db:
    db.create_project("semiconductor", "半导体周期研究")
    db.save_events("semiconductor", events)
    db.save_chains("semiconductor", chains)
    
    # 按时间/标签查询
    events = db.load_events("semiconductor", start="2024-01-01", tags=["AI"])
```

### 9. 报告生成

自动推断研究类型，集成插件分析结果：

```python
from src import ReportGenerator

gen = ReportGenerator(timeline)
report = gen.generate(title="研究报告", topic_type="行业研究")
# 摘要自动包含 PEST/SWOT/周期 插件洞察
print(report.executive_summary)
gen.export_markdown(report, "report.md")
```

### 10. Web 可视化控制台

Three.js 3D 力导向因果网络可视化：

```bash
python3 console.py
# 访问 http://localhost:8765
# 支持：AI 研究（输入问题自动提取事件+挖掘因果）、事件管理、领域分类
```

## 快速开始（完整流程）

```python
from src import TimelineBase, AnalyzerEngine, ReportGenerator, StorageEngine
from src.core.counterfactual import CounterfactualAnalyzer
from datetime import datetime

# 1. 构建时间轴
timeline = TimelineBase(title="研究课题")
events_data = [
    ("原因事件", "2024-01-01", ["标签"]),
    ("中间事件", "2024-02-01", ["标签"]),
    ("结果事件", "2024-03-01", ["标签"]),
]
for summary, date, tags in events_data:
    timeline.add_event(
        timestamp=datetime.strptime(date, "%Y-%m-%d"),
        data={}, source="来源", tags=tags, summary=summary,
    )

# 2. 因果分析
engine = AnalyzerEngine(timeline)
network = engine.build_causal_network(min_confidence=0.2, multihop=True)
print(f"因果链: {network.chain_count}")

# 3. 反事实分析
cf = CounterfactualAnalyzer(network)
# ... 使用 do-calculus ...

# 4. 持久化
with StorageEngine("data/research.db") as db:
    db.create_project("my_research", "我的研究")
    db.save_events("my_research", timeline.timeline.get_all_events())

# 5. 生成报告
gen = ReportGenerator(timeline)
report = gen.generate(title="研究报告")
```

## 性能

| 操作 | 耗时 |
|------|------|
| 创建 CausalGraph（懒加载） | 53ms |
| 首次 score()（含加载 10967 对） | 363ms |
| 后续 score()（倒排索引） | 0.13ms |
| 50 事件因果发现 | 43ms |
| 100 事件因果网络（含多跳） | 164ms |
| do-calculus 反事实 | 0.2ms |
| SQLite 100 条读写 | 3ms |

## 架构

```
src/
├── core/           核心引擎（13 模块，~5500 行）
│   ├── timeline         时间轴 + 章节检测（3 种算法）
│   ├── analyzer         因果网络 + 多跳推理 + 增量更新
│   ├── causal_graph     因果图谱（79 内置 + 10882 ConceptNet）
│   ├── causal_lag       12 领域分类 + gamma 预测 + 贝叶斯
│   ├── causal_mining    四层漏斗 + LLM 批量并发
│   ├── counterfactual   do-calculus + 简化版
│   ├── llm_config       LLM 配置中心（多 profile + 限速 + 并发）
│   ├── storage          SQLite 持久化
│   ├── report_generator 报告生成 + 插件集成
│   └── semantic         语义分类器
├── plugins/        核心插件（3 个，启动加载）
│   ├── pest / swot / cycle
└── extras/         扩展模块（按需加载）
    ├── anomaly / trend / correlation / scenario
    └── data_collector / task_decomposer / validator
```

## 测试

```bash
python3 -m pytest tests/ -q
# 390 passed in 2.6s
```

## 配置

LLM 配置文件：`chronovisor.yaml`

```yaml
mining:
  api_url: "https://api.example.com/v1"
  api_key: "sk-xxx"
  api_model: "model-name"
  temperature: 0.1

semantic:
  mode: "heuristic"  # heuristic / ollama / api
```

## 注意事项

- 因果图谱懒加载，首次 score() 有 363ms 开销
- LLM 因果挖掘需要配置 API（chronovisor.yaml 或环境变量）
- do-calculus 在简单场景下与简化版结果一致，混杂场景下更准确
- ConceptNet 中文数据偏口语化，专业术语靠内置 79 条概念对
