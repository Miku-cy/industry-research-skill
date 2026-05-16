from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from .timeline import TimelineEvent
from .analyzer import PESTResult, SWOTResult


@dataclass
class SemanticScores:
    pest_scores: Dict[str, float] = field(default_factory=dict)
    swot_scores: Dict[str, float] = field(default_factory=dict)
    chapter_label: str = ""
    confidence: float = 0.0


class SemanticClassifier:
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

    def __init__(
        self,
        mode: str = "heuristic",
        llm_callable: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    ):
        self.mode = mode
        self.llm_callable = llm_callable

    def classify(self, event: TimelineEvent) -> SemanticScores:
        if self.mode == "llm" and self.llm_callable:
            return self._classify_with_llm(event)
        return self._classify_heuristic(event)

    def classify_batch(self, events: List[TimelineEvent]) -> List[SemanticScores]:
        return [self.classify(e) for e in events]

    def _classify_heuristic(self, event: TimelineEvent) -> SemanticScores:
        text = (event.summary or "") + " " + " ".join(event.tags) + " " + str(event.data or "")
        text_lower = text.lower()

        scores = {}
        for category, keywords in self.HEURISTIC_CATEGORIES.items():
            match_count = sum(1 for kw in keywords if kw.lower() in text_lower)
            scores[category] = match_count

        best_label = max(scores, key=scores.get) if scores and max(scores.values()) > 0 else "一般事件"
        confidence = min(1.0, max(scores.values()) / 3.0) if scores else 0.0

        pest_scores = self._infer_pest_scores(text_lower)
        swot_scores = self._infer_swot_scores(text_lower)

        return SemanticScores(
            pest_scores=pest_scores,
            swot_scores=swot_scores,
            chapter_label=best_label,
            confidence=confidence,
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

    def _classify_with_llm(self, event: TimelineEvent) -> SemanticScores:
        prompt = self._build_llm_prompt(event)
        result = self.llm_callable(prompt, "classify")
        return self._parse_llm_result(result)

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

    def _parse_llm_result(self, result: Dict[str, Any]) -> SemanticScores:
        return SemanticScores(
            pest_scores=result.get("pest_scores", {}),
            swot_scores=result.get("swot_scores", {}),
            chapter_label=result.get("chapter_label", ""),
            confidence=result.get("confidence", 0.0),
        )

    def enhance_pest(
        self, events: List[TimelineEvent], base_result: PESTResult
    ) -> PESTResult:
        for event in events:
            scores = self.classify(event)
            if scores.confidence < 0.3:
                continue
            summary = event.summary or str(event.data)[:100]
            pest = scores.pest_scores
            if pest.get("political", 0) > 0.4:
                base_result.political.append(summary)
            if pest.get("economic", 0) > 0.4:
                base_result.economic.append(summary)
            if pest.get("social", 0) > 0.4:
                base_result.social.append(summary)
            if pest.get("technological", 0) > 0.4:
                base_result.technological.append(summary)
        return base_result

    def enhance_swot(
        self, events: List[TimelineEvent], base_result: SWOTResult
    ) -> SWOTResult:
        for event in events:
            scores = self.classify(event)
            if scores.confidence < 0.3:
                continue
            summary = event.summary or str(event.data)[:100]
            swot = scores.swot_scores
            if swot.get("strengths", 0) > 0.4:
                base_result.strengths.append(summary)
            if swot.get("weaknesses", 0) > 0.4:
                base_result.weaknesses.append(summary)
            if swot.get("opportunities", 0) > 0.4:
                base_result.opportunities.append(summary)
            if swot.get("threats", 0) > 0.4:
                base_result.threats.append(summary)
        return base_result