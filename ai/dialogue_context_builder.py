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

        # 本局聊天历史（仅LLM生成的消息作为上下文，本地预制消息对LLM无意义）
        chat_history = ()
        if hasattr(app, 'chat_controller') and app.chat_controller.messages:
            chat_history = tuple(
                f"{m['name']}: {m['text']}"
                for m in app.chat_controller.messages[-10:]
                if m.get("source") == "llm"
            )

        # 上一手胜者信息
        last_hand_winner = ""
        if hasattr(app, 'session_hand_history') and app.session_hand_history:
            last_entry = app.session_hand_history[-1]
            winners = last_entry.get("winners", [])
            if winners:
                parts = []
                for w in winners:
                    name = w.get("name", "?")
                    hand_type = w.get("hand_type", "")
                    amount = w.get("amount", 0)
                    if hand_type == "弃牌获胜":
                        parts.append(f"{name} 弃牌获胜 拿走{amount}筹码")
                    else:
                        parts.append(f"{name} 用{hand_type}赢了{amount}筹码")
                last_hand_winner = "；".join(parts)

        # 当前下注轮其他玩家的动作摘要
        table_actions_summary = ""
        if app.game and hasattr(app.game, 'action_history') and app.game.action_history:
            action_names = {
                "fold": "弃牌", "check": "过牌", "call": "跟注",
                "bet": "下注", "raise": "加注", "all_in": "全押",
            }
            # 取当前轮的动作（按phase分组，取最后一组）
            current_phase = app.game.phase
            current_round_actions = [
                a for a in app.game.action_history
                if getattr(a, 'phase', None) == current_phase
            ]
            # 排除自己，只显示其他玩家的动作
            my_seat = player.seat_index
            other_actions = []
            for a in current_round_actions:
                if a.player_index == my_seat:
                    continue
                p = app.game.players[a.player_index] if a.player_index < len(app.game.players) else None
                p_name = p.name if p else f"玩家{a.player_index}"
                act_name = action_names.get(a.action_type.value if hasattr(a.action_type, 'value') else str(a.action_type), str(a.action_type))
                amount_str = f"{a.amount}" if a.amount else ""
                other_actions.append(f"{p_name}{act_name}{amount_str}")
            if other_actions:
                table_actions_summary = "，".join(other_actions)

        # 跨手记忆：最近 3-5 手结果
        recent_hand_results = ()
        hand_result_history = getattr(player, '_hand_result_history', [])
        if hand_result_history:
            recent_hand_results = tuple(hand_result_history[-5:])

        # 本局会话摘要
        session_summary = ""
        hand_number = app.game.hand_number if app.game else 0
        if hand_number > 0:
            results = hand_result_history[-10:] if hand_result_history else []
            wins = sum(1 for r in results if "赢" in r)
            losses = sum(1 for r in results if "输" in r)
            folds = sum(1 for r in results if "弃牌" in r)
            # 连胜/连败
            streak = 0
            for r in reversed(results):
                if "赢" in r:
                    streak = streak + 1 if streak >= 0 else 1
                elif "输" in r:
                    streak = streak - 1 if streak <= 0 else -1
                else:
                    break
            parts = [f"已打{hand_number}手"]
            if results:
                parts.append(f"近{len(results)}手赢{wins}输{losses}弃{folds}")
            if streak >= 2:
                parts.append(f"连胜{streak}手")
            elif streak <= -2:
                parts.append(f"连败{abs(streak)}手")
            session_summary = "，".join(parts)

        # 慢打状态：用于台词伪装
        is_slow_playing = False
        if hasattr(player, 'ai_brain') and player.ai_brain:
            is_slow_playing = getattr(player.ai_brain, '_is_slow_playing', False)

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
            hole_cards=tuple(player.hole_cards) if player.hole_cards else (),
            community_cards=tuple(app.game.community_cards) if app.game.community_cards else (),
            last_hand_result=getattr(player, '_last_hand_result', ''),
            recent_hand_results=recent_hand_results,
            session_summary=session_summary,
            chat_history=chat_history,
            last_hand_winner=last_hand_winner,
            table_actions_summary=table_actions_summary,
            is_slow_playing=is_slow_playing,
        )
