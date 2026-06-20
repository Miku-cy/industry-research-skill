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

        # 批量分析
        all_chains = []
        for batch_start in range(0, len(pairs), batch_size):
            batch = pairs[batch_start:batch_start + batch_size]
            chains = self._analyze_batch(batch)
            all_chains.extend(chains)

        # 过滤+构建网络
        network = CausalNetwork(title="因果挖掘结果")
        for chain in all_chains:
            if chain.confidence >= min_confidence:
                network.add_chain(chain)

        return network

    def _analyze_batch(
        self, pairs: List[Tuple[TimelineEvent, TimelineEvent]]
    ) -> List[CausalChain]:
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

考虑：
1. 时间顺序（因在前，果在后）
2. 传导机制（有没有合理的因果路径）
3. 领域关联（同领域或跨领域传导）
4. 间接因果（通过中间事件传导，如加息→加密崩盘→交易所破产）

只返回JSON数组，不要其他文字：
[{{"idx": 1, "confidence": 0.8, "reason": "加息导致流动性收紧，加密市场暴跌", "type": "indirect"}}, ...]"""

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
    ) -> List[CausalChain]:
        """解析 mimo 返回的因果分析结果"""
        chains = []
        if not isinstance(result, list):
            return chains

        for item in result:
            idx = item.get("idx", 0) - 1
            if idx < 0 or idx >= len(pairs):
                continue

            confidence = item.get("confidence", 0)
            reason = item.get("reason", "")
            ctype = item.get("type", "none")

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
            chains.append(chain)

        return chains

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
