"""手牌历史 SQLite 存储

存储每手牌的完整日志（玩家、公共牌、动作历史、摊牌结果），
支持按时间倒序查询最近 N 手，供回放使用。
"""
import json
import os
import sqlite3
import threading
import time
from typing import List, Optional, Dict, Any


class HandHistoryDB:
    """手牌历史 SQLite 存储

    表结构:
      hand_logs: 每行一手牌的完整 JSON 日志
    """

    def __init__(self, db_path: str = "data/hand_history.db"):
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
                    CREATE TABLE IF NOT EXISTS hand_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        hand_number INTEGER NOT NULL,
                        timestamp TEXT NOT NULL,
                        session_id TEXT NOT NULL DEFAULT '',
                        data_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_hand_logs_timestamp
                        ON hand_logs(timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_hand_logs_hand_number
                        ON hand_logs(hand_number);
                """)
                conn.commit()
            finally:
                conn.close()

    def add_hand(self, hand_number: int, data: dict, session_id: str = "") -> int:
        """添加一条手牌日志，返回自增 ID"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        data_json = json.dumps(data, ensure_ascii=False)
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """INSERT INTO hand_logs (hand_number, timestamp, session_id, data_json)
                       VALUES (?, ?, ?, ?)""",
                    (hand_number, timestamp, session_id, data_json)
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.Error:
                return -1
            finally:
                conn.close()

    def get_recent_hands(self, count: int = 20) -> List[dict]:
        """获取最近 count 手牌的完整日志（按时间倒序）"""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT id, hand_number, timestamp, data_json FROM hand_logs "
                    "ORDER BY id DESC LIMIT ?",
                    (count,)
                ).fetchall()
                result = []
                for row in rows:
                    try:
                        data = json.loads(row["data_json"])
                        data["_log_id"] = row["id"]
                        data["_log_timestamp"] = row["timestamp"]
                        result.append(data)
                    except json.JSONDecodeError:
                        continue
                return result
            finally:
                conn.close()

    def get_hand_by_id(self, log_id: int) -> Optional[dict]:
        """按日志 ID 获取单条手牌"""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM hand_logs WHERE id = ?", (log_id,)
                ).fetchone()
                if not row:
                    return None
                try:
                    data = json.loads(row["data_json"])
                    data["_log_id"] = row["id"]
                    data["_log_timestamp"] = row["timestamp"]
                    return data
                except json.JSONDecodeError:
                    return None
            finally:
                conn.close()

    def count(self) -> int:
        """返回总记录数"""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT COUNT(*) as cnt FROM hand_logs").fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def clear_old(self, keep: int = 50):
        """只保留最近 keep 条记录，删除更早的"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM hand_logs WHERE id NOT IN "
                    "(SELECT id FROM hand_logs ORDER BY id DESC LIMIT ?)",
                    (keep,)
                )
                conn.commit()
            except sqlite3.Error:
                pass
            finally:
                conn.close()

    def get_recent_summaries(self, count: int = 50) -> List[dict]:
        """获取最近 count 手牌的摘要信息（不含完整动作，用于列表展示）"""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT id, hand_number, timestamp, data_json FROM hand_logs "
                    "ORDER BY id DESC LIMIT ?",
                    (count,)
                ).fetchall()
                result = []
                for row in rows:
                    try:
                        data = json.loads(row["data_json"])
                        result.append({
                            "log_id": row["id"],
                            "hand_number": data.get("hand_number", row["hand_number"]),
                            "timestamp": row["timestamp"],
                            "community_cards": data.get("community_cards", ""),
                            "pot_total": data.get("pot_total", 0),
                            "showdown": data.get("showdown", []),
                            "players": [p.get("name", "") for p in data.get("players", [])],
                        })
                    except json.JSONDecodeError:
                        continue
                return result
            finally:
                conn.close()
