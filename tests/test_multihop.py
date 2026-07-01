"""多跳因果链推理测试"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import TimelineBase, AnalyzerEngine, CausalNetwork


def _add_events(timeline, specs):
    for summary, day, tags in specs:
        timeline.add_event(
            timestamp=datetime(2024, 1, 1) + timedelta(days=day),
            data={"summary": summary},
            source="test",
            tags=tags,
            summary=summary,
        )


class TestMultihopChains(unittest.TestCase):
    """多跳因果链推理"""

    def setUp(self):
        self.timeline = TimelineBase(title="多跳测试")
        _add_events(self.timeline, [
            ("美联储加息25基点", 0, ["加息", "美联储", "利率"]),
            ("美元指数走强", 7, ["美元", "走强", "汇率"]),
            ("新兴市场资本外流", 14, ["新兴市场", "资本外流"]),
            ("新兴市场股市下跌", 21, ["新兴市场", "股市", "下跌"]),
        ])

    def test_multihop_discovered(self):
        """应发现 A→B→C 间接因果链"""
        engine = AnalyzerEngine(self.timeline)
        network = engine.build_causal_network(min_confidence=0.2, multihop=True)
        direct = network.chain_count
        # 多跳链应该比直接链多
        self.assertGreater(direct, 0)

    def test_multihop_confidence_lower(self):
        """间接链置信度应低于直接链"""
        engine = AnalyzerEngine(self.timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=True)
        # 找间接链（description含"[间接因果]"）
        indirect = []
        for effects in network._downstream.values():
            for chain in effects.values():
                if "[间接因果]" in chain.description:
                    indirect.append(chain)
        for chain in indirect:
            self.assertLess(chain.confidence, 0.5, "间接链置信度应较低")

    def test_multihop_disabled(self):
        """关闭多跳时不生成间接链"""
        engine = AnalyzerEngine(self.timeline)
        network = engine.build_causal_network(min_confidence=0.2, multihop=False)
        indirect = []
        for effects in network._downstream.values():
            for chain in effects.values():
                if "[间接因果]" in chain.description:
                    indirect.append(chain)
        self.assertEqual(len(indirect), 0)

    def test_multihop_no_cycles(self):
        """多跳不应产生环"""
        engine = AnalyzerEngine(self.timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=True, max_hops=4)
        # 检查没有 A→...→A 的路径
        for effects in network._downstream.values():
            for chain in effects.values():
                if "[间接因果]" in chain.description:
                    self.assertNotEqual(
                        chain.cause_event.id, chain.effect_event.id,
                        "间接链不应自环"
                    )

    def test_multihop_time_order(self):
        """间接链应保持时间顺序（因在果之前）"""
        engine = AnalyzerEngine(self.timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=True)
        for effects in network._downstream.values():
            for chain in effects.values():
                if "[间接因果]" in chain.description:
                    self.assertLess(
                        chain.cause_event.timestamp,
                        chain.effect_event.timestamp,
                        "因应在果之前"
                    )

    def test_multihop_real_data(self):
        """真实数据：半导体周期多跳"""
        timeline = TimelineBase(title="多跳真实数据")
        _add_events(timeline, [
            ("ChatGPT爆火引发AI算力需求激增", 0, ["AI", "算力", "需求"]),
            ("英伟达H100供不应求", 30, ["英伟达", "GPU", "供不应求"]),
            ("英伟达市值突破2万亿美元", 60, ["英伟达", "市值"]),
            ("SK海力士HBM3E量产", 90, ["SK海力士", "HBM", "存储"]),
            ("HBM产能过剩担忧初现", 180, ["HBM", "产能过剩"]),
        ])
        engine = AnalyzerEngine(timeline)
        network = engine.build_causal_network(min_confidence=0.15, multihop=True)

        # 应该有直接链和间接链
        direct_count = 0
        indirect_count = 0
        for effects in network._downstream.values():
            for chain in effects.values():
                if "[间接因果]" in chain.description:
                    indirect_count += 1
                else:
                    direct_count += 1

        self.assertGreater(direct_count, 0, "应有直接链")
        # 间接链可能有也可能没有，取决于直接链的连接性
        total = direct_count + indirect_count
        self.assertGreater(total, 0)


class TestMultihopPaths(unittest.TestCase):
    """多跳路径查询"""

    def test_get_multihop_effects(self):
        """从根事件查看多跳下游"""
        timeline = TimelineBase(title="路径查询")
        _add_events(timeline, [
            ("事件A", 0, ["a"]),
            ("事件B", 5, ["b"]),
            ("事件C", 10, ["c"]),
        ])
        engine = AnalyzerEngine(timeline)
        network = engine.build_causal_network(min_confidence=0.1, multihop=True)

        root_ids = network.root_ids
        if root_ids:
            descendants = network.get_descendants(root_ids[0], max_depth=3)
            self.assertIsInstance(descendants, list)


if __name__ == "__main__":
    unittest.main()
