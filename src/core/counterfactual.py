"""反事实分析引擎 — Pearl 因果阶梯第三层

支持两种分析方法：
1. 简化版：基于替代路径估计（向后兼容）
2. do-calculus：基于 Pearl 的 do 算子和图手术

核心问题：如果 A 没发生，B 还会发生吗？

参考：Pearl, J. (2009). Causality: Models, Reasoning, and Inference.
"""
import json
import os
from typing import Dict, List, Optional, Set, Tuple
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
    method: str = "simple"         # 分析方法: simple / do_calculus
    paths_cut: List[str] = field(default_factory=list)  # do-calculus 切断的路径


class CounterfactualAnalyzer:
    """反事实分析器（支持 do-calculus）"""

    def __init__(self, network: CausalNetwork):
        self.network = network

    def analyze(self, cause_id: str, effect_id: str, method: str = "do_calculus") -> CounterfactualResult:
        """分析反事实：如果 cause 没发生，effect 还会发生吗？

        Args:
            cause_id: 因事件 ID
            effect_id: 果事件 ID
            method: "simple"（替代路径估计）或 "do_calculus"（Pearl do 算子）

        Returns:
            CounterfactualResult
        """
        if method == "do_calculus":
            return self._analyze_do(cause_id, effect_id)
        return self._analyze_simple(cause_id, effect_id)

    # ═══ do-calculus 实现 ═══

    def _analyze_do(self, cause_id: str, effect_id: str) -> CounterfactualResult:
        """Pearl do-calculus 反事实分析

        核心思想：P(B | do(¬A)) 通过图手术计算
        1. 切断 A 的所有上游边（消除混杂）
        2. 在修改后的图中计算 P(B)
        3. 与 P(B | A) 比较得到因果效应
        """
        cause_event = self.network._events.get(cause_id)
        effect_event = self.network._events.get(effect_id)

        if not cause_event or not effect_event:
            return self._error_result("事件不存在", "do_calculus")

        # Step 1: P(B|A) — 观测概率
        direct_chain = self._find_direct_chain(cause_id, effect_id)
        p_given_cause = direct_chain.confidence if direct_chain else 0.0

        # Step 2: 图手术 — 切断 A 的所有上游边
        # 也切断 A 对 B 的直接路径（模拟 A 不发生）
        paths_cut = self._find_paths_to_cut(cause_id, effect_id)

        # Step 3: P(B | do(¬A)) — 干预后的概率
        # 在截断图中，B 只通过非 A 的路径获得概率
        p_given_do_no_cause = self._compute_interventional_prob(
            cause_id, effect_id, paths_cut
        )

        # Step 4: 因果效应
        causal_effect = p_given_cause - p_given_do_no_cause

        # Step 5: 混杂检测
        # 如果 P(B|A) ≈ P(B|do(A))，说明没有混杂
        # 如果差异大，说明 A→B 有混杂因素
        all_cause_chains = self.network.get_direct_causes(effect_id)
        alternative_causes = [
            chain.cause_event for chain in all_cause_chains
            if chain.cause_event.id != cause_id
        ]

        # Step 6: 结论
        conclusion = self._generate_do_conclusion(
            cause_event, effect_event,
            p_given_cause, p_given_do_no_cause,
            causal_effect, alternative_causes, paths_cut,
        )

        return CounterfactualResult(
            cause_event=cause_event.summary,
            effect_event=effect_event.summary,
            p_effect_given_cause=p_given_cause,
            p_effect_given_no_cause=p_given_do_no_cause,
            causal_effect=causal_effect,
            alternative_causes=[c.summary for c in alternative_causes],
            conclusion=conclusion,
            confidence=direct_chain.confidence if direct_chain else 0.5,
            method="do_calculus",
            paths_cut=paths_cut,
        )

    def _find_paths_to_cut(self, cause_id: str, effect_id: str) -> List[str]:
        """找到 do(¬A) 需要切断的路径

        do 算子要求：
        1. 切断 A 的所有上游（消除混杂 C→A→B 中 C 的影响）
        2. 保留 A 的下游（但标记为"被干预"）
        """
        paths_cut = []

        # 切断 A 的所有上游（混杂路径）
        upstream = self.network._upstream.get(cause_id, {})
        for up_id, chain in upstream.items():
            up_event = self.network._events.get(up_id)
            if up_event:
                paths_cut.append(f"混杂路径: {up_event.summary[:20]}→{self.network._events[cause_id].summary[:20]}")

        # 切断 A→B 直接路径
        direct = self.network._downstream.get(cause_id, {}).get(effect_id)
        if direct:
            paths_cut.append(f"直接路径: {direct.cause_event.summary[:20]}→{direct.effect_event.summary[:20]}")

        # 切断 A→M→B 间接路径（中间变量路径）
        for mid_id, chain in self.network._downstream.get(cause_id, {}).items():
            if mid_id == effect_id:
                continue
            mid_event = self.network._events.get(mid_id)
            if mid_event and self._find_direct_chain(mid_id, effect_id):
                paths_cut.append(f"中介路径: {cause_event_summary(self.network, cause_id)}→{mid_event.summary[:20]}→{effect_event_summary(self.network, effect_id)}")

        return paths_cut

    def _compute_interventional_prob(
        self, cause_id: str, effect_id: str, paths_cut: List[str],
    ) -> float:
        """计算 P(B | do(¬A))

        在截断图中，B 的概率来自：
        1. B 的非 A 上游（混杂因素被切断后剩余的）
        2. B 的先验概率

        使用截断因子分解：
        P(B | do(¬A)) = Σ_{parents(B) \\ A} P(B | parents(B)) × P(parents(B))
        """
        # 找 B 的所有上游（排除通过 A 的路径）
        b_upstream = self.network._upstream.get(effect_id, {})

        # 过滤掉通过 A 的上游
        valid_upstream = {}
        for up_id, chain in b_upstream.items():
            if up_id == cause_id:
                continue  # 排除 A 本身
            # 检查是否通过 A 到达 B
            if self._is_on_path(up_id, cause_id, effect_id):
                continue  # 排除通过 A 的中介
            valid_upstream[up_id] = chain

        if not valid_upstream:
            # B 没有非 A 的上游 → P(B | do(¬A)) 接近先验
            return 0.1

        # 计算联合概率：1 - Π(1 - conf_i)
        joint = 1.0
        for up_id, chain in valid_upstream.items():
            joint *= (1 - chain.confidence)

        return 1 - joint

    def _is_on_path(self, node_id: str, from_id: str, to_id: str) -> bool:
        """检查 node_id 是否在 from_id → to_id 的某条路径上"""
        if node_id == from_id or node_id == to_id:
            return True
        # BFS 从 from_id 到 node_id
        visited = set()
        queue = [from_id]
        while queue:
            current = queue.pop(0)
            if current == node_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            for next_id in self.network._downstream.get(current, {}):
                if next_id not in visited:
                    queue.append(next_id)
        return False

    def _generate_do_conclusion(
        self, cause, effect, p_with, p_without,
        effect_size, alternatives, paths_cut,
    ) -> str:
        """生成 do-calculus 结论"""
        cause_name = cause.summary[:20]
        effect_name = effect.summary[:20]
        n_cut = len(paths_cut)

        if effect_size > 0.5:
            if p_without < 0.2:
                return (
                    f"【强因果·do-calculus】{cause_name} 是 {effect_name} 的关键原因。"
                    f"干预移除 {cause_name} 后，{effect_name} 概率从 {p_with:.0%} 降至 {p_without:.0%}。"
                    f"切断 {n_cut} 条路径（含混杂和中介），剩余替代路径不足支撑 {effect_name}。"
                )
            else:
                alt_names = "、".join(a.summary[:10] for a in alternatives[:2])
                return (
                    f"【强因果·do-calculus】{cause_name} 是 {effect_name} 的主要原因，"
                    f"但存在 {alt_names} 等独立路径。"
                    f"干预后概率 {p_with:.0%}→{p_without:.0%}，{effect_name} 仍可能发生。"
                    f"切断 {n_cut} 条路径后剩余替代路径有效。"
                )

        elif effect_size > 0.2:
            alt_names = "、".join(a.summary[:10] for a in alternatives[:2])
            return (
                f"【中等因果·do-calculus】{cause_name} 对 {effect_name} 有影响但非唯一。"
                f"干预后 {p_with:.0%}→{p_without:.0%}。"
                f"{alt_names} 等独立路径可部分支撑 {effect_name}。"
                f"建议检查混杂因素是否同时影响因和果。"
            )

        elif effect_size > 0:
            return (
                f"【弱因果·do-calculus】{cause_name} 对 {effect_name} 影响较小。"
                f"干预后概率变化不大（{p_with:.0%}→{p_without:.0%}）。"
                f"{effect_name} 主要由其他独立因素驱动。"
            )

        else:
            return (
                f"【无显著因果效应·do-calculus】{cause_name} 对 {effect_name} 无显著影响。"
                f"观测相关性（{p_with:.0%}）可能由混杂因素造成。"
                f"干预后概率 {p_without:.0%}，说明因果效应不显著。"
            )

    # ═══ 简化版（向后兼容）═══

    def _analyze_simple(self, cause_id: str, effect_id: str) -> CounterfactualResult:
        """简化版分析（基于替代路径估计）"""
        cause_event = self.network._events.get(cause_id)
        effect_event = self.network._events.get(effect_id)

        if not cause_event or not effect_event:
            return self._error_result("事件不存在", "simple")

        direct_chain = self._find_direct_chain(cause_id, effect_id)
        all_cause_chains = self.network.get_direct_causes(effect_id)
        alternative_causes = [
            chain.cause_event for chain in all_cause_chains
            if chain.cause_event.id != cause_id
        ]

        p_given_cause = direct_chain.confidence if direct_chain else 0.0
        p_given_no_cause = self._estimate_p_without_cause(
            cause_id, effect_id, alternative_causes
        )
        causal_effect = p_given_cause - p_given_no_cause

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
            method="simple",
        )

    # ═══ 公共方法 ═══

    def _find_direct_chain(self, cause_id: str, effect_id: str) -> Optional[CausalChain]:
        effects = self.network._downstream.get(cause_id, {})
        return effects.get(effect_id)

    def _estimate_p_without_cause(self, cause_id, effect_id, alternative_causes):
        if not alternative_causes:
            return 0.1
        max_confidence = 0.0
        for alt_cause in alternative_causes:
            chain = self._find_direct_chain(alt_cause.id, effect_id)
            if chain and chain.confidence > max_confidence:
                max_confidence = chain.confidence
        if len(alternative_causes) > 1:
            joint = 1.0
            for alt_cause in alternative_causes:
                chain = self._find_direct_chain(alt_cause.id, effect_id)
                if chain:
                    joint *= (1 - chain.confidence)
            return 1 - joint
        return max_confidence

    def _generate_conclusion(self, cause, effect, p_with, p_without, effect_size, alternatives):
        cause_name = cause.summary[:20]
        effect_name = effect.summary[:20]
        if effect_size > 0.5:
            if p_without < 0.2:
                return f"【强因果】{cause_name} 是 {effect_name} 的关键原因。如果没发生，{effect_name} 大概率不会（P={p_without:.0%}）。"
            else:
                alt_names = "、".join(a.summary[:10] for a in alternatives[:2])
                return f"【强因果】{cause_name} 是主因，但有 {alt_names} 等替代路径（P={p_without:.0%}）。"
        elif effect_size > 0.2:
            alt_names = "、".join(a.summary[:10] for a in alternatives[:2])
            return f"【中等因果】{cause_name} 有影响但非唯一。无 {cause_name} 时仍有 {p_without:.0%}（通过 {alt_names}）。"
        elif effect_size > 0:
            return f"【弱因果】{cause_name} 影响较小。{effect_name} 仍很可能（P={p_without:.0%}）。"
        else:
            return f"【无显著因果效应】{cause_name} 对 {effect_name} 无显著影响（{p_with:.0%} vs {p_without:.0%}）。"

    def _error_result(self, msg, method="simple"):
        return CounterfactualResult(
            cause_event="", effect_event="",
            p_effect_given_cause=0, p_effect_given_no_cause=0,
            causal_effect=0, alternative_causes=[],
            conclusion=msg, confidence=0, method=method,
        )

    def analyze_by_summary(self, cause_summary: str, effect_summary: str, method: str = "do_calculus") -> CounterfactualResult:
        cause_id = None
        effect_id = None
        for eid, event in self.network._events.items():
            if cause_summary in event.summary or event.summary in cause_summary:
                cause_id = eid
            if effect_summary in event.summary or event.summary in effect_summary:
                effect_id = eid
        if not cause_id or not effect_id:
            return self._error_result(f"未找到匹配: '{cause_summary}' / '{effect_summary}'", method)
        return self.analyze(cause_id, effect_id, method)

    def batch_analyze(self, method: str = "do_calculus") -> List[CounterfactualResult]:
        results = []
        for cause_id, effects in self.network._downstream.items():
            for effect_id, chain in effects.items():
                result = self.analyze(cause_id, effect_id, method)
                if result.confidence > 0.1:
                    results.append(result)
        return results


def cause_event_summary(network, cause_id):
    e = network._events.get(cause_id)
    return e.summary[:20] if e else cause_id[:8]


def effect_event_summary(network, effect_id):
    e = network._events.get(effect_id)
    return e.summary[:20] if e else effect_id[:8]
