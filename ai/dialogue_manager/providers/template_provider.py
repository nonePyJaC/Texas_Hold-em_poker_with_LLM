"""TemplateProvider — 模板台词提供者

通过薄适配层调用现有 dialogue.py，不直接依赖其内部结构。
以后换模板来源 (JSON/YAML/DB) 只需替换适配层，Provider 不动。
"""
import random
from typing import Optional

from ai.dialogue_manager.context import DialogueContext
from ai.dialogue_manager.providers.base import DialogueProvider


# === 薄适配层 ===

class TemplateSource:
    """模板台词源适配层

    当前包装现有 dialogue.py 的函数调用。
    以后换 JSON/YAML/DB 只需实现相同接口，Provider 不用改。
    """

    def get_line(
        self,
        personality,
        context: str,
        archetype: Optional[str] = None,
        name: Optional[str] = None,
        hand_strength: Optional[float] = None,
    ) -> Optional[str]:
        """获取模板台词"""
        from ai.dialogue import get_dialogue
        return get_dialogue(personality, context, archetype, name, hand_strength)

    def get_action_line(
        self,
        personality,
        action_key: str,
        archetype: Optional[str] = None,
        name: Optional[str] = None,
        hand_strength: Optional[float] = None,
    ) -> Optional[str]:
        """获取行动台词"""
        from ai.dialogue import get_dialogue
        return get_dialogue(personality, action_key, archetype, name, hand_strength)


# === Provider ===

class TemplateProvider(DialogueProvider):
    """模板台词提供者

    包装 TemplateSource，根据 DialogueContext 选择合适的台词。
    情绪和关系只影响称呼修饰，不影响台词选择逻辑。
    """

    def __init__(self, source: Optional[TemplateSource] = None):
        self.source = source or TemplateSource()

    def generate(self, ctx: DialogueContext, emotion_tag: str, intensity: float) -> Optional[str]:
        """根据上下文生成模板台词"""
        line = None

        # 慢打时伪装手牌强度：向台词系统报告弱牌强度
        effective_strength = ctx.hand_strength
        if ctx.is_slow_playing and ctx.hand_strength > 0.7:
            effective_strength = 0.35  # 伪装成中等弱牌

        if ctx.trigger == "think":
            line = self.source.get_line(
                ctx.personality, "think",
                archetype=ctx.archetype or None,
                name=ctx.char_name or None,
                hand_strength=effective_strength or None,
            )
        elif ctx.trigger in ("fold", "check", "call", "bet", "raise", "all_in"):
            line = self.source.get_action_line(
                ctx.personality, ctx.trigger,
                archetype=ctx.archetype or None,
                name=ctx.char_name or None,
                hand_strength=effective_strength or None,
            )
        elif ctx.trigger == "win":
            line = self.source.get_line(
                ctx.personality, "bet",
                archetype=ctx.archetype or None,
                name=ctx.char_name or None,
                hand_strength=0.9,
            )
        elif ctx.trigger == "lose":
            line = self.source.get_line(
                ctx.personality, "fold",
                archetype=ctx.archetype or None,
                name=ctx.char_name or None,
                hand_strength=0.1,
            )

        # 关系系统: 根据标签添加称呼修饰
        if line and ctx.relationship and ctx.opponent_name:
            line = self._apply_relationship_modifier(line, ctx)

        return line

    def is_available(self) -> bool:
        return True

    def _apply_relationship_modifier(self, line: str, ctx: DialogueContext) -> str:
        """根据关系标签修饰台词 (只影响称呼和调侃，不影响内容)"""
        tags = ctx.relationship.tags
        opponent = ctx.opponent_name

        # 只在部分台词后追加修饰，避免每句都加
        if random.random() < 0.3:
            if "easy_target" in tags:
                prefixes = [f" {opponent}，", f" 嘿，{opponent}，"]
                return random.choice(prefixes) + line
            elif "rival" in tags:
                suffixes = [f" — {opponent}，你看到了吗？", f" 学着点，{opponent}。"]
                return line + random.choice(suffixes)
            elif "tough" in tags:
                suffixes = [f" 不过{opponent}确实难缠。", f" {opponent}，别得意。"]
                return line + random.choice(suffixes)

        return line
