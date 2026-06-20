"""导航层专业测试套件
覆盖：跳转、搜索、时间范围过滤、搜索翻页、上下文、边界条件
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from src.core.timeline import TimelineBase, TimelineNavigator, TimelineEvent, TimeType

PASS = 0
FAIL = 0
ERRORS = []


def run_test(name, func):
    global PASS, FAIL, ERRORS
    try:
        func()
        PASS += 1
        print(f"  ✅ {name}")
    except AssertionError as e:
        FAIL += 1
        ERRORS.append(f"{name}: {e}")
        print(f"  ❌ {name}: {e}")
    except Exception as e:
        FAIL += 1
        ERRORS.append(f"{name}: {type(e).__name__}: {e}")
        print(f"  💥 {name}: {type(e).__name__}: {e}")


def _make_tb():
    """创建标准测试时间轴"""
    tb = TimelineBase(title="导航测试")
    tb.add_event(timestamp=datetime(2024, 1, 15), data={"cpi": 3.4}, summary="CPI上涨3.4%", tags=["通胀", "CPI"], source="劳工部")
    tb.add_event(timestamp=datetime(2024, 3, 1), data={}, summary="美联储加息25基点", tags=["加息", "美联储"], source="美联储")
    tb.add_event(timestamp=datetime(2024, 3, 15), data={}, summary="股市暴跌3%", tags=["股市", "下跌"], source="市场数据")
    tb.add_event(timestamp=datetime(2024, 6, 1), data={}, summary="降息预期升温", tags=["降息", "预期"], source="市场预期")
    tb.add_event(timestamp=datetime(2024, 9, 1), data={}, summary="央行降息", tags=["降息", "央行"], source="美联储")
    tb.add_event(timestamp=datetime(2024, 12, 1), data={}, summary="年终经济回顾", tags=["经济", "总结"], source="统计局")
    return tb


# ═══════════════════════════════════════════════════════
# 1. 基础跳转
# ═══════════════════════════════════════════════════════

def test_jump_to():
    tb = _make_tb()
    ctx = tb.jump_to(datetime(2024, 3, 1))
    assert ctx["current_position"] == "2024-03-01T00:00:00"


def test_jump_to_event():
    tb = _make_tb()
    events = tb.timeline.get_all_events()
    ctx = tb.jump_to_event(events[2].id)
    assert ctx is not None
    assert "2024-03-15" in ctx["current_position"]


def test_jump_to_nonexistent_event():
    tb = _make_tb()
    ctx = tb.jump_to_event("nonexist")
    assert ctx is None


def test_jump_to_start():
    tb = _make_tb()
    ctx = tb.navigator.jump_to_start()
    assert "2024-01-15" in ctx["current_position"]


def test_jump_to_end():
    tb = _make_tb()
    ctx = tb.navigator.jump_to_end()
    assert "2024-12-01" in ctx["current_position"]


def test_rewind():
    tb = _make_tb()
    tb.jump_to(datetime(2024, 6, 1))
    ctx = tb.navigator.rewind(timedelta(days=90))
    # 2024-06-01 - 90天 ≈ 2024-03-03
    assert "2024-03" in ctx["current_position"]


def test_fast_forward():
    tb = _make_tb()
    tb.jump_to(datetime(2024, 3, 1))
    ctx = tb.navigator.fast_forward(timedelta(days=90))
    # 2024-03-01 + 90天 ≈ 2024-05-30
    assert "2024-05" in ctx["current_position"]


# ═══════════════════════════════════════════════════════
# 2. 搜索
# ═══════════════════════════════════════════════════════

def test_search_keyword():
    tb = _make_tb()
    results = tb.search(keyword="CPI")
    assert len(results) == 1
    assert "CPI" in results[0]["summary"]


def test_search_keyword_no_match():
    tb = _make_tb()
    results = tb.search(keyword="不存在的关键词")
    assert len(results) == 0


def test_search_keyword_case_insensitive():
    tb = _make_tb()
    results = tb.search(keyword="cpi")
    assert len(results) == 1


def test_search_keyword_in_data():
    tb = _make_tb()
    results = tb.search(keyword="3.4")
    assert len(results) == 1


def test_search_tags():
    tb = _make_tb()
    results = tb.search(tags=["美联储"])
    assert len(results) == 1


def test_search_tags_or():
    tb = _make_tb()
    results = tb.search(tags=["CPI", "加息"])
    assert len(results) == 2


def test_search_source():
    tb = _make_tb()
    results = tb.search(source="美联储")
    assert len(results) == 2  # 加息 + 降息


def test_search_time_range():
    tb = _make_tb()
    results = tb.search(start_time=datetime(2024, 3, 1), end_time=datetime(2024, 6, 30))
    assert len(results) == 3  # 加息 + 暴跌 + 降息预期


def test_search_start_only():
    tb = _make_tb()
    results = tb.search(start_time=datetime(2024, 9, 1))
    assert len(results) == 2  # 降息 + 年终


def test_search_end_only():
    tb = _make_tb()
    results = tb.search(end_time=datetime(2024, 3, 1))
    assert len(results) == 2  # CPI + 加息


def test_search_time_type():
    tb = _make_tb()
    tb.add_event(timestamp=datetime(2025, 1, 1), data={}, summary="预测事件", time_type=TimeType.PREDICTED)
    results = tb.search(time_type=TimeType.PREDICTED)
    assert len(results) == 1


def test_search_combined():
    tb = _make_tb()
    results = tb.search(keyword="降息", start_time=datetime(2024, 6, 1))
    assert len(results) == 2  # 降息预期 + 降息


def test_search_returns_dicts():
    tb = _make_tb()
    results = tb.search(keyword="CPI")
    assert isinstance(results[0], dict)
    assert "summary" in results[0]
    assert "timestamp" in results[0]


def test_search_events_returns_events():
    tb = _make_tb()
    results = tb.search_events(keyword="CPI")
    assert isinstance(results[0], TimelineEvent)


# ═══════════════════════════════════════════════════════
# 3. 搜索翻页
# ═══════════════════════════════════════════════════════

def test_search_and_jump():
    tb = _make_tb()
    ctx = tb.search_and_jump(keyword="降息")
    assert ctx is not None
    assert "2024-06" in ctx["current_position"]  # 第一个降息相关


def test_search_and_jump_no_result():
    tb = _make_tb()
    ctx = tb.search_and_jump(keyword="不存在")
    assert ctx is None


def test_jump_to_next_result():
    tb = _make_tb()
    tb.search_and_jump(tags=["降息"])
    ctx = tb.jump_to_next_result()
    assert ctx is not None
    # 两个降息事件，跳到第二个
    assert tb.navigator.search_result_count == 2


def test_jump_to_prev_result():
    tb = _make_tb()
    tb.search_and_jump(tags=["降息"])
    tb.jump_to_next_result()
    ctx = tb.jump_to_prev_result()
    assert ctx is not None
    # 回到第一个
    assert "2024-06" in ctx["current_position"]


def test_next_wraps_around():
    tb = _make_tb()
    tb.search_and_jump(tags=["降息"])
    tb.jump_to_next_result()  # 到第2个
    ctx = tb.jump_to_next_result()  # 应回到第1个
    assert ctx is not None
    assert "2024-06" in ctx["current_position"]


def test_prev_wraps_around():
    tb = _make_tb()
    tb.search_and_jump(tags=["降息"])
    ctx = tb.jump_to_prev_result()  # 应到最后一个
    assert ctx is not None
    assert "2024-09" in ctx["current_position"]


def test_next_no_results():
    tb = _make_tb()
    ctx = tb.jump_to_next_result()
    assert ctx is None


def test_prev_no_results():
    tb = _make_tb()
    ctx = tb.jump_to_prev_result()
    assert ctx is None


def test_search_caches_results():
    tb = _make_tb()
    tb.search(tags=["降息"])
    assert tb.navigator.search_result_count == 2
    assert len(tb.navigator.last_search_results) == 2


def test_new_search_clears_cache():
    tb = _make_tb()
    tb.search(tags=["降息"])
    tb.search(tags=["CPI"])
    assert tb.navigator.search_result_count == 1


# ═══════════════════════════════════════════════════════
# 4. 时间范围过滤
# ═══════════════════════════════════════════════════════

def test_get_events_between():
    tb = _make_tb()
    events = tb.get_events_between(datetime(2024, 3, 1), datetime(2024, 6, 30))
    assert len(events) == 3


def test_get_events_between_inclusive():
    tb = _make_tb()
    events = tb.get_events_between(datetime(2024, 3, 1), datetime(2024, 3, 1))
    assert len(events) == 1


def test_get_events_between_empty():
    tb = _make_tb()
    events = tb.get_events_between(datetime(2025, 1, 1), datetime(2025, 12, 31))
    assert len(events) == 0


def test_get_events_before():
    tb = _make_tb()
    events = tb.get_events_before(datetime(2024, 3, 1))
    assert len(events) == 1  # 只有CPI


def test_get_events_before_default():
    tb = _make_tb()
    tb.jump_to(datetime(2024, 6, 1))
    events = tb.get_events_before()
    assert len(events) == 3  # CPI + 加息 + 暴跌


def test_get_events_after():
    tb = _make_tb()
    events = tb.get_events_after(datetime(2024, 6, 1))
    assert len(events) == 2  # 降息 + 年终


def test_get_events_after_default():
    tb = _make_tb()
    tb.jump_to(datetime(2024, 6, 1))
    events = tb.get_events_after()
    assert len(events) == 2


def test_get_events_around():
    tb = _make_tb()
    tb.jump_to(datetime(2024, 3, 1))
    events = tb.navigator.get_events_around(window=timedelta(days=30))
    # 3月1日 ±15天：加息(3/1) + 暴跌(3/15)
    assert len(events) == 2


# ═══════════════════════════════════════════════════════
# 5. 上下文
# ═══════════════════════════════════════════════════════

def test_get_context():
    tb = _make_tb()
    tb.jump_to(datetime(2024, 3, 15))
    ctx = tb.get_current_context()
    assert "current_position" in ctx
    assert "events" in ctx
    assert "navigation" in ctx


def test_context_navigation_info():
    tb = _make_tb()
    tb.jump_to(datetime(2024, 6, 1))
    ctx = tb.get_current_context()
    nav = ctx["navigation"]
    assert nav["events_before_current"] == 3
    assert nav["events_after_current"] == 2
    assert nav["total_events"] == 6


def test_context_search_info():
    tb = _make_tb()
    tb.search(tags=["降息"])
    ctx = tb.get_current_context()
    assert ctx["navigation"]["search_results_cached"] == 2


def test_context_chapter():
    tb = _make_tb()
    tb.auto_detect_chapters()
    tb.jump_to(datetime(2024, 3, 15))
    ctx = tb.get_current_context()
    # 章节检测可能有也可能没有，取决于数据
    # 但不应报错
    assert "current_chapter" in ctx


def test_pause_and_reflect():
    tb = _make_tb()
    ctx = tb.navigator.pause_and_reflect("当前形势如何？")
    assert ctx["question"] == "当前形势如何？"
    assert "events" in ctx


# ═══════════════════════════════════════════════════════
# 6. 边界条件
# ═══════════════════════════════════════════════════════

def test_empty_timeline_jump():
    tb = TimelineBase()
    ctx = tb.navigator.jump_to_start()
    assert ctx["navigation"]["total_events"] == 0


def test_empty_timeline_search():
    tb = TimelineBase()
    results = tb.search(keyword="test")
    assert results == []


def test_empty_timeline_range():
    tb = TimelineBase()
    events = tb.get_events_between(datetime(2024, 1, 1), datetime(2024, 12, 31))
    assert events == []


def test_single_event_navigation():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 6, 1), data={}, summary="唯一事件")
    ctx = tb.navigator.jump_to_start()
    assert "2024-06-01" in ctx["current_position"]
    ctx = tb.navigator.jump_to_end()
    assert "2024-06-01" in ctx["current_position"]


def test_search_after_update():
    tb = _make_tb()
    eid = tb.timeline.get_all_events()[0].id
    tb.update_event(eid, summary="PPI上涨2.1%", data={"ppi": 2.1}, tags=["通胀", "PPI"])
    results = tb.search(keyword="PPI")
    assert len(results) == 1
    results = tb.search(keyword="CPI")
    # data 里已无 cpi，summary 也改了，应搜不到
    assert len(results) == 0, f"预期0条，实际{len(results)}条"


def test_search_after_remove():
    tb = _make_tb()
    eid = tb.timeline.get_all_events()[0].id
    tb.remove_event(eid)
    results = tb.search(keyword="CPI")
    assert len(results) == 0
    assert tb.timeline.get_event_count() == 5


def test_search_after_add():
    tb = _make_tb()
    tb.add_event(timestamp=datetime(2025, 1, 1), data={}, summary="新年新事件", tags=["新年"])
    results = tb.search(keyword="新年")
    assert len(results) == 1


# ═══════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("🧭 ChronoVisor 导航层专业测试")
    print("=" * 55)

    sections = {
        "1. 基础跳转": [
            ("跳转到时间点", test_jump_to),
            ("跳转到事件", test_jump_to_event),
            ("跳转不存在事件", test_jump_to_nonexistent_event),
            ("跳转到起点", test_jump_to_start),
            ("跳转到终点", test_jump_to_end),
            ("后退", test_rewind),
            ("前进", test_fast_forward),
        ],
        "2. 搜索": [
            ("关键词搜索", test_search_keyword),
            ("无匹配搜索", test_search_keyword_no_match),
            ("大小写不敏感", test_search_keyword_case_insensitive),
            ("搜索data字段", test_search_keyword_in_data),
            ("标签搜索", test_search_tags),
            ("多标签OR", test_search_tags_or),
            ("来源搜索", test_search_source),
            ("时间范围搜索", test_search_time_range),
            ("仅开始时间", test_search_start_only),
            ("仅结束时间", test_search_end_only),
            ("时间类型搜索", test_search_time_type),
            ("组合搜索", test_search_combined),
            ("搜索返回字典", test_search_returns_dicts),
            ("search_events返回对象", test_search_events_returns_events),
        ],
        "3. 搜索翻页": [
            ("搜索并跳转", test_search_and_jump),
            ("无结果跳转", test_search_and_jump_no_result),
            ("下一个结果", test_jump_to_next_result),
            ("上一个结果", test_jump_to_prev_result),
            ("下一个循环", test_next_wraps_around),
            ("上一个循环", test_prev_wraps_around),
            ("无结果时next", test_next_no_results),
            ("无结果时prev", test_prev_no_results),
            ("搜索缓存", test_search_caches_results),
            ("新搜索覆盖缓存", test_new_search_clears_cache),
        ],
        "4. 时间范围过滤": [
            ("时间区间查询", test_get_events_between),
            ("区间包含边界", test_get_events_between_inclusive),
            ("空区间", test_get_events_between_empty),
            ("之前事件", test_get_events_before),
            ("之前事件(默认位置)", test_get_events_before_default),
            ("之后事件", test_get_events_after),
            ("之后事件(默认位置)", test_get_events_after_default),
            ("周围事件", test_get_events_around),
        ],
        "5. 上下文": [
            ("获取上下文", test_get_context),
            ("导航信息", test_context_navigation_info),
            ("搜索信息", test_context_search_info),
            ("章节信息", test_context_chapter),
            ("暂停反思", test_pause_and_reflect),
        ],
        "6. 边界条件": [
            ("空时间轴跳转", test_empty_timeline_jump),
            ("空时间轴搜索", test_empty_timeline_search),
            ("空时间轴范围", test_empty_timeline_range),
            ("单事件导航", test_single_event_navigation),
            ("更新后搜索", test_search_after_update),
            ("删除后搜索", test_search_after_remove),
            ("添加后搜索", test_search_after_add),
        ],
    }

    total = sum(len(tests) for tests in sections.values())
    print(f"\n共 {total} 个测试用例\n")

    for section_name, tests in sections.items():
        print(f"  {section_name}")
        for name, func in tests:
            run_test(name, func)
        print()

    print("=" * 55)
    if FAIL == 0:
        print(f"🎉 全部通过: {PASS}/{total}")
    else:
        print(f"⚠️  通过 {PASS}, 失败 {FAIL}")
        print("\n失败详情:")
        for err in ERRORS:
            print(f"  • {err}")
    print("=" * 55)
