"""趋势外推插件 — 基于历史模式预测"""
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List, Optional

from src.plugins.base import AnalysisPlugin, PluginResult


class TrendPlugin(AnalysisPlugin):
    name = "trend"
    description = "趋势外推（基于历史模式的方向预测）"
    version = "1.0.0"

    # 趋势方向关键词
    DIRECTION_KEYWORDS = {
        "bullish": ["上涨", "增长", "反弹", "新高", "突破", "回升", "复苏", "扩张", "牛市", "利好"],
        "bearish": ["下跌", "暴跌", "衰退", "下行", "回调", "萎缩", "熊市", "利空", "承压"],
        "neutral": ["震荡", "盘整", "横盘", "持平", "稳定", "窄幅"],
    }

    def analyze(
        self,
        events: List[Any],
        network: Optional[Any] = None,
        chapters: Optional[List[Any]] = None,
        lookback: int = 10,
        **kwargs,
    ) -> PluginResult:
        if len(events) < 2:
            return PluginResult(
                plugin_name=self.name, category="趋势",
                items={}, insights=["事件不足"],
            )

        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # 1. 为每个事件标注方向
        directions = []
        for event in sorted_events:
            text = (event.summary or "") + " " + " ".join(event.tags)
            text_lower = text.lower()
            scores = {}
            for dir_name, keywords in self.DIRECTION_KEYWORDS.items():
                scores[dir_name] = sum(1 for kw in keywords if kw.lower() in text_lower)
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                directions.append((event.timestamp, best, event.summary))

        if not directions:
            return PluginResult(
                plugin_name=self.name, category="趋势",
                items={}, insights=["无法识别趋势方向"],
            )

        # 2. 计算近期趋势（最近 lookback 个事件）
        recent = directions[-lookback:]
        bullish_count = sum(1 for _, d, _ in recent if d == "bullish")
        bearish_count = sum(1 for _, d, _ in recent if d == "bearish")
        neutral_count = sum(1 for _, d, _ in recent if d == "neutral")
        total = len(recent)

        # 3. 趋势强度
        trend_strength = (bullish_count - bearish_count) / max(1, total)
        if trend_strength > 0.3:
            trend_label = "看涨趋势"
        elif trend_strength < -0.3:
            trend_label = "看跌趋势"
        else:
            trend_label = "震荡/中性"

        # 4. 动量：最近一半 vs 前一半
        mid = len(recent) // 2
        first_half = recent[:mid] if mid > 0 else recent[:1]
        second_half = recent[mid:] if mid > 0 else recent[1:]

        def _dir_score(d_list):
            return sum(1 if d == "bullish" else (-1 if d == "bearish" else 0) for _, d, _ in d_list) / max(1, len(d_list))

        momentum = _dir_score(second_half) - _dir_score(first_half)
        if momentum > 0.2:
            momentum_label = "加速上涨"
        elif momentum < -0.2:
            momentum_label = "加速下跌"
        else:
            momentum_label = "动量平稳"

        # 5. 趋势转折检测
        reversals = []
        for i in range(1, len(directions)):
            _, prev_dir, _ = directions[i - 1]
            _, curr_dir, curr_summary = directions[i]
            if prev_dir != curr_dir and prev_dir != "neutral" and curr_dir != "neutral":
                reversals.append({
                    "from": prev_dir,
                    "to": curr_dir,
                    "time": str(directions[i][0]),
                    "summary": curr_summary,
                })

        insights = [
            f"当前趋势: {trend_label} (强度 {trend_strength:+.2f})",
            f"动量: {momentum_label} ({momentum:+.2f})",
            f"近期: 看涨{bullish_count} / 看跌{bearish_count} / 中性{neutral_count}",
        ]
        if reversals:
            insights.append(f"检测到 {len(reversals)} 次趋势转折")

        items = {
            "趋势方向": [f"看涨:{bullish_count}", f"看跌:{bearish_count}", f"中性:{neutral_count}"],
            "趋势转折": [f"{r['from']}→{r['to']} @ {r['time']}" for r in reversals[-5:]],
        }

        return PluginResult(
            plugin_name=self.name,
            category="趋势外推",
            items=items,
            insights=insights,
            score=abs(trend_strength),
            metadata={
                "trend": trend_label,
                "strength": trend_strength,
                "momentum": momentum,
                "reversals": len(reversals),
            },
        )
