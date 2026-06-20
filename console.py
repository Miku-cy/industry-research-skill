"""ChronoVisor 因果分析控制台 — 后端 API

启动：python console.py
访问：http://localhost:8765
"""
import json
import os
import sys
import time
import uuid
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src import TimelineBase, AnalyzerEngine, CausalMiningEngine, CausalNetwork

# ═══ 数据存储 ═══
DB_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DB_DIR, exist_ok=True)

EVENTS_FILE = os.path.join(DB_DIR, "events.json")
NETWORKS_DIR = os.path.join(DB_DIR, "networks")
os.makedirs(NETWORKS_DIR, exist_ok=True)

# 任务状态
tasks = {}


def load_events():
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_events(events):
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def save_network(name, network_data):
    path = os.path.join(NETWORKS_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(network_data, f, ensure_ascii=False, indent=2)
    return path


def list_networks():
    result = []
    for f in os.listdir(NETWORKS_DIR):
        if f.endswith(".json"):
            path = os.path.join(NETWORKS_DIR, f)
            stat = os.stat(path)
            result.append({
                "name": f.replace(".json", ""),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return result


def load_network(name):
    path = os.path.join(NETWORKS_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ═══ 因果挖掘线程 ═══
def run_mining_task(task_id, events_data, config):
    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = "正在初始化..."

        tb = TimelineBase(title="因果挖掘")
        for ed in events_data:
            tb.add_event(
                timestamp=datetime.fromisoformat(ed["timestamp"]) if "T" in ed["timestamp"] else datetime.strptime(ed["timestamp"], "%Y-%m-%d"),
                data={},
                summary=ed["summary"],
                tags=ed.get("tags", []),
            )

        miner = CausalMiningEngine(
            api_url=config.get("api_url", ""),
            api_key=config.get("api_key", ""),
            api_model=config.get("api_model", "mimo-v2.5"),
        )

        tasks[task_id]["progress"] = f"正在分析 {len(events_data)} 个事件的因果关系..."
        tasks[task_id]["started_at"] = time.time()

        network = miner.mine(
            tb.timeline.get_all_events(),
            batch_size=config.get("batch_size", 15),
            min_confidence=config.get("min_confidence", 0.3),
        )

        # 序列化结果
        nodes = []
        for eid, event in network._events.items():
            nodes.append({
                "id": eid,
                "name": event.summary,
                "timestamp": event.timestamp.strftime("%Y-%m-%d"),
                "tags": event.tags,
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
                    "description": chain.description,
                })

        result = {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "root_count": len(network.root_ids),
                "leaf_count": len(network.leaf_ids),
            },
        }

        tasks[task_id]["status"] = "done"
        tasks[task_id]["result"] = result
        tasks[task_id]["progress"] = f"完成：{len(nodes)} 节点 / {len(edges)} 条因果链"
        tasks[task_id]["elapsed"] = round(time.time() - tasks[task_id]["started_at"], 1)

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["progress"] = f"错误：{str(e)}"


def run_ai_task(task_id, query, config):
    """AI 研究任务：用户描述问题 → mimo 提取事件 → 挖掘因果"""
    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = "AI 正在分析问题..."
        tasks[task_id]["started_at"] = time.time()

        # 第一步：让 mimo 从问题中提取事件
        import urllib.request
        base = config.get("api_url", "").rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"

        extract_prompt = f"""你是研究分析师。用户想了解：「{query}」

请列出与这个主题相关的关键事件（10-20个），按时间顺序排列。

只返回JSON数组，不要其他文字：
[{{"timestamp": "2020-01-01", "summary": "事件描述", "tags": ["标签1", "标签2"]}}, ...]

要求：
1. 事件要有明确的时间
2. 事件之间有因果或相关关系
3. 涵盖起因、过程、结果
4. 标签要能反映事件属性"""

        payload = json.dumps({
            "model": config.get("api_model", "mimo-v2.5"),
            "messages": [{"role": "user", "content": extract_prompt}],
            "temperature": 0.3,
            "max_tokens": 4096,
        }).encode()

        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.get('api_key', '')}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content and msg.get("reasoning_content"):
                content = msg["reasoning_content"]

        # 解析事件
        import re
        match = re.search(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
        if not match:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["progress"] = "AI 未能提取事件"
            return

        events_data = json.loads(match.group(0))
        tasks[task_id]["progress"] = f"AI 发现了 {len(events_data)} 个事件，正在挖掘因果..."

        # 保存事件
        existing = load_events()
        existing.extend(events_data)
        save_events(existing)

        # 第二步：挖掘因果
        tb = TimelineBase(title=query[:30])
        for ed in events_data:
            try:
                ts = ed.get("timestamp", "")
                if ts:
                    dt = datetime.fromisoformat(ts) if "T" in ts else datetime.strptime(ts, "%Y-%m-%d")
                    tb.add_event(timestamp=dt, data={}, summary=ed.get("summary", ""), tags=ed.get("tags", []))
            except Exception:
                continue

        miner = CausalMiningEngine(
            api_url=config.get("api_url", ""),
            api_key=config.get("api_key", ""),
            api_model=config.get("api_model", "mimo-v2.5"),
        )

        network = miner.mine(tb.timeline.get_all_events(), batch_size=15, min_confidence=0.3)

        # 序列化结果
        nodes = []
        for eid, event in network._events.items():
            nodes.append({
                "id": eid, "name": event.summary,
                "timestamp": event.timestamp.strftime("%Y-%m-%d"),
                "tags": event.tags,
                "isRoot": eid in network.root_ids,
                "isLeaf": eid in network.leaf_ids,
            })

        edges = []
        for cause_id, effects in network._downstream.items():
            for effect_id, chain in effects.items():
                edges.append({
                    "source": cause_id, "target": effect_id,
                    "confidence": round(chain.confidence, 2),
                    "description": chain.description,
                })

        result = {
            "nodes": nodes, "edges": edges,
            "stats": {
                "node_count": len(nodes), "edge_count": len(edges),
                "root_count": len(network.root_ids), "leaf_count": len(network.leaf_ids),
            },
            "query": query,
        }

        # 自动保存
        name = "ai_" + query[:20].replace(" ", "_") + "_" + datetime.now().strftime("%H%M%S")
        save_network(name, result)

        tasks[task_id]["status"] = "done"
        tasks[task_id]["result"] = result
        tasks[task_id]["progress"] = f"完成：{len(nodes)} 事件 / {len(edges)} 条因果链"
        tasks[task_id]["elapsed"] = round(time.time() - tasks[task_id]["started_at"], 1)

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["progress"] = f"错误：{str(e)}"


# ═══ API 路由 ═══
class ChronoVisorHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.serve_file("console.html", "text/html")
        elif path == "/api/events":
            self.json_response(load_events())
        elif path == "/api/networks":
            self.json_response(list_networks())
        elif path.startswith("/api/network/"):
            name = path.split("/")[-1]
            data = load_network(name)
            if data:
                self.json_response(data)
            else:
                self.json_response({"error": "not found"}, 404)
        elif path.startswith("/api/task/"):
            task_id = path.split("/")[-1]
            if task_id in tasks:
                self.json_response(tasks[task_id])
            else:
                self.json_response({"error": "not found"}, 404)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))

        if path == "/api/events":
            events = load_events()
            events.extend(body.get("events", []))
            save_events(events)
            self.json_response({"ok": True, "count": len(events)})
        elif path == "/api/events/clear":
            save_events([])
            self.json_response({"ok": True})
        elif path == "/api/ai-task":
            query = body.get("query", "")
            if not query:
                self.json_response({"error": "请描述你想了解的问题"}, 400)
                return
            config = {}
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
            task_id = str(uuid.uuid4())[:8]
            tasks[task_id] = {"status": "pending", "progress": "AI 正在研究..."}
            thread = threading.Thread(target=run_ai_task, args=(task_id, query, config))
            thread.daemon = True
            thread.start()
            self.json_response({"task_id": task_id})
        elif path == "/api/mine":
            events = body.get("events", load_events())
            if not events:
                self.json_response({"error": "没有事件数据"}, 400)
                return
            config = body.get("config", {})
            # 读取 openclaw 配置
            oc_path = os.path.expanduser("~/.openclaw/openclaw.json")
            if os.path.exists(oc_path):
                with open(oc_path) as f:
                    oc = json.load(f)
                providers = oc.get("models", {}).get("providers", {})
                for name, prov in providers.items():
                    if prov.get("apiKey"):
                        config.setdefault("api_url", prov.get("baseUrl", ""))
                        config.setdefault("api_key", prov.get("apiKey", ""))
                        models = prov.get("models", [])
                        if models:
                            config.setdefault("api_model", models[0].get("id", ""))
                        break
            task_id = str(uuid.uuid4())[:8]
            tasks[task_id] = {"status": "pending", "progress": "等待中..."}
            thread = threading.Thread(target=run_mining_task, args=(task_id, events, config))
            thread.daemon = True
            thread.start()
            self.json_response({"task_id": task_id})
        elif path == "/api/save":
            name = body.get("name", datetime.now().strftime("%Y%m%d_%H%M%S"))
            data = body.get("data", {})
            save_network(name, data)
            self.json_response({"ok": True, "name": name})
        elif path == "/api/events/import":
            imported = body.get("events", [])
            events = load_events()
            events.extend(imported)
            save_events(events)
            self.json_response({"ok": True, "imported": len(imported), "total": len(events)})
        else:
            self.json_response({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def json_response(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def serve_file(self, filename, content_type):
        filepath = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(filepath):
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.end_headers()
            with open(filepath, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # 静默日志


def main():
    port = 8765
    server = HTTPServer(("0.0.0.0", port), ChronoVisorHandler)
    print(f"🧠 ChronoVisor 因果分析控制台")
    print(f"   http://localhost:{port}")
    print(f"   Ctrl+C 退出")
    server.serve_forever()


if __name__ == "__main__":
    main()
