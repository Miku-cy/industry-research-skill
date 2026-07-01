"""因果挖掘引擎 — 用 mimo v2.5 自动发现间接因果链

工作流程：
1. 把所有事件两两配对
2. 批量发给 mimo 分析因果关系
3. mimo 返回因果置信度 + 因果解释
4. 构建因果网络
"""
import json
import os
import urllib.request
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from .timeline import TimelineEvent, TimelineBase
from .analyzer import CausalChain, CausalNetwork
from .causal_lag import CausalLagModel
from .causal_graph import CausalGraph, causal_graph
import re


class CausalMiningEngine:
    """用 LLM 自动挖掘因果关系"""

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        api_model: str = "mimo-v2.5",
        config_path: str = "",
    ):
        config = self._load_config(config_path)
        self.api_url = api_url or config.get("api_url", "")
        self.api_key = api_key or config.get("api_key", "") or os.environ.get("OPENAI_API_KEY", "")
        self.api_model = api_model or config.get("api_model", "mimo-v2.5")
        self.lag_model = CausalLagModel()
        self.graph = causal_graph

    @staticmethod
    def _load_config(config_path: str = "") -> Dict:
        if not config_path:
            for p in ["chronovisor.yaml", "../chronovisor.yaml"]:
                if os.path.exists(p):
                    config_path = p
                    break
        if not config_path or not os.path.exists(config_path):
            return {}
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            semantic = data.get("semantic", {})
            api = semantic.get("api", {})
            return {
                "api_url": api.get("url", ""),
                "api_key": api.get("key", ""),
                "api_model": api.get("model", ""),
            }
        except Exception:
            return {}

    def mine(
        self,
        events: List[TimelineEvent],
        batch_size: int = 10,
        min_confidence: float = 0.3,
    ) -> CausalNetwork:
        """挖掘所有事件对的因果关系，构建网络

        四层漏斗过滤：
        Layer 1: 时序过滤 — A.timestamp < B.timestamp
        Layer 2: 时间窗口过滤 — 超出领域最大传导时间的淘汰
        Layer 3: 动态路由 — 图谱认识走快车道，不认识走 TF-IDF/LLM
        Layer 4: LLM 精细分析 — mechanism + similar_cases
        """
        # Layer 1: 时序过滤 + Layer 2: 时间窗口过滤
        pairs = []
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                cause, effect = events[i], events[j]
                if cause.timestamp >= effect.timestamp:
                    continue  # Layer 1: 时序过滤

                gap_days = (effect.timestamp - cause.timestamp).days

                # Layer 2: 时间窗口过滤
                all_tags = cause.tags + effect.tags
                all_summary = cause.summary + " " + effect.summary
                domain = self.lag_model.classify_domain(all_tags, all_summary)
                profile = self.lag_model.get_profile(domain)

                # 硬规则：超出领域最大传导时间 → 淘汰
                if gap_days > profile.typical_max_days:
                    continue

                pairs.append((cause, effect))

        # Layer 3: 动态路由
        fast_lane = []   # 图谱认识，直接进后处理
        slow_lane = []   # 图谱部分认识，送 LLM 确认
        for cause, effect in pairs:
            all_tags = cause.tags + effect.tags
            graph_result = self.graph.score(cause.summary, effect.summary, all_tags)

            if graph_result.known and graph_result.score > 0:
                # 图谱确认有因果（方向正确）→ 快车道
                chain = CausalChain(
                    cause_event=cause,
                    effect_event=effect,
                    time_gap=effect.timestamp - cause.timestamp,
                    confidence=graph_result.score,
                    description=f"{cause.summary} → {effect.summary} [图谱:{graph_result.match_info}]",
                )
                fast_lane.append(chain)

            elif graph_result.known and graph_result.source == "reverse":
                # 图谱发现反向匹配 → 淘汰（因果方向可能相反）
                pass

            elif graph_result.source == "partial":
                # 图谱部分认识（有触发词但效果词不匹配）→ 送 LLM 确认
                slow_lane.append((cause, effect))

            elif graph_result.source == "unknown":
                # 图谱完全不认识 → 淘汰（没有已知因果机制）
                pass

            else:
                # 其他情况 → 送 LLM
                slow_lane.append((cause, effect))

        # Layer 4: LLM 精细分析（只分析慢车道）
        # 并发处理多个批次，提高吞吐量
        all_chains = list(fast_lane)  # 快车道直接加入
        all_similar_cases: Dict[str, List[Dict]] = {}

        batches = []
        for batch_start in range(0, len(slow_lane), batch_size):
            batches.append(slow_lane[batch_start:batch_start + batch_size])

        if batches:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            max_workers = min(3, len(batches))  # 最多 3 个并发，受速率限制约束

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_idx = {
                    executor.submit(self._analyze_batch, batch): i
                    for i, batch in enumerate(batches)
                }
                batch_results = [None] * len(batches)
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        batch_results[idx] = future.result()
                    except Exception as e:
                        print(f"  [causal_mining] 批次 {idx} 失败: {e}")
                        batch_results[idx] = ([], {})

                for chains, similar_cases_map in batch_results:
                    if chains:
                        all_chains.extend(chains)
                    if similar_cases_map:
                        all_similar_cases.update(similar_cases_map)

        # LLM 结果后处理：用滞后模型校准置信度
        network = CausalNetwork(title="因果挖掘结果")
        for chain in all_chains:
            cause = chain.cause_event
            effect = chain.effect_event
            gap_days = (effect.timestamp - cause.timestamp).days

            all_tags = cause.tags + effect.tags
            all_summary = cause.summary + " " + effect.summary
            domain = self.lag_model.classify_domain(all_tags, all_summary)
            decay = self.lag_model.get_decay(gap_days, domain)

            # 最终置信度 = LLM 置信度 × 滞后衰减因子
            # 注：decay 作为时间合理性权重，LLM 给基础置信度，decay 调整时间合理性
            calibrated = chain.confidence * decay
            chain.confidence = calibrated

            if calibrated >= min_confidence:
                # 贝叶斯预测：用 LLM 提供的类似案例更新先验
                chain_key = f"{cause.id}->{effect.id}"
                llm_cases = all_similar_cases.get(chain_key, [])
                if llm_cases:
                    pred = self.lag_model.predict_with_evidence(
                        cause.tags, cause.summary, llm_cases,
                    )
                else:
                    pred = self.lag_model.predict_lag(
                        cause.tags, cause.summary,
                        effect.tags, effect.summary,
                    )

                ci = pred["ci_90"]
                prob7 = pred["prob_within"].get("7天", 0)
                prob30 = pred["prob_within"].get("30天", 0)
                method = pred.get("method", "prior")
                label = "贝叶斯" if method == "bayesian_with_evidence" else "先验"
                chain.description += (
                    f" [{label}预测:{pred['domain']}"
                    f" 预计传导:{pred['peak_days']}天"
                    f" 90%CI:[{ci[0]},{ci[1]}]天"
                    f" 7天概率:{prob7:.0%}"
                    f" 30天概率:{prob30:.0%}]"
                )
                network.add_chain(chain)

                # 自动闭环：记录观测数据，用于更新滞后模型
                self.lag_model.observe(
                    cause.tags, cause.summary,
                    effect.tags, effect.summary,
                    gap_days, calibrated,
                )

        # 累积够 10 条观测 → 自动学习更新滞后参数（避免小样本过拟合）
        if len(self.lag_model.observations) >= 10:
            self.lag_model.learn()
            self.lag_model.save()

        # 图谱自动学习：从挖掘结果扩充因果图谱
        for chain in all_chains:
            if chain.confidence >= min_confidence:
                self.graph.learn_from_chain(
                    chain.cause_event.summary,
                    chain.effect_event.summary,
                    chain.cause_event.tags,
                    chain.effect_event.tags,
                    chain.confidence,
                )

        return network

    def predict(self, summary: str, tags: List[str] = None) -> Dict:
        """给定一个事件描述，预测果事件的传导时间

        Args:
            summary: 事件摘要，如 "美联储加息25基点"
            tags: 标签列表，如 ["加息", "美联储"]

        Returns:
            {
                "domain": "金融市场",
                "peak_days": 7,
                "ci_90": [2, 18],
                "ci_50": [4, 10],
                "prob_within": {"7天": 0.6, "30天": 0.9, ...},
                "confidence": 0.8,
            }
        """
        return self.lag_model.predict_lag(tags or [], summary)

    def predict_with_evidence(
        self,
        summary: str,
        tags: List[str] = None,
        cases: List[Dict] = None,
    ) -> Dict:
        """结合历史案例的贝叶斯预测

        Args:
            summary: 事件摘要
            tags: 标签列表
            cases: 历史案例，如 [{"gap_days": 3, "confidence": 0.9}, ...]

        Returns:
            同 predict()，但用贝叶斯更新了先验
        """
        return self.lag_model.predict_with_evidence(
            tags or [], summary, cases,
        )

    @staticmethod
    def _tfidf_score(cause: str, effect: str, tags: List[str] = None) -> float:
        """TF-IDF 关键词重叠评分（纯统计，零 API 调用）"""
        def tokenize(text: str):
            cn = set(re.findall(r'[\u4e00-\u9fff]{2,}', text))
            cn_chars = set(re.findall(r'[\u4e00-\u9fff]', text))
            en = set(re.findall(r'[a-zA-Z]+', text.lower()))
            return cn | cn_chars | en

        cause_text = cause + " " + " ".join(tags or [])
        effect_text = effect + " " + " ".join(tags or [])
        tc = tokenize(cause_text)
        te = tokenize(effect_text)
        common = tc & te
        union = tc | te
        return len(common) / len(union) if union else 0

    def _analyze_batch(
        self, pairs: List[Tuple[TimelineEvent, TimelineEvent]]
    ) -> Tuple[List[CausalChain], Dict[str, List[Dict]]]:
        """批量分析事件对的因果关系"""
        prompt = self._build_batch_prompt(pairs)
        result = self._call_api(prompt)
        return self._parse_batch_result(result, pairs)

    def _build_batch_prompt(
        self, pairs: List[Tuple[TimelineEvent, TimelineEvent]]
    ) -> str:
        pairs_text = ""
        for idx, (cause, effect) in enumerate(pairs, 1):
            pairs_text += f"""
--- 对 {idx} ---
因: [{cause.timestamp.strftime('%Y-%m-%d')}] {cause.summary} (标签: {', '.join(cause.tags)})
果: [{effect.timestamp.strftime('%Y-%m-%d')})] {effect.summary} (标签: {', '.join(effect.tags)})
"""
        return f"""你是金融因果分析专家。分析以下事件对，判断是否存在因果关系。

{pairs_text}

对每一对，返回：
- confidence: 0.0-1.0 的因果置信度
- reason: 因果逻辑（一句话）
- type: "direct"(直接因果) / "indirect"(间接因果) / "correlation"(相关非因果) / "none"(无关)
- mechanism: 传导机制链，用箭头连接，如 "流动性收紧→风险资产抛售→加密市场暴跌"
- similar_cases: 你记忆中的类似历史因果案例，每个含 event(事件名)、gap_days(传导天数)、confidence(置信度)

考虑：
1. 时间顺序（因在前，果在后）
2. 传导机制（有没有合理的因果路径）
3. 领域关联（同领域或跨领域传导）
4. 间接因果（通过中间事件传导，如加息→加密崩盘→交易所破产）
5. 类似历史案例（如 2018 年加息周期中发生过什么）

只返回JSON数组，不要其他文字：
[{{"idx": 1, "confidence": 0.8, "reason": "加息导致流动性收紧，加密市场暴跌", "type": "indirect", "mechanism": "加息→流动性收紧→风险资产抛售→加密暴跌", "similar_cases": [{{"event": "2018年美联储加息周期", "gap_days": 30, "confidence": 0.7}}, {{"event": "2022年加息", "gap_days": 5, "confidence": 0.8}}]}}, ...]"""

    def _call_api(self, prompt: str) -> Dict:
        """调用 mimo API"""
        base = self.api_url.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"

        payload = json.dumps({
            "model": self.api_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4096,
        }).encode()

        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content and msg.get("reasoning_content"):
                content = msg["reasoning_content"]
            return self._extract_json(content)

    @staticmethod
    def _extract_json(text: str) -> Any:
        import re
        # 找 JSON 数组
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return []

    def _parse_batch_result(
        self, result: Any, pairs: List[Tuple[TimelineEvent, TimelineEvent]]
    ) -> Tuple[List[CausalChain], Dict[str, List[Dict]]]:
        """解析 mimo 返回的因果分析结果

        Returns:
            (chains, similar_cases_map)
            similar_cases_map: {chain_key: [{event, gap_days, confidence}, ...]}
        """
        chains = []
        similar_cases_map: Dict[str, List[Dict]] = {}
        if not isinstance(result, list):
            return chains, similar_cases_map

        for item in result:
            idx = item.get("idx", 0) - 1
            if idx < 0 or idx >= len(pairs):
                continue

            confidence = item.get("confidence", 0)
            reason = item.get("reason", "")
            ctype = item.get("type", "none")
            mechanism = item.get("mechanism", "")
            similar_cases = item.get("similar_cases", [])

            if ctype == "none" or confidence < 0.1:
                continue

            cause, effect = pairs[idx]
            chain = CausalChain(
                cause_event=cause,
                effect_event=effect,
                time_gap=effect.timestamp - cause.timestamp,
                confidence=confidence,
                description=reason or f"{cause.summary} → {effect.summary}",
            )
            if mechanism:
                chain.description += f" [机制:{mechanism}]"

            chain_key = f"{cause.id}->{effect.id}"
            if similar_cases:
                similar_cases_map[chain_key] = similar_cases

            chains.append(chain)

        return chains, similar_cases_map

    def mine_and_merge(
        self,
        timeline: TimelineBase,
        existing_network: Optional[CausalNetwork] = None,
    ) -> CausalNetwork:
        """挖掘并与现有网络合并"""
        events = timeline.timeline.get_all_events()
        mined = self.mine(events)

        if existing_network is None:
            return mined

        # 合并：保留已有链，补充新发现的
        merged = CausalNetwork(title="合并因果网络")
        existing_keys = set()

        for cause_id, effects in existing_network._downstream.items():
            for effect_id, chain in effects.items():
                merged.add_chain(chain)
                existing_keys.add(f"{cause_id}->{effect_id}")

        for cause_id, effects in mined._downstream.items():
            for effect_id, chain in effects.items():
                key = f"{cause_id}->{effect_id}"
                if key not in existing_keys:
                    merged.add_chain(chain)

        return merged
