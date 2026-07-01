"""causal_lag.py 单元测试

测试范围：
- LagProfile: decay_factor, to_dict, from_dict
- CausalLagModel: classify_domain, get_decay, get_profile,
  observe, learn, save/load, predict_lag, predict_with_evidence, summary
"""
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.causal_lag import LagProfile, CausalLagModel, DEFAULT_PROFILES


# ─── LagProfile ───

class TestLagProfile:
    def test_decay_factor_before_peak(self):
        p = DEFAULT_PROFILES["金融与资本市场"]  # peak=7
        assert p.decay_factor(0) == 0.0
        assert p.decay_factor(3.5) == pytest.approx(0.5, abs=0.01)
        assert p.decay_factor(7) == pytest.approx(1.0, abs=0.01)

    def test_decay_factor_at_peak(self):
        p = DEFAULT_PROFILES["金融与资本市场"]
        assert p.decay_factor(7) == 1.0

    def test_decay_factor_after_peak(self):
        p = DEFAULT_PROFILES["金融与资本市场"]  # peak=7, decay_rate=2.0
        val = p.decay_factor(14)  # 7天超出峰值
        assert 0 < val < 1.0

    def test_decay_factor_negative(self):
        p = DEFAULT_PROFILES["金融与资本市场"]
        assert p.decay_factor(-1) == 0.0

    def test_decay_factor_zero(self):
        p = DEFAULT_PROFILES["金融与资本市场"]
        assert p.decay_factor(0) == 0.0

    def test_to_dict(self):
        p = DEFAULT_PROFILES["金融与资本市场"]
        d = p.to_dict()
        assert d["domain"] == "金融与资本市场"
        assert d["peak_days"] == 7
        assert "decay_rate" in d

    def test_from_dict(self):
        d = {"domain": "test", "typical_min_days": 1, "typical_max_days": 30,
             "peak_days": 10, "decay_rate": 1.5}
        p = LagProfile.from_dict(d)
        assert p.domain == "test"
        assert p.peak_days == 10

    def test_roundtrip(self):
        p = DEFAULT_PROFILES["加密货币与区块链"]
        d = p.to_dict()
        p2 = LagProfile.from_dict(d)
        assert p2.domain == p.domain
        assert p2.peak_days == p.peak_days
        assert p2.decay_rate == p.decay_rate


# ─── CausalLagModel.classify_domain ───

class TestClassifyDomain:
    def test_financial(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = {}
        assert model.classify_domain(["股票", "暴跌"]) == "金融与资本市场"

    def test_crypto(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = {}
        assert model.classify_domain(["比特币", "加密"]) == "加密货币与区块链"

    def test_macro(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = {}
        assert model.classify_domain(["GDP", "通胀"]) == "宏观经济"

    def test_policy(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = {}
        assert model.classify_domain(["制裁", "关税"]) == "政策与治理"

    def test_company(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = {}
        assert model.classify_domain(["营收", "财报"]) == "企业与组织"

    def test_default_fallback(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = {}
        assert model.classify_domain(["未知标签"]) == "默认"

    def test_summary_used(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = {}
        assert model.classify_domain([], "股市暴跌引发恐慌") == "金融与资本市场"

    def test_multiple_keywords_higher_score(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = {}
        assert model.classify_domain(["比特币", "加密", "交易所"]) == "加密货币与区块链"


# ─── CausalLagModel.get_decay / get_profile ───

class TestGetDecay:
    def test_known_domain(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        decay = model.get_decay(7, "金融与资本市场")
        assert decay == pytest.approx(1.0, abs=0.01)  # peak=7

    def test_unknown_domain_fallback(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        decay = model.get_decay(90, "不存在的领域")
        assert 0 < decay <= 1.0

    def test_get_profile_known(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        p = model.get_profile("金融与资本市场")
        assert p.domain == "金融与资本市场"

    def test_get_profile_unknown(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        p = model.get_profile("不存在")
        assert p.domain == "默认"


# ─── observe / learn ───

class TestObserveAndLearn:
    def test_observe_adds_observation(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        model.observations = []
        model.observe(["股票"], "暴跌", ["加密"], "崩盘", 5, 0.8)
        assert len(model.observations) == 1
        assert model.observations[0]["gap_days"] == 5

    def test_learn_requires_minimum_samples(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        model.observations = [
            {"domain": "金融与资本市场", "gap_days": 5, "confidence": 0.8, "timestamp": "", "cause_summary": "", "effect_summary": ""},
            {"domain": "金融与资本市场", "gap_days": 7, "confidence": 0.7, "timestamp": "", "cause_summary": "", "effect_summary": ""},
        ]
        model.learn()
        # 2条 < 3条阈值，不应更新
        assert model.profiles["金融与资本市场"].peak_days == 7  # 未改变

    def test_learn_updates_profile(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        model.observations = [
            {"domain": "金融与资本市场", "gap_days": i, "confidence": 0.8, "timestamp": "", "cause_summary": "", "effect_summary": ""}
            for i in [3, 5, 7, 10, 14]
        ]
        model.learn()
        p = model.profiles["金融与资本市场"]
        assert p.sample_count == 5
        assert p.peak_days > 0

    def test_learn_clears_observations(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        model.observations = [
            {"domain": "test", "gap_days": i, "confidence": 0.5, "timestamp": "", "cause_summary": "", "effect_summary": ""}
            for i in range(5)
        ]
        model.learn()
        assert len(model.observations) == 0


# ─── save / load ───

class TestPersistence:
    def test_save_and_load(self):
        path = tempfile.mktemp(suffix=".json")
        try:
            model = CausalLagModel(config_path=path)
            model.profiles = dict(DEFAULT_PROFILES)
            model.observations = [{"domain": "test", "gap_days": 5, "confidence": 0.8, "timestamp": "", "cause_summary": "", "effect_summary": ""}]
            model.save()

            model2 = CausalLagModel(config_path=path)
            assert "金融与资本市场" in model2.profiles
            assert len(model2.observations) == 1
            assert model2.profiles["金融与资本市场"].peak_days == 7
        finally:
            os.unlink(path)

    def test_save_creates_dir(self):
        path = tempfile.mkdtemp() + "/sub/dir/model.json"
        try:
            model = CausalLagModel(config_path=path)
            model.profiles = dict(DEFAULT_PROFILES)
            model.save()
            assert os.path.exists(path)
        finally:
            import shutil
            shutil.rmtree(os.path.dirname(os.path.dirname(path)))


# ─── predict_lag ───

class TestPredictLag:
    def test_returns_required_fields(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        result = model.predict_lag(["股票"], "暴跌")
        assert "domain" in result
        assert "peak_days" in result
        assert "mean_days" in result
        assert "ci_90" in result
        assert "ci_50" in result
        assert "prob_within" in result
        assert "confidence" in result

    def test_domain_classification(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        result = model.predict_lag(["比特币"], "加密暴跌")
        assert result["domain"] == "加密货币与区块链"

    def test_ci_90_wider_than_ci_50(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        result = model.predict_lag(["股票"], "暴跌")
        ci_90_range = result["ci_90"][1] - result["ci_90"][0]
        ci_50_range = result["ci_50"][1] - result["ci_50"][0]
        assert ci_90_range > ci_50_range

    def test_prob_within_monotonic(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        result = model.predict_lag(["股票"], "暴跌")
        probs = list(result["prob_within"].values())
        # 概率应单调递增
        for i in range(len(probs) - 1):
            assert probs[i] <= probs[i + 1] + 0.001  # 允许浮点误差

    def test_peak_days_positive(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        result = model.predict_lag(["股票"], "暴跌")
        assert result["peak_days"] > 0


# ─── predict_with_evidence ───

class TestPredictWithEvidence:
    def test_no_evidence_returns_prior(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        result = model.predict_with_evidence(["股票"], "暴跌", None)
        assert "domain" in result
        assert result.get("method") != "bayesian_with_evidence"

    def test_too_few_cases_returns_prior(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        result = model.predict_with_evidence(["股票"], "暴跌", [{"gap_days": 5, "confidence": 0.8}])
        assert result.get("method") != "bayesian_with_evidence"

    def test_with_evidence_updates(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        cases = [
            {"gap_days": 3, "confidence": 0.9},
            {"gap_days": 5, "confidence": 0.8},
            {"gap_days": 7, "confidence": 0.7},
        ]
        result = model.predict_with_evidence(["股票"], "暴跌", cases)
        assert result["method"] == "bayesian_with_evidence"
        assert result["sample_count"] > 0

    def test_evidence_shifts_peak(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        prior = model.predict_lag(["股票"], "暴跌")
        # 给出远超先验峰值的案例
        cases = [{"gap_days": 60, "confidence": 0.9}] * 5
        posterior = model.predict_with_evidence(["股票"], "暴跌", cases)
        # 后验峰值应比先验大
        assert posterior["peak_days"] > prior["peak_days"]


# ─── summary ───

class TestSummary:
    def test_summary_contains_domains(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        model.observations = []
        s = model.summary()
        assert "金融与资本市场" in s
        assert "加密货币与区块链" in s
        assert "待学习观测" in s

    def test_summary_format(self):
        model = CausalLagModel.__new__(CausalLagModel)
        model.profiles = dict(DEFAULT_PROFILES)
        model.observations = []
        s = model.summary()
        assert "峰值" in s
        assert "天" in s
