"""PromptBuilder — 独立构建 LLM 提示词

拆成小方法，方便切模型时只改部分。
PromptBuilder 不调用模型、不做业务逻辑、不影响策略。
"""
from ai.dialogue_manager.context import DialogueContext


# 情绪标签 → 中文描述
_EMOTION_DESC = {
    "neutral": "平静",
    "happy": "开心",
    "angry": "愤怒",
    "tilt": "上头",
    "excited": "兴奋",
    "confident": "自信",
    "frustrated": "沮丧",
}

# 原型 → 自然语言描述
_ARCHETYPE_DESC = {
    "rock": "岩石型（稳健、紧、被动）",
    "tag": "紧激进型（谨慎底牌，但下注果断）",
    "lag": "松激进型（范围宽、爱加注）",
    "maniac": "疯狂型（爱玩大池、爱诈唬）",
    "calling_station": "跟注站（不爱弃牌、不爱加注）",
    "nit": "极紧型（只玩强牌）",
    "shark": "鲨鱼型（均衡、适应性强）",
    "beginner": "新手型（打法不稳定）",
}


class PromptBuilder:
    """LLM 提示词构建器"""

    def build_prompt(self, ctx: DialogueContext, emotion_tag: str, intensity: float) -> str:
        """构建完整提示词"""
        return "\n\n".join([
            self.build_system_prompt(ctx),
            self.build_character_prompt(ctx),
            self.build_emotion_prompt(ctx, emotion_tag, intensity),
            self.build_relationship_prompt(ctx),
            self.build_memory_prompt(ctx),
            self.build_cards_prompt(ctx),
            self.build_context_prompt(ctx),
            self.build_task_prompt(ctx, emotion_tag, intensity),
        ])

    def build_system_prompt(self, ctx: DialogueContext) -> str:
        """系统设定: 角色扮演框架"""
        return (
            "你是一个德州扑克 AI 角色的台词生成器。\n"
            "根据角色设定和当前情绪，生成一句符合角色性格的台词。\n"
            "要求：\n"
            "- 只输出台词本身，不要解释\n"
            "- 台词简短 (1-2句话，不超过50字)\n"
            "- 用中文\n"
            "- 不要给出任何策略建议或牌局分析\n"
            "- 台词要自然，像真人说话\n"
            "- 允许根据当前牌面诈唬，例如声称自己已成顺子/同花等，但绝对不要透露或暗示真实底牌的具体点数、花色或组合\n"
            "- 注意：台词中不能出现与德州扑克牌型大小规则矛盾的逻辑错误。牌型大小顺序为：高牌 < 一对 < 两对 < 三条 < 顺子 < 同花 < 葫芦 < 四条 < 同花顺。即使诈唬，也不能说\"两对能赢顺子\"这类错误的话"
        )

    def build_character_prompt(self, ctx: DialogueContext) -> str:
        """角色设定: 性格和原型"""
        parts = ["## 角色设定"]
        if ctx.char_name:
            parts.append(f"角色名: {ctx.char_name}")
        if ctx.char_description:
            parts.append(f"角色背景: {ctx.char_description}")

        if ctx.archetype:
            if ctx.archetype in _ARCHETYPE_DESC:
                parts.append(f"原型风格: {_ARCHETYPE_DESC[ctx.archetype]} (archetype: {ctx.archetype})")
            elif ctx.archetype == "random":
                parts.append("原型风格: 随机生成的综合风格，无固定原型")
            else:
                parts.append(f"原型风格: {ctx.archetype}")

        if ctx.personality:
            parts.append(f"性格概述: {ctx.personality.describe()}")
            parts.append(f"性格维度（数值越大越极端）:")
            parts.append(f"  松紧度: {ctx.personality.tight_loose:.1f} (0=范围很宽，1=只玩强牌)")
            parts.append(f"  激进性: {ctx.personality.passive_aggressive:.1f} (0=被动，1=激进)")
            parts.append(f"  诈唬倾向: {ctx.personality.bluff_frequency:.1f} (0=诚实，1=很爱诈唬)")
            parts.append(f"  跟注倾向: {ctx.personality.call_tendency:.1f} (0=容易弃牌，1=跟注站)")
        return "\n".join(parts)

    def build_emotion_prompt(self, ctx: DialogueContext, emotion_tag: str, intensity: float) -> str:
        """情绪上下文"""
        emo_desc = _EMOTION_DESC.get(emotion_tag, "平静")
        parts = ["## 当前情绪"]
        parts.append(f"情绪: {emo_desc}")
        parts.append(f"强度: {intensity:.1f} (0=轻微, 1=非常强烈)")

        if ctx.emotion_state:
            parts.append(f"上头程度: {ctx.emotion_state.tilt:.2f}")
            parts.append(f"自信心: {ctx.emotion_state.confidence:.2f}")
            parts.append(f"挫败感: {ctx.emotion_state.frustration:.2f}")
            parts.append(f"兴奋度: {ctx.emotion_state.excitement:.2f}")

        parts.append("注意: 情绪只影响语气和用词强度，不要反映策略变化。")
        return "\n".join(parts)

    def build_relationship_prompt(self, ctx: DialogueContext) -> str:
        """关系上下文 (只影响称呼和调侃)"""
        if not ctx.relationship or not ctx.opponent_name:
            return "## 对手关系\n无特殊关系"

        parts = ["## 对手关系"]
        parts.append(f"对手名: {ctx.opponent_name}")
        if ctx.relationship.tags:
            parts.append(f"关系标签: {', '.join(ctx.relationship.tags)}")
        parts.append(f"情感倾向: {ctx.relationship.sentiment:.1f} (-1=厌恶, 1=友好)")
        parts.append(f"交手次数: {ctx.relationship.hands_vs_target}")
        parts.append("注意: 关系只影响称呼和调侃语气，不影响台词内容的核心含义。")
        return "\n".join(parts)

    def build_memory_prompt(self, ctx: DialogueContext) -> str:
        """记忆上下文 (提供可引用的过往事件)"""
        parts = ["## 过往记忆"]
        if ctx.self_summary:
            parts.append(f"自我认知: {ctx.self_summary}")

        if ctx.recent_episodes:
            parts.append("近期重要事件 (按重要性排序):")
            for ep in ctx.recent_episodes[:3]:
                parts.append(f"  - [{ep.event_type}] {ep.description} (重要性:{ep.importance:.1f})")
        else:
            parts.append("无重要事件记录")

        parts.append("提示: 可以自然地引用过往事件，但不要生硬复述。")
        return "\n".join(parts)

    def build_cards_prompt(self, ctx: DialogueContext) -> str:
        """牌局信息 (仅用于语气参考)"""
        parts = ["## 当前牌局信息（仅作参考，可据此诈唬，但绝不要暴露真实底牌）"]
        if ctx.hole_cards:
            parts.append(f"你的真实底牌: {self._format_cards(ctx.hole_cards)} (仅限你知，不可对外泄露)")
        else:
            parts.append("你的真实底牌: 未知")
        if ctx.community_cards:
            parts.append(f"公共牌: {self._format_cards(ctx.community_cards)}")
        else:
            parts.append("公共牌: 尚未发出")
        return "\n".join(parts)

    def build_context_prompt(self, ctx: DialogueContext) -> str:
        """上下文信息：近期手牌结果 + 会话摘要 + 聊天历史（Token 优化版）"""
        parts = ["## 上下文"]

        # 会话摘要（压缩信息，1 行）
        if ctx.session_summary:
            parts.append(f"本局概况: {ctx.session_summary}")

        # 最近手牌结果（最多 5 手，压缩为 1 行）
        if ctx.recent_hand_results:
            results = list(ctx.recent_hand_results[-5:])
            parts.append(f"近期手牌: {' → '.join(results)}")
        elif ctx.last_hand_result:
            parts.append(f"上一局结果: {ctx.last_hand_result}")

        # 聊天历史（Token 优化：最多 5 条，超出则压缩）
        if ctx.chat_history:
            msgs = list(ctx.chat_history)
            if len(msgs) <= 5:
                parts.append("本局聊天记录:")
                for msg in msgs:
                    parts.append(f"  {msg}")
            else:
                # 保留最近 5 条，更早的压缩为摘要
                older = msgs[:-5]
                recent = msgs[-5:]
                parts.append(f"本局聊天记录（较早 {len(older)} 条已省略）:")
                for msg in recent:
                    parts.append(f"  {msg}")

        parts.append("提示: 可以自然地引用近期手牌和聊天内容，但不要生硬复述。")
        return "\n".join(parts)

    def build_task_prompt(self, ctx: DialogueContext, emotion_tag: str, intensity: float) -> str:
        """任务指令"""
        trigger_desc = {
            "think": "思考中，正在犹豫要不要继续",
            "fold": "弃牌了",
            "check": "过牌",
            "call": "跟注",
            "bet": "下注",
            "raise": "加注",
            "all_in": "全押",
            "win": "赢了这手",
            "lose": "输了这手",
        }
        action = trigger_desc.get(ctx.trigger, ctx.trigger)

        parts = ["## 任务"]
        parts.append(f"当前动作: {action}")
        if ctx.phase:
            parts.append(f"阶段: {ctx.phase}")
        if ctx.pot_size:
            parts.append(f"底池: {ctx.pot_size}")
        if ctx.is_all_in:
            parts.append("局面: 全押")
        if ctx.hand_strength:
            parts.append(f"手牌强度: {ctx.hand_strength:.1f}")

        emo_desc = _EMOTION_DESC.get(emotion_tag, "平静")
        parts.append(f"\n请生成一句{emo_desc}情绪下的台词，符合角色设定。")
        return "\n".join(parts)

    def build_reply_prompt(self, ctx: DialogueContext, human_message: str) -> str:
        """构建回复玩家聊天的提示词（返回 system+user 两段，便于正确喂给模型）"""
        system = self._build_reply_system_prompt()
        user = "\n\n".join([
            self._build_reply_character_user(ctx),
            self._build_cards_prompt(ctx),
            self._build_relationship_user(ctx),
            self._build_reply_context_user(ctx),
            self._build_reply_task_prompt(ctx, human_message),
        ])
        return system, user

    def _build_reply_system_prompt(self) -> str:
        """回复场景专用系统设定"""
        return (
            "你正在参与一场德州扑克游戏，需要扮演一个角色回应其他玩家的话。\n"
            "请只输出一句简短的中文台词（1-2句话，不超过50字），不要解释、不要策略建议。\n"
            "你可以根据当前牌面进行诈唬，例如声称自己已中顺子、同花等，但绝对不要透露或暗示真实底牌的具体点数、花色或组合。\n"
            "注意：回复中不能出现与德州扑克牌型大小规则矛盾的逻辑错误。牌型大小顺序为：高牌 < 一对 < 两对 < 三条 < 顺子 < 同花 < 葫芦 < 四条 < 同花顺。即使诈唬，也不能说\"两对能赢顺子\"这类错误的话"
        )

    def _build_reply_character_user(self, ctx: DialogueContext) -> str:
        """角色身份（放在 user 里，更自然）"""
        parts = [f"你扮演的角色: {ctx.char_name}"]
        if ctx.char_description:
            parts.append(f"角色背景: {ctx.char_description}")
        if ctx.archetype:
            if ctx.archetype in _ARCHETYPE_DESC:
                parts.append(f"原型风格: {_ARCHETYPE_DESC[ctx.archetype]} (archetype: {ctx.archetype})")
            elif ctx.archetype == "random":
                parts.append("原型风格: 随机生成的综合风格，无固定原型")
            else:
                parts.append(f"原型风格: {ctx.archetype}")
        if ctx.personality:
            parts.append(f"性格概述: {ctx.personality.describe()}")
            parts.append(
                f"性格维度: 松紧度{ctx.personality.tight_loose:.1f}, "
                f"激进性{ctx.personality.passive_aggressive:.1f}, "
                f"诈唬倾向{ctx.personality.bluff_frequency:.1f}"
            )
        return "\n".join(parts)

    def _build_cards_prompt(self, ctx: DialogueContext) -> str:
        """牌局信息 (仅用于语气参考)"""
        parts = ["当前牌局信息（仅作参考，可据此诈唬，但绝不要暴露真实底牌）:"]
        if ctx.hole_cards:
            parts.append(f"你的真实底牌: {self._format_cards(ctx.hole_cards)} (仅限你知，不可对外泄露)")
        else:
            parts.append("你的真实底牌: 未知")
        if ctx.community_cards:
            parts.append(f"公共牌: {self._format_cards(ctx.community_cards)}")
        else:
            parts.append("公共牌: 尚未发出")
        return "\n".join(parts)

    def _build_relationship_user(self, ctx: DialogueContext) -> str:
        """关系信息（user 里的自然描述）"""
        if not ctx.relationship or not ctx.opponent_name:
            return f"对手: {ctx.opponent_name or '玩家'}"
        tags = f"，关系: {', '.join(ctx.relationship.tags)}" if ctx.relationship.tags else ""
        sentiment = ctx.relationship.sentiment
        desc = "普通"
        if sentiment > 0.3:
            desc = "友好"
        elif sentiment < -0.3:
            desc = "敌对"
        return f"对手: {ctx.opponent_name}{tags}，态度{desc}（交手{ctx.relationship.hands_vs_target}次）"

    def _build_reply_context_user(self, ctx: DialogueContext) -> str:
        """上下文信息：近期手牌结果 + 会话摘要 + 聊天历史（回复路径，Token 优化）"""
        parts = ["上下文:"]
        if ctx.session_summary:
            parts.append(f"本局概况: {ctx.session_summary}")
        if ctx.recent_hand_results:
            results = list(ctx.recent_hand_results[-5:])
            parts.append(f"近期手牌: {' → '.join(results)}")
        elif ctx.last_hand_result:
            parts.append(f"上一局结果: {ctx.last_hand_result}")
        if ctx.chat_history:
            msgs = list(ctx.chat_history)
            if len(msgs) <= 5:
                parts.append("聊天记录:")
                for msg in msgs:
                    parts.append(f"  {msg}")
            else:
                recent = msgs[-5:]
                parts.append(f"聊天记录（最近 {len(recent)} 条）:")
                for msg in recent:
                    parts.append(f"  {msg}")
        return "\n".join(parts)

    def _build_reply_task_prompt(self, ctx: DialogueContext, human_message: str) -> str:
        """构建回复任务指令"""
        return f"对手对你说: \"{human_message}\"\n请用角色的语气回一句中文。"

    def _format_cards(self, cards) -> str:
        """将牌列表格式化为中文描述"""
        if not cards:
            return "无"
        suit_names = {'s': '黑桃', 'h': '红桃', 'd': '方块', 'c': '梅花'}
        rank_names = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
        for r in range(2, 11):
            rank_names[r] = str(r)
        parts = []
        for card in cards:
            rank = getattr(card, 'rank', None)
            suit = getattr(card, 'suit', None)
            if rank is None or suit is None:
                parts.append(str(card))
            else:
                parts.append(f"{suit_names.get(suit, suit)}{rank_names.get(rank, str(rank))}")
        return " ".join(parts)
