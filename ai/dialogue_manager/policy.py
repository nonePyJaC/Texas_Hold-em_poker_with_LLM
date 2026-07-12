"""SpeakPolicy — 决定何时说话、说话概率、情绪标签、时长

不包含任何牌局决策逻辑。
情绪只影响语气 (标签/强度/时长)，不影响策略。
"""
import random
from ai.dialogue_manager.context import DialogueContext


# 触发类型 → 基础说话概率
_BASE_PROBABILITY = {
    "think": 0.70,
    "fold": 0.60,
    "check": 0.50,
    "call": 0.65,
    "bet": 0.75,
    "raise": 0.75,
    "all_in": 0.85,
    "win": 0.80,
    "lose": 0.70,
}


class SpeakPolicy:
    """说话策略"""

    def should_speak(self, ctx: DialogueContext) -> bool:
        """根据触发类型和情绪决定是否说话

        情绪影响:
        - tilt 高 → 更爱说话 (+15%)
        - excitement 高 → 更爱说话 (+15%)
        - confidence 低 → 更爱抱怨 (+10%)
        """
        base = _BASE_PROBABILITY.get(ctx.trigger, 0.60)

        emo = ctx.emotion_state
        if emo:
            if emo.tilt > 0.4:
                base += 0.15
            if emo.excitement > 0.4:
                base += 0.15
            if emo.confidence < 0.3:
                base += 0.10

        base = min(base, 0.95)
        return random.random() < base

    def get_target_duration(self, ctx: DialogueContext) -> float:
        """根据情绪决定台词显示时长 (秒)

        - tilt 高 → 说话更长 (抱怨更多)
        - excitement 高 → 说话更短促 (兴奋)
        - 默认 3.5 秒
        """
        duration = 3.5
        emo = ctx.emotion_state
        if not emo:
            return duration

        if emo.tilt > 0.4:
            duration += 1.0       # 抱怨说更多
        if emo.frustration > 0.4:
            duration += 0.5       # 挫败感也多说点
        if emo.excitement > 0.5:
            duration -= 0.5       # 兴奋时短促
        if emo.confidence > 0.7:
            duration -= 0.3      # 自信时简洁

        # 全押局面加 1 秒
        if ctx.is_all_in:
            duration += 1.0

        return max(2.0, min(duration, 6.0))

    def get_emotion_tag(self, ctx: DialogueContext) -> str:
        """从情绪状态推导情绪标签

        优先级: tilt > excitement > frustration > confidence > neutral
        """
        emo = ctx.emotion_state
        if not emo:
            return "neutral"

        if emo.tilt > 0.5:
            return "tilt"
        if emo.excitement > 0.5:
            return "excited"
        if emo.frustration > 0.5:
            return "frustrated"
        if emo.confidence > 0.7:
            return "confident"
        if emo.tilt > 0.3 or emo.frustration > 0.3:
            return "angry"
        if ctx.trigger == "win":
            return "happy"
        return "neutral"

    def get_intensity(self, ctx: DialogueContext) -> float:
        """从情绪状态推导情绪强度 0.0-1.0

        取最强情绪维度的值。
        """
        emo = ctx.emotion_state
        if not emo:
            return 0.3
        return max(emo.tilt, emo.excitement, emo.frustration, abs(emo.confidence - 0.5) * 2)
