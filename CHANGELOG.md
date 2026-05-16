# Changelog

所有版本的迭代记录。基于白银趋势分析实测驱动改进。

---

## v1.1.0 — 稳定性修复（2026-05-16）

### 🐛 Bug Fixes

**章节检测：数据密集时输出 1 章**
- 问题：21 个事件、大部分间隔 < 60 天时，`_find_time_gaps` 不产生边界，所有事件被塞进一个大章节
- 修复：新增 `_fallback_even_split` 兜底策略——边界 < 3 且事件 >= 6 时，按时间均匀分段
- 修复：新增 `_force_merge_to_max` 方法，确保章节不超过 `max_chapters` 上限
- 结果：同一数据集从 1 章 → 5 章（价格→供应紧张→价格峰值→暴跌→利率企稳）

**PEST/SWOT 分析重复项**
- 问题：`analyze_pest()`（标签匹配）和 `enhance_pest()`（语义匹配）独立运行，合并时同一事件出现两次
- 修复：`enhance_pest` 和 `enhance_swot` 内部添加去重逻辑——收集已有结果中的所有摘要，跳过已存在的
- 结果：PEST 经济因素从 19 项（含重复）→ 16 项（无重复）

### 📝 Changed Files

- `src/core/timeline.py` — ChapterDetector 新增 `max_chapters`、`_fallback_even_split`、`_force_merge_to_max`
- `src/core/semantic.py` — `enhance_pest`、`enhance_swot` 内部去重
- `CHANGELOG.md` — 新增版本迭代记录

---

## v1.0.0 — 语义分类增强版（2026-05-16）

### ✨ Features

**SemanticClassifier 语义分类器**
- 新增 `src/core/semantic.py` 模块
- 启发式分类：8 个类别（政策驱动、市场波动、产业趋势、技术突破、财务表现、竞争格局、风险事件、宏观环境）
- PEST 评分：每个事件自动打分（political/economic/social/technological），0-1 分
- SWOT 评分：每个事件自动打分（strengths/weaknesses/opportunities/threats），0-1 分
- LLM 模式支持：可传入 `llm_callable` 切换为 LLM 驱动的语义分类
- `enhance_pest()` 方法：用语义分类增强 PEST 分析结果
- `enhance_swot()` 方法：用语义分类增强 SWOT 分析结果

**ChapterDetector 章节检测改进**
- 时间间隔阈值：`LARGE_GAP_DAYS=180`、`MIN_GAP_DAYS=60`
- 语义偏移检测：`_is_semantic_shift` 识别否定关键词（停止、取消、逆转等）
- 小章节合并：`_merge_small_chapters` 将不够 `min_events` 的章节向前合并

### 📝 Changed Files

- `src/core/semantic.py` — 新增 SemanticClassifier
- `src/core/analyzer.py` — 更新 PEST/SWOT 数据结构
- `src/core/timeline.py` — 更新 ChapterDetector
- `skill.md` — 新增使用文档
- `.gitignore` — 新增

---

## v0.x — 初始版本

### 核心模块

| 模块 | 功能 |
|------|------|
| `timeline.py` | TimelineBase、TimelineNavigator、ChapterDetector |
| `data_collector.py` | DataCollector、新鲜度检测 |
| `analyzer.py` | AnalyzerEngine、PEST/SWOT/情景分析/因果链 |
| `validator.py` | RealTimeValidator、数据新鲜度验证 |
| `report_generator.py` | ReportGenerator、Markdown 报告输出 |
| `task_decomposer.py` | TaskDecomposer、研究任务拆解 |

---

## 实测数据对比

基于白银趋势分析（21 个事件，2024-2026）：

| 指标 | V1 (v0.x) | V2 (v1.0.0) | V3 (v1.1.0) |
|------|-----------|-------------|-------------|
| 章节数 | 18 ❌ | 1 ❌ | **5 ✅** |
| PEST 经济因素 | 0 | 19（含重复） | **16（无重复）** |
| PEST 政治因素 | 2 | 10 | **7（无重复）** |
| SWOT 劣势 | 1 | 3 | **3（无重复）** |
| 因果链置信度 | 55-65% | 63-73% | **63-73%** |
| PEST 重复项 | 0 | 有重复 ❌ | **0 ✅** |
| SWOT 重复项 | 0 | 有重复 ❌ | **0 ✅** |
