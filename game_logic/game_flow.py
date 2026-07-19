"""游戏流程控制：从 GameApp 中抽离的对局业务逻辑。

包含：下注轮处理、行动后推进、人类玩家动作、AI 银行结算、
离开对局、开始下一手、发牌动画。
"""

import pygame

from config import SCREEN_WIDTH, SCREEN_HEIGHT, SHOWDOWN, DEFAULT_STARTING_CHIPS
from engine.action import Action, ActionType
from utils.audit_log import log_transaction


class GameFlow:
    """对局流程控制器，持有 GameApp 引用，操作其状态。"""

    def __init__(self, app):
        self.app = app

    # ==================== 下注轮 ====================

    def process_betting_round(self):
        """处理下注轮逻辑"""
        app = self.app
        if app.game.phase == SHOWDOWN:
            return

        if app.game.is_betting_round_complete():
            app.game.end_betting_round()
            app.ai_controller.check_turn()
            return

        current = app.game.get_current_player()
        if not current or not current.can_act():
            app.game.advance_to_next_player()

    def advance_after_action(self):
        """玩家行动后推进游戏"""
        app = self.app
        if app.game.get_active_player_count() <= 1:
            app.game.go_to_showdown()
            return

        if app.game.is_betting_round_complete():
            app.game.end_betting_round()
        else:
            app.game.advance_to_next_player()

        app.ai_controller.check_turn()

    # ==================== 人类玩家动作 ====================

    def on_human_action(self, action_key):
        """人类玩家执行动作"""
        app = self.app
        player = app.human_player
        player_index = app.game.players.index(player)
        legal = app.game.get_legal_actions(player_index)
        legal_types = set(legal)

        if action_key == "fold" and ActionType.FOLD in legal_types:
            app.game.execute_action(Action(player_index, ActionType.FOLD))
        elif action_key == "check" and ActionType.CHECK in legal_types:
            app.game.execute_action(Action(player_index, ActionType.CHECK))
        elif action_key == "call" and ActionType.CALL in legal_types:
            app.game.execute_action(Action(player_index, ActionType.CALL))
        elif action_key == "raise":
            ri = app.renderer.raise_input
            if ri.active and ri.int_value is not None:
                clamped = max(app.renderer.raise_slider.min_val,
                              min(app.renderer.raise_slider.max_val, ri.int_value))
                app.renderer.raise_slider.value = clamped
            raise_to = app.renderer.raise_slider.value
            if ActionType.RAISE in legal_types:
                app.game.execute_action(Action(player_index, ActionType.RAISE, raise_to))
            elif ActionType.BET in legal_types:
                app.game.execute_action(Action(player_index, ActionType.BET, raise_to))
        elif action_key == "all_in" and ActionType.ALL_IN in legal_types:
            app.game.execute_action(Action(player_index, ActionType.ALL_IN))
        else:
            return

        app.renderer.raise_input.active = False
        self.advance_after_action()

    # ==================== AI 银行结算 ====================

    def settle_ai_banks(self):
        """将 AI 玩家当前持有的筹码存回各自银行"""
        app = self.app
        for player in app.players:
            if not player.is_human and hasattr(player, '_char_id') and player.chips > 0:
                char = app.character_pool.get_by_id(player._char_id)
                if char:
                    before = char.bank
                    char.bank += player.chips
                    if hasattr(player, '_char_stats'):
                        player._char_stats["bank"] = char.bank
                    log_transaction("game_settle", f"AI:{char.name}", player.chips,
                                    before, char.bank, "对局结束筹码存回银行")
                    player.chips = 0

    # ==================== 离开对局 ====================

    def _process_ai_menu_loans(self):
        """返回主菜单时触发 AI 借钱系统（bank 不足买入金额的 AI 向富友借钱）"""
        app = self.app
        buy_in = getattr(app, 'setup_buy_in', DEFAULT_STARTING_CHIPS)
        records = app.character_pool.process_main_menu_loans(threshold=buy_in)
        if records:
            for borrower_name, lender_name, amount in records:
                app.chat_controller.add_message(
                    "系统",
                    f"{borrower_name} 向 {lender_name} 借了 {amount} 筹码",
                    source="system",
                )
                log_transaction("ai_loan", f"AI:{borrower_name}", amount,
                                -1, -1, f"向{lender_name}借{amount}")
            app.character_pool.save()
            app.save_manager.mark_dirty()

    def leave_game(self):
        """玩家主动离开对局，将剩余筹码存回银行"""
        app = self.app
        app._stop_background_simulator()
        app.audio.stop_all_sounds()
        if hasattr(app, '_hand_end_thread') and app._hand_end_thread:
            app._hand_end_thread.join(timeout=0.5)
            app._hand_end_thread = None
        if app.human_player:
            app.save_manager.deposit_to_bank(app.human_player.chips)
        self.settle_ai_banks()
        self._process_ai_menu_loans()
        app.save_manager.save(force=True)
        app.chat_controller.messages = []
        app.chat_controller.active = False
        if app.chat_controller.input:
            app.chat_controller.input.text = ""
            app.chat_controller.input.active = False
            pygame.key.stop_text_input()
        app.switch_scene("menu")
        app.ai_thinking = False
        app.ai_speaking = False
        app._pending_ai_action = None
        app._pending_hand_end_results = None
        app.chat_controller.target = None
        app.animations.clear()

    # ==================== 下一手 ====================

    def next_hand(self):
        """开始下一手"""
        app = self.app

        # 锦标赛模式：走锦标赛流程
        if app.scene in ("tournament", "showdown") and app.tournament_controller and app.tournament_controller.state:
            if app.tournament_controller.state.phase.value in ("group", "final", "ultimate"):
                app._advance_tournament()
                return

        # 等待后台 on_hand_end 线程完成
        if hasattr(app, '_hand_end_thread') and app._hand_end_thread:
            app._hand_end_thread.join(timeout=2.0)
            app._hand_end_thread = None
        app._pending_hand_end_results = None

        # 当前在场 AI 角色ID集合
        active_char_ids = set()
        for p in app.players:
            if not p.is_human and hasattr(p, '_char_id'):
                active_char_ids.add(p._char_id)

        # 1. 处理筹码为 0 的 AI 玩家
        # 规则：bank >= buy_in 则取钱重新入场；否则直接换新的可用 AI
        # （借钱系统只在主菜单触发）
        from ai.personality import Personality
        from ai.mcts_ai import MCTSAI, OpponentModel
        from ai.advanced_ai import AdvancedAI

        for p in app.players:
            if not p.is_human and p.chips == 0:
                char_id = getattr(p, '_char_id', None)
                if char_id:
                    char = app.character_pool.get_by_id(char_id)
                    if char and char.bank >= app.setup_buy_in:
                        char.bank -= app.setup_buy_in
                        p.chips = app.setup_buy_in
                    else:
                        # bank 不足，直接换人
                        active_char_ids.discard(char_id)
                        new_chars = app.character_pool.pick_random_excluding(
                            1, active_char_ids
                        )
                        if new_chars:
                            new_char = new_chars[0]
                            active_char_ids.add(new_char.id)
                            new_session_personality = Personality.randomized_from_archetype(new_char.archetype)
                            new_buy_in = min(app.setup_buy_in, new_char.bank)
                            new_char.bank -= new_buy_in
                            p.name = new_char.name
                            p.chips = new_buy_in
                            p.personality = new_session_personality
                            p._archetype = new_char.archetype
                            p._char_id = new_char.id
                            p._char_stats = {
                                "hands_played": new_char.hands_played,
                                "hands_won": new_char.hands_won,
                                "total_profit": new_char.total_profit,
                                "bank": new_char.bank,
                            }
                            num_players = len(app.players)
                            if num_players == 2:
                                p.ai_brain = AdvancedAI(new_session_personality, difficulty=app.setup_difficulty)
                            else:
                                p.ai_brain = MCTSAI(new_session_personality, difficulty=app.setup_difficulty)

                            for opp_key, mem_dict in new_char.opponent_memories.items():
                                if isinstance(p.ai_brain, AdvancedAI):
                                    p.ai_brain.opponent_model = OpponentModel.from_dict(mem_dict)
                                else:
                                    p.ai_brain.opponent_models[opp_key] = OpponentModel.from_dict(mem_dict)
                        else:
                            p.chips = 0
                            p.folded = True
                            p.all_in = True

        # 2. 检查人类玩家是否破产
        if app.human_player.chips == 0:
            rebuy_amount = getattr(app, 'setup_buy_in', DEFAULT_STARTING_CHIPS)
            bank_balance = app.save_manager.player_data.bank
            app.bankruptcy_buttons["rebuy"].enabled = bank_balance >= rebuy_amount
            if bank_balance < rebuy_amount:
                app.bankruptcy_buttons["rebuy"].text = "银行余额不足"
            else:
                app.bankruptcy_buttons["rebuy"].text = f"从银行取出 {rebuy_amount}"
            app.audio.stop_background_music()
            app.audio.play_bankruptcy()
            app.switch_scene("bankruptcy")
            return

        # 3. 检查游戏是否结束
        if app.game.is_game_over():
            app._stop_background_simulator()
            app.save_manager.deposit_to_bank(app.human_player.chips)
            self.settle_ai_banks()
            self._process_ai_menu_loans()
            app.save_manager.save(force=True)
            app.audio.stop_background_music()
            app.chat_controller.messages = []
            app.chat_controller.active = False
            if app.chat_controller.input:
                app.chat_controller.input.text = ""
                app.chat_controller.input.active = False
                pygame.key.stop_text_input()
            app.switch_scene("menu")
            return

        # 开始下一手
        app.audio.play("shuffle")
        app.game.start_new_hand()
        app.showdown_results = None
        app.ai_thinking = False
        app.ai_speaking = False
        app._pending_ai_action = None
        app._pending_hand_end_results = None
        app.chat_controller.target = None
        app.human_player_initial_chips = app.human_player.chips
        for p in app.players:
            p.initial_chips = p.chips
        self.start_dealing_animation()

    # ==================== 发牌动画 ====================

    def start_dealing_animation(self):
        """创建逐张发牌动画，按小盲先发顺序"""
        app = self.app
        from ui.animations import DealCardAnimation

        num_players = len(app.players)
        positions = app.renderer.get_seat_positions(app.players)
        deck_x = SCREEN_WIDTH // 2
        deck_y = SCREEN_HEIGHT // 2 - 50

        active_indices = [i for i, p in enumerate(app.players) if p.chips > 0]
        sb = app.game.small_blind_index
        sb_pos = active_indices.index(sb) if sb in active_indices else 0
        deal_order = active_indices[sb_pos:] + active_indices[:sb_pos]

        app.animations.clear()
        card_delay = 0.12
        card_duration = 0.25

        idx = 0
        for round_num in range(2):
            for seat_idx in deal_order:
                if seat_idx >= len(positions):
                    continue
                player = app.players[seat_idx]
                if not player.hole_cards or round_num >= len(player.hole_cards):
                    continue
                card = player.hole_cards[round_num] if round_num < len(player.hole_cards) else player.hole_cards[-1]
                end_pos = positions[seat_idx]
                end_y = end_pos[1] - 60
                face_up = player.is_human
                delay = idx * card_delay
                anim = DealCardAnimation(
                    (deck_x, deck_y), (end_pos[0], end_y),
                    card, duration=card_duration, face_up=face_up, delay=delay
                )
                app.animations.add(anim)
                idx += 1

        app._dealing_total_cards = idx
        app._dealing_card_index = 0
        app._dealing_timer = 0.0
        app.switch_scene("dealing")
