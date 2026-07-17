"""设置场景：音效、音量、全屏切换、LLM 对话配置"""
import pygame
from .base_scene import BaseScene


class SettingsScene(BaseScene):
    """设置页面"""

    @property
    def name(self) -> str:
        return "settings"

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

        for comp in app.settings_components.values():
            if hasattr(comp, 'handle_event'):
                comp.handle_event(event)

        # 音量滑块实时更新
        if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.MOUSEMOTION:
            vol = app.settings_components["volume"].value
            app.audio.set_volume(vol)

    def update(self, dt: float):
        self.app.animations.update(dt)

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_settings()
        app._present()
