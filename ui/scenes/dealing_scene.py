"""发牌动画场景：逐张发牌动画播放完毕后进入对局"""
import pygame
from .base_scene import BaseScene


class DealingScene(BaseScene):
    """发牌动画场景"""

    @property
    def name(self) -> str:
        return "dealing"

    def handle_event(self, event):
        app = self.app
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            # 发牌动画期间仅允许 ESC 离开
            is_tournament = (app.tournament_controller and app.tournament_controller.state
                             and app.tournament_controller.state.phase.value in ("group", "final", "ultimate"))
            if is_tournament:
                app._leave_tournament()
            else:
                app._leave_game()
            return

    def update(self, dt: float):
        app = self.app
        app.animations.update(dt)

        # 逐张播放发牌音效
        app._dealing_timer += dt
        card_delay = 0.12
        while app._dealing_card_index < app._dealing_total_cards:
            if app._dealing_timer >= app._dealing_card_index * card_delay:
                app.audio.play("deal")
                app._dealing_card_index += 1
            else:
                break

        # 所有动画结束后进入 playing 或 tournament
        if not app.animations.is_busy:
            app.animations.clear()
            if (app.tournament_controller and app.tournament_controller.state
                    and app.tournament_controller.state.phase.value in ("group", "final", "ultimate")):
                app.switch_scene("tournament")
            else:
                app.switch_scene("playing")
            app.ai_controller.check_turn()

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_dealing()
        app._present()
