"""主菜单场景"""
import pygame
from config import SCREEN_WIDTH
from .base_scene import BaseScene


class MenuScene(BaseScene):
    """主菜单：开始游戏 / 锦标赛 / 设置 / 退出 / 每日奖励 / 贷款 / 对战记录"""

    @property
    def name(self) -> str:
        return "menu"

    def on_enter(self):
        pass

    def handle_event(self, event):
        app = self.app
        # 鼠标坐标映射
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            app._quit()
            return

        for btn in app.menu_buttons.values():
            btn.handle_event(event)
        if app.history_button.handle_event(event):
            app.switch_scene("history")

    def update(self, dt: float):
        # 菜单无特殊更新逻辑，只更新动画
        self.app.animations.update(dt)

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_menu()
        app._present()
