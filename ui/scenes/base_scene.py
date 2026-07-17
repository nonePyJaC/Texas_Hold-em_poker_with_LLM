"""场景基类：所有场景的公共接口。

每个场景负责自己的事件处理、更新逻辑和渲染。
GameApp 通过 switch_scene() 切换场景，委托 update/handle_event/render 给当前场景。
"""


class BaseScene:
    """场景基类，子类需实现 on_enter/on_exit/handle_event/update/render。

    Attributes:
        app: GameApp 实例，用于访问共享资源（screen, renderer, audio, game, players 等）
    """

    def __init__(self, app):
        self.app = app

    @property
    def name(self) -> str:
        """场景名称，用于注册和切换。子类可覆盖。"""
        return self.__class__.__name__

    def on_enter(self):
        """进入场景时调用，用于初始化场景状态。"""
        pass

    def on_exit(self):
        """离开场景时调用，用于清理场景状态。"""
        pass

    def handle_event(self, event):
        """处理 pygame 事件。子类必须实现。"""
        pass

    def update(self, dt: float):
        """每帧更新逻辑。子类必须实现。

        Args:
            dt: 距上一帧的时间（秒）
        """
        pass

    def render(self, screen):
        """渲染场景到 screen。子类必须实现。

        Args:
            screen: pygame Surface，渲染目标
        """
        pass
