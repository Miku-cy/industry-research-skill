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
import logging
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
        "api_model": "mimo-v2-pro",
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

    # 速率限制：每分钟最多 90 次请求（留 10 次余量）
    MAX_RPM = 90
    MIN_INTERVAL = 60.0 / MAX_RPM  # 每次请求最小间隔（秒）
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2.0  # 指数退避倍数

    def __init__(self, config_path: str = ""):
        self.profiles: Dict[str, Dict] = {}
        self._config_path = config_path or self._find_config()
        self._last_call_time = 0.0
        self._rate_lock = threading.Lock()  # 线程安全的速率限制锁
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
        if self._config_path and os.path.exists(self._config_path):
            try:
                import yaml
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except ImportError:
                data = self._parse_yaml_simple(self._config_path)
            except Exception:
                data = {}

            # 读取 llm 配置段
            llm_section = data.get("llm", {})
            if isinstance(llm_section, dict):
                for name, overrides in llm_section.items():
                    if name in self.profiles and isinstance(overrides, dict):
                        for key, value in overrides.items():
                            if value:
                                self.profiles[name][key] = value

            # 兼容旧格式：semantic.api 段
            semantic = data.get("semantic", {})
            if isinstance(semantic, dict) and semantic:
                api = semantic.get("api", {})
                if isinstance(api, dict) and api and "semantic" in self.profiles:
                    self.profiles["semantic"]["api_url"] = api.get("url", "") or self.profiles["semantic"]["api_url"]
                    self.profiles["semantic"]["api_key"] = api.get("key", "") or self.profiles["semantic"]["api_key"]
                    self.profiles["semantic"]["api_model"] = api.get("model", "") or self.profiles["semantic"]["api_model"]
                ollama = semantic.get("ollama", {})
                if isinstance(ollama, dict) and ollama and "semantic" in self.profiles:
                    self.profiles["semantic"]["ollama_url"] = ollama.get("url", "") or self.profiles["semantic"]["ollama_url"]
                    self.profiles["semantic"]["ollama_model"] = ollama.get("model", "") or self.profiles["semantic"]["ollama_model"]
                mode = semantic.get("mode", "")
                if mode and "semantic" in self.profiles:
                    self.profiles["semantic"]["mode"] = mode

        # 3. 从 openclaw.json 读取通用 API key/url（最终回退）
        oc_key = self._get_openclaw_key()
        oc_url = self._get_openclaw_url()
        for name in self.profiles:
            if not self.profiles[name].get("api_key") and oc_key:
                self.profiles[name]["api_key"] = oc_key
            if not self.profiles[name].get("api_url") and oc_url:
                self.profiles[name]["api_url"] = oc_url

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

    def _get_openclaw_url(self) -> str:
        """从 openclaw.json 读取 API URL"""
        oc_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if not os.path.exists(oc_path):
            return ""
        try:
            with open(oc_path) as f:
                oc = json.load(f)
            providers = oc.get("models", {}).get("providers", {})
            for name, prov in providers.items():
                if prov.get("baseUrl"):
                    return prov["baseUrl"]
        except Exception:
            pass
        return ""

    @staticmethod
    def _parse_yaml_simple(path: str) -> Dict:
        """简易 YAML 解析器（pyyaml 不可用时的回退）

        支持的特性：
        - 缩进表示嵌套 dict（2 空格为常见单位，但实际按相对缩进解析）
        - `key: value` 叶节点（字符串、数字、布尔）
        - `key:` 开启子字典
        - `#` 注释、空行
        - 引号包裹的字符串

        不支持：列表、锚点、多行字符串、流式语法。
        足以覆盖 chronovisor.yaml 的结构。
        """
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        root: Dict[str, Any] = {}
        # stack: [(indent, dict_obj)]
        stack: list = [(-1, root)]

        def _parse_scalar(raw: str) -> Any:
            raw = raw.strip()
            if not raw:
                return ""
            # 去引号
            if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
                return raw[1:-1]
            low = raw.lower()
            if low in ("true", "yes"):
                return True
            if low in ("false", "no"):
                return False
            if low in ("null", "none", "~"):
                return None
            # 数字
            try:
                if "." in raw:
                    return float(raw)
                return int(raw)
            except ValueError:
                return raw

        for raw_line in lines:
            # 去行尾换行
            line = raw_line.rstrip("\n")
            # 去注释（粗略：行首 # 或纯空白后 #）
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            # 行内注释：`key: value # comment` —— 只在 value 段无引号时简单处理
            if "#" in stripped:
                # 不处理引号内的 #，简化
                hash_idx = stripped.find("#")
                # 检查 # 前是否有非空白字符
                before = stripped[:hash_idx].rstrip()
                if before == "" or before.endswith(":"):
                    # 整行或仅 key: 形式后的注释，跳过
                    if before.endswith(":"):
                        stripped = before
                    else:
                        continue
                else:
                    stripped = before

            indent = len(line) - len(line.lstrip())
            key, sep, val = stripped.partition(":")
            if not sep:
                continue
            key = key.strip()
            val = val.strip()

            # 弹栈到当前缩进的父级
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1] if stack else root

            if val == "":
                # 开启子字典
                child: Dict[str, Any] = {}
                parent[key] = child
                stack.append((indent, child))
            else:
                parent[key] = _parse_scalar(val)

        return root

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

    def call_batch(
        self,
        profile_name: str,
        prompts: List[str],
        max_workers: int = 3,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """批量并发 LLM 调用

        用 ThreadPoolExecutor 并发执行多个 call()，
        内部速率限制器保证不超限。

        Args:
            profile_name: 配置名
            prompts: 提示词列表
            max_workers: 最大并发数（默认 3，受速率限制约束）
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大 token

        Returns:
            结果列表，与 prompts 顺序一致
        """
        if not prompts:
            return []
        if len(prompts) == 1:
            return [self.call(profile_name, prompts[0], temperature, max_tokens)]

        results = [None] * len(prompts)

        def _call_one(idx: int):
            return idx, self.call(profile_name, prompts[idx], temperature, max_tokens)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_call_one, i) for i in range(len(prompts))]
            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    results[idx] = result
                except Exception as e:
                    # 找到对应的 index
                    for i, f in enumerate(futures):
                        if f is future:
                            results[i] = {"content": "", "error": str(e)}
                            break

        return results

    def _call_openai_compat(
        self,
        cfg: Dict,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """调用 OpenAI 兼容 API（带速率限制和重试）"""
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

        for attempt in range(self.MAX_RETRIES):
            # 速率限制（线程安全）：在锁内只计算等待时间，释放锁后再 sleep，
            # 避免在持有锁期间阻塞导致所有线程串行化
            with self._rate_lock:
                now = time.time()
                elapsed = now - self._last_call_time
                wait_for_rate = max(0.0, self.MIN_INTERVAL - elapsed)
                # 预占位：把下次合法调用时间设为"现在 + 待等时间"，
                # 让并发的其他线程排队到自己应等的时刻
                if wait_for_rate > 0:
                    self._last_call_time = now + wait_for_rate
                else:
                    self._last_call_time = now
            if wait_for_rate > 0:
                time.sleep(wait_for_rate)

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
                    # MiMo 推理模型：content 可能为空，答案在 reasoning_content 里
                    if not content and reasoning:
                        import re
                        json_match = re.search(r'\[[\s\S]*\]', reasoning)
                        if json_match:
                            content = json_match.group(0)
                        else:
                            content = reasoning
                    return {"content": content, "reasoning_content": reasoning}
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    # 限流，指数退避重试
                    wait = self.RETRY_BACKOFF ** (attempt + 1)
                    logger.warning("[llm_config] 429 限流，%.1fs 后重试 (%s/%s)", wait, attempt+1, self.MAX_RETRIES)
                    time.sleep(wait)
                    continue
                return {"content": "", "error": f"HTTP Error {e.code}: {e.reason}"}
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BACKOFF ** (attempt + 1))
                    continue
                return {"content": "", "error": str(e)}

        return {"content": "", "error": "超过最大重试次数"}

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
