"""StrategyAdapter — 主适配器

只组合不计算: 收集修正值 → 委托 Calculator 融合 → 输出 DynamicStrategyProfile
不包含任何扑克牌算法 (MCTS、EV)。
"""
from typing import Optional

from ai.strategy_adapter.context import StrategyContext
from ai.strategy_adapter.result import DynamicStrategyProfile
from ai.strategy_adapter.modifiers import (
    EmotionModifier, MemoryModifier, RelationshipModifier, SituationModifier,
)
from ai.strategy_adapter.calculator import StrategyCalculator


class StrategyAdapter:
    """策略适配器

    用法:
        adapter = StrategyAdapter()
        profile = adapter.adapt(ctx)
        # MCTS 读取 profile.aggression, profile.bluff_rate 等
    """

    def __init__(
        self,
        emotion_modifier: Optional[EmotionModifier] = None,
        memory_modifier: Optional[MemoryModifier] = None,
        relationship_modifier: Optional[RelationshipModifier] = None,
        situation_modifier: Optional[SituationModifier] = None,
        calculator: Optional[StrategyCalculator] = None,
    ):
        self.emotion_modifier = emotion_modifier or EmotionModifier()
        self.memory_modifier = memory_modifier or MemoryModifier()
        self.relationship_modifier = relationship_modifier or RelationshipModifier()
        self.situation_modifier = situation_modifier or SituationModifier()
        self.calculator = calculator or StrategyCalculator()

    def adapt(self, ctx: StrategyContext) -> DynamicStrategyProfile:
        """融合所有输入，输出动态策略画像

        流程:
        1. 各修正器独立提取修正值
        2. Calculator 融合基准值 + 修正值
        3. 返回只读 DynamicStrategyProfile
        """
        emo_mods = self.emotion_modifier.get_modifiers(ctx)
        mem_mods = self.memory_modifier.get_modifiers(ctx)
        rel_mods = self.relationship_modifier.get_modifiers(ctx)
        sit_mods = self.situation_modifier.get_modifiers(ctx)

        return self.calculator.calculate(ctx, emo_mods, mem_mods, rel_mods, sit_mods)
