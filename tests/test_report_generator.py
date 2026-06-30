"""report_generator.py 单元测试

测试范围：
- ReportSection: to_markdown
- Report: to_markdown, to_dict
- ReportGenerator: generate, _detect_topic_type, _to_chinese_num, export
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.timeline import TimelineBase, TimelineEvent
from src.core.report_generator import Report, ReportSection, ReportGenerator


# ─── fixtures ───

def _make_timeline_with_events():
    tb = TimelineBase(title="测试时间轴")
    for i in range(5):
        tb.add_event(
            timestamp=datetime(2024, 1, 1) + timedelta(days=i * 30),
            data={},
            summary=f"事件{i+1}",
            tags=["测试", f"tag{i}"],
            source="test",
        )
    return tb


@pytest.fixture
def report():
    return Report(
        title="测试报告",
        subtitle="副标题",
        author="测试",
        executive_summary="这是摘要",
        key_conclusions=["结论1", "结论2"],
        risk_warnings=["风险1"],
    )


@pytest.fixture
def generator():
    return ReportGenerator(_make_timeline_with_events())


# ─── ReportSection ───

class TestReportSection:
    def test_to_markdown_basic(self):
        section = ReportSection(title="测试章节", level=2, content="内容")
        md = section.to_markdown()
        assert "## 测试章节" in md
        assert "内容" in md

    def test_to_markdown_with_insights(self):
        section = ReportSection(title="洞察", level=2, insights=["洞察1", "洞察2"])
        md = section.to_markdown()
        assert "核心洞察" in md
        assert "- 洞察1" in md

    def test_to_markdown_with_subsections(self):
        sub = ReportSection(title="子节", level=3, content="子内容")
        section = ReportSection(title="父节", level=2, subsections=[sub])
        md = section.to_markdown()
        assert "父节" in md
        assert "子节" in md

    def test_heading_level(self):
        section = ReportSection(title="一级", level=1)
        md = section.to_markdown()
        assert md.startswith("# ")

    def test_max_heading_level(self):
        section = ReportSection(title="深层", level=10)
        md = section.to_markdown()
        # 不应超过 h6
        assert "#######" not in md


# ─── Report ───

class TestReport:
    def test_to_markdown_basic(self, report):
        md = report.to_markdown()
        assert "# 测试报告" in md
        assert "副标题" in md
        assert "作者：测试" in md

    def test_to_markdown_executive_summary(self, report):
        md = report.to_markdown()
        assert "核心摘要" in md
        assert "这是摘要" in md

    def test_to_markdown_conclusions(self, report):
        md = report.to_markdown()
        assert "核心结论" in md
        assert "1. 结论1" in md
        assert "2. 结论2" in md

    def test_to_markdown_risk_warnings(self, report):
        md = report.to_markdown()
        assert "风险提示" in md
        assert "⚠️ 风险1" in md

    def test_to_dict(self, report):
        d = report.to_dict()
        assert d["title"] == "测试报告"
        assert d["author"] == "测试"
        assert len(d["key_conclusions"]) == 2

    def test_to_markdown_with_timeline_snapshot(self, report):
        report.timeline_snapshot = {
            "chapters": [
                {"title": "第一阶段", "duration": "30天", "event_count": 5}
            ]
        }
        md = report.to_markdown()
        assert "时间轴概览" in md
        assert "第一阶段" in md

    def test_to_markdown_minimal(self):
        r = Report(title="最小报告")
        md = r.to_markdown()
        assert "# 最小报告" in md
        # 不应崩溃

    def test_to_dict_roundtrip(self, report):
        d = report.to_dict()
        assert isinstance(d, dict)
        assert d["title"] == report.title
        assert d["risk_warnings"] == report.risk_warnings


# ─── ReportGenerator ───

class TestReportGenerator:
    def test_generate_basic(self, generator):
        report = generator.generate("测试报告", author="测试")
        assert report.title == "测试报告"
        assert report.author == "测试"
        assert len(report.sections) > 0
        assert report.executive_summary != ""

    def test_generate_with_topic_type(self, generator):
        report = generator.generate("报告", topic_type="宏观研究")
        assert any("宏观" in s.title for s in report.sections)

    def test_generate_event_analysis(self, generator):
        report = generator.generate("报告", topic_type="事件分析")
        assert any("事件" in s.title or "因果" in s.title for s in report.sections)

    def test_generate_company_research(self, generator):
        report = generator.generate("报告", topic_type="公司研究")
        assert any("公司" in s.title or "基本" in s.title for s in report.sections)

    def test_timeline_snapshot(self, generator):
        report = generator.generate("报告")
        assert report.timeline_snapshot is not None
        assert report.timeline_snapshot["total_events"] == 5

    def test_key_conclusions(self, generator):
        report = generator.generate("报告")
        assert len(report.key_conclusions) > 0


# ─── _detect_topic_type ───

class TestDetectTopicType:
    def test_macro_detection(self):
        tb = TimelineBase()
        tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="GDP增长", tags=["通胀", "央行"])
        tb.add_event(timestamp=datetime(2024, 2, 1), data={}, summary="CPI数据", tags=["利率"])
        gen = ReportGenerator(tb)
        assert gen._detect_topic_type() == "宏观研究"

    def test_company_detection(self):
        tb = TimelineBase()
        tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="财报发布", tags=["营收", "利润"])
        gen = ReportGenerator(tb)
        assert gen._detect_topic_type() == "公司研究"

    def test_event_detection(self):
        tb = TimelineBase()
        tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="突发事件", tags=["公告"])
        gen = ReportGenerator(tb)
        assert gen._detect_topic_type() == "事件分析"

    def test_default_to_industry(self):
        tb = TimelineBase()
        gen = ReportGenerator(tb)
        assert gen._detect_topic_type() == "行业研究"


# ─── _to_chinese_num ───

class TestToChineseNum:
    def test_1_to_10(self):
        assert ReportGenerator._to_chinese_num(1) == "一"
        assert ReportGenerator._to_chinese_num(5) == "五"
        assert ReportGenerator._to_chinese_num(10) == "十"

    def test_out_of_range(self):
        assert ReportGenerator._to_chinese_num(11) == "11"
        assert ReportGenerator._to_chinese_num(0) == "0"


# ─── export ───

class TestExport:
    def test_export_markdown(self, generator, report):
        path = tempfile.mktemp(suffix=".md")
        try:
            generator.export_markdown(report, path)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "# 测试报告" in content
        finally:
            os.unlink(path)

    def test_export_json(self, generator, report):
        path = tempfile.mktemp(suffix=".json")
        try:
            generator.export_json(report, path)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["title"] == "测试报告"
        finally:
            os.unlink(path)
