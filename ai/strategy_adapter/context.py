"""StrategyContext — 策略适配器输入快照

frozen dataclass，上层构建后传入，Calculator 只读不写。
聚合 Personality + Emotion + Memory + 当前牌局上下文。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from ai.personality import Personality
from ai.emotion import EmotionState
from ai.memory.models import PlayerMemory, StatisticsMemory, RelationshipMemory


@dataclass(frozen=True)
class StrategyContext:
    """策略上下文快照 (只读)

    上层 (main.py) 负责从各系统填充。
    StrategyAdapter 和 Calculator 只消费此对象，不修改。
    """

    # === 基础性格 (基准值) ===
    personality: Personality = None

    # === 情绪状态 ===
    emotion_state: Optional[EmotionState] = None

    # === 记忆系统: 对手统计 ===
    opponent_stats: Dict[str, PlayerMemory] = field(default_factory=dict)
    self_stats: Optional[StatisticsMemory] = None

    # === 关系系统 (只提供影响因子，不直接控制策略) ===
    relationship: Optional[RelationshipMemory] = None

    # === 当前牌局上下文 (仅提供环境信息，不含算法) ===
    phase: str = ""                # "preflop" / "flop" / "turn" / "river"
    pot_size: int = 0
    hand_strength: float = 0.0    # 0.0-1.0
    is_all_in_situation: bool = False
    active_player_count: int = 2
    hand_number: int = 0

    # === 当前对手信息 ===
    opponent_id: str = ""
    opponent_name: str = ""

    # === 扩展预留 ===
    extra: Dict[str, Any] = field(default_factory=dict)
