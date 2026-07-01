"""插件注册表 — 发现、加载、管理分析插件"""
import importlib
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from .base import AnalysisPlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """插件注册表"""

    # 核心插件（随启动加载）
    CORE_PLUGINS = [
        ("pest", ".pest", "PESTPlugin"),
        ("swot", ".swot", "SWOTPlugin"),
        ("cycle", ".cycle", "CyclePlugin"),
    ]

    # 扩展插件（按需加载）
    EXTRAS = {
        "anomaly": ("src.extras.anomaly", "AnomalyPlugin"),
        "trend": ("src.extras.trend", "TrendPlugin"),
        "correlation": ("src.extras.correlation", "CorrelationPlugin"),
        "scenario": ("src.extras.scenario", "ScenarioPlugin"),
    }

    def __init__(self):
        self._plugins: Dict[str, AnalysisPlugin] = {}
        self._register_builtins()

    def _register_builtins(self):
        """注册核心插件"""
        for name, module_path, class_name in self.CORE_PLUGINS:
            try:
                mod = importlib.import_module(module_path, package="src.plugins")
                cls = getattr(mod, class_name)
                self._plugins[name] = cls()
            except Exception as e:
                logger.warning("[plugin_registry] 核心插件 %s 加载失败: %s", name, e)

    def load_extras(self):
        """加载扩展插件（不随启动自动加载，需要显式调用）"""
        for name, (module_path, class_name) in self.EXTRAS.items():
            if name in self._plugins:
                continue
            try:
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                self._plugins[name] = cls()
            except Exception as e:
                logger.warning("[plugin_registry] 扩展插件 %s 加载失败: %s", name, e)

    def register(self, plugin: AnalysisPlugin, *, overwrite: bool = False):
        """手动注册插件

        Args:
            plugin: 待注册的插件实例
            overwrite: 是否覆盖同名插件。默认 False — 同名插件已存在时抛出 ValueError，
                避免静默覆盖。
        """
        if not isinstance(plugin, AnalysisPlugin):
            raise TypeError(f"插件必须继承 AnalysisPlugin, got {type(plugin)}")
        if plugin.name in self._plugins and not overwrite:
            raise ValueError(
                f"插件名 '{plugin.name}' 已注册；如需覆盖请显式传 overwrite=True"
            )
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Optional[AnalysisPlugin]:
        """获取插件（核心直接返回，扩展尝试加载）"""
        if name in self._plugins:
            return self._plugins[name]
        # 尝试从扩展加载
        if name in self.EXTRAS:
            self.load_extras()
            return self._plugins.get(name)
        return None

    def list_plugins(self) -> List[Dict[str, str]]:
        return [p.get_info() for p in self._plugins.values()]

    def run(self, name: str, events: list, **kwargs):
        plugin = self.get(name)
        if not plugin:
            raise KeyError(f"插件 '{name}' 未注册")
        return plugin.analyze(events, **kwargs)

    def run_all(self, events: list, **kwargs) -> Dict[str, Any]:
        results = {}
        for name, plugin in self._plugins.items():
            try:
                results[name] = plugin.analyze(events, **kwargs)
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @property
    def names(self) -> List[str]:
        return list(self._plugins.keys())


plugin_registry = PluginRegistry()
