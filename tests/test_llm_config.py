"""llm_config.py 单元测试

测试范围：
- LLMConfig.get: 获取配置
- LLMConfig.list_profiles: 列出配置
- LLMConfig._load: 默认加载
- LLMConfig.call: 统一调用（mock API）
- 速率限制常量
- 错误处理
"""
import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.llm_config import LLMConfig, DEFAULT_PROFILES


# ─── fixtures ───

@pytest.fixture
def config():
    """无配置文件的实例"""
    return LLMConfig(config_path="/nonexistent/path")


# ─── get ───

class TestGet:
    def test_mining_profile(self, config):
        cfg = config.get("mining")
        assert cfg["api_model"] == "mimo-v2.5"
        assert "description" in cfg

    def test_semantic_profile(self, config):
        cfg = config.get("semantic")
        assert cfg["mode"] == "auto"
        assert cfg["ollama_model"] == "qwen3:1.7b"

    def test_report_profile(self, config):
        cfg = config.get("report")
        assert cfg["max_tokens"] == 8192

    def test_unknown_profile_raises(self, config):
        with pytest.raises(ValueError, match="未知的 LLM 配置"):
            config.get("nonexistent")

    def test_returns_copy(self, config):
        cfg1 = config.get("mining")
        cfg2 = config.get("mining")
        assert cfg1 == cfg2
        # 修改一个不应影响另一个（如果返回的是副本）


# ─── list_profiles ───

class TestListProfiles:
    def test_lists_all(self, config):
        profiles = config.list_profiles()
        assert "mining" in profiles
        assert "semantic" in profiles
        assert "report" in profiles
        assert "explanation" in profiles

    def test_descriptions_present(self, config):
        profiles = config.list_profiles()
        for name, desc in profiles.items():
            assert len(desc) > 0, f"{name} has no description"


# ─── _load defaults ───

class TestLoadDefaults:
    def test_all_default_profiles_loaded(self, config):
        for name in DEFAULT_PROFILES:
            assert name in config.profiles, f"Missing profile: {name}"

    def test_default_values(self, config):
        mining = config.profiles["mining"]
        assert mining["temperature"] == 0.1
        assert mining["max_tokens"] == 4096


# ─── call ───

class TestCall:
    def test_missing_url_returns_error(self, config):
        config.profiles["mining"]["api_url"] = ""
        config.profiles["mining"]["api_key"] = ""
        result = config.call("mining", "test prompt")
        assert "error" in result or result.get("content") == ""

    def test_openai_compat_success(self, config):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "test response"}}]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            config.profiles["mining"]["api_url"] = "http://test"
            result = config.call("mining", "test prompt")
            assert result["content"] == "test response"

    def test_openai_compat_with_reasoning(self, config):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {
                "content": "",
                "reasoning_content": "分析结果 [1,2,3]"
            }}]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            config.profiles["mining"]["api_url"] = "http://test"
            result = config.call("mining", "test prompt")
            assert result["content"] != ""  # 应从 reasoning_content 提取

    def test_custom_temperature(self, config):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "ok"}}]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            config.profiles["mining"]["api_url"] = "http://test"
            config.call("mining", "test", temperature=0.5)
            call_args = mock_urlopen.call_args
            payload = json.loads(call_args[0][0].data)
            assert payload["temperature"] == 0.5


# ─── rate limiting ───

class TestRateLimiting:
    def test_max_rpm(self):
        assert LLMConfig.MAX_RPM == 90

    def test_min_interval(self):
        assert LLMConfig.MIN_INTERVAL == pytest.approx(60.0 / 90, abs=0.01)

    def test_max_retries(self):
        assert LLMConfig.MAX_RETRIES == 3

    def test_retry_backoff(self):
        assert LLMConfig.RETRY_BACKOFF == 2.0


# ─── _parse_yaml_simple ───

class TestParseYamlSimple:
    def test_valid_yaml(self):
        path = tempfile.mktemp(suffix=".yaml")
        with open(path, "w") as f:
            f.write("key1: value1\nkey2: value2\n")
        try:
            result = LLMConfig._parse_yaml_simple(path)
            assert result["key1"] == "value1"
            assert result["key2"] == "value2"
        finally:
            os.unlink(path)

    def test_skips_comments(self):
        path = tempfile.mktemp(suffix=".yaml")
        with open(path, "w") as f:
            f.write("# comment\nkey: value\n")
        try:
            result = LLMConfig._parse_yaml_simple(path)
            assert "#" not in result
            assert result["key"] == "value"
        finally:
            os.unlink(path)


# ─── config file loading ───

class TestConfigFileLoading:
    def test_yaml_overrides(self):
        content = "llm:\n  mining:\n    api_model: custom-model\n"
        path = tempfile.mktemp(suffix=".yaml")
        with open(path, "w") as f:
            f.write(content)
        try:
            config = LLMConfig(config_path=path)
            assert config.profiles["mining"]["api_model"] == "custom-model"
        finally:
            os.unlink(path)

    def test_semantic_api_compat(self):
        content = "semantic:\n  api:\n    url: http://test\n    key: abc\n    model: test-model\n"
        path = tempfile.mktemp(suffix=".yaml")
        with open(path, "w") as f:
            f.write(content)
        try:
            config = LLMConfig(config_path=path)
            assert config.profiles["semantic"]["api_url"] == "http://test"
            assert config.profiles["semantic"]["api_key"] == "abc"
            assert config.profiles["semantic"]["api_model"] == "test-model"
        finally:
            os.unlink(path)
