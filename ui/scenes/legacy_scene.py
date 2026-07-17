"""LegacyScene：安全回退场景。

所有 13 个场景已注册为独立 Scene 类，此场景仅在 switch_scene 找不到
注册场景时作为兜底使用。正常流程不会到达此处。
"""

from .base_scene import BaseScene


class LegacyScene(BaseScene):
    """兜底场景 — 仅打印警告，不做任何操作。"""

    def __init__(self, app, scene_name: str = "unknown"):
        super().__init__(app)
        self._scene_name = scene_name

    @property
    def name(self) -> str:
        return self._scene_name

    def on_enter(self):
        print(f"[Warning] LegacyScene fallback for '{self._scene_name}' — no registered Scene found.")

    def handle_event(self, event):
        pass

    def update(self, dt: float):
        self.app.animations.update(dt)

    def render(self, screen):
        pass
