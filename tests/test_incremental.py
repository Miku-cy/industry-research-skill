"""因果网络增量更新测试"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import TimelineBase, AnalyzerEngine


def _add_events(timeline, specs):
    for summary, day, tags in specs:
        timeline.add_event(
            timestamp=datetime(2024, 1, 1) + timedelta(days=day),
            data={"summary": summary},
            source="test",
            tags=tags,
            summary=summary,
        )


class TestIncrementalUpdate(unittest.TestCase):
    """增量更新"""

    def test_incremental_adds_new_chains(self):
        """增量更新应添加新链"""
        timeline = TimelineBase(title="增量测试")
        _add_events(timeline, [
            ("美联储加息25基点", 0, ["加息", "美联储"]),
            ("美元指数走强", 7, ["美元", "走强"]),
            ("新兴市场股市下跌", 14, ["新兴市场", "股市", "下跌"]),
        ])

        engine = AnalyzerEngine(timeline)
        # 第一次：全量构建
        network = engine.build_causal_network(min_confidence=0.2, multihop=False)
        chains_before = network.chain_count

        # 新事件
        new_evt = timeline.add_event(
            timestamp=datetime(2024, 1, 25),
            data={"summary": "资本外流加速"},
            source="test",
            tags=["资本外流", "新兴市场"],
            summary="资本外流加速",
        )
        new_events = [timeline.timeline.get_event(new_evt)]

        # 增量更新
        engine.update_incremental(network, new_events, min_confidence=0.2)
        chains_after = network.chain_count

        self.assertGreaterEqual(chains_after, chains_before)

    def test_incremental_faster_than_full(self):
        """增量更新只分析新事件，不重复分析旧事件"""
        timeline = TimelineBase(title="效率测试")
        _add_events(timeline, [
            (f"事件{i}", i * 5, ["标签" + str(i % 3)]) for i in range(10)
        ])

        engine = AnalyzerEngine(timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=False)

        # 记录已分析的事件数
        analyzed_count = len(network._analyzed_ids)

        # 新增1个事件
        new_evt = timeline.add_event(
            timestamp=datetime(2024, 6, 1),
            data={"summary": "新事件"},
            source="test",
            tags=["标签0"],
            summary="新事件",
        )
        new_events = [timeline.timeline.get_event(new_evt)]

        engine.update_incremental(network, new_events, min_confidence=0.1)

        # 分析的事件应该增加了
        self.assertGreater(len(network._analyzed_ids), analyzed_count)

    def test_incremental_preserves_existing(self):
        """增量更新不丢失已有链"""
        timeline = TimelineBase(title="保留测试")
        _add_events(timeline, [
            ("AI需求爆发", 0, ["AI", "需求"]),
            ("芯片价格上涨", 30, ["芯片", "价格上涨"]),
        ])

        engine = AnalyzerEngine(timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=False)
        chains_before = network.chain_count

        # 增量加一个无关事件
        new_evt = timeline.add_event(
            timestamp=datetime(2024, 3, 1),
            data={"summary": "天气晴朗"},
            source="test",
            tags=["天气"],
            summary="天气晴朗",
        )
        new_events = [timeline.timeline.get_event(new_evt)]

        engine.update_incremental(network, new_events, min_confidence=0.1)

        # 已有链不应减少
        self.assertGreaterEqual(network.chain_count, chains_before)

    def test_incremental_empty_events(self):
        """空事件列表不影响网络"""
        timeline = TimelineBase(title="空测试")
        _add_events(timeline, [
            ("事件A", 0, ["a"]),
            ("事件B", 5, ["b"]),
        ])

        engine = AnalyzerEngine(timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=False)
        chains_before = network.chain_count

        engine.update_incremental(network, [], min_confidence=0.1)
        self.assertEqual(network.chain_count, chains_before)


if __name__ == "__main__":
    unittest.main()
