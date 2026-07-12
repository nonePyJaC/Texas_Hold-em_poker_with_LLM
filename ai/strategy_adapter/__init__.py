"""StrategyAdapter — 策略适配器包

融合 Personality + Emotion + Memory + Relationship + 牌局上下文，
输出只读的 DynamicStrategyProfile 给 MCTS。

设计原则:
  - 不包含任何扑克牌算法 (MCTS、EV)
  - Emotion 只产生修正值，不直接控制动作
  - Memory 只提供影响因子，不存策略
  - 所有修正值都有范围限制 (±0.20)
  - 输出统一为 DynamicStrategyProfile

核心组件:
  StrategyContext       — 输入快照 (frozen, 只读)
  DynamicStrategyProfile — 输出对象 (frozen, 只读)
  EmotionModifier       — 情绪 → 修正值
  MemoryModifier        — 记忆 → 修正值
  RelationshipModifier  — 关系 → 修正值
  SituationModifier     — 牌局环境 → 修正值
  StrategyCalculator    — 融合逻辑
  StrategyAdapter        — 主适配器 (只组合不计算)
"""
from ai.strategy_adapter.context import StrategyContext
from ai.strategy_adapter.result import DynamicStrategyProfile
from ai.strategy_adapter.clamp import clamp_modifier, clamp_profile_value, RANGES, ModifierRange
from ai.strategy_adapter.modifiers import (
    EmotionModifier, MemoryModifier, RelationshipModifier, SituationModifier,
)
from ai.strategy_adapter.calculator import StrategyCalculator
from ai.strategy_adapter.adapter import StrategyAdapter
