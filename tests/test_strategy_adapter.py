"""strategy_adapter 单元测试

覆盖:
  1. StrategyContext / DynamicStrategyProfile 不可变性
  2. 不同情绪 (neutral/confidence/tilt/fear/excitement) 修正值在范围内
  3. 对手松/紧/爱弃牌时 Memory 修正方向正确
  4. 关系标签 (easy_target/tough) 影响很小
  5. Clamp 能把越界数值拉回 0-1
  6. to_personality_dict 与现有 MCTS Personality 兼容
  7. 多次调用结果确定无随机波动
  8. 集成测试: Personality+Emotion+Memory+Relationship 整条链路产出 profile
"""
import unittest
from dataclasses import FrozenInstanceError

from ai.personality import Personality
from ai.emotion import EmotionState
from ai.memory.models import PlayerMemory, StatisticsMemory, RelationshipMemory
from ai.strategy_adapter import (
    StrategyContext, DynamicStrategyProfile, StrategyAdapter,
    EmotionModifier, MemoryModifier, RelationshipModifier, SituationModifier,
    StrategyCalculator, clamp_modifier, clamp_profile_value, RANGES,
)


def make_ctx(
    personality=None,
    emotion=None,
    opponent_stats=None,
    self_stats=None,
    relationship=None,
    phase="preflop",
    pot_size=0,
    hand_strength=0.0,
    is_all_in=False,
    active_players=6,
    opponent_id="opp1",
) -> StrategyContext:
    """辅助构建 StrategyContext"""
    return StrategyContext(
        personality=personality or Personality.from_archetype("tag"),
        emotion_state=emotion,
        opponent_stats=opponent_stats or {},
        self_stats=self_stats,
        relationship=relationship,
        phase=phase,
        pot_size=pot_size,
        hand_strength=hand_strength,
        is_all_in_situation=is_all_in,
        active_player_count=active_players,
        opponent_id=opponent_id,
    )


# ═══════════════════════════════════════════════════
# 1. 不可变性
# ═══════════════════════════════════════════════════
class TestImmutability(unittest.TestCase):

    def test_strategy_context_frozen(self):
        ctx = make_ctx()
        with self.assertRaises(FrozenInstanceError):
            ctx.phase = "river"

    def test_dynamic_strategy_profile_frozen(self):
        profile = DynamicStrategyProfile()
        with self.assertRaises(FrozenInstanceError):
            profile.aggression = 0.99

    def test_context_default_dict_isolated(self):
        """两个 context 的 default_factory dict 不共享"""
        ctx1 = make_ctx()
        ctx2 = make_ctx()
        ctx1.extra["x"] = 1
        self.assertNotIn("x", ctx2.extra)


# ═══════════════════════════════════════════════════
# 2. 情绪修正值范围
# ═══════════════════════════════════════════════════
class TestEmotionModifiers(unittest.TestCase):

    def _all_in_range(self, mods):
        for k, v in mods.items():
            r = RANGES.get(k)
            if r:
                self.assertGreaterEqual(v, r.min, f"{k}={v} < {r.min}")
                self.assertLessEqual(v, r.max, f"{k}={v} > {r.max}")
            else:
                self.assertGreaterEqual(v, -0.2, f"{k}={v}")
                self.assertLessEqual(v, 0.2, f"{k}={v}")

    def test_neutral_emotion_near_zero(self):
        """平静情绪 (tilt=0, confidence=0.5, frustration=0, excitement=0) → 修正≈0"""
        emo = EmotionState(tilt=0.0, confidence=0.5, frustration=0.0, excitement=0.0)
        ctx = make_ctx(emotion=emo)
        mods = EmotionModifier().get_modifiers(ctx)
        self._all_in_range(mods)
        for k, v in mods.items():
            self.assertAlmostEqual(v, 0.0, places=5, msg=f"{k} should be ~0 for neutral")

    def test_high_confidence(self):
        """高自信 → confidence 修正为正, patience 略正, risk_tolerance 略正"""
        emo = EmotionState(tilt=0.0, confidence=0.9, frustration=0.0, excitement=0.0)
        ctx = make_ctx(emotion=emo)
        mods = EmotionModifier().get_modifiers(ctx)
        self._all_in_range(mods)
        self.assertGreater(mods["confidence"], 0.0)
        self.assertGreater(mods["patience"], 0.0)
        self.assertGreater(mods["risk_tolerance"], 0.0)

    def test_tilt(self):
        """高 tilt → aggression 正, bluff_rate 正, patience 负, risk_tolerance 负"""
        emo = EmotionState(tilt=0.9, confidence=0.5, frustration=0.0, excitement=0.0)
        ctx = make_ctx(emotion=emo)
        mods = EmotionModifier().get_modifiers(ctx)
        self._all_in_range(mods)
        self.assertGreater(mods["aggression"], 0.0)
        self.assertGreater(mods["bluff_rate"], 0.0)
        self.assertLess(mods["patience"], 0.0)
        self.assertLess(mods["risk_tolerance"], 0.0)

    def test_fear(self):
        """恐惧 (frustration 高, confidence 低) → patience 降低, aggression 微增"""
        emo = EmotionState(tilt=0.0, confidence=0.2, frustration=0.8, excitement=0.0)
        ctx = make_ctx(emotion=emo)
        mods = EmotionModifier().get_modifiers(ctx)
        self._all_in_range(mods)
        # frustration 高 → aggression 正
        self.assertGreater(mods["aggression"], 0.0)
        # confidence 低 → confidence 修正为负
        self.assertLess(mods["confidence"], 0.0)

    def test_excitement(self):
        """兴奋 → aggression 正, bluff_rate 正"""
        emo = EmotionState(tilt=0.0, confidence=0.5, frustration=0.0, excitement=0.8)
        ctx = make_ctx(emotion=emo)
        mods = EmotionModifier().get_modifiers(ctx)
        self._all_in_range(mods)
        self.assertGreater(mods["aggression"], 0.0)
        self.assertGreater(mods["bluff_rate"], 0.0)

    def test_no_emotion_all_zero(self):
        """无 EmotionState → 所有修正值为 0"""
        ctx = make_ctx(emotion=None)
        mods = EmotionModifier().get_modifiers(ctx)
        for k, v in mods.items():
            self.assertEqual(v, 0.0, f"{k} should be 0 without emotion")


# ═══════════════════════════════════════════════════
# 3. Memory 修正方向
# ═══════════════════════════════════════════════════
class TestMemoryModifiers(unittest.TestCase):

    def _all_in_range(self, mods):
        for k, v in mods.items():
            r = RANGES.get(k)
            if r:
                self.assertGreaterEqual(v, r.min, f"{k}={v} < {r.min}")
                self.assertLessEqual(v, r.max, f"{k}={v} > {r.max}")

    def test_loose_opponent_we_tighter(self):
        """对手很松 (vpip>0.6) → looseness 负, tightness 正"""
        opp = PlayerMemory(target_id="opp1", total_hands=10, vpip=0.7)
        ctx = make_ctx(opponent_stats={"opp1": opp})
        mods = MemoryModifier().get_modifiers(ctx)
        self._all_in_range(mods)
        self.assertLess(mods["looseness"], 0.0, "vs loose opp, looseness should decrease")
        self.assertGreater(mods["tightness"], 0.0, "vs loose opp, tightness should increase")

    def test_tight_opponent_we_looser(self):
        """对手很紧 (vpip<0.25) → looseness 正, bluff_rate 正"""
        opp = PlayerMemory(target_id="opp1", total_hands=10, vpip=0.2)
        ctx = make_ctx(opponent_stats={"opp1": opp})
        mods = MemoryModifier().get_modifiers(ctx)
        self._all_in_range(mods)
        self.assertGreater(mods["looseness"], 0.0, "vs tight opp, looseness should increase")
        self.assertGreater(mods["bluff_rate"], 0.0, "vs tight opp, bluff_rate should increase")

    def test_fold_prone_opponent_more_bluff(self):
        """对手爱弃牌 (fold_to_bet_rate>0.5) → bluff_rate 正"""
        opp = PlayerMemory(target_id="opp1", total_hands=10, vpip=0.4, fold_to_bet_rate=0.6)
        ctx = make_ctx(opponent_stats={"opp1": opp})
        mods = MemoryModifier().get_modifiers(ctx)
        self._all_in_range(mods)
        self.assertGreater(mods["bluff_rate"], 0.0, "vs fold-prone opp, bluff_rate should increase")

    def test_no_opponent_stats_zero(self):
        """无对手统计 → 所有修正为 0"""
        ctx = make_ctx(opponent_stats={})
        mods = MemoryModifier().get_modifiers(ctx)
        for k, v in mods.items():
            self.assertEqual(v, 0.0, f"{k} should be 0 without opponent stats")

    def test_high_win_rate_confidence_up(self):
        """近期胜率高 → confidence 正"""
        stats = StatisticsMemory(total_hands=20, recent_win_rate=0.6)
        ctx = make_ctx(self_stats=stats)
        mods = MemoryModifier().get_modifiers(ctx)
        self.assertGreater(mods["confidence"], 0.0)

    def test_low_win_rate_confidence_down(self):
        """近期胜率低 → confidence 负"""
        stats = StatisticsMemory(total_hands=20, recent_win_rate=0.25)
        ctx = make_ctx(self_stats=stats)
        mods = MemoryModifier().get_modifiers(ctx)
        self.assertLess(mods["confidence"], 0.0)


# ═══════════════════════════════════════════════════
# 4. 关系修正影响很小
# ═══════════════════════════════════════════════════
class TestRelationshipModifiers(unittest.TestCase):

    def test_easy_target_small_aggression(self):
        rel = RelationshipMemory(target_id="opp1", tags=["easy_target"])
        ctx = make_ctx(relationship=rel)
        mods = RelationshipModifier().get_modifiers(ctx)
        self.assertGreater(mods["aggression"], 0.0)
        self.assertLessEqual(abs(mods["aggression"]), 0.05)
        self.assertGreater(mods["bluff_rate"], 0.0)
        self.assertLessEqual(abs(mods["bluff_rate"]), 0.05)

    def test_tough_more_patient(self):
        rel = RelationshipMemory(target_id="opp1", tags=["tough"])
        ctx = make_ctx(relationship=rel)
        mods = RelationshipModifier().get_modifiers(ctx)
        self.assertGreater(mods["patience"], 0.0)
        self.assertLess(mods["aggression"], 0.0)
        self.assertLessEqual(abs(mods["patience"]), 0.05)
        self.assertLessEqual(abs(mods["aggression"]), 0.05)

    def test_no_relationship_zero(self):
        ctx = make_ctx(relationship=None)
        mods = RelationshipModifier().get_modifiers(ctx)
        for k, v in mods.items():
            self.assertEqual(v, 0.0)

    def test_all_relationship_values_within_005(self):
        """所有关系修正值绝对值 ≤ 0.05"""
        for tags in [["easy_target"], ["tough"], ["rival"], ["easy_target", "tough"]]:
            rel = RelationshipMemory(target_id="opp1", tags=tags)
            ctx = make_ctx(relationship=rel)
            mods = RelationshipModifier().get_modifiers(ctx)
            for k, v in mods.items():
                self.assertLessEqual(
                    abs(v), 0.05,
                    f"{k}={v} exceeds 0.05 for tags={tags}"
                )


# ═══════════════════════════════════════════════════
# 5. Clamp 测试
# ═══════════════════════════════════════════════════
class TestClamp(unittest.TestCase):

    def test_clamp_modifier_upper(self):
        self.assertEqual(clamp_modifier("aggression", 0.5), 0.20)
        self.assertEqual(clamp_modifier("bluff_rate", 0.3), 0.15)

    def test_clamp_modifier_lower(self):
        self.assertEqual(clamp_modifier("aggression", -0.5), -0.20)
        self.assertEqual(clamp_modifier("patience", -0.3), -0.15)

    def test_clamp_modifier_unknown_default(self):
        self.assertEqual(clamp_modifier("unknown_dim", 0.5), 0.2)
        self.assertEqual(clamp_modifier("unknown_dim", -0.5), -0.2)

    def test_clamp_profile_value(self):
        self.assertEqual(clamp_profile_value(1.5), 1.0)
        self.assertEqual(clamp_profile_value(-0.5), 0.0)
        self.assertEqual(clamp_profile_value(0.5), 0.5)

    def test_profile_values_in_01(self):
        """极端输入后 profile 值仍在 0-1"""
        p = Personality.from_archetype("maniac")
        emo = EmotionState(tilt=1.0, confidence=1.0, frustration=1.0, excitement=1.0)
        opp = PlayerMemory(target_id="opp1", total_hands=30, vpip=0.8, fold_to_bet_rate=0.7, aggression_factor=2.0)
        stats = StatisticsMemory(total_hands=20, recent_win_rate=0.8, recent_profit_trend="up")
        rel = RelationshipMemory(target_id="opp1", tags=["easy_target", "rival"])
        ctx = make_ctx(
            personality=p, emotion=emo,
            opponent_stats={"opp1": opp}, self_stats=stats,
            relationship=rel, is_all_in=True, phase="river", active_players=2,
        )
        profile = StrategyAdapter().adapt(ctx)
        for field_name in ("aggression", "bluff_rate", "risk_tolerance",
                           "patience", "confidence", "looseness",
                           "tightness", "adaptability"):
            v = getattr(profile, field_name)
            self.assertGreaterEqual(v, 0.0, f"{field_name}={v} < 0")
            self.assertLessEqual(v, 1.0, f"{field_name}={v} > 1")


# ═══════════════════════════════════════════════════
# 6. to_personality_dict 兼容性
# ═══════════════════════════════════════════════════
class TestPersonalityDictCompat(unittest.TestCase):

    def test_has_5_fields(self):
        profile = DynamicStrategyProfile()
        d = profile.to_personality_dict()
        self.assertEqual(len(d), 5)

    def test_keys_match_personality(self):
        d = DynamicStrategyProfile().to_personality_dict()
        expected = {"tight_loose", "passive_aggressive", "bluff_frequency", "call_tendency", "adaptivity"}
        self.assertEqual(set(d.keys()), expected)

    def test_can_construct_personality(self):
        """to_personality_dict 的输出可以直接构造 Personality"""
        profile = DynamicStrategyProfile(
            aggression=0.7, bluff_rate=0.4, patience=0.6,
            looseness=0.55, adaptability=0.5,
        )
        d = profile.to_personality_dict()
        p = Personality.from_dict(d)
        self.assertAlmostEqual(p.passive_aggressive, 0.7)
        self.assertAlmostEqual(p.bluff_frequency, 0.4)
        self.assertAlmostEqual(p.call_tendency, 1.0 - 0.6)
        self.assertAlmostEqual(p.tight_loose, 0.55)
        self.assertAlmostEqual(p.adaptivity, 0.5)

    def test_all_values_in_01(self):
        profile = DynamicStrategyProfile(
            aggression=0.9, bluff_rate=0.8, risk_tolerance=0.7,
            patience=0.6, confidence=0.8, looseness=0.65,
            tightness=0.35, adaptability=0.5,
        )
        d = profile.to_personality_dict()
        for k, v in d.items():
            self.assertGreaterEqual(v, 0.0, f"{k}={v}")
            self.assertLessEqual(v, 1.0, f"{k}={v}")


# ═══════════════════════════════════════════════════
# 7. 确定性 — 多次调用无随机波动
# ═══════════════════════════════════════════════════
class TestDeterminism(unittest.TestCase):

    def test_same_input_same_output(self):
        p = Personality.from_archetype("lag")
        emo = EmotionState(tilt=0.5, confidence=0.7, frustration=0.3, excitement=0.4)
        opp = PlayerMemory(target_id="opp1", total_hands=15, vpip=0.5, fold_to_bet_rate=0.4)
        stats = StatisticsMemory(total_hands=20, recent_win_rate=0.5, recent_profit_trend="stable")
        rel = RelationshipMemory(target_id="opp1", tags=["rival"])

        results = []
        for _ in range(10):
            ctx = make_ctx(
                personality=p, emotion=emo,
                opponent_stats={"opp1": opp}, self_stats=stats,
                relationship=rel, phase="turn", active_players=4,
            )
            profile = StrategyAdapter().adapt(ctx)
            results.append(profile)

        base = results[0]
        for i, r in enumerate(results[1:], 1):
            for field_name in ("aggression", "bluff_rate", "risk_tolerance",
                               "patience", "confidence", "looseness",
                               "tightness", "adaptability",
                               "emotion_contribution", "memory_contribution",
                               "relationship_contribution"):
                self.assertEqual(
                    getattr(base, field_name), getattr(r, field_name),
                    f"Run {i}: {field_name} differs"
                )

    def test_modifier_deterministic(self):
        emo = EmotionState(tilt=0.6, confidence=0.3, frustration=0.5, excitement=0.2)
        ctx = make_ctx(emotion=emo)
        m = EmotionModifier()
        r1 = m.get_modifiers(ctx)
        r2 = m.get_modifiers(ctx)
        self.assertEqual(r1, r2)


# ═══════════════════════════════════════════════════
# 8. 集成测试 — 全链路
# ═══════════════════════════════════════════════════
class TestIntegration(unittest.TestCase):

    def test_full_chain_produces_valid_profile(self):
        """Personality + Emotion + Memory + Relationship → 合法 profile"""
        p = Personality.from_archetype("shark")
        emo = EmotionState(tilt=0.4, confidence=0.7, frustration=0.2, excitement=0.3)
        opp = PlayerMemory(target_id="opp1", total_hands=25, vpip=0.65, fold_to_bet_rate=0.3, aggression_factor=1.8)
        stats = StatisticsMemory(total_hands=30, recent_win_rate=0.55, recent_profit_trend="up")
        rel = RelationshipMemory(target_id="opp1", tags=["tough"], sentiment=-0.3)

        ctx = make_ctx(
            personality=p, emotion=emo,
            opponent_stats={"opp1": opp}, self_stats=stats,
            relationship=rel, phase="flop", pot_size=300,
            hand_strength=0.6, active_players=5,
        )
        adapter = StrategyAdapter()
        profile = adapter.adapt(ctx)

        # 基本类型检查
        self.assertIsInstance(profile, DynamicStrategyProfile)

        # 所有字段 0-1
        for field_name in ("aggression", "bluff_rate", "risk_tolerance",
                           "patience", "confidence", "looseness",
                           "tightness", "adaptability"):
            v = getattr(profile, field_name)
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

        # tightness = 1 - looseness
        self.assertAlmostEqual(profile.tightness, round(1.0 - profile.looseness, 3), places=2)

        # 贡献追踪 > 0 (有情绪和记忆输入)
        self.assertGreater(profile.emotion_contribution, 0.0)
        self.assertGreater(profile.memory_contribution, 0.0)
        self.assertGreater(profile.relationship_contribution, 0.0)

        # to_personality_dict 可构造 Personality
        d = profile.to_personality_dict()
        p2 = Personality.from_dict(d)
        self.assertAlmostEqual(p2.passive_aggressive, profile.aggression, places=2)

    def test_profile_does_not_mutate_personality(self):
        """adapt 不修改原始 Personality"""
        p = Personality.from_archetype("tag")
        original_agg = p.passive_aggressive
        emo = EmotionState(tilt=0.8, confidence=0.2, frustration=0.6, excitement=0.5)
        ctx = make_ctx(personality=p, emotion=emo)
        StrategyAdapter().adapt(ctx)
        self.assertEqual(p.passive_aggressive, original_agg)

    def test_adapter_does_not_affect_mcts_personality(self):
        """StrategyAdapter 输出可安全用于 MCTS 而不影响原 Personality"""
        original = Personality.from_archetype("tag")
        emo = EmotionState(tilt=0.7, confidence=0.3, frustration=0.5, excitement=0.6)
        ctx = make_ctx(personality=original, emotion=emo)
        adapter = StrategyAdapter()
        profile = adapter.adapt(ctx)

        # MCTS 可以用 to_personality_dict 构造临时 Personality
        temp_p = Personality.from_dict(profile.to_personality_dict())
        self.assertNotEqual(temp_p.passive_aggressive, original.passive_aggressive)

        # 原始 Personality 不受影响
        self.assertEqual(original.passive_aggressive, Personality.from_archetype("tag").passive_aggressive)

    def test_empty_context_still_works(self):
        """最小输入 (只有 personality) 也能产出合法 profile"""
        ctx = StrategyContext(
            personality=Personality.from_archetype("rock"),
            active_player_count=6,
        )
        profile = StrategyAdapter().adapt(ctx)
        self.assertIsInstance(profile, DynamicStrategyProfile)
        # 无情绪/记忆/关系 → 贡献为 0
        self.assertEqual(profile.emotion_contribution, 0.0)
        self.assertEqual(profile.memory_contribution, 0.0)
        self.assertEqual(profile.relationship_contribution, 0.0)
        # 值应接近原始 personality
        p = Personality.from_archetype("rock")
        self.assertAlmostEqual(profile.aggression, p.passive_aggressive, places=2)
        self.assertAlmostEqual(profile.bluff_rate, p.bluff_frequency, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
