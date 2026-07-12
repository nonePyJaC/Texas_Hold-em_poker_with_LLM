"""对话上下文构建器"""
from ai.dialogue_manager import DialogueContext
from ai.character_descriptions import get_description as get_char_description
from ai.character_pool import HUMAN_OPPONENT_KEY


class DialogueContextBuilder:
    """为 AI 对话构建 DialogueContext 快照"""

    @staticmethod
    def build(app, player, trigger, hand_strength=None):
        """构建对话上下文快照 (只读)"""
        # 确定对手
        opponent_name = ""
        opponent_id = ""
        rel = None
        for other in app.players:
            if other.seat_index != player.seat_index and not other.folded:
                if other.is_human:
                    opponent_id = HUMAN_OPPONENT_KEY
                else:
                    opponent_id = str(getattr(other, '_char_id', other.seat_index))
                opponent_name = other.name
                break

        # 从记忆系统获取关系和事件
        char_id = getattr(player, '_char_id', 0)
        if hasattr(app, 'memory_manager') and opponent_id:
            rel = app.memory_manager.get_relationship(char_id, opponent_id)
        recent_episodes = ()
        self_summary = ""
        if hasattr(app, 'memory_manager'):
            dctx = app.memory_manager.getDialogueContext(char_id, opponent_id=opponent_id)
            recent_episodes = tuple(dctx.recent_episodes[:3])
            self_summary = dctx.self_summary

        # 情绪状态
        emotion_state = None
        if hasattr(player, 'emotion_engine'):
            emotion_state = player.emotion_engine.get_state()

        is_all_in = any(p.all_in and not p.folded for p in app.players)

        return DialogueContext(
            char_id=char_id,
            char_name=player.name,
            char_description=get_char_description(player.name),
            archetype=getattr(player, '_archetype', ''),
            personality=player.personality,
            trigger=trigger,
            hand_strength=hand_strength or 0.0,
            emotion_state=emotion_state,
            relationship=rel,
            opponent_name=opponent_name,
            recent_episodes=recent_episodes,
            self_summary=self_summary,
            pot_size=app.game.pot,
            phase=app.game.phase,
            is_all_in=is_all_in,
            hand_number=app.game.hand_number,
        )
