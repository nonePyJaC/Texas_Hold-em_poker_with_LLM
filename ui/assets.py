"""资源加载模块：程序化生成扑克牌、筹码等图形资源，并优先加载真实的外部素材"""
import math
import os
import sys

# 支持直接运行此文件时也能找到项目根目录下的模块
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pygame
from config import (
    COLOR_CARD_FACE, COLOR_CARD_BACK, COLOR_BLACK, COLOR_WHITE,
    COLOR_RED, COLOR_GOLD, COLOR_CHIP_RED, COLOR_CHIP_BLUE,
    COLOR_CHIP_GREEN, COLOR_CHIP_BLACK, COLOR_CHIP_WHITE,
)
from engine.deck import RANK_NAMES, SUIT_SYMBOLS, SUIT_COLORS
from ui.font_util import get_font

# 缓存
_card_cache = {}
_chip_cache = {}

# Kenney 资产目录（相对路径，兼容 PyInstaller 打包）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KENNEY_CARDS_DIR = os.path.join(_PROJECT_ROOT, "kenney_boardgame-pack", "PNG", "Cards")

# 映射字典
SUIT_MAP = {
    's': 'Spades',
    'h': 'Hearts',
    'd': 'Diamonds',
    'c': 'Clubs'
}
RANK_MAP = {
    2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9', 10: '10',
    11: 'J', 12: 'Q', 13: 'K', 14: 'A'
}


def get_card_surface(card, w=70, h=100, face_up=True):
    """获取牌面 Surface（带缓存，优先加载 Kenney 外部素材，否则程序化生成）"""
    key = (card.rank, card.suit, w, h, face_up)
    if key in _card_cache:
        return _card_cache[key]

    if not face_up:
        return get_card_back(w, h)

    # 尝试加载 Kenney 素材
    suit_name = SUIT_MAP.get(card.suit)
    rank_name = RANK_MAP.get(card.rank)
    if suit_name and rank_name:
        filename = f"card{suit_name}{rank_name}.png"
        filepath = os.path.join(KENNEY_CARDS_DIR, filename)
        if os.path.exists(filepath):
            try:
                img = pygame.image.load(filepath).convert_alpha()
                surf = pygame.transform.smoothscale(img, (w, h))
                _card_cache[key] = surf
                return surf
            except Exception:
                pass

    # 程序化生成备用牌面
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, COLOR_CARD_FACE, (0, 0, w, h), border_radius=8)
    pygame.draw.rect(surf, COLOR_BLACK, (0, 0, w, h), 1, border_radius=8)

    color = COLOR_RED if SUIT_COLORS[card.suit] == 'red' else COLOR_BLACK

    font_rank = get_font(20, bold=True)
    font_suit = get_font(18)

    rank_str = RANK_NAMES[card.rank]
    suit_str = SUIT_SYMBOLS[card.suit]

    # 左上角
    rank_surf = font_rank.render(rank_str, True, color)
    suit_surf = font_suit.render(suit_str, True, color)
    surf.blit(rank_surf, (5, 3))
    surf.blit(suit_surf, (5, 22))

    # 右下角（倒置）
    rank_flip = pygame.transform.rotate(rank_surf, 180)
    suit_flip = pygame.transform.rotate(suit_surf, 180)
    surf.blit(rank_flip, (w - 5 - rank_flip.get_width(), h - 3 - rank_flip.get_height()))
    surf.blit(suit_flip, (w - 5 - suit_flip.get_width(), h - 22 - suit_flip.get_height()))

    # 中央大花色
    big_suit = get_font(36).render(suit_str, True, color)
    surf.blit(big_suit, (w // 2 - big_suit.get_width() // 2, h // 2 - big_suit.get_height() // 2))

    _card_cache[key] = surf
    return surf


def get_card_back(w=70, h=100):
    """获取牌背 Surface（优先加载 Kenney 外部素材，否则程序化生成）"""
    key = ("back", w, h)
    if key in _card_cache:
        return _card_cache[key]

    # 尝试加载 Kenney 素材中的蓝色或红色经典牌背
    filepath = os.path.join(KENNEY_CARDS_DIR, "cardBack_blue2.png")
    if os.path.exists(filepath):
        try:
            img = pygame.image.load(filepath).convert_alpha()
            surf = pygame.transform.smoothscale(img, (w, h))
            _card_cache[key] = surf
            return surf
        except Exception:
            pass

    # 程序化生成备用牌背
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, COLOR_CARD_BACK, (0, 0, w, h), border_radius=8)
    pygame.draw.rect(surf, COLOR_WHITE, (0, 0, w, h), 2, border_radius=8)

    for i in range(4, w - 4, 6):
        for j in range(4, h - 4, 6):
            if (i + j) % 12 == 0:
                pygame.draw.circle(surf, (100, 140, 200), (i, j), 2)

    _card_cache[key] = surf
    return surf


def _chip_color_for_amount(amount):
    """根据金额返回筹码颜色：便于识别 10/20/50/100 等面值"""
    if amount >= 500:
        return (120, 40, 160)   # 紫色
    elif amount >= 100:
        return (30, 30, 30)     # 黑色
    elif amount >= 50:
        return (30, 160, 70)   # 绿色
    elif amount >= 20:
        return (40, 90, 200)   # 蓝色
    elif amount >= 10:
        return (210, 35, 35)   # 红色
    else:
        return (230, 230, 230)  # 白色


def _draw_single_chip(surface, cx, cy, radius, color):
    """程序化绘制一枚俯视筹码，边缘清晰无切图问题"""
    # 厚度阴影
    pygame.draw.circle(surface, (0, 0, 0, 60), (cx + 1, cy + 2), radius)
    # 主色
    pygame.draw.circle(surface, color, (cx, cy), radius)
    # 外圈白边
    pygame.draw.circle(surface, (240, 240, 240), (cx, cy), radius, 2)
    # 内圈浅色圆
    inner_r = max(2, radius - 6)
    inner_color = tuple(min(255, c + 30) for c in color[:3])
    pygame.draw.circle(surface, inner_color, (cx, cy), inner_r)
    # 边缘装饰点
    if radius >= 8:
        dot_r = 2
        dots = 8
        for i in range(dots):
            angle = 2 * math.pi * i / dots
            dot_x = cx + int((radius - 4) * math.cos(angle))
            dot_y = cy + int((radius - 4) * math.sin(angle))
            pygame.draw.circle(surface, (240, 240, 240), (dot_x, dot_y), dot_r)


def get_chip_surface(amount, radius=16):
    """获取彩色堆叠筹码 Surface（程序化绘制，无素材切边问题）"""
    effective_amount = amount
    if radius <= 10:
        # 小指示器也按真实金额着色，但只堆叠 1 层
        effective_amount = amount

    key = ("stack", effective_amount, radius)
    if key in _chip_cache:
        return _chip_cache[key]

    color = _chip_color_for_amount(effective_amount)

    # 堆叠层数：随金额增加，但限制最大层数避免过高
    if radius <= 10:
        num_chips = 1
    else:
        if amount >= 500:
            num_chips = 8
        elif amount >= 200:
            num_chips = 6
        elif amount >= 100:
            num_chips = 5
        elif amount >= 50:
            num_chips = 4
        elif amount >= 20:
            num_chips = 3
        elif amount >= 10:
            num_chips = 2
        else:
            num_chips = 1

    offset_y = max(3, int(radius * 0.28))
    total_h = radius * 2 + (num_chips - 1) * offset_y + 4
    surf = pygame.Surface((radius * 2 + 4, total_h), pygame.SRCALPHA)
    cx = radius + 2

    for i in range(num_chips):
        cy = total_h - radius - 2 - i * offset_y
        _draw_single_chip(surf, cx, cy, radius, color)

    _chip_cache[key] = surf
    return surf


# 筹码面值定义（从大到小）
_CHIP_DENOMINATIONS = [500, 100, 50, 20, 10, 1]


def _breakdown_amount(amount):
    """将金额按面值拆分为 {面值: 数量} 字典"""
    result = {}
    remaining = amount
    for denom in _CHIP_DENOMINATIONS:
        if remaining <= 0:
            break
        count = remaining // denom
        if count > 0:
            result[denom] = count
            remaining -= count * denom
    return result


def get_pot_chip_surface(amount, radius=16):
    """获取底池筹码 Surface：按面值拆分成多摞并排展示"""
    key = ("pot", amount, radius)
    if key in _chip_cache:
        return _chip_cache[key]

    breakdown = _breakdown_amount(amount)
    if not breakdown:
        # 金额为 0，画一个白色空筹码
        surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        _draw_single_chip(surf, radius + 2, radius + 2, radius, (230, 230, 230))
        _chip_cache[key] = surf
        return surf

    # 每摞最多显示 5 层，超过则压缩
    max_stack = 5
    offset_y = max(3, int(radius * 0.28))

    # 计算每摞的宽度
    stack_w = radius * 2 + 4
    stack_gap = 3  # 摞间间距

    denoms = sorted(breakdown.keys(), reverse=True)
    num_stacks = len(denoms)

    # 计算总宽度和最大高度
    total_w = num_stacks * stack_w + (num_stacks - 1) * stack_gap
    max_h = 0
    stack_heights = []
    for denom in denoms:
        count = breakdown[denom]
        display_count = min(count, max_stack)
        h = radius * 2 + (display_count - 1) * offset_y + 4
        stack_heights.append(h)
        if h > max_h:
            max_h = h

    surf = pygame.Surface((total_w, max_h), pygame.SRCALPHA)

    x = 0
    for i, denom in enumerate(denoms):
        count = breakdown[denom]
        display_count = min(count, max_stack)
        color = _chip_color_for_amount(denom)
        cx = x + radius + 2

        for j in range(display_count):
            cy = max_h - radius - 2 - j * offset_y
            _draw_single_chip(surf, cx, cy, radius, color)

        x += stack_w + stack_gap

    _chip_cache[key] = surf
    return surf


def get_dealer_button(radius=18):
    """获取庄家按钮 Surface"""
    surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
    cx, cy = radius + 2, radius + 2
    pygame.draw.circle(surf, COLOR_WHITE, (cx, cy), radius)
    pygame.draw.circle(surf, COLOR_BLACK, (cx, cy), radius, 2)

    # 用中文字体绘制 "庄" (字体缩小一点以完美居中)
    font = get_font(int(radius * 1.15), bold=True)
    text = font.render("庄", True, COLOR_BLACK)
    surf.blit(text, (cx - text.get_width() // 2, cy - text.get_height() // 2 - 1))
    return surf
