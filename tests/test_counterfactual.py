"""counterfactual.py 单元测试

测试范围：
- CounterfactualAnalyzer: analyze, analyze_by_summary, batch_analyze
- _find_direct_chain, _estimate_p_without_cause, _generate_conclusion, _error_result
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.timeline import TimelineEvent
from src.core.analyzer import CausalChain, CausalNetwork
from src.core.counterfactual import CounterfactualAnalyzer, CounterfactualResult


# ─── helpers ───

def _event(eid, summary, days_offset=0):
    e = TimelineEvent(
        timestamp=datetime(2024, 1, 1) + timedelta(days=days_offset),
        summary=summary,
        tags=[],
        source="test",
    )
    e.id = eid
    return e


def _chain(cause, effect, confidence=0.8, desc=""):
    return CausalChain(
        cause_event=cause,
        effect_event=effect,
        time_gap=effect.timestamp - cause.timestamp,
        confidence=confidence,
        description=desc or f"{cause.summary} → {effect.summary}",
    )


def _build_network():
    """构建一个测试因果网络：A→B→D, C→D"""
    a = _event("A", "加息", 0)
    b = _event("B", "流动性收紧", 1)
    c = _event("C", "地缘冲突", 2)
    d = _event("D", "市场暴跌", 3)

    net = CausalNetwork()
    net.add_chain(_chain(a, b, 0.9))
    net.add_chain(_chain(b, d, 0.8))
    net.add_chain(_chain(c, d, 0.6))

    return net, a, b, c, d


# ─── analyze ───

class TestAnalyze:
    def test_direct_chain_exists(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        result = analyzer.analyze(a.id, b.id)
        assert result.cause_event == "加息"
        assert result.effect_event == "流动性收紧"
        assert result.p_effect_given_cause == pytest.approx(0.9)
        assert result.confidence > 0

    def test_indirect_chain(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        # A→D 是间接链（通过 B），没有直接链
        result = analyzer.analyze(a.id, d.id)
        assert result.cause_event == "加息"
        assert result.effect_event == "市场暴跌"
        # 没有直接链，p_effect_given_cause 应该是 0
        assert result.p_effect_given_cause == 0.0

    def test_alternative_causes(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        # D 有两个原因：B 和 C
        result = analyzer.analyze(b.id, d.id)
        assert "地缘冲突" in result.alternative_causes

    def test_nonexistent_event(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        result = analyzer.analyze("nonexistent", d.id)
        assert result.confidence == 0
        assert "不存在" in result.conclusion

    def test_causal_effect_positive(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        result = analyzer.analyze(b.id, d.id)
        # B→D 有直接链，D 有替代原因 C
        assert result.causal_effect > 0


# ─── _find_direct_chain ───

class TestFindDirectChain:
    def test_existing_chain(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        chain = analyzer._find_direct_chain(a.id, b.id)
        assert chain is not None
        assert chain.confidence == pytest.approx(0.9)

    def test_missing_chain(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        chain = analyzer._find_direct_chain(a.id, d.id)
        assert chain is None


# ─── _estimate_p_without_cause ───

class TestEstimatePWithoutCause:
    def test_no_alternatives(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        p = analyzer._estimate_p_without_cause(a.id, b.id, [])
        assert p == 0.1  # 保留不确定性

    def test_single_alternative(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        alt = [c]  # C 是 D 的替代原因
        p = analyzer._estimate_p_without_cause(b.id, d.id, alt)
        assert p == pytest.approx(0.6)  # C→D 的置信度

    def test_multiple_alternatives(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        # 添加更多替代原因
        e = _event("E", "新因素", 1)
        net.add_chain(_chain(e, d, 0.5))
        alts = [c, e]
        p = analyzer._estimate_p_without_cause(b.id, d.id, alts)
        # 联合概率 = 1 - (1-0.6)*(1-0.5) = 1 - 0.2 = 0.8
        assert p == pytest.approx(0.8, abs=0.01)


# ─── _generate_conclusion ───

class TestGenerateConclusion:
    def test_strong_causal_low_alternative(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        conclusion = analyzer._generate_conclusion(a, b, 0.9, 0.1, 0.8, [])
        assert "强因果" in conclusion
        assert "关键原因" in conclusion

    def test_strong_causal_with_alternatives(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        conclusion = analyzer._generate_conclusion(b, d, 0.9, 0.3, 0.6, [c])
        assert "强因果" in conclusion
        assert "主因" in conclusion

    def test_moderate_causal(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        conclusion = analyzer._generate_conclusion(a, d, 0.5, 0.3, 0.3, [b])
        assert "中等因果" in conclusion

    def test_weak_causal(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        conclusion = analyzer._generate_conclusion(a, d, 0.3, 0.25, 0.05, [])
        assert "弱因果" in conclusion

    def test_no_significant_effect(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        conclusion = analyzer._generate_conclusion(a, d, 0.3, 0.3, 0.0, [])
        assert "无显著因果效应" in conclusion


# ─── _error_result ───

class TestErrorResult:
    def test_error_result_fields(self):
        net = CausalNetwork()
        analyzer = CounterfactualAnalyzer(net)
        result = analyzer._error_result("测试错误")
        assert result.conclusion == "测试错误"
        assert result.confidence == 0
        assert result.causal_effect == 0


# ─── analyze_by_summary ───

class TestAnalyzeBySummary:
    def test_exact_match(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        result = analyzer.analyze_by_summary("加息", "流动性收紧")
        assert result.cause_event == "加息"
        assert result.effect_event == "流动性收紧"

    def test_partial_match(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        result = analyzer.analyze_by_summary("加", "流动")
        # 摘要包含关系
        assert result.cause_event == "加息"

    def test_no_match(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        result = analyzer.analyze_by_summary("不存在的事件", "也不存在")
        assert result.confidence == 0
        assert "未找到" in result.conclusion


# ─── batch_analyze ───

class TestBatchAnalyze:
    def test_returns_all_chains(self):
        net, a, b, c, d = _build_network()
        analyzer = CounterfactualAnalyzer(net)
        results = analyzer.batch_analyze()
        assert len(results) >= 3  # A→B, B→D, C→D

    def test_filters_low_confidence(self):
        net = CausalNetwork()
        a = _event("A", "弱事件", 0)
        b = _event("B", "结果", 1)
        net.add_chain(_chain(a, b, confidence=0.05))  # 低置信度

        analyzer = CounterfactualAnalyzer(net)
        results = analyzer.batch_analyze()
        assert len(results) == 0  # 被过滤

    def test_empty_network(self):
        net = CausalNetwork()
        analyzer = CounterfactualAnalyzer(net)
        results = analyzer.batch_analyze()
        assert results == []
