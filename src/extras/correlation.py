"""相关性分析插件 — 指标关联发现"""
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from src.plugins.base import AnalysisPlugin, PluginResult


class CorrelationPlugin(AnalysisPlugin):
    name = "correlation"
    description = "相关性分析（事件标签共现与时间关联）"
    version = "1.0.0"

    def analyze(
        self,
        events: List[Any],
        network: Optional[Any] = None,
        chapters: Optional[List[Any]] = None,
        window_days: int = 7,
        min_cooccur: int = 2,
        **kwargs,
    ) -> PluginResult:
        if len(events) < 3:
            return PluginResult(
                plugin_name=self.name, category="相关性",
                items={}, insights=["事件不足"],
            )

        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # 1. 标签共现分析
        tag_pairs: Dict[Tuple[str, str], int] = defaultdict(int)
        tag_counts: Dict[str, int] = defaultdict(int)

        for event in sorted_events:
            tags = list(set(event.tags))  # 去重
            for tag in tags:
                tag_counts[tag] += 1
            # 标签对
            for i in range(len(tags)):
                for j in range(i + 1, len(tags)):
                    pair = tuple(sorted([tags[i], tags[j]]))
                    tag_pairs[pair] += 1

        # 2. 时间窗口内共现
        time_cooccur: Dict[Tuple[str, str], int] = defaultdict(int)
        for i in range(len(sorted_events)):
            for j in range(i + 1, len(sorted_events)):
                gap = (sorted_events[j].timestamp - sorted_events[i].timestamp)
                if hasattr(gap, 'days') and gap.days > window_days:
                    break
                tags_i = set(sorted_events[i].tags)
                tags_j = set(sorted_events[j].tags)
                for ti in tags_i:
                    for tj in tags_j:
                        if ti != tj:
                            pair = tuple(sorted([ti, tj]))
                            time_cooccur[pair] += 1

        # 3. 排序并过滤
        strong_pairs = [
            {"tags": list(pair), "count": count, "type": "co-occurrence"}
            for pair, count in tag_pairs.items()
            if count >= min_cooccur
        ]
        strong_pairs.sort(key=lambda x: x["count"], reverse=True)

        time_pairs = [
            {"tags": list(pair), "count": count, "type": "time-window"}
            for pair, count in time_cooccur.items()
            if count >= min_cooccur
        ]
        time_pairs.sort(key=lambda x: x["count"], reverse=True)

        # 4. Jaccard 相关系数
        jaccard_scores = []
        for pair, cooccur in tag_pairs.items():
            t1, t2 = pair
            union = tag_counts[t1] + tag_counts[t2] - cooccur
            if union > 0:
                jaccard = cooccur / union
                if jaccard >= 0.3:
                    jaccard_scores.append({
                        "tags": [t1, t2],
                        "jaccard": round(jaccard, 3),
                        "cooccur": cooccur,
                        "t1_count": tag_counts[t1],
                        "t2_count": tag_counts[t2],
                    })
        jaccard_scores.sort(key=lambda x: x["jaccard"], reverse=True)

        # 洞察
        insights = []
        if jaccard_scores:
            top = jaccard_scores[0]
            insights.append(f"最强关联: {top['tags'][0]} ↔ {top['tags'][1]} (Jaccard={top['jaccard']:.2f})")
        if time_pairs:
            top_t = time_pairs[0]
            insights.append(f"最强时间关联: {top_t['tags'][0]} ↔ {top_t['tags'][1]} ({top_t['count']}次共现)")
        insights.append(f"共分析 {len(tag_counts)} 个标签, {len(tag_pairs)} 对共现")

        items = {
            "强关联对": [f"{j['tags'][0]}↔{j['tags'][1]}: Jaccard={j['jaccard']}" for j in jaccard_scores[:10]],
            "时间窗口关联": [f"{t['tags'][0]}↔{t['tags'][1]}: {t['count']}次" for t in time_pairs[:10]],
        }

        return PluginResult(
            plugin_name=self.name,
            category="相关性分析",
            items=items,
            insights=insights,
            score=min(1.0, len(jaccard_scores) / max(1, len(tag_pairs))),
            metadata={
                "tag_count": len(tag_counts),
                "pair_count": len(tag_pairs),
                "strong_pairs": len(strong_pairs),
                "jaccard_top": jaccard_scores[:5],
            },
        )
