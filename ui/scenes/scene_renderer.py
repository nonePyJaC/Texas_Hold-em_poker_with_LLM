"""场景渲染器：将 GameApp 中的各场景渲染逻辑抽离"""
import pygame
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    DEFAULT_STARTING_CHIPS,
    PREFLOP, SHOWDOWN,
)
from ui.scenes.replay_renderer import HandReplayRenderer


class SceneRenderer:
    """负责所有场景的渲染"""

    def __init__(self, game_app):
        """Args:
            game_app: GameApp 实例
        """
        self.app = game_app
        self.replay_renderer = HandReplayRenderer(game_app)

    def render(self, scene):
        """根据场景名分发渲染"""
        if scene == "menu":
            self._render_menu()
        elif scene == "setup":
            self._render_setup()
        elif scene == "settings":
            self._render_settings()
        elif scene == "bankruptcy":
            self._render_bankruptcy()
        elif scene == "history":
            self._render_history()
        elif scene == "replay":
            self.replay_renderer.render()
        elif scene == "dealing":
            self._render_playing()
            self.app.animations.draw(self.app.screen)
            # 锦标赛发牌时也显示阶段信息条
            if self.app.tournament_controller and self.app.tournament_controller.state:
                self._draw_tournament_info_bar()
        elif scene == "playing":
            self._render_playing()
        elif scene == "showdown":
            self._render_playing()
            self.app.renderer.draw_showdown_results(
                self.app.showdown_results,
                self.app.players,
                self.app.game.community_cards,
                hand_number=self.app.game.hand_number,
                timer=self.app.showdown_timer
            )
            # 锦标赛 showdown 时也显示阶段信息条
            if self.app.tournament_controller and self.app.tournament_controller.state:
                self._draw_tournament_info_bar()
        elif scene == "tournament_setup":
            self._render_tournament_setup()
        elif scene == "tournament":
            self._render_tournament()
        elif scene == "tournament_waiting":
            self._render_tournament_waiting()
        elif scene == "tournament_result":
            self._render_tournament_result()

    def _render_menu(self):
        """渲染主菜单"""
        app = self.app
        app.renderer.draw_menu(app.menu_buttons.values())

        cx = SCREEN_WIDTH // 2
        stats = app.save_manager.get_stats_summary()
        font = app.renderer.font_normal
        small = app.renderer.font_small

        bank_text = font.render(f"银行余额: {stats['bank']:,}", True, (255, 215, 0))
        app.screen.blit(bank_text, (cx - bank_text.get_width() // 2, 180))

        loan = app.save_manager.player_data.loan
        if loan > 0:
            loan_text = small.render(f"欠款: {loan:,}（赢钱自动还）", True, (255, 120, 120))
            app.screen.blit(loan_text, (cx - loan_text.get_width() // 2, 210))

        if app.save_manager.can_get_daily_bonus():
            app.menu_buttons["bonus"].text = "每日奖励 +2000"
            app.menu_buttons["bonus"].enabled = True
        else:
            app.menu_buttons["bonus"].text = "今日已领取"
            app.menu_buttons["bonus"].enabled = False

        if app.save_manager.can_take_loan():
            app.menu_buttons["loan"].text = "申请贷款 5000"
            app.menu_buttons["loan"].enabled = True
        else:
            app.menu_buttons["loan"].text = "贷款额度已满"
            app.menu_buttons["loan"].enabled = False

        if stats['total_hands'] > 0:
            info_lines = [
                f"总手数: {stats['total_hands']}  胜率: {stats['win_rate']}",
                f"总盈亏: {stats['total_profit']:+,}  最大底池: {stats['biggest_pot']:,}",
            ]
            for i, line in enumerate(info_lines):
                surf = small.render(line, True, (180, 180, 180))
                app.screen.blit(surf, (cx - surf.get_width() // 2, 495 + i * 20))

        # 锦标赛冠军信息
        champion_name = ""
        human_tw = getattr(app.save_manager.player_data, 'tournament_wins', 0)
        if hasattr(app, 'tournament_controller') and app.tournament_controller:
            champion_name = app.tournament_controller.get_current_champion_name()
        app.renderer.draw_bank_leaderboard(
            "你", stats['bank'], app.save_manager.character_pool.characters,
            champion_name=champion_name, human_tournament_wins=human_tw,
        )

        history_count = len(app.save_manager.player_data.hand_history)
        app.history_button.text = f"对战记录 ({history_count})"
        lb_h = 32 + min(10, 1 + len(app.save_manager.character_pool.characters)) * 24 + 12
        app.history_button.rect.y = 130 + lb_h + 8
        mouse_pos = pygame.mouse.get_pos()
        app.history_button.update(mouse_pos)
        app.history_button.draw(app.screen)

    def _render_setup(self):
        """渲染游戏设置界面"""
        app = self.app
        app.screen.fill((18, 18, 18))

        cx = SCREEN_WIDTH // 2
        title = app.renderer.font_title.render("游戏设置", True, (255, 215, 0))
        app.screen.blit(title, (cx - title.get_width() // 2, 60))

        labels = [
            (160, "玩家数量"),
            (240, "盲注选择"),
            (320, "下注模式"),
            (400, "牌组类型"),
            (480, "AI 难度"),
            (540, "买入金额"),
        ]

        for y, label in labels:
            surf = app.renderer.font_normal.render(label, True, (255, 255, 255))
            app.screen.blit(surf, (cx - 320, y + 8))

        mouse_pos = pygame.mouse.get_pos()

        for comp in app.setup_components.values():
            if hasattr(comp, 'update'):
                comp.update(mouse_pos)

        expanded_comp = None
        for comp in app.setup_components.values():
            if getattr(comp, "expanded", False):
                expanded_comp = comp
                continue
            if hasattr(comp, 'draw'):
                comp.draw(app.screen)

        if expanded_comp and hasattr(expanded_comp, 'draw'):
            expanded_comp.draw(app.screen)

        bank = app.save_manager.player_data.bank
        try:
            buy_in_val = int(app.setup_components["buy_in"].text)
        except (ValueError, TypeError):
            buy_in_val = DEFAULT_STARTING_CHIPS

        bank_color = (255, 215, 0) if bank >= buy_in_val else (255, 80, 80)
        bank_text = app.renderer.font_small.render(f"银行余额: {bank:,}", True, bank_color)
        app.screen.blit(bank_text, (cx - bank_text.get_width() // 2, 600))

        if bank < buy_in_val:
            warn = app.renderer.font_small.render("余额不足！请返回菜单领取每日奖励或申请贷款", True, (255, 80, 80))
            app.screen.blit(warn, (cx - warn.get_width() // 2, 620))

    def _render_settings(self):
        """渲染设置界面"""
        app = self.app
        app.screen.fill((18, 18, 18))
        cx = SCREEN_WIDTH // 2

        title = app.renderer.font_title.render("设置", True, (255, 215, 0))
        app.screen.blit(title, (cx - title.get_width() // 2, 80))

        audio_title = app.renderer.font_normal.render("音效设置", True, (255, 255, 255))
        app.screen.blit(audio_title, (cx - 320, 125))
        labels = [
            (160, "音效"),
            (220, "音量"),
        ]
        for y, label in labels:
            surf = app.renderer.font_small.render(label, True, (180, 180, 180))
            app.screen.blit(surf, (cx - 320, y - 18))

        panel_x = cx + 20
        llm_title = app.renderer.font_normal.render("LLM 对话配置", True, (100, 180, 255))
        app.screen.blit(llm_title, (panel_x, 125))

        llm_labels = [
            (160, "API Key"),
            (220, "API Base"),
            (280, "模型"),
            (340, "LLM 概率"),
            (400, "启用"),
        ]
        for y, label in llm_labels:
            surf = app.renderer.font_small.render(label, True, (180, 180, 180))
            app.screen.blit(surf, (panel_x, y - 18))

        mouse_pos = pygame.mouse.get_pos()

        expanded_comp = None
        for comp in app.settings_components.values():
            if hasattr(comp, 'update'):
                comp.update(mouse_pos)
            if getattr(comp, "expanded", False):
                expanded_comp = comp

        for comp in app.settings_components.values():
            if comp is expanded_comp:
                continue
            if hasattr(comp, 'draw'):
                comp.draw(app.screen)

        if expanded_comp and hasattr(expanded_comp, 'draw'):
            expanded_comp.draw(app.screen)

        vol = app.settings_components["volume"].value
        vol_text = app.renderer.font_small.render(f"{int(vol * 100)}%", True, (200, 200, 200))
        app.screen.blit(vol_text, (cx - 110, 212))

        if app._llm_test_result:
            result_surf = app.renderer.font_small.render(
                app._llm_test_result, True, app._llm_test_result_color
            )
            app.screen.blit(result_surf, (panel_x, 510))

    def _render_bankruptcy(self):
        """渲染破产/补充筹码界面"""
        app = self.app
        app.screen.fill((18, 18, 18))
        cx = SCREEN_WIDTH // 2

        title = app.renderer.font_title.render("你已经输光了所有筹码！", True, (220, 40, 40))
        app.screen.blit(title, (cx - title.get_width() // 2, 100))

        info_font = app.renderer.font_normal
        small = app.renderer.font_small
        stats = app.save_manager.get_stats_summary()
        bank_balance = stats["bank"]
        loan = app.save_manager.player_data.loan

        desc1 = info_font.render(f"当前银行余额: {bank_balance:,} 筹码", True, (255, 215, 0))
        app.screen.blit(desc1, (cx - desc1.get_width() // 2, 170))

        if loan > 0:
            loan_text = small.render(f"当前欠款: {loan:,} 筹码（赢钱后自动偿还）", True, (255, 120, 120))
            app.screen.blit(loan_text, (cx - loan_text.get_width() // 2, 200))

        rebuy_amount = getattr(app, 'setup_buy_in', DEFAULT_STARTING_CHIPS)
        desc2 = info_font.render(f"从银行取出 {rebuy_amount} 筹码继续对局", True, (200, 200, 200))
        app.screen.blit(desc2, (cx - desc2.get_width() // 2, 230))

        desc3 = small.render("银行没钱了？可以申请贷款或领取每日奖励", True, (180, 180, 180))
        app.screen.blit(desc3, (cx - desc3.get_width() // 2, 260))

        bank_balance = app.save_manager.player_data.bank
        app.bankruptcy_buttons["rebuy"].enabled = bank_balance >= rebuy_amount
        if bank_balance < rebuy_amount:
            app.bankruptcy_buttons["rebuy"].text = "银行余额不足"
        else:
            app.bankruptcy_buttons["rebuy"].text = f"从银行取出 {rebuy_amount}"

        if not app.save_manager.can_take_loan():
            app.bankruptcy_buttons["loan"].text = "贷款额度已满"
            app.bankruptcy_buttons["loan"].enabled = False
        else:
            app.bankruptcy_buttons["loan"].text = "申请贷款 5000"
            app.bankruptcy_buttons["loan"].enabled = True

        if not app.save_manager.can_get_daily_bonus():
            app.bankruptcy_buttons["bonus"].text = "今日已领取"
            app.bankruptcy_buttons["bonus"].enabled = False
        else:
            app.bankruptcy_buttons["bonus"].text = "领取每日奖励 +2000"
            app.bankruptcy_buttons["bonus"].enabled = True

        mouse_pos = pygame.mouse.get_pos()
        for btn in app.bankruptcy_buttons.values():
            if hasattr(btn, 'update'):
                btn.update(mouse_pos)
            if hasattr(btn, 'draw'):
                btn.draw(app.screen)

    def _render_history(self):
        """渲染对战记录页面"""
        app = self.app
        app.screen.fill((18, 18, 18))
        cx = SCREEN_WIDTH // 2

        title = app.renderer.font_title.render("对战记录", True, (255, 215, 0))
        app.screen.blit(title, (cx - title.get_width() // 2, 30))

        # 获取 SQLite 中的完整手牌日志（供回放）
        recent_hands = app.game_logger.get_recent_hands(count=50)

        history = app.save_manager.player_data.hand_history
        if not history and not recent_hands:
            hint = app.renderer.font_normal.render("暂无对战记录，开始游戏后会有记录", True, (180, 180, 180))
            app.screen.blit(hint, (cx - hint.get_width() // 2, 200))
        else:
            header_y = 80
            col_time = 40
            col_hand = 130
            col_winner = 230
            col_type = 450
            col_amount = 620
            col_replay = 740

            headers = [("时间", col_time), ("手数", col_hand), ("获胜者", col_winner), ("牌型", col_type), ("净赢", col_amount), ("回放", col_replay)]
            for label, x in headers:
                surf = app.renderer.font_small.render(label, True, (255, 215, 0))
                app.screen.blit(surf, (x, header_y))

            pygame.draw.line(app.screen, (80, 80, 80), (20, header_y + 22), (SCREEN_WIDTH - 20, header_y + 22), 1)

            display = list(reversed(history))
            max_rows = (SCREEN_HEIGHT - 130) // 28
            mouse_pos = pygame.mouse.get_pos()

            for i, entry in enumerate(display[:max_rows]):
                y = header_y + 30 + i * 28

                if i % 2 == 0:
                    row_bg = pygame.Surface((SCREEN_WIDTH - 40, 26), pygame.SRCALPHA)
                    row_bg.fill((30, 30, 35, 100))
                    app.screen.blit(row_bg, (20, y - 2))

                time_surf = app.renderer.font_tiny.render(entry.get("time", ""), True, (160, 160, 160))
                app.screen.blit(time_surf, (col_time, y))

                hand_num = entry.get("hand_num", "")
                hand_surf = app.renderer.font_tiny.render(f"#{hand_num}", True, (160, 160, 160))
                app.screen.blit(hand_surf, (col_hand, y))

                winners = entry.get("winners", [])
                winner_names = ", ".join(w["name"] for w in winners)
                if len(winner_names) > 12:
                    winner_names = winner_names[:11] + ".."

                has_human = any(w.get("is_human") for w in winners)
                w_color = (100, 255, 150) if has_human else (220, 220, 220)
                winner_surf = app.renderer.font_tiny.render(winner_names, True, w_color)
                app.screen.blit(winner_surf, (col_winner, y))

                types = ", ".join(w["hand_type"] for w in winners)
                if len(types) > 16:
                    types = types[:15] + ".."
                type_surf = app.renderer.font_tiny.render(types, True, (200, 200, 200))
                app.screen.blit(type_surf, (col_type, y))

                total_amount = sum(w["amount"] for w in winners)
                if total_amount >= 0:
                    amount_text = f"+{total_amount:,}"
                    amount_color = (255, 215, 0) if has_human else (200, 200, 200)
                else:
                    amount_text = f"{total_amount:,}"
                    amount_color = (255, 80, 80) if has_human else (180, 120, 120)
                amount_surf = app.renderer.font_tiny.render(amount_text, True, amount_color)
                app.screen.blit(amount_surf, (col_amount, y))

                # 回放按钮 — 检查是否有对应的完整日志
                hand_num_int = entry.get("game_hand_number", entry.get("hand_num", -1))
                has_full_log = any(rh.get("hand_number") == hand_num_int for rh in recent_hands)
                if has_full_log:
                    replay_text = "> 回放"
                    replay_color = (100, 180, 255)
                else:
                    replay_text = "无日志"
                    replay_color = (60, 60, 60)
                replay_surf = app.renderer.font_tiny.render(replay_text, True, replay_color)
                app.screen.blit(replay_surf, (col_replay, y))

            if len(display) > max_rows:
                more_text = app.renderer.font_tiny.render(f"... 共 {len(display)} 条记录，仅显示最近 {max_rows} 条", True, (120, 120, 120))
                app.screen.blit(more_text, (cx - more_text.get_width() // 2, SCREEN_HEIGHT - 50))

        # 底部提示
        hints = ["按 ESC 返回主菜单"]
        if recent_hands:
            hints.append(f"可回放手牌: {len(recent_hands)} 手")
        for j, h in enumerate(hints):
            hint = app.renderer.font_small.render(h, True, (120, 120, 120))
            app.screen.blit(hint, (cx - hint.get_width() // 2, SCREEN_HEIGHT - 30 + j * 18))

    def _render_playing(self):
        """渲染游戏画面"""
        app = self.app
        app.renderer.draw_background()
        app.renderer.draw_table()

        if not app.game:
            return

        positions = app.renderer.get_seat_positions(app.players)
        app.renderer._last_players = app.players

        mouse_pos = pygame.mouse.get_pos()
        hovered_index = None
        for i, pos in enumerate(positions):
            card_w, card_h = 160, 70
            rect_x = pos[0] - card_w // 2
            rect_y = pos[1] - card_h // 2
            if rect_x <= mouse_pos[0] <= rect_x + card_w and rect_y <= mouse_pos[1] <= rect_y + card_h:
                hovered_index = i
                break

        for i, player in enumerate(app.players):
            pos = positions[i]
            is_current = (i == app.game.current_player_index and player.can_act()
                         and app.scene in ("playing", "tournament"))
            is_dealer = (i == app.game.dealer_index)
            is_sb = (i == app.game.small_blind_index)
            is_bb = (i == app.game.big_blind_index)
            show_cards = (app.scene == "showdown" and not player.folded)
            hovered = (i == hovered_index)
            app.renderer.draw_player(
                player, pos, is_current, is_dealer, is_sb, is_bb,
                show_cards=show_cards, is_human=player.is_human, hovered=hovered,
                hide_hole_cards=(app.scene == "dealing")
            )

        app.renderer.draw_community_cards(app.game.community_cards)
        app.renderer.draw_pot(app.game.pot)
        app.renderer.draw_leaderboard(app.players)

        num_players = len(app.players)
        lb_h = 30 + num_players * 22 + 10
        app.renderer.draw_history_panel(
            app.session_hand_history,
            lb_panel_x=SCREEN_WIDTH - 190,
            lb_panel_y=60,
            lb_panel_h=lb_h
        )

        app.renderer.draw_phase_info(app.game.phase, app.game.hand_number)
        app.renderer.draw_betting_info(app.game.current_bet, app.game.min_raise)

        if app.scene in ("playing", "tournament"):
            app.renderer.draw_action_panel(app.game, app.human_player)

            if app.ai_thinking and not (app.ai_action_dialogue and app.ai_action_dialogue_timer > 0):
                current = app.game.get_current_player()
                if current:
                    think_text = app.ai_dialogue.text if app.ai_dialogue and hasattr(app.ai_dialogue, 'text') else None
                    app.renderer.draw_ai_thinking(current.name, think_text)

        if app.ai_action_dialogue and app.ai_action_dialogue_timer > 0:
            app.renderer.draw_speech_bubble(
                app.ai_action_dialogue_revealed or app.ai_action_dialogue.text,
                app.ai_action_dialogue_name
            )

        if app.selected_player_index is not None and app.selected_player_index < len(app.players):
            selected_player = app.players[app.selected_player_index]
            app.player_popup_close_btn = app.renderer.draw_player_popup(
                selected_player,
                close_callback=lambda: (setattr(app, 'selected_player_index', None), setattr(app, 'player_popup_close_btn', None))
            )

        app.animations.draw(app.screen)

        # 聊天框 (左下角)
        app.chat_controller.render(app.screen, app.renderer)

    # ==================== 锦标赛渲染 ====================

    def _render_tournament_setup(self):
        """渲染锦标赛报名页"""
        app = self.app
        screen = app.screen
        screen.fill((18, 18, 18))
        cx = SCREEN_WIDTH // 2

        # 标题
        title = app.renderer.font_title.render("锦标赛", True, (255, 215, 0))
        screen.blit(title, (cx - title.get_width() // 2, 60))

        # 规则说明
        rules = [
            "阶段1: 8桌×3人 短牌德州, 盲注10/20, 最多30局, 胜者出线",
            "阶段2: 8人决赛圈 标准牌, 盲注25/50, 24局, 前3名进最终局",
            "阶段3: 最终局 短牌, 盲注50/100, 打到只剩1人",
            "",
            "入场费: 5,000 筹码 (24人共120,000池子)",
            "冠军: 独吞池子 + 额外10,000 奖励",
            "决赛圈出局: 每人3,000 筹码奖励",
            "最终局失败者: 每人7,500 筹码奖励",
        ]
        for i, line in enumerate(rules):
            surf = app.renderer.font_normal.render(line, True, (200, 200, 200) if line else (100, 100, 100))
            screen.blit(surf, (cx - 300, 130 + i * 28))

        # 检查条件
        tc = app.tournament_controller
        eligible = tc.get_eligible_ai_count()
        human_bank = app.save_manager.player_data.bank

        y = 380
        if human_bank < 5000:
            surf = app.renderer.font_normal.render(f"你的银行余额不足5,000 (当前: {human_bank:,})", True, (220, 80, 80))
            screen.blit(surf, (cx - 200, y))
            app.tournament_buttons["start"].enabled = False
            app.tournament_buttons["start"].text = "余额不足"
        elif eligible < 23:
            surf = app.renderer.font_normal.render(f"符合条件的AI玩家不足23人 (当前: {eligible}人, 需>5,000筹码)", True, (220, 80, 80))
            screen.blit(surf, (cx - 250, y))
            app.tournament_buttons["start"].enabled = False
            app.tournament_buttons["start"].text = "人数不足"
        else:
            surf = app.renderer.font_normal.render(f"符合条件的AI玩家: {eligible}人  你的银行: {human_bank:,}", True, (80, 200, 80))
            screen.blit(surf, (cx - 200, y))
            app.tournament_buttons["start"].enabled = True
            app.tournament_buttons["start"].text = "开始锦标赛"

        # 检查是否有存档
        has_save = tc.has_saved_tournament()
        if has_save:
            app.tournament_buttons["continue"].visible = True
        else:
            app.tournament_buttons["continue"].visible = False

        # 绘制按钮
        mouse_pos = pygame.mouse.get_pos()
        for key in ["start", "continue", "back"]:
            btn = app.tournament_buttons[key]
            if hasattr(btn, 'visible') and not btn.visible:
                continue
            btn.update(mouse_pos)
            btn.draw(screen)

    def _render_tournament(self):
        """渲染锦标赛进行中（复用 playing 渲染 + 锦标赛信息条）"""
        app = self.app
        screen = app.screen

        # 先渲染正常的游戏画面
        self._render_playing()

        # 在顶部绘制锦标赛阶段信息条
        self._draw_tournament_info_bar()

    def _draw_tournament_info_bar(self):
        """绘制锦标赛阶段信息条（可被 tournament 和 showdown 场景复用）"""
        app = self.app
        screen = app.screen
        state = app.tournament_controller.state
        if not state:
            return
        phase_names = {
            "group": f"阶段1: 小组赛 (桌{state.current_table_id + 1}/8)",
            "final": f"阶段2: 决赛圈 ({state.final_hand_count}/{state.FINAL_MAX_HANDS}局)",
            "ultimate": f"阶段3: 最终局 ({state.ultimate_hand_count}/{state.ULTIMATE_MAX_HANDS}局)",
        }
        phase_text = phase_names.get(state.phase.value, "")
        if not phase_text:
            return
        # 半透明背景条
        bar_surf = pygame.Surface((SCREEN_WIDTH, 28), pygame.SRCALPHA)
        bar_surf.fill((40, 20, 60, 200))
        screen.blit(bar_surf, (0, 0))
        text_surf = app.renderer.font_small.render(phase_text, True, (255, 215, 0))
        screen.blit(text_surf, (SCREEN_WIDTH // 2 - text_surf.get_width() // 2, 4))

        # 阶段1显示当前桌局数
        if state.phase.value == "group":
            table = state.get_table(state.current_table_id)
            if table:
                hand_text = f"第{table.hand_count}/{state.GROUP_MAX_HANDS}局"
                hand_surf = app.renderer.font_small.render(hand_text, True, (200, 200, 200))
                screen.blit(hand_surf, (SCREEN_WIDTH - hand_surf.get_width() - 20, 4))

    def _render_tournament_waiting(self):
        """渲染等待其他桌完成页面"""
        app = self.app
        screen = app.screen
        screen.fill((18, 18, 18))
        cx = SCREEN_WIDTH // 2

        state = app.tournament_controller.state
        if state and state.phase.value != "group":
            # 自动模拟中（人类已淘汰）
            title = app.renderer.font_title.render("正在模拟剩余比赛...", True, (255, 215, 0))
            screen.blit(title, (cx - title.get_width() // 2, 60))
            hint = app.renderer.font_normal.render("请稍候，AI 正在完成锦标赛", True, (160, 160, 160))
            screen.blit(hint, (cx - hint.get_width() // 2, 200))
            return

        title = app.renderer.font_title.render("等待其他桌完成...", True, (255, 215, 0))
        screen.blit(title, (cx - title.get_width() // 2, 60))

        # 显示各桌进度
        state = app.tournament_controller.state
        if state:
            progress = app.tournament_controller.get_group_stage_progress()
            for i, t in enumerate(progress.get("tables", [])):
                y = 140 + i * 50
                # 桌号
                table_text = f"桌 {t['table_id'] + 1}"
                surf = app.renderer.font_normal.render(table_text, True, (200, 200, 200))
                screen.blit(surf, (cx - 300, y))

                # 玩家
                for j, p in enumerate(t["players"]):
                    color = (100, 255, 150) if p["is_human"] else (200, 200, 200)
                    name = p["name"][:6]
                    psurf = app.renderer.font_small.render(f"{name}: {p['chips']:,}", True, color)
                    screen.blit(psurf, (cx - 200 + j * 130, y))

                # 进度
                if t["finished"]:
                    status = f"完成 - 胜者: {t['winner_name']}"
                    color = (80, 200, 80)
                else:
                    status = f"进行中 {t['hand_count']}/{t['max_hands']}"
                    color = (200, 200, 80)
                ssurf = app.renderer.font_small.render(status, True, color)
                screen.blit(ssurf, (cx + 200, y))

        # 提示
        hint = app.renderer.font_normal.render("其他桌正在后台进行，请稍候...", True, (160, 160, 160))
        screen.blit(hint, (cx - hint.get_width() // 2, SCREEN_HEIGHT - 100))

    def _render_tournament_result(self):
        """渲染锦标赛结果页"""
        app = self.app
        screen = app.screen
        screen.fill((18, 18, 18))
        cx = SCREEN_WIDTH // 2

        state = app.tournament_controller.state
        if not state:
            return

        title = app.renderer.font_title.render("锦标赛结束", True, (255, 215, 0))
        screen.blit(title, (cx - title.get_width() // 2, 30))

        # 冠军展示（用 pygame 画奖杯，不用 emoji）
        if state.champion_id is not None:
            champion = state.get_player_by_id(state.champion_id)
            if champion:
                # 画奖杯图标
                trophy_x = cx - 120
                trophy_y = 90
                self._draw_trophy_icon(screen, trophy_x, trophy_y, size=32)
                # 冠军文字
                champ_text = f"冠军: {champion.name}"
                champ_surf = app.renderer.font_title.render(champ_text, True, (255, 215, 0))
                screen.blit(champ_surf, (cx - champ_surf.get_width() // 2 + 20, 95))
                # 冠军奖金（只显示奖金，不含底池）
                prize_text = f"奖金: {champion.prize_won:,}"
                prize_surf = app.renderer.font_small.render(prize_text, True, (255, 215, 0))
                screen.blit(prize_surf, (cx - prize_surf.get_width() // 2, 135))

        # 排名列表（用固定列坐标，避免中文字符宽度不一致导致歪斜）
        y = 170
        ranked = sorted(state.players, key=lambda p: (p.final_rank if p.final_rank else 999, -p.chips))
        line_h = 22
        max_lines = (SCREEN_HEIGHT - 80 - y) // line_h

        # 列坐标
        col_rank = cx - 200
        col_name = cx - 130
        col_chips = cx + 10
        col_prize = cx + 130

        # 表头
        header_y = y - line_h
        hdr_surf = app.renderer.font_small.render("排名", True, (160, 160, 160))
        screen.blit(hdr_surf, (col_rank, header_y))
        hdr_surf = app.renderer.font_small.render("玩家", True, (160, 160, 160))
        screen.blit(hdr_surf, (col_name, header_y))
        hdr_surf = app.renderer.font_small.render("筹码", True, (160, 160, 160))
        screen.blit(hdr_surf, (col_chips, header_y))
        hdr_surf = app.renderer.font_small.render("奖金", True, (160, 160, 160))
        screen.blit(hdr_surf, (col_prize, header_y))

        for i, p in enumerate(ranked[:max_lines]):
            row_y = y + i * line_h
            rank = p.final_rank if p.final_rank else "-"
            if p.is_human:
                name = "你"
                color = (100, 255, 150)
            else:
                name = p.name
                color = (200, 200, 200)

            # 前三名用奖牌颜色
            rank_colors = {1: (255, 215, 0), 2: (192, 192, 192), 3: (205, 127, 50)}
            rank_color = rank_colors.get(rank if isinstance(rank, int) else 0, color)
            text_color = rank_color if rank in (1, 2, 3) else color

            # 排名
            rank_str = f"第{rank}名" if isinstance(rank, int) else str(rank)
            rank_surf = app.renderer.font_small.render(rank_str, True, text_color)
            screen.blit(rank_surf, (col_rank, row_y))
            # 玩家名
            name_surf = app.renderer.font_small.render(name, True, text_color)
            screen.blit(name_surf, (col_name, row_y))
            # 筹码
            chips_surf = app.renderer.font_small.render(f"{p.chips:,}", True, text_color)
            screen.blit(chips_surf, (col_chips, row_y))
            # 奖金
            prize_surf = app.renderer.font_small.render(f"{p.prize_won:,}", True, text_color)
            screen.blit(prize_surf, (col_prize, row_y))

        # 返回按钮
        if not hasattr(app, 'tournament_result_buttons'):
            from ui.components import Button
            app.tournament_result_buttons = {
                "back": Button(cx - 100, SCREEN_HEIGHT - 80, 200, 50, "返回菜单", color=(80, 80, 80)),
            }
            app.tournament_result_buttons["back"].on_click = lambda: (
                app.tournament_controller.clear_save(),
                setattr(app, 'scene', 'menu'),
            )

        mouse_pos = pygame.mouse.get_pos()
        for btn in app.tournament_result_buttons.values():
            btn.update(mouse_pos)
            btn.draw(screen)

    def _draw_trophy_icon(self, screen, x, y, size=32):
        """用 pygame 基本图形画奖杯图标"""
        gold = (255, 200, 50)
        gold_dark = (200, 150, 30)
        # 杯体（梯形）
        cup_pts = [
            (x, y),
            (x + size, y),
            (x + size - 4, y + size // 2),
            (x + 4, y + size // 2),
        ]
        pygame.draw.polygon(screen, gold, cup_pts)
        # 左把手
        pygame.draw.arc(screen, gold, (x - 8, y + 2, 12, size // 3), 0, 3.14, 3)
        # 右把手
        pygame.draw.arc(screen, gold, (x + size - 4, y + 2, 12, size // 3), 0, 3.14, 3)
        # 杯柱
        stem_x = x + size // 2 - 3
        pygame.draw.rect(screen, gold_dark, (stem_x, y + size // 2, 6, size // 4))
        # 底座
        pygame.draw.rect(screen, gold_dark, (x + 4, y + size // 2 + size // 4, size - 8, 6))
