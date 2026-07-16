"""场景事件处理器：将 GameApp 中的事件分发逻辑抽离"""
import pygame
from config import SCREEN_WIDTH, SCREEN_HEIGHT


class SceneEventHandler:
    """负责所有场景的事件处理与分发"""

    CARD_W = 160
    CARD_H = 70

    def __init__(self, game_app):
        """Args:
            game_app: GameApp 实例
        """
        self.app = game_app

    def _find_clicked_player_index(self, mouse_pos):
        """返回鼠标位置下的 AI 玩家索引，未命中返回 -1"""
        app = self.app
        if not app.game or not app.players:
            return -1
        positions = app.renderer.get_seat_positions(app.players)
        for i, player in enumerate(app.players):
            if player.is_human or not hasattr(player, '_char_stats'):
                continue
            pos = positions[i]
            rect = pygame.Rect(
                pos[0] - self.CARD_W // 2,
                pos[1] - self.CARD_H // 2,
                self.CARD_W,
                self.CARD_H,
            )
            if rect.collidepoint(mouse_pos):
                return i
        return -1

    def handle_event(self, event):
        """处理事件"""
        # 将鼠标坐标事件映射到虚拟 1280x720 坐标
        if hasattr(event, 'pos'):
            event.pos = self.app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            self.app._quit()

        if event.type == pygame.VIDEORESIZE:
            new_w = max(event.w, SCREEN_WIDTH)
            new_h = max(event.h, SCREEN_HEIGHT)
            if new_w != event.w or new_h != event.h:
                pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)
            self.app._window_size = (new_w, new_h)
            self.app.display = pygame.display.get_surface()
            self.app.screen = self.app.display
            self.app.renderer.screen = self.app.display

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                self.app._toggle_fullscreen()
                return
            if event.key == pygame.K_ESCAPE:
                # 优先关闭弹窗（playing 和 tournament 场景）
                if self.app.scene in ("playing", "tournament") and self.app.selected_player_index is not None:
                    self.app.selected_player_index = None
                    self.app.player_popup_close_btn = None
                    return
                # 锦标赛场景按 ESC 存档离开（含 showdown/dealing）
                is_tournament = (self.app.tournament_controller and self.app.tournament_controller.state)
                if is_tournament and self.app.scene in ("tournament", "dealing"):
                    # 锦标赛进行中，ESC 存档离开
                    self.app._leave_tournament()
                    return
                if is_tournament and self.app.scene == "showdown" and self.app.game and self.app.game.on_hand_end == self.app._on_tournament_hand_end:
                    self.app._leave_tournament()
                    return
                # 其他场景按 ESC 返回菜单
                if self.app.scene in ("playing", "setup", "settings", "history", "replay", "tournament_setup", "tournament_waiting", "tournament_result"):
                    self.app.selected_player_index = None
                    self.app.player_popup_close_btn = None
                    self.app.scene = "menu"
                elif self.app.scene == "menu":
                    self.app._quit()
                return
            elif event.key == pygame.K_SPACE:
                if self.app.scene == "showdown":
                    self.app._next_hand()
                elif self.app.scene == "replay":
                    self.app._replay_toggle_play()
            elif event.key == pygame.K_LEFT:
                if self.app.scene == "replay":
                    self.app._replay_prev()
                    return
            elif event.key == pygame.K_RIGHT:
                if self.app.scene == "replay":
                    self.app._replay_next()
                    return

        if self.app.scene == "menu":
            for btn in self.app.menu_buttons.values():
                btn.handle_event(event)
            if self.app.history_button.handle_event(event):
                self.app.scene = "history"

        elif self.app.scene == "setup":
            for comp in self.app.setup_components.values():
                if hasattr(comp, 'handle_event'):
                    comp.handle_event(event)

        elif self.app.scene == "settings":
            for comp in self.app.settings_components.values():
                if hasattr(comp, 'handle_event'):
                    comp.handle_event(event)
            # 音量滑块更新
            if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.MOUSEMOTION:
                vol = self.app.settings_components["volume"].value
                self.app.audio.set_volume(vol)

        elif self.app.scene == "bankruptcy":
            for btn in self.app.bankruptcy_buttons.values():
                btn.handle_event(event)

        elif self.app.scene == "dealing":
            # 发牌动画期间仅允许 ESC 离开
            pass

        elif self.app.scene == "playing":
            self._handle_playing_event(event)

        elif self.app.scene == "showdown":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.app._next_hand()

        elif self.app.scene == "history":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_history_click(event.pos)

        elif self.app.scene == "replay":
            self._handle_replay_event(event)

        elif self.app.scene == "tournament_setup":
            for btn in self.app.tournament_buttons.values():
                if hasattr(btn, 'visible') and not btn.visible:
                    continue
                btn.handle_event(event)

        elif self.app.scene == "tournament":
            self._handle_tournament_event(event)

        elif self.app.scene == "tournament_waiting":
            # 等待页只处理自动跳转（在 update 中处理）
            pass

        elif self.app.scene == "tournament_result":
            if hasattr(self.app, 'tournament_result_buttons'):
                for btn in self.app.tournament_result_buttons.values():
                    btn.handle_event(event)

    def _handle_replay_event(self, event):
        """处理回放场景事件"""
        for btn in self.app.replay_buttons.values():
            btn.handle_event(event)

    def _handle_history_click(self, pos):
        """处理对战记录页面的点击 — 检测回放按钮点击"""
        app = self.app
        history = app.save_manager.player_data.hand_history
        if not history:
            return

        recent_hands = app.game_logger.get_recent_hands(count=50)
        display = list(reversed(history))
        header_y = 80
        col_replay = 740
        max_rows = (SCREEN_HEIGHT - 130) // 28

        for i, entry in enumerate(display[:max_rows]):
            y = header_y + 30 + i * 28
            hand_num = entry.get("game_hand_number", entry.get("hand_num", -1))
            has_full_log = any(rh.get("hand_number") == hand_num for rh in recent_hands)
            if not has_full_log:
                continue

            # 检测点击是否在回放按钮区域
            replay_rect = pygame.Rect(col_replay - 5, y - 2, 60, 22)
            if replay_rect.collidepoint(pos):
                # 找到完整日志并启动回放
                full_hands = app.game_logger.get_recent_full_hands(count=50)
                for hand in full_hands:
                    if hand.get("hand_number") == hand_num:
                        app._start_replay(hand)
                        return

    def _handle_playing_event(self, event):
        """处理游戏中的事件"""
        # 聊天输入处理 (最高优先级，激活时拦截事件)
        if self.app.chat_controller.handle_event(event):
            return

        # Enter 键激活聊天 (仅在加注输入框未激活时)
        if (event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN
                and self.app.chat_controller.input and not self.app.renderer.raise_input.active):
            self.app.chat_controller.input.active = True
            self.app.chat_controller.active = True
            return

        # 弹窗关闭优先处理
        if self.app.selected_player_index is not None:
            if self.app.player_popup_close_btn and self.app.player_popup_close_btn.handle_event(event):
                self.app.selected_player_index = None
                self.app.player_popup_close_btn = None
                return
            # 点击弹窗外部任意位置也关闭
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.app.selected_player_index = None
                self.app.player_popup_close_btn = None
                return

        # 离开按钮 - 任何时候都可以点击
        if self.app.renderer.leave_button.handle_event(event):
            self.app._leave_game()
            return

        # 点击 AI 玩家卡片打开详情弹窗
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.app.scene == "playing" and self.app.game:
            idx = self._find_clicked_player_index(event.pos)
            if idx >= 0:
                self.app.selected_player_index = idx
                return

        # 右键点击 AI 玩家卡片：艾特该 AI
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and self.app.scene == "playing" and self.app.game:
            idx = self._find_clicked_player_index(event.pos)
            if idx >= 0:
                self.app.chat_controller.activate_with_target(self.app.players[idx].name)
                return

        if self.app.ai_thinking:
            return

        if self.app.scene != "playing":
            return

        current = self.app.game.get_current_player()
        if not current or not current.is_human or not current.can_act():
            return

        # 操作面板按钮
        for key, btn in self.app.renderer.action_buttons.items():
            if btn.handle_event(event):
                self.app._on_human_action(key)
                return

        # 加注滑块
        if self.app.renderer.raise_slider.handle_event(event):
            return

        # 加注数值输入框
        if self.app.renderer.raise_input.handle_event(event):
            return

    def _handle_tournament_event(self, event):
        """处理锦标赛进行中的事件（复用 playing 逻辑，但离开按钮调用 _leave_tournament）"""
        # 聊天输入处理
        if self.app.chat_controller.handle_event(event):
            return

        if (event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN
                and self.app.chat_controller.input and not self.app.renderer.raise_input.active):
            self.app.chat_controller.input.active = True
            self.app.chat_controller.active = True
            return

        # 弹窗关闭
        if self.app.selected_player_index is not None:
            if self.app.player_popup_close_btn and self.app.player_popup_close_btn.handle_event(event):
                self.app.selected_player_index = None
                self.app.player_popup_close_btn = None
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.app.selected_player_index = None
                self.app.player_popup_close_btn = None
                return

        # 离开按钮 → 存档离开锦标赛
        if self.app.renderer.leave_button.handle_event(event):
            self.app._leave_tournament()
            return

        # 点击 AI 玩家卡片打开详情
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.app.game:
            idx = self._find_clicked_player_index(event.pos)
            if idx >= 0:
                self.app.selected_player_index = idx
                return

        # 右键点击 AI 玩家：艾特
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and self.app.game:
            idx = self._find_clicked_player_index(event.pos)
            if idx >= 0:
                self.app.chat_controller.activate_with_target(self.app.players[idx].name)
                return

        if self.app.ai_thinking:
            return

        if self.app.scene != "tournament":
            return

        current = self.app.game.get_current_player()
        if not current or not current.is_human or not current.can_act():
            return

        # 操作面板按钮
        for key, btn in self.app.renderer.action_buttons.items():
            if btn.handle_event(event):
                self.app._on_human_action(key)
                return

        # 加注滑块
        if self.app.renderer.raise_slider.handle_event(event):
            return

        # 加注数值输入框
        if self.app.renderer.raise_input.handle_event(event):
            return
