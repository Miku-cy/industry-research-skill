"""持久化存储引擎测试"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.storage import StorageEngine


class TestStorageEngine(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.storage = StorageEngine(db_path=self.tmp.name)
        self.storage.create_project("test", "测试项目", "用于测试")

    def tearDown(self):
        self.storage.close()
        os.unlink(self.tmp.name)

    def _make_event(self, eid, day, summary="test", tags=None):
        class E:
            pass
        e = E()
        e.id = eid
        e.timestamp = datetime(2024, 1, 1) + timedelta(days=day)
        e.time_type = type('T', (), {'value': 'historical'})()
        e.summary = summary
        e.data = {"summary": summary}
        e.source = "test"
        e.source_reliability = type('R', (), {'value': 3})()
        e.tags = tags or []
        e.chapter_id = None
        return e

    def test_project_crud(self):
        projects = self.storage.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["id"], "test")

    def test_save_and_load_events(self):
        events = [self._make_event(f"e{i}", i, f"事件{i}", ["tag"]) for i in range(5)]
        count = self.storage.save_events("test", events)
        self.assertEqual(count, 5)

        loaded = self.storage.load_events("test")
        self.assertEqual(len(loaded), 5)

    def test_load_events_time_filter(self):
        events = [self._make_event(f"e{i}", i) for i in range(10)]
        self.storage.save_events("test", events)

        # 只取前5天
        loaded = self.storage.load_events("test", start="2024-01-01", end="2024-01-06")
        self.assertEqual(len(loaded), 5)

    def test_load_events_tag_filter(self):
        events = [
            self._make_event("e0", 0, tags=["AI", "芯片"]),
            self._make_event("e1", 1, tags=["游戏"]),
            self._make_event("e2", 2, tags=["AI"]),
        ]
        self.storage.save_events("test", events)

        loaded = self.storage.load_events("test", tags=["AI"])
        self.assertEqual(len(loaded), 2)

    def test_count_events(self):
        events = [self._make_event(f"e{i}", i) for i in range(10)]
        self.storage.save_events("test", events)
        self.assertEqual(self.storage.count_events("test"), 10)

    def test_save_and_load_chains(self):
        class Chain:
            pass
        chains = []
        for i in range(3):
            c = Chain()
            c.cause_event = self._make_event(f"cause{i}", i)
            c.effect_event = self._make_event(f"effect{i}", i + 5)
            c.confidence = 0.3 + i * 0.1
            c.time_gap = timedelta(days=5)
            c.description = f"链{i}"
            chains.append(c)

        count = self.storage.save_chains("test", chains)
        self.assertEqual(count, 3)

        loaded = self.storage.load_chains("test", min_confidence=0.3)
        self.assertEqual(len(loaded), 3)

    def test_load_chains_confidence_filter(self):
        class Chain:
            pass
        chains = []
        for i in range(5):
            c = Chain()
            c.cause_event = self._make_event(f"c{i}", i)
            c.effect_event = self._make_event(f"e{i}", i + 3)
            c.confidence = 0.1 * (i + 1)
            c.time_gap = timedelta(days=3)
            c.description = ""
            chains.append(c)

        self.storage.save_chains("test", chains)
        loaded = self.storage.load_chains("test", min_confidence=0.4)
        self.assertEqual(len(loaded), 2)  # 0.4 and 0.5

    def test_save_and_load_chapters(self):
        class Ch:
            pass
        chapters = []
        for i in range(3):
            ch = Ch()
            ch.id = f"ch{i}"
            ch.title = f"第{i}章"
            ch.start_time = datetime(2024, 1, 1) + timedelta(days=i * 30)
            ch.end_time = datetime(2024, 1, 1) + timedelta(days=(i + 1) * 30)
            ch.summary = f"章节{i}"
            ch.tags = [f"tag{i}"]
            ch.event_ids = [f"e{i}_0", f"e{i}_1"]
            chapters.append(ch)

        count = self.storage.save_chapters("test", chapters)
        self.assertEqual(count, 3)

        loaded = self.storage.load_chapters("test")
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0]["title"], "第0章")

    def test_observation_crud(self):
        self.storage.save_observation("科技与半导体", 30, 0.8, "芯片涨价", "存储厂商利润增")
        self.storage.save_observation("科技与半导体", 60, 0.6, "AI需求", "算力扩张")
        self.storage.save_observation("金融与资本市场", 7, 0.9, "加息", "股市跌")

        obs = self.storage.load_observations("科技与半导体")
        self.assertEqual(len(obs), 2)

        all_obs = self.storage.load_observations()
        self.assertEqual(len(all_obs), 3)

    def test_stats(self):
        events = [self._make_event(f"e{i}", i) for i in range(5)]
        self.storage.save_events("test", events)

        s = self.storage.stats("test")
        self.assertEqual(s["events"], 5)
        self.assertEqual(s["chains"], 0)
        self.assertEqual(s["chapters"], 0)

    def test_project_isolation(self):
        self.storage.create_project("p1", "项目1")
        self.storage.create_project("p2", "项目2")

        self.storage.save_events("p1", [self._make_event("e0", 0)])
        self.storage.save_events("p2", [self._make_event("e0", 0), self._make_event("e1", 1)])

        self.assertEqual(self.storage.count_events("p1"), 1)
        self.assertEqual(self.storage.count_events("p2"), 2)

    def test_clear_chains(self):
        class Chain:
            pass
        c = Chain()
        c.cause_event = self._make_event("c0", 0)
        c.effect_event = self._make_event("e0", 5)
        c.confidence = 0.5
        c.time_gap = timedelta(days=5)
        c.description = "test"

        self.storage.save_chains("test", [c])
        self.assertEqual(len(self.storage.load_chains("test")), 1)

        self.storage.clear_chains("test")
        self.assertEqual(len(self.storage.load_chains("test")), 0)


if __name__ == "__main__":
    unittest.main()
