import copy
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum


class TaskPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class SubTask:
    id: str = field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    purpose: str = ""
    input_description: str = ""
    output_description: str = ""
    dependencies: List[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    search_queries: List[str] = field(default_factory=list)
    estimated_timeframe: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "purpose": self.purpose,
            "input": self.input_description,
            "output": self.output_description,
            "dependencies": self.dependencies,
            "priority": self.priority.value,
            "status": self.status.value,
            "search_queries": self.search_queries,
            "estimated_timeframe": self.estimated_timeframe,
            "tags": self.tags,
        }


@dataclass
class ResearchPlan:
    id: str = field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""
    tasks: List[SubTask] = field(default_factory=list)
    hierarchy: Dict[str, List[str]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
            "hierarchy": self.hierarchy,
            "created_at": self.created_at.isoformat(),
        }

    def get_executable_tasks(self) -> List[SubTask]:
        completed_ids = {t.id for t in self.tasks if t.status == TaskStatus.COMPLETED}
        executable = []
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            if all(dep in completed_ids for dep in task.dependencies):
                executable.append(task)
        return executable

    def get_next_task(self) -> Optional[SubTask]:
        executable = self.get_executable_tasks()
        if not executable:
            return None
        executable.sort(key=lambda t: t.priority.value)
        return executable[0]


class TaskDecomposer:
    def __init__(self):
        self._default_hierarchy_template = ["宏观层", "中观层", "微观层"]

    def decompose(self, raw_requirement: str) -> ResearchPlan:
        plan = ResearchPlan(title=raw_requirement[:50])
        hierarchy_layers = self._identify_hierarchy(raw_requirement)
        tasks = self._generate_tasks(raw_requirement, hierarchy_layers)
        plan.tasks = tasks
        plan.hierarchy = self._build_hierarchy(tasks, hierarchy_layers)
        return plan

    def _identify_hierarchy(self, requirement: str) -> List[str]:
        layers = []
        keywords_map = {
            "宏观层": ["产业", "行业", "市场", "全景", "宏观", "整体"],
            "中观层": ["公司", "企业", "上市公司", "竞争", "格局", "对比"],
            "微观层": ["个股", "股票", "股价", "投资", "估值", "预测"],
        }
        for layer, keywords in keywords_map.items():
            for kw in keywords:
                if kw in requirement:
                    if layer not in layers:
                        layers.append(layer)
                    break
        if not layers:
            layers = self._default_hierarchy_template
        return layers

    def _generate_tasks(self, requirement: str, layers: List[str]) -> List[SubTask]:
        tasks = []
        task_templates = {
            "宏观层": [
                SubTask(purpose="搜集行业宏观数据", input_description="行业名称、时间范围",
                    output_description="结构化的市场规模、增长率、用户数据",
                    priority=TaskPriority.HIGH, tags=["宏观", "数据", "行业规模"]),
                SubTask(purpose="分析行业政策环境", input_description="行业名称、时间范围",
                    output_description="政策变化清单及影响评估",
                    priority=TaskPriority.HIGH, tags=["宏观", "政策", "PEST-P"]),
                SubTask(purpose="识别行业发展趋势", input_description="行业宏观数据、政策环境",
                    output_description="3-5个关键趋势及判断依据",
                    priority=TaskPriority.MEDIUM, tags=["宏观", "趋势", "PEST-T"], dependencies=[]),
            ],
            "中观层": [
                SubTask(purpose="对比上市公司财务数据", input_description="目标公司列表、时间范围",
                    output_description="关键财务指标对比表",
                    priority=TaskPriority.HIGH, tags=["中观", "财务", "对比"]),
                SubTask(purpose="分析竞争格局", input_description="行业数据、公司数据",
                    output_description="竞争格局描述与市场份额",
                    priority=TaskPriority.MEDIUM, tags=["中观", "竞争", "波特五力"]),
            ],
            "微观层": [
                SubTask(purpose="深度分析目标公司基本面", input_description="目标公司名称、时间范围",
                    output_description="公司SWOT分析、财务趋势",
                    priority=TaskPriority.HIGH, tags=["微观", "基本面", "SWOT"]),
                SubTask(purpose="构建投资情景分析", input_description="公司基本面数据、行业前景",
                    output_description="乐观/基准/风险三种情景及估值",
                    priority=TaskPriority.HIGH, tags=["微观", "投资", "情景分析"]),
                SubTask(purpose="撰写投资建议", input_description="情景分析结果、风险因素",
                    output_description="投资建议与目标价",
                    priority=TaskPriority.MEDIUM, tags=["微观", "投资", "结论"], dependencies=[]),
            ],
        }
        prev_layer_tasks = []
        for layer in layers:
            templates = task_templates.get(layer, [])
            for template in templates:
                task = copy.deepcopy(template)
                if prev_layer_tasks and not task.dependencies:
                    task.dependencies = [t.id for t in prev_layer_tasks[:2]]
                tasks.append(task)
            prev_layer_tasks = [t for t in tasks if t.priority == TaskPriority.HIGH]
        for task in tasks:
            if not task.dependencies:
                task.dependencies = []
        return tasks

    def _build_hierarchy(self, tasks: List[SubTask], layers: List[str]) -> Dict[str, List[str]]:
        hierarchy: Dict[str, List[str]] = {}
        for layer in layers:
            hierarchy[layer] = []
        for task in tasks:
            matched = False
            for layer in layers:
                for tag in task.tags:
                    if layer.replace("层", "") in tag or tag in layer:
                        hierarchy.setdefault(layer, []).append(task.id)
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                hierarchy.setdefault(layers[0], []).append(task.id)
        return hierarchy

    def validate_decomposition(self, plan: ResearchPlan) -> Dict[str, Any]:
        issues = []
        warnings = []
        for task in plan.tasks:
            if not task.purpose:
                issues.append(f"任务 {task.id} 缺少目的描述")
            if not task.output_description:
                issues.append(f"任务 {task.id} 缺少输出描述")
            for dep in task.dependencies:
                if not any(t.id == dep for t in plan.tasks):
                    issues.append(f"任务 {task.id} 依赖了不存在的任务 {dep}")
        if len(plan.tasks) < 3:
            warnings.append("任务数量偏少，建议增加拆解粒度")
        if len(plan.tasks) > 20:
            warnings.append("任务数量偏多，建议合并相似任务")
        has_circular = self._check_circular_deps(plan.tasks)
        if has_circular:
            issues.append("检测到循环依赖")
        return {"valid": len(issues) == 0, "issues": issues, "warnings": warnings, "task_count": len(plan.tasks)}

    def _check_circular_deps(self, tasks: List[SubTask]) -> bool:
        visited = set()
        rec_stack = set()
        task_map = {t.id: t for t in tasks}
        def dfs(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            task = task_map.get(task_id)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        if dfs(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            rec_stack.discard(task_id)
            return False
        for task in tasks:
            if task.id not in visited:
                if dfs(task.id):
                    return True
        return False
