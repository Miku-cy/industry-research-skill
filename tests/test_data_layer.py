"""数据层专业测试套件
覆盖：数据校验、去重、增删改、导入导出、搜索、边界条件、异常处理
"""
import sys, os, json, csv, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from src.core.timeline import (
    Timeline, TimelineEvent, TimelineBase, Chapter,
    ValidationError, DuplicateError, validate_event_data,
    TimeType, SourceReliability,
)

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


# ═══════════════════════════════════════════════════════
# 1. 数据校验
# ═══════════════════════════════════════════════════════

def test_validate_normal():
    ok, errs = validate_event_data(datetime(2024, 6, 15), "美联储加息", ["加息"], "美联储")
    assert ok is True
    assert errs == []


def test_validate_empty_timestamp():
    ok, errs = validate_event_data(None, "test", [], "")
    assert ok is False
    assert "时间戳不能为空" in errs[0]


def test_validate_empty_summary():
    ok, errs = validate_event_data(datetime.now(), "", [], "")
    assert ok is False
    assert "摘要不能为空" in errs[0]


def test_validate_whitespace_summary():
    ok, errs = validate_event_data(datetime.now(), "   ", [], "")
    assert ok is False


def test_validate_old_year():
    ok, errs = validate_event_data(datetime(1800, 1, 1), "test", [], "")
    assert ok is False
    assert "1800" in errs[0]


def test_validate_future_far():
    ok, errs = validate_event_data(datetime(2099, 1, 1), "test", [], "")
    assert ok is False
    assert "未来" in errs[0]


def test_validate_future_ok():
    ok, errs = validate_event_data(datetime.now() + timedelta(days=30), "test", [], "")
    assert ok is True


def test_validate_long_summary():
    ok, errs = validate_event_data(datetime.now(), "x" * 2001, [], "")
    assert ok is False
    assert "过长" in errs[0]


def test_validate_summary_at_limit():
    ok, errs = validate_event_data(datetime.now(), "x" * 2000, [], "")
    assert ok is True


def test_validate_empty_tag():
    ok, errs = validate_event_data(datetime.now(), "test", [""], "")
    assert ok is False
    assert "标签不能为空" in errs[0]


def test_validate_long_tag():
    ok, errs = validate_event_data(datetime.now(), "test", ["x" * 51], "")
    assert ok is False
    assert "标签过长" in errs[0]


def test_validate_tag_at_limit():
    ok, errs = validate_event_data(datetime.now(), "test", ["x" * 50], "")
    assert ok is True


def test_validate_long_source():
    ok, errs = validate_event_data(datetime.now(), "test", [], "x" * 201)
    assert ok is False
    assert "来源名称过长" in errs[0]


# ═══════════════════════════════════════════════════════
# 2. 事件去重
# ═══════════════════════════════════════════════════════

def test_dedup_same_event():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A", tags=["t1"])
    try:
        tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A", tags=["t2"])
        assert False, "应该抛 DuplicateError"
    except DuplicateError:
        pass
    assert tb.timeline.get_event_count() == 1


def test_dedup_different_summary():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A")
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件B")
    assert tb.timeline.get_event_count() == 2


def test_dedup_different_time():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A")
    tb.add_event(timestamp=datetime(2024, 1, 2), data={}, summary="事件A")
    assert tb.timeline.get_event_count() == 2


def test_dedup_different_source():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A", source="来源1")
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A", source="来源2")
    assert tb.timeline.get_event_count() == 2


def test_dedup_skip_false():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A")
    tb.timeline.add_event(
        TimelineEvent(timestamp=datetime(2024, 1, 1), summary="事件A"),
        skip_duplicate=False,
    )
    assert tb.timeline.get_event_count() == 2


def test_dedup_fingerprint_consistency():
    e1 = TimelineEvent(timestamp=datetime(2024, 1, 1), summary="test", source="src")
    e2 = TimelineEvent(timestamp=datetime(2024, 1, 1), summary="test", source="src")
    assert e1.fingerprint() == e2.fingerprint()


def test_dedup_after_remove():
    tb = TimelineBase()
    eid = tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A")
    tb.remove_event(eid)
    # 删除后应能重新添加
    eid2 = tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A")
    assert tb.timeline.get_event_count() == 1


def test_dedup_after_update():
    tb = TimelineBase()
    eid = tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A", source="src1")
    tb.update_event(eid, source="src2")
    # 更新后旧指纹释放，新指纹生效
    try:
        tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="事件A", source="src1")
        assert tb.timeline.get_event_count() == 2  # 旧的可以再加
    except DuplicateError:
        assert False, "旧指纹应该已释放"


# ═══════════════════════════════════════════════════════
# 3. 事件增删改
# ═══════════════════════════════════════════════════════

def test_add_event():
    tb = TimelineBase()
    eid = tb.add_event(timestamp=datetime(2024, 1, 1), data={"v": 1}, summary="test")
    assert len(eid) == 8
    e = tb.timeline.get_event(eid)
    assert e.summary == "test"
    assert e.data == {"v": 1}


def test_add_event_validation_fail():
    tb = TimelineBase()
    try:
        tb.add_event(timestamp=None, data={}, summary="test")
        assert False, "应该抛 ValidationError"
    except ValidationError:
        pass


def test_add_events_batch():
    tb = TimelineBase()
    ids = tb.add_events_batch([
        {"timestamp": datetime(2024, 1, 1), "summary": "A"},
        {"timestamp": datetime(2024, 1, 2), "summary": "B"},
        {"timestamp": datetime(2024, 1, 3), "summary": "C"},
    ])
    assert len(ids) == 3
    assert tb.timeline.get_event_count() == 3


def test_update_event():
    tb = TimelineBase()
    eid = tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="old", tags=["old"])
    ok = tb.update_event(eid, summary="new", tags=["new"])
    assert ok is True
    e = tb.timeline.get_event(eid)
    assert e.summary == "new"
    assert e.tags == ["new"]


def test_update_nonexistent():
    tb = TimelineBase()
    ok = tb.update_event("nonexist", summary="x")
    assert ok is False


def test_update_invalid_field():
    tb = TimelineBase()
    eid = tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="test")
    try:
        tb.update_event(eid, nonexistent_field="x")
        assert False, "应该抛 ValueError"
    except ValueError as e:
        assert "没有字段" in str(e)


def test_remove_event():
    tb = TimelineBase()
    eid = tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="test")
    ok = tb.remove_event(eid)
    assert ok is True
    assert tb.timeline.get_event(eid) is None
    assert tb.timeline.get_event_count() == 0


def test_remove_nonexistent():
    tb = TimelineBase()
    ok = tb.remove_event("nonexist")
    assert ok is False


def test_remove_from_chapter():
    tb = TimelineBase()
    eid = tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="test")
    chapter = Chapter(
        title="ch1", start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 31), event_ids=[eid],
    )
    tb.timeline.add_chapter(chapter)
    tb.remove_event(eid)
    assert eid not in chapter.event_ids


def test_chronological_order():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 3, 1), data={}, summary="C")
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="A")
    tb.add_event(timestamp=datetime(2024, 2, 1), data={}, summary="B")
    events = tb.timeline.get_all_events()
    assert events[0].summary == "A"
    assert events[1].summary == "B"
    assert events[2].summary == "C"


# ═══════════════════════════════════════════════════════
# 4. CSV 导入导出
# ═══════════════════════════════════════════════════════

def _make_csv(rows):
    """创建临时 CSV 文件"""
    path = tempfile.mktemp(suffix=".csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "summary", "tags", "source", "time_type", "source_reliability", "data"])
        for row in rows:
            writer.writerow(row)
    return path


def test_csv_export_import_roundtrip():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 15), data={"cpi": 3.4}, summary="CPI上涨", tags=["通胀"], source="劳工部")
    tb.add_event(timestamp=datetime(2024, 3, 1), data={}, summary="加息", tags=["美联储"], source="美联储")

    path = tempfile.mktemp(suffix=".csv")
    tb.export_csv(path)

    tb2 = TimelineBase()
    result = tb2.import_csv(path)
    assert result["imported"] == 2
    assert result["errors"] == []
    assert tb2.timeline.get_event_count() == 2

    events = tb2.timeline.get_all_events()
    assert events[0].summary == "CPI上涨"
    assert events[1].tags == ["美联储"]
    os.unlink(path)


def test_csv_dedup_on_import():
    csv_path = _make_csv([
        ["2024-01-01", "事件A", "tag1", "来源1", "historical", "3", ""],
        ["2024-02-01", "事件B", "tag2", "来源2", "historical", "2", ""],
    ])
    tb = TimelineBase()
    tb.import_csv(csv_path)
    result = tb.import_csv(csv_path)
    assert result["imported"] == 0
    assert result["skipped"] == 2
    assert tb.timeline.get_event_count() == 2
    os.unlink(csv_path)


def test_csv_skip_duplicate_false():
    csv_path = _make_csv([
        ["2024-01-01", "事件A", "", "", "historical", "2", ""],
    ])
    tb = TimelineBase()
    tb.import_csv(csv_path, skip_duplicate=False)
    tb.import_csv(csv_path, skip_duplicate=False)
    assert tb.timeline.get_event_count() == 2
    os.unlink(csv_path)


def test_csv_validation_errors():
    csv_path = _make_csv([
        ["", "空时间", "", "", "historical", "2", ""],
        ["2024-01-01", "", "", "", "historical", "2", ""],
        ["bad-date", "test", "", "", "historical", "2", ""],
        ["2024-01-01", "正常事件", "", "", "historical", "2", ""],
    ])
    tb = TimelineBase()
    result = tb.import_csv(csv_path)
    assert result["imported"] == 1
    assert len(result["errors"]) == 3
    os.unlink(csv_path)


def test_csv_tags_parsing():
    csv_path = _make_csv([
        ["2024-01-01", "test", "tag1,tag2,tag3", "", "historical", "2", ""],
    ])
    tb = TimelineBase()
    tb.import_csv(csv_path)
    e = tb.timeline.get_all_events()[0]
    assert e.tags == ["tag1", "tag2", "tag3"]
    os.unlink(csv_path)


def test_csv_empty_tags():
    csv_path = _make_csv([
        ["2024-01-01", "test", "", "", "historical", "2", ""],
    ])
    tb = TimelineBase()
    tb.import_csv(csv_path)
    e = tb.timeline.get_all_events()[0]
    assert e.tags == []
    os.unlink(csv_path)


def test_csv_data_json():
    csv_path = _make_csv([
        ["2024-01-01", "test", "", "", "historical", "2", '{"price": 100}'],
    ])
    tb = TimelineBase()
    tb.import_csv(csv_path)
    e = tb.timeline.get_all_events()[0]
    assert e.data == {"price": 100}
    os.unlink(csv_path)


def test_csv_time_type_mapping():
    csv_path = _make_csv([
        ["2024-01-01", "hist", "", "", "historical", "2", ""],
        ["2024-02-01", "rt", "", "", "real-time", "5", ""],
        ["2024-03-01", "pred", "", "", "predicted", "1", ""],
    ])
    tb = TimelineBase()
    tb.import_csv(csv_path)
    events = tb.timeline.get_all_events()
    assert events[0].time_type == TimeType.HISTORICAL
    assert events[1].time_type == TimeType.REAL_TIME
    assert events[2].time_type == TimeType.PREDICTED
    os.unlink(csv_path)


def test_csv_reliability_mapping():
    csv_path = _make_csv([
        ["2024-01-01", "test", "", "", "historical", "5", ""],
    ])
    tb = TimelineBase()
    tb.import_csv(csv_path)
    e = tb.timeline.get_all_events()[0]
    assert e.source_reliability == SourceReliability.OFFICIAL
    os.unlink(csv_path)


def test_csv_bom_handling():
    """utf-8-sig 编码应正确处理 BOM"""
    path = tempfile.mktemp(suffix=".csv")
    with open(path, "wb") as f:
        f.write(b'\xef\xbb\xbftimestamp,summary,tags,source,time_type,source_reliability,data\r\n')
        f.write(b'2024-01-01,test,,,historical,2,\r\n')
    tb = TimelineBase()
    result = tb.import_csv(path)
    assert result["imported"] == 1
    os.unlink(path)


# ═══════════════════════════════════════════════════════
# 5. JSON 导入导出
# ═══════════════════════════════════════════════════════

def test_json_export_import_roundtrip():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={"v": 1}, summary="A", tags=["t1"])
    tb.add_event(timestamp=datetime(2024, 2, 1), data={}, summary="B")

    path = tempfile.mktemp(suffix=".json")
    tb.export_json(path)

    tb2 = TimelineBase()
    result = tb2.import_json(path)
    assert result["imported"] == 2
    assert tb2.timeline.get_event_count() == 2
    os.unlink(path)


def test_json_list_format():
    """纯数组格式也能导入"""
    path = tempfile.mktemp(suffix=".json")
    with open(path, "w") as f:
        json.dump([
            {"timestamp": "2024-01-01", "summary": "A"},
            {"timestamp": "2024-02-01", "summary": "B"},
        ], f)
    tb = TimelineBase()
    result = tb.import_json(path)
    assert result["imported"] == 2
    os.unlink(path)


def test_json_invalid_format():
    path = tempfile.mktemp(suffix=".json")
    with open(path, "w") as f:
        json.dump({"invalid": "format"}, f)
    tb = TimelineBase()
    result = tb.import_json(path)
    assert result["imported"] == 0
    assert len(result["errors"]) == 1
    os.unlink(path)


def test_json_dedup():
    path = tempfile.mktemp(suffix=".json")
    with open(path, "w") as f:
        json.dump([{"timestamp": "2024-01-01", "summary": "A"}], f)
    tb = TimelineBase()
    tb.import_json(path)
    result = tb.import_json(path)
    assert result["imported"] == 0
    assert result["skipped"] == 1
    os.unlink(path)


# ═══════════════════════════════════════════════════════
# 6. 搜索
# ═══════════════════════════════════════════════════════

def _make_search_tb():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="CPI上涨3.4%", tags=["通胀", "CPI"], source="劳工部")
    tb.add_event(timestamp=datetime(2024, 3, 1), data={}, summary="美联储加息", tags=["加息", "美联储"], source="美联储")
    tb.add_event(timestamp=datetime(2024, 6, 1), data={}, summary="股市暴跌", tags=["股市", "下跌"], source="市场")
    return tb


def test_search_keyword():
    tb = _make_search_tb()
    assert len(tb.search_events(keyword="CPI")) == 1
    assert len(tb.search_events(keyword="加息")) == 1
    assert len(tb.search_events(keyword="不存在")) == 0


def test_search_keyword_case_insensitive():
    tb = _make_search_tb()
    assert len(tb.search_events(keyword="cpi")) == 1


def test_search_tags():
    tb = _make_search_tb()
    assert len(tb.search_events(tags=["美联储"])) == 1
    assert len(tb.search_events(tags=["通胀"])) == 1
    assert len(tb.search_events(tags=["不存在"])) == 0


def test_search_multi_tags():
    """多标签是 OR 关系"""
    tb = _make_search_tb()
    results = tb.search_events(tags=["CPI", "加息"])
    assert len(results) == 2


def test_search_source():
    tb = _make_search_tb()
    assert len(tb.search_events(source="美联储")) == 1
    assert len(tb.search_events(source="市场")) == 1


def test_search_time_range():
    tb = _make_search_tb()
    results = tb.search_events(start_time=datetime(2024, 2, 1))
    assert len(results) == 2  # 加息 + 暴跌

    results = tb.search_events(end_time=datetime(2024, 2, 1))
    assert len(results) == 1  # CPI


def test_search_combined():
    tb = _make_search_tb()
    results = tb.search_events(keyword="加息", start_time=datetime(2024, 2, 1))
    assert len(results) == 1


def test_search_time_type():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="历史", time_type=TimeType.HISTORICAL)
    tb.add_event(timestamp=datetime(2024, 2, 1), data={}, summary="预测", time_type=TimeType.PREDICTED)
    assert len(tb.search_events(time_type=TimeType.PREDICTED)) == 1
    assert len(tb.search_events(time_type=TimeType.HISTORICAL)) == 1


# ═══════════════════════════════════════════════════════
# 7. 持久化
# ═══════════════════════════════════════════════════════

def test_save_load_roundtrip():
    tb = TimelineBase(title="持久化测试")
    tb.add_event(timestamp=datetime(2024, 1, 1), data={"v": 1}, summary="A", tags=["t1"])
    tb.add_event(timestamp=datetime(2024, 2, 1), data={}, summary="B")
    tb.timeline.start_time = datetime(2024, 1, 1)
    tb.timeline.end_time = datetime(2024, 12, 31)

    path = tempfile.mktemp(suffix=".json")
    tb.save(path)

    tb2 = TimelineBase.load(path)
    assert tb2.timeline.title == "持久化测试"
    assert tb2.timeline.get_event_count() == 2
    assert tb2.timeline.start_time == datetime(2024, 1, 1)
    assert tb2.timeline.get_all_events()[0].data == {"v": 1}
    os.unlink(path)


def test_save_load_empty():
    tb = TimelineBase(title="空")
    path = tempfile.mktemp(suffix=".json")
    tb.save(path)
    tb2 = TimelineBase.load(path)
    assert tb2.timeline.get_event_count() == 0
    os.unlink(path)


# ═══════════════════════════════════════════════════════
# 8. 边界条件
# ═══════════════════════════════════════════════════════

def test_empty_timeline():
    tb = TimelineBase()
    assert tb.timeline.get_event_count() == 0
    assert tb.timeline.get_all_events() == []
    assert tb.search_events(keyword="x") == []


def test_single_event():
    tb = TimelineBase()
    eid = tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="only")
    assert tb.timeline.get_event_count() == 1
    assert tb.timeline.get_event(eid).summary == "only"


def test_large_batch():
    tb = TimelineBase()
    for i in range(100):
        tb.add_event(timestamp=datetime(2024, 1, 1) + timedelta(days=i), data={}, summary=f"事件{i}")
    assert tb.timeline.get_event_count() == 100
    events = tb.timeline.get_all_events()
    assert events[0].summary == "事件0"
    assert events[-1].summary == "事件99"


def test_special_characters():
    tb = TimelineBase()
    eid = tb.add_event(
        timestamp=datetime(2024, 1, 1), data={},
        summary='包含"引号"、逗号,、换行\n、中文、emoji🎉',
        tags=['标签,带逗号', '标签"带引号'],
    )
    # CSV 导出导入不应丢失
    path = tempfile.mktemp(suffix=".csv")
    tb.export_csv(path)
    tb2 = TimelineBase()
    tb2.import_csv(path)
    e = tb2.timeline.get_all_events()[0]
    assert "引号" in e.summary
    assert "🎉" in e.summary
    os.unlink(path)


def test_unicode_tags():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="test", tags=["宏观经济", "货币政策", "美联储"])
    path = tempfile.mktemp(suffix=".csv")
    tb.export_csv(path)
    tb2 = TimelineBase()
    tb2.import_csv(path)
    assert tb2.timeline.get_all_events()[0].tags == ["宏观经济", "货币政策", "美联储"]
    os.unlink(path)


# ═══════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("🔬 ChronoVisor 数据层专业测试")
    print("=" * 55)

    sections = {
        "1. 数据校验": [
            ("正常数据通过", test_validate_normal),
            ("空时间戳拦截", test_validate_empty_timestamp),
            ("空摘要拦截", test_validate_empty_summary),
            ("纯空格摘要拦截", test_validate_whitespace_summary),
            ("1800年拦截", test_validate_old_year),
            ("远未来拦截", test_validate_future_far),
            ("近未来通过", test_validate_future_ok),
            ("超长摘要拦截", test_validate_long_summary),
            ("2000字摘要通过", test_validate_summary_at_limit),
            ("空标签拦截", test_validate_empty_tag),
            ("超长标签拦截", test_validate_long_tag),
            ("50字标签通过", test_validate_tag_at_limit),
            ("超长来源拦截", test_validate_long_source),
        ],
        "2. 事件去重": [
            ("相同事件去重", test_dedup_same_event),
            ("不同摘要不去重", test_dedup_different_summary),
            ("不同时间不去重", test_dedup_different_time),
            ("不同来源不去重", test_dedup_different_source),
            ("skip_duplicate=False", test_dedup_skip_false),
            ("指纹一致性", test_dedup_fingerprint_consistency),
            ("删除后可重新添加", test_dedup_after_remove),
            ("更新后指纹释放", test_dedup_after_update),
        ],
        "3. 增删改": [
            ("添加事件", test_add_event),
            ("校验失败拦截", test_add_event_validation_fail),
            ("批量添加", test_add_events_batch),
            ("更新事件", test_update_event),
            ("更新不存在事件", test_update_nonexistent),
            ("更新无效字段", test_update_invalid_field),
            ("删除事件", test_remove_event),
            ("删除不存在事件", test_remove_nonexistent),
            ("删除后清理章节引用", test_remove_from_chapter),
            ("时间排序", test_chronological_order),
        ],
        "4. CSV 导入导出": [
            ("导出导入往返", test_csv_export_import_roundtrip),
            ("导入去重", test_csv_dedup_on_import),
            ("skip_duplicate=False", test_csv_skip_duplicate_false),
            ("校验错误处理", test_csv_validation_errors),
            ("标签解析", test_csv_tags_parsing),
            ("空标签处理", test_csv_empty_tags),
            ("JSON数据字段", test_csv_data_json),
            ("时间类型映射", test_csv_time_type_mapping),
            ("可靠性映射", test_csv_reliability_mapping),
            ("BOM处理", test_csv_bom_handling),
        ],
        "5. JSON 导入导出": [
            ("导出导入往返", test_json_export_import_roundtrip),
            ("纯数组格式", test_json_list_format),
            ("无效格式处理", test_json_invalid_format),
            ("JSON去重", test_json_dedup),
        ],
        "6. 搜索": [
            ("关键词搜索", test_search_keyword),
            ("大小写不敏感", test_search_keyword_case_insensitive),
            ("标签搜索", test_search_tags),
            ("多标签OR", test_search_multi_tags),
            ("来源搜索", test_search_source),
            ("时间范围搜索", test_search_time_range),
            ("组合搜索", test_search_combined),
            ("时间类型搜索", test_search_time_type),
        ],
        "7. 持久化": [
            ("保存加载往返", test_save_load_roundtrip),
            ("空时间轴保存", test_save_load_empty),
        ],
        "8. 边界条件": [
            ("空时间轴", test_empty_timeline),
            ("单事件", test_single_event),
            ("100事件批量", test_large_batch),
            ("特殊字符CSV", test_special_characters),
            ("中文标签", test_unicode_tags),
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
