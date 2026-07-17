"""滚动播报系统 — 在屏幕顶部显示大牌播报消息

消息从右向左滚动，牌型越大颜色越炫彩。
"""
import pygame
from typing import List, Optional
from ui.font_util import get_font
from game_logic.background_simulator import BroadcastMessage


class BroadcastBar:
    """滚动播报栏 — 管理多条播报消息的排队和渲染"""

    def __init__(self, screen_width: int):
        self.screen_width = screen_width
        self.messages: List[BroadcastMessage] = []
        self._current: Optional[BroadcastMessage] = None
        self._scroll_x = 0.0
        self._text_width = 0

    def add(self, msg: BroadcastMessage):
        """添加一条播报消息到队列"""
        self.messages.append(msg)

    def add_local(self, text: str, color, rank: int):
        """直接创建并添加一条本地播报（玩家自己的大牌）"""
        msg = BroadcastMessage(text, color, rank)
        msg.duration = 999.0  # 不用时间截断，靠滚动位置决定消失
        self.messages.append(msg)

    def update(self, dt: float):
        """更新播报状态"""
        if self._current is None:
            if self.messages:
                self._current = self.messages.pop(0)
                self._scroll_x = float(self.screen_width)
                # 预计算文字宽度
                font = get_font(22, bold=True)
                surf = font.render(self._current.text, True, self._current.color)
                self._text_width = surf.get_width()
            else:
                return

        self._current.update(dt)

        # 滚动：固定像素速度 60px/s，慢速易读
        scroll_speed = 60.0
        self._scroll_x -= scroll_speed * dt

        # 仅当文字完全滚出屏幕左侧时才消失（不用 duration 截断）
        if self._scroll_x < -self._text_width - 50:
            self._current = None

    def draw(self, screen):
        """渲染当前播报消息"""
        if self._current is None:
            return

        font = get_font(22, bold=True)
        text = self._current.text
        color = self._current.color
        rank = self._current.rank

        text_surf = font.render(text, True, color)

        x = int(self._scroll_x)
        y = 42  # 在顶部场所栏下方

        # 高级牌型添加光晕效果
        if rank >= 6:  # 同花及以上
            # 多层光晕
            for offset in [(2, 0), (-2, 0), (0, 2), (0, -2)]:
                glow_surf = font.render(text, True, color)
                glow_surf.set_alpha(80)
                screen.blit(glow_surf, (x + offset[0], y + offset[1]))

            # 皇家同花顺额外特效
            if rank >= 9:
                # 金色闪烁边框
                pulse = abs(pygame.time.get_ticks() % 1000 - 500) / 500.0
                border_color = (
                    int(255 * (0.5 + 0.5 * pulse)),
                    int(215 * (0.5 + 0.5 * pulse)),
                    int(0 + 100 * pulse),
                )
                bg_rect = pygame.Rect(x - 8, y - 4, text_surf.get_width() + 16, text_surf.get_height() + 8)
                pygame.draw.rect(screen, border_color, bg_rect, 2, border_radius=8)

        screen.blit(text_surf, (x, y))
