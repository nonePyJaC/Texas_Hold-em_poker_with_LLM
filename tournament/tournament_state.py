"""锦标赛数据模型 — 阶段、桌、玩家状态"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from enum import Enum


class TournamentPhase(Enum):
    SETUP = "setup"           # 报名/分桌
    GROUP_STAGE = "group"     # 阶段1: 8桌×3人 短牌
    FINAL_STAGE = "final"     # 阶段2: 8人标准牌
    ULTIMATE_STAGE = "ultimate"  # 阶段3: ≤3人短牌
    FINISHED = "finished"     # 结束


@dataclass
class TournamentPlayer:
    """锦标赛参赛者"""
    char_id: int              # AI角色ID, -1 = 人类玩家
    name: str
    is_human: bool = False
    chips: int = 0            # 当前筹码
    table_id: int = 0         # 所在桌号 (0-7), 阶段2/3 固定为0
    eliminated: bool = False  # 是否被淘汰
    final_rank: int = 0       # 最终排名 (1=冠军)
    prize_won: int = 0        # 获得的奖金
    # AI 属性快照（用于重建 AI 大脑）
    archetype: str = "tag"
    personality_dict: dict = field(default_factory=dict)
    opponent_memories: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class TableInfo:
    """单桌信息"""
    table_id: int
    players: List[TournamentPlayer] = field(default_factory=list)
    hand_count: int = 0       # 已打局数
    finished: bool = False    # 该桌是否已决出胜者
    winner_id: Optional[int] = None  # 胜者的 char_id (-1=人类)

    def to_dict(self):
        return {
            "table_id": self.table_id,
            "players": [p.to_dict() for p in self.players],
            "hand_count": self.hand_count,
            "finished": self.finished,
            "winner_id": self.winner_id,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            table_id=d["table_id"],
            players=[TournamentPlayer.from_dict(p) for p in d.get("players", [])],
            hand_count=d.get("hand_count", 0),
            finished=d.get("finished", False),
            winner_id=d.get("winner_id"),
        )


class TournamentState:
    """锦标赛完整状态（可序列化存档）"""

    # 锦标赛常量
    BUY_IN = 5000
    TOTAL_PLAYERS = 24
    NUM_TABLES = 8
    PLAYERS_PER_TABLE = 3

    # 阶段1: 短牌, 最多30局, 盲注10/20
    GROUP_MAX_HANDS = 30
    GROUP_SMALL_BLIND = 10
    GROUP_BIG_BLIND = 20

    # 阶段2: 标准牌, 24局, 盲注25/50
    FINAL_MAX_HANDS = 24
    FINAL_SMALL_BLIND = 25
    FINAL_BIG_BLIND = 50

    # 阶段3: 短牌, 最多30局, 盲注50/100
    ULTIMATE_MAX_HANDS = 30
    ULTIMATE_SMALL_BLIND = 50
    ULTIMATE_BIG_BLIND = 100

    # 奖金
    PRIZE_FINAL_ELIMINATED = 3000   # 决赛圈出局者
    PRIZE_RUNNER_UP = 7500          # 最终局失败者
    PRIZE_CHAMPION_BONUS = 10000    # 冠军额外奖励

    def __init__(self):
        self.phase = TournamentPhase.SETUP
        self.players: List[TournamentPlayer] = []
        self.tables: List[TableInfo] = []
        self.current_table_id: int = 0   # 玩家当前桌 (阶段1)
        self.final_hand_count: int = 0   # 阶段2已打局数
        self.ultimate_hand_count: int = 0  # 阶段3已打局数
        self.champion_id: Optional[int] = None  # 冠军 char_id
        self.tournament_number: int = 1  # 第几届

    @property
    def human_player(self) -> Optional[TournamentPlayer]:
        for p in self.players:
            if p.is_human:
                return p
        return None

    @property
    def active_players(self) -> List[TournamentPlayer]:
        """未淘汰的玩家"""
        return [p for p in self.players if not p.eliminated]

    @property
    def total_pot(self) -> int:
        """当前总筹码池"""
        return sum(p.chips for p in self.players if not p.eliminated)

    def get_table(self, table_id: int) -> Optional[TableInfo]:
        for t in self.tables:
            if t.table_id == table_id:
                return t
        return None

    def get_player_by_id(self, char_id: int) -> Optional[TournamentPlayer]:
        for p in self.players:
            if p.char_id == char_id:
                return p
        return None

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "players": [p.to_dict() for p in self.players],
            "tables": [t.to_dict() for t in self.tables],
            "current_table_id": self.current_table_id,
            "final_hand_count": self.final_hand_count,
            "ultimate_hand_count": self.ultimate_hand_count,
            "champion_id": self.champion_id,
            "tournament_number": self.tournament_number,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TournamentState":
        state = cls()
        state.phase = TournamentPhase(d.get("phase", "setup"))
        state.players = [TournamentPlayer.from_dict(p) for p in d.get("players", [])]
        state.tables = [TableInfo.from_dict(t) for t in d.get("tables", [])]
        state.current_table_id = d.get("current_table_id", 0)
        state.final_hand_count = d.get("final_hand_count", 0)
        state.ultimate_hand_count = d.get("ultimate_hand_count", 0)
        state.champion_id = d.get("champion_id")
        state.tournament_number = d.get("tournament_number", 1)
        return state

    def save(self, filepath="data/tournament_save.json"):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath="data/tournament_save.json") -> Optional["TournamentState"]:
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @staticmethod
    def has_save(filepath="data/tournament_save.json") -> bool:
        return os.path.exists(filepath)

    @staticmethod
    def clear_save(filepath="data/tournament_save.json"):
        if os.path.exists(filepath):
            os.remove(filepath)
