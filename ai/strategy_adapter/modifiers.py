"""modifiers — 各类修正器

每个修正器从特定输入源 (情绪/记忆/关系/牌局) 提取修正值。
所有修正值通过 clamp 限制范围，不直接控制动作。
"""
from ai.strategy_adapter.context import StrategyContext
from ai.strategy_adapter.clamp import clamp_modifier


class EmotionModifier:
    """情绪修正器 — 将情绪状态转化为策略修正值

    情绪只产生修正值 (如 aggression +0.1)，不直接控制动作。
    """

    def get_modifiers(self, ctx: StrategyContext) -> dict:
        """返回各维度的情绪修正值"""
        mods = {
            "aggression": 0.0, "bluff_rate": 0.0, "risk_tolerance": 0.0,
            "patience": 0.0, "confidence": 0.0, "looseness": 0.0,
            "tightness": 0.0, "adaptability": 0.0,
        }

        emo = ctx.emotion_state
        if not emo:
            return mods

        # tilt 高 → 更激进、更爱诈唬、更没耐心、风险承受降低
        tilt_factor = emo.tilt
        mods["aggression"] = clamp_modifier("aggression", tilt_factor * 0.20)
        mods["bluff_rate"] = clamp_modifier("bluff_rate", tilt_factor * 0.15)
        mods["patience"] = clamp_modifier("patience", -tilt_factor * 0.15)
        mods["risk_tolerance"] = clamp_modifier("risk_tolerance", -tilt_factor * 0.10)

        # confidence 高 → 更有耐心、风险承受略高
        conf_factor = emo.confidence - 0.5  # -0.5 ~ 0.5
        mods["confidence"] = clamp_modifier("confidence", conf_factor * 0.40)
        mods["patience"] += clamp_modifier("patience", conf_factor * 0.10)
        mods["risk_tolerance"] += clamp_modifier("risk_tolerance", conf_factor * 0.08)

        # frustration 高 → 更激进 (报复性打法)、更没耐心
        frust_factor = emo.frustration
        mods["aggression"] += clamp_modifier("aggression", frust_factor * 0.10)
        mods["patience"] += clamp_modifier("patience", -frust_factor * 0.08)

        # excitement 高 → 更激进、更爱诈唬
        excite_factor = emo.excitement
        mods["aggression"] += clamp_modifier("aggression", excite_factor * 0.08)
        mods["bluff_rate"] += clamp_modifier("bluff_rate", excite_factor * 0.05)

        # 重新 clamp 累加后的值
        for k in mods:
            mods[k] = clamp_modifier(k, mods[k])

        return mods


class MemoryModifier:
    """记忆修正器 — 从长期统计和对手行为提取修正值

    Memory 只提供影响因子，不存策略。
    """

    def get_modifiers(self, ctx: StrategyContext) -> dict:
        """返回各维度的记忆修正值"""
        mods = {
            "aggression": 0.0, "bluff_rate": 0.0, "risk_tolerance": 0.0,
            "patience": 0.0, "confidence": 0.0, "looseness": 0.0,
            "tightness": 0.0, "adaptability": 0.0,
        }

        # 自我统计: 根据近期胜率和趋势微调
        stats = ctx.self_stats
        if stats and stats.total_hands > 10:
            # 近期胜率高 → 自信提升
            if stats.recent_win_rate > 0.55:
                mods["confidence"] = clamp_modifier("confidence", 0.10)
            elif stats.recent_win_rate < 0.30:
                mods["confidence"] = clamp_modifier("confidence", -0.12)

            # 利润趋势
            if stats.recent_profit_trend == "down":
                mods["risk_tolerance"] = clamp_modifier("risk_tolerance", -0.08)
                mods["patience"] = clamp_modifier("patience", 0.05)
            elif stats.recent_profit_trend == "up":
                mods["risk_tolerance"] = clamp_modifier("risk_tolerance", 0.06)

        # 对手统计: 根据对手风格调整
        if ctx.opponent_id and ctx.opponent_stats:
            opp = ctx.opponent_stats.get(ctx.opponent_id)
            if opp and opp.total_hands >= 3:
                # 对手很松 → 我们可以更紧
                if opp.vpip > 0.6:
                    mods["looseness"] = clamp_modifier("looseness", -0.10)
                    mods["tightness"] = clamp_modifier("tightness", 0.10)
                # 对手很紧 → 我们可以更松、更爱诈唬
                elif opp.vpip < 0.25:
                    mods["looseness"] = clamp_modifier("looseness", 0.08)
                    mods["bluff_rate"] = clamp_modifier("bluff_rate", 0.10)

                # 对手爱弃牌 → 更爱诈唬
                if opp.fold_to_bet_rate > 0.5:
                    mods["bluff_rate"] += clamp_modifier("bluff_rate", 0.08)

                # 对手很激进 → 我们更有耐心 (等好牌反打)
                if opp.aggression_factor > 1.5:
                    mods["patience"] += clamp_modifier("patience", 0.08)
                    mods["aggression"] += clamp_modifier("aggression", -0.05)

                # 适应性: 对手数据越多，适应性修正越大
                if opp.total_hands > 20:
                    mods["adaptability"] = clamp_modifier("adaptability", 0.06)

        # 重新 clamp
        for k in mods:
            mods[k] = clamp_modifier(k, mods[k])

        return mods


class RelationshipModifier:
    """关系修正器 — 从关系系统提取修正值

    关系系统主要影响对话，但对策略有轻微影响:
    - 对 "tough" 对手更谨慎
    - 对 "easy_target" 对手更激进
    修正值很小 (±0.05)，不会颠覆性格。
    """

    def get_modifiers(self, ctx: StrategyContext) -> dict:
        """返回各维度的关系修正值"""
        mods = {
            "aggression": 0.0, "bluff_rate": 0.0, "risk_tolerance": 0.0,
            "patience": 0.0, "confidence": 0.0, "looseness": 0.0,
            "tightness": 0.0, "adaptability": 0.0,
        }

        rel = ctx.relationship
        if not rel or not rel.tags:
            return mods

        if "easy_target" in rel.tags:
            mods["aggression"] = clamp_modifier("aggression", 0.05)
            mods["bluff_rate"] = clamp_modifier("bluff_rate", 0.04)

        if "tough" in rel.tags:
            mods["aggression"] += clamp_modifier("aggression", -0.04)
            mods["patience"] = clamp_modifier("patience", 0.05)
            mods["risk_tolerance"] = clamp_modifier("risk_tolerance", -0.04)

        if "rival" in rel.tags:
            mods["aggression"] += clamp_modifier("aggression", 0.03)
            mods["bluff_rate"] += clamp_modifier("bluff_rate", 0.02)

        # 重新 clamp
        for k in mods:
            mods[k] = clamp_modifier(k, mods[k])

        return mods


class SituationModifier:
    """牌局环境修正器 — 根据当前牌局阶段和局势微调

    不含任何扑克算法，只根据阶段和全押状态做轻微调整。
    """

    def get_modifiers(self, ctx: StrategyContext) -> dict:
        """返回各维度的环境修正值"""
        mods = {
            "aggression": 0.0, "bluff_rate": 0.0, "risk_tolerance": 0.0,
            "patience": 0.0, "confidence": 0.0, "looseness": 0.0,
            "tightness": 0.0, "adaptability": 0.0,
        }

        # 全押局面: 风险承受提升 (已经全押了)
        if ctx.is_all_in_situation:
            mods["risk_tolerance"] = clamp_modifier("risk_tolerance", 0.05)
            mods["patience"] = clamp_modifier("patience", -0.05)

        # 后期阶段 (turn/river): 诈唬更有意义
        if ctx.phase in ("turn", "river"):
            mods["bluff_rate"] = clamp_modifier("bluff_rate", 0.03)

        # 短桌 (2-3人): 更松更激进
        if ctx.active_player_count <= 3:
            mods["looseness"] = clamp_modifier("looseness", 0.05)
            mods["aggression"] = clamp_modifier("aggression", 0.03)

        # 重新 clamp
        for k in mods:
            mods[k] = clamp_modifier(k, mods[k])

        return mods
