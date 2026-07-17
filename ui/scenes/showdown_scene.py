"""摊牌场景：展示手牌比较结果，点击/空格继续"""
import pygame
from .base_scene import BaseScene


class ShowdownScene(BaseScene):
    """摊牌结算场景"""

    @property
    def name(self) -> str:
        return "showdown"

    def handle_event(self, event):
        app = self.app
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        # ESC 处理：锦标赛 showdown → 离开锦标赛；普通 → 回菜单
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            is_tournament = (app.tournament_controller and app.tournament_controller.state
                             and app.tournament_controller.state.phase.value in ("group", "final", "ultimate"))
            if is_tournament and app.game and app.game.on_hand_end == app._on_tournament_hand_end:
                app._leave_tournament()
            else:
                app._leave_game()
            return

        # 空格或点击 → 下一手
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            app._next_hand()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            app._next_hand()

    def update(self, dt: float):
        app = self.app
        app.animations.update(dt)
        app.showdown_timer += dt

        # 轮询 AI 回复玩家聊天的结果（玩家可能在摊牌阶段@AI）
        if hasattr(app, 'dialogue_manager') and app.dialogue_manager:
            replies = app.dialogue_manager.poll_replies()
            for reply in replies:
                app.chat_controller.add_message(
                    reply.metadata.get("char_name", ""),
                    reply.text,
                    "llm"
                )

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_showdown()
        app._present()
