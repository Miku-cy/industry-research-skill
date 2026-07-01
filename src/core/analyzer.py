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


class CausalNetwork:
    """因果网络图 — 有向无环图结构

    支持：
    - 从任意事件查看因果后代（因→果方向）
    - 从任意事件查看因果祖先（果→因方向）
    - 导出 Mermaid / DOT / JSON 格式
    """

    def __init__(self, title: str = ""):
        self.title = title
        # event_id -> {event_id -> CausalChain}
        self._downstream: Dict[str, Dict[str, CausalChain]] = {}
        self._upstream: Dict[str, Dict[str, CausalChain]] = {}
        self._events: Dict[str, TimelineEvent] = {}
        self._analyzed_ids: set = set()  # 已分析过的事件 ID

    def add_chain(self, chain: CausalChain):
        """添加一条因果链到网络"""
        cause_id = chain.cause_event.id
        effect_id = chain.effect_event.id

        self._events[cause_id] = chain.cause_event
        self._events[effect_id] = chain.effect_event

        if cause_id not in self._downstream:
            self._downstream[cause_id] = {}
        self._downstream[cause_id][effect_id] = chain

        if effect_id not in self._upstream:
            self._upstream[effect_id] = {}
        self._upstream[effect_id][cause_id] = chain

    # ── 查询 ─────────────────────────────────────────

    def get_event(self, event_id: str) -> Optional[TimelineEvent]:
        return self._events.get(event_id)

    def get_direct_effects(self, event_id: str) -> List[CausalChain]:
        """获取直接果（一级下游）"""
        return list(self._downstream.get(event_id, {}).values())

    def get_direct_causes(self, event_id: str) -> List[CausalChain]:
        """获取直接因（一级上游）"""
        return list(self._upstream.get(event_id, {}).values())

    def get_descendants(self, event_id: str, max_depth: int = 10) -> List[Dict]:
        """获取所有因果后代（BFS，按层级展开）

        返回: [{depth, event_id, timestamp, summary, chain_confidence, chain_description}, ...]
        """
        result = []
        visited = {event_id}
        queue = [(event_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for effect_id, chain in self._downstream.get(current_id, {}).items():
                if effect_id in visited:
                    continue
                visited.add(effect_id)
                effect = chain.effect_event
                result.append({
                    "depth": depth + 1,
                    "event_id": effect_id,
                    "timestamp": effect.timestamp.isoformat(),
                    "summary": effect.summary,
                    "chain_confidence": chain.confidence,
                    "chain_description": chain.description,
                    "from_event_id": current_id,
                })
                queue.append((effect_id, depth + 1))

        return result

    def get_ancestors(self, event_id: str, max_depth: int = 10) -> List[Dict]:
        """获取所有因果祖先（BFS，按层级展开）"""
        result = []
        visited = {event_id}
        queue = [(event_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for cause_id, chain in self._upstream.get(current_id, {}).items():
                if cause_id in visited:
                    continue
                visited.add(cause_id)
                cause = chain.cause_event
                result.append({
                    "depth": depth + 1,
                    "event_id": cause_id,
                    "timestamp": cause.timestamp.isoformat(),
                    "summary": cause.summary,
                    "chain_confidence": chain.confidence,
                    "chain_description": chain.description,
                    "from_event_id": current_id,
                })
                queue.append((cause_id, depth + 1))

        return result

    def get_subgraph(self, event_id: str, max_depth: int = 5) -> "CausalNetwork":
        """以某事件为中心，截取子网络（含上下游）"""
        sub = CausalNetwork(title=f"{self.title} - 子网络")
        visited = set()
        queued = {event_id}
        queue = [(event_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth > max_depth or current_id in visited:
                continue
            visited.add(current_id)

            # 下游
            for effect_id, chain in self._downstream.get(current_id, {}).items():
                if effect_id not in queued and depth + 1 <= max_depth:
                    sub.add_chain(chain)
                    queued.add(effect_id)
                    queue.append((effect_id, depth + 1))

            # 上游
            for cause_id, chain in self._upstream.get(current_id, {}).items():
                if cause_id not in queued and depth + 1 <= max_depth:
                    sub.add_chain(chain)
                    queued.add(cause_id)
                    queue.append((cause_id, depth + 1))

        return sub

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def chain_count(self) -> int:
        return sum(len(v) for v in self._downstream.values())

    @property
    def root_ids(self) -> List[str]:
        """没有上游的根事件（最初的因）"""
        return [eid for eid in self._events if eid not in self._upstream]

    @property
    def leaf_ids(self) -> List[str]:
        """没有下游的叶事件（最终的果）"""
        return [eid for eid in self._events if eid not in self._downstream]

    # ── 多跳推理 ─────────────────────────────────────

    def find_multihop_chains(
        self,
        max_hops: int = 3,
        min_confidence: float = 0.1,
        confidence_decay: float = 0.7,
    ) -> List["CausalChain"]:
        """多跳因果链推理：从直接因果链推导间接因果链

        原理：如果 A→B (conf=0.5) 且 B→C (conf=0.4)，
        则 A→C 为间接因果链 (conf=0.5*0.4*decay)。

        Args:
            max_hops: 最大跳数（默认 3，即 A→B→C→D）
            min_confidence: 最低置信度阈值
            confidence_decay: 每跳的置信度衰减因子

        Returns:
            间接因果链列表（不含已有直接链）
        """
        indirect_chains = []
        # 已有的直接链（避免重复）
        existing_pairs = set()
        for cause_id, effects in self._downstream.items():
            for effect_id in effects:
                existing_pairs.add((cause_id, effect_id))

        # 从每个根节点开始 BFS
        for root_id in self.root_ids:
            # BFS: (current_id, path, cumulative_confidence)
            queue = [(root_id, [root_id], 1.0)]
            while queue:
                current_id, path, cum_conf = queue.pop(0)
                if len(path) > max_hops:
                    continue
                # 遍历当前节点的下游
                downstream = self._downstream.get(current_id, {})
                for next_id, chain in downstream.items():
                    if next_id in path:
                        continue  # 避免环
                    new_path = path + [next_id]
                    new_conf = cum_conf * chain.confidence * confidence_decay
                    # 跳数 >= 2 时记录间接链
                    if len(new_path) >= 2:
                        pair = (new_path[0], new_path[-1])
                        if pair not in existing_pairs:
                            # 时间顺序检查
                            cause_event = self._events.get(new_path[0])
                            effect_event = self._events.get(new_path[-1])
                            if cause_event and effect_event and \
                               cause_event.timestamp < effect_event.timestamp:
                                # 构造间接链描述
                                mid_summaries = [
                                    self._events[sid].summary[:20]
                                    for sid in new_path[1:-1]
                                    if sid in self._events
                                ]
                                chain_desc = "→".join(
                                    [cause_event.summary[:25]] +
                                    mid_summaries +
                                    [effect_event.summary[:25]]
                                ) + " [间接因果]"
                                indirect = CausalChain(
                                    cause_event=cause_event,
                                    effect_event=effect_event,
                                    time_gap=effect_event.timestamp - cause_event.timestamp,
                                    confidence=new_conf,
                                    description=chain_desc,
                                )
                                indirect_chains.append(indirect)
                                existing_pairs.add(pair)
                    if new_conf >= min_confidence:
                        queue.append((next_id, new_path, new_conf))

        indirect_chains.sort(key=lambda c: c.confidence, reverse=True)
        return indirect_chains

    # ── 导出 ─────────────────────────────────────────

    def to_mermaid(self, direction: str = "LR") -> str:
        """导出 Mermaid 流程图（可嵌入 Markdown）

        direction: LR=从左到右, TD=从上到下
        """
        lines = [f"graph {direction}"]

        # 节点定义（用摘要做标签，截短）
        for eid, event in self._events.items():
            label = (event.summary or "事件")[:30].replace('"', "'")
            ts = event.timestamp.strftime("%Y-%m")
            lines.append(f'    {eid}["{ts} {label}"]')

        # 边定义
        for cause_id, effects in self._downstream.items():
            for effect_id, chain in effects.items():
                conf = f"{chain.confidence:.0%}"
                lines.append(f'    {cause_id} -->|"{conf}"| {effect_id}')

        return "\n".join(lines)

    def to_dot(self, rankdir: str = "LR") -> str:
        """导出 DOT 格式（Graphviz 可渲染）"""
        lines = [f'digraph "{self.title}" {{']
        lines.append(f'    rankdir={rankdir};')
        lines.append('    node [shape=box, style=filled, fillcolor=lightyellow];')
        lines.append('')

        # 节点
        for eid, event in self._events.items():
            label = (event.summary or "事件")[:40].replace('"', "'")
            ts = event.timestamp.strftime("%Y-%m-%d")
            lines.append(f'    {eid} [label="{ts}\n{label}"];')

        lines.append('')

        # 边
        for cause_id, effects in self._downstream.items():
            for effect_id, chain in effects.items():
                conf = f"{chain.confidence:.0%}"
                color = "red" if chain.confidence >= 0.5 else "orange" if chain.confidence >= 0.3 else "gray"
                lines.append(f'    {cause_id} -> {effect_id} [label="{conf}", color={color}];')

        lines.append('}')
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """导出为字典（可序列化为 JSON）"""
        nodes = []
        for eid, event in self._events.items():
            nodes.append({
                "id": eid,
                "timestamp": event.timestamp.isoformat(),
                "summary": event.summary,
                "tags": event.tags,
                "is_root": eid not in self._upstream,
                "is_leaf": eid not in self._downstream,
            })

        edges = []
        for cause_id, effects in self._downstream.items():
            for effect_id, chain in effects.items():
                edges.append({
                    "from": cause_id,
                    "to": effect_id,
                    "confidence": chain.confidence,
                    "description": chain.description,
                    "time_gap": str(chain.time_gap),
                })

        return {
            "title": self.title,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }


class AnalyzerEngine:
    # 因果概念图谱：(因概念集合, 果概念集合, 因果强度加成)
    # 概念用 frozenset 存储，匹配时检查事件文本是否包含集合中任意概念
    CAUSAL_CONCEPT_PAIRS = [
        # 货币政策因果链
        (frozenset(["通胀", "cpi", "物价上涨", "通胀预期"]),
         frozenset(["加息", "收紧", "紧缩", "缩表"]), 0.4),
        (frozenset(["加息", "收紧货币政策", "紧缩", "缩表"]),
         frozenset(["利率上升", "借贷成本", "融资成本", "房贷利率"]), 0.35),
        (frozenset(["加息", "紧缩", "利率上升"]),
         frozenset(["股市下跌", "暴跌", "回调", "熊市", "股灾"]), 0.3),
        (frozenset(["加息", "紧缩", "利率上升"]),
         frozenset(["黄金下跌", "金价下跌", "贵金属下跌"]), 0.3),
        (frozenset(["降息", "宽松", "放水", "qe"]),
         frozenset(["股市上涨", "反弹", "牛市", "新高"]), 0.3),
        (frozenset(["降息", "宽松", "放水"]),
         frozenset(["黄金上涨", "金价上涨", "贵金属上涨"]), 0.3),
        (frozenset(["衰退", "经济下行", "gdp下降"]),
         frozenset(["降息", "宽松", "刺激", "救市"]), 0.4),
        # 行业/公司因果链
        (frozenset(["版号", "审批", "许可证"]),
         frozenset(["上线", "发布", "上线"]), 0.3),
        (frozenset(["裁员", "降本", "成本控制"]),
         frozenset(["利润增长", "盈利改善", "扭亏"]), 0.25),
        (frozenset(["新产品发布", "爆款", "大作上线"]),
         frozenset(["营收增长", "收入提升", "流水增长"]), 0.3),
        (frozenset(["监管", "合规", "反垄断"]),
         frozenset(["罚款", "处罚", "整改"]), 0.35),
        (frozenset(["制裁", "关税", "贸易战"]),
         frozenset(["供应链", "断供", "脱钩"]), 0.35),
        (frozenset(["并购", "收购", "整合"]),
         frozenset(["市占率", "份额", "格局"]), 0.25),
        # 供需因果
        (frozenset(["需求增长", "消费增长", "订单增长"]),
         frozenset(["价格上涨", "涨价", "提价"]), 0.3),
        (frozenset(["供给过剩", "产能过剩", "库存积压"]),
         frozenset(["价格下跌", "降价", "折扣"]), 0.3),
    ]

    # 语义对立概念对：对立事件往往有强因果
    CAUSAL_ANTONYM_PAIRS = [
        (frozenset(["加息", "紧缩", "收紧"]), frozenset(["降息", "宽松", "放水"]), 0.25),
        (frozenset(["上涨", "增长", "反弹", "新高"]), frozenset(["下跌", "下降", "暴跌", "新低"]), 0.15),
        (frozenset(["利好", "正面", "超预期"]), frozenset(["利空", "负面", "低于预期"]), 0.15),
        (frozenset(["扩张", "增长", "投入"]), frozenset(["收缩", "裁员", "缩减"]), 0.15),
        (frozenset(["供不应求", "紧缺", "稀缺"]), frozenset(["过剩", "饱和", "积压"]), 0.2),
    ]

    # 间接因果：通过中间概念传导
    CAUSAL_INDIRECT_CHAINS = [
        # 加息 → 美元走强 → 新兴市场承压
        (frozenset(["加息", "紧缩"]), frozenset(["美元"]), frozenset(["新兴市场", "汇率"]), 0.2),
        # 油价上涨 → 通胀 → 加息
        (frozenset(["油价", "原油", "能源价格"]), frozenset(["通胀", "cpi"]), frozenset(["加息", "紧缩"]), 0.2),
    ]

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
                    description=self._generate_causal_description(cause, effect),
                )
                chains.append(chain)

        chains.sort(key=lambda x: x.confidence, reverse=True)
        return chains

    def build_causal_network(
        self, min_confidence: float = 0.3, multihop: bool = True,
        max_hops: int = 3,
    ) -> CausalNetwork:
        """构建因果网络图

        从因果链构建有向图，支持：
        - 从任意事件查看因果后代/祖先
        - 导出 Mermaid/DOT/JSON 格式
        - 截取子网络
        - 多跳间接因果链推理
        """
        chains = self.find_causal_chains(min_confidence)
        network = CausalNetwork(title=self.timeline.timeline.title or "因果网络")
        for chain in chains:
            network.add_chain(chain)

        # 多跳推理：从直接链推导间接链
        if multihop and network.chain_count > 0:
            indirect = network.find_multihop_chains(
                max_hops=max_hops,
                min_confidence=min_confidence * 0.5,
                confidence_decay=0.7,
            )
            for chain in indirect:
                network.add_chain(chain)

        return network

    def update_incremental(
        self,
        network: CausalNetwork,
        new_events: List[TimelineEvent],
        min_confidence: float = 0.3,
        multihop: bool = True,
        max_hops: int = 3,
    ) -> CausalNetwork:
        """增量更新因果网络

        只分析新事件与已有事件之间的因果关系，
        将新链合并进现有网络，不重新分析旧事件对。

        Args:
            network: 已有的因果网络
            new_events: 新加入的事件列表
            min_confidence: 最低置信度阈值
            multihop: 是否进行多跳推理
            max_hops: 最大跳数

        Returns:
            更新后的因果网络（同一个对象）
        """
        if not new_events:
            return network

        all_events = list(network._events.values()) + new_events

        # 只分析新事件对：
        # 1. 新事件 vs 已有事件（双向）
        # 2. 新事件 vs 新事件
        pairs = []
        for new_evt in new_events:
            for old_evt in all_events:
                if old_evt.id == new_evt.id:
                    continue
                if old_evt.id in network._analyzed_ids and \
                   new_evt.id in network._analyzed_ids:
                    continue  # 两个都分析过了

                if new_evt.timestamp < old_evt.timestamp:
                    cause, effect = new_evt, old_evt
                elif old_evt.timestamp < new_evt.timestamp:
                    cause, effect = old_evt, new_evt
                else:
                    continue
                pairs.append((cause, effect))

        # 图谱评分 + LLM 分析（复用 find_causal_chains 的逻辑）
        new_chains = self._analyze_pairs(pairs, min_confidence)

        for chain in new_chains:
            network.add_chain(chain)

        # 标记已分析
        for evt in new_events:
            network._analyzed_ids.add(evt.id)

        # 增量多跳：只从新事件出发
        if multihop and new_chains:
            # 临时构建只含新链的子网络做多跳
            sub = CausalNetwork()
            for chain in new_chains:
                sub.add_chain(chain)
            indirect = sub.find_multihop_chains(
                max_hops=max_hops,
                min_confidence=min_confidence * 0.5,
                confidence_decay=0.7,
            )
            for chain in indirect:
                network.add_chain(chain)

        return network

    def _analyze_pairs(
        self,
        pairs: List[tuple],
        min_confidence: float,
    ) -> List[CausalChain]:
        """分析事件对，返回因果链（复用于增量更新）"""
        from .causal_graph import CausalGraph
        graph = CausalGraph()

        fast_lane = []
        slow_lane = []

        for cause, effect in pairs:
            all_tags = cause.tags + effect.tags
            graph_result = graph.score(cause.summary, effect.summary, all_tags)

            if graph_result.known and graph_result.score > 0:
                chain = CausalChain(
                    cause_event=cause,
                    effect_event=effect,
                    time_gap=effect.timestamp - cause.timestamp,
                    confidence=graph_result.score,
                    description=f"{cause.summary} -> {effect.summary} [graph]",
                )
                fast_lane.append(chain)
            elif graph_result.source == "partial":
                slow_lane.append((cause, effect))

        # 规则引擎评分（不依赖 LLM）
        for cause, effect in slow_lane:
            confidence = self._calculate_causality_confidence(cause, effect)
            if confidence >= min_confidence:
                chain = CausalChain(
                    cause_event=cause,
                    effect_event=effect,
                    time_gap=effect.timestamp - cause.timestamp,
                    confidence=confidence,
                    description=self._generate_causal_description(cause, effect),
                )
                fast_lane.append(chain)

        return fast_lane

    def _find_indirect_chains(
        self, events: List[TimelineEvent]
    ) -> List[CausalChain]:
        """发现间接因果链（A→B→C）"""
        chains = []
        for i, mid_event in enumerate(events):
            mid_text = self._get_event_text(mid_event).lower()
            for chain_def in self.CAUSAL_INDIRECT_CHAINS:
                trigger_concepts, mid_concepts, effect_concepts, boost = chain_def
                # 检查中间事件是否匹配中间概念
                if not self._matches_concepts(mid_text, mid_concepts):
                    continue
                # 向前找触发事件
                for j in range(i):
                    cause_event = events[j]
                    cause_text = self._get_event_text(cause_event).lower()
                    if not self._matches_concepts(cause_text, trigger_concepts):
                        continue
                    # 向后找结果事件
                    for k in range(i + 1, len(events)):
                        effect_event = events[k]
                        effect_text = self._get_event_text(effect_event).lower()
                        if not self._matches_concepts(effect_text, effect_concepts):
                            continue
                        time_gap = effect_event.timestamp - cause_event.timestamp
                        if time_gap < timedelta(days=365):
                            chains.append(CausalChain(
                                cause_event=cause_event,
                                effect_event=effect_event,
                                time_gap=time_gap,
                                confidence=min(0.7, boost + 0.2),
                                description=self._generate_causal_description(
                                    cause_event, effect_event
                                ) + " [间接因果]",
                            ))
        return chains

    def _generate_causal_description(
        self, cause: TimelineEvent, effect: TimelineEvent
    ) -> str:
        cause_summary = cause.summary or "事件A"
        effect_summary = effect.summary or "事件B"
        # 尝试识别因果关系类型
        cause_text = self._get_event_text(cause).lower()
        effect_text = self._get_event_text(effect).lower()
        relation = "→"
        for trigger_kw, effect_kw_set in [
            ("加息", {"利率", "借贷", "融资"}),
            ("降息", {"利率", "借贷", "融资"}),
            ("通胀", {"加息", "紧缩"}),
            ("裁员", {"利润", "盈利"}),
        ]:
            if trigger_kw in cause_text:
                for ek in effect_kw_set:
                    if ek in effect_text:
                        relation = "导致"
                        break
        return f"{cause_summary} {relation} {effect_summary}"

    def _get_event_text(self, event: TimelineEvent) -> str:
        return (event.summary or "") + " " + " ".join(event.tags) + " " + str(event.data or "")

    def _matches_concepts(self, text: str, concepts: frozenset) -> bool:
        return any(concept in text for concept in concepts)

    def _calculate_causality_confidence(
        self, cause: TimelineEvent, effect: TimelineEvent
    ) -> float:
        confidence = 0.05  # 基础分降低，避免所有事件对都过阈值

        cause_text = self._get_event_text(cause).lower()
        effect_text = self._get_event_text(effect).lower()

        # 1. 因果概念图谱匹配（最高权重）
        concept_score = 0.0
        for trigger_concepts, effect_concepts, boost in self.CAUSAL_CONCEPT_PAIRS:
            if self._matches_concepts(cause_text, trigger_concepts) and \
               self._matches_concepts(effect_text, effect_concepts):
                concept_score = max(concept_score, boost)
        confidence += concept_score

        # 2. 语义对立检测（对立事件有因果关系）
        antonym_score = 0.0
        for pos_concepts, neg_concepts, boost in self.CAUSAL_ANTONYM_PAIRS:
            cause_has_pos = self._matches_concepts(cause_text, pos_concepts)
            cause_has_neg = self._matches_concepts(cause_text, neg_concepts)
            effect_has_pos = self._matches_concepts(effect_text, pos_concepts)
            effect_has_neg = self._matches_concepts(effect_text, neg_concepts)
            # 因为正→果为负，或因为负→果为正
            if (cause_has_pos and effect_has_neg) or (cause_has_neg and effect_has_pos):
                antonym_score = max(antonym_score, boost)
        confidence += antonym_score

        # 3. 标签重叠（权重降低，标签是相关性不是因果性）
        common_tags = set(cause.tags) & set(effect.tags)
        if common_tags:
            confidence += min(len(common_tags) * 0.03, 0.08)

        # 4. 关键词重叠（权重降低）
        all_pest_kw = set()
        for kws in self.PEST_KEYWORDS.values():
            all_pest_kw.update(kws)
        all_swot_kw = set()
        for kws in self.SWOT_KEYWORDS.values():
            all_swot_kw.update(kws)
        all_kw = all_pest_kw | all_swot_kw

        cause_kw = {kw for kw in all_kw if kw in cause_text}
        effect_kw = {kw for kw in all_kw if kw in effect_text}
        shared_kw = cause_kw & effect_kw
        if shared_kw:
            confidence += min(len(shared_kw) * 0.02, 0.06)

        # 4b. 反向惩罚：果事件包含"因型"关键词（发布/公布/推出/扩产）
        #     说明果更可能是主动行为者，不是被动结果
        cause_action_keywords = [
            "发布", "公布", "推出", "宣布", "扩产", "投产", "量产",
            "突破", "创新", "签署", "获批", "收购", "合并",
            "市值", "股价", "估值", "融资", "上市", "ipo",
        ]
        effect_action_hits = sum(1 for kw in cause_action_keywords if kw in effect_text)
        if effect_action_hits > 0:
            confidence -= effect_action_hits * 0.12

        # 4c. 同实体惩罚：因和果是同一公司/主题，且果是主动行为
        #     例：英伟达市值→英伟达发布产品，后者是前者的原因，不是结果
        cause_entities = {tag for tag in cause.tags}
        effect_entities = {tag for tag in effect.tags}
        shared_entities = cause_entities & effect_entities
        if shared_entities and effect_action_hits > 0:
            # 同一实体的"主动行为"事件更可能是原因而非结果
            confidence -= 0.1

        # 5. 时间衰减（非线性，越近越强）
        time_gap = effect.timestamp - cause.timestamp
        days = time_gap.days
        if days <= 7:
            confidence += 0.25
        elif days <= 30:
            confidence += 0.2
        elif days <= 90:
            confidence += 0.1
        elif days <= 180:
            confidence += 0.05
        elif days > 365:
            confidence -= 0.05  # 超过一年略微惩罚

        # 6. 来源可靠性加成
        if cause.source_reliability.value >= 4 and effect.source_reliability.value >= 4:
            confidence += 0.05

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