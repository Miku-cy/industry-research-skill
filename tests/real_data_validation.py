"""真实数据验证 — 半导体周期因果挖掘

用 2023-2025 年半导体行业真实事件，测试 ChronoVisor 完整流程：
时间轴 → 四层漏斗 → 因果网络 → 预测
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
from src import TimelineBase, AnalyzerEngine
from src.core.causal_mining import CausalMiningEngine
from src.core.causal_lag import CausalLagModel
from src.core.causal_graph import CausalGraph

# ═══ 真实事件数据（半导体周期 2023-2025）═══

EVENTS = [
    # 2023: AI 需求爆发 + 存储触底
    ("ChatGPT 爆火引发 AI 算力需求激增", "2023-01-23", ["AI", "算力", "需求", "英伟达"]),
    ("英伟达 H100 供不应求，订单排到 2024", "2023-05-25", ["英伟达", "GPU", "供不应求"]),
    ("三星宣布 NAND 减产 50%", "2023-04-01", ["三星", "NAND", "减产", "存储"]),
    ("美光 Q3 财报超预期，存储触底反弹", "2023-06-28", ["美光", "存储", "财报", "反弹"]),
    ("华为 Mate60 Pro 搭载麒麟 9000S", "2023-08-29", ["华为", "芯片", "国产替代"]),
    ("OpenAI 发布 GPT-4，AI 军备竞赛加速", "2023-03-14", ["AI", "GPT-4", "算力"]),
    ("台积电 Q2 业绩指引超预期", "2023-04-20", ["台积电", "财报", "半导体"]),
    ("ASML 订单创新高，EUV 需求强劲", "2023-07-19", ["ASML", "EUV", "设备", "订单"]),
    ("长江存储突破 232 层 NAND", "2023-09-01", ["长江存储", "NAND", "国产替代"]),
    ("英伟达发布 H200，AI 算力再升级", "2023-11-13", ["英伟达", "H200", "AI", "算力"]),

    # 2024: 半导体全面复苏
    ("英伟达市值突破 2 万亿美元", "2024-02-23", ["英伟达", "市值", "AI", "芯片"]),
    ("SK 海力士 HBM3E 量产，供不应求", "2024-03-01", ["SK海力士", "HBM", "存储", "AI"]),
    ("台积电上调全年资本开支", "2024-04-18", ["台积电", "资本开支", "扩产"]),
    ("ASML Q1 订单暴增 3 倍", "2024-04-17", ["ASML", "订单", "设备"]),
    ("三星 HBM3E 良率不足，落后 SK 海力士", "2024-05-01", ["三星", "HBM", "良率", "存储"]),
    ("英伟达发布 Blackwell 架构", "2024-03-18", ["英伟达", "Blackwell", "AI", "芯片"]),
    ("全球半导体销售额同比增长 15%", "2024-06-01", ["半导体", "销售额", "增长"]),
    ("存储芯片价格连续 4 季度上涨", "2024-07-01", ["存储", "价格上涨", "周期"]),
    ("中芯国际 Q2 产能利用率回升至 85%", "2024-08-08", ["中芯国际", "产能", "利用率"]),
    ("苹果 A18 采用台积电 3nm", "2024-09-01", ["苹果", "台积电", "3nm", "芯片"]),

    # 2025: 周期见顶信号
    ("英伟达 Blackwell 出货延迟", "2025-01-15", ["英伟达", "Blackwell", "延迟"]),
    ("存储芯片价格增速放缓", "2025-02-01", ["存储", "价格", "放缓"]),
    ("台积电 Q1 业绩指引低于最乐观预期", "2025-01-10", ["台积电", "财报", "预期"]),
    ("AI 训练成本飙升，部分企业缩减开支", "2025-03-01", ["AI", "成本", "缩减"]),
    ("半导体设备订单增速回落", "2025-04-01", ["半导体", "设备", "订单", "回落"]),
    ("HBM 产能过剩担忧初现", "2025-05-01", ["HBM", "产能过剩", "存储"]),
    ("全球半导体库存升至历史高位", "2025-06-01", ["半导体", "库存", "高位"]),
]


def run_validation():
    print("=" * 60)
    print("ChronoVisor 真实数据验证 — 半导体周期")
    print("=" * 60)

    # Step 1: 构建时间轴
    print("\n📅 Step 1: 构建时间轴")
    timeline = TimelineBase(title="半导体周期 2023-2025")
    for summary, date_str, tags in EVENTS:
        timeline.add_event(
            timestamp=datetime.strptime(date_str, "%Y-%m-%d"),
            data={"summary": summary},
            source="real_news",
            tags=tags,
            summary=summary,
        )
    events = timeline.timeline.get_all_events()
    print(f"  事件数: {len(events)}")
    print(f"  时间跨度: {events[0].timestamp.date()} → {events[-1].timestamp.date()}")

    # Step 2: 因果图谱预评分
    print("\n🔗 Step 2: 因果图谱预评分")
    graph = CausalGraph()
    known_count = 0
    unknown_count = 0
    for i, cause in enumerate(events):
        for j, effect in enumerate(events):
            if i >= j:
                continue
            result = graph.score(cause.summary, effect.summary, cause.tags + effect.tags)
            if result.known and result.score > 0:
                known_count += 1
            elif not result.known:
                unknown_count += 1
    total_pairs = len(events) * (len(events) - 1) // 2
    print(f"  总事件对: {total_pairs}")
    print(f"  图谱已知(快车道): {known_count}")
    print(f"  图谱未知(需LLM): {unknown_count}")
    print(f"  快车道比例: {known_count/max(1, total_pairs)*100:.1f}%")

    # Step 3: 规则引擎因果发现（不调LLM）
    print("\n⚡ Step 3: AnalyzerEngine 规则因果发现")
    engine = AnalyzerEngine(timeline)
    chains = engine.find_causal_chains(min_confidence=0.2)
    print(f"  发现因果链: {len(chains)} 条")

    if chains:
        print("\n  Top 10 因果链:")
        for i, chain in enumerate(chains[:10]):
            gap = chain.time_gap.days
            print(f"  {i+1}. [{chain.confidence:.2f}] {chain.cause_event.summary[:30]}")
            print(f"     → {chain.effect_event.summary[:30]} ({gap}天)")

    # Step 4: 构建因果网络
    print("\n🕸️ Step 4: 因果网络")
    network = engine.build_causal_network(min_confidence=0.2)
    print(f"  节点数: {network.event_count}")
    print(f"  边数: {network.chain_count}")
    print(f"  根节点: {len(network.root_ids)}")
    print(f"  叶节点: {len(network.leaf_ids)}")

    # Step 5: 滞后模型预测
    print("\n🔮 Step 5: 滞后模型预测")
    lag_model = CausalLagModel()
    
    predictions = [
        ("AI算力需求激增", ["AI", "算力", "需求"]),
        ("存储芯片价格上涨", ["存储", "芯片", "价格上涨"]),
        ("半导体库存高位", ["半导体", "库存", "高位"]),
    ]
    for summary, tags in predictions:
        pred = lag_model.predict_lag(tags, summary)
        print(f"\n  「{summary}」")
        print(f"    领域: {pred['domain']}")
        print(f"    峰值传导: {pred['peak_days']}天")
        print(f"    90%CI: [{pred['ci_90'][0]}, {pred['ci_90'][1]}]天")
        print(f"    7天概率: {pred['prob_within']['7天']:.0%}")
        print(f"    30天概率: {pred['prob_within']['30天']:.0%}")

    # Step 6: 因果图谱学习
    print("\n📚 Step 6: 图谱自动学习")
    learned_before = graph.stats()["learned"]
    for chain in chains[:5]:
        graph.learn_from_chain(
            cause_summary=chain.cause_event.summary,
            effect_summary=chain.effect_event.summary,
            cause_tags=chain.cause_event.tags,
            effect_tags=chain.effect_event.tags,
            confidence=chain.confidence,
        )
    learned_after = graph.stats()["learned"]
    print(f"  学习前: {learned_before} 条")
    print(f"  学习后: {learned_after} 条")
    print(f"  新增: {learned_after - learned_before} 条")

    # Step 7: 章节检测
    print("\n📖 Step 7: 章节检测")
    from src.core.timeline import ChapterDetector
    detector = ChapterDetector(timeline.timeline)
    chapters = detector.detect(min_events=3)
    print(f"  检测到 {len(chapters)} 个章节:")
    for ch in chapters:
        print(f"    [{ch.id[:8]}] {ch.title} ({len(ch.event_ids)}个事件)")

    print("\n" + "=" * 60)
    print("验证完成")
    print("=" * 60)


if __name__ == "__main__":
    run_validation()
