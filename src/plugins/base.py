"""分析插件基类

所有 ChronoVisor 分析插件必须继承此类并实现 analyze() 方法。
插件基于因果网络和章节数据进行分析，返回结构化结果。

设计原则：因果底座是公共的，分析策略是私有的。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 前向声明，避免循环导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..core.analyzer import CausalNetwork
    from ..core.timeline import Chapter


@dataclass
class PluginResult:
    """插件分析结果"""
    plugin_name: str                    # 插件名
    category: str                       # 结果分类
    items: Dict[str, List[str]]         # 分类 → 条目列表
    insights: List[str]                 # 洞察列表
    score: float = 0.0                  # 综合评分 0~1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "plugin": self.plugin_name,
            "category": self.category,
            "items": self.items,
            "insights": self.insights,
            "score": self.score,
            "metadata": self.metadata,
        }


class AnalysisPlugin(ABC):
    """分析插件基类"""

    name: str = "base"
    description: str = ""
    version: str = "1.0.0"

    @abstractmethod
    def analyze(
        self,
        events: List[Any],
        network: Optional[Any] = None,
        chapters: Optional[List[Any]] = None,
        **kwargs,
    ) -> PluginResult:
        """执行分析

        Args:
            events: 时间轴事件列表
            network: 因果网络（可选）
            chapters: 章节列表（可选）
            **kwargs: 插件特定参数

        Returns:
            PluginResult 分析结果
        """
        raise NotImplementedError

    def get_insights(self) -> List[str]:
        """返回上次分析的洞察列表"""
        return []

    def get_info(self) -> Dict[str, str]:
        """返回插件元信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
        }
