from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from .timeline import TimelineBase, Chapter


@dataclass
class ReportSection:
    title: str = ""
    level: int = 1
    content: str = ""
    subsections: List["ReportSection"] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    data_points: List[Dict] = field(default_factory=list)

    def to_markdown(self, indent: int = 0) -> str:
        lines = []
        prefix = "#" * min(self.level + indent, 6)
        lines.append(f"{prefix} {self.title}")
        lines.append("")
        if self.content:
            lines.append(self.content)
            lines.append("")
        if self.insights:
            lines.append("**核心洞察：**")
            lines.append("")
            for insight in self.insights:
                lines.append(f"- {insight}")
            lines.append("")
        for sub in self.subsections:
            lines.append(sub.to_markdown(indent))
            lines.append("")
        return "\n".join(lines)


@dataclass
class Report:
    title: str = ""
    subtitle: str = ""
    author: str = ""
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    sections: List[ReportSection] = field(default_factory=list)
    executive_summary: str = ""
    key_conclusions: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)
    timeline_snapshot: Optional[Dict] = None

    def to_markdown(self) -> str:
        lines = []
        lines.append(f"# {self.title}")
        lines.append("")
        if self.subtitle:
            lines.append(f"*{self.subtitle}*")
            lines.append("")
        lines.append(f"> 作者：{self.author} | 日期：{self.date}")
        lines.append("")
        lines.append("---")
        lines.append("")
        if self.executive_summary:
            lines.append("## 核心摘要")
            lines.append("")
            lines.append(self.executive_summary)
            lines.append("")
        if self.key_conclusions:
            lines.append("## 核心结论")
            lines.append("")
            for i, conclusion in enumerate(self.key_conclusions, 1):
                lines.append(f"{i}. {conclusion}")
            lines.append("")
        if self.risk_warnings:
            lines.append("## 风险提示")
            lines.append("")
            for warning in self.risk_warnings:
                lines.append(f"- ⚠️ {warning}")
            lines.append("")
        if self.timeline_snapshot:
            lines.append(self._render_timeline_snapshot())
            lines.append("")
        for section in self.sections:
            lines.append(section.to_markdown())
            lines.append("")
        return "\n".join(lines)

    def _render_timeline_snapshot(self) -> str:
        if not self.timeline_snapshot:
            return ""
        lines = []
        lines.append("## 时间轴概览")
        lines.append("")
        lines.append("| 章节 | 时间段 | 关键事件数 |")
        lines.append("|------|--------|-----------|")
        for chapter in self.timeline_snapshot.get("chapters", []):
            lines.append(f"| {chapter.get('title', '')} | "
                f"{chapter.get('duration', '')} | {chapter.get('event_count', 0)} |")
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "title": self.title, "subtitle": self.subtitle,
            "author": self.author, "date": self.date,
            "executive_summary": self.executive_summary,
            "key_conclusions": self.key_conclusions,
            "risk_warnings": self.risk_warnings,
            "sections": [self._section_to_dict(s) for s in self.sections],
            "timeline_snapshot": self.timeline_snapshot,
        }

    def _section_to_dict(self, section: ReportSection) -> Dict:
        return {
            "title": section.title, "level": section.level,
            "content": section.content, "insights": section.insights,
            "data_points": section.data_points,
            "subsections": [self._section_to_dict(s) for s in section.subsections],
        }


class ReportGenerator:
    # 研究主题类型及其对应报告结构
    REPORT_TEMPLATES = {
        "宏观研究": [
            "宏观经济环境分析",
            "政策与监管动态",
            "市场表现与趋势",
            "风险因素与展望",
        ],
        "行业研究": [
            "产业全景分析",
            "行业竞争格局",
            "重点公司对比",
            "投资建议与风险提示",
        ],
        "公司研究": [
            "公司基本面分析",
            "财务数据解读",
            "竞争优势与护城河",
            "估值与投资建议",
        ],
        "事件分析": [
            "事件背景与起因",
            "影响范围评估",
            "因果链分析",
            "后续展望与应对",
        ],
        "趋势预测": [
            "历史趋势回顾",
            "关键驱动因素",
            "情景分析",
            "时间节点与信号",
        ],
    }

    def __init__(self, timeline_base: TimelineBase):
        self.timeline = timeline_base
        # 加载插件
        from ..plugins import plugin_registry
        self.plugins = plugin_registry

    def generate(self, title: str, author: str = "", topic_type: str = "") -> Report:
        report = Report(title=title, author=author)
        report.timeline_snapshot = self._build_timeline_snapshot()

        # 自动推断主题类型
        if not topic_type:
            topic_type = self._detect_topic_type()

        # 根据主题类型生成对应章节
        sections = self._generate_adaptive_sections(topic_type)
        report.sections = sections

        report.executive_summary = self._generate_executive_summary()
        report.key_conclusions = self._extract_key_conclusions()
        return report

    def _detect_topic_type(self) -> str:
        """根据时间轴数据特征自动推断研究主题类型"""
        events = self.timeline.timeline.get_all_events()
        if not events:
            return "行业研究"  # 默认

        # 统计各类标签出现频率
        tag_counts: Dict[str, int] = {}
        for e in events:
            for tag in e.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # 统计文本中的关键概念
        all_text = " ".join(
            (e.summary or "") + " " + " ".join(e.tags) for e in events
        ).lower()

        # 宏观指标
        macro_keywords = ["gdp", "通胀", "cpi", "ppi", "利率", "央行", "美联储",
                          "货币政策", "财政政策", "pmi", "就业", "失业"]
        macro_score = sum(all_text.count(kw) for kw in macro_keywords)

        # 公司指标
        company_keywords = ["营收", "利润", "财报", "季报", "年报", "净利率",
                            "毛利率", "市盈率", "pe", "估值", "分红"]
        company_score = sum(all_text.count(kw) for kw in company_keywords)

        # 事件指标
        event_keywords = ["事件", "突发", "公告", "声明", "发布会", "裁决",
                          "事故", "丑闻", "暴雷"]
        event_score = sum(all_text.count(kw) for kw in event_keywords)

        # 趋势指标
        trend_keywords = ["预测", "展望", "趋势", "预期", "展望", "前景",
                          "未来", "规划", "目标"]
        trend_score = sum(all_text.count(kw) for kw in trend_keywords)

        scores = {
            "宏观研究": macro_score,
            "公司研究": company_score,
            "事件分析": event_score,
            "趋势预测": trend_score,
            "行业研究": 1,  # 默认基准分
        }
        return max(scores, key=scores.get)

    def _generate_adaptive_sections(self, topic_type: str) -> List[ReportSection]:
        """根据主题类型生成自适应章节"""
        template = self.REPORT_TEMPLATES.get(topic_type, self.REPORT_TEMPLATES["行业研究"])
        sections = []

        for i, section_title in enumerate(template, 1):
            section = ReportSection(
                title=f"{self._to_chinese_num(i)}、{section_title}",
                level=2,
                content=self._generate_section_content(section_title, topic_type),
            )
            # 根据章节标题添加子节
            section.subsections = self._generate_subsections(section_title, i)
            sections.append(section)

        # 添加结论章
        sections.append(ReportSection(
            title=f"{self._to_chinese_num(len(template) + 1)}、结论与建议",
            level=2,
            content="综合以上分析，得出最终研究结论与投资建议。",
        ))

        return sections

    def _generate_section_content(self, section_title: str, topic_type: str) -> str:
        """根据章节标题和数据生成内容摘要（集成插件分析）"""
        events = self.timeline.timeline.get_all_events()
        if not events:
            return "暂无足够数据进行分析。"

        # 运行相关插件
        plugin_insights = self._run_relevant_plugins(section_title, events)

        # 根据章节标题匹配相关事件
        relevant = []
        keywords = section_title.replace("分析", "").replace("与", "").split()
        for e in events:
            text = (e.summary or "") + " " + " ".join(e.tags)
            if any(kw in text for kw in keywords):
                relevant.append(e)

        parts = []
        if relevant:
            summaries = [e.summary for e in relevant[:5] if e.summary]
            parts.append("基于时间轴数据：" + "；".join(summaries) + "。")
        else:
            parts.append(f"基于 {len(events)} 个时间轴数据点进行{section_title}。")

        if plugin_insights:
            parts.append("\n**插件分析洞察：**")
            for insight in plugin_insights:
                parts.append(f"- {insight}")

        return "\n".join(parts)

    def _generate_subsections(self, section_title: str, chapter_num: int) -> List[ReportSection]:
        """为每个主章节生成合理的子节"""
        subsections = []
        events = self.timeline.timeline.get_all_events()
        chapters = self.timeline.timeline.chapters

        if "全景" in section_title or "环境" in section_title:
            if chapters:
                for j, ch in enumerate(chapters[:3], 1):
                    subsections.append(ReportSection(
                        title=f"{chapter_num}.{j} {ch.title}",
                        level=3,
                        content=ch.summary or f"该阶段包含 {len(ch.event_ids)} 个关键事件。",
                    ))

        elif "竞争" in section_title or "格局" in section_title:
            # 从标签中提取竞争主体
            tag_counts: Dict[str, int] = {}
            for e in events:
                for tag in e.tags:
                    if len(tag) > 1:  # 过滤单字符标签
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            for j, (tag, count) in enumerate(top_tags, 1):
                subsections.append(ReportSection(
                    title=f"{chapter_num}.{j} {tag}",
                    level=3,
                    content=f"涉及 {count} 个相关数据点。",
                ))

        elif "情景" in section_title:
            for j, scenario_name in enumerate(["乐观情景", "基准情景", "风险情景"], 1):
                subsections.append(ReportSection(
                    title=f"{chapter_num}.{j} {scenario_name}",
                    level=3,
                    content=f"基于不同假设构建的{scenario_name}分析。",
                ))

        return subsections

    @staticmethod
    def _to_chinese_num(n: int) -> str:
        nums = "一二三四五六七八九十"
        if 1 <= n <= 10:
            return nums[n - 1]
        return str(n)

    def _build_timeline_snapshot(self) -> Dict:
        chapters = []
        for chapter in self.timeline.timeline.chapters:
            event_count = len(self.timeline.timeline.get_chapter_events(chapter.id))
            chapters.append({"title": chapter.title, "duration": chapter.duration_label,
                "event_count": event_count, "summary": chapter.summary})
        return {
            "title": self.timeline.timeline.title,
            "total_events": self.timeline.timeline.get_event_count(),
            "chapters": chapters, "bookmarks": len(self.timeline.timeline.bookmarks),
            "time_range": (
                f"{self.timeline.timeline.start_time.strftime('%Y-%m-%d') if self.timeline.timeline.start_time else '?'}"
                f" → "
                f"{self.timeline.timeline.end_time.strftime('%Y-%m-%d') if self.timeline.timeline.end_time else '?'}"),
        }

    def _run_relevant_plugins(self, section_title: str, events: list) -> List[str]:
        """根据章节标题运行相关插件，返回洞察列表"""
        insights = []
        # 章节标题 → 插件映射
        plugin_map = {
            "宏观": ["pest"],
            "环境": ["pest"],
            "政策": ["pest"],
            "竞争": ["swot"],
            "格局": ["swot"],
            "优势": ["swot"],
            "情景": ["scenario"],
            "周期": ["cycle", "trend"],
            "趋势": ["trend"],
            "风险": ["anomaly"],
            "异常": ["anomaly"],
            "因果": ["correlation"],
            "相关": ["correlation"],
        }
        plugin_names = set()
        for keyword, names in plugin_map.items():
            if keyword in section_title:
                plugin_names.update(names)

        for name in plugin_names:
            plugin = self.plugins.get(name)
            if plugin:
                try:
                    result = plugin.analyze(events)
                    insights.extend(result.insights[:3])  # 最多3条
                except Exception:
                    pass

        return insights

    def _find_chapter_by_tag(self, tag: str) -> Optional[Dict]:
        for chapter in self.timeline.timeline.chapters:
            if tag in chapter.tags:
                events = self.timeline.timeline.get_chapter_events(chapter.id)
                return {
                    "title": chapter.title, "summary": chapter.summary,
                    "data_points": [{"summary": e.summary, "source": e.source}
                        for e in events if e.summary],
                }
        return None

    def _generate_executive_summary(self) -> str:
        total_events = self.timeline.timeline.get_event_count()
        chapter_count = len(self.timeline.timeline.chapters)
        summary_parts = [
            f"本报告基于时间轴研究方法，共收录 {total_events} 个关键数据点，"
            f"划分为 {chapter_count} 个研究章节。"]
        if self.timeline.timeline.chapters:
            latest_chapter = self.timeline.timeline.chapters[-1]
            summary_parts.append(f"当前研究阶段：{latest_chapter.title}。")

        # 插件分析摘要
        events = self.timeline.timeline.get_all_events()
        plugin_summaries = []
        for name in ["pest", "swot", "cycle", "anomaly"]:
            plugin = self.plugins.get(name)
            if plugin:
                try:
                    result = plugin.analyze(events)
                    if result.insights:
                        plugin_summaries.append(f"{result.category}: {result.insights[0]}")
                except Exception:
                    pass
        if plugin_summaries:
            summary_parts.append(" 插件分析发现：" + "；".join(plugin_summaries) + "。")

        return "".join(summary_parts)

    def _extract_key_conclusions(self) -> List[str]:
        conclusions = []
        events = self.timeline.timeline.get_all_events()
        prediction_events = [e for e in events if e.time_type.value == "predicted"]
        if prediction_events:
            conclusions.append(f"基于时间轴预测，未来有 {len(prediction_events)} 个关键节点需要关注。")
        chapters = self.timeline.timeline.chapters
        if chapters:
            conclusions.append(f"研究覆盖 {chapters[0].duration_label} 至 "
                f"{chapters[-1].duration_label}，共 {len(chapters)} 个发展阶段。")
        if not conclusions:
            conclusions.append("研究数据正在收集中，结论将随数据完善而更新。")
        return conclusions

    def export_markdown(self, report: Report, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())

    def export_json(self, report: Report, filepath: str):
        import json
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
