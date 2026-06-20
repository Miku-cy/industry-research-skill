import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from .timeline import TimelineBase, TimelineEvent, TimeType, SourceReliability, FreshnessLevel


@dataclass
class CollectedData:
    id: str = field(default_factory=lambda: f"data-{uuid.uuid4().hex[:8]}")
    raw_data: Any = None
    timestamp: datetime = field(default_factory=datetime.now)
    time_type: TimeType = TimeType.HISTORICAL
    source: str = ""
    source_url: str = ""
    source_reliability: SourceReliability = SourceReliability.GENERAL
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    freshness: FreshnessLevel = FreshnessLevel.RECENT


class DataCollector:
    def __init__(self, timeline_base: TimelineBase):
        self.timeline = timeline_base
        self._collected_data: List[CollectedData] = []
        self._search_history: List[Dict] = []

    def collect(self, data: Any, source: str = "", source_url: str = "",
        source_reliability: SourceReliability = SourceReliability.GENERAL,
        tags: List[str] = None, summary: str = "",
        timestamp: Optional[datetime] = None, time_type: Optional[TimeType] = None) -> str:
        if timestamp is None:
            timestamp = self._extract_timestamp_from_data(data)
        if time_type is None:
            time_type = self._infer_time_type(timestamp)
        freshness = self._calculate_freshness(timestamp)
        collected = CollectedData(raw_data=data, timestamp=timestamp, time_type=time_type,
            source=source, source_url=source_url, source_reliability=source_reliability,
            tags=tags or [], summary=summary, freshness=freshness)
        self._collected_data.append(collected)
        event_id = self.timeline.add_event(timestamp=timestamp, data=data, source=source,
            time_type=time_type, source_reliability=source_reliability, tags=tags or [], summary=summary)
        self._log_search(source, tags or [])
        return event_id

    def collect_batch(self, data_items: List[Dict]) -> List[str]:
        event_ids = []
        for item in data_items:
            event_id = self.collect(data=item.get("data"), source=item.get("source", ""),
                source_url=item.get("source_url", ""),
                source_reliability=item.get("source_reliability", SourceReliability.GENERAL),
                tags=item.get("tags", []), summary=item.get("summary", ""),
                timestamp=item.get("timestamp"), time_type=item.get("time_type"))
            event_ids.append(event_id)
        return event_ids

    def _extract_timestamp_from_data(self, data: Any) -> datetime:
        if isinstance(data, dict):
            for key in ["timestamp", "time", "date", "datetime", "时间", "日期"]:
                if key in data:
                    val = data[key]
                    if isinstance(val, datetime):
                        return val
                    if isinstance(val, str):
                        try:
                            return datetime.fromisoformat(val)
                        except ValueError:
                            pass
        return datetime.now()

    def _infer_time_type(self, timestamp: datetime) -> TimeType:
        now = datetime.now()
        if timestamp > now:
            return TimeType.PREDICTED
        diff = now - timestamp
        if diff < timedelta(hours=1):
            return TimeType.REAL_TIME
        return TimeType.HISTORICAL

    def _calculate_freshness(self, timestamp: datetime) -> FreshnessLevel:
        now = datetime.now()
        diff = now - timestamp
        if diff < timedelta(hours=1):
            return FreshnessLevel.FRESH
        elif diff < timedelta(days=1):
            return FreshnessLevel.RECENT
        elif diff < timedelta(days=7):
            return FreshnessLevel.STALE
        elif diff < timedelta(days=365):
            return FreshnessLevel.EXPIRED
        else:
            return FreshnessLevel.ARCHIVE

    def _log_search(self, source: str, tags: List[str]):
        self._search_history.append({"source": source, "tags": tags, "timestamp": datetime.now().isoformat()})

    def get_freshness_report(self) -> Dict[str, int]:
        report = {}
        for data in self._collected_data:
            level = data.freshness.value
            report[level] = report.get(level, 0) + 1
        return report

    def get_stale_data_warnings(self) -> List[Dict]:
        warnings = []
        for data in self._collected_data:
            if data.freshness in [FreshnessLevel.STALE, FreshnessLevel.EXPIRED]:
                warnings.append({"id": data.id, "source": data.source,
                    "timestamp": data.timestamp.isoformat(), "freshness": data.freshness.value,
                    "warning": f"数据可能过时，采集时间：{data.timestamp}"})
        return warnings

    def get_search_history(self) -> List[Dict]:
        return self._search_history

    def get_collected_data_summary(self) -> Dict:
        return {
            "total_collected": len(self._collected_data),
            "freshness_report": self.get_freshness_report(),
            "stale_warnings": len(self.get_stale_data_warnings()),
            "sources_used": len(set(d.source for d in self._collected_data if d.source)),
        }

    def design_search_query(self, topic: str, indicators: List[str], time_range: str = "") -> str:
        parts = [topic]
        if time_range:
            parts.append(time_range)
        parts.extend(indicators)
        return " ".join(parts)

    def merge_search_queries(self, topics: List[str], common_indicators: List[str]) -> str:
        topic_str = " ".join(topics)
        indicator_str = " ".join(common_indicators)
        return f"{topic_str} {indicator_str}"
