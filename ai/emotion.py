"""AI 动态情绪引擎

为每个 AI 玩家维护实时情绪状态，影响决策和对话。
情绪维度: tilt / confidence / frustration / excitement
不修改现有 Personality 类，作为独立组件挂载到 Player 对象上。
"""
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EmotionState:
    """情绪状态，4 个维度 (0.0-1.0)"""
    tilt: float = 0.0           # 上头程度: 连续输牌/被诈唬后升高
    confidence: float = 0.5     # 自信心: 赢牌后升高
    frustration: float = 0.0    # 挫败感: 被反复加注/弃牌后升高
    excitement: float = 0.0     # 兴奋度: 大牌/全押局面升高

    def clamp(self):
        for f_name in ("tilt", "confidence", "frustration", "excitement"):
            v = getattr(self, f_name)
            setattr(self, f_name, max(0.0, min(1.0, v)))

    def to_dict(self) -> dict:
        return {
            "tilt": round(self.tilt, 3),
            "confidence": round(self.confidence, 3),
            "frustration": round(self.frustration, 3),
            "excitement": round(self.excitement, 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EmotionState":
        return cls(
            tilt=d.get("tilt", 0.0),
            confidence=d.get("confidence", 0.5),
            frustration=d.get("frustration", 0.0),
            excitement=d.get("excitement", 0.0),
        )

    def describe(self) -> str:
        parts = []
        if self.tilt > 0.6:
            parts.append("上头")
        elif self.tilt > 0.3:
            parts.append("烦躁")
        if self.confidence > 0.7:
            parts.append("自信")
        elif self.confidence < 0.3:
            parts.append("动摇")
        if self.frustration > 0.6:
            parts.append("挫败")
        if self.excitement > 0.6:
            parts.append("兴奋")
        return " ".join(parts) if parts else "平静"


# 事件类型常量
EVENT_WIN_POT = "win_pot"
EVENT_LOSE_POT = "lose_pot"
EVENT_LOSE_BIG = "lose_big"           # 输掉大牌（底池较大）
EVENT_BLUFFED = "bluffed"             # 被对手诈唬成功
EVENT_SUCCESSFUL_BLUFF = "successful_bluff"  # 自己诈唬成功
EVENT_CONSECUTIVE_FOLD = "consecutive_fold"  # 连续弃牌
EVENT_STRONG_HAND = "strong_hand"     # 拿到超强牌
EVENT_ALL_IN_SITUATION = "all_in"     # 全押局面
EVENT_FOLD_TO_AGGRO = "fold_to_aggro"  # 被对手加注后弃牌


class EmotionEngine:
    """动态情绪引擎

    用法:
        engine = EmotionEngine(personality)
        engine.on_event(EVENT_WIN_POT, {"pot_size": 500})
        state = engine.get_state()
        temp_personality = engine.apply_to_personality(base_personality)
        engine.decay(dt)
    """

    # 衰减速率（每秒）
    DECAY_RATES = {
        "tilt": 0.02,          # 上头衰减慢
        "confidence": 0.03,    # 自信衰减中等
        "frustration": 0.025,  # 挫败衰减中等
        "excitement": 0.08,    # 兴奋衰减快（短暂情绪）
    }

    def __init__(self, personality=None):
        self.state = EmotionState()
        self.personality = personality
        self._consecutive_folds = 0
        self._hands_since_win = 0
        self._last_update = time.time()

    def on_event(self, event_type: str, context: Optional[dict] = None):
        """处理游戏事件，更新情绪状态

        Args:
            event_type: 事件常量 (EVENT_*)
            context: 可选上下文，如 pot_size, hand_strength 等
        """
        context = context or {}
        p = self.personality

        # 性格影响情绪强度：激进型更容易上头，紧型更耐得住
        if p:
            tilt_multiplier = 0.7 + p.passive_aggressive * 0.6   # 激进型更容易 tilt
            calm_bonus = (1 - p.tight_loose) * 0.3               # 紧型更冷静
        else:
            tilt_multiplier = 1.0
            calm_bonus = 0.0

        if event_type == EVENT_WIN_POT:
            pot_size = context.get("pot_size", 0)
            big_win = pot_size > 500
            self.state.confidence += 0.12 + (0.08 if big_win else 0)
            self.state.excitement += 0.15 + (0.1 if big_win else 0)
            self.state.frustration = max(0.0, self.state.frustration - 0.15)
            self.state.tilt = max(0.0, self.state.tilt - 0.08)
            self._hands_since_win = 0

        elif event_type == EVENT_LOSE_POT:
            self._hands_since_win += 1
            self.state.confidence -= 0.05
            self.state.frustration += 0.05 * tilt_multiplier

        elif event_type == EVENT_LOSE_BIG:
            pot_size = context.get("pot_size", 0)
            severity = min(1.0, pot_size / 1000) if pot_size > 0 else 0.5
            self.state.tilt += (0.15 + 0.15 * severity) * tilt_multiplier
            self.state.confidence -= 0.1 + 0.05 * severity
            self.state.frustration += (0.12 + 0.08 * severity) * tilt_multiplier
            self._hands_since_win += 1

        elif event_type == EVENT_BLUFFED:
            # 被诈唬成功 — 最容易引发 tilt
            self.state.tilt += 0.2 * tilt_multiplier
            self.state.frustration += 0.15 * tilt_multiplier
            self.state.confidence -= 0.08

        elif event_type == EVENT_SUCCESSFUL_BLUFF:
            self.state.confidence += 0.1
            self.state.excitement += 0.12

        elif event_type == EVENT_CONSECUTIVE_FOLD:
            count = context.get("count", self._consecutive_folds)
            self._consecutive_folds = count
            if count >= 3:
                self.state.frustration += 0.06 * (count - 2) * tilt_multiplier
                self.state.confidence -= 0.03

        elif event_type == EVENT_STRONG_HAND:
            hand_strength = context.get("hand_strength", 0.8)
            self.state.excitement += 0.1 + 0.1 * hand_strength
            self.state.confidence += 0.05

        elif event_type == EVENT_ALL_IN_SITUATION:
            self.state.excitement += 0.15
            self.state.tilt += 0.03 * tilt_multiplier

        elif event_type == EVENT_FOLD_TO_AGGRO:
            self.state.frustration += 0.04 * tilt_multiplier
            self.state.confidence -= 0.02

        # 平静加成减少 tilt
        self.state.tilt = max(0.0, self.state.tilt - calm_bonus * 0.01)

        self.state.clamp()

    def reset_hand_counters(self):
        """每手牌开始时重置手内计数器（不重置情绪状态）"""
        self._consecutive_folds = 0

    def on_fold(self):
        """玩家弃牌时调用"""
        self._consecutive_folds += 1
        if self._consecutive_folds >= 3:
            self.on_event(EVENT_CONSECUTIVE_FOLD, {"count": self._consecutive_folds})

    def on_win(self, pot_size: int, is_bluff: bool = False):
        """赢得底池时调用"""
        self.on_event(EVENT_WIN_POT, {"pot_size": pot_size})
        if is_bluff:
            self.on_event(EVENT_SUCCESSFUL_BLUFF)
        self._consecutive_folds = 0

    def on_lose(self, pot_size: int, was_bluffed: bool = False):
        """输掉底池时调用"""
        big = pot_size > 500
        if was_bluffed:
            self.on_event(EVENT_BLUFFED)
        elif big:
            self.on_event(EVENT_LOSE_BIG, {"pot_size": pot_size})
        else:
            self.on_event(EVENT_LOSE_POT, {"pot_size": pot_size})
        self._consecutive_folds = 0

    def get_state(self) -> EmotionState:
        """获取当前情绪状态"""
        return self.state

    def apply_to_personality(self, base) -> "Personality":
        """根据当前情绪返回临时调整后的性格

        不修改原始 Personality 对象，返回一个新的实例。
        """
        from ai.personality import Personality

        s = self.state
        tilt = s.tilt
        confidence = s.confidence
        frustration = s.frustration
        excitement = s.excitement

        # tilt 高 → 更松、更爱诈唬、更爱跟注
        tight_loose = base.tight_loose + tilt * 0.2
        bluff_frequency = base.bluff_frequency + tilt * 0.15 + frustration * 0.08
        call_tendency = base.call_tendency + tilt * 0.12

        # confidence 高 → 更激进
        passive_aggressive = base.passive_aggressive + (confidence - 0.5) * 0.16

        # excitement 高 → 略微更激进
        passive_aggressive += excitement * 0.06

        # frustration 高 → 更爱诈唬（报复心理）
        bluff_frequency += frustration * 0.06

        # adaptivity 不受情绪影响

        return Personality(
            tight_loose=round(Personality._clamp(tight_loose), 2),
            passive_aggressive=round(Personality._clamp(passive_aggressive), 2),
            bluff_frequency=round(Personality._clamp(bluff_frequency), 2),
            call_tendency=round(Personality._clamp(call_tendency), 2),
            adaptivity=base.adaptivity,
        )

    def decay(self, dt: float):
        """时间衰减：情绪随时间自然回归

        Args:
            dt: 距上次 decay 的秒数
        """
        for field_name, rate in self.DECAY_RATES.items():
            v = getattr(self.state, field_name)
            # 向基准值衰减
            baseline = 0.5 if field_name == "confidence" else 0.0
            v += (baseline - v) * rate * dt
            setattr(self.state, field_name, v)

        self.state.clamp()
        self._last_update = time.time()

    def to_dict(self) -> dict:
        return {
            "state": self.state.to_dict(),
            "consecutive_folds": self._consecutive_folds,
            "hands_since_win": self._hands_since_win,
        }

    @classmethod
    def from_dict(cls, d: dict, personality=None) -> "EmotionEngine":
        engine = cls(personality)
        engine.state = EmotionState.from_dict(d.get("state", {}))
        engine._consecutive_folds = d.get("consecutive_folds", 0)
        engine._hands_since_win = d.get("hands_since_win", 0)
        return engine
