"""锦标赛结果场景：显示最终排名，返回菜单"""
import pygame
from .base_scene import BaseScene


class TournamentResultScene(BaseScene):
    """锦标赛结果页"""

    @property
    def name(self) -> str:
        return "tournament_result"

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

        if hasattr(app, 'tournament_result_buttons'):
            for btn in app.tournament_result_buttons.values():
                btn.handle_event(event)

    def update(self, dt: float):
        self.app.animations.update(dt)

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_tournament_result()
        app._present()
