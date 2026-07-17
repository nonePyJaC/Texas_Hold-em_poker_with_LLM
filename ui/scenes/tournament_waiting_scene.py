"""锦标赛等待场景：等待其他桌完成，自动推进"""
import pygame
from .base_scene import BaseScene


class TournamentWaitingScene(BaseScene):
    """锦标赛等待页 — 仅处理自动跳转（在 update 中检查）"""

    @property
    def name(self) -> str:
        return "tournament_waiting"

    def handle_event(self, event):
        app = self.app
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            app._leave_tournament()
            return

    def update(self, dt: float):
        app = self.app
        app.animations.update(dt)

        # 仅在小组赛阶段检查所有桌是否完成
        state = app.tournament_controller.state
        if state and state.phase.value == "group":
            if app._check_all_tables_done():
                app.tournament_controller.advance_to_final_stage()
                human = state.human_player
                if human and not human.eliminated:
                    app._setup_tournament_table("final")
                else:
                    app._auto_simulate_final_and_ultimate()

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_tournament_waiting()
        app._present()
