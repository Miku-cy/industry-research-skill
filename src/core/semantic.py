from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import json
import os
import re
from .timeline import TimelineEvent
from .analyzer import PESTResult, SWOTResult


@dataclass
class SemanticScores:
    pest_scores: Dict[str, float] = field(default_factory=dict)
    swot_scores: Dict[str, float] = field(default_factory=dict)
    chapter_label: str = ""
    confidence: float = 0.0
    causal_concepts: List[str] = field(default_factory=list)


class SemanticClassifier:
    """语义分类器，支持三种模式：
    - heuristic: 纯本地关键词+短语映射（零依赖，最快）
    - ollama: 本地 Ollama 模型（隐私好，离线可用）
    - api: OpenAI 兼容 API（质量最高，需网络）
    - auto: 自动检测 Ollama，可用则用，否则回退 heuristic
    """

    HEURISTIC_CATEGORIES = {
        "政策驱动": ["政策", "监管", "审批", "央行", "美联储", "政府", "法律"],
        "市场波动": ["价格", "涨跌", "波动", "反弹", "回调", "突破", "新高", "新低"],
        "产业趋势": ["产业", "行业", "趋势", "转型", "升级", "周期", "结构"],
        "技术突破": ["技术", "创新", "研发", "专利", "突破", "首发", "量产"],
        "财务表现": ["营收", "利润", "亏损", "现金流", "毛利率", "净利率", "财报"],
        "竞争格局": ["竞争", "市占率", "份额", "格局", "对手", "追赶", "领先"],
        "风险事件": ["风险", "危机", "诉讼", "违约", "暴雷", "制裁", "调查"],
        "宏观环境": ["GDP", "通胀", "利率", "汇率", "PMI", "就业", "消费"],
    }

    # 语义映射：短语→标准化概念
    SEMANTIC_PHRASE_MAP = {
        # 货币政策
        "收紧货币政策": "加息", "紧缩货币政策": "加息",
        "收紧银根": "加息", "上调基准利率": "加息",
        "提高利率": "加息", "加息周期": "加息", "鹰派": "加息",
        "宽松货币政策": "降息", "放松银根": "降息",
        "下调基准利率": "降息", "降低利率": "降息",
        "降息周期": "降息", "鸽派": "降息",
        "量化宽松": "qe", "量化紧缩": "缩表",
        "扩表": "qe", "缩表": "缩表",
        "注入流动性": "放水", "回收流动性": "收紧",
        # 经济周期
        "经济衰退": "衰退", "经济下行": "衰退",
        "负增长": "衰退", "技术性衰退": "衰退",
        "经济复苏": "复苏", "经济回暖": "复苏", "触底反弹": "复苏",
        "过热": "过热", "泡沫": "泡沫",
        # 市场
        "大幅下跌": "暴跌", "急剧下跌": "暴跌", "闪崩": "暴跌",
        "大幅上涨": "暴涨", "强势上涨": "暴涨",
        "屡创新高": "新高", "突破历史高位": "新高",
        # 行业
        "产能扩张": "扩产", "产能收缩": "减产",
        "供过于求": "过剩", "供不应求": "紧缺",
        "行业洗牌": "整合", "强强联合": "并购",
    }

    def __init__(
        self,
        mode: str = "heuristic",
        llm_callable: Optional[Callable[[str, str], Dict[str, Any]]] = None,
        ollama_model: str = "qwen3:1.7b",
        ollama_url: str = "http://localhost:11434",
        api_url: str = "",
        api_key: str = "",
        api_model: str = "gpt-4o-mini",
        config_path: str = "",
    ):
        # 支持从 chronovisor.yaml 加载配置
        config = self._load_config(config_path)
        if config:
            mode = config.get("mode", mode)
            ollama_model = config.get("ollama_model", ollama_model)
            ollama_url = config.get("ollama_url", ollama_url)
            api_url = config.get("api_url", api_url)
            api_key = config.get("api_key", api_key)
            api_model = config.get("api_model", api_model)

        self.mode = mode
        self.llm_callable = llm_callable
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url
        self.api_url = api_url
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.api_model = api_model
        self._ollama_available: Optional[bool] = None

    @staticmethod
    def _load_config(config_path: str = "") -> Dict[str, Any]:
        """从 chronovisor.yaml 加载配置"""
        if not config_path:
            # 默认查找路径
            for p in [
                "chronovisor.yaml",
                "../chronovisor.yaml",
                os.path.expanduser("~/.chronovisor/config.yaml"),
            ]:
                if os.path.exists(p):
                    config_path = p
                    break
        if not config_path or not os.path.exists(config_path):
            return {}
        try:
            import yaml
        except ImportError:
            # 无 PyYAML 时用简单解析
            return SemanticClassifier._parse_yaml_simple(config_path)
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return SemanticClassifier._extract_config(data)

    @staticmethod
    def _parse_yaml_simple(path: str) -> Dict[str, Any]:
        """简单 YAML 解析（无需依赖）"""
        config = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if val.startswith("#") or not val:
                    continue
                config[key] = val
        return config

    @staticmethod
    def _extract_config(data: Dict) -> Dict[str, Any]:
        """从 YAML 数据中提取语义分类配置"""
        if not data:
            return {}
        semantic = data.get("semantic", {})
        config = {"mode": semantic.get("mode", "heuristic")}
        ollama = semantic.get("ollama", {})
        if ollama:
            config["ollama_model"] = ollama.get("model", "qwen3:1.7b")
            config["ollama_url"] = ollama.get("url", "http://localhost:11434")
        api = semantic.get("api", {})
        if api:
            config["api_url"] = api.get("url", "")
            config["api_key"] = api.get("key", "")
            config["api_model"] = api.get("model", "")
        return config

    def classify(self, event: TimelineEvent) -> SemanticScores:
        if self.mode == "auto":
            return self._classify_auto(event)
        if self.mode == "ollama":
            return self._classify_with_ollama(event)
        if self.mode == "api":
            return self._classify_with_api(event)
        if self.mode == "llm" and self.llm_callable:
            return self._classify_with_llm(event)
        return self._classify_heuristic(event)

    def classify_batch(self, events: List[TimelineEvent]) -> List[SemanticScores]:
        return [self.classify(e) for e in events]

    # ── 自动模式 ──────────────────────────────────────────────

    def _classify_auto(self, event: TimelineEvent) -> SemanticScores:
        """自动模式：先试 Ollama，失败回退 heuristic"""
        if self._check_ollama():
            try:
                return self._classify_with_ollama(event)
            except Exception:
                pass
        return self._classify_heuristic(event)

    def _check_ollama(self) -> bool:
        """检查 Ollama 是否可用（结果缓存）"""
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.ollama_url}/api/tags", method="GET"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                self._ollama_available = any(
                    self.ollama_model in m for m in models
                )
        except Exception:
            self._ollama_available = False
        return self._ollama_available

    # ── Ollama 本地调用 ───────────────────────────────────────

    def _classify_with_ollama(self, event: TimelineEvent) -> SemanticScores:
        prompt = self._build_semantic_prompt(event)
        result = self._call_ollama(prompt)
        return self._parse_llm_result(result)

    def _call_ollama(self, prompt: str) -> Dict[str, Any]:
        import urllib.request
        payload = json.dumps({
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 512},
        }).encode()
        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            response_text = data.get("response", "")
            return self._extract_json_from_text(response_text)

    # ── OpenAI 兼容 API 调用 ─────────────────────────────────

    def _classify_with_api(self, event: TimelineEvent) -> SemanticScores:
        if not self.api_url:
            return self._classify_heuristic(event)
        prompt = self._build_semantic_prompt(event)
        result = self._call_openai_api(prompt)
        return self._parse_llm_result(result)

    def _call_openai_api(self, prompt: str) -> Dict[str, Any]:
        import urllib.request
        payload = json.dumps({
            "model": self.api_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2048,
        }).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        base = self.api_url.rstrip('/')
        if not base.endswith('/v1'):
            base = base + '/v1'
        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            msg = data["choices"][0]["message"]
            # DeepSeek 推理格式：content 可能为空，答案在 reasoning_content 里
            content = msg.get("content") or ""
            if not content and msg.get("reasoning_content"):
                # 从推理过程中提取 JSON
                content = msg["reasoning_content"]
            return self._extract_json_from_text(content)

    # ── 自定义 LLM callable ──────────────────────────────────

    def _classify_with_llm(self, event: TimelineEvent) -> SemanticScores:
        prompt = self._build_llm_prompt(event)
        result = self.llm_callable(prompt, "classify")
        return self._parse_llm_result(result)

    # ── 启发式（纯本地关键词）─────────────────────────────────

    def _classify_heuristic(self, event: TimelineEvent) -> SemanticScores:
        text = (event.summary or "") + " " + " ".join(event.tags) + " " + str(event.data or "")
        text_lower = text.lower()
        expanded_text = self._expand_semantic_phrases(text_lower)

        scores = {}
        for category, keywords in self.HEURISTIC_CATEGORIES.items():
            match_count = sum(1 for kw in keywords if kw.lower() in expanded_text)
            scores[category] = match_count

        best_label = max(scores, key=scores.get) if scores and max(scores.values()) > 0 else "一般事件"
        confidence = min(1.0, max(scores.values()) / 3.0) if scores else 0.0

        pest_scores = self._infer_pest_scores(expanded_text)
        swot_scores = self._infer_swot_scores(expanded_text)

        return SemanticScores(
            pest_scores=pest_scores,
            swot_scores=swot_scores,
            chapter_label=best_label,
            confidence=confidence,
        )

    def _expand_semantic_phrases(self, text: str) -> str:
        expanded = text
        for phrase, concept in self.SEMANTIC_PHRASE_MAP.items():
            if phrase in expanded:
                expanded = expanded + " " + concept
        return expanded

    # ── 工具方法 ─────────────────────────────────────────────

    def _build_semantic_prompt(self, event: TimelineEvent) -> str:
        """构建语义分类提示词（给 Ollama/API 用）"""
        return f"""分析以下金融/产业事件，返回JSON格式分类结果。

事件摘要：{event.summary}
事件标签：{', '.join(event.tags)}
事件数据：{event.data}

请识别事件的真实含义，例如：
- "收紧货币政策" = 加息
- "放松银根" = 降息
- "经济下行" = 衰退
- "大幅回调" = 下跌

只返回JSON，不要其他文字：
{{
    "pest_scores": {{"political": 0.0-1.0, "economic": 0.0-1.0, "social": 0.0-1.0, "technological": 0.0-1.0}},
    "swot_scores": {{"strengths": 0.0-1.0, "weaknesses": 0.0-1.0, "opportunities": 0.0-1.0, "threats": 0.0-1.0}},
    "chapter_label": "事件分类标签",
    "confidence": 0.0-1.0,
    "causal_concepts": ["识别出的核心概念"]
}}"""

    def _build_llm_prompt(self, event: TimelineEvent) -> str:
        return f"""分析以下事件，返回 JSON：

事件摘要：{event.summary}
事件标签：{', '.join(event.tags)}
事件数据：{event.data}

返回格式：
{{
    "pest_scores": {{"political": 0.0-1.0, "economic": 0.0-1.0, "social": 0.0-1.0, "technological": 0.0-1.0}},
    "swot_scores": {{"strengths": 0.0-1.0, "weaknesses": 0.0-1.0, "opportunities": 0.0-1.0, "threats": 0.0-1.0}},
    "chapter_label": "分类标签",
    "confidence": 0.0-1.0
}}"""

    @staticmethod
    def _extract_json_from_text(text: str) -> Dict[str, Any]:
        """从 LLM 输出中提取 JSON"""
        json_match = re.search(r'```json\s*(.+?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    def _parse_llm_result(self, result: Dict[str, Any]) -> SemanticScores:
        return SemanticScores(
            pest_scores=result.get("pest_scores", {}),
            swot_scores=result.get("swot_scores", {}),
            chapter_label=result.get("chapter_label", ""),
            confidence=result.get("confidence", 0.0),
            causal_concepts=result.get("causal_concepts", []),
        )

    def _infer_pest_scores(self, text: str) -> Dict[str, float]:
        indicators = {
            "political": [
                "政策", "监管", "审批", "央行", "美联储", "政府", "法律", "制裁",
                "关税", "大选", "选举", "白宫", "国会", "版号", "合规",
            ],
            "economic": [
                "GDP", "通胀", "CPI", "PPI", "利率", "价格", "成本", "利润",
                "营收", "亏损", "银价", "金价", "指数", "期货", "需求", "供给",
            ],
            "social": [
                "就业", "失业", "裁员", "人口", "消费", "品牌", "信任", "ESG",
                "环保", "社区", "用户", "玩家", "文化",
            ],
            "technological": [
                "技术", "AI", "人工智能", "研发", "专利", "数字化", "自动化",
                "芯片", "半导体", "新能源", "算法", "平台", "系统",
            ],
        }
        return {
            cat: min(1.0, sum(1 for kw in kws if kw.lower() in text) / 3.0)
            for cat, kws in indicators.items()
        }

    def _infer_swot_scores(self, text: str) -> Dict[str, float]:
        indicators = {
            "strengths": [
                "增长", "突破", "领先", "利好", "盈利", "创新高", "超预期",
                "买入", "增持", "看好", "现金流", "回购", "分红",
            ],
            "weaknesses": [
                "亏损", "下降", "下滑", "裁员", "负债", "诉讼", "违规",
                "低于预期", "波动", "不确定", "减值", "流失",
            ],
            "opportunities": [
                "机会", "复苏", "回暖", "红利", "开放", "松绑", "刺激",
                "新兴", "蓝海", "增量", "出海", "并购", "降息",
            ],
            "threats": [
                "威胁", "竞争", "压力", "收紧", "制裁", "冲突", "战争",
                "泡沫", "危机", "衰退", "内卷", "价格战", "加息",
            ],
        }
        return {
            cat: min(1.0, sum(1 for kw in kws if kw.lower() in text) / 3.0)
            for cat, kws in indicators.items()
        }

    # ── PEST/SWOT 增强 ──────────────────────────────────────

    def enhance_pest(
        self, events: List[TimelineEvent], base_result: PESTResult
    ) -> PESTResult:
        seen = set()
        for lst in [base_result.political, base_result.economic,
                    base_result.social, base_result.technological]:
            seen.update(lst)

        for event in events:
            scores = self.classify(event)
            if scores.confidence < 0.3:
                continue
            summary = event.summary or str(event.data)[:100]
            if summary in seen:
                continue
            pest = scores.pest_scores
            added = False
            if pest.get("political", 0) > 0.4:
                base_result.political.append(summary)
                added = True
            if pest.get("economic", 0) > 0.4:
                base_result.economic.append(summary)
                added = True
            if pest.get("social", 0) > 0.4:
                base_result.social.append(summary)
                added = True
            if pest.get("technological", 0) > 0.4:
                base_result.technological.append(summary)
                added = True
            if added:
                seen.add(summary)
        return base_result

    def enhance_swot(
        self, events: List[TimelineEvent], base_result: SWOTResult
    ) -> SWOTResult:
        seen = set()
        for lst in [base_result.strengths, base_result.weaknesses,
                    base_result.opportunities, base_result.threats]:
            seen.update(lst)

        for event in events:
            scores = self.classify(event)
            if scores.confidence < 0.3:
                continue
            summary = event.summary or str(event.data)[:100]
            if summary in seen:
                continue
            swot = scores.swot_scores
            added = False
            if swot.get("strengths", 0) > 0.4:
                base_result.strengths.append(summary)
                added = True
            if swot.get("weaknesses", 0) > 0.4:
                base_result.weaknesses.append(summary)
                added = True
            if swot.get("opportunities", 0) > 0.4:
                base_result.opportunities.append(summary)
                added = True
            if swot.get("threats", 0) > 0.4:
                base_result.threats.append(summary)
                added = True
            if added:
                seen.add(summary)
        return base_result
