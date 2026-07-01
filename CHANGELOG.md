# Changelog

所有版本的迭代记录。

---

## v1.4.0 — 因果引擎正确性与性能修复（2026-07-02）

### 🐛 P0 严重 Bug 修复（影响正确性）

**causal_lag.py — gamma 分布数学错误**
- 删除重复的 `return` 死代码（两条完全相同语句）
- 修正 gamma 参数化：`mode ≈ peak_days`（原注释声称 `peak=shape·scale`，实际众数是 `(shape-1)·scale`）
- CDF 改用 Wilson-Hilferty 正态变换，替代粗糙的正态近似（gamma 右偏分布尾部概率更准确）

**counterfactual.py — do-calculus 实现与注释对齐**
- `_is_on_path` 逻辑 bug 修复：原 BFS 只判断"能否到达 node"，不验证 node 之后能否到 to，导致 false positive 高发；改为严格判断两段连通性（from→node AND node→to）
- do-calculus 注释对齐实现：明确标注为 Noisy-OR 近似（非严格 Pearl 后门准则），`paths_cut` 仅作展示不参与计算

**timeline.py — rstrip 误用**
- `rstrip("（前）（后）")` 改用 `endswith + 切片`：`str.rstrip` 接收字符集合非子串，会把 `"第3章：加息/降息（前）"` 错剥成 `"第3章：加息/降息（"`，导致合并标题损坏

**causal_mining.py — 因果挖掘漏斗**
- `unknown` 路由修复：原直接 `pass` 淘汰，与设计文档矛盾；改为在 LLM 已配置时送慢车道，系统性找回 LLM 才能发现的间接因果链
- 标签方向分离：`cause_tags`/`effect_tags` 分离传参，避免把 `cause.tags+effect.tags` 同时塞入两端破坏图谱方向敏感评分

**analyzer.py — 多跳推理遗漏**
- `find_multihop_chains` 从所有节点出发 BFS（原只从根节点），修复中间起点间接链系统性遗漏（如 B→C→D，B 有上游 A 时，B→D 永远不被发现）

### ⚡ P1 性能/架构修复

**analyzer.py**
- 缓存 PEST/SWOT 关键词集合，避免在 O(N²) 配对循环里每次重建（K≈200 关键词）
- 复用 `causal_graph` 模块级单例，避免增量更新时磁盘重载 10967 条概念对 + 重建索引
- `find_causal_chains` 复用 `_analyze_pairs`，统一全量/增量评分路径，保证结果可重复
- 删除失效的"已分析跳过"死代码，加 `seen_pairs` 去重
- 4 处 `list.pop(0)` → `deque.popleft()`（O(N) → O(1) 出队）

**causal_graph.py**
- 全局单例懒加载加双重检查锁，避免多线程首次调用重复加载
- 倒排索引加 2-4 字中文 token 提取（中文场景下索引查询原本退化回 O(N) 全量扫描）
- `source` 字段保留真实来源（不再被 `builtin` 覆盖，影响 mining 路由判断）

**llm_config.py**
- 限速锁内只计算等待时间，释放锁后再 sleep，避免所有线程串行化

**storage.py**
- 新增 `replace_chains` 原子方法（DELETE+INSERT 同事务），替代 `clear_chains + save_chains` 的非原子组合

### 🧹 P2 代码质量改进

**死代码清理**
- 删除 `analyzer.py._find_indirect_chains`（从未被调用）
- 删除 `report_generator.py` 的 4 个 `_build_*_section` 方法

**代码质量**
- 库代码 `print` → `logging`（causal_graph / causal_mining / llm_config / timeline / registry），支持级别配置和重定向
- `registry.py`：`Dict[str, any]` → `Dict[str, Any]`；`register()` 增加 name 唯一性检查（默认 raise，可传 `overwrite=True` 覆盖）
- `analyzer.py._get_event_text` 修复 `str(None)="None"` / `str({})="{}"` 污染评分文本
- `storage.py` 给 `lag_observations(domain)` / `learned_graph(domain, trigger_words)` 补建索引
- `analyzer.py.chain_count` 拆分为 `direct_chain_count` / `indirect_chain_count`
- `analyze_scenario` 重构为接受 `Scenario` 对象（保留旧 9 参数位置形式兼容）

### 📝 Changed Files
- 10 files changed, +341 / -224 lines
- 修改：analyzer.py, causal_graph.py, causal_lag.py, causal_mining.py, counterfactual.py, llm_config.py, report_generator.py, storage.py, timeline.py, plugins/registry.py

### 🧪 Tests
- 390 passed in 1.9s（无回归）

---

## v1.3.0 — 通用因果分析引擎（2026-07-01）

### ✨ Features

**因果链多跳推理**
- `CausalNetwork.find_multihop_chains()`: BFS 遍历发现 A→B→C 间接因果链
- 置信度自动衰减（每跳 ×0.7），环检测，时间顺序保证

**因果网络增量更新**
- `AnalyzerEngine.update_incremental()`: 只分析新事件与已有事件的关系
- `_analyzed_ids` 标记已分析事件，避免重复计算

**do-calculus 反事实分析**
- Pearl 图手术：do(¬A) 切断 A 的所有上游边
- 截断因子分解 + 混杂检测
- 保留简化版（method="simple"）向后兼容

**持久化存储**
- SQLite StorageEngine：事件/因果链/章节/滞后观测
- 多项目隔离，时间范围 + 标签过滤

**插件架构**
- 核心插件（启动加载）：PEST / SWOT / Cycle
- 扩展插件（按需加载）：Anomaly / Trend / Correlation / Scenario
- 报告生成器自动集成插件洞察

**性能优化**
- 倒排索引：score() 30x 提速（2.8ms → 0.13ms）
- 懒加载：CausalGraph 创建从 367ms 降到 53ms

**领域分类器通用化**
- 12 通用领域（基于维基百科分类体系）
- ~500 关键词，去投资偏见

**ConceptNet 中文扩充**
- 10,882 条（4700 中文 + 6100 英文）
- 内置概念对 24 → 79 条

**架构精简**
- core/ 13 模块 + plugins/ 3 插件 + extras/ 7 扩展
- 非核心模块移入 extras/

### 📝 Changed Files
- 40 files changed, +60,617 lines
- 新增：storage.py, plugins/*, extras/*, test_*.py × 7
- 重构：analyzer.py, causal_graph.py, causal_lag.py, counterfactual.py

### 🧪 Tests
- 390 passed in 2.6s

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
