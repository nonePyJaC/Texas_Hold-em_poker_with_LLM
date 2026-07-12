"""AI 记忆系统

四层记忆架构:
  PlayerMemory       — 玩家行为统计 (SQLite)
  EpisodeMemory      — 重要牌局事件 (JSON, 仅关键事件)
  RelationshipMemory — AI 间关系标签 (JSON, 仅影响对话)
  StatisticsMemory   — 长期统计 (SQLite)

统一入口: MemoryManager
聚合接口: getStrategyContext() / getDialogueContext()
"""
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
from ai.memory.manager import MemoryManager, StrategyContext, DialogueContext
