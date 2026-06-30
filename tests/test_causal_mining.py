"""causal_mining.py 单元测试

测试范围：
- _tfidf_score: TF-IDF 关键词重叠评分
- _extract_json: 从 LLM 输出提取 JSON
- _parse_batch_result: 解析 LLM 批量结果
- _build_batch_prompt: prompt 构建
- mine: 四层漏斗过滤（mock LLM）
- predict / predict_with_evidence: 预测
- mine_and_merge: 网络合并
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.timeline import TimelineEvent, TimelineBase
from src.core.analyzer import CausalChain, CausalNetwork
from src.core.causal_mining import CausalMiningEngine


# ─── fixtures ───

def _event(summary, days_offset=0, tags=None, source="test"):
    return TimelineEvent(
        timestamp=datetime(2024, 1, 1) + timedelta(days=days_offset),
        summary=summary,
        tags=tags or [],
        source=source,
    )


@pytest.fixture
def engine():
    """无 API 的引擎实例"""
    return CausalMiningEngine(api_url="", api_key="", api_model="test")


@pytest.fixture
def engine_with_mock_api():
    """带 mock API 的引擎"""
    return CausalMiningEngine(
        api_url="http://localhost:8787/v1",
        api_key="test-key",
        api_model="test",
    )


# ─── _tfidf_score ───

class TestTfidfScore:
    def test_identical_text(self):
        score = CausalMiningEngine._tfidf_score("美联储加息", "美联储加息")
        assert score == 1.0

    def test_no_overlap(self):
        score = CausalMiningEngine._tfidf_score("苹果发布新手机", "原油价格暴涨")
        assert score == 0.0

    def test_partial_overlap(self):
        score = CausalMiningEngine._tfidf_score(
            "美联储加息25基点", "美联储缩表加速"
        )
        assert 0 < score < 1.0

    def test_with_tags(self):
        score = CausalMiningEngine._tfidf_score(
            "加息", "缩表", tags=["美联储", "货币政策"]
        )
        assert score > 0  # tags 提供共同词

    def test_empty_input(self):
        score = CausalMiningEngine._tfidf_score("", "")
        assert score == 0.0

    def test_english_overlap(self):
        score = CausalMiningEngine._tfidf_score(
            "Fed rate hike", "Fed balance sheet"
        )
        assert 0 < score < 1.0  # "fed" 重叠

    def test_mixed_language(self):
        score = CausalMiningEngine._tfidf_score(
            "Fed加息", "Fed降息"
        )
        assert score > 0  # "fed" + "加" "降" 部分重叠


# ─── _extract_json ───

class TestExtractJson:
    def test_clean_json_array(self):
        text = '[{"idx": 1, "confidence": 0.8}]'
        result = CausalMiningEngine._extract_json(text)
        assert result == [{"idx": 1, "confidence": 0.8}]

    def test_json_with_surrounding_text(self):
        text = '分析结果如下：\n[{"idx": 1, "confidence": 0.5}]。以上是我的分析。'
        result = CausalMiningEngine._extract_json(text)
        assert len(result) == 1
        assert result[0]["confidence"] == 0.5

    def test_json_in_code_block(self):
        text = '```json\n[{"idx": 1}]\n```'
        result = CausalMiningEngine._extract_json(text)
        assert result == [{"idx": 1}]

    def test_empty_array(self):
        text = '没有发现因果关系 []'
        result = CausalMiningEngine._extract_json(text)
        assert result == []

    def test_invalid_json(self):
        text = '[{"idx": 1, broken]'
        result = CausalMiningEngine._extract_json(text)
        assert result == []

    def test_no_json(self):
        text = '这是一段纯文本，没有JSON'
        result = CausalMiningEngine._extract_json(text)
        assert result == []

    def test_multiple_arrays(self):
        text = '前置 [[1]] 后 [{"idx": 2}]'
        result = CausalMiningEngine._extract_json(text)
        # 应该匹配第一个合法的 JSON 数组
        assert isinstance(result, list)


# ─── _parse_batch_result ───

class TestParseBatchResult:
    def _make_pairs(self, n=2):
        pairs = []
        for i in range(n):
            cause = _event(f"因{i}", days_offset=i)
            effect = _event(f"果{i}", days_offset=i + 1)
            pairs.append((cause, effect))
        return pairs

    def test_valid_result(self, engine):
        pairs = self._make_pairs(2)
        result = [
            {"idx": 1, "confidence": 0.8, "reason": "原因1→结果1", "type": "direct", "mechanism": "A→B"},
            {"idx": 2, "confidence": 0.6, "reason": "原因2→结果2", "type": "indirect", "mechanism": "X→Y"},
        ]
        chains, cases = engine._parse_batch_result(result, pairs)
        assert len(chains) == 2
        assert chains[0].confidence == 0.8
        assert chains[1].confidence == 0.6
        assert "机制:A→B" in chains[0].description

    def test_none_type_filtered(self, engine):
        pairs = self._make_pairs(2)
        result = [
            {"idx": 1, "confidence": 0.8, "type": "direct"},
            {"idx": 2, "confidence": 0.5, "type": "none"},
        ]
        chains, _ = engine._parse_batch_result(result, pairs)
        assert len(chains) == 1

    def test_low_confidence_filtered(self, engine):
        pairs = self._make_pairs(1)
        result = [{"idx": 1, "confidence": 0.05, "type": "direct"}]
        chains, _ = engine._parse_batch_result(result, pairs)
        assert len(chains) == 0

    def test_invalid_index_skipped(self, engine):
        pairs = self._make_pairs(1)
        result = [{"idx": 99, "confidence": 0.9, "type": "direct"}]
        chains, _ = engine._parse_batch_result(result, pairs)
        assert len(chains) == 0

    def test_similar_cases_collected(self, engine):
        pairs = self._make_pairs(1)
        result = [{
            "idx": 1,
            "confidence": 0.8,
            "type": "direct",
            "similar_cases": [{"event": "历史案例", "gap_days": 7, "confidence": 0.7}],
        }]
        chains, cases = engine._parse_batch_result(result, pairs)
        assert len(chains) == 1
        key = f"{pairs[0][0].id}->{pairs[0][1].id}"
        assert key in cases
        assert cases[key][0]["event"] == "历史案例"

    def test_empty_result(self, engine):
        chains, cases = engine._parse_batch_result([], [])
        assert chains == []
        assert cases == {}

    def test_non_list_result(self, engine):
        chains, cases = engine._parse_batch_result("not a list", [])
        assert chains == []


# ─── _build_batch_prompt ───

class TestBuildBatchPrompt:
    def test_contains_event_info(self, engine):
        cause = _event("美联储加息", days_offset=0, tags=["加息"])
        effect = _event("加密暴跌", days_offset=5, tags=["加密"])
        prompt = engine._build_batch_prompt([(cause, effect)])
        assert "美联储加息" in prompt
        assert "加密暴跌" in prompt
        assert "加息" in prompt

    def test_multiple_pairs(self, engine):
        pairs = [
            (_event("A", 0), _event("B", 1)),
            (_event("C", 2), _event("D", 3)),
        ]
        prompt = engine._build_batch_prompt(pairs)
        assert "对 1" in prompt
        assert "对 2" in prompt


# ─── mine: 四层漏斗 ───

class TestMineFunnel:
    def test_layer1_time_order(self, engine):
        """Layer 1: 因必须在果之前"""
        e1 = _event("事件A", days_offset=5)
        e2 = _event("事件B", days_offset=1)
        # e1 在 e2 之后，不应配对
        with patch.object(engine, '_analyze_batch', return_value=({}, {})):
            network = engine.mine([e1, e2])
        assert network.chain_count == 0

    def test_layer2_time_window(self, engine):
        """Layer 2: 超出领域最大传导时间 → 淘汰"""
        e1 = _event("事件A", days_offset=0, tags=["金融市场"])
        e2 = _event("事件B", days_offset=500, tags=["金融市场"])
        # 500天超出金融市场最大传导时间
        with patch.object(engine, '_analyze_batch', return_value=({}, {})):
            network = engine.mine([e1, e2])
        assert network.chain_count == 0

    def test_fast_lane_graph_match(self, engine):
        """Layer 3: 图谱认识 → 快车道"""
        e1 = _event("美联储加息", days_offset=0, tags=["加息"])
        e2 = _event("加密市场下跌", days_offset=5, tags=["加密"])

        # mock graph to return known match
        mock_result = MagicMock()
        mock_result.known = True
        mock_result.score = 0.8
        mock_result.match_info = "test"
        mock_result.source = "builtin"

        with patch.object(engine.graph, 'score', return_value=mock_result):
            with patch.object(engine, '_analyze_batch', return_value=([], {})):
                with patch.object(engine.lag_model, 'get_decay', return_value=1.0):
                    with patch.object(engine.lag_model, 'predict_lag', return_value={
                        "domain": "test", "peak_days": 5,
                        "ci_90": [1, 10], "ci_50": [3, 7],
                        "prob_within": {"7天": 0.5, "30天": 0.8},
                        "method": "prior",
                    }):
                        with patch.object(engine.graph, 'learn_from_chain'):
                            network = engine.mine([e1, e2])

        assert network.chain_count >= 1

    def test_slow_lane_unknown(self, engine):
        """Layer 3: 图谱不认识 → 不进网络（除非 LLM 补充）"""
        e1 = _event("未知事件A", days_offset=0)
        e2 = _event("未知事件B", days_offset=5)

        mock_result = MagicMock()
        mock_result.known = False
        mock_result.source = "unknown"
        mock_result.score = 0

        with patch.object(engine.graph, 'score', return_value=mock_result):
            with patch.object(engine, '_analyze_batch', return_value=([], {})):
                network = engine.mine([e1, e2])

        assert network.chain_count == 0

    def test_reverse_filtered(self, engine):
        """Layer 3: 图谱反向匹配 → 淘汰"""
        e1 = _event("事件A", days_offset=0)
        e2 = _event("事件B", days_offset=5)

        mock_result = MagicMock()
        mock_result.known = True
        mock_result.source = "reverse"
        mock_result.score = 0

        with patch.object(engine.graph, 'score', return_value=mock_result):
            with patch.object(engine, '_analyze_batch', return_value=([], {})):
                network = engine.mine([e1, e2])

        assert network.chain_count == 0

    def test_min_confidence_filter(self, engine):
        """低于 min_confidence 的链被过滤"""
        e1 = _event("事件A", days_offset=0)
        e2 = _event("事件B", days_offset=5)

        # graph 返回低置信度
        mock_result = MagicMock()
        mock_result.known = True
        mock_result.score = 0.1
        mock_result.match_info = "weak"
        mock_result.source = "builtin"

        with patch.object(engine.graph, 'score', return_value=mock_result):
            with patch.object(engine, '_analyze_batch', return_value=([], {})):
                network = engine.mine([e1, e2], min_confidence=0.5)

        assert network.chain_count == 0


# ─── predict ───

class TestPredict:
    def test_predict_basic(self, engine):
        result = engine.predict("美联储加息", tags=["加息"])
        assert "domain" in result
        assert "peak_days" in result
        assert "ci_90" in result
        assert "prob_within" in result

    def test_predict_with_evidence(self, engine):
        cases = [{"gap_days": 7, "confidence": 0.8}]
        result = engine.predict_with_evidence("加息", tags=["加息"], cases=cases)
        assert "domain" in result
        assert "peak_days" in result


# ─── mine_and_merge ───

class TestMineAndMerge:
    def test_merge_empty_existing(self, engine):
        """无现有网络时返回挖掘结果"""
        tb = TimelineBase()
        tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="A")
        tb.add_event(timestamp=datetime(2024, 1, 2), data={}, summary="B")

        with patch.object(engine, 'mine', return_value=CausalNetwork()):
            result = engine.mine_and_merge(tb)
        assert isinstance(result, CausalNetwork)

    def test_merge_preserves_existing(self, engine):
        """合并时保留已有链"""
        tb = TimelineBase()
        tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="A")
        tb.add_event(timestamp=datetime(2024, 1, 2), data={}, summary="B")

        # 现有网络有一条链
        existing = CausalNetwork()
        e1 = _event("X", 0)
        e2 = _event("Y", 1)
        existing.add_chain(CausalChain(
            cause_event=e1, effect_event=e2,
            time_gap=timedelta(days=1), confidence=0.9, description="existing"
        ))

        # 挖掘发现新链
        mined = CausalNetwork()
        e3 = _event("A", 0)
        e4 = _event("B", 1)
        mined.add_chain(CausalChain(
            cause_event=e3, effect_event=e4,
            time_gap=timedelta(days=1), confidence=0.7, description="new"
        ))

        with patch.object(engine, 'mine', return_value=mined):
            result = engine.mine_and_merge(tb, existing_network=existing)

        assert result.chain_count == 2


# ─── _load_config ───

class TestLoadConfig:
    def test_no_config(self):
        config = CausalMiningEngine._load_config("")
        assert config == {}

    def test_nonexistent_file(self):
        config = CausalMiningEngine._load_config("/nonexistent/path.yaml")
        assert config == {}

    def test_valid_yaml(self):
        content = "semantic:\n  api:\n    url: http://test\n    key: abc\n    model: test-model\n"
        path = tempfile.mktemp(suffix=".yaml")
        with open(path, "w") as f:
            f.write(content)
        try:
            config = CausalMiningEngine._load_config(path)
            assert config["api_url"] == "http://test"
            assert config["api_key"] == "abc"
            assert config["api_model"] == "test-model"
        finally:
            os.unlink(path)
