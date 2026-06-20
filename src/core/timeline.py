from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable, Tuple
from enum import Enum
import uuid
import json
import os
import csv
import io


class TimeType(Enum):
    REAL_TIME = "real-time"
    HISTORICAL = "historical"
    PREDICTED = "predicted"


class FreshnessLevel(Enum):
    FRESH = "fresh"
    RECENT = "recent"
    STALE = "stale"
    EXPIRED = "expired"
    ARCHIVE = "archive"


class SourceReliability(Enum):
    OFFICIAL = 5
    PROFESSIONAL = 4
    AUTHORITATIVE_MEDIA = 3
    GENERAL = 2
    UNVERIFIED = 1


# ── 数据校验 ─────────────────────────────────────────────────

class ValidationError(Exception):
    """数据校验错误"""
    pass


class DuplicateError(Exception):
    """重复数据错误"""
    pass


def validate_event_data(
    timestamp: datetime = None,
    summary: str = "",
    tags: List[str] = None,
    source: str = "",
) -> Tuple[bool, List[str]]:
    """校验事件数据，返回 (是否合法, 错误列表)"""
    errors = []

    if timestamp is None:
        errors.append("时间戳不能为空")
    elif timestamp.year < 1900:
        errors.append(f"时间戳年份不合理: {timestamp.year}")
    elif timestamp > datetime.now() + timedelta(days=365 * 10):
        errors.append(f"时间戳不能超过未来10年: {timestamp}")

    if not summary or not summary.strip():
        errors.append("事件摘要不能为空")
    elif len(summary) > 2000:
        errors.append(f"事件摘要过长: {len(summary)} 字符（上限 2000）")

    if tags:
        for tag in tags:
            if not tag or not tag.strip():
                errors.append("标签不能为空字符串")
            elif len(tag) > 50:
                errors.append(f"标签过长: '{tag[:20]}...'（上限 50 字符）")

    if source and len(source) > 200:
        errors.append(f"来源名称过长（上限 200 字符）")

    return (len(errors) == 0, errors)


@dataclass
class TimelineEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    time_type: TimeType = TimeType.HISTORICAL
    data: Any = None
    source: str = ""
    source_reliability: SourceReliability = SourceReliability.GENERAL
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    chapter_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "time_type": self.time_type.value,
            "data": self.data,
            "source": self.source,
            "source_reliability": self.source_reliability.value,
            "tags": self.tags,
            "summary": self.summary,
            "chapter_id": self.chapter_id,
        }

    def fingerprint(self) -> str:
        """生成事件指纹，用于去重判断"""
        return f"{self.timestamp.isoformat()}|{self.summary.strip()}|{self.source.strip()}"


@dataclass
class Chapter:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)

    @property
    def duration_label(self) -> str:
        start = self.start_time.strftime("%Y-%m")
        end = self.end_time.strftime("%Y-%m")
        return f"{start} -> {end}"


@dataclass
class Bookmark:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    title: str = ""
    note: str = ""
    color: str = "#FFD700"
    linked_event_ids: List[str] = field(default_factory=list)


@dataclass
class Annotation:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    type: str = "note"
    content: str = ""
    cross_timeline_note: str = ""


class Timeline:
    def __init__(self, title: str = ""):
        self.id: str = str(uuid.uuid4())[:8]
        self.title: str = title
        self.base_time: datetime = datetime.now()
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self._events: Dict[str, TimelineEvent] = {}
        self._event_list: List[TimelineEvent] = []
        self._fingerprints: set = set()  # 去重指纹集合
        self.chapters: List[Chapter] = []
        self.bookmarks: List[Bookmark] = []
        self.annotations: List[Annotation] = []
        self._event_change_callbacks: List[Callable] = []

    def set_range(self, start: datetime, end: datetime):
        self.start_time = start
        self.end_time = end

    # ── 事件增删改 ─────────────────────────────────────────

    def add_event(self, event: TimelineEvent, skip_duplicate: bool = True) -> str:
        """添加事件，自动去重"""
        if skip_duplicate:
            fp = event.fingerprint()
            if fp in self._fingerprints:
                raise DuplicateError(
                    f"重复事件: {event.summary[:30]}... @ {event.timestamp.strftime('%Y-%m-%d')}"
                )
            self._fingerprints.add(fp)

        self._events[event.id] = event
        self._event_list.append(event)
        self._event_list.sort(key=lambda x: x.timestamp)
        self._notify_change("event_added", event)
        return event.id

    def update_event(self, event_id: str, **kwargs) -> bool:
        """更新事件字段"""
        event = self._events.get(event_id)
        if not event:
            return False

        old_fp = event.fingerprint()

        for key, value in kwargs.items():
            if hasattr(event, key):
                setattr(event, key, value)
            else:
                raise ValueError(f"事件没有字段: {key}")

        # 更新指纹
        self._fingerprints.discard(old_fp)
        self._fingerprints.add(event.fingerprint())

        self._event_list.sort(key=lambda x: x.timestamp)
        self._notify_change("event_updated", event)
        return True

    def remove_event(self, event_id: str) -> bool:
        """删除事件"""
        event = self._events.pop(event_id, None)
        if not event:
            return False

        self._fingerprints.discard(event.fingerprint())
        self._event_list = [e for e in self._event_list if e.id != event_id]

        # 从章节中移除
        for chapter in self.chapters:
            if event_id in chapter.event_ids:
                chapter.event_ids.remove(event_id)

        self._notify_change("event_removed", event)
        return True

    def add_events(self, events: List[TimelineEvent], skip_duplicate: bool = True) -> List[str]:
        ids = []
        for event in events:
            ids.append(self.add_event(event, skip_duplicate=skip_duplicate))
        return ids

    def is_duplicate(self, event: TimelineEvent) -> bool:
        """检查事件是否重复"""
        return event.fingerprint() in self._fingerprints

    # ── 事件查询 ─────────────────────────────────────────

    def get_event(self, event_id: str) -> Optional[TimelineEvent]:
        return self._events.get(event_id)

    def get_events_before(self, time: datetime) -> List[TimelineEvent]:
        return [e for e in self._event_list if e.timestamp < time]

    def get_events_after(self, time: datetime) -> List[TimelineEvent]:
        return [e for e in self._event_list if e.timestamp > time]

    def get_events_between(self, start: datetime, end: datetime) -> List[TimelineEvent]:
        return [e for e in self._event_list if start <= e.timestamp <= end]

    def get_events_around(self, time: datetime, window: timedelta) -> List[TimelineEvent]:
        half = window / 2
        return self.get_events_between(time - half, time + half)

    def get_all_events(self) -> List[TimelineEvent]:
        return list(self._event_list)

    def get_event_count(self) -> int:
        return len(self._event_list)

    def search_events(
        self,
        keyword: str = "",
        tags: List[str] = None,
        source: str = "",
        start_time: datetime = None,
        end_time: datetime = None,
        time_type: TimeType = None,
    ) -> List[TimelineEvent]:
        """多条件搜索事件"""
        results = self._event_list

        if keyword:
            kw = keyword.lower()
            results = [
                e for e in results
                if kw in (e.summary or "").lower()
                or kw in " ".join(e.tags).lower()
                or kw in str(e.data or "").lower()
            ]

        if tags:
            tag_set = set(tags)
            results = [e for e in results if tag_set & set(e.tags)]

        if source:
            src = source.lower()
            results = [e for e in results if src in (e.source or "").lower()]

        if start_time:
            results = [e for e in results if e.timestamp >= start_time]

        if end_time:
            results = [e for e in results if e.timestamp <= end_time]

        if time_type:
            results = [e for e in results if e.time_type == time_type]

        return results

    # ── 章节管理 ─────────────────────────────────────────

    def add_chapter(self, chapter: Chapter):
        self.chapters.append(chapter)
        self.chapters.sort(key=lambda x: x.start_time)

    def remove_chapter(self, chapter_id: str):
        self.chapters = [c for c in self.chapters if c.id != chapter_id]

    def get_chapter(self, chapter_id: str) -> Optional[Chapter]:
        for c in self.chapters:
            if c.id == chapter_id:
                return c
        return None

    def get_chapter_at_time(self, time: datetime) -> Optional[Chapter]:
        for c in self.chapters:
            if c.start_time <= time <= c.end_time:
                return c
        return None

    def get_chapter_events(self, chapter_id: str) -> List[TimelineEvent]:
        chapter = self.get_chapter(chapter_id)
        if not chapter:
            return []
        return [self._events[eid] for eid in chapter.event_ids if eid in self._events]

    # ── 书签/批注 ─────────────────────────────────────────

    def add_bookmark(self, bookmark: Bookmark):
        self.bookmarks.append(bookmark)
        self.bookmarks.sort(key=lambda x: x.timestamp)

    def remove_bookmark(self, bookmark_id: str):
        self.bookmarks = [b for b in self.bookmarks if b.id != bookmark_id]

    def add_annotation(self, annotation: Annotation):
        self.annotations.append(annotation)
        self.annotations.sort(key=lambda x: x.timestamp)

    def get_bookmarks_at_time(self, time: datetime) -> List[Bookmark]:
        return [b for b in self.bookmarks if b.timestamp == time]

    # ── 序列化 ─────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "base_time": self.base_time.isoformat(),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "events": [e.to_dict() for e in self._event_list],
            "chapters": [
                {
                    "id": c.id,
                    "title": c.title,
                    "start_time": c.start_time.isoformat(),
                    "end_time": c.end_time.isoformat(),
                    "summary": c.summary,
                    "tags": c.tags,
                    "event_ids": c.event_ids,
                }
                for c in self.chapters
            ],
            "bookmarks": [
                {
                    "id": b.id,
                    "timestamp": b.timestamp.isoformat(),
                    "title": b.title,
                    "note": b.note,
                    "color": b.color,
                }
                for b in self.bookmarks
            ],
        }

    def on_change(self, callback: Callable):
        self._event_change_callbacks.append(callback)

    def _notify_change(self, change_type: str, data: Any):
        for cb in self._event_change_callbacks:
            try:
                cb(change_type, data)
            except Exception:
                pass

    def __len__(self) -> int:
        return len(self._event_list)

    def __repr__(self) -> str:
        return (
            f"Timeline(id={self.id}, title={self.title}, "
            f"events={len(self._event_list)}, chapters={len(self.chapters)})"
        )


class TimelineNavigator:
    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        self._current_position: datetime = datetime.now()
        self._last_search_results: List[TimelineEvent] = []
        self._search_index: int = -1

    @property
    def current_position(self) -> datetime:
        return self._current_position

    @property
    def last_search_results(self) -> List[TimelineEvent]:
        return self._last_search_results

    @property
    def search_result_count(self) -> int:
        return len(self._last_search_results)

    # ── 跳转 ─────────────────────────────────────────

    def jump_to(self, time: datetime) -> Dict:
        self._current_position = time
        return self.get_context()

    def jump_to_event(self, event_id: str) -> Optional[Dict]:
        event = self.timeline.get_event(event_id)
        if not event:
            return None
        return self.jump_to(event.timestamp)

    def jump_to_chapter(self, chapter_id: str) -> Optional[Dict]:
        chapter = self.timeline.get_chapter(chapter_id)
        if not chapter:
            return None
        return self.jump_to(chapter.start_time)

    def jump_to_start(self) -> Dict:
        if self.timeline.start_time:
            return self.jump_to(self.timeline.start_time)
        events = self.timeline.get_all_events()
        if events:
            return self.jump_to(events[0].timestamp)
        return self.get_context()

    def jump_to_end(self) -> Dict:
        if self.timeline.end_time:
            return self.jump_to(self.timeline.end_time)
        events = self.timeline.get_all_events()
        if events:
            return self.jump_to(events[-1].timestamp)
        return self.get_context()

    def rewind(self, duration: timedelta) -> Dict:
        new_time = self._current_position - duration
        return self.jump_to(new_time)

    def fast_forward(self, duration: timedelta) -> Dict:
        new_time = self._current_position + duration
        return self.jump_to(new_time)

    # ── 搜索 ─────────────────────────────────────────

    def search(self, **kwargs) -> List[Dict]:
        """搜索事件并缓存结果

        参数同 Timeline.search_events: keyword, tags, source,
        start_time, end_time, time_type
        """
        results = self.timeline.search_events(**kwargs)
        self._last_search_results = results
        self._search_index = -1
        return [e.to_dict() for e in results]

    def search_and_jump(self, **kwargs) -> Optional[Dict]:
        """搜索并跳转到第一个结果"""
        self.search(**kwargs)
        if self._last_search_results:
            self._search_index = 0
            return self.jump_to(self._last_search_results[0].timestamp)
        return None

    def jump_to_next_result(self) -> Optional[Dict]:
        """跳转到下一个搜索结果"""
        if not self._last_search_results:
            return None
        self._search_index = (self._search_index + 1) % len(self._last_search_results)
        event = self._last_search_results[self._search_index]
        return self.jump_to(event.timestamp)

    def jump_to_prev_result(self) -> Optional[Dict]:
        """跳转到上一个搜索结果"""
        if not self._last_search_results:
            return None
        self._search_index = (self._search_index - 1) % len(self._last_search_results)
        event = self._last_search_results[self._search_index]
        return self.jump_to(event.timestamp)

    # ── 时间范围过滤 ─────────────────────────────────

    def get_events_between(self, start: datetime, end: datetime) -> List[Dict]:
        """获取指定时间范围内的事件"""
        events = self.timeline.get_events_between(start, end)
        return [e.to_dict() for e in events]

    def get_events_before(self, time: datetime = None) -> List[Dict]:
        """获取指定时间之前的事件（默认当前位置之前）"""
        t = time or self._current_position
        events = self.timeline.get_events_before(t)
        return [e.to_dict() for e in events]

    def get_events_after(self, time: datetime = None) -> List[Dict]:
        """获取指定时间之后的事件（默认当前位置之后）"""
        t = time or self._current_position
        events = self.timeline.get_events_after(t)
        return [e.to_dict() for e in events]

    def get_events_around(self, window: timedelta = timedelta(days=30)) -> List[Dict]:
        """获取当前位置周围的事件"""
        events = self.timeline.get_events_around(self._current_position, window)
        return [e.to_dict() for e in events]

    # ── 上下文 ─────────────────────────────────────────

    def get_context(self, window: timedelta = timedelta(days=90)) -> Dict:
        events_around = self.timeline.get_events_around(self._current_position, window)
        current_chapter = self.timeline.get_chapter_at_time(self._current_position)
        bookmarks = self.timeline.get_bookmarks_at_time(self._current_position)

        before_count = len(self.timeline.get_events_before(self._current_position))
        after_count = len(self.timeline.get_events_after(self._current_position))

        return {
            "current_position": self._current_position.isoformat(),
            "events": [e.to_dict() for e in events_around],
            "current_chapter": (
                {
                    "id": current_chapter.id,
                    "title": current_chapter.title,
                    "duration": current_chapter.duration_label,
                }
                if current_chapter
                else None
            ),
            "bookmarks": [
                {"id": b.id, "title": b.title, "note": b.note} for b in bookmarks
            ],
            "navigation": {
                "events_before_current": before_count,
                "events_after_current": after_count,
                "total_events": self.timeline.get_event_count(),
                "search_results_cached": len(self._last_search_results),
                "search_index": self._search_index,
            },
        }

    def pause_and_reflect(self, question: str) -> Dict:
        context = self.get_context()
        context["question"] = question
        return context


class TimelineBase:
    def __init__(self, title: str = ""):
        self.timeline = Timeline(title=title)
        self.navigator = TimelineNavigator(self.timeline)
        self._chapter_detector = ChapterDetector(self.timeline)

    # ── 持久化 ─────────────────────────────────────────

    def save(self, filepath: str) -> str:
        """将时间轴持久化到 JSON 文件"""
        data = self.to_dict()
        data["_meta"] = {
            "saved_at": datetime.now().isoformat(),
            "version": "1.0",
            "format": "chronovisor-timeline",
        }
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    @classmethod
    def load(cls, filepath: str) -> "TimelineBase":
        """从 JSON 文件加载时间轴"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        tb = cls(title=data.get("title", ""))
        if data.get("start_time"):
            tb.timeline.start_time = datetime.fromisoformat(data["start_time"])
        if data.get("end_time"):
            tb.timeline.end_time = datetime.fromisoformat(data["end_time"])
        if data.get("base_time"):
            tb.timeline.base_time = datetime.fromisoformat(data["base_time"])

        for ed in data.get("events", []):
            event = TimelineEvent(
                id=ed["id"],
                timestamp=datetime.fromisoformat(ed["timestamp"]),
                time_type=TimeType(ed.get("time_type", "historical")),
                data=ed.get("data"),
                source=ed.get("source", ""),
                source_reliability=SourceReliability(ed.get("source_reliability", 2)),
                tags=ed.get("tags", []),
                summary=ed.get("summary", ""),
                chapter_id=ed.get("chapter_id"),
            )
            tb.timeline.add_event(event)

        for cd in data.get("chapters", []):
            chapter = Chapter(
                id=cd["id"],
                title=cd["title"],
                start_time=datetime.fromisoformat(cd["start_time"]),
                end_time=datetime.fromisoformat(cd["end_time"]),
                summary=cd.get("summary", ""),
                tags=cd.get("tags", []),
                event_ids=cd.get("event_ids", []),
            )
            tb.timeline.add_chapter(chapter)

        for bd in data.get("bookmarks", []):
            bookmark = Bookmark(
                id=bd["id"],
                timestamp=datetime.fromisoformat(bd["timestamp"]),
                title=bd.get("title", ""),
                note=bd.get("note", ""),
                color=bd.get("color", "#FFD700"),
            )
            tb.timeline.add_bookmark(bookmark)

        return tb

    # ── 批量导入 ─────────────────────────────────────────

    def import_csv(self, filepath: str, skip_duplicate: bool = True) -> Dict:
        """从 CSV 文件批量导入事件

        CSV 列格式（第一行表头）：
        timestamp, summary, tags, source, time_type, source_reliability, data

        - timestamp: ISO 格式或 YYYY-MM-DD
        - summary: 事件摘要（必填）
        - tags: 逗号分隔的标签，如 "加息,美联储"
        - source: 数据来源
        - time_type: historical/real-time/predicted
        - source_reliability: 1-5
        - data: JSON 格式的附加数据

        返回: {"imported": N, "skipped": N, "errors": [...]}
        """
        result = {"imported": 0, "skipped": 0, "errors": []}

        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):  # 第2行起（第1行是表头）
                try:
                    # 解析时间戳
                    ts_str = row.get("timestamp", "").strip()
                    if not ts_str:
                        result["errors"].append(f"第{i}行: 时间戳为空")
                        continue
                    try:
                        timestamp = datetime.fromisoformat(ts_str)
                    except ValueError:
                        timestamp = datetime.strptime(ts_str, "%Y-%m-%d")

                    summary = row.get("summary", "").strip()
                    if not summary:
                        result["errors"].append(f"第{i}行: 摘要为空")
                        continue

                    tags_str = row.get("tags", "").strip()
                    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

                    source = row.get("source", "").strip()

                    time_type_str = row.get("time_type", "historical").strip()
                    try:
                        time_type = TimeType(time_type_str)
                    except ValueError:
                        time_type = TimeType.HISTORICAL

                    reliability_str = row.get("source_reliability", "2").strip()
                    try:
                        source_reliability = SourceReliability(int(reliability_str))
                    except (ValueError, TypeError):
                        source_reliability = SourceReliability.GENERAL

                    data_str = row.get("data", "").strip()
                    data = json.loads(data_str) if data_str else None

                    # 校验
                    valid, errors = validate_event_data(timestamp, summary, tags, source)
                    if not valid:
                        result["errors"].append(f"第{i}行: {'; '.join(errors)}")
                        continue

                    event = TimelineEvent(
                        timestamp=timestamp,
                        summary=summary,
                        tags=tags,
                        source=source,
                        time_type=time_type,
                        source_reliability=source_reliability,
                        data=data,
                    )

                    try:
                        self.timeline.add_event(event, skip_duplicate=skip_duplicate)
                        result["imported"] += 1
                    except DuplicateError:
                        result["skipped"] += 1

                except Exception as e:
                    result["errors"].append(f"第{i}行: {type(e).__name__}: {e}")

        return result

    def import_json(self, filepath: str, skip_duplicate: bool = True) -> Dict:
        """从 JSON 文件批量导入事件

        支持两种格式：
        1. 事件数组：[{timestamp, summary, tags, ...}, ...]
        2. 完整时间轴：{"events": [{...}], "chapters": [...]}

        返回: {"imported": N, "skipped": N, "errors": [...]}
        """
        result = {"imported": 0, "skipped": 0, "errors": []}

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 支持两种格式
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "events" in data:
            items = data["events"]
        else:
            result["errors"].append("JSON 格式不支持：需为事件数组或包含 events 字段的对象")
            return result

        for i, item in enumerate(items, start=1):
            try:
                ts_str = item.get("timestamp", "")
                if not ts_str:
                    result["errors"].append(f"第{i}项: 时间戳为空")
                    continue
                try:
                    timestamp = datetime.fromisoformat(ts_str)
                except ValueError:
                    timestamp = datetime.strptime(ts_str, "%Y-%m-%d")

                summary = item.get("summary", "")
                if not summary:
                    result["errors"].append(f"第{i}项: 摘要为空")
                    continue

                tags = item.get("tags", [])
                source = item.get("source", "")

                time_type_str = item.get("time_type", "historical")
                try:
                    time_type = TimeType(time_type_str)
                except ValueError:
                    time_type = TimeType.HISTORICAL

                try:
                    source_reliability = SourceReliability(int(item.get("source_reliability", 2)))
                except (ValueError, TypeError):
                    source_reliability = SourceReliability.GENERAL

                data = item.get("data")

                valid, errors = validate_event_data(timestamp, summary, tags, source)
                if not valid:
                    result["errors"].append(f"第{i}项: {'; '.join(errors)}")
                    continue

                event = TimelineEvent(
                    timestamp=timestamp,
                    summary=summary,
                    tags=tags,
                    source=source,
                    time_type=time_type,
                    source_reliability=source_reliability,
                    data=data,
                )

                try:
                    self.timeline.add_event(event, skip_duplicate=skip_duplicate)
                    result["imported"] += 1
                except DuplicateError:
                    result["skipped"] += 1

            except Exception as e:
                result["errors"].append(f"第{i}项: {type(e).__name__}: {e}")

        return result

    # ── 导出 ─────────────────────────────────────────

    def export_csv(self, filepath: str) -> str:
        """导出为 CSV 文件（默认格式，方便查看和云文档）"""
        events = self.timeline.get_all_events()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id", "timestamp", "summary", "tags", "source",
                "time_type", "source_reliability", "data",
            ])
            for e in events:
                writer.writerow([
                    e.id,
                    e.timestamp.isoformat(),
                    e.summary,
                    ",".join(e.tags),
                    e.source,
                    e.time_type.value,
                    e.source_reliability.value,
                    json.dumps(e.data, ensure_ascii=False) if e.data else "",
                ])
        return filepath

    def export_json(self, filepath: str) -> str:
        """导出为 JSON 文件"""
        data = self.to_dict()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    # ── 事件操作 ─────────────────────────────────────────

    def add_event(
        self,
        timestamp: datetime,
        data: Any,
        source: str = "",
        time_type: TimeType = TimeType.HISTORICAL,
        source_reliability: SourceReliability = SourceReliability.GENERAL,
        tags: List[str] = None,
        summary: str = "",
    ) -> str:
        # 数据校验
        valid, errors = validate_event_data(timestamp, summary, tags, source)
        if not valid:
            raise ValidationError("; ".join(errors))

        event = TimelineEvent(
            timestamp=timestamp,
            time_type=time_type,
            data=data,
            source=source,
            source_reliability=source_reliability,
            tags=tags or [],
            summary=summary,
        )
        return self.timeline.add_event(event)

    def update_event(self, event_id: str, **kwargs) -> bool:
        """更新事件字段"""
        return self.timeline.update_event(event_id, **kwargs)

    def remove_event(self, event_id: str) -> bool:
        """删除事件"""
        return self.timeline.remove_event(event_id)

    def search_events(self, **kwargs) -> List[TimelineEvent]:
        """搜索事件（返回 TimelineEvent 列表）"""
        return self.timeline.search_events(**kwargs)

    def search(self, **kwargs) -> List[Dict]:
        """搜索事件（返回字典列表，支持缓存和翻页）"""
        return self.navigator.search(**kwargs)

    def search_and_jump(self, **kwargs) -> Optional[Dict]:
        """搜索并跳转到第一个结果"""
        return self.navigator.search_and_jump(**kwargs)

    def jump_to_next_result(self) -> Optional[Dict]:
        """跳转到下一个搜索结果"""
        return self.navigator.jump_to_next_result()

    def jump_to_prev_result(self) -> Optional[Dict]:
        """跳转到上一个搜索结果"""
        return self.navigator.jump_to_prev_result()

    def get_events_between(self, start: datetime, end: datetime) -> List[Dict]:
        """获取指定时间范围内的事件"""
        return self.navigator.get_events_between(start, end)

    def get_events_before(self, time: datetime = None) -> List[Dict]:
        """获取指定时间之前的事件"""
        return self.navigator.get_events_before(time)

    def get_events_after(self, time: datetime = None) -> List[Dict]:
        """获取指定时间之后的事件"""
        return self.navigator.get_events_after(time)

    def add_events_batch(self, events_data: List[Dict]) -> List[str]:
        ids = []
        for ed in events_data:
            event_id = self.add_event(
                timestamp=ed.get("timestamp", datetime.now()),
                data=ed.get("data"),
                source=ed.get("source", ""),
                time_type=ed.get("time_type", TimeType.HISTORICAL),
                source_reliability=ed.get(
                    "source_reliability", SourceReliability.GENERAL
                ),
                tags=ed.get("tags", []),
                summary=ed.get("summary", ""),
            )
            ids.append(event_id)
        return ids

    def auto_detect_chapters(self, min_events: int = 3, max_chapters: int = None) -> List[Chapter]:
        return self._chapter_detector.detect(min_events, max_chapters)

    def add_bookmark(self, timestamp: datetime, title: str, note: str = "", color: str = "#FFD700") -> str:
        bookmark = Bookmark(timestamp=timestamp, title=title, note=note, color=color)
        self.timeline.add_bookmark(bookmark)
        return bookmark.id

    def add_annotation(self, timestamp: datetime, type: str, content: str, cross_timeline_note: str = "") -> str:
        annotation = Annotation(
            timestamp=timestamp,
            type=type,
            content=content,
            cross_timeline_note=cross_timeline_note,
        )
        self.timeline.add_annotation(annotation)
        return annotation.id

    def jump_to(self, time: datetime) -> Dict:
        return self.navigator.jump_to(time)

    def jump_to_event(self, event_id: str) -> Optional[Dict]:
        return self.navigator.jump_to_event(event_id)

    def jump_to_chapter(self, chapter_id: str) -> Optional[Dict]:
        return self.navigator.jump_to_chapter(chapter_id)

    def rewind(self, duration: timedelta) -> Dict:
        return self.navigator.rewind(duration)

    def fast_forward(self, duration: timedelta) -> Dict:
        return self.navigator.fast_forward(duration)

    def pause_and_reflect(self, question: str) -> Dict:
        return self.navigator.pause_and_reflect(question)

    def get_current_context(self) -> Dict:
        return self.navigator.get_context()

    def to_dict(self) -> Dict:
        return self.timeline.to_dict()

    def __repr__(self) -> str:
        return f"TimelineBase(title={self.timeline.title}, events={len(self.timeline)}, chapters={len(self.timeline.chapters)})"


class ChapterDetector:
    LARGE_GAP_DAYS = 180
    MIN_GAP_DAYS = 60
    DEFAULT_MAX_CHAPTERS = 8
    DEFAULT_TARGET_CHAPTERS = 5

    def __init__(self, timeline: Timeline):
        self.timeline = timeline

    def detect(self, min_events: int = 3, max_chapters: int = None) -> List[Chapter]:
        if max_chapters is None:
            max_chapters = self.DEFAULT_MAX_CHAPTERS
        events = self.timeline.get_all_events()
        if len(events) < 3:
            return []

        raw_boundaries = self._find_time_gaps(events)

        if len(raw_boundaries) < 3 and len(events) >= 6:
            raw_boundaries = self._fallback_even_split(
                events, target_chapters=self.DEFAULT_TARGET_CHAPTERS
            )

        raw_chapters = self._build_raw_chapters(events, raw_boundaries)
        merged = self._merge_small_chapters(raw_chapters, min_events)

        if len(merged) > max_chapters:
            merged = self._force_merge_to_max(merged, max_chapters)

        chapters = self._finalize_chapters(merged)
        return chapters

    def _find_time_gaps(self, events: List[TimelineEvent]) -> List[int]:
        boundaries = [0]
        for i in range(1, len(events)):
            gap_days = (events[i].timestamp - events[i - 1].timestamp).days
            if gap_days > self.LARGE_GAP_DAYS:
                boundaries.append(i)
            elif gap_days > self.MIN_GAP_DAYS and self._is_semantic_shift(
                events[i - 1], events[i]
            ):
                boundaries.append(i)
        boundaries.append(len(events))
        return boundaries

    def _fallback_even_split(
        self, events: List[TimelineEvent], target_chapters: int = 5
    ) -> List[int]:
        if len(events) < target_chapters:
            target_chapters = len(events)
        n = len(events)
        chunk_size = max(1, n // target_chapters)
        boundaries = [0]
        for i in range(chunk_size, n, chunk_size):
            boundaries.append(i)
        boundaries.append(n)
        boundaries = sorted(set(boundaries))
        return boundaries

    def _force_merge_to_max(
        self, chapters: List[List[TimelineEvent]], max_chapters: int
    ) -> List[List[TimelineEvent]]:
        if len(chapters) <= max_chapters:
            return chapters
        all_events = []
        for ch in chapters:
            all_events.extend(ch)
        n = len(all_events)
        chunk_size = max(1, n // max_chapters)
        result = []
        for i in range(0, n, chunk_size):
            result.append(all_events[i : i + chunk_size])
        if len(result) > max_chapters:
            last = result.pop()
            result[-1].extend(last)
        return result

    def _is_semantic_shift(self, prev: TimelineEvent, curr: TimelineEvent) -> bool:
        if curr.time_type == TimeType.PREDICTED and prev.time_type != TimeType.PREDICTED:
            return True
        prev_text = (prev.summary or "") + " " + " ".join(prev.tags)
        curr_text = (curr.summary or "") + " " + " ".join(curr.tags)
        negation_keywords = ["停止", "取消", "逆转", "收紧", "放开", "转向", "重启"]
        for kw in negation_keywords:
            if kw in curr_text and kw not in prev_text:
                return True
        return False

    def _build_raw_chapters(
        self, events: List[TimelineEvent], boundaries: List[int]
    ) -> List[List[TimelineEvent]]:
        chapters = []
        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]
            end_idx = boundaries[i + 1]
            chapter_events = events[start_idx:end_idx]
            if chapter_events:
                chapters.append(chapter_events)
        return chapters

    def _merge_small_chapters(
        self, raw_chapters: List[List[TimelineEvent]], min_events: int
    ) -> List[List[TimelineEvent]]:
        if not raw_chapters:
            return raw_chapters
        merged = []
        buffer = []
        for ch in raw_chapters:
            buffer.extend(ch)
            if len(buffer) >= min_events:
                merged.append(buffer)
                buffer = []
        if buffer:
            if merged:
                merged[-1].extend(buffer)
            else:
                merged.append(buffer)
        return merged

    def _finalize_chapters(self, event_groups: List[List[TimelineEvent]]) -> List[Chapter]:
        chapters = []
        for i, group in enumerate(event_groups):
            group.sort(key=lambda e: e.timestamp)
            start_time = group[0].timestamp
            end_time = group[-1].timestamp
            chapter = Chapter(
                title=self._generate_title(group, i),
                start_time=start_time,
                end_time=end_time,
                summary=self._generate_summary(group),
                tags=self._extract_tags(group),
                event_ids=[e.id for e in group],
            )
            chapters.append(chapter)
            self.timeline.add_chapter(chapter)
        return chapters

    def _generate_title(self, events: List[TimelineEvent], index: int) -> str:
        tags = self._extract_tags(events)
        if tags:
            primary_tag = tags[0]
        else:
            primary_tag = "发展阶段"
        start = events[0].timestamp.strftime("%Y-%m")
        end = events[-1].timestamp.strftime("%Y-%m")
        return f"第{index + 1}章：{primary_tag} ({start} -> {end})"

    def _generate_summary(self, events: List[TimelineEvent]) -> str:
        summaries = [e.summary for e in events if e.summary]
        if summaries:
            return "；".join(summaries[:3])
        return f"包含 {len(events)} 个关键事件"

    def _extract_tags(self, events: List[TimelineEvent]) -> List[str]:
        tag_counts: Dict[str, int] = {}
        for e in events:
            for tag in e.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        return [tag for tag, _ in sorted_tags[:3]]
