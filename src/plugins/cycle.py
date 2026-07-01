"""周期识别插件 — 库存周期/利率周期/信贷周期等"""
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import AnalysisPlugin, PluginResult


class CyclePlugin(AnalysisPlugin):
    name = "cycle"
    description = "周期识别（Kitchin/利率/信贷/商品周期）"
    version = "1.0.0"

    # 周期定义：名称 → 典型周期长度（天）
    CYCLE_DEFS = {
        "kitchin": {"label": "基钦周期(库存)", "min_days": 300, "max_days": 600, "peak_days": 450},
        "interest": {"label": "利率周期", "min_days": 365, "max_days": 1825, "peak_days": 1095},
        "credit": {"label": "信贷周期", "min_days": 730, "max_days": 3650, "peak_days": 2190},
        "commodity": {"label": "商品周期", "min_days": 1825, "max_days": 5475, "peak_days": 3650},
    }

    # 周期阶段关键词
    PHASE_KEYWORDS = {
        "expansion": ["扩张", "增长", "上涨", "新高", "反弹", "复苏", "牛市", "繁荣", "景气"],
        "peak": ["见顶", "过热", "泡沫", "高位", "顶部", "拐点"],
        "contraction": ["收缩", "下跌", "暴跌", "衰退", "下行", "熊市", "回调", "萧条"],
        "trough": ["见底", "底部", "低谷", "企稳", "触底", "反弹迹象"],
    }

    def analyze(
        self,
        events: List[Any],
        network: Optional[Any] = None,
        chapters: Optional[List[Any]] = None,
        **kwargs,
    ) -> PluginResult:
        if len(events) < 3:
            return PluginResult(
                plugin_name=self.name, category="周期",
                items={}, insights=["事件不足，无法识别周期"],
            )

        # 按时间排序
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # 1. 识别每个事件的周期阶段
        phase_timeline = []
        for event in sorted_events:
            text = (event.summary or "") + " " + " ".join(event.tags)
            text_lower = text.lower()
            phase_scores = {}
            for phase, keywords in self.PHASE_KEYWORDS.items():
                phase_scores[phase] = sum(1 for kw in keywords if kw.lower() in text_lower)
            best_phase = max(phase_scores, key=phase_scores.get)
            if phase_scores[best_phase] > 0:
                phase_timeline.append((event.timestamp, best_phase, event.summary))

        # 2. 检测阶段转换
        transitions = []
        for i in range(1, len(phase_timeline)):
            prev_time, prev_phase, _ = phase_timeline[i - 1]
            curr_time, curr_phase, curr_summary = phase_timeline[i]
            if prev_phase != curr_phase:
                transitions.append({
                    "from": prev_phase,
                    "to": curr_phase,
                    "time": curr_time.isoformat() if hasattr(curr_time, "isoformat") else str(curr_time),
                    "summary": curr_summary,
                })

        # 3. 估算周期长度
        cycle_estimates = self._estimate_cycle_length(phase_timeline)

        # 4. 生成洞察
        insights = []
        if transitions:
            latest = transitions[-1]
            insights.append(f"最近阶段转换: {latest['from']} → {latest['to']}")
        for cycle_name, est in cycle_estimates.items():
            def_info = self.CYCLE_DEFS.get(cycle_name, {})
            insights.append(f"{def_info.get('label', cycle_name)}: 约 {est['days']} 天")

        items = {
            "阶段转换": [f"{t['from']}→{t['to']} @ {t['time']}" for t in transitions],
            "周期估算": [f"{k}: {v['days']}天" for k, v in cycle_estimates.items()],
        }

        return PluginResult(
            plugin_name=self.name,
            category="周期识别",
            items=items,
            insights=insights,
            score=min(1.0, len(phase_timeline) / max(1, len(events))),
            metadata={"transitions": transitions, "estimates": cycle_estimates},
        )

    def _estimate_cycle_length(self, phase_timeline: list) -> Dict[str, Dict]:
        """从阶段转换序列估算周期长度"""
        estimates = {}
        # 简单方法：找连续的同阶段转换间隔
        phase_times: Dict[str, List] = defaultdict(list)
        for time, phase, _ in phase_timeline:
            phase_times[phase].append(time)

        # 用 expansion 阶段间距估算主周期
        if len(phase_times.get("expansion", [])) >= 2:
            times = sorted(phase_times["expansion"])
            gaps = [(times[i+1] - times[i]).days for i in range(len(times)-1)
                    if hasattr(times[i+1], 'day')]
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                # 匹配最接近的周期定义
                for cycle_name, defn in self.CYCLE_DEFS.items():
                    if defn["min_days"] <= avg_gap <= defn["max_days"]:
                        estimates[cycle_name] = {"days": int(avg_gap), "confidence": 0.6}
                        break
                if not estimates:
                    # 默认归类为基钦周期
                    estimates["kitchin"] = {"days": int(avg_gap), "confidence": 0.3}

        return estimates
