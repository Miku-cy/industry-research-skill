#!/usr/bin/env python3
"""ChronoVisor 因果挖掘 CLI

用法：
  # 从 CSV 挖掘因果，生成 3D HTML
  python mine.py events.csv -o network.html

  # 从 JSON 挖掘
  python mine.py events.json -o network.html

  # 指定模型和置信度
  python mine.py events.csv -o network.html --model mimo-v2.5 --min-conf 0.3

  # 直接输入事件文本（逗号分隔）
  python mine.py --text "美联储加息,Terra崩盘,FTX破产,BTC暴跌"

CSV 格式：
  timestamp, summary, tags
  2022-03-16, 美联储宣布加息25基点, 加息|美联储
  2022-05-10, Terra/Luna崩盘, 加密货币|崩盘
"""
import sys
import os
import json
import csv
import argparse
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import TimelineBase, AnalyzerEngine, CausalMiningEngine


def load_config():
    """从 chronovisor.yaml 或 openclaw.json 加载配置"""
    config = {}
    # 尝试 chronovisor.yaml
    for p in ["chronovisor.yaml", "../chronovisor.yaml"]:
        if os.path.exists(p):
            try:
                import yaml
                with open(p) as f:
                    data = yaml.safe_load(f) or {}
                api = data.get("semantic", {}).get("api", {})
                config["api_url"] = api.get("url", "")
                config["api_key"] = api.get("key", "")
                config["api_model"] = api.get("model", "")
            except Exception:
                pass
            break
    # 回退 openclaw.json
    if not config.get("api_key"):
        oc_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(oc_path):
            with open(oc_path) as f:
                oc = json.load(f)
            providers = oc.get("models", {}).get("providers", {})
            for name, prov in providers.items():
                if prov.get("apiKey"):
                    config["api_url"] = prov.get("baseUrl", "")
                    config["api_key"] = prov.get("apiKey", "")
                    models = prov.get("models", [])
                    if models:
                        config["api_model"] = models[0].get("id", "")
                    break
    return config


def load_events_csv(path):
    events = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row.get("timestamp", "").strip()
            summary = row.get("summary", "").strip()
            tags_str = row.get("tags", "").strip()
            tags = [t.strip() for t in tags_str.replace("|", ",").split(",") if t.strip()]
            if ts and summary:
                events.append({
                    "timestamp": datetime.fromisoformat(ts) if "T" in ts else datetime.strptime(ts, "%Y-%m-%d"),
                    "summary": summary,
                    "tags": tags,
                })
    return events


def load_events_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    events = []
    items = data if isinstance(data, list) else data.get("events", [])
    for item in items:
        ts = item.get("timestamp", "")
        summary = item.get("summary", "")
        tags = item.get("tags", [])
        if ts and summary:
            events.append({
                "timestamp": datetime.fromisoformat(ts) if "T" in ts else datetime.strptime(ts, "%Y-%m-%d"),
                "summary": summary,
                "tags": tags if isinstance(tags, list) else [t.strip() for t in tags.split(",")],
            })
    return events


def load_events_text(text):
    """从逗号分隔的文本创建事件（自动分配时间）"""
    items = [t.strip() for t in text.split(",") if t.strip()]
    events = []
    for i, summary in enumerate(items):
        events.append({
            "timestamp": datetime(2022, 3, 1) + timedelta(days=i * 30),
            "summary": summary,
            "tags": [],
        })
    return events


def generate_html(network, timeline, output_path, title="因果网络 3D"):
    """生成 3D HTML 可视化"""
    # 序列化节点和边
    nodes = []
    for eid, event in network._events.items():
        nodes.append({
            "id": eid,
            "name": event.summary,
            "timestamp": event.timestamp.strftime("%Y-%m-%d"),
            "domain": 0,
            "domainName": "事件",
            "depth": 0,
            "color": "#D55E00",
            "isRoot": eid in network.root_ids,
            "isLeaf": eid in network.leaf_ids,
        })

    edges = []
    for cause_id, effects in network._downstream.items():
        for effect_id, chain in effects.items():
            edges.append({
                "source": cause_id,
                "target": effect_id,
                "confidence": round(chain.confidence, 2),
            })

    data_json = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)

    html_template = os.path.join(os.path.dirname(__file__), "causal_network_3d.html")
    if os.path.exists(html_template):
        with open(html_template, "r", encoding="utf-8") as f:
            html = f.read()
        # 替换数据
        import re
        html = re.sub(r'const D=\{.*?\};', f'const D={data_json};', html, count=1, flags=re.DOTALL)
        html = re.sub(r'<h1>.*?</h1>', f'<h1>{title}</h1>', html, count=1)
        html = re.sub(r'<p>.*?条因果链.*?</p>', f'<p>{len(nodes)} 个事件 · {len(edges)} 条因果链 · mimo 自动挖掘</p>', html, count=1)
    else:
        # 生成简化版 HTML
        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
</head><body>
<script>const D={data_json};</script>
</body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def cmd_mine(args):
    """挖掘因果关系"""
    config = load_config()

    if args.text:
        events_data = load_events_text(args.text)
    elif args.input:
        if args.input.endswith(".json"):
            events_data = load_events_json(args.input)
        else:
            events_data = load_events_csv(args.input)
    else:
        print("❌ 请指定输入文件或 --text")
        sys.exit(1)

    if not events_data:
        print("❌ 没有加载到事件数据")
        sys.exit(1)

    tb = TimelineBase(title=args.title)
    for ed in events_data:
        tb.add_event(
            timestamp=ed["timestamp"],
            data={},
            summary=ed["summary"],
            tags=ed.get("tags", []),
        )

    print(f"📊 加载 {tb.timeline.get_event_count()} 个事件")

    model = args.model or config.get("api_model", "mimo-v2.5")
    miner = CausalMiningEngine(
        api_url=config.get("api_url", ""),
        api_key=config.get("api_key", ""),
        api_model=model,
        config_path=args.config,
    )

    # 显式提示 LLM 未配置（避免静默生成空 HTML）
    if not config.get("api_url") or not config.get("api_key"):
        print("⚠️  未检测到 LLM 配置（chronovisor.yaml / openclaw.json）。")
        print("   将仅使用 ConceptNet 因果图谱挖掘，覆盖范围有限。")
        print("   配置方法：复制 chronovisor.yaml.example → chronovisor.yaml 并填入 api_key。")

    print(f"🤖 使用 {model} 挖掘因果关系...")
    print(f"   批大小={args.batch_size}, 最小置信度={args.min_conf}")

    network = miner.mine(
        tb.timeline.get_all_events(),
        batch_size=args.batch_size,
        min_confidence=args.min_conf,
    )

    print(f"\n✅ 挖掘完成：{network.event_count} 节点 / {network.chain_count} 条因果链")

    if network.chain_count == 0:
        print("\n⚠️  未发现任何因果链。可能原因：")
        print("   1) 事件之间无 ConceptNet 已知因果关系，且 LLM 未配置或调用失败")
        print("   2) 事件时间间隔超出领域传导窗口（默认会被过滤）")
        print("   3) 事件过少（至少需要 2 个有时序先后的事件）")
        print("   仍会生成 HTML，但网络为空。建议配置 LLM 后重试。")

    chains = []
    for cause_id, effects in network._downstream.items():
        for effect_id, chain in effects.items():
            chains.append(chain)
    chains.sort(key=lambda c: c.confidence, reverse=True)

    print(f"\n📈 Top 10 因果链：")
    for i, c in enumerate(chains[:10], 1):
        print(f"  {i}. [{c.confidence:.0%}] {c.cause_event.summary[:30]} → {c.effect_event.summary[:30]}")

    output_path = generate_html(network, tb, args.output, args.title)
    print(f"\n🌐 3D 可视化已生成：{output_path}")
    print(f"   浏览器打开即可查看")


def cmd_predict(args):
    """预测因果传导时间"""
    config = load_config()
    miner = CausalMiningEngine(
        api_url=config.get("api_url", ""),
        api_key=config.get("api_key", ""),
        api_model=args.model or config.get("api_model", "mimo-v2.5"),
        config_path=args.config,
    )

    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    pred = miner.predict(args.summary, tags)

    ci90 = pred["ci_90"]
    ci50 = pred["ci_50"]
    print(f"\n🔮 预测结果：{args.summary}")
    print(f"   领域：{pred['domain']}")
    print(f"   预计传导：{pred['peak_days']} 天")
    print(f"   90% 置信区间：[{ci90[0]}, {ci90[1]}] 天")
    print(f"   50% 置信区间：[{ci50[0]}, {ci50[1]}] 天")
    print(f"   预测置信度：{pred['confidence']:.0%}")
    print(f"\n   各时间段内发生概率：")
    for label, prob in pred["prob_within"].items():
        bar = "█" * int(prob * 20)
        print(f"     {label:>5s}  {bar} {prob:.0%}")


def cmd_predict_be(args):
    """贝叶斯更新预测：先验 + 历史案例 → 后验"""
    config = load_config()
    miner = CausalMiningEngine(
        api_url=config.get("api_url", ""),
        api_key=config.get("api_key", ""),
        api_model=args.model or config.get("api_model", "mimo-v2.5"),
        config_path=args.config,
    )

    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []

    # 加载历史案例
    cases = []
    if args.cases:
        with open(args.cases, "r", encoding="utf-8") as f:
            cases = json.load(f)
    elif args.case:
        # 格式：gap_days:confidence，如 "3:0.9,7:0.8"
        for item in args.case.split(","):
            parts = item.strip().split(":")
            if len(parts) == 2:
                cases.append({"gap_days": float(parts[0]), "confidence": float(parts[1])})

    if not cases:
        print("❌ 请提供历史案例：--case '3:0.9,7:0.8' 或 --cases cases.json")
        sys.exit(1)

    # 先验预测
    prior = miner.predict(args.summary, tags)
    # 贝叶斯更新
    posterior = miner.predict_with_evidence(args.summary, tags, cases)

    ci90 = posterior["ci_90"]
    ci50 = posterior["ci_50"]
    print(f"\n🔮 贝叶斯预测：{args.summary}")
    print(f"   领域：{posterior['domain']}")
    print(f"   历史案例：{len(cases)} 个")
    print(f"")
    print(f"   先验（领域知识）: {prior['peak_days']} 天")
    print(f"   后验（+案例更新）: {posterior['peak_days']} 天")
    print(f"")
    print(f"   90% 置信区间：[{ci90[0]}, {ci90[1]}] 天")
    print(f"   50% 置信区间：[{ci50[0]}, {ci50[1]}] 天")
    print(f"   预测置信度：{posterior['confidence']:.0%}")
    print(f"\n   各时间段内发生概率：")
    for label, prob in posterior["prob_within"].items():
        bar = "█" * int(prob * 20)
        print(f"     {label:>5s}  {bar} {prob:.0%}")


def main():
    # 兼容旧用法：python mine.py --text "..." 或 python mine.py events.csv -o ...
    # 如果第一个参数不是已知子命令，自动注入 "mine"
    SUBCMDS = {"mine", "predict", "predict-be"}
    argv = sys.argv[1:]
    if argv and argv[0] not in SUBCMDS and not argv[0].startswith("-h"):
        # 第一个非选项参数若不是子命令，就当 mine 处理
        if argv[0] not in ("-h", "--help"):
            argv = ["mine"] + argv

    parser = argparse.ArgumentParser(description="ChronoVisor 因果挖掘 CLI")
    subparsers = parser.add_subparsers(dest="command")

    # mine 子命令（默认）
    mine_parser = subparsers.add_parser("mine", help="挖掘因果关系")
    mine_parser.add_argument("input", nargs="?", help="输入文件 (CSV/JSON)")
    mine_parser.add_argument("-o", "--output", default="causal_network.html", help="输出 HTML 文件")
    mine_parser.add_argument("-t", "--title", default="因果网络 3D", help="标题")
    mine_parser.add_argument("--text", help="逗号分隔的事件文本")
    mine_parser.add_argument("--model", default="", help="LLM 模型名")
    mine_parser.add_argument("--min-conf", type=float, default=0.3, help="最小置信度")
    mine_parser.add_argument("--batch-size", type=int, default=15, help="批处理大小")
    mine_parser.add_argument("--config", default="", help="配置文件路径")

    # predict 子命令
    pred_parser = subparsers.add_parser("predict", help="预测因果传导时间")
    pred_parser.add_argument("summary", help="事件摘要，如 '美联储加息25基点'")
    pred_parser.add_argument("--tags", default="", help="逗号分隔的标签，如 '加息,美联储'")
    pred_parser.add_argument("--model", default="", help="LLM 模型名")
    pred_parser.add_argument("--config", default="", help="配置文件路径")

    # predict-be 子命令（贝叶斯更新预测）
    be_parser = subparsers.add_parser("predict-be", help="贝叶斯更新预测：先验+案例→后验")
    be_parser.add_argument("summary", help="事件摘要")
    be_parser.add_argument("--tags", default="", help="逗号分隔的标签")
    be_parser.add_argument("--case", default="", help="历史案例，格式：gap_days:confidence，如 '3:0.9,7:0.8'")
    be_parser.add_argument("--cases", default="", help="历史案例 JSON 文件")
    be_parser.add_argument("--model", default="", help="LLM 模型名")
    be_parser.add_argument("--config", default="", help="配置文件路径")

    args = parser.parse_args(argv)

    if args.command == "predict":
        cmd_predict(args)
    elif args.command == "predict-be":
        cmd_predict_be(args)
    elif args.command == "mine":
        cmd_mine(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
