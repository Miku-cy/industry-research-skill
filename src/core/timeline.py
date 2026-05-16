from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
import uuid
import copy


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
        return f"{start} → {end}"


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
        self.chapters: List[Chapter] = []
        self.bookmarks: List[Bookmark] = []
        self.annotations: List[Annotation] = []
        self._event_change_callbacks: List[Callable] = []

    def set_range(self, start: datetime, end: datetime):
        self.start_time = start
        self.end_time = end

    def add_event(self, event: TimelineEvent) -> str:
        self._events[event.id] = event
        self._event_list.append(event)
        self._event_list.sort(key=lambda x: x.timestamp)
        self._notify_change("event_added", event)
        return event.id

    def add_events(self, events: List[TimelineEvent]) -> List[str]:
        ids = []
        for event in events:
            ids.append(self.add_event(event))
        return ids

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

    @property
    def current_position(self) -> datetime:
        return self._current_position

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

    def auto_detect_chapters(self, min_events: int = 3) -> List[Chapter]:
        return self._chapter_detector.detect(min_events)

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
    def __init__(self, timeline: Timeline):
        self.timeline = timeline

    def detect(self, min_events: int = 3) -> List[Chapter]:
        events = self.timeline.get_all_events()
        if len(events) < min_events * 2:
            return []

        inflection_points = self._find_inflection_points(events)
        return self._build_chapters(events, inflection_points)

    def _find_inflection_points(self, events: List[TimelineEvent]) -> List[TimelineEvent]:
        inflection_points = [events[0]]
        for i in range(1, len(events) - 1):
            prev = events[i - 1]
            curr = events[i]
            if self._is_inflection(prev, curr):
                inflection_points.append(curr)
        inflection_points.append(events[-1])
        return inflection_points

    def _is_inflection(self, prev: TimelineEvent, curr: TimelineEvent) -> bool:
        gap = curr.timestamp - prev.timestamp
        if gap > timedelta(days=180):
            return True
        prev_tags = set(prev.tags)
        curr_tags = set(curr.tags)
        if prev_tags and curr_tags and not prev_tags.intersection(curr_tags):
            return True
        if curr.time_type == TimeType.PREDICTED and prev.time_type != TimeType.PREDICTED:
            return True
        return False

    def _build_chapters(
        self, events: List[TimelineEvent], inflection_points: List[TimelineEvent]
    ) -> List[Chapter]:
        chapters = []
        for i in range(len(inflection_points) - 1):
            start = inflection_points[i]
            end = inflection_points[i + 1]
            chapter_events = self.timeline.get_events_between(start.timestamp, end.timestamp)
            if len(chapter_events) < 2:
                continue
            chapter = Chapter(
                title=self._generate_title(chapter_events, i),
                start_time=start.timestamp,
                end_time=end.timestamp,
                summary=self._generate_summary(chapter_events),
                tags=self._extract_tags(chapter_events),
                event_ids=[e.id for e in chapter_events],
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
        return f"第{index + 1}章：{primary_tag} ({start} → {end})"

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
