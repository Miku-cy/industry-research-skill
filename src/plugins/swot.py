"""SWOT 分析插件 — 优势/劣势/机会/威胁"""
from typing import Any, Dict, List, Optional

from .base import AnalysisPlugin, PluginResult


class SWOTPlugin(AnalysisPlugin):
    name = "swot"
    description = "SWOT 态势分析（优势/劣势/机会/威胁）"
    version = "1.0.0"

    KEYWORDS = {
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

    def analyze(
        self,
        events: List[Any],
        network: Optional[Any] = None,
        chapters: Optional[List[Any]] = None,
        chapter_id: Optional[str] = None,
        **kwargs,
    ) -> PluginResult:
        if chapter_id and chapters:
            events = [e for e in events if getattr(e, "chapter_id", None) == chapter_id]

        items: Dict[str, List[str]] = {cat: [] for cat in self.KEYWORDS}

        for event in events:
            summary = event.summary or str(event.data or "")[:100]
            text = summary + " " + " ".join(event.tags)
            text_lower = text.lower()

            scores = {}
            for cat, keywords in self.KEYWORDS.items():
                count = sum(1 for kw in keywords if kw.lower() in text_lower)
                scores[cat] = count

            max_score = max(scores.values())
            if max_score <= 0:
                continue

            best_cats = [cat for cat, s in scores.items() if s == max_score]
            for cat in best_cats:
                items[cat].append(summary)

            threshold = max_score * 0.5
            for cat, score in scores.items():
                if cat not in best_cats and score >= threshold and score > 0:
                    items[cat].append(summary + " [相关]")

        insights = []
        s, w, o, t = len(items["strengths"]), len(items["weaknesses"]), len(items["opportunities"]), len(items["threats"])
        if s > w:
            insights.append(f"优势({s}) > 劣势({w})，基本面积极")
        elif w > s:
            insights.append(f"劣势({w}) > 优势({s})，基本面承压")
        if o > t:
            insights.append(f"机会({o}) > 威胁({t})，外部环境有利")
        elif t > o:
            insights.append(f"威胁({t}) > 机会({o})，外部环境不利")

        total = s + w + o + t
        return PluginResult(
            plugin_name=self.name,
            category="SWOT",
            items=items,
            insights=insights,
            score=min(1.0, total / max(1, len(events))),
            metadata={"strengths": s, "weaknesses": w, "opportunities": o, "threats": t},
        )
