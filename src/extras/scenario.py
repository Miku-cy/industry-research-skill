"""情景分析插件 — 乐观/基准/悲观三情景"""
from typing import Any, Dict, List, Optional

from src.plugins.base import AnalysisPlugin, PluginResult


class ScenarioPlugin(AnalysisPlugin):
    name = "scenario"
    description = "情景分析（乐观/基准/悲观三情景）"
    version = "1.0.0"

    def analyze(
        self,
        events: List[Any],
        network: Optional[Any] = None,
        chapters: Optional[List[Any]] = None,
        optimistic: Optional[Dict] = None,
        baseline: Optional[Dict] = None,
        pessimistic: Optional[Dict] = None,
        **kwargs,
    ) -> PluginResult:
        """执行情景分析

        Args:
            optimistic: {"assumptions": [...], "target": float, "prob": float}
            baseline: 同上
            pessimistic: 同上
        """
        scenarios = {}
        for name, data in [("乐观", optimistic), ("基准", baseline), ("悲观", pessimistic)]:
            if data:
                scenarios[name] = {
                    "assumptions": data.get("assumptions", []),
                    "target": data.get("target", 0),
                    "probability": data.get("prob", 0),
                }

        # 计算加权目标
        weighted = sum(
            s["target"] * s["probability"] for s in scenarios.values()
        ) if scenarios else 0

        insights = []
        if scenarios:
            if optimistic and pessimistic:
                spread = optimistic.get("target", 0) - pessimistic.get("target", 0)
                insights.append(f"情景跨度: {spread:.1f}")
            insights.append(f"加权目标: {weighted:.2f}")

        return PluginResult(
            plugin_name=self.name,
            category="情景分析",
            items={name: s["assumptions"] for name, s in scenarios.items()},
            insights=insights,
            score=0.5,
            metadata={"scenarios": scenarios, "weighted_target": weighted},
        )
