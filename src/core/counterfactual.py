"""反事实分析引擎 — Pearl 因果阶梯第三层

核心问题：如果 A 没发生，B 还会发生吗？

方法：
1. 从因果网络中找到 A→B 的因果链
2. 寻找 B 的其他可能原因（替代路径）
3. 估计 P(B|A) vs P(B|¬A)
4. 给出反事实结论

参考：Pearl, J. (2009). Causality: Models, Reasoning, and Inference.
"""
import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from .timeline import TimelineEvent, Timeline
from .analyzer import CausalChain, CausalNetwork


@dataclass
class CounterfactualResult:
    """反事实分析结果"""
    cause_event: str           # 因事件摘要
    effect_event: str          # 果事件摘要
    p_effect_given_cause: float    # P(B|A): 因发生时果发生的概率
    p_effect_given_no_cause: float # P(B|¬A): 因不发生时果发生的概率
    causal_effect: float           # 因果效应 = P(B|A) - P(B|¬A)
    alternative_causes: List[str]  # B 的其他可能原因
    conclusion: str                # 结论
    confidence: float              # 置信度


class CounterfactualAnalyzer:
    """反事实分析器"""

    def __init__(self, network: CausalNetwork):
        self.network = network

    def analyze(self, cause_id: str, effect_id: str) -> CounterfactualResult:
        """分析反事实：如果 cause 没发生，effect 还会发生吗？

        Args:
            cause_id: 因事件 ID
            effect_id: 果事件 ID

        Returns:
            CounterfactualResult
        """
        cause_event = self.network._events.get(cause_id)
        effect_event = self.network._events.get(effect_id)

        if not cause_event or not effect_event:
            return self._error_result("事件不存在")

        # Step 1: 找到 A→B 的因果链
        direct_chain = self._find_direct_chain(cause_id, effect_id)

        # Step 2: 找到 B 的所有可能原因
        all_cause_chains = self.network.get_direct_causes(effect_id)
        alternative_causes = [
            chain.cause_event for chain in all_cause_chains
            if chain.cause_event.id != cause_id
        ]

        # Step 3: 估计概率
        # P(B|A): 有直接因果链时的概率
        p_given_cause = direct_chain.confidence if direct_chain else 0.0

        # P(B|¬A): 没有 A 时，B 通过其他原因发生的概率
        p_given_no_cause = self._estimate_p_without_cause(
            cause_id, effect_id, alternative_causes
        )

        # Step 4: 计算因果效应
        causal_effect = p_given_cause - p_given_no_cause

        # Step 5: 生成结论
        conclusion = self._generate_conclusion(
            cause_event, effect_event,
            p_given_cause, p_given_no_cause,
            causal_effect, alternative_causes
        )

        return CounterfactualResult(
            cause_event=cause_event.summary,
            effect_event=effect_event.summary,
            p_effect_given_cause=p_given_cause,
            p_effect_given_no_cause=p_given_no_cause,
            causal_effect=causal_effect,
            alternative_causes=[c.summary for c in alternative_causes],
            conclusion=conclusion,
            confidence=direct_chain.confidence if direct_chain else 0.5,
        )

    def _find_direct_chain(self, cause_id: str, effect_id: str) -> Optional[CausalChain]:
        """找到 A→B 的直接因果链"""
        effects = self.network._downstream.get(cause_id, {})
        return effects.get(effect_id)

    def _estimate_p_without_cause(
        self,
        cause_id: str,
        effect_id: str,
        alternative_causes: list,
    ) -> float:
        """估计没有 A 时 B 发生的概率

        方法：B 的其他原因中，最强的那条链的置信度
        """
        if not alternative_causes:
            # B 没有其他原因 → 如果 A 没发生，B 不太可能发生
            return 0.1  # 保留一点不确定性

        # 找最强的替代路径
        max_confidence = 0.0
        for alt_cause in alternative_causes:
            chain = self._find_direct_chain(alt_cause.id, effect_id)
            if chain and chain.confidence > max_confidence:
                max_confidence = chain.confidence

        # 如果有多条替代路径，联合概率更高
        if len(alternative_causes) > 1:
            joint = 1.0
            for alt_cause in alternative_causes:
                chain = self._find_direct_chain(alt_cause.id, effect_id)
                if chain:
                    joint *= (1 - chain.confidence)
            return 1 - joint

        return max_confidence

    def _generate_conclusion(
        self,
        cause: TimelineEvent,
        effect: TimelineEvent,
        p_with: float,
        p_without: float,
        effect_size: float,
        alternatives: list,
    ) -> str:
        """生成反事实结论"""
        cause_name = cause.summary[:20]
        effect_name = effect.summary[:20]

        if effect_size > 0.5:
            strength = "强因果"
            if p_without < 0.2:
                return (
                    f"【{strength}】{cause_name} 是 {effect_name} 的关键原因。"
                    f"如果 {cause_name} 没发生，{effect_name} 大概率不会发生"
                    f"（P={p_without:.0%}）。"
                )
            else:
                alt_names = "、".join(a.summary[:10] for a in alternatives[:2])
                return (
                    f"【{strength}】{cause_name} 是 {effect_name} 的主要原因，"
                    f"但即使没有 {cause_name}，{effect_name} 仍有 {p_without:.0%} 概率发生"
                    f"（通过 {alt_names} 等途径）。"
                )

        elif effect_size > 0.2:
            strength = "中等因果"
            alt_names = "、".join(a.summary[:10] for a in alternatives[:2])
            return (
                f"【{strength}】{cause_name} 对 {effect_name} 有一定影响，"
                f"但不是唯一原因。没有 {cause_name} 时，"
                f"{effect_name} 仍有 {p_without:.0%} 概率发生"
                f"（通过 {alt_names} 等途径）。"
            )

        elif effect_size > 0:
            strength = "弱因果"
            return (
                f"【{strength}】{cause_name} 对 {effect_name} 影响较小。"
                f"即使没有 {cause_name}，{effect_name} 仍很可能发生"
                f"（P={p_without:.0%}）。"
            )

        else:
            return (
                f"【无显著因果效应】{cause_name} 对 {effect_name} 无显著影响。"
                f"有无 {cause_name}，{effect_name} 发生概率相近"
                f"（{p_with:.0%} vs {p_without:.0%}）。"
            )

    def _error_result(self, msg: str) -> CounterfactualResult:
        return CounterfactualResult(
            cause_event="", effect_event="",
            p_effect_given_cause=0, p_effect_given_no_cause=0,
            causal_effect=0, alternative_causes=[],
            conclusion=msg, confidence=0,
        )

    def analyze_by_summary(self, cause_summary: str, effect_summary: str) -> CounterfactualResult:
        """通过事件摘要查找并分析反事实

        模糊匹配：摘要包含关系即可
        """
        cause_id = None
        effect_id = None

        for eid, event in self.network._events.items():
            if cause_summary in event.summary or event.summary in cause_summary:
                cause_id = eid
            if effect_summary in event.summary or event.summary in effect_summary:
                effect_id = eid

        if not cause_id or not effect_id:
            return self._error_result(
                f"未找到匹配事件: cause='{cause_summary}', effect='{effect_summary}'"
            )

        return self.analyze(cause_id, effect_id)

    def batch_analyze(self) -> List[CounterfactualResult]:
        """批量分析因果网络中所有因果链的反事实"""
        results = []
        for cause_id, effects in self.network._downstream.items():
            for effect_id, chain in effects.items():
                result = self.analyze(cause_id, effect_id)
                if result.confidence > 0.1:
                    results.append(result)
        return results
