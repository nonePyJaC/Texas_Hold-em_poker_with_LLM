"""记忆系统数据模型

四层记忆:
  PlayerMemory       — 玩家行为统计 (SQLite)
  EpisodeMemory      — 重要牌局事件 (JSON)
  RelationshipMemory — AI 间关系标签 (JSON, 仅影响对话)
  StatisticsMemory   — 长期统计 (SQLite)
"""
from dataclasses import dataclass, field
from typing import List, Optional
import time
import uuid


@dataclass
class PlayerMemory:
    """玩家行为统计 — 记录观察者对目标玩家的行为模式"""
    target_id: str
    target_name: str = ""
    total_hands: int = 0
    # 基础统计
    vpip: float = 0.0                  # 入池率
    pfr: float = 0.0                   # 翻前加注率
    aggression_factor: float = 0.0     # 激进因子
    # 扩展统计
    fold_to_bet_rate: float = 0.0      # 面对下注的弃牌率
    raise_rate: float = 0.0            # 加注率
    bluff_success_rate: float = 0.0    # 诈唬成功率
    avg_bet_ratio: float = 0.0         # 平均下注占底池比例
    # 按阶段统计
    preflop_raise_rate: float = 0.0
    flop_cbet_rate: float = 0.0        # continuation bet 率
    turn_barrel_rate: float = 0.0
    # 内部计数器 (不序列化)
    _vpip_count: int = field(default=0, repr=False)
    _pfr_count: int = field(default=0, repr=False)
    _fold_to_bet_count: int = field(default=0, repr=False)
    _bet_faced_count: int = field(default=0, repr=False)
    _raise_count: int = field(default=0, repr=False)
    _action_count: int = field(default=0, repr=False)
    _bluff_success_count: int = field(default=0, repr=False)
    _bluff_attempt_count: int = field(default=0, repr=False)
    _bet_sum: float = field(default=0.0, repr=False)
    _bet_instances: int = field(default=0, repr=False)
    _preflop_raise_count: int = field(default=0, repr=False)
    _preflop_hand_count: int = field(default=0, repr=False)
    _flop_cbet_count: int = field(default=0, repr=False)
    _flop_cbet_opp_count: int = field(default=0, repr=False)
    _turn_barrel_count: int = field(default=0, repr=False)
    _turn_barrel_opp_count: int = field(default=0, repr=False)
    # 最近动作滑动窗口
    recent_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "total_hands": self.total_hands,
            "vpip": round(self.vpip, 3),
            "pfr": round(self.pfr, 3),
            "aggression_factor": round(self.aggression_factor, 3),
            "fold_to_bet_rate": round(self.fold_to_bet_rate, 3),
            "raise_rate": round(self.raise_rate, 3),
            "bluff_success_rate": round(self.bluff_success_rate, 3),
            "avg_bet_ratio": round(self.avg_bet_ratio, 3),
            "preflop_raise_rate": round(self.preflop_raise_rate, 3),
            "flop_cbet_rate": round(self.flop_cbet_rate, 3),
            "turn_barrel_rate": round(self.turn_barrel_rate, 3),
            "recent_actions": self.recent_actions[-20:],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlayerMemory":
        m = cls(target_id=d.get("target_id", ""))
        m.target_name = d.get("target_name", "")
        m.total_hands = d.get("total_hands", 0)
        m.vpip = d.get("vpip", 0.0)
        m.pfr = d.get("pfr", 0.0)
        m.aggression_factor = d.get("aggression_factor", 0.0)
        m.fold_to_bet_rate = d.get("fold_to_bet_rate", 0.0)
        m.raise_rate = d.get("raise_rate", 0.0)
        m.bluff_success_rate = d.get("bluff_success_rate", 0.0)
        m.avg_bet_ratio = d.get("avg_bet_ratio", 0.0)
        m.preflop_raise_rate = d.get("preflop_raise_rate", 0.0)
        m.flop_cbet_rate = d.get("flop_cbet_rate", 0.0)
        m.turn_barrel_rate = d.get("turn_barrel_rate", 0.0)
        m.recent_actions = d.get("recent_actions", [])
        return m


@dataclass
class EpisodeMemory:
    """重要牌局事件 — 只记录值得记住的关键手牌"""
    episode_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    hand_number: int = 0
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    phase: str = ""                    # "preflop" / "flop" / "turn" / "river" / "showdown"
    event_type: str = ""               # "big_win" / "bad_beat" / "successful_bluff" /
                                       # "bluffed_by" / "big_fold" / "all_in_call"
    description: str = ""              # 人类可读摘要
    pot_size: int = 0
    my_hand: str = ""                  # "AKs" / "QQ" 等
    opponent_id: str = ""
    opponent_name: str = ""
    my_action: str = ""
    outcome: str = ""                  # "won" / "lost" / "folded"
    chips_delta: int = 0
    importance: float = 0.5            # 0.0-1.0, 越高越值得提起

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "hand_number": self.hand_number,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "event_type": self.event_type,
            "description": self.description,
            "pot_size": self.pot_size,
            "my_hand": self.my_hand,
            "opponent_id": self.opponent_id,
            "opponent_name": self.opponent_name,
            "my_action": self.my_action,
            "outcome": self.outcome,
            "chips_delta": self.chips_delta,
            "importance": round(self.importance, 2),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EpisodeMemory":
        return cls(
            episode_id=d.get("episode_id", ""),
            hand_number=d.get("hand_number", 0),
            timestamp=d.get("timestamp", ""),
            phase=d.get("phase", ""),
            event_type=d.get("event_type", ""),
            description=d.get("description", ""),
            pot_size=d.get("pot_size", 0),
            my_hand=d.get("my_hand", ""),
            opponent_id=d.get("opponent_id", ""),
            opponent_name=d.get("opponent_name", ""),
            my_action=d.get("my_action", ""),
            outcome=d.get("outcome", ""),
            chips_delta=d.get("chips_delta", 0),
            importance=d.get("importance", 0.5),
        )


@dataclass
class RelationshipMemory:
    """AI 间关系标签 — 仅影响对话语气，不影响策略"""
    target_id: str = ""
    target_name: str = ""
    tags: List[str] = field(default_factory=list)
    sentiment: float = 0.0             # -1.0=厌恶 ~ 1.0=友好
    hands_vs_target: int = 0
    wins_vs_target: int = 0
    losses_vs_target: int = 0
    last_interaction: str = ""
    last_event: str = ""

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "tags": self.tags,
            "sentiment": round(self.sentiment, 3),
            "hands_vs_target": self.hands_vs_target,
            "wins_vs_target": self.wins_vs_target,
            "losses_vs_target": self.losses_vs_target,
            "last_interaction": self.last_interaction,
            "last_event": self.last_event,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RelationshipMemory":
        return cls(
            target_id=d.get("target_id", ""),
            target_name=d.get("target_name", ""),
            tags=d.get("tags", []),
            sentiment=d.get("sentiment", 0.0),
            hands_vs_target=d.get("hands_vs_target", 0),
            wins_vs_target=d.get("wins_vs_target", 0),
            losses_vs_target=d.get("losses_vs_target", 0),
            last_interaction=d.get("last_interaction", ""),
            last_event=d.get("last_event", ""),
        )


@dataclass
class StatisticsMemory:
    """长期统计 — 跨对局的角色画像"""
    char_id: int = 0
    total_hands: int = 0
    total_wins: int = 0
    total_profit: int = 0
    best_hand: str = ""
    biggest_pot_won: int = 0
    recent_win_rate: float = 0.0       # 最近 100 手
    recent_profit_trend: str = "stable"  # "up" / "down" / "stable"
    preferred_style: str = ""          # "tight_aggressive" 等
    vs_human_wins: int = 0
    vs_human_losses: int = 0
    vs_human_profit: int = 0

    def to_dict(self) -> dict:
        return {
            "char_id": self.char_id,
            "total_hands": self.total_hands,
            "total_wins": self.total_wins,
            "total_profit": self.total_profit,
            "best_hand": self.best_hand,
            "biggest_pot_won": self.biggest_pot_won,
            "recent_win_rate": round(self.recent_win_rate, 3),
            "recent_profit_trend": self.recent_profit_trend,
            "preferred_style": self.preferred_style,
            "vs_human_wins": self.vs_human_wins,
            "vs_human_losses": self.vs_human_losses,
            "vs_human_profit": self.vs_human_profit,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StatisticsMemory":
        return cls(
            char_id=d.get("char_id", 0),
            total_hands=d.get("total_hands", 0),
            total_wins=d.get("total_wins", 0),
            total_profit=d.get("total_profit", 0),
            best_hand=d.get("best_hand", ""),
            biggest_pot_won=d.get("biggest_pot_won", 0),
            recent_win_rate=d.get("recent_win_rate", 0.0),
            recent_profit_trend=d.get("recent_profit_trend", "stable"),
            preferred_style=d.get("preferred_style", ""),
            vs_human_wins=d.get("vs_human_wins", 0),
            vs_human_losses=d.get("vs_human_losses", 0),
            vs_human_profit=d.get("vs_human_profit", 0),
        )
