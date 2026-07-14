"""渲染器：绘制游戏画面"""
import math
import colorsys
import pygame
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    COLOR_TABLE_FELT, COLOR_TABLE_RIM, COLOR_TABLE_RIM_DARK, COLOR_BG,
    COLOR_WHITE, COLOR_BLACK, COLOR_GOLD, COLOR_RED, COLOR_GREEN, COLOR_BLUE,
    COLOR_GRAY, COLOR_DARK_GRAY, COLOR_TEXT_DIM, COLOR_PANEL_BG, COLOR_PANEL_BORDER,
    COLOR_FOLD, COLOR_CALL, COLOR_RAISE, COLOR_BUTTON_BG,
    PREFLOP, FLOP, TURN, RIVER, SHOWDOWN,
)
from engine.action import ActionType
from engine.hand_evaluator import HAND_RANK_NAMES
from ui.assets import get_card_surface, get_card_back, get_chip_surface, get_pot_chip_surface, get_dealer_button, get_table_surface
from ui.components import Button, Slider, Panel, TextInput
from ui.font_util import get_font


PHASE_NAMES = {
    PREFLOP: "翻牌前",
    FLOP: "翻牌",
    TURN: "转牌",
    RIVER: "河牌",
    SHOWDOWN: "摊牌",
}

ACTION_NAMES = {
    ActionType.FOLD: "弃牌",
    ActionType.CHECK: "过牌",
    ActionType.CALL: "跟注",
    ActionType.BET: "下注",
    ActionType.RAISE: "加注",
    ActionType.ALL_IN: "全押",
}


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.w = SCREEN_WIDTH
        self.h = SCREEN_HEIGHT

        self.font_title = get_font(28, bold=True)
        self.font_large = get_font(22, bold=True)
        self.font_normal = get_font(18)
        self.font_small = get_font(14)
        self.font_tiny = get_font(12)

        # 操作面板组件
        self.action_buttons = {}
        self.raise_slider = None
        self.raise_input_active = False
        self._init_action_panel()

        # 动画状态
        self.dealing_animation = None
        self.chip_animation = None

        # 渲染缓存
        self._overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        self._avatar_cache = {}  # (name, size) -> surface

    def _init_action_panel(self):
        """初始化操作面板按钮"""
        panel_y = SCREEN_HEIGHT - 90
        btn_w, btn_h = 100, 40
        gap = 12
        start_x = 200

        # 离开按钮（左上角）
        self.leave_button = Button(10, panel_y, 80, 40, "离开", color=(100, 60, 60))

        actions = [
            ("fold", "弃牌", COLOR_FOLD),
            ("check", "过牌", COLOR_GRAY),
            ("call", "跟注", COLOR_CALL),
            ("raise", "加注", COLOR_RAISE),
            ("all_in", "全押", COLOR_RED),
        ]

        for i, (key, label, color) in enumerate(actions):
            x = start_x + i * (btn_w + gap)
            btn = Button(x, panel_y, btn_w, btn_h, label, color=color)
            self.action_buttons[key] = btn

        # 加注滑块 (向右移动 60 像素，消除与全押按钮的重叠)
        slider_x = start_x + 5 * (btn_w + gap) + 70
        self.raise_slider = Slider(slider_x, panel_y + 10, 180, 20, 0, 1000, show_value=False)

        # 加注数值输入框 (滑块右侧，支持手动输入数字)
        self.raise_input = TextInput(
            slider_x + 190, panel_y + 5, 90, 30,
            "金额", font_size=18, numeric_only=True, max_length=8
        )

    def draw_background(self):
        self.screen.fill(COLOR_BG)

    # 8 个固定座位坐标（对应 1280x720 的牌桌素材）
    # 从底部人类玩家开始逆时针编号：0 底部，1 左下，2 左侧，3 左上，4 顶部，5 右上，6 右侧，7 右下
    SEAT_POSITIONS = [
        (640, 565),  # 0 底部（人类玩家）
        (300, 530),  # 1 左下
        (160, 360),  # 2 左侧
        (300, 190),  # 3 左上
        (640, 130),  # 4 顶部
        (980, 190),  # 5 右上
        (1120, 360), # 6 右侧
        (980, 530),  # 7 右下
    ]

    def draw_table(self):
        """绘制牌桌背景（使用预缩放素材，零缩放）"""
        table = get_table_surface()
        if table:
            # 先铺纯黑底，让贴图透明/半透明区域统一为黑色，避免 alpha 处理不当出现噪点
            self.screen.fill(COLOR_BLACK)
            self.screen.blit(table, (0, 0))
        else:
            # 备用：绘制简单绿色椭圆
            self.screen.fill(COLOR_BG)
            cx, cy = self.w // 2, self.h // 2 - 30
            table_w, table_h = 800, 400
            pygame.draw.ellipse(self.screen, COLOR_TABLE_FELT,
                                pygame.Rect(cx - table_w // 2, cy - table_h // 2, table_w, table_h))

    def get_seat_positions(self, players):
        """根据玩家 seat_index 返回对应座位坐标"""
        return [self.SEAT_POSITIONS[p.seat_index] for p in players]

    def _get_avatar_color(self, name):
        """根据名字生成稳定的头像颜色"""
        hash_val = sum(ord(c) for c in name) % 360
        # 使用 HSL 色调，保证颜色鲜艳且不同名字差异明显
        r, g, b = colorsys.hsv_to_rgb(hash_val / 360.0, 0.75, 0.85)
        return (int(r * 255), int(g * 255), int(b * 255))

    def get_avatar_surface(self, name, size=40):
        """生成角色头像：圆形背景 + 名字首字（带缓存）"""
        if not name:
            return None
        key = (name, size)
        if key in self._avatar_cache:
            return self._avatar_cache[key]

        avatar = pygame.Surface((size, size), pygame.SRCALPHA)
        color = self._get_avatar_color(name)
        center = size // 2
        radius = size // 2 - 1
        pygame.draw.circle(avatar, color, (center, center), radius)
        pygame.draw.circle(avatar, (255, 255, 255, 180), (center, center), radius, 2)

        # 首字（如果是中文，取第一个字；英文取第一个字母）
        first_char = name[0]
        font = get_font(max(14, size // 2), bold=True)
        text = font.render(first_char, True, (255, 255, 255))
        tx = (size - text.get_width()) // 2
        ty = (size - text.get_height()) // 2
        avatar.blit(text, (tx, ty))

        self._avatar_cache[key] = avatar
        return avatar

    def draw_player_popup(self, player, close_callback=None):
        """绘制点击弹出的角色详情面板

        Args:
            player: 玩家对象
            close_callback: 关闭按钮的回调函数
        """
        if not player or player.is_human or not hasattr(player, '_char_stats'):
            return None

        stats = player._char_stats
        cx, cy = self.w // 2, self.h // 2
        panel_w, panel_h = 300, 220
        panel_x = cx - panel_w // 2
        panel_y = cy - panel_h // 2
        title_h = 50

        # 半透明遮罩（复用缓存 surface）
        self._overlay.fill((0, 0, 0, 180))
        self.screen.blit(self._overlay, (0, 0))

        # 面板背景
        pygame.draw.rect(self.screen, COLOR_PANEL_BG, (panel_x, panel_y, panel_w, panel_h), border_radius=12)
        pygame.draw.rect(self.screen, COLOR_GOLD, (panel_x, panel_y, panel_w, panel_h), 2, border_radius=12)

        # 标题栏背景
        title_rect = pygame.Rect(panel_x + 2, panel_y + 2, panel_w - 4, title_h)
        pygame.draw.rect(self.screen, (40, 45, 50), title_rect, border_radius=10)
        # 标题栏下划线
        pygame.draw.line(self.screen, (80, 80, 80), (panel_x + 12, panel_y + title_h), (panel_x + panel_w - 12, panel_y + title_h), 1)

        # 头像（中尺寸）
        avatar_size = 40
        avatar = self.get_avatar_surface(player.name, avatar_size)
        if avatar:
            self.screen.blit(avatar, (panel_x + 14, panel_y + 5))

        # 名字
        name_surf = self.font_title.render(player.name, True, COLOR_GOLD)
        self.screen.blit(name_surf, (panel_x + 64, panel_y + 12))

        # 关闭按钮：右上角 X
        close_btn = Button(panel_x + panel_w - 38, panel_y + 8, 30, 30, "X", color=(180, 60, 60), font_size=18)
        if close_callback:
            close_btn.on_click = close_callback
        mouse_pos = pygame.mouse.get_pos()
        close_btn.update(mouse_pos)
        close_btn.draw(self.screen)

        # 统计数据
        lines = [
            ("总局数", f"{stats.get('hands_played', 0)} 手"),
            ("胜场", f"{stats.get('hands_won', 0)} 手"),
            ("胜率", f"{stats.get('hands_won', 0) / max(1, stats.get('hands_played', 1)):.1%}"),
            ("银行余额", f"{stats.get('bank', 0):,} 筹码"),
            ("总盈亏", f"{stats.get('total_profit', 0):,} 筹码"),
            ("本场带入", f"{getattr(player, 'initial_chips', player.chips):,} 筹码"),
            ("当前筹码", f"{player.chips:,} 筹码"),
        ]
        label_color = COLOR_TEXT_DIM
        value_color = COLOR_WHITE
        line_y = panel_y + title_h + 18
        for label, value in lines:
            label_surf = self.font_small.render(label, True, label_color)
            value_surf = self.font_small.render(value, True, value_color)
            self.screen.blit(label_surf, (panel_x + 30, line_y))
            self.screen.blit(value_surf, (panel_x + 130, line_y))
            line_y += 22

        return close_btn

    def get_player_pos(self, player_index):
        """获取指定玩家的座位坐标"""
        positions = self.get_seat_positions(self._last_players if hasattr(self, '_last_players') and self._last_players else [])
        if player_index < len(positions):
            return positions[player_index]
        return (self.w // 2, self.h // 2)

    def draw_player(self, player, pos, is_current, is_dealer, is_small_blind, is_big_blind,
                    show_cards=False, is_human=False, hovered=False, hide_hole_cards=False):
        """绘制玩家信息卡"""
        x, y = pos
        card_w = 160
        card_h = 70

        # 调整位置使信息卡居中
        rect_x = x - card_w // 2
        rect_y = y - card_h // 2

        # 背景面板
        bg_color = COLOR_PANEL_BG
        border_color = COLOR_PANEL_BORDER
        border_width = 2

        if is_current:
            # 采用显眼的霓虹绿，搭配呼吸动态边框线宽
            border_color = (50, 255, 100)
            border_width = 3 + int(1.5 * math.sin(pygame.time.get_ticks() / 120))
        elif player.folded:
            bg_color = (20, 20, 20)
            border_color = (40, 40, 40)

        pygame.draw.rect(self.screen, bg_color, (rect_x, rect_y, card_w, card_h), border_radius=8)
        pygame.draw.rect(self.screen, border_color, (rect_x, rect_y, card_w, card_h), border_width, border_radius=8)

        # 头像：左侧圆形，40x40
        avatar_size = 40
        avatar = self.get_avatar_surface(player.name, avatar_size)
        if avatar:
            self.screen.blit(avatar, (rect_x + 6, rect_y + (card_h - avatar_size) // 2))

        # 悬停时给 AI 玩家卡片加高亮边框，提示可点击查看详情
        if hovered and not is_human and hasattr(player, '_char_stats'):
            pygame.draw.rect(self.screen, COLOR_GOLD, (rect_x, rect_y, card_w, card_h), 2, border_radius=8)
            hint = self.font_tiny.render("点击查看详情", True, COLOR_GOLD)
            self.screen.blit(hint, (rect_x + (card_w - hint.get_width()) // 2, rect_y - 14))

        # 绘制“思考中...”或“到你了”悬浮呼吸胶囊标签
        if is_current and not player.folded:
            badge_w, badge_h = 74, 20
            badge_x = rect_x + (card_w - badge_w) // 2
            badge_y = rect_y - 12
            pygame.draw.rect(self.screen, (0, 140, 50), (badge_x, badge_y, badge_w, badge_h), border_radius=6)
            pygame.draw.rect(self.screen, (100, 255, 150), (badge_x, badge_y, badge_w, badge_h), 1, border_radius=6)
            
            badge_text = "到你了" if is_human else "思考中"
            badge_surf = self.font_tiny.render(badge_text, True, COLOR_WHITE)
            self.screen.blit(badge_surf, (badge_x + (badge_w - badge_surf.get_width()) // 2, badge_y + (badge_h - badge_surf.get_height()) // 2))

        # 文本区偏移：给头像留出 50 像素
        text_x = rect_x + 50

        # 玩家名
        name_color = COLOR_TEXT_DIM if player.folded else COLOR_WHITE
        name_surf = self.font_normal.render(player.name, True, name_color)
        self.screen.blit(name_surf, (text_x, rect_y + 4))

        # 筹码
        chip_color = COLOR_GOLD if not player.folded else COLOR_TEXT_DIM
        # 绘制筹码小图标 (大小 radius=7)
        player_chip_icon = get_chip_surface(player.chips, 7)
        self.screen.blit(player_chip_icon, (text_x, rect_y + 28))

        chip_surf = self.font_small.render(f"筹码: {player.chips}", True, chip_color)
        self.screen.blit(chip_surf, (text_x + 18, rect_y + 26))

        # 状态标记
        status_text = ""
        if player.folded:
            status_text = "弃牌"
        elif player.all_in:
            status_text = "全押"
        if status_text:
            st_surf = self.font_small.render(status_text, True, COLOR_RED if player.folded else COLOR_GOLD)
            self.screen.blit(st_surf, (rect_x + card_w - st_surf.get_width() - 8, rect_y + 4))

        # 最近动作
        if player.last_action and not player.folded:
            at = player.last_action.action_type
            action_name = ACTION_NAMES.get(at, "")
            amount = player.last_action.amount
            if amount > 0:
                action_text = f"{action_name} {amount}"
            else:
                action_text = action_name
            act_surf = self.font_tiny.render(action_text, True, COLOR_GREEN)
            self.screen.blit(act_surf, (rect_x + card_w - act_surf.get_width() - 8, rect_y + 26))

        # 庄家/盲注按钮
        if is_dealer:
            btn = get_dealer_button(14)
            self.screen.blit(btn, (rect_x + card_w - 20, rect_y + card_h - 20))
        if is_small_blind:
            sb_surf = self.font_tiny.render("小盲", True, COLOR_WHITE)
            self.screen.blit(sb_surf, (text_x, rect_y + card_h - 18))
        if is_big_blind:
            bb_surf = self.font_tiny.render("大盲", True, COLOR_WHITE)
            self.screen.blit(bb_surf, (text_x, rect_y + card_h - 18))

        # 手牌
        if player.hole_cards and not hide_hole_cards:
            card_w_small, card_h_small = 50, 70
            card_gap = 4
            cards_total_w = card_w_small * 2 + card_gap
            cards_x = x - cards_total_w // 2
            cards_y = rect_y - card_h_small - 5

            if is_human or show_cards:
                for i, card in enumerate(player.hole_cards):
                    card_surf = get_card_surface(card, card_w_small, card_h_small, face_up=True)
                    self.screen.blit(card_surf, (cards_x + i * (card_w_small + card_gap), cards_y))
            else:
                for i in range(2):
                    back_surf = get_card_back(card_w_small, card_h_small)
                    self.screen.blit(back_surf, (cards_x + i * (card_w_small + card_gap), cards_y))

        # 当前下注：把筹码堆放在玩家与桌面中央之间，避免信息卡拥挤
        if not player.folded and player.current_bet > 0:
            self._draw_player_bet_stack(player, x, y, is_human)

    def _draw_player_bet_stack(self, player, player_x, player_y, is_human=False):
        """把下注筹码放在玩家信息卡外缘；人类玩家放在底牌左侧"""
        if is_human:
            # 人类玩家：把筹码放在底牌左侧（红框区域），与底牌中心对齐
            card_w_small, card_h_small = 50, 70
            card_gap = 4
            cards_total_w = card_w_small * 2 + card_gap
            cards_x = player_x - cards_total_w // 2
            cards_y = player_y - 35 - card_h_small - 5  # 信息卡半高 35
            bet_x = cards_x - 22
            bet_y = cards_y + card_h_small // 2
            ndx, ndy = 0, -1  # 文字朝上
        else:
            cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30
            dx, dy = cx - player_x, cy - player_y
            dist = math.hypot(dx, dy)
            if dist == 0:
                return
            ndx, ndy = dx / dist, dy / dist

            # 玩家信息卡半宽高：让筹码从边框外一点的位置发出
            card_half_w = 80
            card_half_h = 35
            margin = 12
            # 沿方向射线离开信息卡矩形所需的距离
            t_x = card_half_w / abs(ndx) if ndx != 0 else float('inf')
            t_y = card_half_h / abs(ndy) if ndy != 0 else float('inf')
            t = min(t_x, t_y) + margin

            bet_x = int(player_x + ndx * t)
            bet_y = int(player_y + ndy * t)

        chip = get_chip_surface(player.current_bet, 10)
        chip_w, chip_h = chip.get_width(), chip.get_height()
        self.screen.blit(chip, (bet_x - chip_w // 2, bet_y - chip_h // 2))

        # 金额标签
        bet_surf = self.font_small.render(str(player.current_bet), True, COLOR_GOLD)
        if is_human:
            text_x = bet_x - bet_surf.get_width() // 2
            text_y = bet_y - chip_h // 2 - bet_surf.get_height() - 2
        else:
            text_x = bet_x + int(ndx * (chip_w // 2 + 4)) - bet_surf.get_width() // 2
            text_y = bet_y + int(ndy * (chip_h // 2 + 4)) - bet_surf.get_height() // 2
        self.screen.blit(bet_surf, (text_x, text_y))

    def draw_community_cards(self, cards):
        """绘制公共牌"""
        cx = self.w // 2
        cy = self.h // 2 - 30

        card_w, card_h = 60, 85
        gap = 8
        total_w = 5 * card_w + 4 * gap
        start_x = cx - total_w // 2

        # 预留5个位置
        for i in range(5):
            x = start_x + i * (card_w + gap)
            y = cy - card_h // 2

            # 空位框
            if i >= len(cards):
                pygame.draw.rect(self.screen, (20, 70, 45), (x, y, card_w, card_h), 2, border_radius=6)
            else:
                card_surf = get_card_surface(cards[i], card_w, card_h, face_up=True)
                self.screen.blit(card_surf, (x, y))

    def draw_pot(self, pot_amount):
        """绘制底池（公共牌下方，无背景边框）"""
        cx = self.w // 2
        cy = self.h // 2 + 50

        # 筹码图标
        chip = get_pot_chip_surface(pot_amount, 14)

        # 底池金额
        pot_text = f"底池 {pot_amount:,}"
        pot_surf = self.font_large.render(pot_text, True, COLOR_GOLD)

        # 总宽度
        total_w = chip.get_width() + 10 + pot_surf.get_width()
        start_x = cx - total_w // 2
        chip_y = cy - chip.get_height() // 2
        text_y = cy - pot_surf.get_height() // 2

        # 筹码 + 文字
        self.screen.blit(chip, (start_x, chip_y))
        self.screen.blit(pot_surf, (start_x + chip.get_width() + 10, text_y))

    def draw_phase_info(self, phase, hand_number):
        """绘制阶段信息 — 胶囊式徽章，带阶段配色"""
        phase_colors = {
            PREFLOP: (80, 140, 200),
            FLOP: (80, 180, 100),
            TURN: (200, 160, 60),
            RIVER: (200, 100, 60),
            SHOWDOWN: (200, 60, 60),
        }
        color = phase_colors.get(phase, (120, 120, 140))
        text = f"#{hand_number}  {PHASE_NAMES.get(phase, phase)}"
        surf = self.font_normal.render(text, True, COLOR_WHITE)

        # 胶囊背景
        pad_x, pad_y = 14, 6
        bg_w = surf.get_width() + pad_x * 2
        bg_h = surf.get_height() + pad_y * 2
        bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (*color, 180), (0, 0, bg_w, bg_h), border_radius=bg_h // 2)
        pygame.draw.rect(bg, (*color, 255), (0, 0, bg_w, bg_h), 1, border_radius=bg_h // 2)
        self.screen.blit(bg, (10, 8))
        self.screen.blit(surf, (10 + pad_x, 8 + pad_y))

    def draw_betting_info(self, current_bet, min_raise):
        """绘制下注信息 — 带背景条，醒目显示"""
        if current_bet > 0:
            text = f"当前下注 {current_bet:,}  ·  最小加注 {min_raise:,}"
            surf = self.font_small.render(text, True, (255, 220, 100))
            bg_w = surf.get_width() + 20
            bg_h = surf.get_height() + 8
            bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
            pygame.draw.rect(bg, (0, 0, 0, 100), (0, 0, bg_w, bg_h), border_radius=6)
            self.screen.blit(bg, (10, 38))
            self.screen.blit(surf, (20, 42))

    def draw_action_panel(self, game, human_player):
        """绘制操作面板"""
        panel = Panel(10, SCREEN_HEIGHT - 100, SCREEN_WIDTH - 20, 90)
        panel.draw(self.screen)

        # 离开按钮始终可见
        mouse_pos = pygame.mouse.get_pos()
        self.leave_button.update(mouse_pos)
        self.leave_button.draw(self.screen)

        if not human_player or human_player.folded or human_player.all_in:
            label = self.font_normal.render("等待中...", True, COLOR_TEXT_DIM)
            self.screen.blit(label, (110, SCREEN_HEIGHT - 75))
            return

        human_index = game.players.index(human_player)
        legal = game.get_legal_actions(human_index)
        legal_types = set(legal)

        to_call = game.current_bet - human_player.current_bet

        # 更新按钮状态
        btn_map = {
            ActionType.FOLD: "fold",
            ActionType.CHECK: "check",
            ActionType.CALL: "call",
            ActionType.RAISE: "raise",
            ActionType.ALL_IN: "all_in",
        }

        for at, key in btn_map.items():
            btn = self.action_buttons[key]
            btn.enabled = at in legal_types

        # 特殊处理“下注 (BET)”与“加注 (RAISE)”复用同一个按键的德州核心逻辑
        raise_btn = self.action_buttons["raise"]
        is_bet = ActionType.BET in legal_types
        is_raise = ActionType.RAISE in legal_types
        
        raise_btn.enabled = is_bet or is_raise
        if is_bet:
            raise_btn.text = "下注"
        else:
            raise_btn.text = "加注"

        # 跟注按钮显示金额
        call_btn = self.action_buttons["call"]
        if ActionType.CALL in legal_types and to_call > 0:
            call_btn.text = f"跟注 {to_call}"
        elif ActionType.CALL in legal_types:
            call_btn.text = "跟注"
        else:
            call_btn.text = "跟注"

        # 加注滑块
        if is_raise or is_bet:
            min_raise_to = game.get_min_raise_to(human_index)
            max_raise_to = game.get_max_raise_to(human_index)
            if max_raise_to > min_raise_to:
                self.raise_slider.min_val = min_raise_to
                self.raise_slider.max_val = max_raise_to
                
                # 核心修复：仅在滑块初次启用、或者当前下注下限发生变动时，才重载初始值。
                # 严禁在 60FPS 渲染循环中每帧强制重置，否则会导致无法滑动进度条！
                if not getattr(self, "_slider_initialized", False) or getattr(self, "_last_min_raise_to", None) != min_raise_to:
                    self.raise_slider.value = min_raise_to
                    self._last_min_raise_to = min_raise_to
                    self._slider_initialized = True
                
                self.raise_slider.enabled = True
            else:
                self.raise_slider.enabled = False
                self._slider_initialized = False
                self.raise_input.active = False
        else:
            self.raise_slider.enabled = False
            self._slider_initialized = False
            self._last_min_raise_to = None
            self.raise_input.active = False

        # 绘制按钮
        for btn in self.action_buttons.values():
            btn.draw(self.screen)

        # 绘制滑块和输入框
        if self.raise_slider.enabled:
            # 同步：当输入框未激活时，用滑块值更新输入框文本
            if not self.raise_input.active:
                self.raise_input.text = str(self.raise_slider.value)
            else:
                # 当输入框激活且有有效数字时，更新滑块值
                val = self.raise_input.int_value
                if val is not None:
                    clamped = max(self.raise_slider.min_val, min(self.raise_slider.max_val, val))
                    self.raise_slider.value = clamped

            self.raise_slider.draw(self.screen)
            self.raise_input.draw(self.screen)

            label_text = "下注到:" if is_bet else "加注到:"
            label = self.font_small.render(label_text, True, COLOR_WHITE)
            self.screen.blit(label, (self.raise_slider.rect.x - 55, self.raise_slider.rect.centery - 8))

    def draw_showdown_results(self, results, players, community_cards=None, hand_number=None, timer=0.0):
        """绘制摊牌结果 - 带入场动画和赢家高亮

        Args:
            timer: 摊牌场景已持续时间（秒），用于控制动画阶段
        """
        cx = self.w // 2
        cy = self.h // 2

        # === 动画阶段 ===
        # Phase 0: 0-0.4s 悬念（仅遮罩 + 提示）
        # Phase 1: 0.4-0.8s 面板滑入
        # Phase 2: 0.8s+ 完整显示 + 赢家脉冲
        SUSPENSE_DUR = 0.4
        SLIDE_DUR = 0.4

        if timer < SUSPENSE_DUR:
            # 悬念阶段：渐暗遮罩 + "摊牌中..." 文字
            alpha = int(160 * (timer / SUSPENSE_DUR))
            self._overlay.fill((0, 0, 0, alpha))
            self.screen.blit(self._overlay, (0, 0))
            pulse = 0.5 + 0.5 * math.sin(timer * 8)
            text_color = (int(255 * pulse), int(215 * pulse), 0)
            text = self.font_title.render("摊牌中...", True, text_color)
            self.screen.blit(text, (cx - text.get_width() // 2, cy - text.get_height() // 2))
            return

        # 滑入进度
        slide_t = min(1.0, (timer - SUSPENSE_DUR) / SLIDE_DUR)
        slide_eased = 1 - (1 - slide_t) ** 3  # ease-out

        # 半透明遮罩
        self._overlay.fill((0, 0, 0, 160))
        self.screen.blit(self._overlay, (0, 0))

        # 结果面板 - 加大以容纳牌面
        panel_w, panel_h = 760, 520
        panel_x = cx - panel_w // 2
        panel_y_offset = int((1 - slide_eased) * 100)  # 从下方滑入
        panel_y = cy - panel_h // 2 + panel_y_offset

        # 面板透明度（滑入时渐显）
        panel_alpha = int(255 * slide_eased)

        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (*COLOR_PANEL_BG, panel_alpha), (0, 0, panel_w, panel_h), border_radius=12)
        pygame.draw.rect(panel_surf, (*COLOR_GOLD, panel_alpha), (0, 0, panel_w, panel_h), 3, border_radius=12)
        self.screen.blit(panel_surf, (panel_x, panel_y))

        # 滑入未完成时只画面板框架
        if slide_t < 1.0:
            return

        # 左上角对局编号
        if hand_number is not None:
            hand_label = self.font_small.render(f"#{hand_number}", True, (180, 180, 180))
            self.screen.blit(hand_label, (panel_x + 12, panel_y + 10))

        # 标题
        title = self.font_title.render("摊牌结果", True, COLOR_GOLD)
        self.screen.blit(title, (cx - title.get_width() // 2, panel_y + 10))

        card_w, card_h = 44, 62

        if results.get('fold_win'):
            winner = results['winners'][0]
            text = f"{winner.name} 获胜（其他玩家弃牌）"
            surf = self.font_large.render(text, True, COLOR_GOLD)
            self.screen.blit(surf, (cx - surf.get_width() // 2, panel_y + 55))
            net = results.get('pot_won', 0) - winner.total_bet
            pot_text = f"净赢 +{net:,} 筹码"
            pot_surf = self.font_normal.render(pot_text, True, COLOR_GOLD)
            self.screen.blit(pot_surf, (cx - pot_surf.get_width() // 2, panel_y + 90))
        else:
            payouts = results.get('payouts', {})
            evaluations = results.get('evaluations', {})
            max_payout = max(payouts.values()) if payouts else 0

            # 公共牌区域（顶部）
            comm_label = self.font_small.render("公共牌", True, COLOR_TEXT_DIM)
            self.screen.blit(comm_label, (cx - comm_label.get_width() // 2, panel_y + 48))

            if community_cards:
                comm_count = len(community_cards)
                comm_total_w = comm_count * card_w + (comm_count - 1) * 6
                comm_start_x = cx - comm_total_w // 2
                comm_y = panel_y + 68
                for i, card in enumerate(community_cards):
                    cs = get_card_surface(card, card_w, card_h, face_up=True)
                    # 公共牌 - 蓝色粗边框
                    card_x = comm_start_x + i * (card_w + 6)
                    bg = pygame.Surface((card_w + 6, card_h + 6), pygame.SRCALPHA)
                    bg.fill((30, 100, 200, 220))
                    self.screen.blit(bg, (card_x - 3, comm_y - 3))
                    self.screen.blit(cs, (card_x, comm_y))
                    pygame.draw.rect(self.screen, (80, 160, 255), (card_x - 3, comm_y - 3, card_w + 6, card_h + 6), 2, border_radius=4)

            # 玩家结果区域
            non_folded = [(p, p.seat_index) for p in players if not p.folded and p.seat_index in evaluations]
            y = panel_y + 145

            for player, seat_idx in non_folded:
                ev = evaluations.get(seat_idx)
                ev_name = ev.name if ev else "未知"
                won = payouts.get(seat_idx, 0)
                is_main_winner = won > 0 and won == max_payout
                is_side_winner = won > 0 and won < max_payout

                # 玩家行背景
                row_w = panel_w - 40
                row_h = 80
                row_x = panel_x + 20
                if is_main_winner:
                    row_bg = pygame.Surface((row_w, row_h), pygame.SRCALPHA)
                    row_bg.fill((80, 60, 10, 120))
                    self.screen.blit(row_bg, (row_x, y))
                    pygame.draw.rect(self.screen, COLOR_GOLD, (row_x, y, row_w, row_h), 2, border_radius=6)
                    # 脉冲光效（Phase 2 后）
                    glow_pulse = 0.5 + 0.5 * math.sin(timer * 4)
                    glow_alpha = int(60 * glow_pulse)
                    glow_surf = pygame.Surface((row_w + 8, row_h + 8), pygame.SRCALPHA)
                    pygame.draw.rect(glow_surf, (255, 215, 0, glow_alpha), (0, 0, row_w + 8, row_h + 8), 3, border_radius=8)
                    self.screen.blit(glow_surf, (row_x - 4, y - 4))
                elif is_side_winner:
                    row_bg = pygame.Surface((row_w, row_h), pygame.SRCALPHA)
                    row_bg.fill((60, 40, 10, 80))
                    self.screen.blit(row_bg, (row_x, y))
                    pygame.draw.rect(self.screen, (255, 165, 0), (row_x, y, row_w, row_h), 1, border_radius=6)

                # 底牌（左侧）
                hole_label = self.font_tiny.render("底牌", True, COLOR_TEXT_DIM)
                self.screen.blit(hole_label, (row_x + 8, y + 4))

                hole_x = row_x + 8
                hole_y = y + 18
                if player.hole_cards:
                    for j, card in enumerate(player.hole_cards):
                        cs = get_card_surface(card, card_w, card_h, face_up=True)
                        # 底牌 - 绿色粗边框区分
                        card_x = hole_x + j * (card_w + 6)
                        bg = pygame.Surface((card_w + 6, card_h + 6), pygame.SRCALPHA)
                        bg.fill((20, 120, 40, 220))
                        self.screen.blit(bg, (card_x - 3, hole_y - 3))
                        self.screen.blit(cs, (card_x, hole_y))
                        pygame.draw.rect(self.screen, (80, 220, 120), (card_x - 3, hole_y - 3, card_w + 6, card_h + 6), 2, border_radius=4)

                # 右侧信息：名字、牌型、赢取
                info_x = row_x + 2 * (card_w + 6) + 20
                if is_main_winner:
                    name_text = f"★ {player.name}"
                    name_color = COLOR_GOLD
                    name_font = self.font_large
                elif is_side_winner:
                    name_text = f"{player.name} (边池)"
                    name_color = (255, 165, 0)
                    name_font = self.font_normal
                else:
                    name_text = player.name
                    name_color = COLOR_TEXT_DIM
                    name_font = self.font_normal

                name_surf = name_font.render(name_text, True, name_color)
                self.screen.blit(name_surf, (info_x, y + 8))

                hand_surf = self.font_normal.render(f"牌型: {ev_name}", True, COLOR_WHITE if won > 0 else COLOR_TEXT_DIM)
                self.screen.blit(hand_surf, (info_x, y + 32))

                # 净利润 = 派彩 - 自己的总下注
                net = won - player.total_bet
                if net >= 0:
                    win_text = f"净赢 +{net:,} 筹码"
                    win_color = COLOR_GOLD if is_main_winner else (255, 165, 0)
                else:
                    win_text = f"净输 -{abs(net):,} 筹码" if player.total_bet > 0 else "未下注"
                    win_color = COLOR_TEXT_DIM
                win_surf = self.font_normal.render(win_text, True, win_color)
                self.screen.blit(win_surf, (info_x, y + 54))

                y += row_h + 6

            # 平分底池说明
            if len(payouts) > 1:
                split_text = "平分底池：多名玩家手牌相同，底池均分"
                split_surf = self.font_small.render(split_text, True, (200, 200, 200))
                self.screen.blit(split_surf, (cx - split_surf.get_width() // 2, y + 2))

        # 提示
        hint = self.font_normal.render("按 空格键 或 点击 继续下一手", True, COLOR_TEXT_DIM)
        self.screen.blit(hint, (cx - hint.get_width() // 2, panel_y + panel_h - 35))

    def draw_waiting_screen(self, message=""):
        """绘制等待画面"""
        self.screen.fill(COLOR_BG)
        if message:
            surf = self.font_title.render(message, True, COLOR_WHITE)
            self.screen.blit(surf, (self.w // 2 - surf.get_width() // 2, self.h // 2))

    def draw_menu(self, menu_items, title="德州扑克"):
        """绘制菜单"""
        self.screen.fill(COLOR_BG)

        title_surf = self.font_title.render(title, True, COLOR_GOLD)
        self.screen.blit(title_surf, (self.w // 2 - title_surf.get_width() // 2, 80))

        for item in menu_items:
            item.draw(self.screen)

    def draw_bank_leaderboard(self, human_name, human_bank, ai_characters, max_entries=10):
        """绘制银行存款排行榜（主菜单用）

        Args:
            human_name: 人类玩家名
            human_bank: 人类玩家银行余额
            ai_characters: AI角色列表 (AICharacter)
            max_entries: 最多显示条目数
        """
        # 合并人类和AI玩家，按银行余额排序
        entries = [("你", human_bank, True)]
        for c in ai_characters:
            entries.append((c.name, c.bank, False))
        entries.sort(key=lambda x: x[1], reverse=True)
        entries = entries[:max_entries]

        panel_w = 240
        line_h = 24
        header_h = 32
        panel_h = header_h + len(entries) * line_h + 12

        panel_x = 20
        panel_y = 130

        # 半透明背景
        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill((30, 35, 40, 200))
        self.screen.blit(bg, (panel_x, panel_y))
        pygame.draw.rect(self.screen, COLOR_PANEL_BORDER, (panel_x, panel_y, panel_w, panel_h), 1, border_radius=8)

        # 标题
        title_surf = self.font_small.render("银行存款排行", True, COLOR_GOLD)
        self.screen.blit(title_surf, (panel_x + (panel_w - title_surf.get_width()) // 2, panel_y + 8))

        # 排名列表
        medals = ["1", "2", "3"]
        for i, (name, bank, is_human) in enumerate(entries):
            y = panel_y + header_h + i * line_h

            # 排名
            rank_color = COLOR_GOLD if i == 0 else (COLOR_TEXT_DIM if i >= 3 else COLOR_WHITE)
            rank_surf = self.font_tiny.render(medals[i] if i < 3 else str(i + 1), True, rank_color)
            self.screen.blit(rank_surf, (panel_x + 10, y + 5))

            # 名字（截断过长名字）
            display_name = name
            if len(display_name) > 7:
                display_name = display_name[:6] + ".."
            name_color = (100, 255, 150) if is_human else COLOR_WHITE
            if bank <= 0:
                name_color = COLOR_TEXT_DIM
            name_surf = self.font_tiny.render(display_name, True, name_color)
            self.screen.blit(name_surf, (panel_x + 28, y + 5))

            # 银行余额（右对齐）
            bank_text = f"{bank:,}"
            bank_color = COLOR_GOLD if bank > 0 else COLOR_TEXT_DIM
            bank_surf = self.font_tiny.render(bank_text, True, bank_color)
            self.screen.blit(bank_surf, (panel_x + panel_w - bank_surf.get_width() - 10, y + 5))

    def draw_ai_thinking(self, player_name, dialogue=None):
        """绘制AI思考提示，可附带对话气泡"""
        text = f"{player_name} 正在思考..."
        surf = self.font_normal.render(text, True, COLOR_TEXT_DIM)
        self.screen.blit(surf, (self.w // 2 - surf.get_width() // 2, SCREEN_HEIGHT - 120))

        # 绘制对话气泡
        if dialogue:
            self.draw_speech_bubble(dialogue, player_name)

    def _wrap_text(self, text, font, max_width):
        """将文本按最大宽度折成多行（中文按字，英文按词）"""
        lines = []
        current_line = ""
        for char in text:
            test_line = current_line + char
            if font.render(test_line, True, (0, 0, 0)).get_width() <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
        return lines if lines else [text]

    def draw_speech_bubble(self, text, player_name=None, pos=None, color=(255, 255, 240)):
        """绘制对话气泡（支持多行自动换行）

        Args:
            text: 对话内容
            player_name: 可选的玩家名（用于定位）
            pos: 可选的固定位置 (x, y)，如果提供则优先使用
            color: 气泡背景色
        """
        if not text:
            return

        # 气泡最大宽度
        max_bubble_w = 360
        padding = 12
        line_h = self.font_small.get_height()

        # 折行
        max_text_w = max_bubble_w - padding * 2
        lines = self._wrap_text(text, self.font_small, max_text_w)

        # 计算实际气泡尺寸
        text_w = max(self.font_small.render(line, True, (40, 40, 40)).get_width() for line in lines)
        text_h = len(lines) * line_h
        bubble_w = text_w + padding * 2
        bubble_h = text_h + padding * 2

        # 确定位置
        if pos:
            bx, by = pos
        elif player_name and hasattr(self, '_last_players') and self._last_players:
            positions = self.get_seat_positions(self._last_players)
            for i, p in enumerate(self._last_players):
                if p.name == player_name and i < len(positions):
                    px, py = positions[i]
                    bx = px - bubble_w // 2
                    by = py - bubble_h - 40  # 气泡从玩家上方 40px 处向上生长
                    break
            else:
                bx = self.w // 2 - bubble_w // 2
                by = SCREEN_HEIGHT - 160 - bubble_h
        else:
            bx = self.w // 2 - bubble_w // 2
            by = SCREEN_HEIGHT - 160 - bubble_h

        # 确保不超出屏幕
        bx = max(5, min(bx, self.w - bubble_w - 5))
        by = max(5, min(by, self.h - bubble_h - 5))

        # 绘制气泡背景
        bubble_rect = pygame.Rect(bx, by, bubble_w, bubble_h)
        pygame.draw.rect(self.screen, color, bubble_rect, border_radius=10)
        pygame.draw.rect(self.screen, (180, 180, 160), bubble_rect, 2, border_radius=10)

        # 绘制小三角指向玩家
        if player_name and hasattr(self, '_last_players') and self._last_players:
            positions = self.get_seat_positions(self._last_players)
            for i, p in enumerate(self._last_players):
                if p.name == player_name and i < len(positions):
                    px, py = positions[i]
                    triangle_base_y = by + bubble_h
                    triangle_cx = max(bx + 15, min(px, bx + bubble_w - 15))
                    pygame.draw.polygon(self.screen, color, [
                        (triangle_cx - 8, triangle_base_y - 2),
                        (triangle_cx + 8, triangle_base_y - 2),
                        (triangle_cx, triangle_base_y + 10),
                    ])
                    pygame.draw.polygon(self.screen, (180, 180, 160), [
                        (triangle_cx - 8, triangle_base_y - 2),
                        (triangle_cx + 8, triangle_base_y - 2),
                        (triangle_cx, triangle_base_y + 10),
                    ], 1)
                    break

        # 绘制多行文本
        y = by + padding
        for line in lines:
            line_surf = self.font_small.render(line, True, (40, 40, 40))
            self.screen.blit(line_surf, (bx + padding, y))
            y += line_h

    def draw_leaderboard(self, players):
        """绘制筹码排行榜面板"""
        # 按筹码排序（降序）
        sorted_players = sorted(players, key=lambda p: p.chips, reverse=True)

        panel_w = 180
        line_h = 22
        header_h = 30
        panel_h = header_h + len(sorted_players) * line_h + 10

        panel_x = SCREEN_WIDTH - panel_w - 10
        panel_y = 60

        # 半透明背景
        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill((30, 35, 40, 200))
        self.screen.blit(bg, (panel_x, panel_y))
        pygame.draw.rect(self.screen, COLOR_PANEL_BORDER, (panel_x, panel_y, panel_w, panel_h), 1, border_radius=8)

        # 标题
        title_surf = self.font_small.render("筹码排行", True, COLOR_GOLD)
        self.screen.blit(title_surf, (panel_x + (panel_w - title_surf.get_width()) // 2, panel_y + 6))

        # 排名列表
        medals = ["1", "2", "3"]
        for i, p in enumerate(sorted_players):
            y = panel_y + header_h + i * line_h

            # 排名
            rank_color = COLOR_GOLD if i == 0 else (COLOR_TEXT_DIM if i >= 3 else COLOR_WHITE)
            rank_surf = self.font_tiny.render(medals[i] if i < 3 else str(i + 1), True, rank_color)
            self.screen.blit(rank_surf, (panel_x + 8, y + 4))

            # 名字（截断过长名字）
            name = p.name
            if len(name) > 6:
                name = name[:5] + ".."
            name_color = (100, 255, 150) if p.is_human else COLOR_WHITE
            if p.folded or p.chips == 0:
                name_color = COLOR_TEXT_DIM
            name_surf = self.font_tiny.render(name, True, name_color)
            self.screen.blit(name_surf, (panel_x + 24, y + 4))

            # 筹码金额（右对齐）
            chip_text = f"{p.chips:,}"
            chip_surf = self.font_tiny.render(chip_text, True, COLOR_GOLD if p.chips > 0 else COLOR_TEXT_DIM)
            self.screen.blit(chip_surf, (panel_x + panel_w - chip_surf.get_width() - 8, y + 4))

    def draw_history_panel(self, hand_history, lb_panel_x=SCREEN_WIDTH - 190, lb_panel_y=60, lb_panel_h=0):
        """在对局右侧绘制最近赢牌历史

        Args:
            hand_history: 历史记录列表
            lb_panel_x: 排行榜面板x坐标
            lb_panel_y: 排行榜面板y坐标
            lb_panel_h: 排行榜面板高度
        """
        if not hand_history:
            return

        panel_w = 180
        panel_x = lb_panel_x
        # 排行榜下方
        panel_y = lb_panel_y + lb_panel_h + 8

        # 最多显示最近8条
        display = list(reversed(hand_history))[:8]
        line_h = 32
        header_h = 28
        panel_h = header_h + len(display) * line_h + 8

        # 不超出屏幕
        max_h = SCREEN_HEIGHT - panel_y - 110
        if panel_h > max_h:
            panel_h = max_h
            visible_rows = (panel_h - header_h - 8) // line_h
            display = display[:visible_rows]

        if not display:
            return

        # 半透明背景
        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill((30, 35, 40, 200))
        self.screen.blit(bg, (panel_x, panel_y))
        pygame.draw.rect(self.screen, COLOR_PANEL_BORDER, (panel_x, panel_y, panel_w, panel_h), 1, border_radius=8)

        # 标题
        title_surf = self.font_small.render("近期赢牌", True, COLOR_GOLD)
        self.screen.blit(title_surf, (panel_x + (panel_w - title_surf.get_width()) // 2, panel_y + 6))

        for i, entry in enumerate(display):
            y = panel_y + header_h + i * line_h

            # 分隔线
            if i > 0:
                pygame.draw.line(self.screen, (50, 50, 55), (panel_x + 6, y), (panel_x + panel_w - 6, y), 1)

            winners = entry.get("winners", [])
            if not winners:
                continue

            # 时间 + 手数
            time_str = entry.get("time", "")
            hand_str = f"#{entry.get('hand_num', '')}"
            time_surf = self.font_tiny.render(f"{time_str} {hand_str}", True, (120, 120, 120))
            self.screen.blit(time_surf, (panel_x + 6, y + 2))

            # 获胜者名字
            w = winners[0]
            name = w["name"]
            if len(name) > 6:
                name = name[:5] + ".."
            name_color = (100, 255, 150) if w.get("is_human") else COLOR_WHITE
            name_surf = self.font_tiny.render(name, True, name_color)
            self.screen.blit(name_surf, (panel_x + 6, y + 14))

            # 牌型
            hand_type = w.get("hand_type", "")
            if len(hand_type) > 6:
                hand_type = hand_type[:5] + ".."
            type_surf = self.font_tiny.render(hand_type, True, (200, 200, 200))
            self.screen.blit(type_surf, (panel_x + 70, y + 14))

            # 净赢金额
            amount = w.get("amount", 0)
            if amount >= 0:
                amt_text = f"+{amount:,}"
                amt_color = COLOR_GOLD if w.get("is_human") else (200, 200, 200)
            else:
                amt_text = f"{amount:,}"
                amt_color = (255, 80, 80)
            amt_surf = self.font_tiny.render(amt_text, True, amt_color)
            self.screen.blit(amt_surf, (panel_x + panel_w - amt_surf.get_width() - 6, y + 14))
