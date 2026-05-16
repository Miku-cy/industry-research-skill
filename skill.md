# ChronoVisor · 时轴之眼

**Time-Axis Intelligence for Deep Research**

像看电影一样做研究，让知识在时间轴上展开。

---

## 核心能力

### 🎬 时间轴底座

- **精确时间戳**：每个数据点都有时间标记，精确到分钟
- **自动章节检测**：研究自动分段（成长期→危机期→转折期→展望期）
- **双向导航**：跳到任意时间点，回看，快进，像看视频一样

### ⚡ 实时性验证

- **五级新鲜度**：实时 / 近期 / 过期 / 严重过期 / 归档
- **冲突自动检测**：过时数据 vs 实时数据，冲突时立刻警告
- **来源可靠性评分**：官方 / 专业 / 权威媒体 / 一般 / 需验证

### 🔗 因果链引擎

- **时间顺序验证**：因必须在果之前
- **置信度评分**：共享标签 + 时间接近度 + 来源可靠性
- **自动因果发现**：遍历整个时间轴发现因果关系

### 📊 可插拔分析框架

- **PEST**：政治 / 经济 / 社会 / 技术
- **SWOT**：优势 / 劣势 / 机会 / 威胁
- **情景分析**：乐观 / 基准 / 悲观
- **波特五力**：竞争格局分析
- **章节对比**：跨章节 SWOT 对比，追踪变化

### 🧠 语义增强层

- **启发式模式**：基于扩展关键词的语义分类（零依赖）
- **LLM 模式**：接入任意 LLM 进行深度语义理解

---

## 快速开始

```python
from src import TimelineBase, AnalyzerEngine, SemanticClassifier
from datetime import datetime

# 建立时间轴
timeline = TimelineBase(title="行业研究")
timeline.add_event(
    timestamp=datetime(2024, 1, 1),
    data={"price": 100},
    source="实时行情",
    tags=["经济", "价格"],
    summary="银价突破30美元"
)

# 自动章节检测
chapters = timeline.auto_detect_chapters(min_events=3)

# 分析
analyzer = AnalyzerEngine(timeline)
pest = analyzer.analyze_pest()
swot = analyzer.analyze_swot()
chains = analyzer.find_causal_chains()

# 语义增强（可选）
semantic = SemanticClassifier(mode="heuristic")
scores = semantic.classify(timeline.timeline.get_all_events()[0])
```

---

## 架构

```
用户研究需求
      │
      ▼
┌─────────────────┐
│  任务拆解器      │
│  数据收集器      │
│  新鲜度验证器    │  ← ChronoVisor 核心
│  分析引擎        │
│  报告生成器      │
└────────┬────────┘
         │
  ┌──────┴──────┐
  │  上层框架   │
  │ PEST/SWOT/情景 │
  └──────┬──────┘
         │
  ┌──────┴──────┐
  │ 🎬 时间轴底座 │
  │ ⏮ ⏪ ⏸ ⏩ ⏭ │
  └─────────────┘
```

---

## 核心类

| 类 | 功能 |
|---|---|
| `TimelineBase` | 时间轴主入口 |
| `AnalyzerEngine` | PEST / SWOT / 因果链 / 情景分析 |
| `SemanticClassifier` | 语义分类（启发式 / LLM） |
| `RealTimeValidator` | 数据新鲜度验证 |
| `ReportGenerator` | 报告生成 |

---

## 文件结构

```
chronovisor/
├── skill.yaml           # 配置文件
├── skill.md             # 使用文档
├── README.md            # 中文文档（默认）
├── README_EN.md         # English
├── src/
│   ├── core/
│   │   ├── timeline.py         # 时间轴引擎
│   │   ├── task_decomposer.py # 任务拆解
│   │   ├── data_collector.py  # 数据收集
│   │   ├── validator.py       # 新鲜度验证
│   │   ├── analyzer.py        # 分析引擎
│   │   ├── semantic.py        # 语义分类
│   │   └── report_generator.py # 报告生成
│   └── ...
```

---

## 许可证

MIT
