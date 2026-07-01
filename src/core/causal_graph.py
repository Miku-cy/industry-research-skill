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
import threading
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
        self._pairs: List[ConceptPair] = []
        self.persist_path = persist_path or self._default_path()
        self._loaded = False
        self._load_lock = threading.Lock()
        self._trigger_index: Dict[str, List[int]] = {}
        self._effect_index: Dict[str, List[int]] = {}

    @property
    def pairs(self) -> List[ConceptPair]:
        self._ensure_loaded()
        return self._pairs

    def _ensure_loaded(self):
        """懒加载：首次调用时才加载数据和构建索引（线程安全）

        使用双重检查锁定避免多线程首次调用时重复加载 builtin/conceptnet/learned
        导致索引与 _pairs 不一致。
        """
        if not self._loaded:
            with self._load_lock:
                if not self._loaded:
                    self._load_builtin()
                    self._load_learned()
                    self._build_index()
                    self._loaded = True

    def _default_path(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "..", "data", "learned_graph.json")

    def _build_index(self):
        """构建倒排索引：关键词 → 概念对索引

        score() 从 O(N) 遍历优化为 O(k) 候选查找
        """
        self._trigger_index: Dict[str, List[int]] = {}  # keyword → pair indices
        self._effect_index: Dict[str, List[int]] = {}
        for i, pair in enumerate(self._pairs):
            for kw in pair.trigger:
                key = kw.lower()
                if key not in self._trigger_index:
                    self._trigger_index[key] = []
                self._trigger_index[key].append(i)
            for kw in pair.effect:
                key = kw.lower()
                if key not in self._effect_index:
                    self._effect_index[key] = []
                self._effect_index[key].append(i)

    def _rebuild_index(self):
        """学习新概念对后重建索引"""
        self._build_index()

    # ═══ 内置概念对 ═══

    def _load_builtin(self):
        """加载内置先验知识"""
        builtin = [
            # ═══ 金融与资本市场 ═══
            ConceptPair({"加息", "紧缩", "升息", "上调基点", "rate hike"},
                        {"股市", "下跌", "暴跌", "下挫", "回调", "stock", "decline"}, 0.35, "builtin", "金融"),
            ConceptPair({"降息", "宽松", "降准", "rate cut"},
                        {"股市", "上涨", "反弹", "流动性改善"}, 0.35, "builtin", "金融"),
            ConceptPair({"负利率", "结束负利率"},
                        {"汇率", "升值", "日元"}, 0.35, "builtin", "金融"),
            ConceptPair({"CPI", "通胀", "低于预期"},
                        {"降息", "收益率下行", "债券上涨"}, 0.35, "builtin", "宏观"),
            ConceptPair({"非农", "就业超预期", "就业人数"},
                        {"美元", "走强", "加息预期"}, 0.35, "builtin", "宏观"),
            ConceptPair({"PMI", "重回扩张", "景气"},
                        {"经济复苏", "周期股", "上涨"}, 0.3, "builtin", "宏观"),
            ConceptPair({"债务违约", "暴雷", "default"},
                        {"信用风险", "担忧蔓延", "债券下跌"}, 0.35, "builtin", "金融"),
            ConceptPair({"银行", "倒闭", "流动性危机"},
                        {"银行股", "暴跌", "恐慌", "蔓延"}, 0.35, "builtin", "金融"),
            ConceptPair({"ETF", "获批"},
                        {"资金流入", "上涨", "新高"}, 0.3, "builtin", "金融"),
            ConceptPair({"融资", "杠杆", "配资"},
                        {"风险", "爆仓", "强平"}, 0.3, "builtin", "金融"),
            ConceptPair({"北向资金", "外资", "流入"},
                        {"A股", "上涨", "反弹"}, 0.3, "builtin", "金融"),
            ConceptPair({"回购", "增持", "分红"},
                        {"股价", "支撑", "利好"}, 0.3, "builtin", "金融"),
            ConceptPair({"减持", "大股东", "解禁"},
                        {"股价", "承压", "下跌"}, 0.3, "builtin", "金融"),
            ConceptPair({"IPO", "上市", "新股"},
                        {"市场", "扩容", "资金分流"}, 0.25, "builtin", "金融"),

            # ═══ 宏观经济 ═══
            ConceptPair({"GDP", "增速", "超预期"},
                        {"经济向好", "股市上涨", "信心"}, 0.3, "builtin", "宏观"),
            ConceptPair({"GDP", "增速", "放缓", "低于预期"},
                        {"经济下行", "衰退担忧", "刺激预期"}, 0.3, "builtin", "宏观"),
            ConceptPair({"M2", "社融", "信贷", "放量"},
                        {"流动性", "宽松", "资产价格"}, 0.3, "builtin", "宏观"),
            ConceptPair({"贸易顺差", "出口", "超预期"},
                        {"经济增长", "外汇储备"}, 0.3, "builtin", "宏观"),
            ConceptPair({"贸易逆差", "出口", "下滑"},
                        {"经济承压", "汇率贬值"}, 0.3, "builtin", "宏观"),
            ConceptPair({"失业率", "就业", "恶化"},
                        {"消费下降", "经济衰退"}, 0.3, "builtin", "宏观"),
            ConceptPair({"美联储", "鸽派", "暂停加息"},
                        {"风险资产", "上涨", "美元走弱"}, 0.35, "builtin", "宏观"),
            ConceptPair({"美联储", "鹰派", "超预期加息"},
                        {"风险资产", "下跌", "美元走强"}, 0.35, "builtin", "宏观"),

            # ═══ 科技与半导体 ═══
            ConceptPair({"芯片", "AI", "算力", "半导体"},
                        {"科技股", "上涨", "纳斯达克"}, 0.3, "builtin", "科技"),
            ConceptPair({"产能", "扩产", "晶圆代工"},
                        {"供给增加", "价格下行", "竞争加剧"}, 0.3, "builtin", "科技"),
            ConceptPair({"减产", "产能不足", "供不应求"},
                        {"价格上涨", "缺货", "订单积压"}, 0.35, "builtin", "科技"),
            ConceptPair({"制程", "突破", "量产"},
                        {"竞争力", "提升", "客户导入"}, 0.3, "builtin", "科技"),
            ConceptPair({"良率", "不足", "缺陷"},
                        {"延迟", "成本上升", "客户流失"}, 0.3, "builtin", "科技"),
            ConceptPair({"大模型", "GPT", "发布"},
                        {"AI概念", "算力需求", "上涨"}, 0.3, "builtin", "科技"),
            ConceptPair({"数据中心", "建设", "扩建"},
                        {"服务器", "芯片", "需求增长"}, 0.3, "builtin", "科技"),
            ConceptPair({"制裁", "出口管制", "实体清单"},
                        {"供应链", "中断", "国产替代"}, 0.35, "builtin", "科技"),
            ConceptPair({"存储芯片", "DRAM", "NAND", "价格上涨"},
                        {"存储厂商", "利润改善", "股价上涨"}, 0.35, "builtin", "科技"),
            ConceptPair({"存储芯片", "DRAM", "NAND", "价格下跌"},
                        {"存储厂商", "利润下滑", "股价下跌"}, 0.35, "builtin", "科技"),

            # ═══ 大宗商品与能源 ═══
            ConceptPair({"OPEC", "减产"},
                        {"原油", "油价", "上涨"}, 0.35, "builtin", "大宗商品"),
            ConceptPair({"冲突", "战争", "地缘"},
                        {"原油", "黄金", "上涨", "避险", "小麦", "粮食"}, 0.35, "builtin", "大宗商品"),
            ConceptPair({"干旱", "运河", "航运"},
                        {"运输成本", "航运股", "上涨"}, 0.3, "builtin", "大宗商品"),
            ConceptPair({"油价", "原油", "上涨"},
                        {"通胀", "CPI", "上行"}, 0.3, "builtin", "大宗商品"),
            ConceptPair({"央行", "增持", "购金"},
                        {"黄金", "金价", "上涨"}, 0.35, "builtin", "大宗商品"),
            ConceptPair({"美元", "走强"},
                        {"黄金", "承压", "下跌"}, 0.3, "builtin", "大宗商品"),
            ConceptPair({"美元", "走弱"},
                        {"黄金", "上涨", "大宗商品上涨"}, 0.3, "builtin", "大宗商品"),
            ConceptPair({"库存", "累积", "高库存"},
                        {"价格", "下跌", "去库存"}, 0.3, "builtin", "大宗商品"),
            ConceptPair({"库存", "下降", "低库存"},
                        {"价格", "上涨", "补库存"}, 0.3, "builtin", "大宗商品"),
            ConceptPair({"铜", "上涨"},
                        {"经济复苏", "需求改善", "通胀预期"}, 0.25, "builtin", "大宗商品"),
            ConceptPair({"锂", "碳酸锂", "价格下跌"},
                        {"电池成本", "下降", "新能源车"}, 0.3, "builtin", "大宗商品"),

            # ═══ 企业与组织 ═══
            ConceptPair({"财报", "营收不及预期", "利润下滑"},
                        {"股价", "大跌", "下跌"}, 0.35, "builtin", "企业"),
            ConceptPair({"财报", "盈利超预期", "营收增长"},
                        {"股价", "上涨", "反弹"}, 0.35, "builtin", "企业"),
            ConceptPair({"裁员", "降本", "重组"},
                        {"短期利空", "长期利好", "利润改善"}, 0.25, "builtin", "企业"),
            ConceptPair({"并购", "收购"},
                        {"股价", "波动", "整合风险"}, 0.25, "builtin", "企业"),
            ConceptPair({"产品发布", "新品", "爆款"},
                        {"营收增长", "股价上涨"}, 0.3, "builtin", "企业"),
            ConceptPair({"管理层", "变更", "CEO离职"},
                        {"不确定性", "股价波动"}, 0.25, "builtin", "企业"),
            ConceptPair({"研发投入", "增加"},
                        {"技术壁垒", "长期竞争力"}, 0.2, "builtin", "企业"),

            # ═══ 政策与治理 ═══
            ConceptPair({"产业政策", "规划", "补贴"},
                        {"板块", "概念股", "上涨"}, 0.3, "builtin", "政策"),
            ConceptPair({"取消限购", "限购", "放松"},
                        {"房地产", "成交量", "回升"}, 0.35, "builtin", "政策"),
            ConceptPair({"加息", "央行", "收紧"},
                        {"流动性", "收紧", "资产价格下跌"}, 0.35, "builtin", "政策"),
            ConceptPair({"降息", "央行", "宽松"},
                        {"流动性", "宽松", "资产价格上涨"}, 0.35, "builtin", "政策"),
            ConceptPair({"制裁", "关税", "贸易战"},
                        {"供应链", "中断", "成本上升"}, 0.35, "builtin", "政策"),
            ConceptPair({"反垄断", "罚款", "调查"},
                        {"公司股价", "下跌", "监管风险"}, 0.3, "builtin", "政策"),
            ConceptPair({"碳中和", "碳交易", "碳税"},
                        {"能源转型", "新能源", "传统能源承压"}, 0.3, "builtin", "政策"),
            ConceptPair({"芯片法案", "补贴", "产业扶持"},
                        {"半导体", "投资增加", "产能扩张"}, 0.35, "builtin", "政策"),

            # ═══ 加密货币与区块链 ═══
            ConceptPair({"ETF", "比特币", "获批"},
                        {"比特币", "新高", "资金流入"}, 0.35, "builtin", "加密"),
            ConceptPair({"监管", "打击", "禁止"},
                        {"加密货币", "暴跌", "恐慌"}, 0.35, "builtin", "加密"),
            ConceptPair({"减半", "比特币"},
                        {"供给减少", "价格上涨"}, 0.3, "builtin", "加密"),
            ConceptPair({"交易所", "暴雷", "破产"},
                        {"信任危机", "抛售", "暴跌"}, 0.35, "builtin", "加密"),
            ConceptPair({"推文", "马斯克", "社交媒体"},
                        {"加密货币", "暴涨", "暴跌"}, 0.3, "builtin", "加密"),

            # ═══ 游戏与数字娱乐 ═══
            ConceptPair({"版号", "发放", "审批"},
                        {"游戏股", "上涨", "利好"}, 0.35, "builtin", "游戏"),
            ConceptPair({"爆款", "上线", "流水超预期"},
                        {"游戏公司", "营收增长", "股价上涨"}, 0.35, "builtin", "游戏"),
            ConceptPair({"游戏", "监管", "限制"},
                        {"游戏股", "下跌", "利空"}, 0.3, "builtin", "游戏"),

            # ═══ 国际关系与地缘 ═══
            ConceptPair({"冲突", "升级", "战争"},
                        {"避险", "黄金上涨", "股市下跌"}, 0.35, "builtin", "地缘"),
            ConceptPair({"冲突", "升级", "中东"},
                        {"原油", "油价", "上涨"}, 0.35, "builtin", "地缘"),
            ConceptPair({"制裁", "俄罗斯"},
                        {"能源", "价格上涨", "供应链"}, 0.3, "builtin", "地缘"),
            ConceptPair({"台海", "紧张", "军演"},
                        {"半导体", "供应链风险", "避险"}, 0.3, "builtin", "地缘"),

            # ═══ 环境与气候 ═══
            ConceptPair({"极端天气", "洪水", "干旱"},
                        {"农产品", "减产", "价格上涨"}, 0.35, "builtin", "环境"),
            ConceptPair({"碳中和", "新能源"},
                        {"光伏", "风电", "储能", "需求增长"}, 0.3, "builtin", "环境"),
            ConceptPair({"电动车", "渗透率", "提升"},
                        {"锂电池", "充电桩", "需求增长"}, 0.3, "builtin", "环境"),

            # ═══ 社会与文化 ═══
            ConceptPair({"疫情", "爆发", "封锁"},
                        {"经济", "停摆", "消费下降"}, 0.35, "builtin", "社会"),
            ConceptPair({"人口", "老龄化"},
                        {"劳动力", "短缺", "养老需求"}, 0.3, "builtin", "社会"),
            ConceptPair({"消费", "降级", "信心下降"},
                        {"零售", "下滑", "经济放缓"}, 0.3, "builtin", "社会"),

            # ═══ 医疗与健康 ═══
            ConceptPair({"疫情", "爆发", "传染病"},
                        {"疫苗", "需求激增", "医药股上涨"}, 0.35, "builtin", "医疗"),
            ConceptPair({"新药", "获批", "临床试验"},
                        {"药企", "股价上涨", "专利保护"}, 0.3, "builtin", "医疗"),
            ConceptPair({"集采", "医保", "降价"},
                        {"药企", "利润承压", "股价下跌"}, 0.3, "builtin", "医疗"),
        ]
        self._pairs.extend(builtin)

    def _load_learned(self):
        """加载 LLM 学习到的概念对 + ConceptNet 数据"""
        # 加载 LLM 学习结果
        learned_path = self.persist_path
        if os.path.exists(learned_path):
            try:
                with open(learned_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    self._pairs.append(ConceptPair(
                        trigger=set(item["trigger"]),
                        effect=set(item["effect"]),
                        weight=item.get("weight", 0.3),
                        source="learned",
                        domain=item.get("domain", ""),
                    ))
            except Exception:
                pass

        # 加载 ConceptNet 因果关系（英文原版）
        cn_path = os.path.join(os.path.dirname(self.persist_path), "conceptnet_causal.json")
        if os.path.exists(cn_path):
            try:
                with open(cn_path, "r", encoding="utf-8") as f:
                    cn_data = json.load(f)
                finance_kw = {"econom", "financ", "stock", "bank", "inflati", "interest",
                              "invest", "market", "price", "money", "tax", "trade",
                              "gdp", "unemploy", "金融", "股票", "银行", "经济", "利率",
                              "通胀", "投资", "市场", "价格", "货币", "贸易"}
                for item in cn_data:
                    start = item["start"].lower()
                    end = item["end"].lower()
                    if any(kw in start or kw in end for kw in finance_kw):
                        self._pairs.append(ConceptPair(
                            trigger={item["start"]},
                            effect={item["end"]},
                            weight=0.25,
                            source="conceptnet",
                            domain="金融",
                        ))
            except Exception:
                pass

        # 加载 ConceptNet 中文扩展版（繁→简转换+领域筛选后）
        cn_zh_path = os.path.join(os.path.dirname(self.persist_path), "conceptnet_causal_zh.json")
        if os.path.exists(cn_zh_path):
            try:
                with open(cn_zh_path, "r", encoding="utf-8") as f:
                    cn_zh_data = json.load(f)
                for item in cn_zh_data:
                    self._pairs.append(ConceptPair(
                        trigger={item["start"]},
                        effect={item["end"]},
                        weight=item.get("weight", 0.25),
                        source="conceptnet",
                        domain="通用",
                    ))
            except Exception:
                pass

        cn_count = sum(1 for p in self._pairs if p.source == "conceptnet")
        print(f"  [causal_graph] 加载 ConceptNet: {cn_count} 条")

    def save_learned(self):
        """保存学习到的概念对"""
        learned = [p for p in self._pairs if p.source == "learned"]
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

    def score(self, cause: str, effect: str, tags: List[str] = None,
              cause_tags: List[str] = None, effect_tags: List[str] = None) -> GraphResult:
        """因果关系评分（方向敏感）

        关键：触发词必须在因文本中，效果词必须在果文本中。
        这样才能区分方向：加息→股市下跌 ✓，股市下跌→加息 ✗

        Args:
            cause: 因事件摘要
            effect: 果事件摘要
            tags: 旧参数，会同时拼到因/果两端（向后兼容，破坏方向性，不推荐）
            cause_tags: 仅拼到因文本（推荐，保留方向性）
            effect_tags: 仅拼到果文本（推荐，保留方向性）
        """
        self._ensure_loaded()
        if cause_tags is not None or effect_tags is not None:
            # 方向分离接口（推荐）
            ct = cause_tags or []
            et = effect_tags or []
        else:
            # 旧接口：tags 同时拼到两端（破坏方向性，仅向后兼容）
            ct = tags or []
            et = tags or []
        cause_text = (cause + " " + " ".join(ct)).lower()
        effect_text = (effect + " " + " ".join(et)).lower()

        best_score = 0.0
        best_match = ""
        best_source = "builtin"
        trigger_found = False

        # 倒排索引优化：只检查包含命中关键词的概念对
        candidate_indices = set()
        # 英文 token（空格分隔）
        for kw in cause_text.split():
            if kw in self._trigger_index:
                candidate_indices.update(self._trigger_index[kw])
        # 中文 2-4 字 token（中文没有空格，split 拿不到，需用正则提取候选词）
        for cn_kw in re.findall(r'[\u4e00-\u9fff]{2,4}', cause_text):
            if cn_kw in self._trigger_index:
                candidate_indices.update(self._trigger_index[cn_kw])
        # 兜底：子串匹配（处理图谱关键词长度 > 4 或含混合字符的情况）
        # 复杂度 O(K)，K = 索引中关键词数，作为正则提取的补集
        for key, indices in self._trigger_index.items():
            if len(key) > 1 and key in cause_text:
                candidate_indices.update(indices)

        for idx in candidate_indices:
            pair = self._pairs[idx]
            trigger_hit = any(kw.lower() in cause_text for kw in pair.trigger)
            if not trigger_hit:
                continue

            trigger_found = True

            effect_hit = any(kw.lower() in effect_text for kw in pair.effect)
            if effect_hit:
                if pair.weight > best_score:
                    best_score = pair.weight
                    best_source = pair.source  # 保留真实来源（builtin/conceptnet/learned）
                    matched_triggers = {kw for kw in pair.trigger if kw.lower() in cause_text}
                    matched_effects = {kw for kw in pair.effect if kw.lower() in effect_text}
                    best_match = f"{matched_triggers}->{matched_effects} [{pair.source}]"

        if best_score > 0:
            return GraphResult(score=best_score, known=True,
                              source=best_source, match_info=best_match)

        if trigger_found:
            # 反向检查：只检查已命中的候选对
            reverse_candidates = set()
            for kw in effect_text.split():
                if kw in self._trigger_index:
                    reverse_candidates.update(self._trigger_index[kw])
            for cn_kw in re.findall(r'[\u4e00-\u9fff]{2,4}', effect_text):
                if cn_kw in self._trigger_index:
                    reverse_candidates.update(self._trigger_index[cn_kw])
            for key, indices in self._trigger_index.items():
                if len(key) > 1 and key in effect_text:
                    reverse_candidates.update(indices)
            for idx in reverse_candidates:
                pair = self._pairs[idx]
                reverse_trigger = any(kw.lower() in effect_text for kw in pair.trigger)
                reverse_effect = any(kw.lower() in cause_text for kw in pair.effect)
                if reverse_trigger and reverse_effect:
                    return GraphResult(score=0, known=True,
                                      source="reverse", match_info="反向匹配（因果方向可能相反）")
            return GraphResult(score=0, known=False,
                              source="partial", match_info="触发词命中但效果词未命中")

        return GraphResult(score=0, known=False,
                          source="unknown", match_info="图谱中无匹配")

    # ═══ 学习 ═══

    def learn_from_chain(self, cause_summary: str, effect_summary: str,
                         cause_tags: List[str], effect_tags: List[str],
                         confidence: float, domain: str = ""):
        """从 LLM 挖掘的因果链中学习新概念对"""
        self._ensure_loaded()
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
        for pair in self._pairs:
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
        self._pairs.append(new_pair)
        self._rebuild_index()
        self.save_learned()

    # ═══ 统计 ═══

    def stats(self) -> Dict:
        self._ensure_loaded()
        builtin = sum(1 for p in self._pairs if p.source == "builtin")
        learned = sum(1 for p in self._pairs if p.source == "learned")
        return {
            "total_pairs": len(self._pairs),
            "builtin": builtin,
            "learned": learned,
        }


# ═══ 全局实例 ═══
causal_graph = CausalGraph()
