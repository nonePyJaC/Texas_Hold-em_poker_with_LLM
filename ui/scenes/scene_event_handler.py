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
        positions = app.renderer.get_seat_positions(len(app.players))
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
            self.app._window_size = (max(event.w, SCREEN_WIDTH), max(event.h, SCREEN_HEIGHT))
            self.app.display = pygame.display.set_mode(self.app._window_size, self.app._window_flags)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                self.app._toggle_fullscreen()
                return
            if event.key == pygame.K_ESCAPE:
                # 优先关闭弹窗（仅在 playing 场景）
                if self.app.scene == "playing" and self.app.selected_player_index is not None:
                    self.app.selected_player_index = None
                    self.app.player_popup_close_btn = None
                    return
                # 其他场景按 ESC 返回菜单
                if self.app.scene in ("playing", "setup", "settings", "history"):
                    self.app.selected_player_index = None
                    self.app.player_popup_close_btn = None
                    self.app.scene = "menu"
                elif self.app.scene == "menu":
                    self.app._quit()
                return
            elif event.key == pygame.K_SPACE:
                if self.app.scene == "showdown":
                    self.app._next_hand()

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
