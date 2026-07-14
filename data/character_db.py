"""AI 角色池 SQLite 存储

替代原有的 characters.json，支持更大存储量、增量更新和快速查询。
首次启动时自动从 characters.json 迁移数据。
"""
import json
import os
import sqlite3
import threading
from typing import List, Optional, Dict, Any


class CharacterDB:
    """角色池 SQLite 存储

    表结构:
      characters: 每行一个 AI 角色，personality 和 opponent_memories 以 JSON 文本存储
    """

    def __init__(self, db_path: str = "data/characters.db"):
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
                    CREATE TABLE IF NOT EXISTS characters (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        archetype TEXT NOT NULL DEFAULT 'random',
                        personality_json TEXT NOT NULL,
                        bank INTEGER NOT NULL DEFAULT 10000,
                        hands_played INTEGER NOT NULL DEFAULT 0,
                        hands_won INTEGER NOT NULL DEFAULT 0,
                        total_profit INTEGER NOT NULL DEFAULT 0,
                        opponent_memories_json TEXT NOT NULL DEFAULT '{}',
                        debt INTEGER NOT NULL DEFAULT 0,
                        lender_id INTEGER NOT NULL DEFAULT -1
                    );
                    CREATE INDEX IF NOT EXISTS idx_characters_bank
                        ON characters(bank);
                """)
                conn.commit()
            finally:
                conn.close()

    def load_all(self) -> List[dict]:
        """加载所有角色，返回 dict 列表（兼容 AICharacter.from_dict 格式）"""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM characters ORDER BY id"
                ).fetchall()
                result = []
                for row in rows:
                    result.append({
                        "id": row["id"],
                        "name": row["name"],
                        "personality": json.loads(row["personality_json"]),
                        "archetype": row["archetype"],
                        "bank": row["bank"],
                        "hands_played": row["hands_played"],
                        "hands_won": row["hands_won"],
                        "total_profit": row["total_profit"],
                        "opponent_memories": json.loads(row["opponent_memories_json"]),
                        "debt": row["debt"],
                        "lender_id": row["lender_id"],
                    })
                return result
            finally:
                conn.close()

    def save_all(self, characters: List[dict]) -> bool:
        """批量保存所有角色（全量替换）"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM characters")
                params = []
                for c in characters:
                    params.append((
                        c["id"],
                        c["name"],
                        c.get("archetype", "random"),
                        json.dumps(c.get("personality", {}), ensure_ascii=False),
                        c.get("bank", 10000),
                        c.get("hands_played", 0),
                        c.get("hands_won", 0),
                        c.get("total_profit", 0),
                        json.dumps(c.get("opponent_memories", {}), ensure_ascii=False),
                        c.get("debt", 0),
                        c.get("lender_id", -1),
                    ))
                conn.executemany(
                    """INSERT OR REPLACE INTO characters
                       (id, name, archetype, personality_json, bank,
                        hands_played, hands_won, total_profit,
                        opponent_memories_json, debt, lender_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    params
                )
                conn.commit()
                return True
            except sqlite3.Error:
                return False
            finally:
                conn.close()

    def update_one(self, char_id: int, fields: Dict[str, Any]) -> bool:
        """增量更新单个角色的指定字段"""
        allowed = {
            "name", "archetype", "bank", "hands_played", "hands_won",
            "total_profit", "debt", "lender_id",
        }
        json_fields = {"personality", "opponent_memories"}

        sets = []
        params = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
            elif k in json_fields:
                sets.append(f"{k}_json = ?")
                params.append(json.dumps(v, ensure_ascii=False))

        if not sets:
            return False

        params.append(char_id)
        sql = f"UPDATE characters SET {', '.join(sets)} WHERE id = ?"

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(sql, params)
                conn.commit()
                return True
            except sqlite3.Error:
                return False
            finally:
                conn.close()

    def get_by_id(self, char_id: int) -> Optional[dict]:
        """查询单个角色"""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM characters WHERE id = ?", (char_id,)
                ).fetchone()
                if not row:
                    return None
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "personality": json.loads(row["personality_json"]),
                    "archetype": row["archetype"],
                    "bank": row["bank"],
                    "hands_played": row["hands_played"],
                    "hands_won": row["hands_won"],
                    "total_profit": row["total_profit"],
                    "opponent_memories": json.loads(row["opponent_memories_json"]),
                    "debt": row["debt"],
                    "lender_id": row["lender_id"],
                }
            finally:
                conn.close()

    def get_richest(self, count: int = 10, exclude_id: int = -1) -> List[dict]:
        """获取银行余额最高的角色"""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM characters WHERE id != ? AND bank > 0 "
                    "ORDER BY bank DESC LIMIT ?",
                    (exclude_id, count)
                ).fetchall()
                result = []
                for row in rows:
                    result.append({
                        "id": row["id"],
                        "name": row["name"],
                        "personality": json.loads(row["personality_json"]),
                        "archetype": row["archetype"],
                        "bank": row["bank"],
                        "hands_played": row["hands_played"],
                        "hands_won": row["hands_won"],
                        "total_profit": row["total_profit"],
                        "opponent_memories": json.loads(row["opponent_memories_json"]),
                        "debt": row["debt"],
                        "lender_id": row["lender_id"],
                    })
                return result
            finally:
                conn.close()

    def count(self) -> int:
        """返回角色总数"""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT COUNT(*) as cnt FROM characters").fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def migrate_from_json(self, json_path: str) -> int:
        """从 JSON 文件迁移数据到 SQLite，返回迁移数量"""
        if not os.path.exists(json_path):
            return 0
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return 0
            self.save_all(data)
            return len(data)
        except (json.JSONDecodeError, IOError, OSError):
            return 0
