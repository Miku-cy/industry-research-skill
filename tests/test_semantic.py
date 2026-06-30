"""semantic.py 单元测试

测试范围：
- classify (heuristic 模式): 关键词分类
- _expand_semantic_phrases: 短语展开
- _infer_pest_scores / _infer_swot_scores: PEST/SWOT 推断
- classify_batch: 批量分类
- _extract_json_from_text: JSON 提取
- _parse_llm_result: LLM 结果解析
- _load_config / _extract_config: 配置加载
- enhance_pest / enhance_swot: PEST/SWOT 增强
"""
import json
import os
import sys
import tempfile
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.timeline import TimelineEvent
from src.core.analyzer import PESTResult, SWOTResult
from src.core.semantic import SemanticClassifier, SemanticScores


# ─── fixtures ───

def _event(summary, tags=None, data=None):
    return TimelineEvent(
        timestamp=datetime(2024, 1, 1),
        summary=summary,
        tags=tags or [],
        source="test",
        data=data or {},
    )


@pytest.fixture
def classifier():
    return SemanticClassifier(mode="heuristic")


# ─── classify (heuristic) ───

class TestClassifyHeuristic:
    def test_policy_event(self, classifier):
        e = _event("央行宣布加息", tags=["货币政策"])
        scores = classifier.classify(e)
        assert scores.chapter_label == "政策驱动"
        assert scores.confidence > 0

    def test_market_event(self, classifier):
        e = _event("股市大幅反弹", tags=["价格"])
        scores = classifier.classify(e)
        assert scores.chapter_label == "市场波动"

    def test_tech_event(self, classifier):
        e = _event("AI技术突破", tags=["创新"])
        scores = classifier.classify(e)
        assert scores.chapter_label == "技术突破"

    def test_finance_event(self, classifier):
        e = _event("财报显示营收增长30%", tags=["利润"])
        scores = classifier.classify(e)
        assert scores.chapter_label == "财务表现"

    def test_risk_event(self, classifier):
        e = _event("公司暴雷", tags=["风险"])
        scores = classifier.classify(e)
        assert scores.chapter_label == "风险事件"

    def test_no_match_default(self, classifier):
        e = _event("今天天气不错")
        scores = classifier.classify(e)
        assert scores.chapter_label == "一般事件"
        assert scores.confidence == 0.0

    def test_multiple_keywords_higher_confidence(self, classifier):
        e = _event("央行加息", tags=["政策", "监管", "审批"])
        scores = classifier.classify(e)
        assert scores.confidence > 0.5


# ─── _expand_semantic_phrases ───

class TestExpandSemanticPhrases:
    def test_expands_known_phrase(self, classifier):
        result = classifier._expand_semantic_phrases("收紧货币政策")
        assert "加息" in result

    def test_expands_economic_downturn(self, classifier):
        result = classifier._expand_semantic_phrases("经济衰退")
        assert "衰退" in result

    def test_no_expansion_for_unknown(self, classifier):
        result = classifier._expand_semantic_phrases("普通文本")
        assert result == "普通文本"

    def test_multiple_phrases(self, classifier):
        result = classifier._expand_semantic_phrases("收紧货币政策，经济衰退")
        assert "加息" in result
        assert "衰退" in result


# ─── _infer_pest_scores ───

class TestInferPestScores:
    def test_political_keywords(self, classifier):
        scores = classifier._infer_pest_scores("政策监管央行")
        assert scores["political"] > 0

    def test_economic_keywords(self, classifier):
        scores = classifier._infer_pest_scores("GDP通胀利率")
        assert scores["economic"] > 0

    def test_technological_keywords(self, classifier):
        scores = classifier._infer_pest_scores("AI技术芯片")
        assert scores["technological"] > 0

    def test_empty_text(self, classifier):
        scores = classifier._infer_pest_scores("")
        assert all(v == 0 for v in scores.values())

    def test_max_cap_at_one(self, classifier):
        # 超过3个关键词应封顶在1.0
        scores = classifier._infer_pest_scores("政策 监管 审批 央行 美联储 政府 法律")
        assert scores["political"] <= 1.0


# ─── _infer_swot_scores ───

class TestInferSwotScores:
    def test_strengths(self, classifier):
        scores = classifier._infer_swot_scores("增长突破领先利好")
        assert scores["strengths"] > 0

    def test_weaknesses(self, classifier):
        scores = classifier._infer_swot_scores("亏损下降裁员")
        assert scores["weaknesses"] > 0

    def test_opportunities(self, classifier):
        scores = classifier._infer_swot_scores("机会复苏蓝海")
        assert scores["opportunities"] > 0

    def test_threats(self, classifier):
        scores = classifier._infer_swot_scores("威胁竞争危机")
        assert scores["threats"] > 0


# ─── classify_batch ───

class TestClassifyBatch:
    def test_batch_returns_list(self, classifier):
        events = [_event("加息"), _event("暴跌")]
        results = classifier.classify_batch(events)
        assert len(results) == 2
        assert all(isinstance(r, SemanticScores) for r in results)

    def test_empty_batch(self, classifier):
        assert classifier.classify_batch([]) == []


# ─── _extract_json_from_text ───

class TestExtractJsonFromText:
    def test_json_in_code_block(self):
        text = '```json\n{"key": "value"}\n```'
        result = SemanticClassifier._extract_json_from_text(text)
        assert result == {"key": "value"}

    def test_bare_json(self):
        text = '结果：{"chapter_label": "test", "confidence": 0.8}'
        result = SemanticClassifier._extract_json_from_text(text)
        assert result["chapter_label"] == "test"

    def test_no_json(self):
        result = SemanticClassifier._extract_json_from_text("纯文本")
        assert result == {}

    def test_invalid_json(self):
        result = SemanticClassifier._extract_json_from_text("{broken json}")
        assert result == {}


# ─── _parse_llm_result ───

class TestParseLlmResult:
    def test_valid_result(self, classifier):
        result = {
            "pest_scores": {"political": 0.8},
            "swot_scores": {"strengths": 0.6},
            "chapter_label": "政策驱动",
            "confidence": 0.9,
            "causal_concepts": ["加息"],
        }
        scores = classifier._parse_llm_result(result)
        assert scores.chapter_label == "政策驱动"
        assert scores.confidence == 0.9
        assert scores.causal_concepts == ["加息"]

    def test_empty_result(self, classifier):
        scores = classifier._parse_llm_result({})
        assert scores.chapter_label == ""
        assert scores.confidence == 0.0


# ─── _load_config / _extract_config ───

class TestLoadConfig:
    def test_no_config(self, classifier):
        config = SemanticClassifier._load_config("")
        assert config == {}

    def test_extract_config_valid(self):
        data = {
            "semantic": {
                "mode": "api",
                "ollama": {"model": "test", "url": "http://test"},
                "api": {"url": "http://api", "key": "abc", "model": "gpt"},
            }
        }
        config = SemanticClassifier._extract_config(data)
        assert config["mode"] == "api"
        assert config["ollama_model"] == "test"
        assert config["api_url"] == "http://api"

    def test_extract_config_empty(self):
        assert SemanticClassifier._extract_config({}) == {}

    def test_extract_config_minimal(self):
        data = {"semantic": {"mode": "heuristic"}}
        config = SemanticClassifier._extract_config(data)
        assert config["mode"] == "heuristic"


# ─── enhance_pest / enhance_swot ───

class TestEnhancePest:
    def test_adds_to_pest(self, classifier):
        e1 = _event("央行宣布加息", tags=["政策"])
        e2 = _event("GDP增长超预期", tags=["经济"])
        base = PESTResult(
            political=[], economic=[], social=[], technological=[]
        )
        result = classifier.enhance_pest([e1, e2], base)
        assert len(result.political) > 0 or len(result.economic) > 0

    def test_skips_low_confidence(self, classifier):
        e = _event("普通事件", tags=[])
        base = PESTResult(
            political=[], economic=[], social=[], technological=[]
        )
        result = classifier.enhance_pest([e], base)
        # 低置信度事件不应被添加
        total = (len(result.political) + len(result.economic) +
                 len(result.social) + len(result.technological))
        assert total == 0

    def test_deduplicates(self, classifier):
        e = _event("央行加息", tags=["政策"])
        base = PESTResult(
            political=["央行加息"], economic=[], social=[], technological=[]
        )
        result = classifier.enhance_pest([e], base)
        # 不应重复添加
        assert result.political.count("央行加息") == 1


class TestEnhanceSwot:
    def test_adds_to_swot(self, classifier):
        e = _event("营收增长超预期", tags=["利好"])
        base = SWOTResult(
            strengths=[], weaknesses=[], opportunities=[], threats=[]
        )
        result = classifier.enhance_swot([e], base)
        assert len(result.strengths) > 0

    def test_threat_event(self, classifier):
        e = _event("美联储加息", tags=["威胁"])
        base = SWOTResult(
            strengths=[], weaknesses=[], opportunities=[], threats=[]
        )
        result = classifier.enhance_swot([e], base)
        assert len(result.threats) > 0


# ─── SemanticScores ───

class TestSemanticScores:
    def test_default_values(self):
        s = SemanticScores()
        assert s.pest_scores == {}
        assert s.swot_scores == {}
        assert s.chapter_label == ""
        assert s.confidence == 0.0
        assert s.causal_concepts == []
