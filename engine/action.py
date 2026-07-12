"""动作定义模块"""
from enum import Enum
from dataclasses import dataclass


class ActionType(Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass
class Action:
    """表示一个玩家动作"""
    player_index: int
    action_type: ActionType
    amount: int = 0  # 下注/加注金额（总投入差额）

    def __repr__(self):
        if self.amount > 0:
            return f"Player{self.player_index}: {self.action_type.value} {self.amount}"
        return f"Player{self.player_index}: {self.action_type.value}"
