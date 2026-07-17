"""回放场景：逐步回放历史手牌"""
import pygame
from .base_scene import BaseScene
from .replay_renderer import fix_blind_phases, normalize_action_order


class ReplayScene(BaseScene):
    """手牌回放场景"""

    @property
    def name(self) -> str:
        return "replay"

    def start_replay(self, hand_data):
        """开始回放指定手牌"""
        app = self.app
        actions = hand_data.get("actions", [])
        actions = fix_blind_phases(actions)
        actions = normalize_action_order(actions)
        hand_data = {**hand_data, "actions": actions}

        app.replay_state = {
            "hand_data": hand_data,
            "step": 0,
            "timer": 0.0,
            "paused": False,
            "speed": 1.0,
        }
        app.switch_scene("replay")

    def replay_next(self):
        """回放前进一步"""
        app = self.app
        if not app.replay_state:
            return
        actions = app.replay_state["hand_data"].get("actions", [])
        total = len(actions) + 1
        if app.replay_state["step"] < total:
            app.replay_state["step"] += 1
            app.replay_state["timer"] = 0.0

    def replay_prev(self):
        """回放后退一步"""
        app = self.app
        if not app.replay_state:
            return
        if app.replay_state["step"] > 0:
            app.replay_state["step"] -= 1
            app.replay_state["timer"] = 0.0

    def replay_toggle_play(self):
        """切换回放播放/暂停"""
        app = self.app
        if not app.replay_state:
            return
        app.replay_state["paused"] = not app.replay_state.get("paused", False)

    def handle_event(self, event):
        app = self.app
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                app.switch_scene("menu")
                return
            elif event.key == pygame.K_SPACE:
                self.replay_toggle_play()
                return
            elif event.key == pygame.K_LEFT:
                self.replay_prev()
                return
            elif event.key == pygame.K_RIGHT:
                self.replay_next()
                return

        # 回放控制按钮
        for btn in app.replay_buttons.values():
            btn.handle_event(event)

    def update(self, dt: float):
        app = self.app
        app.animations.update(dt)

        if app.replay_state and not app.replay_state.get("paused", False):
            app.replay_state["timer"] += dt * app.replay_state.get("speed", 1.0)
            step_delay = 1.2
            if app.replay_state["timer"] >= step_delay:
                app.replay_state["timer"] = 0.0
                actions = app.replay_state["hand_data"].get("actions", [])
                total = len(actions) + 1
                if app.replay_state["step"] < total:
                    app.replay_state["step"] += 1
                else:
                    app.replay_state["paused"] = True

    def render(self, screen):
        app = self.app
        app.scene_renderer.replay_renderer.render()
        app._present()
