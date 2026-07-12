"""存储后端 — JSON + SQLite 双存储

语义化接口: 上层 Store 通过本模块读写，不直接操作文件/数据库。
JSONStorage: 低频读写 (事件、关系)
SQLiteStorage: 高频读写 (玩家行为统计、长期统计)
"""
import json
import os
import sqlite3
import threading
from typing import Optional, List, Dict, Any


class JSONStorage:
    """JSON 文件存储

    目录结构: {base_dir}/{namespace}/{key}.json
    例如: data/memory/char_5/episodes.json
    """

    def __init__(self, base_dir: str = "data/memory"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _path(self, namespace: str, key: str) -> str:
        dir_path = os.path.join(self.base_dir, namespace)
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, f"{key}.json")

    def load(self, namespace: str, key: str) -> Optional[Any]:
        """加载 JSON 数据"""
        path = self._path(namespace, key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def save(self, namespace: str, key: str, data: Any) -> bool:
        """保存 JSON 数据"""
        path = self._path(namespace, key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except IOError:
            return False

    def delete(self, namespace: str, key: str) -> bool:
        """删除 JSON 文件"""
        path = self._path(namespace, key)
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except IOError:
                return False
        return False

    def list_keys(self, namespace: str) -> List[str]:
        """列出命名空间下所有 key (不含扩展名)"""
        dir_path = os.path.join(self.base_dir, namespace)
        if not os.path.isdir(dir_path):
            return []
        return [
            f[:-5] for f in os.listdir(dir_path)
            if f.endswith(".json")
        ]


class SQLiteStorage:
    """SQLite 数据库存储

    表结构:
      player_memory: (observer_id TEXT, target_id TEXT, data TEXT, PRIMARY KEY(observer_id, target_id))
      statistics_memory: (char_id INTEGER PRIMARY KEY, data TEXT)
    """

    def __init__(self, db_path: str = "data/memory/game.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS player_memory (
                        observer_id TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        data TEXT NOT NULL,
                        PRIMARY KEY (observer_id, target_id)
                    );
                    CREATE TABLE IF NOT EXISTS statistics_memory (
                        char_id INTEGER PRIMARY KEY,
                        data TEXT NOT NULL
                    );
                """)
                conn.commit()
            finally:
                conn.close()

    def execute(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """执行 SQL 查询，返回结果行"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                conn.commit()
                return rows
            finally:
                conn.close()

    def execute_batch(self, query: str, params_list: List[tuple]) -> bool:
        """批量执行同一条 SQL，共用一个连接"""
        if not params_list:
            return True
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executemany(query, params_list)
                conn.commit()
                return True
            except sqlite3.Error:
                return False
            finally:
                conn.close()

    def execute_many(self, query: str, params_list: List[tuple]) -> bool:
        """批量执行"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executemany(query, params_list)
                conn.commit()
                return True
            except sqlite3.Error:
                return False
            finally:
                conn.close()

    # === 语义化方法: player_memory ===

    def load_player_memory(self, observer_id: str, target_id: str) -> Optional[dict]:
        rows = self.execute(
            "SELECT data FROM player_memory WHERE observer_id=? AND target_id=?",
            (observer_id, target_id)
        )
        if rows:
            try:
                return json.loads(rows[0]["data"])
            except (json.JSONDecodeError, KeyError):
                return None
        return None

    def save_player_memory(self, observer_id: str, target_id: str, data: dict) -> bool:
        return self.execute(
            "INSERT OR REPLACE INTO player_memory (observer_id, target_id, data) VALUES (?, ?, ?)",
            (observer_id, target_id, json.dumps(data, ensure_ascii=False))
        ) is not None

    def load_all_player_memories(self, observer_id: str) -> Dict[str, dict]:
        rows = self.execute(
            "SELECT target_id, data FROM player_memory WHERE observer_id=?",
            (observer_id,)
        )
        result = {}
        for row in rows:
            try:
                result[row["target_id"]] = json.loads(row["data"])
            except (json.JSONDecodeError, KeyError):
                continue
        return result

    # === 语义化方法: statistics_memory ===

    def load_statistics(self, char_id: int) -> Optional[dict]:
        rows = self.execute(
            "SELECT data FROM statistics_memory WHERE char_id=?",
            (char_id,)
        )
        if rows:
            try:
                return json.loads(rows[0]["data"])
            except (json.JSONDecodeError, KeyError):
                return None
        return None

    def save_statistics(self, char_id: int, data: dict) -> bool:
        return self.execute(
            "INSERT OR REPLACE INTO statistics_memory (char_id, data) VALUES (?, ?)",
            (char_id, json.dumps(data, ensure_ascii=False))
        ) is not None
