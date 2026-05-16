"""
ChronoVisor 基础功能测试
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import TimelineBase, AnalyzerEngine


def test_timeline_creation():
    """测试时间轴创建"""
    timeline = TimelineBase(title="测试研究")
    assert timeline.timeline.title == "测试研究"
    assert timeline.timeline is not None
    print("✅ 时间轴创建测试通过")


def test_event_addition():
    """测试事件添加"""
    timeline = TimelineBase(title="测试研究")
    timeline.add_event(
        timestamp=datetime(2024, 1, 1),
        data={"price": 100},
        source="测试来源",
        tags=["测试", "价格"],
        summary="测试事件"
    )
    events = timeline.timeline.get_all_events()
    assert len(events) == 1
    assert events[0].summary == "测试事件"
    print("✅ 事件添加测试通过")


def test_chapter_detection():
    """测试章节检测"""
    timeline = TimelineBase(title="测试研究")
    
    timeline.add_event(
        timestamp=datetime(2023, 1, 1),
        data={"event": "开始"},
        source="测试",
        tags=["测试"],
        summary="事件1"
    )
    timeline.add_event(
        timestamp=datetime(2025, 6, 1),
        data={"event": "中期"},
        source="测试",
        tags=["测试"],
        summary="事件2"
    )
    timeline.add_event(
        timestamp=datetime(2025, 8, 1),
        data={"event": "转折"},
        source="测试",
        tags=["转折"],
        summary="事件3"
    )
    timeline.add_event(
        timestamp=datetime(2026, 1, 1),
        data={"event": "结束"},
        source="测试",
        tags=["测试"],
        summary="事件4"
    )
    
    chapters = timeline.auto_detect_chapters(min_events=2)
    assert len(chapters) >= 1
    print(f"✅ 章节检测测试通过（检测到 {len(chapters)} 个章节）")


def test_pest_analysis():
    """测试 PEST 分析"""
    timeline = TimelineBase(title="测试研究")
    timeline.add_event(
        timestamp=datetime(2024, 1, 1),
        data={"type": "政策"},
        source="测试",
        tags=["政治", "政策"],
        summary="政策变化"
    )
    timeline.add_event(
        timestamp=datetime(2024, 6, 1),
        data={"type": "经济"},
        source="测试",
        tags=["经济", "GDP"],
        summary="经济增长"
    )
    
    analyzer = AnalyzerEngine(timeline)
    result = analyzer.analyze_pest()
    
    assert hasattr(result, 'political')
    assert hasattr(result, 'economic')
    print("✅ PEST 分析测试通过")


def test_swot_analysis():
    """测试 SWOT 分析"""
    timeline = TimelineBase(title="测试研究")
    timeline.add_event(
        timestamp=datetime(2024, 1, 1),
        data={"type": "优势"},
        source="测试",
        tags=["优势", "技术"],
        summary="技术优势"
    )
    timeline.add_event(
        timestamp=datetime(2024, 6, 1),
        data={"type": "机会"},
        source="测试",
        tags=["机会", "市场"],
        summary="市场机会"
    )
    
    analyzer = AnalyzerEngine(timeline)
    result = analyzer.analyze_swot()
    
    assert hasattr(result, 'strengths')
    assert hasattr(result, 'opportunities')
    print("✅ SWOT 分析测试通过")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*50)
    print("🧪 ChronoVisor 基础功能测试")
    print("="*50 + "\n")
    
    tests = [
        test_timeline_creation,
        test_event_addition,
        test_chapter_detection,
        test_pest_analysis,
        test_swot_analysis,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} 失败: {e}")
            failed += 1
    
    print("\n" + "="*50)
    print(f"📊 测试结果: {passed} 通过, {failed} 失败")
    print("="*50 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)