"""集成测试 — 端到端流程

测试完整 ChronoVisor 流程：
创建时间轴 → 添加事件 → 章节检测 → 插件分析 → 因果网络构建
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import (
    TimelineBase, TimelineEvent, ChapterDetector,
    AnalyzerEngine, CausalChain, CausalNetwork,
    plugin_registry,
)
from src.plugins import PESTPlugin, SWOTPlugin, CyclePlugin
from src.extras.anomaly import AnomalyPlugin
from src.extras.trend import TrendPlugin
from src.extras.correlation import CorrelationPlugin


def _add_events(timeline, event_specs):
    """批量添加事件。event_specs: [(summary, day, tags), ...]"""
    for summary, day, tags in event_specs:
        timeline.add_event(
            timestamp=datetime(2024, 1, 1) + timedelta(days=day),
            data={"summary": summary},
            source="test",
            tags=tags,
            summary=summary,
        )


class TestEndToEndPipeline(unittest.TestCase):
    """端到端：事件 → 章节 → PEST/SWOT/因果"""

    def setUp(self):
        self.timeline = TimelineBase(title="集成测试：半导体周期")
        _add_events(self.timeline, [
            ("全球芯片短缺加剧", 0, ["芯片", "半导体", "供需"]),
            ("台积电扩产计划公布", 30, ["台积电", "扩产", "半导体"]),
            ("美国芯片法案签署", 60, ["芯片", "政策", "美国"]),
            ("半导体设备订单激增", 90, ["半导体", "设备", "订单"]),
            ("存储芯片价格触底反弹", 120, ["存储", "芯片", "价格", "反弹"]),
            ("AI算力需求爆发", 150, ["AI", "算力", "芯片", "需求"]),
            ("半导体板块全面上涨", 180, ["半导体", "上涨", "牛市"]),
            ("芯片库存开始累积", 210, ["芯片", "库存", "供需"]),
            ("半导体周期见顶信号", 240, ["半导体", "见顶", "周期"]),
            ("芯片价格开始回落", 270, ["芯片", "价格", "下跌"]),
        ])
        self.events = self.timeline.timeline.get_all_events()

    def test_full_pipeline(self):
        """完整流程：事件 → 章节 → 因果链 → 因果网络 → 导出"""
        # 1. 章节检测
        detector = ChapterDetector(self.timeline.timeline)
        chapters = detector.detect(min_events=3)
        self.assertGreater(len(chapters), 0, "应检测到至少1个章节")

        # 2. 因果链发现
        engine = AnalyzerEngine(self.timeline)
        chains = engine.find_causal_chains(min_confidence=0.2)
        self.assertGreater(len(chains), 0, "应发现至少1条因果链")

        # 3. 因果网络构建
        network = engine.build_causal_network(min_confidence=0.2)
        self.assertGreater(network.chain_count, 0, "网络应有因果链")

        # 4. 导出验证
        mermaid = network.to_mermaid()
        self.assertIn("graph", mermaid)
        dot = network.to_dot()
        self.assertIn("digraph", dot)
        d = network.to_dict()
        self.assertIn("edges", d)
        self.assertIn("nodes", d)

    def test_pest_plugin_integration(self):
        """PEST 插件集成"""
        plugin = PESTPlugin()
        result = plugin.analyze(self.events)
        self.assertEqual(result.plugin_name, "pest")
        self.assertGreater(len(result.items["technological"]), 0)
        self.assertGreater(len(result.insights), 0)

    def test_swot_plugin_integration(self):
        """SWOT 插件集成"""
        plugin = SWOTPlugin()
        result = plugin.analyze(self.events)
        self.assertEqual(result.plugin_name, "swot")
        total = sum(len(v) for v in result.items.values())
        self.assertGreater(total, 0)

    def test_cycle_plugin_integration(self):
        """周期插件集成"""
        plugin = CyclePlugin()
        result = plugin.analyze(self.events)
        self.assertEqual(result.plugin_name, "cycle")

    def test_anomaly_plugin_integration(self):
        """异常检测插件集成"""
        plugin = AnomalyPlugin()
        result = plugin.analyze(self.events, threshold=0.3)
        self.assertEqual(result.plugin_name, "anomaly")

    def test_trend_plugin_integration(self):
        """趋势插件集成"""
        plugin = TrendPlugin()
        result = plugin.analyze(self.events)
        self.assertEqual(result.plugin_name, "trend")
        self.assertGreater(len(result.insights), 0)

    def test_correlation_plugin_integration(self):
        """相关性插件集成"""
        plugin = CorrelationPlugin()
        result = plugin.analyze(self.events, window_days=60)
        self.assertEqual(result.plugin_name, "correlation")

    def test_plugin_registry_integration(self):
        """插件注册表集成"""
        for name in ["pest", "swot", "cycle"]:
            self.assertIn(name, plugin_registry.names)
        result = plugin_registry.run("pest", self.events)
        self.assertEqual(result.plugin_name, "pest")


class TestCausalNetworkOperations(unittest.TestCase):
    """因果网络操作集成"""

    def setUp(self):
        self.timeline = TimelineBase(title="因果网络测试")
        _add_events(self.timeline, [
            ("美联储加息25基点", 0, ["加息", "美联储"]),
            ("美元指数走强", 7, ["美元", "走强"]),
            ("新兴市场货币贬值", 14, ["新兴市场", "货币", "贬值"]),
            ("新兴市场股市下跌", 21, ["新兴市场", "股市", "下跌"]),
        ])

    def test_network_traversal(self):
        """网络遍历：正向/反向/子图"""
        engine = AnalyzerEngine(self.timeline)
        network = engine.build_causal_network(min_confidence=0.2)

        if network.chain_count > 0:
            # 取第一个有下游的事件
            root_ids = network.root_ids
            self.assertGreater(len(root_ids), 0)
            cause_id = root_ids[0]

            effects = network.get_direct_effects(cause_id)
            self.assertIsInstance(effects, list)
            if effects:
                effect_id = effects[0].effect_event.id
                causes = network.get_direct_causes(effect_id)
                self.assertIsInstance(causes, list)
            sub = network.get_subgraph(cause_id, max_depth=2)
            self.assertIsInstance(sub, CausalNetwork)

    def test_chapter_operations(self):
        """章节操作：重命名"""
        timeline = TimelineBase(title="章节操作测试")
        _add_events(timeline, [(f"事件{i}", i * 10, ["测试"]) for i in range(10)])

        detector = ChapterDetector(timeline.timeline)
        chapters = detector.detect(min_events=3)
        if len(chapters) >= 1:
            timeline.rename_chapter(chapters[0].id, "新标题")
            self.assertEqual(chapters[0].title, "新标题")


class TestTextTilingIntegration(unittest.TestCase):
    """TextTiling 语义分段集成"""

    def test_texttiling_detection(self):
        """TextTiling 应检测到语义断裂"""
        timeline = TimelineBase(title="TextTiling 测试")
        _add_events(timeline, [
            (f"央行加息{i+1}次", i * 5, ["央行", "加息", "利率"]) for i in range(5)
        ] + [
            (f"AI技术突破{i+1}", 30 + i * 5, ["AI", "技术", "突破"]) for i in range(5)
        ])

        detector = ChapterDetector(timeline.timeline)
        chapters = detector.detect_texttiling(min_events=2)
        self.assertGreater(len(chapters), 0, "TextTiling 应检测到章节")


if __name__ == "__main__":
    unittest.main()
