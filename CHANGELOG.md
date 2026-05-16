# Changelog · 变更记录

## [1.0.0] - 2026-05-16

### 🎉 项目启动

- 正式更名为 **ChronoVisor · 时轴之眼**
- 搭建双语文档系统（中文 default + English）
- 文档右上角添加语言切换链接

### 🚀 Features

- **[core/analyzer.py]** PEST/SWOT 从纯标签匹配升级为关键词+摘要语义匹配
- **[core/analyzer.py]** 支持一个事件属于多个分类（主分类 + 阈值 0.5 以内的次分类）
- **[core/timeline.py]** 章节检测从标签不交集切分 → 时间聚类+最小章节合并
- **[core/semantic.py]** 🆕 新增 SemanticClassifier 语义分类增强层（启发式+LLM 双模式）
- **[skill.yaml]** 更新项目 name 和 display_name

### 🐛 Bug Fixes

- **PEST 分析**：修复只检测到政治因素的问题，现在经济/技术/社会因素都能被正确识别
- **SWOT 分析**：修复优势/机会/威胁全部为 0 的问题
- **章节检测**：修复 21 事件切出 18 章的过于碎片化问题
- **因果链置信度**：增强计算逻辑，增加共享关键词匹配权重（之前只有标签）

### 📚 Documentation

- **README.md / README_EN.md**：重写文档，强调独特功能和架构
- **skill.md** 🆕：新增使用文档
- **.gitignore** 🆕：新增标准忽略规则
- **src/__init__.py / src/core/__init__.py**：导出新模块

### 变更统计

| 指标 | 修复前 | 修复后 |
|---|---|---|
| PEST 经济因素 | 0 | 4 ✅ |
| PEST 技术因素 | 0 | 2 ✅ |
| SWOT 优势 | 0 | 4 ✅ |
| SWOT 威胁 | 0 | 2 ✅ |
| 章节数（6 事件测试） | 4 章 | 2 章 ✅ |
