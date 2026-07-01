"""持久化存储引擎 — SQLite 实现

支持：
- 事件数据存储与索引查询
- 因果网络序列化/反序列化
- 多项目数据隔离
- 按时间/标签/领域快速查询
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


class StorageEngine:
    """SQLite 持久化存储引擎

    线程安全：连接开启 check_same_thread=False（允许多线程复用同一连接），
    并在写操作上加 RLock 串行化，避免并发事务交错。读操作在 WAL 模式下可并发。
    """

    def __init__(self, db_path: str = ""):
        if not db_path:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base, "..", "data", "chronovisor.db")
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        # check_same_thread=False 让 daemon 线程能复用此连接
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL 模式：读不阻塞写，写不阻塞读，崩溃恢复更稳健
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error:
            pass
        self._lock = threading.RLock()
        self._init_tables()

    def _init_tables(self):
        """初始化表结构"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                time_type TEXT DEFAULT 'historical',
                summary TEXT DEFAULT '',
                data TEXT DEFAULT '{}',
                source TEXT DEFAULT '',
                source_reliability INTEGER DEFAULT 3,
                tags TEXT DEFAULT '[]',
                chapter_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (project_id, id)
            );

            CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(project_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_chapter ON events(project_id, chapter_id);

            CREATE TABLE IF NOT EXISTS chapters (
                id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                title TEXT DEFAULT '',
                start_time TEXT,
                end_time TEXT,
                summary TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                event_ids TEXT DEFAULT '[]',
                PRIMARY KEY (project_id, id)
            );

            CREATE TABLE IF NOT EXISTS causal_chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                cause_id TEXT NOT NULL,
                effect_id TEXT NOT NULL,
                confidence REAL DEFAULT 0,
                time_gap_days INTEGER DEFAULT 0,
                description TEXT DEFAULT '',
                is_indirect INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_chains_project ON causal_chains(project_id);
            CREATE INDEX IF NOT EXISTS idx_chains_cause ON causal_chains(project_id, cause_id);
            CREATE INDEX IF NOT EXISTS idx_chains_effect ON causal_chains(project_id, effect_id);

            CREATE TABLE IF NOT EXISTS lag_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                gap_days REAL NOT NULL,
                confidence REAL DEFAULT 0,
                cause_summary TEXT DEFAULT '',
                effect_summary TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS learned_graph (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_words TEXT NOT NULL,
                effect_words TEXT NOT NULL,
                weight REAL DEFAULT 0.3,
                domain TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- lag_observations：load_observations 按 domain 过滤，需建索引
            CREATE INDEX IF NOT EXISTS idx_lag_domain ON lag_observations(domain);
            -- learned_graph：按 domain / trigger_words 查询
            CREATE INDEX IF NOT EXISTS idx_learned_domain ON learned_graph(domain);
            CREATE INDEX IF NOT EXISTS idx_learned_trigger ON learned_graph(trigger_words);
        """)
        self.conn.commit()

    # ═══ 项目管理 ═══

    def create_project(self, project_id: str, name: str, description: str = ""):
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO projects (id, name, description) VALUES (?, ?, ?)",
                (project_id, name, description),
            )
            self.conn.commit()

    def list_projects(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    # ═══ 事件存储 ═══

    def save_event(self, project_id: str, event) -> str:
        """保存单个事件"""
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO events
                (id, project_id, timestamp, time_type, summary, data, source, source_reliability, tags, chapter_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.id, project_id,
                event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
                getattr(event.time_type, 'value', str(event.time_type)),
                event.summary or "",
                json.dumps(event.data, ensure_ascii=False) if event.data else "{}",
                event.source or "",
                getattr(event.source_reliability, 'value', 3),
                json.dumps(event.tags, ensure_ascii=False),
                event.chapter_id,
            ))
            self.conn.commit()
        return event.id

    def save_events(self, project_id: str, events: list) -> int:
        """批量保存事件"""
        if not events:
            return 0
        rows = []
        for event in events:
            rows.append((
                event.id, project_id,
                event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
                getattr(event.time_type, 'value', str(event.time_type)),
                event.summary or "",
                json.dumps(event.data, ensure_ascii=False) if event.data else "{}",
                event.source or "",
                getattr(event.source_reliability, 'value', 3),
                json.dumps(event.tags, ensure_ascii=False),
                event.chapter_id,
            ))
        with self._lock:
            self.conn.executemany("""
                INSERT OR REPLACE INTO events
                (id, project_id, timestamp, time_type, summary, data, source, source_reliability, tags, chapter_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            self.conn.commit()
        return len(rows)

    def append_events(self, project_id: str, events: list) -> int:
        """增量追加事件（不读取已有数据，直接 INSERT OR REPLACE）

        避免 load-all → extend → save-all 模式导致的并发竞态与全量重写。
        与 save_events 行为等价，但语义上更明确表示"增量"。
        """
        return self.save_events(project_id, events)

    def clear_events(self, project_id: str):
        """清空指定项目的事件"""
        with self._lock:
            self.conn.execute("DELETE FROM events WHERE project_id = ?", (project_id,))
            self.conn.commit()

    def load_events(self, project_id: str,
                    start: Optional[str] = None,
                    end: Optional[str] = None,
                    tags: Optional[List[str]] = None,
                    limit: int = 10000) -> List[Dict]:
        """查询事件（支持时间范围和标签过滤）"""
        query = "SELECT * FROM events WHERE project_id = ?"
        params: list = [project_id]

        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)

        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        results = [dict(r) for r in rows]

        # 标签过滤（JSON字段，内存过滤）
        if tags:
            tag_set = set(tags)
            results = [r for r in results if tag_set & set(json.loads(r.get("tags", "[]")))]

        return results

    def count_events(self, project_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE project_id = ?", (project_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    # ═══ 因果链存储 ═══

    def save_chains(self, project_id: str, chains: list) -> int:
        """保存因果链"""
        rows = self._build_chain_rows(project_id, chains)
        with self._lock:
            self.conn.executemany("""
                INSERT INTO causal_chains
                (project_id, cause_id, effect_id, confidence, time_gap_days, description, is_indirect)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, rows)
            self.conn.commit()
        return len(rows)

    def replace_chains(self, project_id: str, chains: list) -> int:
        """原子地替换项目的全部因果链（推荐替代 clear_chains + save_chains）

        DELETE + INSERT 在同一事务内提交，避免并发查询时拿到
        "部分旧链 + 部分新链"的混合视图。
        """
        rows = self._build_chain_rows(project_id, chains)
        with self._lock:
            # 单一事务：先删后插，原子提交
            self.conn.execute(
                "DELETE FROM causal_chains WHERE project_id = ?", (project_id,)
            )
            if rows:
                self.conn.executemany("""
                    INSERT INTO causal_chains
                    (project_id, cause_id, effect_id, confidence, time_gap_days, description, is_indirect)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, rows)
            self.conn.commit()
        return len(rows)

    @staticmethod
    def _build_chain_rows(project_id: str, chains: list) -> list:
        rows = []
        for chain in chains:
            gap = chain.time_gap
            gap_days = gap.days if hasattr(gap, 'days') else int(gap)
            rows.append((
                project_id,
                chain.cause_event.id,
                chain.effect_event.id,
                chain.confidence,
                gap_days,
                chain.description or "",
                1 if "[间接因果]" in (chain.description or "") else 0,
            ))
        return rows

    def load_chains(self, project_id: str,
                    min_confidence: float = 0,
                    indirect_only: bool = False) -> List[Dict]:
        """查询因果链"""
        query = "SELECT * FROM causal_chains WHERE project_id = ? AND confidence >= ?"
        params: list = [project_id, min_confidence]
        if indirect_only:
            query += " AND is_indirect = 1"
        query += " ORDER BY confidence DESC"
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def clear_chains(self, project_id: str):
        """清除项目的因果链（重建前调用）"""
        with self._lock:
            self.conn.execute("DELETE FROM causal_chains WHERE project_id = ?", (project_id,))
            self.conn.commit()

    # ═══ 章节存储 ═══

    def save_chapters(self, project_id: str, chapters: list) -> int:
        rows = []
        for ch in chapters:
            rows.append((
                ch.id, project_id, ch.title,
                ch.start_time.isoformat() if hasattr(ch.start_time, 'isoformat') else str(ch.start_time),
                ch.end_time.isoformat() if hasattr(ch.end_time, 'isoformat') else str(ch.end_time),
                ch.summary or "",
                json.dumps(ch.tags, ensure_ascii=False),
                json.dumps(ch.event_ids, ensure_ascii=False),
            ))
        with self._lock:
            self.conn.executemany("""
                INSERT OR REPLACE INTO chapters
                (id, project_id, title, start_time, end_time, summary, tags, event_ids)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            self.conn.commit()
        return len(rows)

    def load_chapters(self, project_id: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM chapters WHERE project_id = ? ORDER BY start_time",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ═══ 滞后观测存储 ═══

    def save_observation(self, domain: str, gap_days: float, confidence: float,
                         cause_summary: str = "", effect_summary: str = ""):
        with self._lock:
            self.conn.execute("""
                INSERT INTO lag_observations (domain, gap_days, confidence, cause_summary, effect_summary)
                VALUES (?, ?, ?, ?, ?)
            """, (domain, gap_days, confidence, cause_summary, effect_summary))
            self.conn.commit()

    def load_observations(self, domain: Optional[str] = None, limit: int = 1000) -> List[Dict]:
        if domain:
            rows = self.conn.execute(
                "SELECT * FROM lag_observations WHERE domain = ? ORDER BY created_at DESC LIMIT ?",
                (domain, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM lag_observations ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ═══ 统计 ═══

    def stats(self, project_id: str) -> Dict:
        events = self.count_events(project_id)
        chains = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM causal_chains WHERE project_id = ?", (project_id,)
        ).fetchone()["cnt"]
        chapters = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM chapters WHERE project_id = ?", (project_id,)
        ).fetchone()["cnt"]
        return {"events": events, "chains": chains, "chapters": chapters}

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
