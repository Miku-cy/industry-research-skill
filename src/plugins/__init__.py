"""ChronoVisor 插件包

核心插件（3个）：PEST / SWOT / 周期
扩展插件（extras/）：异常检测 / 趋势外推 / 相关性 / 情景分析
"""
from .base import AnalysisPlugin, PluginResult
from .registry import PluginRegistry, plugin_registry
from .pest import PESTPlugin
from .swot import SWOTPlugin
from .cycle import CyclePlugin

__all__ = [
    "AnalysisPlugin", "PluginResult",
    "PluginRegistry", "plugin_registry",
    "PESTPlugin", "SWOTPlugin", "CyclePlugin",
]
