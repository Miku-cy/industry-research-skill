from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from .timeline import TimelineBase, TimelineEvent, TimeType, SourceReliability, FreshnessLevel


@dataclass
class ValidationResult:
    event_id: str = ""
    is_valid: bool = True
    is_fresh: bool = True
    freshness: FreshnessLevel = FreshnessLevel.RECENT
    timestamp: Optional[datetime] = None
    data: Any = None
    source_count: int = 1
    sources: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 1.0
    recommendation: str = ""


class RealTimeValidator:
    def __init__(self, timeline_base: TimelineBase):
        self.timeline = timeline_base
        self._validation_history: List[ValidationResult] = []

    def validate_event(self, event: TimelineEvent) -> ValidationResult:
        result = ValidationResult(event_id=event.id, timestamp=event.timestamp,
            data=event.data, sources=[event.source] if event.source else [])
        result = self._check_freshness(result, event)
        result = self._check_reliability(result, event)
        result = self._generate_warnings(result, event)
        result.is_valid = len(result.conflicts) == 0
        result.confidence = self._calculate_confidence(result, event)
        self._validation_history.append(result)
        return result

    def validate_all(self) -> List[ValidationResult]:
        results = []
        events = self.timeline.timeline.get_all_events()
        for event in events:
            results.append(self.validate_event(event))
        return results

    def validate_at_time(self, target_time: datetime) -> Dict:
        events = self.timeline.timeline.get_events_around(target_time, timedelta(days=30))
        results = []
        for event in events:
            result = self.validate_event(event)
            results.append({
                "event_id": result.event_id, "is_valid": result.is_valid,
                "is_fresh": result.is_fresh, "freshness": result.freshness.value,
                "confidence": result.confidence, "warnings": result.warnings,
                "conflicts": result.conflicts,
            })
        stale_count = sum(1 for r in results if not r.get("is_fresh", True))
        invalid_count = sum(1 for r in results if not r.get("is_valid", True))
        return {
            "target_time": target_time.isoformat(),
            "total_events": len(results),
            "valid_events": len(results) - invalid_count,
            "stale_events": stale_count,
            "overall_confidence": 1.0 - (invalid_count + stale_count * 0.5) / max(len(results), 1),
            "results": results,
        }

    def cross_validate(self, event_a: TimelineEvent, event_b: TimelineEvent) -> Dict:
        if event_a.timestamp > event_b.timestamp:
            event_a, event_b = event_b, event_a
        time_gap = event_b.timestamp - event_a.timestamp
        return {
            "event_a": {"id": event_a.id, "timestamp": event_a.timestamp.isoformat()},
            "event_b": {"id": event_b.id, "timestamp": event_b.timestamp.isoformat()},
            "time_gap": str(time_gap),
            "time_order_valid": event_a.timestamp <= event_b.timestamp,
            "causality_possible": event_a.timestamp < event_b.timestamp,
        }

    def _check_freshness(self, result: ValidationResult, event: TimelineEvent) -> ValidationResult:
        now = datetime.now()
        diff = now - event.timestamp
        if diff < timedelta(hours=1):
            result.freshness = FreshnessLevel.FRESH
        elif diff < timedelta(days=1):
            result.freshness = FreshnessLevel.RECENT
        elif diff < timedelta(days=7):
            result.freshness = FreshnessLevel.STALE
            result.is_fresh = False
            result.warnings.append(f"数据已过期 {diff.days} 天")
        elif diff < timedelta(days=365):
            result.freshness = FreshnessLevel.EXPIRED
            result.is_fresh = False
            result.warnings.append(f"数据严重过期 {diff.days} 天")
        else:
            result.freshness = FreshnessLevel.ARCHIVE
            result.is_fresh = False
        return result

    def _check_reliability(self, result: ValidationResult, event: TimelineEvent) -> ValidationResult:
        if event.source_reliability == SourceReliability.UNVERIFIED:
            result.warnings.append("来源可靠性低，需要更多验证")
            result.confidence *= 0.5
        elif event.source_reliability == SourceReliability.GENERAL:
            result.warnings.append("来源为一般来源，建议交叉验证")
            result.confidence *= 0.7
        elif event.source_reliability == SourceReliability.AUTHORITATIVE_MEDIA:
            result.confidence *= 0.85
        return result

    def _generate_warnings(self, result: ValidationResult, event: TimelineEvent) -> ValidationResult:
        if event.time_type == TimeType.REAL_TIME and not result.is_fresh:
            result.conflicts.append(
                f"实时数据不新鲜：标记为实时但已过去 "
                f"{(datetime.now() - event.timestamp).total_seconds() / 3600:.1f} 小时")
        if result.source_count < 2:
            result.warnings.append("只有一个数据源，建议增加交叉验证来源")
        return result

    def _calculate_confidence(self, result: ValidationResult, event: TimelineEvent) -> float:
        confidence = 1.0
        confidence -= len(result.conflicts) * 0.2
        confidence -= len(result.warnings) * 0.1
        if event.source_reliability == SourceReliability.OFFICIAL:
            confidence += 0.1
        if result.source_count >= 3:
            confidence += 0.1
        return max(0.0, min(1.0, confidence))

    def get_validation_summary(self) -> Dict:
        if not self._validation_history:
            return {"message": "尚未进行验证"}
        valid_count = sum(1 for r in self._validation_history if r.is_valid)
        fresh_count = sum(1 for r in self._validation_history if r.is_fresh)
        total = len(self._validation_history)
        return {
            "total_validated": total, "valid_count": valid_count,
            "invalid_count": total - valid_count, "fresh_count": fresh_count,
            "stale_count": total - fresh_count,
            "overall_confidence": sum(r.confidence for r in self._validation_history) / max(total, 1),
            "critical_warnings": [{"event_id": r.event_id, "conflicts": r.conflicts}
                for r in self._validation_history if r.conflicts],
        }

    def compare_timeliness(self, event_a: TimelineEvent, event_b: TimelineEvent) -> Dict:
        now = datetime.now()
        diff_a = now - event_a.timestamp
        diff_b = now - event_b.timestamp
        fresher = "a" if diff_a < diff_b else "b"
        return {
            "event_a": {"id": event_a.id, "age": str(diff_a), "source": event_a.source},
            "event_b": {"id": event_b.id, "age": str(diff_b), "source": event_b.source},
            "fresher": fresher,
            "recommendation": f"建议使用事件 {'A' if fresher == 'a' else 'B'} 的数据，更新 {abs(diff_a - diff_b)}",
        }
