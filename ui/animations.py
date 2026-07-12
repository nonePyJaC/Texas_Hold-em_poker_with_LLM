"""动画模块 - 发牌动画、筹码移动、翻牌动画等"""
import pygame
import random
import time
from typing import List, Optional, Tuple
from engine.deck import Card
from ui.assets import get_card_surface, get_card_back


class Animation:
    """动画基类"""
    def __init__(self, duration: float = 0.5):
        self.duration = duration
        self.elapsed = 0.0
        self.done = False

    def update(self, dt: float):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.done = True

    @property
    def progress(self):
        return min(1.0, self.elapsed / self.duration) if self.duration > 0 else 1.0

    @property
    def eased(self):
        """ease-out 缓动"""
        p = self.progress
        return 1 - (1 - p) ** 3

    def draw(self, screen):
        pass


class DealCardAnimation(Animation):
    """发牌动画 - 牌从牌堆飞向玩家，到达后停留在终点"""
    def __init__(self, start_pos, end_pos, card: Card, duration=0.3, face_up=False, delay=0.0):
        super().__init__(duration)
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.card = card
        self.face_up = face_up
        self.delay = delay
        self._elapsed_with_delay = 0.0
        self.landed = False  # 到达后标记，不再移除

    def update(self, dt: float):
        if self.landed:
            return
        self._elapsed_with_delay += dt
        if self._elapsed_with_delay < self.delay:
            return
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.landed = True  # 到达但不设 done，保持绘制

    @property
    def is_active(self):
        return self._elapsed_with_delay >= self.delay

    def draw(self, screen):
        if not self.is_active:
            return
        if self.landed:
            # 停在终点
            x, y = self.end_pos
            if self.face_up:
                surf = get_card_surface(self.card, 70, 100, face_up=True)
            else:
                surf = get_card_back(70, 100)
            screen.blit(surf, (x - 35, y - 50))
            return

        p = self.eased
        x = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * p
        y = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * p

        # 飞行中显示牌背，接近终点时翻面
        if p < 0.8:
            surf = get_card_back(70, 100)
        else:
            if self.face_up:
                surf = get_card_surface(self.card, 70, 100, face_up=True)
            else:
                surf = get_card_back(70, 100)

        screen.blit(surf, (x - 35, y - 50))


class ChipAnimation(Animation):
    """筹码飞向底池动画"""
    def __init__(self, start_pos, end_pos, amount, duration=0.4, color=(255, 200, 0)):
        super().__init__(duration)
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.amount = amount
        self.color = color

    def draw(self, screen):
        p = self.eased
        x = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * p
        y = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * p

        # 弧线效果
        arc = -50 * p * (1 - p) * 4
        y += arc

        # 画筹码
        radius = 12
        pygame.draw.circle(screen, self.color, (int(x), int(y)), radius)
        pygame.draw.circle(screen, (255, 255, 255), (int(x), int(y)), radius, 2)

        # 金额文字
        from ui.font_util import get_font
        font = get_font(12, bold=True)
        text = font.render(str(self.amount), True, (0, 0, 0))
        screen.blit(text, (x - text.get_width() // 2, y - text.get_height() // 2))


class FlipCardAnimation(Animation):
    """翻牌动画 - 牌从背面翻到正面"""
    def __init__(self, pos, card: Card, duration=0.3):
        super().__init__(duration)
        self.pos = pos
        self.card = card

    def draw(self, screen):
        p = self.progress
        # 0-0.5: 缩小到0, 0.5-1: 从0放大到正常
        if p < 0.5:
            scale = 1 - p * 2
            surf = get_card_back(70, 100)
        else:
            scale = (p - 0.5) * 2
            surf = get_card_surface(self.card, 70, 100, face_up=True)

        w = max(1, int(70 * scale))
        h = 100
        scaled = pygame.transform.scale(surf, (w, h))
        x = self.pos[0] - w // 2
        y = self.pos[1] - h // 2
        screen.blit(scaled, (x, y))


class WinAnimation(Animation):
    """获胜动画 - 筹码从底池飞向赢家"""
    def __init__(self, pot_pos, winner_pos, duration=0.8):
        super().__init__(duration)
        self.pot_pos = pot_pos
        self.winner_pos = winner_pos
        self.chip_offsets = [
            (random.uniform(-30, 30), random.uniform(-30, 30))
            for _ in range(8)
        ]

    def draw(self, screen):
        p = self.eased
        for ox, oy in self.chip_offsets:
            x = self.pot_pos[0] + (self.winner_pos[0] - self.pot_pos[0]) * p + ox * (1 - p)
            y = self.pot_pos[1] + (self.winner_pos[1] - self.pot_pos[1]) * p + oy * (1 - p)
            arc = -40 * p * (1 - p) * 4
            y += arc
            pygame.draw.circle(screen, (255, 200, 0), (int(x), int(y)), 10)
            pygame.draw.circle(screen, (255, 255, 255), (int(x), int(y)), 10, 2)


class TextPopupAnimation(Animation):
    """文字弹出动画 - 如 "ALL IN!" "FOLD" 等"""
    def __init__(self, pos, text, color=(255, 255, 0), duration=1.2):
        super().__init__(duration)
        self.pos = pos
        self.text = text
        self.color = color

    def draw(self, screen):
        from ui.font_util import get_font
        p = self.progress
        # 上升 + 淡出
        y_offset = -30 * p
        alpha = int(255 * (1 - p * p))

        font = get_font(24, bold=True)
        text_surf = font.render(self.text, True, self.color)
        text_surf.set_alpha(alpha)
        x = self.pos[0] - text_surf.get_width() // 2
        y = self.pos[1] - text_surf.get_height() // 2 + y_offset
        screen.blit(text_surf, (x, y))


class AnimationManager:
    """动画管理器"""
    def __init__(self):
        self.animations: List[Animation] = []

    def add(self, anim: Animation):
        self.animations.append(anim)

    def update(self, dt: float):
        for anim in self.animations:
            anim.update(dt)
        self.animations = [a for a in self.animations if not a.done]

    def draw(self, screen):
        for anim in self.animations:
            anim.draw(screen)

    @property
    def is_busy(self):
        # 只要有未落地的动画就忙
        return any(not getattr(a, 'landed', False) for a in self.animations)

    def clear(self):
        self.animations.clear()
