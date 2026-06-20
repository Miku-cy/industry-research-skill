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
from datetime import datetime

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
            "timestamp": datetime(2022, 3, 1) + __import__("datetime").timedelta(days=i * 30),
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


def main():
    parser = argparse.ArgumentParser(description="ChronoVisor 因果挖掘 CLI")
    parser.add_argument("input", nargs="?", help="输入文件 (CSV/JSON)")
    parser.add_argument("-o", "--output", default="causal_network.html", help="输出 HTML 文件")
    parser.add_argument("-t", "--title", default="因果网络 3D", help="标题")
    parser.add_argument("--text", help="逗号分隔的事件文本")
    parser.add_argument("--model", default="", help="LLM 模型名")
    parser.add_argument("--min-conf", type=float, default=0.3, help="最小置信度")
    parser.add_argument("--batch-size", type=int, default=15, help="批处理大小")
    parser.add_argument("--config", default="", help="配置文件路径")
    args = parser.parse_args()

    # 加载配置
    config = load_config()

    # 加载事件
    if args.text:
        events_data = load_events_text(args.text)
    elif args.input:
        if args.input.endswith(".json"):
            events_data = load_events_json(args.input)
        else:
            events_data = load_events_csv(args.input)
    else:
        parser.print_help()
        sys.exit(1)

    if not events_data:
        print("❌ 没有加载到事件数据")
        sys.exit(1)

    # 构建时间轴
    tb = TimelineBase(title=args.title)
    for ed in events_data:
        tb.add_event(
            timestamp=ed["timestamp"],
            data={},
            summary=ed["summary"],
            tags=ed.get("tags", []),
        )

    print(f"📊 加载 {tb.timeline.get_event_count()} 个事件")

    # 初始化挖掘引擎
    model = args.model or config.get("api_model", "mimo-v2.5")
    miner = CausalMiningEngine(
        api_url=config.get("api_url", ""),
        api_key=config.get("api_key", ""),
        api_model=model,
        config_path=args.config,
    )

    print(f"🤖 使用 {model} 挖掘因果关系...")
    print(f"   批大小={args.batch_size}, 最小置信度={args.min_conf}")

    network = miner.mine(
        tb.timeline.get_all_events(),
        batch_size=args.batch_size,
        min_confidence=args.min_conf,
    )

    print(f"\n✅ 挖掘完成：{network.event_count} 节点 / {network.chain_count} 条因果链")

    # 展示 Top 10
    chains = []
    for cause_id, effects in network._downstream.items():
        for effect_id, chain in effects.items():
            chains.append(chain)
    chains.sort(key=lambda c: c.confidence, reverse=True)

    print(f"\n📈 Top 10 因果链：")
    for i, c in enumerate(chains[:10], 1):
        print(f"  {i}. [{c.confidence:.0%}] {c.cause_event.summary[:30]} → {c.effect_event.summary[:30]}")

    # 生成 HTML
    output_path = generate_html(network, tb, args.output, args.title)
    print(f"\n🌐 3D 可视化已生成：{output_path}")
    print(f"   浏览器打开即可查看")


if __name__ == "__main__":
    main()
