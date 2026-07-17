"""锦标赛设置场景：选择开始/继续锦标赛"""
import pygame
from .base_scene import BaseScene


class TournamentSetupScene(BaseScene):
    """锦标赛设置页面"""

    @property
    def name(self) -> str:
        return "tournament_setup"

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

        for btn in app.tournament_buttons.values():
            if hasattr(btn, 'visible') and not btn.visible:
                continue
            btn.handle_event(event)

    def update(self, dt: float):
        self.app.animations.update(dt)

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_tournament_setup()
        app._present()
