"""ChronoVisor 因果分析控制台 — 后端 API

启动：python console.py
访问：http://localhost:8765
"""
import json
import os
import re
import sys
import time
import uuid
import threading
import shutil
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src import TimelineBase, AnalyzerEngine
from src.core.storage import StorageEngine
from src.core.llm_config import llm_config

# ═══ 数据存储 ═══
DB_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DB_DIR, exist_ok=True)

NETWORKS_DIR = os.path.join(DB_DIR, "networks")
os.makedirs(NETWORKS_DIR, exist_ok=True)

# StorageEngine (SQLite，线程安全：check_same_thread=False + 内部 RLock)
storage = StorageEngine(os.path.join(DB_DIR, "chronovisor.db"))
storage.create_project("default", "默认项目")

# 任务状态 + 锁（多线程读写 tasks 字典）
tasks = {}
tasks_lock = threading.Lock()


def _parse_timestamp(ts: str) -> datetime:
    """统一时间戳解析：兼容 ISO 与 YYYY-MM-DD 两种格式"""
    if not ts:
        raise ValueError("empty timestamp")
    return datetime.fromisoformat(ts) if "T" in ts else datetime.strptime(ts, "%Y-%m-%d")


def _events_to_timeline_events(events_data):
    """把 dict 形式的事件转成 TimelineEvent 列表"""
    from src.core.timeline import TimelineEvent, TimeType, SourceReliability
    objs = []
    for ed in events_data:
        ts = ed.get("timestamp", "")
        try:
            dt = _parse_timestamp(ts)
        except Exception:
            continue
        objs.append(TimelineEvent(
            timestamp=dt, time_type=TimeType.HISTORICAL, data={},
            source=ed.get("source", "web"), source_reliability=SourceReliability.GENERAL,
            tags=ed.get("tags", []), summary=ed.get("summary", ""),
        ))
    return objs


def _serialize_network(network, extra=None):
    """把 CausalNetwork 序列化为前端可用的 dict（避免重复 + 不访问私有属性）"""
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
    if extra:
        result.update(extra)
    return result


def _update_task(task_id, **fields):
    """线程安全地更新 tasks[task_id] 的字段（整体替换快照，避免半更新状态被读到）"""
    with tasks_lock:
        snap = dict(tasks.get(task_id, {}))
        snap.update(fields)
        tasks[task_id] = snap


def _get_task(task_id):
    """线程安全地读取任务快照"""
    with tasks_lock:
        return dict(tasks.get(task_id)) if task_id in tasks else None


def load_events():
    """从 SQLite 加载事件"""
    rows = storage.load_events("default")
    return [{"timestamp": r["timestamp"], "summary": r["summary"],
             "tags": json.loads(r.get("tags", "[]")), "id": r["id"]}
            for r in rows]


def save_events(events):
    """保存事件到 SQLite（兼容旧格式；内部走 INSERT OR REPLACE）"""
    objs = _events_to_timeline_events(events)
    if objs:
        storage.save_events("default", objs)


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
    """因果挖掘任务

    用 AnalyzerEngine.build_causal_network() 走规则+ConceptNet 因果图谱。
    注意：当前实现不调用 LLM（用户在 chronovisor.yaml 配的 LLM 对此端点无效）。
    若结果为空且 LLM 未配置，明确返回 error 而非假成功。
    """
    started_at = time.time()
    _update_task(task_id, status="running", progress="正在初始化...", started_at=started_at)
    try:
        tb = TimelineBase(title="因果挖掘")
        for ed in events_data:
            try:
                tb.add_event(
                    timestamp=_parse_timestamp(ed["timestamp"]),
                    data={}, summary=ed["summary"], tags=ed.get("tags", []),
                )
            except Exception:
                continue

        _update_task(task_id, progress=f"正在分析 {len(events_data)} 个事件的因果关系...")

        engine = AnalyzerEngine(tb)
        network = engine.build_causal_network(
            min_confidence=config.get("min_confidence", 0.2),
            multihop=True, max_hops=3,
        )

        result = _serialize_network(network)

        # 空结果且 LLM 未配置 → 明确报错，而不是返回"成功+空网络"让用户摸不着头脑
        if result["stats"]["edge_count"] == 0:
            llm_cfg = llm_config.get("mining")
            llm_ready = bool(llm_cfg.get("api_url") and llm_cfg.get("api_key"))
            if not llm_ready:
                _update_task(
                    task_id, status="error",
                    progress=("未发现因果链。事件间无 ConceptNet 已知因果关系，且 LLM 未配置。"
                              "请在 chronovisor.yaml 配置 api_key 后重试，"
                              "或运行 mine.py --text 走 LLM 挖掘。"),
                    elapsed=round(time.time() - started_at, 1),
                )
                return

        _update_task(
            task_id, status="done", result=result,
            progress=f"完成：{result['stats']['node_count']} 节点 / {result['stats']['edge_count']} 条因果链",
            elapsed=round(time.time() - started_at, 1),
        )

    except Exception as e:
        _update_task(task_id, status="error", progress=f"错误：{str(e)}",
                     elapsed=round(time.time() - started_at, 1))


def run_ai_task(task_id, query, config):
    """AI 研究任务：用户描述问题 → LLM 提取事件 → 挖掘因果

    复用 llm_config.call() 的速率限制/429 退避/重试，不再手写 urllib。
    """
    started_at = time.time()
    _update_task(task_id, status="running", progress="AI 正在分析问题...", started_at=started_at)

    # 进入任务前先校验 LLM 配置，避免 urllib URLError 这种迷惑性错误
    llm_cfg = llm_config.get("mining")
    if not llm_cfg.get("api_url") or not llm_cfg.get("api_key"):
        _update_task(
            task_id, status="error",
            progress=("未配置 LLM。请在 chronovisor.yaml 填写 api_url 和 api_key，"
                      "或确保 ~/.openclaw/openclaw.json 存在。"),
            elapsed=round(time.time() - started_at, 1),
        )
        return

    try:
        extract_prompt = f"""你是研究分析师。用户想了解：「{query}」

请列出与这个主题相关的关键事件（10-20个），按时间顺序排列。

只返回JSON数组，不要其他文字：
[{{"timestamp": "2020-01-01", "summary": "事件描述", "tags": ["标签1", "标签2"]}}, ...]

要求：
1. 事件要有明确的时间
2. 事件之间有因果或相关关系
3. 涵盖起因、过程、结果
4. 标签要能反映事件属性"""

        # 复用 llm_config.call（含速率限制、429 退避、重试）
        resp = llm_config.call("mining", extract_prompt, temperature=0.3, max_tokens=4096)
        if resp.get("error"):
            _update_task(task_id, status="error",
                         progress=f"LLM 调用失败：{resp['error']}",
                         elapsed=round(time.time() - started_at, 1))
            return
        content = resp.get("content") or ""

        # 解析事件
        match = re.search(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
        if not match:
            _update_task(task_id, status="error", progress="AI 未能提取事件（返回格式不符）",
                        elapsed=round(time.time() - started_at, 1))
            return

        events_data = json.loads(match.group(0))
        _update_task(task_id, progress=f"AI 发现了 {len(events_data)} 个事件，正在挖掘因果...")

        # 增量追加事件，避免 load-all → extend → save-all 竞态
        objs = _events_to_timeline_events(events_data)
        if objs:
            storage.append_events("default", objs)

        # 第二步：挖掘因果
        tb = TimelineBase(title=query[:30])
        for ed in events_data:
            try:
                tb.add_event(timestamp=_parse_timestamp(ed.get("timestamp", "")),
                              data={}, summary=ed.get("summary", ""),
                              tags=ed.get("tags", []))
            except Exception:
                continue

        engine = AnalyzerEngine(tb)
        network = engine.build_causal_network(min_confidence=0.2, multihop=True, max_hops=3)

        result = _serialize_network(network, extra={"query": query})

        # 自动保存
        name = "ai_" + query[:20].replace(" ", "_") + "_" + datetime.now().strftime("%H%M%S")
        save_network(name, result)

        _update_task(
            task_id, status="done", result=result,
            progress=f"完成：{result['stats']['node_count']} 事件 / {result['stats']['edge_count']} 条因果链",
            elapsed=round(time.time() - started_at, 1),
        )

    except Exception as e:
        _update_task(task_id, status="error", progress=f"错误：{str(e)}",
                     elapsed=round(time.time() - started_at, 1))


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
        elif path == "/api/stats":
            self.json_response(storage.stats("default"))
        elif path == "/api/domains":
            from src.core.causal_lag import CausalLagModel
            lag = CausalLagModel()
            domains = list(lag.profiles.keys())
            self.json_response({"domains": domains})
        elif path == "/api/classify":
            q = params.get("q", [""])[0]
            if q:
                from src.core.causal_lag import CausalLagModel
                lag = CausalLagModel()
                domain = lag.classify_domain([], q)
                profile = lag.get_profile(domain)
                self.json_response({
                    "domain": domain,
                    "peak_days": profile.peak_days,
                    "max_days": profile.typical_max_days,
                })
            else:
                self.json_response({"error": "missing q param"}, 400)
        elif path.startswith("/api/task/"):
            task_id = path.split("/")[-1]
            snap = _get_task(task_id)
            if snap is not None:
                self.json_response(snap)
            else:
                self.json_response({"error": "not found"}, 404)
        else:
            super().do_GET()

    def _read_body(self):
        """读取并解析 JSON body，失败返回 None（已发送 400）"""
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return None
        try:
            raw = self.rfile.read(length)
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError) as e:
            self.json_response({"error": f"invalid json body: {e}"}, 400)
            return None

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()
        if body is None and path not in ("/api/events/clear",):
            # 已在 _read_body 里发过 400；无 body 的请求只有 clear 不需要
            return

        if path == "/api/events":
            new_events = body.get("events", []) if body else []
            if new_events:
                # 增量追加，避免 load-all → extend → save-all 竞态
                objs = _events_to_timeline_events(new_events)
                storage.append_events("default", objs)
            count = storage.count_events("default")
            self.json_response({"ok": True, "count": count})
        elif path == "/api/events/clear":
            storage.clear_events("default")
            self.json_response({"ok": True})
        elif path == "/api/ai-task":
            query = body.get("query", "") if body else ""
            if not query:
                self.json_response({"error": "请描述你想了解的问题"}, 400)
                return
            # 复用 llm_config 单例（import 时已读盘，零额外 IO）
            task_id = str(uuid.uuid4())[:8]
            _update_task(task_id, status="pending", progress="AI 正在研究...")
            thread = threading.Thread(target=run_ai_task, args=(task_id, query, {}))
            thread.daemon = True
            thread.start()
            self.json_response({"task_id": task_id})
        elif path == "/api/mine":
            events = body.get("events", load_events()) if body else load_events()
            if not events:
                self.json_response({"error": "没有事件数据"}, 400)
                return
            config = body.get("config", {}) if body else {}
            # min_confidence 等参数从 body 传，LLM 配置由 llm_config 单例管理
            task_id = str(uuid.uuid4())[:8]
            _update_task(task_id, status="pending", progress="等待中...")
            thread = threading.Thread(target=run_mining_task, args=(task_id, events, config))
            thread.daemon = True
            thread.start()
            self.json_response({"task_id": task_id})
        elif path == "/api/save":
            name = body.get("name", datetime.now().strftime("%Y%m%d_%H%M%S")) if body else datetime.now().strftime("%Y%m%d_%H%M%S")
            data = body.get("data", {}) if body else {}
            save_network(name, data)
            self.json_response({"ok": True, "name": name})
        elif path == "/api/events/import":
            imported = body.get("events", []) if body else []
            if imported:
                objs = _events_to_timeline_events(imported)
                storage.append_events("default", objs)
            total = storage.count_events("default")
            self.json_response({"ok": True, "imported": len(imported), "total": total})
        else:
            self.json_response({"error": "not found"}, 404)

    def do_PUT(self):
        """增量更新"""
        parsed = urlparse(self.path)
        if parsed.path == "/api/incremental":
            body = self._read_body()
            if body is None:
                return
            new_events = body.get("events", [])
            if not new_events:
                self.json_response({"error": "no events"}, 400)
                return
            objs = _events_to_timeline_events(new_events)
            storage.append_events("default", objs)
            self.json_response({"ok": True, "added": len(objs)})
        else:
            self.json_response({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
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
            # 流式输出，避免大文件一次性读入内存
            with open(filepath, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # 静默日志


def main():
    port = 8765
    # ThreadingHTTPServer：每个请求一个线程，避免大文件下载阻塞其他请求
    server = ThreadingHTTPServer(("0.0.0.0", port), ChronoVisorHandler)
    print(f"🧠 ChronoVisor 因果分析控制台")
    print(f"   http://localhost:{port}")
    print(f"   Ctrl+C 退出")
    server.serve_forever()


if __name__ == "__main__":
    main()
