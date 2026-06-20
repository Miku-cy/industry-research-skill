"""因果网络专业测试套件
覆盖：网络构建、正向/反向遍历、子网络、导出格式、边界条件
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from src import TimelineBase, AnalyzerEngine, CausalNetwork, CausalChain
from src.core.timeline import TimelineEvent

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


def _make_econ_tb():
    """构造经济因果链时间轴（使用匹配因果概念图谱的事件）"""
    tb = TimelineBase(title="经济因果链")
    tb.add_event(timestamp=datetime(2024, 1, 15), data={}, summary="CPI通胀上涨3.4%", tags=["通胀", "CPI"])
    tb.add_event(timestamp=datetime(2024, 3, 1), data={}, summary="美联储加息25基点", tags=["加息", "美联储"])
    tb.add_event(timestamp=datetime(2024, 3, 15), data={}, summary="股市暴跌3%", tags=["下跌", "股市"])
    tb.add_event(timestamp=datetime(2024, 6, 1), data={}, summary="降息预期升温", tags=["降息", "预期"])
    tb.add_event(timestamp=datetime(2024, 9, 1), data={}, summary="央行降息", tags=["降息", "央行"])
    tb.add_event(timestamp=datetime(2024, 12, 1), data={}, summary="黄金价格上涨", tags=["黄金", "金价"])
    return tb


def _make_chain(cause, effect, confidence=0.5):
    return CausalChain(
        cause_event=cause,
        effect_event=effect,
        time_gap=effect.timestamp - cause.timestamp,
        confidence=confidence,
        description=f"{cause.summary} → {effect.summary}",
    )


def _make_manual_network():
    """手动构建一个已知结构的网络：A→B→D, A→C→D"""
    a = TimelineEvent(timestamp=datetime(2024, 1, 1), summary="通胀CPI上涨", id="evtA")
    b = TimelineEvent(timestamp=datetime(2024, 3, 1), summary="美联储加息", id="evtB")
    c = TimelineEvent(timestamp=datetime(2024, 5, 1), summary="降息预期", id="evtC")
    d = TimelineEvent(timestamp=datetime(2024, 9, 1), summary="央行降息", id="evtD")

    net = CausalNetwork(title="测试网络")
    net.add_chain(_make_chain(a, b, 0.7))
    net.add_chain(_make_chain(a, c, 0.6))
    net.add_chain(_make_chain(b, d, 0.5))
    net.add_chain(_make_chain(c, d, 0.5))
    return net, a, b, c, d


# ═══════════════════════════════════════════════════════
# 1. 网络构建
# ═══════════════════════════════════════════════════════

def test_build_network():
    tb = _make_econ_tb()
    analyzer = AnalyzerEngine(tb)
    network = analyzer.build_causal_network()
    assert network.event_count > 0, f"事件数={network.event_count}"
    assert network.chain_count > 0, f"链数={network.chain_count}"


def test_build_network_min_confidence():
    tb = _make_econ_tb()
    analyzer = AnalyzerEngine(tb)
    net_low = analyzer.build_causal_network(min_confidence=0.1)
    net_high = analyzer.build_causal_network(min_confidence=0.6)
    assert net_low.chain_count >= net_high.chain_count


def test_empty_timeline_network():
    tb = TimelineBase()
    analyzer = AnalyzerEngine(tb)
    network = analyzer.build_causal_network()
    assert network.event_count == 0
    assert network.chain_count == 0


def test_single_event_no_chains():
    tb = TimelineBase()
    tb.add_event(timestamp=datetime(2024, 1, 1), data={}, summary="只有一个人")
    analyzer = AnalyzerEngine(tb)
    network = analyzer.build_causal_network()
    assert network.event_count == 0


def test_manual_chain_add():
    a = TimelineEvent(timestamp=datetime(2024, 1, 1), summary="通胀", id="a1")
    b = TimelineEvent(timestamp=datetime(2024, 6, 1), summary="加息", id="b1")
    net = CausalNetwork()
    net.add_chain(_make_chain(a, b, 0.8))
    assert net.event_count == 2
    assert net.chain_count == 1


# ═══════════════════════════════════════════════════════
# 2. 因果遍历
# ═══════════════════════════════════════════════════════

def test_direct_effects():
    net, a, b, c, d = _make_manual_network()
    effects = net.get_direct_effects("evtA")
    assert len(effects) == 2
    effect_ids = {e.effect_event.id for e in effects}
    assert effect_ids == {"evtB", "evtC"}


def test_direct_causes():
    net, a, b, c, d = _make_manual_network()
    causes = net.get_direct_causes("evtD")
    assert len(causes) == 2
    cause_ids = {e.cause_event.id for e in causes}
    assert cause_ids == {"evtB", "evtC"}


def test_descendants():
    net, a, b, c, d = _make_manual_network()
    desc = net.get_descendants("evtA")
    desc_ids = {d["event_id"] for d in desc}
    assert "evtB" in desc_ids
    assert "evtC" in desc_ids
    assert "evtD" in desc_ids
    assert "evtA" not in desc_ids


def test_ancestors():
    net, a, b, c, d = _make_manual_network()
    anc = net.get_ancestors("evtD")
    anc_ids = {a["event_id"] for a in anc}
    assert "evtA" in anc_ids
    assert "evtB" in anc_ids
    assert "evtC" in anc_ids
    assert "evtD" not in anc_ids


def test_descendants_depth():
    net, a, b, c, d = _make_manual_network()
    desc = net.get_descendants("evtA", max_depth=1)
    desc_ids = {d["event_id"] for d in desc}
    assert desc_ids == {"evtB", "evtC"}
    assert "evtD" not in desc_ids


def test_descendants_has_confidence():
    net, a, b, c, d = _make_manual_network()
    desc = net.get_descendants("evtA")
    for d in desc:
        assert "chain_confidence" in d
        assert "chain_description" in d
        assert "depth" in d


def test_root_ids():
    net, a, b, c, d = _make_manual_network()
    assert net.root_ids == ["evtA"]


def test_leaf_ids():
    net, a, b, c, d = _make_manual_network()
    assert net.leaf_ids == ["evtD"]


def test_no_cycles():
    net, a, b, c, d = _make_manual_network()
    desc = net.get_descendants("evtA", max_depth=100)
    desc_ids = [d["event_id"] for d in desc]
    assert len(desc_ids) == len(set(desc_ids))


# ═══════════════════════════════════════════════════════
# 3. 子网络
# ═══════════════════════════════════════════════════════

def test_subgraph():
    net, a, b, c, d = _make_manual_network()
    sub = net.get_subgraph("evtB", max_depth=1)
    assert sub.event_count == 3  # A, B, D


def test_subgraph_center():
    net, a, b, c, d = _make_manual_network()
    sub = net.get_subgraph("evtD", max_depth=10)
    assert sub.event_count == 4


def test_subgraph_empty():
    net = CausalNetwork()
    sub = net.get_subgraph("nonexist")
    assert sub.event_count == 0


# ═══════════════════════════════════════════════════════
# 4. 导出格式
# ═══════════════════════════════════════════════════════

def test_to_mermaid():
    net, a, b, c, d = _make_manual_network()
    mermaid = net.to_mermaid()
    assert "graph LR" in mermaid
    assert "evtA" in mermaid
    assert "-->" in mermaid


def test_to_mermaid_td():
    net, a, b, c, d = _make_manual_network()
    mermaid = net.to_mermaid(direction="TD")
    assert "graph TD" in mermaid


def test_to_dot():
    net, a, b, c, d = _make_manual_network()
    dot = net.to_dot()
    assert "digraph" in dot
    assert "evtA" in dot
    assert "->" in dot


def test_to_dot_custom_rankdir():
    net, a, b, c, d = _make_manual_network()
    dot = net.to_dot(rankdir="TD")
    assert "rankdir=TD" in dot


def test_to_dict():
    net, a, b, c, d = _make_manual_network()
    data = net.to_dict()
    assert data["node_count"] == 4
    assert data["edge_count"] == 4


def test_to_dict_json_serializable():
    net, a, b, c, d = _make_manual_network()
    data = net.to_dict()
    json.dumps(data, ensure_ascii=False)


def test_to_dict_root_leaf():
    net, a, b, c, d = _make_manual_network()
    data = net.to_dict()
    roots = [n for n in data["nodes"] if n["is_root"]]
    leaves = [n for n in data["nodes"] if n["is_leaf"]]
    assert len(roots) == 1
    assert roots[0]["id"] == "evtA"
    assert len(leaves) == 1
    assert leaves[0]["id"] == "evtD"


def test_to_mermaid_export_file():
    net, a, b, c, d = _make_manual_network()
    path = tempfile.mktemp(suffix=".md")
    with open(path, "w") as f:
        f.write("# 因果网络\n\n```mermaid\n")
        f.write(net.to_mermaid())
        f.write("\n```\n")
    with open(path) as f:
        assert "graph LR" in f.read()
    os.unlink(path)


def test_to_dot_export_file():
    net, a, b, c, d = _make_manual_network()
    path = tempfile.mktemp(suffix=".dot")
    with open(path, "w") as f:
        f.write(net.to_dot())
    with open(path) as f:
        assert "digraph" in f.read()
    os.unlink(path)


# ═══════════════════════════════════════════════════════
# 5. 长链
# ═══════════════════════════════════════════════════════

def test_long_chain():
    """通胀→加息→股市暴跌 三段因果"""
    tb = _make_econ_tb()
    analyzer = AnalyzerEngine(tb)
    network = analyzer.build_causal_network(min_confidence=0.1)

    events = tb.timeline.get_all_events()
    e_cpi = [e for e in events if "CPI" in e.summary][0]

    desc = network.get_descendants(e_cpi.id)
    assert len(desc) > 0
    desc_summaries = [d["summary"] for d in desc]
    assert any("加息" in s for s in desc_summaries)


def test_long_chain_depth():
    net = CausalNetwork()
    events = []
    for i in range(5):
        e = TimelineEvent(timestamp=datetime(2020 + i, 1, 1), summary=f"事件{i}", id=f"e{i}")
        events.append(e)
    for i in range(4):
        net.add_chain(_make_chain(events[i], events[i + 1], 0.5))

    desc = net.get_descendants("e0")
    depths = {d["event_id"]: d["depth"] for d in desc}
    assert depths["e1"] == 1
    assert depths["e2"] == 2
    assert depths["e3"] == 3
    assert depths["e4"] == 4


# ═══════════════════════════════════════════════════════
# 6. 边界条件
# ═══════════════════════════════════════════════════════

def test_descendants_nonexistent():
    net, *_ = _make_manual_network()
    assert net.get_descendants("nonexist") == []


def test_ancestors_nonexistent():
    net, *_ = _make_manual_network()
    assert net.get_ancestors("nonexist") == []


def test_direct_effects_nonexistent():
    net, *_ = _make_manual_network()
    assert net.get_direct_effects("nonexist") == []


def test_direct_causes_nonexistent():
    net, *_ = _make_manual_network()
    assert net.get_direct_causes("nonexist") == []


def test_duplicate_chain():
    a = TimelineEvent(timestamp=datetime(2024, 1, 1), summary="A", id="a")
    b = TimelineEvent(timestamp=datetime(2024, 6, 1), summary="B", id="b")
    net = CausalNetwork()
    net.add_chain(_make_chain(a, b, 0.5))
    net.add_chain(_make_chain(a, b, 0.5))
    assert net.chain_count == 1


# ═══════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("🕸️  ChronoVisor 因果网络专业测试")
    print("=" * 55)

    sections = {
        "1. 网络构建": [
            ("构建网络", test_build_network),
            ("最小置信度过滤", test_build_network_min_confidence),
            ("空时间轴", test_empty_timeline_network),
            ("单事件无链", test_single_event_no_chains),
            ("手动添加链", test_manual_chain_add),
        ],
        "2. 因果遍历": [
            ("直接果", test_direct_effects),
            ("直接因", test_direct_causes),
            ("所有后代", test_descendants),
            ("所有祖先", test_ancestors),
            ("深度限制", test_descendants_depth),
            ("后代含置信度", test_descendants_has_confidence),
            ("根事件", test_root_ids),
            ("叶事件", test_leaf_ids),
            ("无循环", test_no_cycles),
        ],
        "3. 子网络": [
            ("截取子网络", test_subgraph),
            ("中心事件子网络", test_subgraph_center),
            ("空网络子网络", test_subgraph_empty),
        ],
        "4. 导出格式": [
            ("Mermaid 导出", test_to_mermaid),
            ("Mermaid TD方向", test_to_mermaid_td),
            ("DOT 导出", test_to_dot),
            ("DOT 自定义方向", test_to_dot_custom_rankdir),
            ("字典导出", test_to_dict),
            ("JSON 序列化", test_to_dict_json_serializable),
            ("字典含根叶标记", test_to_dict_root_leaf),
            ("Mermaid 文件导出", test_to_mermaid_export_file),
            ("DOT 文件导出", test_to_dot_export_file),
        ],
        "5. 长链": [
            ("通胀→加息→暴跌", test_long_chain),
            ("深度字段正确", test_long_chain_depth),
        ],
        "6. 边界条件": [
            ("不存在事件-后代", test_descendants_nonexistent),
            ("不存在事件-祖先", test_ancestors_nonexistent),
            ("不存在事件-直接果", test_direct_effects_nonexistent),
            ("不存在事件-直接因", test_direct_causes_nonexistent),
            ("重复链去重", test_duplicate_chain),
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
