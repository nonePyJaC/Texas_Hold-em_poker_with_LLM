"""calculator — 融合逻辑

将 Personality 基准值 + 各修正器的修正值融合为最终策略参数。
不包含任何扑克算法。
"""
from ai.strategy_adapter.context import StrategyContext
from ai.strategy_adapter.result import DynamicStrategyProfile
from ai.strategy_adapter.clamp import clamp_profile_value


class StrategyCalculator:
    """策略融合计算器

    职责: 基准值 + 修正值 → 最终值，然后 clamp 到 0.0-1.0
    """

    def calculate(
        self,
        ctx: StrategyContext,
        emotion_mods: dict,
        memory_mods: dict,
        relationship_mods: dict,
        situation_mods: dict,
    ) -> DynamicStrategyProfile:
        """融合所有修正值，输出 DynamicStrategyProfile

        流程:
        1. 从 Personality 提取基准值
        2. 叠加所有修正值
        3. clamp 到 0.0-1.0
        4. 计算 tightness = 1.0 - looseness
        """
        p = ctx.personality

        # 基准值来自 Personality
        base_aggression = p.passive_aggressive if p else 0.5
        base_bluff = p.bluff_frequency if p else 0.3
        base_risk = 0.5  # Personality 没有直接对应字段，用中间值
        base_patience = (1.0 - p.call_tendency) if p else 0.5
        base_confidence = 0.5  # 没有直接对应字段
        base_looseness = p.tight_loose if p else 0.5
        base_adaptability = p.adaptivity if p else 0.3

        # 叠加修正值
        agg_mods = [emotion_mods, memory_mods, relationship_mods, situation_mods]

        final_aggression = base_aggression + sum(m.get("aggression", 0) for m in agg_mods)
        final_bluff = base_bluff + sum(m.get("bluff_rate", 0) for m in agg_mods)
        final_risk = base_risk + sum(m.get("risk_tolerance", 0) for m in agg_mods)
        final_patience = base_patience + sum(m.get("patience", 0) for m in agg_mods)
        final_confidence = base_confidence + sum(m.get("confidence", 0) for m in agg_mods)
        final_looseness = base_looseness + sum(m.get("looseness", 0) for m in agg_mods)
        final_adaptability = base_adaptability + sum(m.get("adaptability", 0) for m in agg_mods)

        # clamp 到 0.0-1.0
        final_aggression = clamp_profile_value(final_aggression)
        final_bluff = clamp_profile_value(final_bluff)
        final_risk = clamp_profile_value(final_risk)
        final_patience = clamp_profile_value(final_patience)
        final_confidence = clamp_profile_value(final_confidence)
        final_looseness = clamp_profile_value(final_looseness)
        final_adaptability = clamp_profile_value(final_adaptability)
        final_tightness = clamp_profile_value(1.0 - final_looseness)

        # 追踪各来源贡献量 (调试用)
        emo_total = sum(abs(v) for v in emotion_mods.values())
        mem_total = sum(abs(v) for v in memory_mods.values())
        rel_total = sum(abs(v) for v in relationship_mods.values())

        return DynamicStrategyProfile(
            aggression=round(final_aggression, 3),
            bluff_rate=round(final_bluff, 3),
            risk_tolerance=round(final_risk, 3),
            patience=round(final_patience, 3),
            confidence=round(final_confidence, 3),
            looseness=round(final_looseness, 3),
            tightness=round(final_tightness, 3),
            adaptability=round(final_adaptability, 3),
            emotion_contribution=round(emo_total, 3),
            memory_contribution=round(mem_total, 3),
            relationship_contribution=round(rel_total, 3),
        )
