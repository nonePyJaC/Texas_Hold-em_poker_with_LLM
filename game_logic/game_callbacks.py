"""GameCallbacks：负责 GameApp 注册给 PokerGame 的回调"""
from ai.character_pool import HUMAN_OPPONENT_KEY
from ai.mcts_ai import MCTSAI
from ai.advanced_ai import AdvancedAI
from ai.emotion import EVENT_FOLD_TO_AGGRO, EVENT_ALL_IN_SITUATION
from engine.action import ActionType
from ui.animations import TextPopupAnimation, FlipCardAnimation
from config import SCREEN_WIDTH


_ACTION_TYPE_NAMES = {
    ActionType.FOLD: "fold",
    ActionType.CHECK: "check",
    ActionType.CALL: "call",
    ActionType.BET: "bet",
    ActionType.RAISE: "raise",
    ActionType.ALL_IN: "all_in",
}


class GameCallbacks:
    """PokerGame 回调：音效、动画、记忆、AI 对手模型、情绪"""

    def __init__(self, game_app):
        self.app = game_app

    def bind(self, game):
        """将回调绑定到 game 实例"""
        game.on_phase_change = self.on_phase_change
        game.on_player_action = self.on_player_action
        game.on_deal_hole = self.on_deal_hole
        game.on_deal_community = self.on_deal_community

    def on_phase_change(self, phase):
        if phase == "flop":
            self.app.audio.play("flip")
        elif phase == "turn":
            self.app.audio.play("flip")
        elif phase == "river":
            self.app.audio.play("flip")

    def on_player_action(self, action):
        app = self.app
        at = action.action_type
        if at == ActionType.FOLD:
            app.audio.play("fold")
        elif at == ActionType.CHECK:
            app.audio.play("check")
        elif at == ActionType.CALL:
            app.audio.play("call")
        elif at == ActionType.BET:
            app.audio.play("bet")
        elif at == ActionType.RAISE:
            app.audio.play("raise")
        elif at == ActionType.ALL_IN:
            app.audio.play("allin")
            player = app.game.players[action.player_index]
            pos = app.renderer.get_player_pos(action.player_index)
            app.animations.add(TextPopupAnimation(pos, "ALL IN!", (255, 50, 50)))

        # 更新所有 AI 的对手模型
        self._update_ai_opponent_models(action)

        # 更新记忆系统: 所有 AI 观察并记录该行动
        actor = app.game.players[action.player_index]
        is_preflop = app.game.phase == "preflop"
        did_enter = is_preflop and at in (ActionType.CALL, ActionType.BET, ActionType.RAISE, ActionType.ALL_IN)
        did_raise = is_preflop and at in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN)
        faced_bet = app.game.current_bet > actor.current_bet and at != ActionType.CHECK
        bet_ratio = 0.0
        if action.amount and app.game.pot > 0:
            bet_ratio = action.amount / app.game.pot
        if actor.is_human:
            actor_key = HUMAN_OPPONENT_KEY
            actor_name = "你"
        else:
            actor_key = str(getattr(actor, '_char_id', actor.seat_index))
            actor_name = actor.name
        at_name = _ACTION_TYPE_NAMES.get(at, "fold")
        for p in app.players:
            if not p.is_human and p.seat_index != actor.seat_index and hasattr(p, '_char_id'):
                observer_id = str(p._char_id)
                app.memory_manager.record_action(
                    observer_id, actor_key, actor_name,
                    at_name, app.game.phase, is_preflop,
                    did_enter, did_raise, faced_bet, bet_ratio,
                )

        # 更新行动 AI 的情绪
        if not actor.is_human and hasattr(actor, 'emotion_engine'):
            if at == ActionType.FOLD:
                actor.emotion_engine.on_fold()
                to_call = app.game.current_bet - actor.current_bet
                if to_call > 0:
                    actor.emotion_engine.on_event(EVENT_FOLD_TO_AGGRO)
            elif at == ActionType.ALL_IN:
                actor.emotion_engine.on_event(EVENT_ALL_IN_SITUATION)

        # 其他 AI 感知到全押局面
        if at == ActionType.ALL_IN:
            for p in app.players:
                if not p.is_human and p.seat_index != action.player_index and hasattr(p, 'emotion_engine'):
                    p.emotion_engine.on_event(EVENT_ALL_IN_SITUATION)

    def _update_ai_opponent_models(self, action):
        """某个玩家行动后，更新所有 AI 对该玩家的对手模型"""
        app = self.app
        if not app.game or not hasattr(app, 'players'):
            return
        actor = app.game.players[action.player_index]
        actor_id = actor.seat_index
        is_preflop = app.game.phase == "preflop"
        did_enter = is_preflop and action.action_type in (ActionType.CALL, ActionType.BET, ActionType.RAISE, ActionType.ALL_IN)
        did_raise = is_preflop and action.action_type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN)

        if actor.is_human:
            opp_key = HUMAN_OPPONENT_KEY
        else:
            opp_key = str(getattr(actor, '_char_id', actor_id))

        for p in app.players:
            if not p.is_human and hasattr(p, 'ai_brain') and p.seat_index != actor.seat_index:
                update_fn = getattr(p.ai_brain, 'update_opponent_model', None)
                if update_fn:
                    update_fn(opp_key, action.action_type, is_preflop, did_enter, did_raise)
                    char = app.character_pool.get_by_id(getattr(p, '_char_id', None))
                    if char:
                        if isinstance(p.ai_brain, AdvancedAI):
                            char.opponent_memories[opp_key] = p.ai_brain.opponent_model.to_dict()
                        else:
                            model = p.ai_brain.opponent_models.get(opp_key)
                            if model:
                                char.opponent_memories[opp_key] = model.to_dict()

    def on_deal_hole(self):
        pass  # 发牌音效由 dealing 动画逐张播放

    def on_deal_community(self, new_cards):
        self.app.audio.play("deal")
        cx = SCREEN_WIDTH // 2
        base_x = cx - 175
        y = 280
        existing = len(self.app.game.community_cards) - len(new_cards)
        for i, card in enumerate(new_cards):
            x = base_x + (existing + i) * 75
            self.app.animations.add(FlipCardAnimation((x + 35, y + 50), card, duration=0.3))
