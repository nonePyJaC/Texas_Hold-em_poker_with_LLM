"""锦标赛对局场景：继承 PlayingScene，覆盖离开逻辑和渲染"""
import pygame
from .playing_scene import PlayingScene


class TournamentScene(PlayingScene):
    """锦标赛进行中场景 — 共享 AI 流程，离开按钮调用 _leave_tournament"""

    @property
    def name(self) -> str:
        return "tournament"

    def handle_event(self, event):
        app = self.app
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                app._toggle_fullscreen()
                return
            if event.key == pygame.K_ESCAPE:
                # 优先关闭弹窗
                if app.selected_player_index is not None:
                    app.selected_player_index = None
                    app.player_popup_close_btn = None
                    return
                # 锦标赛进行中 ESC 存档离开
                app._leave_tournament()
                return

        self._handle_playing_event(event)

    def _on_leave(self):
        """离开锦标赛（存档）"""
        self.app._leave_tournament()

    def update(self, dt: float):
        app = self.app
        app.animations.update(dt)
        self._update_common(dt)
        self._update_ai_flow(dt)

        # 锦标赛等待场景检查（从 _update_legacy 迁移）
        # 注意：tournament_waiting 是独立场景，这里不处理

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_tournament()
        app._present()
