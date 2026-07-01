"""因果滞后模型 — 可学习的传导时间参数

每个领域/事件类型的因果传导时间不同：
- 金融市场：天~月
- 宏观经济：月~年
- 政策效果：年~十年
- 教育/人生：十年~一生

本模块：
1. 提供默认滞后配置
2. 支持从历史数据学习
3. 支持持久化和迭代更新
"""
import json
import os
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import statistics


@dataclass
class LagProfile:
    """一个因果关系类型的滞后特征"""
    domain: str                    # 领域名
    typical_min_days: int          # 典型最短传导天数
    typical_max_days: int          # 典型最长传导天数
    peak_days: int                 # 峰值传导天数（最常见）
    decay_rate: float              # 超过峰值后的衰减速度（越大衰减越快）
    confidence: float = 1.0        # 配置置信度（基于样本量）
    sample_count: int = 0          # 观测样本数
    last_updated: str = ""         # 最后更新时间

    def decay_factor(self, gap_days: float) -> float:
        """计算给定时间间隔的衰减因子（0~1）"""
        if gap_days <= 0:
            return 0.0
        if gap_days <= self.peak_days:
            # 峰值之前：线性增长到 1
            return gap_days / self.peak_days
        else:
            # 峰值之后：指数衰减
            excess = gap_days - self.peak_days
            return math.exp(-self.decay_rate * excess / self.peak_days)

    def to_dict(self) -> Dict:
        return {
            "domain": self.domain,
            "typical_min_days": self.typical_min_days,
            "typical_max_days": self.typical_max_days,
            "peak_days": self.peak_days,
            "decay_rate": self.decay_rate,
            "confidence": self.confidence,
            "sample_count": self.sample_count,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "LagProfile":
        return cls(**d)


# ═══ 默认滞后配置（基于领域常识） ═══

DEFAULT_PROFILES = {
    # ── 科技与半导体 ──
    # 芯片/硬件/AI/软件，产品周期 1-6 个月，技术迭代 3-12 个月
    "科技与半导体": LagProfile(
        domain="科技与半导体",
        typical_min_days=7,
        typical_max_days=365,
        peak_days=60,
        decay_rate=1.8,
        confidence=0.7,
    ),
    # ── 金融与资本市场 ──
    # 股票/债券/基金/衍生品，市场反应极快
    "金融与资本市场": LagProfile(
        domain="金融与资本市场",
        typical_min_days=1,
        typical_max_days=180,
        peak_days=7,
        decay_rate=2.0,
        confidence=0.8,
    ),
    # ── 宏观经济 ──
    # GDP/CPI/就业/贸易，数据发布到影响 1-6 个月
    "宏观经济": LagProfile(
        domain="宏观经济",
        typical_min_days=30,
        typical_max_days=730,
        peak_days=90,
        decay_rate=1.5,
        confidence=0.7,
    ),
    # ── 企业与组织 ──
    # 战略/财务/人事/产品，组织决策传导慢
    "企业与组织": LagProfile(
        domain="企业与组织",
        typical_min_days=30,
        typical_max_days=1095,
        peak_days=180,
        decay_rate=1.2,
        confidence=0.7,
    ),
    # ── 政策与治理 ──
    # 法规/监管/国际协议，从出台到落地 3-12 个月
    "政策与治理": LagProfile(
        domain="政策与治理",
        typical_min_days=90,
        typical_max_days=3650,
        peak_days=365,
        decay_rate=1.0,
        confidence=0.6,
    ),
    # ── 大宗商品与能源 ──
    # 供给冲击快(天)，需求变化慢(月)
    "大宗商品与能源": LagProfile(
        domain="大宗商品与能源",
        typical_min_days=1,
        typical_max_days=180,
        peak_days=14,
        decay_rate=2.5,
        confidence=0.7,
    ),
    # ── 加密货币与区块链 ──
    # 7x24 市场，反应极快
    "加密货币与区块链": LagProfile(
        domain="加密货币与区块链",
        typical_min_days=0,
        typical_max_days=90,
        peak_days=3,
        decay_rate=3.0,
        confidence=0.7,
    ),
    # ── 游戏与数字娱乐 ──
    # 版号到上线 3-12 个月，爆款到市场反应 1-3 个月
    "游戏与数字娱乐": LagProfile(
        domain="游戏与数字娱乐",
        typical_min_days=30,
        typical_max_days=365,
        peak_days=90,
        decay_rate=1.5,
        confidence=0.7,
    ),
    # ── 社会与文化 ──
    # 舆论/人口/教育/公共卫生，社会变化慢
    "社会与文化": LagProfile(
        domain="社会与文化",
        typical_min_days=30,
        typical_max_days=3650,
        peak_days=365,
        decay_rate=0.8,
        confidence=0.5,
    ),
    # ── 国际关系与地缘 ──
    # 冲突/制裁/贸易摩擦，传导时间跨度大
    "国际关系与地缘": LagProfile(
        domain="国际关系与地缘",
        typical_min_days=1,
        typical_max_days=1825,
        peak_days=30,
        decay_rate=1.5,
        confidence=0.6,
    ),
    # ── 环境与气候 ──
    # 生态/碳排放/极端天气，长期影响
    "环境与气候": LagProfile(
        domain="环境与气候",
        typical_min_days=365,
        typical_max_days=36500,
        peak_days=3650,
        decay_rate=0.2,
        confidence=0.5,
    ),
    # ── 医疗与健康 ──
    # 疫情/药物/医疗技术，快慢差异大
    "医疗与健康": LagProfile(
        domain="医疗与健康",
        typical_min_days=1,
        typical_max_days=3650,
        peak_days=90,
        decay_rate=1.0,
        confidence=0.5,
    ),
    "默认": LagProfile(
        domain="默认",
        typical_min_days=1,
        typical_max_days=3650,
        peak_days=90,
        decay_rate=1.0,
        confidence=0.5,
    ),
}


class CausalLagModel:
    """因果滞后模型 — 可学习、可迭代、可持久化"""

    def __init__(self, config_path: str = ""):
        self.profiles: Dict[str, LagProfile] = {}
        self.observations: List[Dict] = []  # 原始观测数据
        self.config_path = config_path or self._default_path()

        # 加载已有配置
        if os.path.exists(self.config_path):
            self.load()
        else:
            self._load_defaults()

    def _default_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "..", "data", "causal_lag_model.json")

    def _load_defaults(self):
        for name, profile in DEFAULT_PROFILES.items():
            self.profiles[name] = profile

    # ═══ 查询 ═══

    def get_decay(self, gap_days: float, domain: str = "默认") -> float:
        """获取给定领域和时间间隔的衰减因子"""
        profile = self.profiles.get(domain) or self.profiles.get("默认")
        return profile.decay_factor(gap_days)

    def get_profile(self, domain: str) -> LagProfile:
        return self.profiles.get(domain) or self.profiles.get("默认")

    def classify_domain(self, tags: List[str], summary: str = "") -> str:
        """根据事件标签和摘要自动分类领域

        优先级：精确关键词 > 组合匹配 > 默认
        """
        text = " ".join(tags) + " " + summary
        text = text.lower()

        # 领域关键词表
        # 通用因果分析底座，覆盖 12 个知识领域
        domain_keywords = {
            # ── 科技与半导体 ──
            "科技与半导体": [
                # 芯片制造
                "半导体", "芯片", "晶圆", "硅片", "光刻", "euv", "duv", "asml",
                "蚀刻", "沉积", "离子注入", "制程", "nm", "3nm", "5nm",
                "封装", "先进封装", "cowos", "hbm", "ddr", "nand", "dram",
                "晶圆代工", "foundry", "产能", "良率", "扩产", "减产",
                "晶体管", "mosfet", "二极管", "led", "传感器", "微处理器",
                # 计算与AI
                "cpu", "gpu", "fpga", "asic", "soc", "mcu", "npu", "tpu",
                "ai", "人工智能", "大模型", "llm", "gpt", "深度学习",
                "机器学习", "神经网络", "transformer", "推理", "训练",
                "aigc", "生成式ai", "智能体", "agent", "自动驾驶", "机器人",
                # 软件与互联网
                "云计算", "saas", "paas", "大数据", "数据库", "操作系统",
                "开源", "github", "编程语言", "框架", "api", "微服务",
                "网络安全", "信息安全", "加密算法", "零信任",
                # 硬件与设备
                "手机", "电脑", "服务器", "数据中心", "5g", "6g", "通信",
                "基站", "光纤", "物联网", "iot", "可穿戴", "ar", "vr",
                # 公司
                "台积电", "tsmc", "三星", "英伟达", "nvidia", "英特尔",
                "amd", "高通", "博通", "asml", "中芯国际", "华为",
                "openai", "anthropic", "google", "meta", "苹果", "微软",
            ],

            # ── 金融与资本市场 ──
            "金融与资本市场": [
                # 市场
                "股票", "股市", "a股", "港股", "美股", "债券", "基金", "etf",
                "期货", "期权", "衍生品", "外汇", "汇率", "利率",
                "牛市", "熊市", "反弹", "暴跌", "暴涨", "震荡",
                "涨停", "跌停", "熔断", "成交量", "换手率", "融资融券",
                # 机构
                "交易所", "券商", "投行", "银行", "保险", "公募", "私募",
                "央行", "美联储", "ecb", "证监会", "银保监",
                # 指标
                "市值", "估值", "市盈率", "市净率", "股息率", "收益率",
                "信用评级", "违约", "系统风险", "流动性",
                # 事件
                "ipo", "上市", "退市", "增发", "回购", "分红", "减持", "并购",
            ],

            # ── 宏观经济 ──
            "宏观经济": [
                # 产出
                "gdp", "国内生产总值", "工业增加值", "固定资产投资",
                "社会消费品零售", "服务业", "制造业",
                # 价格
                "cpi", "ppi", "通胀", "通缩", "物价", "平减指数",
                # 就业
                "就业", "失业", "失业率", "非农", "工资", "收入",
                # 贸易
                "出口", "进口", "贸易顺差", "贸易逆差", "关税", "贸易战",
                "外汇储备", "经常账户",
                # 景气
                "pmi", "景气指数", "信心指数", "消费者信心",
                # 货币
                "m1", "m2", "社融", "信贷", "利率", "准备金率",
                "美元", "人民币", "欧元", "日元", "英镑", "美元指数",
                # 周期
                "库存周期", "基钦周期", "朱格拉周期", "康波周期",
                "房地产周期", "债务周期", "信贷周期",
            ],

            # ── 企业与组织 ──
            "企业与组织": [
                # 战略
                "战略", "转型", "多元化", "并购", "收购", "合并", "分拆",
                "重组", "合资", "合作", "竞争", "市场份额",
                # 运营
                "营收", "利润", "成本", "效率", "供应链", "物流",
                "生产", "制造", "质量", "交付", "库存",
                # 人事
                "裁员", "招聘", "管理层", "ceo", "cto", "组织架构",
                "人才", "培训", "绩效", "薪酬",
                # 创新
                "研发", "专利", "产品发布", "新产品", "技术突破",
                # 资本
                "融资", "投资", "资本", "现金流", "资产负债", "上市",
            ],

            # ── 政策与治理 ──
            "政策与治理": [
                # 国内政策
                "政策", "法规", "法律", "监管", "审批", "许可",
                "国务院", "发改委", "工信部", "商务部", "财政部",
                "五年规划", "产业政策", "财政政策", "货币政策",
                "减税", "退税", "补贴", "基建", "转移支付",
                # 国际政策
                "制裁", "关税", "出口管制", "实体清单", "技术封锁",
                "wto", "rcep", "联合国", "g20", "欧盟",
                # 治理
                "反垄断", "数据安全", "隐私保护", "环保法规",
                "碳中和", "碳交易", "esg", "合规",
            ],

            # ── 大宗商品与能源 ──
            "大宗商品与能源": [
                # 能源
                "原油", "石油", "wti", "布伦特", "天然气", "lng",
                "煤炭", "电力", "核电", "风电", "光伏", "氢能",
                "opec", "减产", "增产", "石油输出国",
                # 金属
                "黄金", "白银", "铂金", "铜", "铝", "锌", "镍", "锡",
                "铁矿石", "锂", "钴", "稀土",
                # 农产品
                "大豆", "玉米", "小麦", "棉花", "棕榈油", "咖啡", "糖",
                # 交易
                "期货", "现货", "库存", "产量", "消费量", "进出口",
            ],

            # ── 加密货币与区块链 ──
            "加密货币与区块链": [
                # 主流币
                "比特币", "btc", "以太坊", "eth", "solana", "sol",
                "bnb", "xrp", "doge", "稳定币", "usdt", "usdc",
                # 技术
                "区块链", "去中心化", "共识机制", "pow", "pos",
                "智能合约", "defi", "nft", "dao", "layer2", "rollup",
                "web3", "元宇宙",
                # 产业
                "交易所", "币安", "coinbase", "矿工", "挖矿", "减半",
                "sec", "加密监管", "虚拟货币", "数字货币", "cbdc",
            ],

            # ── 游戏与数字娱乐 ──
            "游戏与数字娱乐": [
                # 类型
                "游戏", "手游", "端游", "主机游戏",
                "rpg", "fps", "moba", "mmorpg", "slg", "二次元", "开放世界",
                # 平台
                "steam", "epic", "playstation", "xbox", "switch",
                # 公司
                "腾讯游戏", "网易游戏", "米哈游", "完美世界", "任天堂",
                # 产业
                "版号", "出海", "爆款", "流水", "dau", "mau",
                "直播", "短视频", "流媒体", "netflix", "b站",
                "影视", "音乐", "动漫", "ip", "版权",
            ],

            # ── 社会与文化 ──
            "社会与文化": [
                # 人口
                "人口", "出生率", "老龄化", "城镇化", "迁移",
                # 教育
                "教育", "高考", "大学", "就业", "职业", "技能",
                # 公共卫生
                "疫情", "传染病", "疫苗", "医疗", "医院", "药物",
                "医保", "公共卫生", "心理健康",
                # 舆论
                "舆论", "社交媒体", "热搜", "舆情", "品牌", "口碑",
                "消费习惯", "生活方式", "文化趋势",
            ],

            # ── 国际关系与地缘 ──
            "国际关系与地缘": [
                # 地缘
                "冲突", "战争", "军事", "军演", "导弹", "核武器",
                "领土", "领海", "南海", "台海", "中东", "俄乌",
                # 外交
                "峰会", "外交", "建交", "断交", "制裁", "谈判",
                "联合国", "安理会", "北约", "欧盟", "东盟",
                # 经贸关系
                "贸易战", "技术封锁", "脱钩", "供应链安全",
                "一带一路", "印太战略", "芯片联盟",
            ],

            # ── 环境与气候 ──
            "环境与气候": [
                "气候", "温度", "碳排放", "co2", "温室效应",
                "极端天气", "洪水", "干旱", "台风", "地震",
                "海平面", "冰川", "生态", "生物多样性",
                "碳中和", "碳交易", "碳税", "esg", "绿色金融",
                "新能源", "电动车", "充电桩", "储能", "锂电池",
                "光伏", "风电", "氢能", "核电",
            ],

            # ── 医疗与健康 ──
            "医疗与健康": [
                "疾病", "诊断", "治疗", "手术", "药物", "疫苗",
                "临床试验", "fda", "药监局", "医保", "医疗器械",
                "基因", "基因编辑", "crispr", "细胞治疗", "免疫治疗",
                "ai诊断", "远程医疗", "数字健康", "可穿戴设备",
                "癌症", "心血管", "糖尿病", "传染病", "罕见病",
                "辉瑞", "默沙东", "罗氏", "药明康德", "恒瑞",
            ],
        }

        # 评分：每个命中关键词 +1，标签命中权重 ×2
        tag_text = " ".join(tags).lower()
        scores = {}
        for domain, keywords in domain_keywords.items():
            score = 0
            for kw in keywords:
                if kw in text:
                    score += 1
                if kw in tag_text:
                    score += 1  # 标签额外加分（更可靠）
            if score > 0:
                scores[domain] = score

        if not scores:
            return "默认"

        # 选最高分；平分时优先更具体的领域（列表靠前的）
        return max(scores, key=scores.get)

    # ═══ 学习 ═══

    def observe(self, cause_tags: List[str], cause_summary: str,
                effect_tags: List[str], effect_summary: str,
                gap_days: float, causal_confidence: float):
        """记录一次因果观测，用于后续学习

        Args:
            cause_tags: 因事件标签
            cause_summary: 因事件摘要
            effect_tags: 果事件标签
            effect_summary: 果事件摘要
            gap_days: 时间间隔（天）
            causal_confidence: 因果置信度（0~1）
        """
        domain = self.classify_domain(cause_tags + effect_tags,
                                       cause_summary + " " + effect_summary)
        self.observations.append({
            "domain": domain,
            "gap_days": gap_days,
            "confidence": causal_confidence,
            "timestamp": datetime.now().isoformat(),
            "cause_summary": cause_summary[:50],
            "effect_summary": effect_summary[:50],
        })

    def learn(self):
        """从观测数据更新滞后参数

        算法：
        1. 按领域分组
        2. 计算每个领域的滞后分布（加权中位数、分位数）
        3. 更新 profile 参数
        4. 增加样本计数和置信度
        """
        from collections import defaultdict

        by_domain = defaultdict(list)
        for obs in self.observations:
            by_domain[obs["domain"]].append(obs)

        for domain, obs_list in by_domain.items():
            if len(obs_list) < 3:
                continue  # 样本太少不更新

            # 获取或创建 profile
            profile = self.profiles.get(domain)
            if not profile:
                profile = DEFAULT_PROFILES["默认"]
                profile.domain = domain

            # 加权统计
            gaps = [o["gap_days"] for o in obs_list]
            confs = [o["confidence"] for o in obs_list]

            # 加权中位数作为 peak
            weighted_gaps = []
            for g, c in zip(gaps, confs):
                weighted_gaps.extend([g] * max(1, int(c * 10)))
            weighted_gaps.sort()
            peak = weighted_gaps[len(weighted_gaps) // 2]

            # 分位数作为 min/max
            sorted_gaps = sorted(gaps)
            q10 = sorted_gaps[max(0, int(len(sorted_gaps) * 0.1))]
            q90 = sorted_gaps[min(len(sorted_gaps) - 1, int(len(sorted_gaps) * 0.9))]

            # 更新
            profile.peak_days = max(1, int(peak))
            profile.typical_min_days = max(0, int(q10))
            profile.typical_max_days = max(profile.peak_days * 2, int(q90))
            profile.sample_count += len(obs_list)
            profile.confidence = min(1.0, 0.5 + len(obs_list) * 0.02)
            profile.last_updated = datetime.now().isoformat()

            # 衰减率：基于分布宽度
            spread = max(1, profile.typical_max_days - profile.typical_min_days)
            profile.decay_rate = max(0.1, min(5.0, profile.peak_days / spread * 3))

            self.profiles[domain] = profile

        # 清空已处理的观测
        self.observations = []

    # ═══ 持久化 ═══

    def save(self):
        """保存模型到文件"""
        data = {
            "version": 1,
            "saved_at": datetime.now().isoformat(),
            "profiles": {name: p.to_dict() for name, p in self.profiles.items()},
            "pending_observations": self.observations,
        }
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self):
        """从文件加载模型"""
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for name, pd in data.get("profiles", {}).items():
            self.profiles[name] = LagProfile.from_dict(pd)

        self.observations = data.get("pending_observations", [])

    # ═══ 贝叶斯滞后推断 ═══

    def predict_lag(self, cause_tags: List[str], cause_summary: str,
                    effect_tags: List[str] = None, effect_summary: str = "") -> Dict:
        """给定因事件，预测果事件发生的概率分布

        Returns:
            {
                "domain": 领域,
                "peak_days": 最可能的传导天数,
                "mean_days": 期望传导天数,
                "ci_90": [下界, 上界], 90%置信区间,
                "ci_50": [下界, 上界], 50%置信区间,
                "prob_within": {"7天": 0.x, "30天": 0.x, ...}, 各时间段内发生的概率,
                "confidence": 预测置信度,
            }
        """
        domain = self.classify_domain(cause_tags, cause_summary)
        profile = self.get_profile(domain)

        # 用 gamma 分布建模滞后
        # 参数：shape = (peak/decay_rate)^2, scale = decay_rate^2/peak
        # 这样 peak = shape * scale
        shape = max(1.0, (profile.peak_days / max(profile.decay_rate, 0.1)) ** 0.5)
        scale = max(1.0, profile.peak_days / shape)

        # 计算分位数
        import math

        def gamma_cdf(x, shape, scale):
            """简化的 gamma CDF（正则化不完全 gamma 函数近似）"""
            if x <= 0:
                return 0.0
            # 使用正态近似
            mu = shape * scale
            sigma = math.sqrt(shape) * scale
            z = (x - mu) / sigma if sigma > 0 else 0
            return 0.5 * (1 + math.erf(z / math.sqrt(2)))

        mu = shape * scale
        sigma = math.sqrt(shape) * scale

        # 90% 和 50% 置信区间
        ci_90_lo = max(0, mu - 1.645 * sigma)
        ci_90_hi = mu + 1.645 * sigma
        ci_50_lo = max(0, mu - 0.674 * sigma)
        ci_50_hi = mu + 0.674 * sigma

        # 各时间段内发生的累积概率
        prob_within = {}
        for days_label, days_val in [("1天", 1), ("7天", 7), ("30天", 30),
                                      ("90天", 90), ("180天", 180),
                                      ("1年", 365), ("3年", 1095), ("5年", 1825),
                                      ("10年", 3650)]:
            prob_within[days_label] = round(gamma_cdf(days_val, shape, scale), 3)

        return {
            "domain": domain,
            "peak_days": int(profile.peak_days),
            "mean_days": round(mu, 1),
            "ci_90": [round(ci_90_lo), round(ci_90_hi)],
            "ci_50": [round(ci_50_lo), round(ci_50_hi)],
            "prob_within": prob_within,
            "confidence": profile.confidence,
            "sample_count": profile.sample_count,
        }

    def predict_with_evidence(self, cause_tags: List[str], cause_summary: str,
                              similar_cases: List[Dict] = None) -> Dict:
        """结合历史案例的贝叶斯推断

        similar_cases: [{"gap_days": 30, "confidence": 0.8}, ...]
        如果提供相似案例，用贝叶斯更新先验分布
        """
        # 先验：基于领域 profile
        prior = self.predict_lag(cause_tags, cause_summary)

        if not similar_cases or len(similar_cases) < 2:
            return prior

        # 贝叶斯更新：用观测数据更新先验
        observed_gaps = [c["gap_days"] for c in similar_cases]
        observed_confs = [c.get("confidence", 0.5) for c in similar_cases]

        # 加权均值和方差
        total_weight = sum(observed_confs)
        if total_weight == 0:
            return prior

        weighted_mean = sum(g * c for g, c in zip(observed_gaps, observed_confs)) / total_weight
        weighted_var = sum(c * (g - weighted_mean) ** 2 for g, c in zip(observed_gaps, observed_confs)) / total_weight

        # 后验：先验和观测的加权混合
        prior_weight = prior["confidence"] * prior["sample_count"]
        data_weight = total_weight
        total = prior_weight + data_weight

        if total == 0:
            return prior

        posterior_mean = (prior_weight * prior["mean_days"] + data_weight * weighted_mean) / total
        posterior_var = (prior_weight * prior["mean_days"] ** 2 + data_weight * (weighted_var + weighted_mean ** 2)) / total - posterior_mean ** 2
        posterior_std = max(1, math.sqrt(abs(posterior_var)))

        # 更新置信区间
        ci_90_lo = max(0, posterior_mean - 1.645 * posterior_std)
        ci_90_hi = posterior_mean + 1.645 * posterior_std
        ci_50_lo = max(0, posterior_mean - 0.674 * posterior_std)
        ci_50_hi = posterior_mean + 0.674 * posterior_std

        # 更新累积概率
        prob_within = {}
        for days_label, days_val in [("1天", 1), ("7天", 7), ("30天", 30),
                                      ("90天", 90), ("180天", 180),
                                      ("1年", 365), ("3年", 1095), ("5年", 1825),
                                      ("10年", 3650)]:
            z = (days_val - posterior_mean) / posterior_std if posterior_std > 0 else 0
            prob_within[days_label] = round(0.5 * (1 + math.erf(z / math.sqrt(2))), 3)

        return {"domain": prior["domain"], "peak_days": int(posterior_mean), "mean_days": round(posterior_mean, 1), "ci_90": [round(ci_90_lo), round(ci_90_hi)], "ci_50": [round(ci_50_lo), round(ci_50_hi)], "prob_within": prob_within, "confidence": min(1.0, prior["confidence"] + len(similar_cases) * 0.05), "sample_count": prior["sample_count"] + len(similar_cases), "method": "bayesian_with_evidence"}

        return {"domain": prior["domain"], "peak_days": int(posterior_mean), "mean_days": round(posterior_mean, 1), "ci_90": [round(ci_90_lo), round(ci_90_hi)], "ci_50": [round(ci_50_lo), round(ci_50_hi)], "prob_within": prob_within, "confidence": min(1.0, prior["confidence"] + len(similar_cases) * 0.05), "sample_count": prior["sample_count"] + len(similar_cases), "method": "bayesian_with_evidence"}

    # ═══ 报告 ═══

    def summary(self) -> str:
        """输出模型概要"""
        lines = ["因果滞后模型概要："]
        for name, p in sorted(self.profiles.items()):
            lines.append(
                f"  {name}: 峰值{p.peak_days}天, "
                f"范围{p.typical_min_days}-{p.typical_max_days}天, "
                f"衰减率{p.decay_rate:.1f}, "
                f"置信度{p.confidence:.0%}, "
                f"样本{p.sample_count}"
            )
        lines.append(f"待学习观测: {len(self.observations)}条")
        return "\n".join(lines)
