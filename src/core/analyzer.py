from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from .timeline import TimelineBase, TimelineEvent, TimeType, Chapter


@dataclass
class PESTResult:
    political: List[str] = field(default_factory=list)
    economic: List[str] = field(default_factory=list)
    social: List[str] = field(default_factory=list)
    technological: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict:
        return {
            "political": self.political,
            "economic": self.economic,
            "social": self.social,
            "technological": self.technological,
            "summary": self.summary,
        }


@dataclass
class SWOTResult:
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    threats: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict:
        return {
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "opportunities": self.opportunities,
            "threats": self.threats,
            "summary": self.summary,
        }


@dataclass
class Scenario:
    name: str = ""
    probability: float = 0.0
    target_price: Optional[float] = None
    key_assumptions: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "probability": self.probability,
            "target_price": self.target_price,
            "key_assumptions": self.key_assumptions,
            "description": self.description,
        }


@dataclass
class ScenarioAnalysis:
    optimistic: Optional[Scenario] = None
    baseline: Optional[Scenario] = None
    pessimistic: Optional[Scenario] = None
    weighted_target: Optional[float] = None

    def calculate_weighted_target(self) -> float:
        total = 0.0
        total_prob = 0.0
        for scenario in [self.optimistic, self.baseline, self.pessimistic]:
            if scenario and scenario.target_price is not None:
                total += scenario.target_price * scenario.probability
                total_prob += scenario.probability
        if total_prob > 0:
            self.weighted_target = total / total_prob
        return self.weighted_target or 0.0

    def to_dict(self) -> Dict:
        return {
            "optimistic": self.optimistic.to_dict() if self.optimistic else None,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "pessimistic": self.pessimistic.to_dict() if self.pessimistic else None,
            "weighted_target": self.weighted_target,
        }


@dataclass
class CausalChain:
    cause_event: TimelineEvent
    effect_event: TimelineEvent
    time_gap: timedelta
    confidence: float
    description: str = ""

    def to_dict(self) -> Dict:
        return {
            "cause": {
                "id": self.cause_event.id,
                "timestamp": self.cause_event.timestamp.isoformat(),
                "summary": self.cause_event.summary,
            },
            "effect": {
                "id": self.effect_event.id,
                "timestamp": self.effect_event.timestamp.isoformat(),
                "summary": self.effect_event.summary,
            },
            "time_gap": str(self.time_gap),
            "confidence": self.confidence,
            "description": self.description,
        }


class AnalyzerEngine:
    PEST_KEYWORDS = {
        "political": [
            "政策", "政治", "监管", "法规", "法律", "版号", "审批", "政府",
            "央行", "美联储", "fed", "加息", "降息", "利率决议", "制裁", "关税",
            "贸易战", "许可证", "合规", "立法", "行政", "国家", "部门", "官方",
            "约谈", "反垄断", "税收", "补贴", "禁令", "协议", "地缘",
            "大选", "选举", "白宫", "国会", "欧盟", "联合国",
        ],
        "economic": [
            "经济", "市场", "收入", "营收", "增速", "gdp", "通胀", "cpi",
            "ppi", "利率", "汇率", "价格", "成本", "利润", "亏损", "投资",
            "融资", "上市", "股价", "市值", "估值", "银价", "金价", "铜价",
            "需求", "供给", "产能", "消费", "出口", "进口", "贸易",
            "牛市", "熊市", "反弹", "回调", "泡沫", "衰退", "复苏",
            "工业需求", "制造业", "零售", "服务业", "房地产", "美元",
            "指数", "期货", "现货", "etf", "持仓", "成交量",
        ],
        "social": [
            "社会", "用户", "玩家", "文化", "人口", "就业", "失业",
            "裁员", "招聘", "工资", "消费习惯", "舆论", "口碑",
            "品牌", "信任", "esg", "环保", "可持续", "公益",
            "教育", "健康", "安全", "隐私", "数据保护",
            "社区", "社交媒体", "趋势", "潮流", "生活方式",
        ],
        "technological": [
            "技术", "ai", "人工智能", "科技", "创新", "研发", "专利",
            "数字化", "自动化", "算法", "大数据", "云计算", "区块链",
            "物联网", "5g", "新能源", "芯片", "半导体", "软件", "硬件",
            "平台", "系统", "架构", "升级", "迭代", "突破",
            "实验室", "科研", "学术", "论文", "光伏", "电池",
            "电动车", "自动驾驶", "量子", "生物技术",
        ],
    }

    SWOT_KEYWORDS = {
        "strengths": [
            "优势", "增长", "利好", "成功", "突破", "领先", "龙头",
            "专利", "壁垒", "护城河", "品牌力", "市占率", "毛利率",
            "净利率", "现金流", "分红", "回购", "创新高", "超预期",
            "低成本", "高效率", "稀缺", "独家", "授权", "获奖",
            "达标", "完成", "盈利", "正增长", "反弹", "回升",
            "买入", "增持", "看好", "跑赢", "推荐",
        ],
        "weaknesses": [
            "劣势", "亏损", "下降", "裁员", "风险", "下滑", "萎缩",
            "负债", "债务", "诉讼", "罚款", "违规", "退市",
            "延期", "停滞", "瓶颈", "依赖", "单一", "波动",
            "不确定性", "减值", "计提", "暴雷", "违约", "逾期",
            "失败", "低于预期", "流失", "退出", "卖出", "减持",
        ],
        "opportunities": [
            "机会", "机遇", "趋势", "政策利好", "风口", "红利",
            "开放", "放开", "松绑", "刺激", "复苏", "回暖",
            "新兴市场", "蓝海", "增量", "渗透率", "国产替代",
            "出海", "全球化", "合作", "并购", "整合", "转型",
            "升级", "数字化", "绿色", "碳中和", "人口红利",
            "降息周期", "宽松", "放水", "qe",
        ],
        "threats": [
            "威胁", "竞争", "挑战", "压力", "替代", "颠覆",
            "收紧", "监管", "制裁", "调查", "封锁", "断供",
            "脱钩", "摩擦", "冲突", "战争", "疫情", "灾害",
            "黑天鹅", "灰犀牛", "内卷", "价格战", "同质化",
            "天花板", "见顶", "过热", "泡沫", "危机",
            "加息周期", "紧缩", "缩表", "衰退风险",
        ],
    }

    def __init__(self, timeline_base: TimelineBase):
        self.timeline = timeline_base

    def _match_keywords(self, text: str, keywords: List[str]) -> int:
        text_lower = text.lower()
        count = 0
        for kw in keywords:
            if kw.lower() in text_lower:
                count += 1
        return count

    def _score_event(self, event: TimelineEvent, keywords: List[str]) -> float:
        text = (event.summary or "") + " " + str(event.data or "")
        tag_text = " ".join(event.tags)
        summary_matches = self._match_keywords(text, keywords)
        tag_matches = self._match_keywords(tag_text, keywords)
        return summary_matches * 1.5 + tag_matches * 2.0

    def analyze_pest(self, chapter_id: Optional[str] = None) -> PESTResult:
        if chapter_id:
            events = self.timeline.timeline.get_chapter_events(chapter_id)
        else:
            events = self.timeline.timeline.get_all_events()

        result = PESTResult()

        for event in events:
            summary = event.summary or str(event.data)[:100]
            scores = {
                cat: self._score_event(event, keywords)
                for cat, keywords in self.PEST_KEYWORDS.items()
            }

            max_score = max(scores.values())
            if max_score <= 0:
                continue

            best_cats = [cat for cat, s in scores.items() if s == max_score]
            for cat in best_cats:
                getattr(result, cat).append(summary)

            threshold = max_score * 0.5
            for cat, score in scores.items():
                if cat not in best_cats and score >= threshold and score > 0:
                    getattr(result, cat).append(summary + " [相关]")

        result.summary = self._generate_pest_summary(result)
        return result

    def analyze_pest_over_time(self) -> Dict[str, PESTResult]:
        results = {}
        for chapter in self.timeline.timeline.chapters:
            results[chapter.id] = self.analyze_pest(chapter.id)
        return results

    def analyze_swot(self, chapter_id: Optional[str] = None) -> SWOTResult:
        if chapter_id:
            events = self.timeline.timeline.get_chapter_events(chapter_id)
        else:
            events = self.timeline.timeline.get_all_events()

        result = SWOTResult()

        for event in events:
            summary = event.summary or str(event.data)[:100]
            scores = {
                cat: self._score_event(event, keywords)
                for cat, keywords in self.SWOT_KEYWORDS.items()
            }

            max_score = max(scores.values())
            if max_score <= 0:
                continue

            best_cats = [cat for cat, s in scores.items() if s == max_score]
            for cat in best_cats:
                getattr(result, cat).append(summary)

            threshold = max_score * 0.5
            for cat, score in scores.items():
                if cat not in best_cats and score >= threshold and score > 0:
                    getattr(result, cat).append(summary + " [相关]")

        result.summary = self._generate_swot_summary(result)
        return result

    def compare_swot(self, chapter_a: str, chapter_b: str) -> Dict:
        swot_a = self.analyze_swot(chapter_a)
        swot_b = self.analyze_swot(chapter_b)

        return {
            "chapter_a": {
                "id": chapter_a,
                "swot": swot_a.to_dict(),
            },
            "chapter_b": {
                "id": chapter_b,
                "swot": swot_b.to_dict(),
            },
            "changes": {
                "new_strengths": [s for s in swot_b.strengths if s not in swot_a.strengths],
                "resolved_weaknesses": [
                    w for w in swot_a.weaknesses if w not in swot_b.weaknesses
                ],
                "new_opportunities": [
                    o for o in swot_b.opportunities if o not in swot_a.opportunities
                ],
                "new_threats": [t for t in swot_b.threats if t not in swot_a.threats],
            },
        }

    def analyze_scenario(
        self,
        optimistic_assumptions: List[str],
        optimistic_target: float,
        optimistic_prob: float,
        baseline_assumptions: List[str],
        baseline_target: float,
        baseline_prob: float,
        pessimistic_assumptions: List[str],
        pessimistic_target: float,
        pessimistic_prob: float,
    ) -> ScenarioAnalysis:
        analysis = ScenarioAnalysis(
            optimistic=Scenario(
                name="乐观情景",
                probability=optimistic_prob,
                target_price=optimistic_target,
                key_assumptions=optimistic_assumptions,
            ),
            baseline=Scenario(
                name="基准情景",
                probability=baseline_prob,
                target_price=baseline_target,
                key_assumptions=baseline_assumptions,
            ),
            pessimistic=Scenario(
                name="风险情景",
                probability=pessimistic_prob,
                target_price=pessimistic_target,
                key_assumptions=pessimistic_assumptions,
            ),
        )
        analysis.calculate_weighted_target()
        return analysis

    def find_causal_chains(
        self, min_confidence: float = 0.3
    ) -> List[CausalChain]:
        events = self.timeline.timeline.get_all_events()
        chains = []

        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                cause = events[i]
                effect = events[j]

                if cause.timestamp >= effect.timestamp:
                    continue

                confidence = self._calculate_causality_confidence(cause, effect)
                if confidence < min_confidence:
                    continue

                chain = CausalChain(
                    cause_event=cause,
                    effect_event=effect,
                    time_gap=effect.timestamp - cause.timestamp,
                    confidence=confidence,
                    description=f"{cause.summary or '事件A'} → {effect.summary or '事件B'}",
                )
                chains.append(chain)

        chains.sort(key=lambda x: x.confidence, reverse=True)
        return chains

    def _calculate_causality_confidence(
        self, cause: TimelineEvent, effect: TimelineEvent
    ) -> float:
        confidence = 0.3

        common_tags = set(cause.tags) & set(effect.tags)
        if common_tags:
            confidence += len(common_tags) * 0.15

        cause_text = (cause.summary or "") + " " + str(cause.data or "")
        effect_text = (effect.summary or "") + " " + str(effect.data or "")

        all_pest_kw = set()
        for kws in self.PEST_KEYWORDS.values():
            all_pest_kw.update(kws)
        all_swot_kw = set()
        for kws in self.SWOT_KEYWORDS.values():
            all_swot_kw.update(kws)
        all_kw = all_pest_kw | all_swot_kw

        cause_kw = {kw for kw in all_kw if kw.lower() in cause_text.lower()}
        effect_kw = {kw for kw in all_kw if kw.lower() in effect_text.lower()}
        shared_kw = cause_kw & effect_kw
        if shared_kw:
            confidence += len(shared_kw) * 0.08

        time_gap = effect.timestamp - cause.timestamp
        if time_gap < timedelta(days=30):
            confidence += 0.2
        elif time_gap < timedelta(days=90):
            confidence += 0.1
        elif time_gap > timedelta(days=365):
            confidence -= 0.1

        return min(1.0, max(0.0, confidence))

    def get_chapter_analysis(self, chapter_id: str) -> Dict:
        chapter = self.timeline.timeline.get_chapter(chapter_id)
        if not chapter:
            return {"error": f"章节 {chapter_id} 不存在"}

        events = self.timeline.timeline.get_chapter_events(chapter_id)
        event_count = len(events)
        time_types = {}
        for e in events:
            time_types[e.time_type.value] = time_types.get(e.time_type.value, 0) + 1

        return {
            "chapter": {
                "id": chapter.id,
                "title": chapter.title,
                "duration": chapter.duration_label,
                "summary": chapter.summary,
            },
            "event_count": event_count,
            "time_types": time_types,
            "pest": self.analyze_pest(chapter_id).to_dict(),
            "swot": self.analyze_swot(chapter_id).to_dict(),
        }

    def generate_timeline_analysis(self) -> Dict:
        total_events = self.timeline.timeline.get_event_count()
        chapter_count = len(self.timeline.timeline.chapters)
        causal_chains = self.find_causal_chains()

        return {
            "overview": {
                "total_events": total_events,
                "chapter_count": chapter_count,
                "causal_chains_found": len(causal_chains),
                "top_causal_chains": [c.to_dict() for c in causal_chains[:5]],
            },
            "chapter_analyses": {
                c.id: self.get_chapter_analysis(c.id)
                for c in self.timeline.timeline.chapters
            },
            "overall_pest": self.analyze_pest().to_dict(),
            "overall_swot": self.analyze_swot().to_dict(),
        }

    def _generate_pest_summary(self, result: PESTResult) -> str:
        parts = []
        if result.political:
            parts.append(f"政治因素：{len(result.political)}项")
        if result.economic:
            parts.append(f"经济因素：{len(result.economic)}项")
        if result.social:
            parts.append(f"社会因素：{len(result.social)}项")
        if result.technological:
            parts.append(f"技术因素：{len(result.technological)}项")
        return "；".join(parts) if parts else "暂无足够数据"

    def _generate_swot_summary(self, result: SWOTResult) -> str:
        parts = []
        if result.strengths:
            parts.append(f"优势：{len(result.strengths)}项")
        if result.weaknesses:
            parts.append(f"劣势：{len(result.weaknesses)}项")
        if result.opportunities:
            parts.append(f"机会：{len(result.opportunities)}项")
        if result.threats:
            parts.append(f"威胁：{len(result.threats)}项")
        return "；".join(parts) if parts else "暂无足够数据"