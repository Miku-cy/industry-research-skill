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
    "金融市场": LagProfile(
        domain="金融市场",
        typical_min_days=1,
        typical_max_days=180,
        peak_days=7,
        decay_rate=2.0,
        confidence=0.8,
    ),
    "宏观经济": LagProfile(
        domain="宏观经济",
        typical_min_days=30,
        typical_max_days=730,
        peak_days=90,
        decay_rate=1.5,
        confidence=0.7,
    ),
    "政策效果": LagProfile(
        domain="政策效果",
        typical_min_days=90,
        typical_max_days=3650,
        peak_days=365,
        decay_rate=1.0,
        confidence=0.6,
    ),
    "加密货币": LagProfile(
        domain="加密货币",
        typical_min_days=0,
        typical_max_days=90,
        peak_days=3,
        decay_rate=3.0,
        confidence=0.7,
    ),
    "教育人生": LagProfile(
        domain="教育人生",
        typical_min_days=365,
        typical_max_days=36500,
        peak_days=3650,
        decay_rate=0.3,
        confidence=0.5,
    ),
    "气候环境": LagProfile(
        domain="气候环境",
        typical_min_days=365,
        typical_max_days=36500,
        peak_days=3650,
        decay_rate=0.2,
        confidence=0.5,
    ),
    "公司经营": LagProfile(
        domain="公司经营",
        typical_min_days=30,
        typical_max_days=1095,
        peak_days=180,
        decay_rate=1.2,
        confidence=0.7,
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
        """根据事件标签和摘要自动分类领域"""
        text = " ".join(tags) + " " + summary
        text = text.lower()

        domain_keywords = {
            "金融市场": ["股票", "股市", "指数", "涨跌", "暴跌", "反弹", "牛市", "熊市", "利率", "债券"],
            "宏观经济": ["gdp", "通胀", "cpi", "ppi", "就业", "失业", "经济", "衰退", "复苏"],
            "政策效果": ["政策", "监管", "法律", "法规", "央行", "美联储", "政府", "国务院"],
            "加密货币": ["比特币", "btc", "以太坊", "eth", "加密", "区块链", "defi", "nft", "交易所"],
            "教育人生": ["高考", "大学", "教育", "毕业", "就业", "职业", "人生", "成长"],
            "气候环境": ["气候", "温度", "碳排放", "污染", "环境", "生态", "海平面"],
            "公司经营": ["营收", "利润", "财报", "上市", "融资", "并购", "裁员", "产品"],
        }

        scores = {}
        for domain, keywords in domain_keywords.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[domain] = score

        if scores:
            return max(scores, key=scores.get)
        return "默认"

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
