"""MemoryManager — 记忆系统统一入口

聚合四层记忆，暴露语义化接口给上层。
核心聚合接口:
  getStrategyContext()  — 策略上下文 (统计 + 玩家行为)
  getDialogueContext()  — 对话上下文 (关系 + 事件)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time

from ai.memory.models import (
    PlayerMemory, EpisodeMemory, RelationshipMemory, StatisticsMemory
)
from ai.memory.storage import JSONStorage, SQLiteStorage
from ai.memory.player_memory import PlayerMemoryStore
from ai.memory.episode_memory import (
    EpisodeMemoryStore,
    EPISODE_BIG_WIN, EPISODE_BAD_BEAT, EPISODE_SUCCESSFUL_BLUFF,
    EPISODE_BLUFFED_BY, EPISODE_BIG_FOLD, EPISODE_ALL_IN_CALL,
)
from ai.memory.relationship_memory import (
    RelationshipMemoryStore,
    REL_EVENT_BEAT_THEM, REL_EVENT_LOST_TO_THEM,
    REL_EVENT_THEY_BLUFFED_ME, REL_EVENT_I_BLUFFED_THEM,
    REL_EVENT_BIG_POT_LOSS,
)
from ai.memory.statistics_memory import StatisticsMemoryStore


@dataclass
class StrategyContext:
    """策略上下文 — 供 AI 决策使用

    只包含统计数据，不包含关系/事件。
    """
    # 该角色对所有对手的行为统计
    opponent_stats: Dict[str, PlayerMemory] = field(default_factory=dict)
    # 该角色的长期统计
    self_stats: Optional[StatisticsMemory] = None
    # 简化的对手画像标签 (从 PlayerMemory 提取)
    opponent_profiles: Dict[str, str] = field(default_factory=dict)

    def get_opponent_profile(self, target_id: str) -> str:
        """获取对手画像描述"""
        return self.opponent_profiles.get(target_id, "unknown")

    def get_opponent_vpip(self, target_id: str) -> float:
        """获取对手入池率"""
        m = self.opponent_stats.get(target_id)
        return m.vpip if m else 0.5

    def get_opponent_aggression(self, target_id: str) -> float:
        """获取对手激进因子"""
        m = self.opponent_stats.get(target_id)
        return m.aggression_factor if m else 0.5

    def get_opponent_fold_to_bet(self, target_id: str) -> float:
        """获取对手面对下注的弃牌率"""
        m = self.opponent_stats.get(target_id)
        return m.fold_to_bet_rate if m else 0.3


@dataclass
class DialogueContext:
    """对话上下文 — 供对话系统使用

    只包含关系和事件，不包含策略统计。
    """
    # 该角色对所有对手的关系
    relationships: Dict[str, RelationshipMemory] = field(default_factory=dict)
    # 该角色的重要事件 (最近)
    recent_episodes: List[EpisodeMemory] = field(default_factory=list)
    # 与当前对手的最近事件
    opponent_episodes: List[EpisodeMemory] = field(default_factory=list)
    # 该角色的长期统计摘要 (用于自我认知对话)
    self_summary: str = ""

    def get_relationship_tags(self, target_id: str) -> List[str]:
        """获取对某对手的关系标签"""
        rel = self.relationships.get(target_id)
        return rel.tags if rel else []

    def get_sentiment(self, target_id: str) -> float:
        """获取对某对手的情感倾向"""
        rel = self.relationships.get(target_id)
        return rel.sentiment if rel else 0.0

    def has_recent_episode_with(self, target_id: str, event_type: str = "") -> bool:
        """是否有与某对手的特定类型最近事件"""
        for ep in self.opponent_episodes:
            if ep.opponent_id == target_id:
                if not event_type or ep.event_type == event_type:
                    return True
        return False

    def get_last_episode_description(self, target_id: str = "") -> str:
        """获取最近事件描述 (用于对话引用)"""
        if target_id:
            for ep in reversed(self.opponent_episodes):
                if ep.opponent_id == target_id:
                    return ep.description
        if self.recent_episodes:
            return self.recent_episodes[-1].description
        return ""


class MemoryManager:
    """记忆系统统一管理器

    用法:
        manager = MemoryManager()
        manager.record_action(observer_id, target_id, ...)
        manager.on_hand_end(char_id, hand_result)
        ctx = manager.getStrategyContext(char_id)
        dctx = manager.getDialogueContext(char_id, opponent_id)
    """

    def __init__(
        self,
        json_base_dir: str = "data/memory",
        sqlite_db_path: str = "data/memory/game.db",
    ):
        self.json_storage = JSONStorage(json_base_dir)
        self.sqlite_storage = SQLiteStorage(sqlite_db_path)

        self.player_store = PlayerMemoryStore(self.sqlite_storage)
        self.episode_store = EpisodeMemoryStore(self.json_storage)
        self.relationship_store = RelationshipMemoryStore(self.json_storage)
        self.statistics_store = StatisticsMemoryStore(self.sqlite_storage)

    # ==================== PlayerMemory ====================

    def record_action(
        self,
        observer_id: str,
        target_id: str,
        target_name: str,
        action_type: str,
        phase: str,
        is_preflop: bool,
        did_enter: bool,
        did_raise: bool,
        faced_bet: bool,
        bet_ratio: float = 0.0,
    ):
        """记录玩家行动 (语义化方法)"""
        self.player_store.record_action(
            observer_id, target_id, target_name,
            action_type, phase, is_preflop,
            did_enter, did_raise, faced_bet, bet_ratio,
        )

    def record_bluff_result(self, observer_id: str, target_id: str, success: bool):
        """记录诈唬结果"""
        self.player_store.record_bluff_result(observer_id, target_id, success)

    def get_player_memory(self, observer_id: str, target_id: str) -> Optional[PlayerMemory]:
        return self.player_store.get(observer_id, target_id)

    def get_all_player_memories(self, observer_id: str) -> Dict[str, PlayerMemory]:
        return self.player_store.get_all(observer_id)

    # ==================== EpisodeMemory ====================

    def record_event(self, char_id: int, episode: EpisodeMemory) -> bool:
        """记录重要事件 (语义化方法)

        自动过滤非重要事件。
        """
        return self.episode_store.record_event(char_id, episode)

    def get_episodes(self, char_id: int, limit: int = 20, by_importance: bool = False) -> List[EpisodeMemory]:
        return self.episode_store.get_episodes(char_id, limit, by_importance=by_importance)

    def get_episodes_with_opponent(
        self, char_id: int, opponent_id: str, limit: int = 5, by_importance: bool = False
    ) -> List[EpisodeMemory]:
        return self.episode_store.get_recent_episodes(char_id, opponent_id, limit, by_importance=by_importance)

    # ==================== RelationshipMemory ====================

    def update_relationship(
        self,
        char_id: int,
        target_id: str,
        target_name: str,
        event: str,
        won: bool = False,
        lost: bool = False,
    ):
        """更新关系 (语义化方法)"""
        self.relationship_store.update_relationship(
            char_id, target_id, target_name, event, won, lost
        )

    def get_relationship(self, char_id: int, target_id: str) -> Optional[RelationshipMemory]:
        return self.relationship_store.get(char_id, target_id)

    def get_all_relationships(self, char_id: int) -> Dict[str, RelationshipMemory]:
        return self.relationship_store.get_all(char_id)

    # ==================== StatisticsMemory ====================

    def get_statistics(self, char_id: int) -> StatisticsMemory:
        return self.statistics_store.get(char_id)

    def update_statistics(
        self,
        char_id: int,
        won: bool,
        profit: int,
        pot_size: int = 0,
        hand_rank_name: str = "",
        vs_human: bool = False,
    ):
        """更新长期统计"""
        self.statistics_store.update_after_hand(
            char_id, won, profit, pot_size, hand_rank_name, vs_human
        )

    # ==================== 聚合接口 ====================

    def getStrategyContext(self, char_id: int, observer_id: str = "") -> StrategyContext:
        """获取策略上下文

        供 AI 决策使用，只包含统计数据。
        """
        ctx = StrategyContext()
        # 使用 char_id 作为 observer_id (与 character_pool 一致)
        oid = observer_id or str(char_id)
        ctx.opponent_stats = self.get_all_player_memories(oid)
        ctx.self_stats = self.get_statistics(char_id)

        # 从 PlayerMemory 提取简化画像
        for tid, m in ctx.opponent_stats.items():
            ctx.opponent_profiles[tid] = self._profile_from_memory(m)

        return ctx

    def getDialogueContext(
        self,
        char_id: int,
        opponent_id: str = "",
        observer_id: str = "",
    ) -> DialogueContext:
        """获取对话上下文

        供对话系统使用，只包含关系和事件。
        """
        ctx = DialogueContext()
        ctx.relationships = self.get_all_relationships(char_id)
        ctx.recent_episodes = self.get_episodes(char_id, limit=10, by_importance=True)
        if opponent_id:
            ctx.opponent_episodes = self.get_episodes_with_opponent(char_id, opponent_id, limit=5, by_importance=True)

        # 生成自我认知摘要
        stats = self.get_statistics(char_id)
        ctx.self_summary = self._build_self_summary(stats)

        return ctx

    def _profile_from_memory(self, m: PlayerMemory) -> str:
        """从 PlayerMemory 提取简化画像"""
        if m.total_hands < 3:
            return "unknown"
        parts = []
        if m.vpip > 0.6:
            parts.append("loose")
        elif m.vpip < 0.25:
            parts.append("tight")
        else:
            parts.append("standard")

        if m.aggression_factor > 1.5:
            parts.append("aggressive")
        elif m.aggression_factor < 0.5:
            parts.append("passive")

        if m.fold_to_bet_rate > 0.6:
            parts.append("folds_often")

        return "_".join(parts) if parts else "unknown"

    def _build_self_summary(self, stats: StatisticsMemory) -> str:
        """构建角色自我认知摘要"""
        if stats.total_hands < 1:
            return ""
        parts = [f"已打{stats.total_hands}手"]
        if stats.total_wins > 0:
            parts.append(f"赢{stats.total_wins}手")
        if stats.total_profit != 0:
            sign = "+" if stats.total_profit > 0 else ""
            parts.append(f"盈亏{sign}{stats.total_profit}")
        if stats.best_hand:
            parts.append(f"最佳牌型{stats.best_hand}")
        return " ".join(parts)

    # ==================== 批量操作 ====================

    def on_hand_end(
        self,
        char_id: int,
        observer_id: str,
        won: bool,
        profit: int,
        pot_size: int = 0,
        hand_rank_name: str = "",
        vs_human: bool = False,
        opponent_id: str = "",
        opponent_name: str = "",
        event_type: str = "",
        episode_description: str = "",
        my_hand: str = "",
        my_action: str = "",
        phase: str = "showdown",
    ):
        """每手结束后的批量更新

        统一更新四层记忆。
        """
        # 1. 更新长期统计
        self.update_statistics(char_id, won, profit, pot_size, hand_rank_name, vs_human)

        # 2. 更新关系
        if opponent_id:
            event = REL_EVENT_BEAT_THEM if won else REL_EVENT_LOST_TO_THEM
            self.update_relationship(
                char_id, opponent_id, opponent_name, event, won=won, lost=not won
            )

        # 3. 记录重要事件
        if event_type and episode_description:
            episode = EpisodeMemory(
                phase=phase,
                event_type=event_type,
                description=episode_description,
                pot_size=pot_size,
                my_hand=my_hand,
                opponent_id=opponent_id,
                opponent_name=opponent_name,
                my_action=my_action,
                outcome="won" if won else "lost",
                chips_delta=profit,
            )
            self.record_event(char_id, episode)

        # 4. 更新玩家行为统计 (finalize)
        if opponent_id:
            self.player_store.finalize_hand(observer_id, opponent_id)

    def save_all(self):
        """持久化所有缓存到磁盘"""
        self.player_store.save_all()
        self.statistics_store.save_all()
