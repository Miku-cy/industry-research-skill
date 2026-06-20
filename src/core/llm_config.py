"""LLM 统一配置中心

所有模块从这里获取 API 配置，不再各自读文件。

用法：
    from .llm_config import llm_config

    # 获取因果挖掘的 LLM 配置
    cfg = llm_config.get("mining")
    # → {"api_url": "...", "api_key": "...", "api_model": "mimo-v2.5"}

    # 获取语义分类的 LLM 配置
    cfg = llm_config.get("semantic")
    # → {"mode": "ollama", "ollama_url": "...", "ollama_model": "qwen3:1.7b", ...}

    # 调用 API（统一入口）
    result = llm_config.call("mining", prompt, temperature=0.1)
"""
import json
import os
import urllib.request
from typing import Any, Dict, Optional


# ═══ 默认配置 ═══

DEFAULT_PROFILES = {
    # ── 因果挖掘：分析事件对的因果关系 ──
    # 需要强推理能力，识别传导机制，提供历史案例
    "mining": {
        "api_url": "",
        "api_key": "",
        "api_model": "mimo-v2.5",
        "temperature": 0.1,
        "max_tokens": 4096,
        "description": "因果挖掘：分析事件对因果关系、传导机制、历史案例",
    },

    # ── 语义分类：事件的 PEST/SWOT 分类 ──
    # 可以用轻量模型，关键词匹配已覆盖大部分场景
    "semantic": {
        "mode": "auto",          # heuristic / ollama / api / auto
        "api_url": "",
        "api_key": "",
        "api_model": "gpt-4o-mini",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "qwen3:1.7b",
        "temperature": 0.1,
        "max_tokens": 512,
        "description": "语义分类：事件 PEST/SWOT 分类、领域识别",
    },

    # ── 报告生成：综合分析报告 ──
    # 需要好的文字组织能力
    "report": {
        "api_url": "",
        "api_key": "",
        "api_model": "mimo-v2.5",
        "temperature": 0.3,
        "max_tokens": 8192,
        "description": "报告生成：综合分析报告、投资建议",
    },

    # ── 因果解释：深度解读因果链 ──
    # 需要最强推理能力
    "explanation": {
        "api_url": "",
        "api_key": "",
        "api_model": "mimo-v2.5",
        "temperature": 0.2,
        "max_tokens": 4096,
        "description": "因果解释：深度解读因果传导逻辑、反事实分析",
    },
}


class LLMConfig:
    """LLM 统一配置中心"""

    def __init__(self, config_path: str = ""):
        self.profiles: Dict[str, Dict] = {}
        self._config_path = config_path or self._find_config()
        self._load()

    def _find_config(self) -> str:
        for p in [
            "chronovisor.yaml",
            "../chronovisor.yaml",
            os.path.expanduser("~/.chronovisor/config.yaml"),
        ]:
            if os.path.exists(p):
                return p
        return ""

    def _load(self):
        """加载配置：先加载默认值，再用配置文件覆盖"""
        # 1. 加载默认值
        for name, profile in DEFAULT_PROFILES.items():
            self.profiles[name] = dict(profile)

        # 2. 从配置文件覆盖
        if not self._config_path or not os.path.exists(self._config_path):
            return

        try:
            import yaml
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except ImportError:
            data = self._parse_yaml_simple(self._config_path)
        except Exception:
            return

        # 读取 llm 配置段
        llm_section = data.get("llm", {})

        for name, overrides in llm_section.items():
            if name in self.profiles and isinstance(overrides, dict):
                for key, value in overrides.items():
                    if value:  # 只覆盖非空值
                        self.profiles[name][key] = value

        # 兼容旧格式：semantic.api 段
        semantic = data.get("semantic", {})
        if semantic:
            api = semantic.get("api", {})
            if api and "semantic" in self.profiles:
                self.profiles["semantic"]["api_url"] = api.get("url", "") or self.profiles["semantic"]["api_url"]
                self.profiles["semantic"]["api_key"] = api.get("key", "") or self.profiles["semantic"]["api_key"]
                self.profiles["semantic"]["api_model"] = api.get("model", "") or self.profiles["semantic"]["api_model"]
            ollama = semantic.get("ollama", {})
            if ollama and "semantic" in self.profiles:
                self.profiles["semantic"]["ollama_url"] = ollama.get("url", "") or self.profiles["semantic"]["ollama_url"]
                self.profiles["semantic"]["ollama_model"] = ollama.get("model", "") or self.profiles["semantic"]["ollama_model"]
            mode = semantic.get("mode", "")
            if mode and "semantic" in self.profiles:
                self.profiles["semantic"]["mode"] = mode

        # 从 openclaw.json 读取通用 API key（回退）
        for name in self.profiles:
            if not self.profiles[name].get("api_key"):
                self.profiles[name]["api_key"] = self._get_openclaw_key()

    def _get_openclaw_key(self) -> str:
        """从 openclaw.json 读取 API key（通用回退）"""
        oc_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if not os.path.exists(oc_path):
            return ""
        try:
            with open(oc_path) as f:
                oc = json.load(f)
            providers = oc.get("models", {}).get("providers", {})
            for name, prov in providers.items():
                if prov.get("apiKey"):
                    return prov["apiKey"]
        except Exception:
            pass
        return ""

    @staticmethod
    def _parse_yaml_simple(path: str) -> Dict:
        config: Dict[str, Any] = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or ":" not in line:
                    continue
                key, _, val = line.partition(":")
                config[key.strip()] = val.strip().strip('"').strip("'")
        return config

    # ═══ 查询接口 ═══

    def get(self, profile_name: str) -> Dict:
        """获取指定功能的 LLM 配置

        Args:
            profile_name: mining / semantic / report / explanation

        Returns:
            配置字典，包含 api_url, api_key, api_model 等
        """
        if profile_name not in self.profiles:
            raise ValueError(
                f"未知的 LLM 配置: {profile_name}，"
                f"可选: {', '.join(self.profiles.keys())}"
            )
        return self.profiles[profile_name]

    def list_profiles(self) -> Dict[str, str]:
        """列出所有配置及其说明"""
        return {
            name: p.get("description", "")
            for name, p in self.profiles.items()
        }

    # ═══ 统一调用接口 ═══

    def call(
        self,
        profile_name: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """统一 LLM 调用入口

        Args:
            profile_name: 配置名（mining/semantic/report/explanation）
            prompt: 提示词
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大 token

        Returns:
            {"content": "...", "reasoning_content": "...(如有)"}
        """
        cfg = self.get(profile_name)

        # 语义分类可能用 ollama
        if profile_name == "semantic" and cfg.get("mode") in ("ollama", "auto"):
            if cfg.get("mode") == "ollama" or self._check_ollama(cfg):
                return self._call_ollama(cfg, prompt)

        return self._call_openai_compat(cfg, prompt, temperature, max_tokens)

    def _call_openai_compat(
        self,
        cfg: Dict,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """调用 OpenAI 兼容 API"""
        base = (cfg.get("api_url") or "").rstrip("/")
        if not base:
            return {"content": "", "error": "未配置 api_url"}
        if not base.endswith("/v1"):
            base += "/v1"

        payload = json.dumps({
            "model": cfg.get("api_model", "mimo-v2.5"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature if temperature is not None else cfg.get("temperature", 0.1),
            "max_tokens": max_tokens or cfg.get("max_tokens", 4096),
        }).encode()

        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.get('api_key', '')}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                msg = data["choices"][0]["message"]
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning_content") or ""
                return {"content": content, "reasoning_content": reasoning}
        except Exception as e:
            return {"content": "", "error": str(e)}

    def _check_ollama(self, cfg: Dict) -> bool:
        """检查 Ollama 是否可用"""
        url = cfg.get("ollama_url", "http://localhost:11434")
        model = cfg.get("ollama_model", "qwen3:1.7b")
        try:
            req = urllib.request.Request(f"{url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                return any(model in m for m in models)
        except Exception:
            return False

    def _call_ollama(self, cfg: Dict, prompt: str) -> Dict[str, Any]:
        """调用 Ollama 本地模型"""
        url = cfg.get("ollama_url", "http://localhost:11434")
        payload = json.dumps({
            "model": cfg.get("ollama_model", "qwen3:1.7b"),
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": cfg.get("temperature", 0.1),
                "num_predict": cfg.get("max_tokens", 512),
            },
        }).encode()

        req = urllib.request.Request(
            f"{url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return {"content": data.get("response", "")}
        except Exception as e:
            return {"content": "", "error": str(e)}


# ═══ 全局实例 ═══

llm_config = LLMConfig()
