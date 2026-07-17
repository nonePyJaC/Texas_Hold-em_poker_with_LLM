"""对战记录场景：查看历史手牌记录，点击回放按钮可进入回放"""
import pygame
from config import SCREEN_HEIGHT
from .base_scene import BaseScene


class HistoryScene(BaseScene):
    """对战记录页面"""

    @property
    def name(self) -> str:
        return "history"

    def handle_event(self, event):
        app = self.app
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            app.switch_scene("menu")
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_history_click(event.pos)

    def update(self, dt: float):
        self.app.animations.update(dt)

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_history()
        app._present()

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

            replay_rect = pygame.Rect(col_replay - 5, y - 2, 60, 22)
            if replay_rect.collidepoint(pos):
                full_hands = app.game_logger.get_recent_full_hands(count=50)
                for hand in full_hands:
                    if hand.get("hand_number") == hand_num:
                        app._start_replay(hand)
                        return
