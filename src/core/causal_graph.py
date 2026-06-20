"""因果图谱引擎 — 自适应因果关系评分

核心设计：
- 图谱认识的 → 快车道（免费，返回 score + known=True）
- 图谱不认识的 → 慢车道（返回 known=False，触发 LLM 兜底）
- 支持自动扩充（LLM 挖掘结果写入图谱）

数据源：
1. 内置概念对（硬编码先验知识）
2. ConceptNet API（待接入）
3. LLM 挖掘结果自动扩充
"""
import json
import os
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class GraphResult:
    """图谱评分结果"""
    score: float = 0.0         # 因果得分 0~1
    known: bool = False        # 图谱是否认识这对关系
    source: str = ""           # 来源：builtin / conceptnet / learned
    match_info: str = ""       # 匹配详情（调试用）


@dataclass
class ConceptPair:
    """因果概念对"""
    trigger: set               # 因的关键词集合
    effect: set                # 果的关键词集合
    weight: float              # 权重 0~1
    source: str = "builtin"    # 来源
    domain: str = ""           # 领域


class CausalGraph:
    """因果图谱引擎"""

    def __init__(self, persist_path: str = ""):
        self.pairs: List[ConceptPair] = []
        self.persist_path = persist_path or self._default_path()
        self._load_builtin()
        self._load_learned()

    def _default_path(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "..", "data", "learned_graph.json")

    # ═══ 内置概念对 ═══

    def _load_builtin(self):
        """加载内置先验知识"""
        builtin = [
            # 货币政策
            ConceptPair({"加息", "紧缩", "升息", "上调基点", "interest rate", "rate hike"},
                        {"股市", "下跌", "暴跌", "全线下跌", "下挫", "stock", "decline"}, 0.35, "builtin", "金融"),
            ConceptPair({"降息", "宽松", "降准", "下调准备金", "rate cut"},
                        {"股市", "上涨", "反弹", "流动性改善", "stock", "rise"}, 0.35, "builtin", "金融"),
            ConceptPair({"负利率", "结束负利率"},
                        {"汇率", "升值", "日元"}, 0.35, "builtin", "金融"),
            ConceptPair({"降息", "宽松", "降准"},
                        {"房地产", "楼市", "成交量", "回升"}, 0.3, "builtin", "房地产"),
            ConceptPair({"CPI", "通胀", "低于预期", "inflation"},
                        {"降息", "收益率下行", "债券"}, 0.35, "builtin", "宏观"),
            ConceptPair({"非农", "就业人数", "超预期", "employment"},
                        {"美元", "美元指数", "走强", "dollar"}, 0.35, "builtin", "宏观"),
            ConceptPair({"PMI", "重回扩张"},
                        {"经济复苏", "周期股", "上涨"}, 0.3, "builtin", "宏观"),
            # 大宗商品
            ConceptPair({"OPEC", "减产", "oil cut"},
                        {"原油", "油价", "飙升", "上涨", "oil", "crude"}, 0.35, "builtin", "大宗商品"),
            ConceptPair({"冲突", "战争", "封锁", "conflict", "war"},
                        {"小麦", "粮食", "期货", "涨停", "wheat"}, 0.35, "builtin", "大宗商品"),
            ConceptPair({"干旱", "运河", "航运"},
                        {"运输成本", "航运股", "上涨"}, 0.3, "builtin", "大宗商品"),
            ConceptPair({"油价", "原油", "oil"},
                        {"通胀", "CPI", "物价", "inflation"}, 0.3, "builtin", "大宗商品"),
            # 公司经营
            ConceptPair({"财报", "营收不及预期", "earnings"},
                        {"股价", "大跌", "下跌", "stock", "decline"}, 0.35, "builtin", "公司"),
            ConceptPair({"财报", "盈利超预期"},
                        {"股价", "上涨"}, 0.35, "builtin", "公司"),
            ConceptPair({"芯片", "AI", "算力", "chip", "semiconductor"},
                        {"纳斯达克", "科技股", "上涨", "nasdaq"}, 0.3, "builtin", "科技"),
            ConceptPair({"债务违约", "暴雷", "default"},
                        {"债券", "下跌", "信用风险", "担忧蔓延"}, 0.35, "builtin", "金融"),
            ConceptPair({"ETF", "获批", "现货"},
                        {"比特币", "新高", "资金流入", "bitcoin"}, 0.35, "builtin", "加密"),
            ConceptPair({"并购", "收购", "merger", "acquisition"},
                        {"股价", "波动", "板块"}, 0.25, "builtin", "公司"),
            # 地缘
            ConceptPair({"冲突", "升级"},
                        {"原油", "油价", "上涨"}, 0.3, "builtin", "地缘"),
            # 政策
            ConceptPair({"产业政策", "规划", "补贴"},
                        {"板块", "概念股", "上涨"}, 0.3, "builtin", "政策"),
            ConceptPair({"取消限购", "限购"},
                        {"房地产", "成交量", "回升"}, 0.35, "builtin", "政策"),
            # 市场情绪
            ConceptPair({"银行", "倒闭", "流动性危机", "bank", "collapse"},
                        {"银行股", "暴跌", "恐慌", "蔓延"}, 0.35, "builtin", "金融"),
            ConceptPair({"推文", "社交媒体", "马斯克", "tweet", "musk"},
                        {"加密货币", "暴涨", "暴跌", "crypto"}, 0.3, "builtin", "加密"),
            # 央行/黄金
            ConceptPair({"央行", "增持", "储备", "central bank"},
                        {"黄金", "金价", "上涨", "gold"}, 0.3, "builtin", "大宗商品"),
            # 消费
            ConceptPair({"新能源", "发展规划"},
                        {"新能源汽车", "板块", "上涨"}, 0.3, "builtin", "政策"),
        ]
        self.pairs.extend(builtin)

    # ═══ 持久化（学习结果 + ConceptNet）═══

    def _load_learned(self):
        """加载 LLM 学习到的概念对 + ConceptNet 数据"""
        # 加载 LLM 学习结果
        learned_path = self.persist_path
        if os.path.exists(learned_path):
            try:
                with open(learned_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    self.pairs.append(ConceptPair(
                        trigger=set(item["trigger"]),
                        effect=set(item["effect"]),
                        weight=item.get("weight", 0.3),
                        source="learned",
                        domain=item.get("domain", ""),
                    ))
            except Exception:
                pass

        # 加载 ConceptNet 因果关系
        cn_path = os.path.join(os.path.dirname(self.persist_path), "conceptnet_causal.json")
        if os.path.exists(cn_path):
            try:
                with open(cn_path, "r", encoding="utf-8") as f:
                    cn_data = json.load(f)
                # 只加载金融/经济相关的，避免图谱过大
                finance_kw = {"econom", "financ", "stock", "bank", "inflati", "interest",
                              "invest", "market", "price", "money", "tax", "trade",
                              "gdp", "unemploy", "金融", "股票", "银行", "经济", "利率",
                              "通胀", "投资", "市场", "价格", "货币", "贸易"}
                for item in cn_data:
                    start = item["start"].lower()
                    end = item["end"].lower()
                    if any(kw in start or kw in end for kw in finance_kw):
                        self.pairs.append(ConceptPair(
                            trigger={item["start"]},
                            effect={item["end"]},
                            weight=0.25,
                            source="conceptnet",
                            domain="金融",
                        ))
                print(f"  [causal_graph] 加载 ConceptNet: {sum(1 for p in self.pairs if p.source=='conceptnet')} 条")
            except Exception as e:
                print(f"  [causal_graph] ConceptNet 加载失败: {e}")

    def save_learned(self):
        """保存学习到的概念对"""
        learned = [p for p in self.pairs if p.source == "learned"]
        if not learned:
            return
        os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
        data = [
            {"trigger": list(p.trigger), "effect": list(p.effect),
             "weight": p.weight, "domain": p.domain}
            for p in learned
        ]
        with open(self.persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ═══ 评分 ═══

    def score(self, cause: str, effect: str, tags: List[str] = None) -> GraphResult:
        """因果关系评分

        Returns:
            GraphResult:
            - score > 0, known=True: 图谱认识，有因果
            - score = 0, known=True: 图谱认识，无因果
            - score = 0, known=False: 图谱不认识，需要 LLM 兜底
        """
        text = cause + " " + effect + " " + " ".join(tags or [])
        text_lower = text.lower()

        best_score = 0.0
        best_match = ""
        trigger_found = False  # 是否有触发词命中

        for pair in self.pairs:
            # 检查触发词
            trigger_hit = any(kw.lower() in text_lower for kw in pair.trigger)
            if not trigger_hit:
                continue

            trigger_found = True

            # 检查效果词
            effect_hit = any(kw.lower() in text_lower for kw in pair.effect)
            if effect_hit:
                if pair.weight > best_score:
                    best_score = pair.weight
                    best_match = f"{pair.trigger & {kw for kw in pair.trigger if kw.lower() in text_lower}}→{pair.effect & {kw for kw in pair.effect if kw.lower() in text_lower}} [{pair.source}]"

        if best_score > 0:
            # 图谱认识，有因果
            return GraphResult(score=best_score, known=True,
                              source="builtin", match_info=best_match)

        if trigger_found:
            # 有触发词但没匹配效果词 → 不确定
            return GraphResult(score=0, known=False,
                              source="partial", match_info="触发词命中但效果词未命中")

        # 完全不认识
        return GraphResult(score=0, known=False,
                          source="unknown", match_info="图谱中无匹配")

    # ═══ 学习 ═══

    def learn_from_chain(self, cause_summary: str, effect_summary: str,
                         cause_tags: List[str], effect_tags: List[str],
                         confidence: float, domain: str = ""):
        """从 LLM 挖掘的因果链中学习新概念对"""
        # 提取关键词作为触发词和效果词
        trigger_words = set(cause_tags)
        effect_words = set(effect_tags)

        # 从摘要中提取中文词（2字以上）
        trigger_words.update(re.findall(r'[\u4e00-\u9fff]{2,}', cause_summary))
        effect_words.update(re.findall(r'[\u4e00-\u9fff]{2,}', effect_summary))

        # 去除常见停用词
        stopwords = {"的", "了", "在", "是", "和", "与", "对", "将", "已", "被", "从", "到"}
        trigger_words -= stopwords
        effect_words -= stopwords

        if not trigger_words or not effect_words:
            return

        # 检查是否已有类似概念对
        for pair in self.pairs:
            if pair.source == "learned":
                if trigger_words & pair.trigger and effect_words & pair.effect:
                    # 已有类似对，更新权重（取较高值）
                    pair.weight = max(pair.weight, confidence * 0.8)
                    pair.trigger |= trigger_words
                    pair.effect |= effect_words
                    self.save_learned()
                    return

        # 新增概念对
        new_pair = ConceptPair(
            trigger=trigger_words,
            effect=effect_words,
            weight=min(0.4, confidence * 0.8),  # 学习到的权重略低于内置
            source="learned",
            domain=domain,
        )
        self.pairs.append(new_pair)
        self.save_learned()

    # ═══ 统计 ═══

    def stats(self) -> Dict:
        builtin = sum(1 for p in self.pairs if p.source == "builtin")
        learned = sum(1 for p in self.pairs if p.source == "learned")
        return {
            "total_pairs": len(self.pairs),
            "builtin": builtin,
            "learned": learned,
        }


# ═══ 全局实例 ═══
causal_graph = CausalGraph()
