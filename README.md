# Industry Research Skill

基于「产业研究方法论」的 **时间轴驱动** 产业深度研究助手 AI Agent Skill。

## 核心理念

> 时间轴 = 知识视频播放器

- **时间轴是底层基础设施**，不是限制思维的工具
- 所有数据按时间标记，像看电影一样可以任意跳转
- 章节分段自动识别研究阶段，如公司成长期、转折期、预测期
- 上层分析框架（PEST/SWOT/情景分析）在时间轴底座上运行

## 架构

```
用户层
  └── 用户输入研究需求

Skill 主控制器
  ├── 任务拆解器 (TaskDecomposer)
  ├── 信息收集器 (DataCollector)
  ├── 交叉验证器 (RealTimeValidator)
  ├── 分析引擎 (AnalyzerEngine)
  └── 报告生成器 (ReportGenerator)

上层分析框架层
  ├── PEST 分析
  ├── SWOT 分析
  ├── 情景分析
  └── 波特五力

时间轴底座（基础设施）
  ├── 时间标记（精确到分钟）
  ├── 章节分段（自动识别）
  ├── 可跳转导航（任意时间点）
  └── 书签与标注（高维视角）
```

## 快速开始

```python
from src import TimelineBase, TaskDecomposer, DataCollector
from src import RealTimeValidator, AnalyzerEngine, ReportGenerator
from datetime import datetime

timeline = TimelineBase(title="完美世界投资研究")
timeline.timeline.set_range(start=datetime(2023, 1, 1), end=datetime(2027, 12, 31))

decomposer = TaskDecomposer()
plan = decomposer.decompose("分析完美世界的投资价值")

collector = DataCollector(timeline)
collector.collect(data={"price": 16.00}, source="实时行情",
    timestamp=datetime(2026, 5, 16, 15, 0), summary="完美世界股价 16.00元")

validator = RealTimeValidator(timeline)
result = validator.validate_all()

analyzer = AnalyzerEngine(timeline)
swot = analyzer.analyze_swot()
pest = analyzer.analyze_pest()
chains = analyzer.find_causal_chains()

generator = ReportGenerator(timeline)
report = generator.generate("完美世界投资分析报告")
print(report.to_markdown())
```

## 关键特性

### 时间轴机制
- 每个数据点都有精确时间戳
- 自动识别章节/阶段
- 可跳转导航，像看视频一样

### 实时性保障
- 数据新鲜度分级（实时/近期/过期/归档）
- 过期数据自动警告
- 多源交叉验证

### 因果分析
- 原因必须在结果之前（避免倒果为因）
- 自动发现因果关系链
- 时间顺序校验

### 可扩展性
- 分析框架可无限扩展
- 时间轴底座不变
- 新框架即插即用