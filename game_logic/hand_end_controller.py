"""HandEnd 控制器：负责每手结束后的统计、记忆、情绪和历史记录"""
from ai.character_pool import HUMAN_OPPONENT_KEY
from ai.memory import (
    EPISODE_BIG_WIN, EPISODE_BAD_BEAT, EPISODE_SUCCESSFUL_BLUFF,
    EPISODE_BLUFFED_BY,
    REL_EVENT_BEAT_THEM, REL_EVENT_LOST_TO_THEM,
    REL_EVENT_THEY_BLUFFED_ME, REL_EVENT_I_BLUFFED_THEM,
)
from engine.hand_evaluator import HandRank


class HandEndController:
    """处理摊牌和每手结束后的重逻辑"""

    def __init__(self, game_app):
        self.app = game_app

    def on_showdown(self, results):
        """摊牌时切换场景并在后台线程执行重逻辑"""
        app = self.app
        app.audio.play("win")
        if results and not results.get('fold_win'):
            evaluations = results.get('evaluations', {})
            payouts = results.get('payouts', {})
            if 0 in payouts and payouts[0] > 0:
                ev = evaluations.get(0)
                if ev and ev.rank >= HandRank.FULL_HOUSE:
                    app.audio.play_cheer()
        app.showdown_results = results
        app.scene = "showdown"
        app.showdown_timer = 0
        # 在后台线程执行重逻辑，用户看结算结果时并行处理
        app._pending_hand_end_results = results
        import threading
        app._hand_end_thread = threading.Thread(
            target=self._run_hand_end_async, args=(results,), daemon=True
        )
        app._hand_end_thread.start()

    def _run_hand_end_async(self, results):
        """后台线程执行 on_hand_end"""
        try:
            self.on_hand_end(results)
        except Exception:
            pass

    def on_hand_end(self, results):
        """每手结束后保存统计、情绪、记忆、历史（在后台线程执行）"""
        app = self.app
        if not results:
            return

        # 判断获胜者
        winner_indices = set()
        if results.get('fold_win'):
            for w in results.get('winners', []):
                winner_indices.add(w.seat_index)
        else:
            winner_indices = set(results.get('payouts', {}).keys())

        # 更新 AI 情绪：赢/输/被诈唬
        pot_size = results.get('pot_won', app.game.pot)
        evaluations = results.get('evaluations', {})
        payouts = results.get('payouts', {})
        for p in app.players:
            if p.is_human or not hasattr(p, 'emotion_engine'):
                continue
            won = p.seat_index in winner_indices
            if won:
                is_bluff = results.get('fold_win', False)
                if not is_bluff:
                    ev = evaluations.get(p.seat_index)
                    if ev and ev.rank < HandRank.PAIR:
                        is_bluff = True
                p.emotion_engine.on_win(pot_size, is_bluff=is_bluff)
            else:
                p.emotion_engine.on_lose(pot_size)
            p.emotion_engine.reset_hand_counters()

        # 更新人类玩家统计
        human_profit = app.human_player.chips - getattr(app, 'human_player_initial_chips', app.human_player.chips)
        human_won = 0 in winner_indices
        app.save_manager.update_after_hand(human_profit, human_won, app.game.pot)

        # 更新AI角色统计
        for player in app.players:
            if not player.is_human and hasattr(player, '_char_id'):
                ai_profit = player.chips - getattr(player, 'initial_chips', player.chips)
                ai_won = player.seat_index in winner_indices
                app.save_manager.update_character_after_hand(player._char_id, ai_profit, ai_won)
                char = app.character_pool.get_by_id(player._char_id)
                if char:
                    player._char_stats = {
                        "hands_played": char.hands_played,
                        "hands_won": char.hands_won,
                        "total_profit": char.total_profit,
                        "bank": char.bank,
                    }
                    # 自动偿还债务：赢钱时还利润的50%
                    if ai_won and ai_profit > 0 and char.debt > 0:
                        repay_result = app.character_pool.repay_debt(player._char_id, ai_profit)
                        if repay_result and repay_result.get("repaid", 0) > 0:
                            msg_text = f"{char.name} 向 {repay_result['lender_name']} 偿还了 {repay_result['repaid']} 筹码"
                            if repay_result.get("debt_cleared"):
                                msg_text += "，债务已清"
                            app.chat_controller.messages.append({
                                "name": "系统",
                                "text": msg_text,
                                "color": (100, 255, 150),
                            })

                # 记录上一局结果，供下次对话使用
                if player.folded and not ai_won:
                    player._last_hand_result = "弃牌"
                elif ai_won:
                    player._last_hand_result = f"赢了{ai_profit:+d}筹码"
                else:
                    player._last_hand_result = f"输了{ai_profit:+d}筹码"

        # 更新记忆系统
        if hasattr(app, 'memory_manager'):
            for player in app.players:
                if player.is_human or not hasattr(player, '_char_id'):
                    continue
                char_id = player._char_id
                observer_id = str(char_id)
                ai_profit = player.chips - getattr(player, 'initial_chips', player.chips)
                ai_won = player.seat_index in winner_indices
                ev = evaluations.get(player.seat_index)
                hand_rank_name = ev.name if ev else ""

                opponent_id = ""
                opponent_name = ""
                for other in app.players:
                    if other.seat_index != player.seat_index and not other.folded:
                        if other.is_human:
                            opponent_id = HUMAN_OPPONENT_KEY
                        else:
                            opponent_id = str(getattr(other, '_char_id', other.seat_index))
                        opponent_name = other.name

                event_type = ""
                episode_desc = ""
                my_hand_str = ""
                if player.hole_cards:
                    my_hand_str = "".join(c.short_str() if hasattr(c, 'short_str') else str(c) for c in player.hole_cards)

                if ai_won:
                    is_bluff_win = results.get('fold_win', False)
                    if not is_bluff_win and ev and ev.rank < HandRank.PAIR:
                        is_bluff_win = True
                    if is_bluff_win:
                        event_type = EPISODE_SUCCESSFUL_BLUFF
                        episode_desc = f"{player.name} 用{my_hand_str}诈唬赢得{pot_size}"
                    elif pot_size > 500 or ai_profit > 300:
                        event_type = EPISODE_BIG_WIN
                        episode_desc = f"{player.name} 用{hand_rank_name}赢得{pot_size}底池"
                else:
                    if results.get('fold_win') and pot_size > 200:
                        event_type = EPISODE_BLUFFED_BY
                        episode_desc = f"{player.name} 被诈唬，输掉{pot_size}底池"
                    elif pot_size > 500 and ai_profit < -200:
                        event_type = EPISODE_BAD_BEAT
                        episode_desc = f"{player.name} 输掉{pot_size}底池，盈亏{ai_profit}"

                rel_event = REL_EVENT_BEAT_THEM if ai_won else REL_EVENT_LOST_TO_THEM
                if event_type == EPISODE_BLUFFED_BY:
                    rel_event = REL_EVENT_THEY_BLUFFED_ME
                elif event_type == EPISODE_SUCCESSFUL_BLUFF:
                    rel_event = REL_EVENT_I_BLUFFED_THEM

                vs_human = opponent_id == HUMAN_OPPONENT_KEY

                app.memory_manager.on_hand_end(
                    char_id=char_id,
                    observer_id=observer_id,
                    won=ai_won,
                    profit=ai_profit,
                    pot_size=pot_size,
                    hand_rank_name=hand_rank_name,
                    vs_human=vs_human,
                    opponent_id=opponent_id,
                    opponent_name=opponent_name,
                    event_type=event_type,
                    episode_description=episode_desc,
                    my_hand=my_hand_str,
                    my_action=player.last_action.action_type.name if player.last_action else "",
                    phase="showdown",
                )

                if opponent_id:
                    app.memory_manager.update_relationship(
                        char_id, opponent_id, opponent_name, rel_event,
                        won=ai_won, lost=not ai_won,
                    )

            # 每 3 手保存一次记忆到磁盘，避免 8 人局每手大量 I/O 导致卡顿
            if app.game.hand_number % 3 == 0:
                app.memory_manager.save_all()

        # 记录对战历史
        winners_info = []
        if results.get('fold_win'):
            for w in results.get('winners', []):
                net = results.get('pot_won', 0) - w.total_bet
                winners_info.append({
                    "name": w.name,
                    "hand_type": "弃牌获胜",
                    "amount": net,
                    "is_human": w.is_human,
                })
        else:
            for idx, amount in payouts.items():
                if amount > 0 and idx < len(app.players):
                    p = app.players[idx]
                    ev = evaluations.get(idx)
                    net = amount - p.total_bet
                    winners_info.append({
                        "name": p.name,
                        "hand_type": ev.name if ev else "未知",
                        "amount": net,
                        "is_human": p.is_human,
                    })
        if winners_info:
            from datetime import datetime
            entry = {
                "time": datetime.now().strftime("%m-%d %H:%M"),
                "hand_num": app.game.hand_number,
                "winners": winners_info,
            }
            app.session_hand_history.append(entry)
            app.save_manager.add_hand_history(winners_info)

        # 记录详细对局日志（每 3 手一次，减少 I/O）
        if app.game.hand_number % 3 == 0:
            app.game_logger.log_hand(
                hand_number=app.game.hand_number,
                players=app.players,
                community_cards=app.game.community_cards,
                action_history=app.game.action_history,
                results=results,
                payouts=payouts,
                evaluations=evaluations,
            )

        # 保存（非强制，受 HANDS_BETWEEN_SAVES 控制）
        app.save_manager.save()
