"""PEST 分析插件 — 政治/经济/社会/技术分类"""
from typing import Any, Dict, List, Optional

from .base import AnalysisPlugin, PluginResult


class PESTPlugin(AnalysisPlugin):
    name = "pest"
    description = "PEST 宏观环境分析（政治/经济/社会/技术）"
    version = "1.0.0"

    KEYWORDS = {
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

    def analyze(
        self,
        events: List[Any],
        network: Optional[Any] = None,
        chapters: Optional[List[Any]] = None,
        chapter_id: Optional[str] = None,
        **kwargs,
    ) -> PluginResult:
        # 按章节筛选
        if chapter_id and chapters:
            from ..core.timeline import TimelineBase
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

        # 生成洞察
        insights = []
        for cat, entries in items.items():
            if entries:
                label = {"political": "政治", "economic": "经济", "social": "社会", "technological": "技术"}[cat]
                insights.append(f"{label}环境：{len(entries)} 个相关事件")

        total = sum(len(v) for v in items.values())
        return PluginResult(
            plugin_name=self.name,
            category="PEST",
            items=items,
            insights=insights,
            score=min(1.0, total / max(1, len(events))),
            metadata={"total_events": len(events), "matched": total},
        )
