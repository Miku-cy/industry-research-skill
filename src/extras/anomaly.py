"""异常检测插件 — 黑天鹅事件识别"""
import math
from datetime import timedelta
from typing import Any, Dict, List, Optional

from src.plugins.base import AnalysisPlugin, PluginResult


class AnomalyPlugin(AnalysisPlugin):
    name = "anomaly"
    description = "异常检测（黑天鹅事件/极端波动识别）"
    version = "1.0.0"

    # 异常指标关键词
    EXTREME_KEYWORDS = {
        "crash": ["暴跌", "崩盘", "熔断", "闪崩", "腰斩", "跳水", "直线暴跌", "黑天鹅"],
        "surge": ["暴涨", "飙升", "涨停", "一字板", "创新高", "历史新高", "翻倍"],
        "crisis": ["危机", "暴雷", "违约", "破产", "倒闭", "清算", "挤兑", "流动性危机"],
        "shock": ["突发事件", "意外", "超预期", "震惊", "地震", "战争", "制裁", "封锁"],
    }

    # 严重程度评分
    SEVERITY = {"crash": 0.9, "surge": 0.7, "crisis": 0.95, "shock": 0.8}

    def analyze(
        self,
        events: List[Any],
        network: Optional[Any] = None,
        chapters: Optional[List[Any]] = None,
        threshold: float = 0.5,
        **kwargs,
    ) -> PluginResult:
        if len(events) < 2:
            return PluginResult(
                plugin_name=self.name, category="异常",
                items={}, insights=["事件不足"],
            )

        sorted_events = sorted(events, key=lambda e: e.timestamp)
        anomalies = []

        for i, event in enumerate(sorted_events):
            text = (event.summary or "") + " " + " ".join(event.tags)
            text_lower = text.lower()

            # 1. 关键词异常检测
            for category, keywords in self.EXTREME_KEYWORDS.items():
                matches = [kw for kw in keywords if kw.lower() in text_lower]
                if matches:
                    severity = self.SEVERITY[category]
                    anomalies.append({
                        "event_id": event.id,
                        "summary": event.summary,
                        "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else str(event.timestamp),
                        "category": category,
                        "matched_keywords": matches,
                        "severity": severity,
                        "method": "keyword",
                    })
                    break

            # 2. 时间密度异常：短时间内事件激增
            if i > 0:
                gap = (event.timestamp - sorted_events[i-1].timestamp)
                if isinstance(gap, timedelta) and gap.days == 0:
                    # 同一天多个事件 → 可能异常
                    same_day_count = sum(
                        1 for e in sorted_events[max(0, i-5):i+1]
                        if (event.timestamp - e.timestamp).days == 0
                    )
                    if same_day_count >= 3:
                        anomalies.append({
                            "event_id": event.id,
                            "summary": event.summary,
                            "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else str(event.timestamp),
                            "category": "density_spike",
                            "matched_keywords": [],
                            "severity": min(0.9, same_day_count * 0.2),
                            "method": "density",
                        })

        # 去重（同一事件只保留最高严重度）
        seen = {}
        for a in anomalies:
            eid = a["event_id"]
            if eid not in seen or a["severity"] > seen[eid]["severity"]:
                seen[eid] = a
        anomalies = sorted(seen.values(), key=lambda x: x["severity"], reverse=True)

        # 过滤低严重度
        anomalies = [a for a in anomalies if a["severity"] >= threshold]

        insights = []
        if anomalies:
            insights.append(f"检测到 {len(anomalies)} 个异常事件")
            top = anomalies[0]
            insights.append(f"最严重: {top['summary'][:50]} (严重度 {top['severity']:.1f})")

        items = {cat: [] for cat in self.EXTREME_KEYWORDS}
        items["density_spike"] = []
        for a in anomalies:
            items[a["category"]].append(f"{a['summary'][:60]} [{a['severity']:.1f}]")

        return PluginResult(
            plugin_name=self.name,
            category="异常检测",
            items=items,
            insights=insights,
            score=min(1.0, len(anomalies) / max(1, len(events))),
            metadata={"anomalies": anomalies, "total_events": len(events)},
        )
