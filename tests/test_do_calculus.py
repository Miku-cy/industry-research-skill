"""do-calculus 反事实分析测试"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import TimelineBase, AnalyzerEngine
from src.core.counterfactual import CounterfactualAnalyzer


def _add_events(timeline, specs):
    for summary, day, tags in specs:
        timeline.add_event(
            timestamp=datetime(2024, 1, 1) + timedelta(days=day),
            data={"summary": summary},
            source="test",
            tags=tags,
            summary=summary,
        )


class TestDoCalculus(unittest.TestCase):
    """do-calculus 反事实分析"""

    def setUp(self):
        # 场景：加息→股市下跌，但也有地缘冲突→股市下跌
        self.timeline = TimelineBase(title="do-calculus测试")
        _add_events(self.timeline, [
            ("美联储加息25基点", 0, ["加息", "美联储"]),
            ("地缘冲突升级", 5, ["冲突", "地缘"]),
            ("美元走强", 7, ["美元", "走强"]),
            ("股市全线下跌", 14, ["股市", "下跌"]),
        ])
        engine = AnalyzerEngine(self.timeline)
        self.network = engine.build_causal_network(min_confidence=0.15, multihop=True)

    def test_do_calculus_method(self):
        """do-calculus 方法可用"""
        analyzer = CounterfactualAnalyzer(self.network)
        # 找到加息和股市下跌的ID
        cause_id = None
        effect_id = None
        for eid, evt in self.network._events.items():
            if "加息" in evt.summary:
                cause_id = eid
            if "股市" in evt.summary and "下跌" in evt.summary:
                effect_id = eid

        if cause_id and effect_id:
            result = analyzer.analyze(cause_id, effect_id, method="do_calculus")
            self.assertEqual(result.method, "do_calculus")
            self.assertGreater(len(result.paths_cut), 0, "应有被切断的路径")
            print(f"  P(B|A)={result.p_effect_given_cause:.2f}")
            print(f"  P(B|do(¬A))={result.p_effect_given_no_cause:.2f}")
            print(f"  因果效应={result.causal_effect:.2f}")
            print(f"  切断路径: {result.paths_cut}")
            print(f"  结论: {result.conclusion}")

    def test_do_vs_simple_comparison(self):
        """do-calculus 与简化版结果可能不同"""
        analyzer = CounterfactualAnalyzer(self.network)
        cause_id = None
        effect_id = None
        for eid, evt in self.network._events.items():
            if "加息" in evt.summary:
                cause_id = eid
            if "股市" in evt.summary and "下跌" in evt.summary:
                effect_id = eid

        if cause_id and effect_id:
            result_do = analyzer.analyze(cause_id, effect_id, method="do_calculus")
            result_simple = analyzer.analyze(cause_id, effect_id, method="simple")
            # do-calculus 应该检测到混杂（地缘冲突同时影响加息预期和股市）
            self.assertEqual(result_do.method, "do_calculus")
            self.assertEqual(result_simple.method, "simple")
            # do-calculus 的 P(B|do(¬A)) 可能高于简化版（因为考虑了独立路径）
            print(f"  do: P(B|do(¬A))={result_do.p_effect_given_no_cause:.2f}")
            print(f"  simple: P(B|¬A)={result_simple.p_effect_given_no_cause:.2f}")

    def test_do_calculus_no_confounding(self):
        """无混杂时 do-calculus 和简化版结果一致"""
        timeline = TimelineBase(title="无混杂")
        _add_events(timeline, [
            ("原因A", 0, ["a"]),
            ("结果B", 10, ["b"]),
        ])
        engine = AnalyzerEngine(timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=False)

        analyzer = CounterfactualAnalyzer(network)
        cause_id = list(network._events.keys())[0]
        effect_id = list(network._events.keys())[1]

        result_do = analyzer.analyze(cause_id, effect_id, "do_calculus")
        result_simple = analyzer.analyze(cause_id, effect_id, "simple")

        # 无混杂时两者应该接近
        self.assertAlmostEqual(
            result_do.p_effect_given_no_cause,
            result_simple.p_effect_given_no_cause,
            delta=0.2,
        )

    def test_paths_cut_identified(self):
        """do-calculus 应识别并报告被切断的路径"""
        analyzer = CounterfactualAnalyzer(self.network)
        for eid, evt in self.network._events.items():
            if "加息" in evt.summary:
                result = analyzer.analyze(eid, list(self.network._events.keys())[-1], "do_calculus")
                if result.paths_cut:
                    self.assertTrue(
                        any("混杂" in p or "直接" in p or "中介" in p for p in result.paths_cut),
                        f"路径描述应含类型标签: {result.paths_cut}"
                    )
                break


class TestDoCalculusBySummary(unittest.TestCase):
    """通过摘要调用 do-calculus"""

    def test_by_summary(self):
        timeline = TimelineBase(title="摘要测试")
        _add_events(timeline, [
            ("OPEC宣布减产", 0, ["OPEC", "减产"]),
            ("油价飙升", 7, ["油价", "上涨"]),
        ])
        engine = AnalyzerEngine(timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=False)

        analyzer = CounterfactualAnalyzer(network)
        result = analyzer.analyze_by_summary("OPEC减产", "油价", method="do_calculus")
        self.assertEqual(result.method, "do_calculus")
        self.assertNotEqual(result.conclusion, "")


if __name__ == "__main__":
    unittest.main()
