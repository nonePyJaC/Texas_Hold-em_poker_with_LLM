"""DialogueContext — 对话上下文只读快照

frozen dataclass，上层构建后传入，Provider/Policy 只读不写。
调试时可以直接 print 整个对象，不用担心被意外修改。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ai.personality import Personality
from ai.emotion import EmotionState
from ai.memory.models import EpisodeMemory, RelationshipMemory


@dataclass(frozen=True)
class DialogueContext:
    """对话上下文快照 (只读)

    上层 (main.py) 负责从 EmotionEngine / MemoryManager / Game 状态填充。
    DialogueManager 和所有 Provider 只消费此对象，不修改。
    """

    # === 角色信息 ===
    char_id: int = 0
    char_name: str = ""
    char_description: str = ""     # 角色世界观描述 (供 LLM 理解角色身份)
    archetype: str = ""            # "rock" / "maniac" / "tag" 等
    personality: Personality = None  # 原始性格 (只读)

    # === 对话触发 ===
    trigger: str = ""              # "think" / "fold" / "call" / "bet" / "raise" / "all_in" / "win" / "lose"
    hand_strength: float = 0.0    # 0.0-1.0

    # === 情绪状态 (只影响语气，不影响策略) ===
    emotion_state: EmotionState = None

    # === 关系系统 (只影响称呼和调侃) ===
    relationship: Optional[RelationshipMemory] = None
    opponent_name: str = ""

    # === 记忆系统 (提供上下文引用) ===
    recent_episodes: Tuple[EpisodeMemory, ...] = field(default_factory=tuple)
    self_summary: str = ""         # "已打50手 赢20手..."

    # === 牌局信息 (仅用于台词内容，不用于决策) ===
    pot_size: int = 0
    phase: str = ""                # "preflop" / "flop" / "turn" / "river" / "showdown"
    is_all_in: bool = False
    hand_number: int = 0
    hole_cards: Tuple[Any, ...] = field(default_factory=tuple)       # AI 自己的底牌
    community_cards: Tuple[Any, ...] = field(default_factory=tuple)  # 当前公共牌

    # === 上下文增强 ===
    last_hand_result: str = ""     # 上一局结果描述，如 "赢了800筹码" / "弃牌" / "输了500筹码"
    chat_history: Tuple[str, ...] = field(default_factory=tuple)  # 本局聊天历史（格式："名字: 消息"）

    # === 扩展预留 ===
    extra: Dict[str, Any] = field(default_factory=dict)
