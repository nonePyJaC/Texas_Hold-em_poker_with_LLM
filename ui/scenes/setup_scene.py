"""游戏设置场景：配置玩家数量、盲注、下注模式、牌组、难度、买入金额"""
import pygame
from .base_scene import BaseScene


class SetupScene(BaseScene):
    """开局设置场景"""

    @property
    def name(self) -> str:
        return "setup"

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

        for comp in app.setup_components.values():
            if hasattr(comp, 'handle_event'):
                comp.handle_event(event)

    def update(self, dt: float):
        self.app.animations.update(dt)

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_setup()
        app._present()
