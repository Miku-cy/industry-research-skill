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
    def __init__(self, timeline_base: TimelineBase):
        self.timeline = timeline_base

    def generate(self, title: str, author: str = "") -> Report:
        report = Report(title=title, author=author)
        report.timeline_snapshot = self._build_timeline_snapshot()
        report.sections.append(self._build_macro_section())
        report.sections.append(self._build_meso_section())
        report.sections.append(self._build_micro_section())
        report.sections.append(self._build_conclusion_section())
        report.executive_summary = self._generate_executive_summary()
        report.key_conclusions = self._extract_key_conclusions()
        return report

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

    def _build_macro_section(self) -> ReportSection:
        section = ReportSection(title="一、宏观层面：产业全景分析", level=2,
            content="基于时间轴上的宏观数据进行产业全景分析。")
        chapter_data = self._find_chapter_by_tag("宏观")
        if chapter_data:
            section.subsections.append(ReportSection(title="1.1 行业规模与增长", level=3,
                content=chapter_data.get("summary", "暂无数据"),
                data_points=chapter_data.get("data_points", [])))
        section.subsections.append(ReportSection(title="1.2 政策环境分析", level=3,
            content="基于时间轴上的政策事件进行分析。"))
        section.subsections.append(ReportSection(title="1.3 行业趋势判断", level=3,
            content="综合宏观数据与政策环境，识别行业发展趋势。"))
        return section

    def _build_meso_section(self) -> ReportSection:
        return ReportSection(title="二、中观层面：行业竞争与公司对比", level=2,
            content="在行业全景的基础上，聚焦上市公司层面的对比分析。",
            subsections=[
                ReportSection(title="2.1 上市公司财务对比", level=3,
                    content="对比主要上市游戏公司的关键财务指标。"),
                ReportSection(title="2.2 竞争格局分析", level=3,
                    content="分析行业竞争格局与市场份额分布。"),
            ])

    def _build_micro_section(self) -> ReportSection:
        return ReportSection(title="三、微观层面：目标公司深度分析", level=2,
            content="聚焦目标公司的基本面与投资价值分析。",
            subsections=[
                ReportSection(title="3.1 公司基本面", level=3,
                    content="分析公司财务状况、产品矩阵与管理团队。"),
                ReportSection(title="3.2 SWOT分析", level=3,
                    content="基于时间轴数据，识别公司优势、劣势、机会与威胁。"),
                ReportSection(title="3.3 情景分析与估值", level=3,
                    content="构建乐观/基准/风险三种情景，给出投资建议。"),
            ])

    def _build_conclusion_section(self) -> ReportSection:
        return ReportSection(title="四、结论与建议", level=2,
            content="综合宏观、中观、微观三个层面的分析，得出最终结论。")

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
