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

        # 排行榜滚轮
        if event.type == pygame.MOUSEWHEEL:
            panel_rect = getattr(app, '_lb_panel_rect', None)
            max_scroll = getattr(app, '_lb_max_scroll', 0)
            if panel_rect and max_scroll > 0:
                mouse_pos = pygame.mouse.get_pos()
                if panel_rect.collidepoint(mouse_pos):
                    scroll_speed = 48
                    app._lb_scroll = max(0, min(max_scroll,
                        getattr(app, '_lb_scroll', 0) - event.y * scroll_speed))
            return

        # 排行榜点击选中
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            entry_rects = getattr(app, '_lb_entry_rects', [])
            clicked_idx = None
            for i, rect in enumerate(entry_rects):
                if rect and rect.collidepoint(event.pos):
                    clicked_idx = i
                    break
            if clicked_idx is not None:
                # 再次点击同一条目则取消选中
                if getattr(app, '_lb_selected', None) == clicked_idx:
                    app._lb_selected = None
                else:
                    app._lb_selected = clicked_idx
                return
            else:
                # 点击排行榜外区域取消选中
                panel_rect = getattr(app, '_lb_panel_rect', None)
                if panel_rect and not panel_rect.collidepoint(event.pos):
                    app._lb_selected = None

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
