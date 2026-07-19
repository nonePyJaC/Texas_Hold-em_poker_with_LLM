"""TableManager — 统一管理娱乐城中的所有牌桌

8张桌子统一管理，玩家和AI共同使用同一个场地。
玩家选桌入座时，该桌从后台模拟中移除；玩家离开后归还给后台。
"""
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TableState(Enum):
    IDLE = "idle"                # 空闲，无人
    BACKGROUND = "background"    # 后台AI模拟中
    PLAYER_ACTIVE = "player"     # 玩家正在该桌游戏


@dataclass
class PokerTable:
    """一张牌桌"""
    id: int
    name: str                    # 桌名（如"黄浦夜岸"）
    theme: str                   # 主题描述
    min_buyin: int = 500
    max_buyin: int = 2000
    blind_level: str = "10/20"
    capacity: int = 8
    state: TableState = TableState.IDLE
    current_players: int = 0     # 当前桌上人数（后台或玩家桌）


# 8张默认桌子的命名
DEFAULT_TABLES = [
    {"name": "黄浦夜岸", "theme": "外滩夜景，霓虹闪烁", "blind": "10/20"},
    {"name": "维加斯大道", "theme": "拉斯维加斯奢华风", "blind": "25/50"},
    {"name": "风暴酒馆", "theme": "海盗主题，木质装潢", "blind": "10/20"},
    {"name": "华尔街角", "theme": "金融街区，商务精英", "blind": "50/100"},
    {"name": "樱花亭", "theme": "日式庭院，静谧对弈", "blind": "5/10"},
    {"name": "皇家庄园", "theme": "欧式古典，金碧辉煌", "blind": "100/200"},
    {"name": "沙漠绿洲", "theme": "中东风情，神秘氛围", "blind": "25/50"},
    {"name": "极地冰屋", "theme": "北欧冰原，冷静博弈", "blind": "10/20"},
]


class TableManager:
    """统一管理所有牌桌的状态和分配"""

    def __init__(self, num_tables: int = 8):
        self._lock = threading.Lock()
        self._tables: dict[int, PokerTable] = {}
        for i, cfg in enumerate(DEFAULT_TABLES[:num_tables], start=1):
            self._tables[i] = PokerTable(
                id=i,
                name=cfg["name"],
                theme=cfg["theme"],
                blind_level=cfg["blind"],
            )

    def get_all_tables(self) -> list[PokerTable]:
        """返回所有桌子（线程安全）"""
        with self._lock:
            return list(self._tables.values())

    def get_table(self, table_id: int) -> Optional[PokerTable]:
        with self._lock:
            return self._tables.get(table_id)

    def get_free_table_ids(self) -> list[int]:
        """返回空闲或后台模拟中的桌号（可供分配）"""
        with self._lock:
            return [
                tid for tid, t in self._tables.items()
                if t.state in (TableState.IDLE, TableState.BACKGROUND)
            ]

    def get_background_table_ids(self) -> list[int]:
        """返回当前可用于后台模拟的桌号（仅空闲桌，排除玩家桌和已在模拟中的桌）"""
        with self._lock:
            return [
                tid for tid, t in self._tables.items()
                if t.state == TableState.IDLE
            ]

    def assign_to_player(self, table_id: Optional[int] = None) -> Optional[int]:
        """玩家选桌入座。可指定桌号，或 None 随机分配。返回桌号。"""
        with self._lock:
            if table_id is not None:
                t = self._tables.get(table_id)
                if t and t.state != TableState.PLAYER_ACTIVE:
                    t.state = TableState.PLAYER_ACTIVE
                    return table_id
                return None
            # 随机选一张非玩家桌
            candidates = [
                tid for tid, t in self._tables.items()
                if t.state != TableState.PLAYER_ACTIVE
            ]
            if not candidates:
                return None
            import random
            tid = random.choice(candidates)
            self._tables[tid].state = TableState.PLAYER_ACTIVE
            return tid

    def release_from_player(self, table_id: int):
        """玩家离开，桌子回到空闲"""
        with self._lock:
            t = self._tables.get(table_id)
            if t:
                t.state = TableState.IDLE
                t.current_players = 0

    def mark_background(self, table_id: int, player_count: int = 0):
        """标记桌子为后台模拟中"""
        with self._lock:
            t = self._tables.get(table_id)
            if t:
                t.state = TableState.BACKGROUND
                t.current_players = player_count

    def unmark_background(self, table_id: int):
        """后台模拟结束，桌子回到空闲"""
        with self._lock:
            t = self._tables.get(table_id)
            if t and t.state == TableState.BACKGROUND:
                t.state = TableState.IDLE
                t.current_players = 0

    def get_stats(self) -> dict:
        """返回统计信息（线程安全）"""
        with self._lock:
            active_bg = sum(1 for t in self._tables.values() if t.state == TableState.BACKGROUND)
            player_active = sum(1 for t in self._tables.values() if t.state == TableState.PLAYER_ACTIVE)
            idle = sum(1 for t in self._tables.values() if t.state == TableState.IDLE)
            bg_players = sum(t.current_players for t in self._tables.values() if t.state == TableState.BACKGROUND)
            return {
                "total_tables": len(self._tables),
                "background_tables": active_bg,
                "player_tables": player_active,
                "idle_tables": idle,
                "background_players": bg_players,
                "tables": [
                    {"id": t.id, "name": t.name, "state": t.state.value,
                     "players": t.current_players, "blind": t.blind_level}
                    for t in self._tables.values()
                ],
            }
