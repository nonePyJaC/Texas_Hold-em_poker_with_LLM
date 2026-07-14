"""手牌历史回放渲染器

逐步重现一手牌的完整过程：发底牌 → 翻牌前下注 → 翻牌 → 转牌 → 河牌 → 摊牌
"""
import pygame
from config import SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_BG, COLOR_GOLD, COLOR_TEXT_DIM
from engine.deck import Card
from ui.assets import get_card_surface


PHASE_NAMES_CN = {
    "preflop": "翻牌前",
    "flop": "翻牌",
    "turn": "转牌",
    "river": "河牌",
    "showdown": "摊牌",
}

ACTION_NAMES_CN = {
    "fold": "弃牌",
    "check": "过牌",
    "call": "跟注",
    "bet": "下注",
    "raise": "加注",
    "all_in": "全押",
}

ACTION_COLORS = {
    "fold": (180, 60, 60),
    "check": (100, 100, 100),
    "call": (60, 160, 80),
    "bet": (230, 180, 50),
    "raise": (230, 130, 50),
    "all_in": (220, 50, 50),
}


def fix_blind_phases(actions):
    """修复前两条盲注动作被误标为后期阶段的问题（历史数据兼容）"""
    if not actions:
        return actions
    fixed = list(actions)
    for i in range(min(2, len(fixed))):
        act = fixed[i]
        if act.get("phase") in ("river", "flop", "turn"):
            fixed[i] = {**act, "phase": "preflop"}
    return fixed


def normalize_action_order(actions):
    """防御性校正：按阶段分组并重新拼接为时间顺序"""
    if not actions or len(actions) < 2:
        return actions
    phase_order = {"preflop": 0, "flop": 1, "turn": 2, "river": 3, "showdown": 4}
    groups = {}
    for act in actions:
        ph = act.get("phase", "preflop")
        groups.setdefault(ph, []).append(act)
    result = []
    for ph in sorted(groups.keys(), key=lambda p: phase_order.get(p, 99)):
        result.extend(groups[ph])
    return result


class HandReplayRenderer:
    """手牌回放渲染器"""

    def __init__(self, app):
        self.app = app

    def render(self):
        """渲染回放场景"""
        app = self.app
        screen = app.screen
        screen.fill(COLOR_BG)

        replay = app.replay_state
        if not replay or not replay.get("hand_data"):
            hint = app.renderer.font_normal.render("无回放数据", True, COLOR_TEXT_DIM)
            screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 200))
            return

        hand_data = replay["hand_data"]
        step = replay["step"]
        paused = replay.get("paused", False)
        speed = replay.get("speed", 1.0)

        cx = SCREEN_WIDTH // 2

        # 标题
        title_text = f"手牌回放 - 第 {hand_data.get('hand_number', '?')} 手"
        title = app.renderer.font_title.render(title_text, True, COLOR_GOLD)
        screen.blit(title, (cx - title.get_width() // 2, 18))

        # 时间戳
        ts = hand_data.get("_log_timestamp", hand_data.get("timestamp", ""))
        ts_surf = app.renderer.font_small.render(ts, True, COLOR_TEXT_DIM)
        screen.blit(ts_surf, (cx - ts_surf.get_width() // 2, 50))

        actions = hand_data.get("actions", [])
        players = hand_data.get("players", [])
        community_str = hand_data.get("community_cards", "")
        showdown = hand_data.get("showdown", [])

        # 计算当前阶段
        current_phase = self._get_phase_at_step(actions, step)

        # 阶段指示器
        self._draw_phase_indicator(screen, current_phase, cx, app)

        # 玩家区域
        player_y = 122
        player_h = 100
        player_w = 190
        num_players = len(players)
        spacing = 12
        total_pw = num_players * player_w + (num_players - 1) * spacing
        p_start_x = cx - total_pw // 2

        for i, p in enumerate(players):
            px = p_start_x + i * (player_w + spacing)
            self._draw_replay_player(screen, p, px, player_y, player_w, player_h, step, actions)

        # 公共牌区域
        comm_y = 232
        if community_str:
            comm_label = app.renderer.font_small.render("公共牌", True, COLOR_TEXT_DIM)
            screen.blit(comm_label, (cx - 250, comm_y + 20))
            # 逐步显示公共牌
            comm_cards = community_str.split()
            revealed_comm = self._get_revealed_community(step, actions, comm_cards)
            total_w = len(revealed_comm) * 70 + (len(revealed_comm) - 1) * 8
            start_x = cx - total_w // 2
            for j, card_str in enumerate(revealed_comm):
                card = self._parse_card_str(card_str)
                if card:
                    card_surf = get_card_surface(card, w=70, h=100, face_up=True)
                    screen.blit(card_surf, (start_x + j * 78, comm_y))
            if not revealed_comm:
                waiting = app.renderer.font_tiny.render("尚未发出", True, (80, 80, 80))
                screen.blit(waiting, (cx - 40, comm_y + 36))
        else:
            no_comm = app.renderer.font_small.render("无公共牌", True, COLOR_TEXT_DIM)
            screen.blit(no_comm, (cx - no_comm.get_width() // 2, comm_y + 36))

        # 下方分为两栏：左侧动作历史，右侧摊牌结果
        left_x = 40
        right_x = SCREEN_WIDTH // 2 + 30
        panel_y = 300

        # 动作历史区域
        self._draw_action_history(screen, actions, step, paused, panel_y, left_x, app)

        # 摊牌结果区域
        if step > len(actions) and showdown:
            self._draw_showdown(screen, showdown, panel_y, right_x, app)

        # 进度条
        bar_y = SCREEN_HEIGHT - 82
        bar_x = 40
        bar_w = SCREEN_WIDTH - 80
        bar_h = 6
        pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_w, bar_h), border_radius=3)
        total_steps = len(actions) + 1
        progress = min(step / max(total_steps, 1), 1.0)
        pygame.draw.rect(screen, COLOR_GOLD, (bar_x, bar_y, int(bar_w * progress), bar_h), border_radius=3)

        # 步骤信息
        step_text = f"步骤 {step}/{total_steps}"
        if step > 0 and step <= len(actions):
            cur_act = actions[step - 1]
            step_text += f"  |  {cur_act.get('player', '')} {ACTION_NAMES_CN.get(cur_act.get('action', ''), '')}"
            if cur_act.get("amount", 0) > 0:
                step_text += f" {cur_act['amount']}"
        elif step > len(actions):
            step_text += "  |  摊牌"
        step_surf = app.renderer.font_small.render(step_text, True, COLOR_TEXT_DIM)
        screen.blit(step_surf, (bar_x, bar_y - 22))

        # 控制按钮
        btn_y = SCREEN_HEIGHT - 52
        mouse_pos = pygame.mouse.get_pos()
        if "replay_play" in app.replay_buttons:
            btn = app.replay_buttons["replay_play"]
            btn.text = "播放" if paused else "暂停"
            btn.update(mouse_pos)
            btn.draw(screen)

        for key in ["replay_prev", "replay_next", "replay_back"]:
            if key in app.replay_buttons:
                btn = app.replay_buttons[key]
                btn.update(mouse_pos)
                btn.draw(screen)

        # 速度指示
        speed_text = f"速度: {speed:.1f}x"
        speed_surf = app.renderer.font_small.render(speed_text, True, COLOR_TEXT_DIM)
        screen.blit(speed_surf, (SCREEN_WIDTH - 110, btn_y + 10))

    def _draw_phase_indicator(self, screen, current_phase, cx, app):
        """绘制顶部阶段指示器"""
        phases = ["preflop", "flop", "turn", "river", "showdown"]
        phase_y = 82
        phase_w = 96
        phase_h = 30
        gap = 8
        total_w = len(phases) * phase_w + (len(phases) - 1) * gap
        start_x = cx - total_w // 2
        for i, ph in enumerate(phases):
            x = start_x + i * (phase_w + gap)
            is_active = ph == current_phase
            bg = (70, 130, 70) if is_active else (45, 45, 48)
            border = (100, 180, 100) if is_active else (70, 70, 70)
            pygame.draw.rect(screen, bg, (x, phase_y, phase_w, phase_h), border_radius=6)
            pygame.draw.rect(screen, border, (x, phase_y, phase_w, phase_h), 1, border_radius=6)
            name = PHASE_NAMES_CN.get(ph, ph)
            color = (255, 255, 255) if is_active else (130, 130, 130)
            txt = app.renderer.font_small.render(name, True, color)
            screen.blit(txt, (x + phase_w // 2 - txt.get_width() // 2, phase_y + 7))

    def _draw_replay_player(self, screen, player_info, x, y, w, h, step, actions):
        """绘制回放中的玩家信息卡片"""
        app = self.app
        name = player_info.get("name", "")
        is_human = player_info.get("is_human", False)
        hole_cards = player_info.get("hole_cards", "")
        folded = player_info.get("folded", False)
        total_bet = player_info.get("total_bet", 0)
        chips_after = player_info.get("chips_after_hand", 0)

        # 检查玩家是否在当前步骤已弃牌
        player_folded_by_step = folded
        if step > 0:
            for j in range(min(step, len(actions))):
                act = actions[j]
                if act.get("player") == name and act.get("action") == "fold":
                    player_folded_by_step = True
                    break

        # 背景面板
        if player_folded_by_step:
            bg_color = (22, 22, 22)
            border_color = (60, 40, 40)
        elif is_human:
            bg_color = (28, 35, 45)
            border_color = (70, 130, 180)
        else:
            bg_color = (30, 33, 36)
            border_color = (70, 70, 70)
        pygame.draw.rect(screen, bg_color, (x, y, w, h), border_radius=6)
        pygame.draw.rect(screen, border_color, (x, y, w, h), 1, border_radius=6)

        # 名字 + 弃牌标记在同一行
        name_color = (100, 180, 255) if is_human else (220, 220, 220)
        if player_folded_by_step:
            name_color = (140, 80, 80)
        name_surf = app.renderer.font_small.render(name, True, name_color)
        screen.blit(name_surf, (x + 8, y + 6))

        if player_folded_by_step:
            fold_surf = app.renderer.font_tiny.render("已弃牌", True, (180, 60, 60))
            screen.blit(fold_surf, (x + w - 8 - fold_surf.get_width(), y + 7))

        # 底牌（用真实扑克牌素材）
        if hole_cards:
            dim = player_folded_by_step
            cards = hole_cards.split()
            cx_cards = x + w // 2
            total_w = len(cards) * 46 + (len(cards) - 1) * 4
            sx = cx_cards - total_w // 2
            for k, card_str in enumerate(cards):
                card = self._parse_card_str(card_str)
                if card:
                    card_surf = get_card_surface(card, w=46, h=66, face_up=True)
                    if dim:
                        card_surf.set_alpha(90)
                    screen.blit(card_surf, (sx + k * 50, y + 24))
        else:
            no_cards = app.renderer.font_tiny.render("（无底牌）", True, (70, 70, 70))
            screen.blit(no_cards, (x + w // 2 - no_cards.get_width() // 2, y + 40))

        # 下注 / 剩余筹码（放在真实牌图下方）
        if player_folded_by_step:
            # 已弃牌：显示最终下注，但颜色暗淡
            info_text = f"投入: {total_bet}"
            info_color = (100, 100, 100)
        else:
            info_text = f"下注: {total_bet}  |  剩余: {chips_after}"
            info_color = COLOR_GOLD if total_bet > 0 else (130, 130, 130)
        info_surf = app.renderer.font_tiny.render(info_text, True, info_color)
        screen.blit(info_surf, (x + 8, y + 92))

    def _draw_action_history(self, screen, actions, step, paused, top_y, left_x, app):
        """绘制动作历史（按阶段分组，只在阶段变化时显示阶段名）"""
        label = app.renderer.font_normal.render("动作历史", True, COLOR_GOLD)
        screen.blit(label, (left_x, top_y))

        visible_actions = actions[:step]
        max_action_rows = 12
        start_idx = max(0, len(visible_actions) - max_action_rows)

        col_phase = left_x
        col_name = left_x + 55
        col_action = left_x + 130
        col_amount = left_x + 210

        y = top_y + 30
        last_phase = None
        for j, act in enumerate(visible_actions[start_idx:], start=start_idx):
            phase = act.get("phase", "preflop")
            phase_cn = PHASE_NAMES_CN.get(phase, phase)
            player_name = act.get("player", "")
            if not player_name:
                player_name = "?"
            action_type = act.get("action", "")
            amount = act.get("amount", 0)
            action_cn = ACTION_NAMES_CN.get(action_type, action_type)
            color = ACTION_COLORS.get(action_type, (200, 200, 200))

            # 行背景
            if (j - start_idx) % 2 == 0:
                pygame.draw.rect(screen, (35, 35, 40), (left_x - 4, y - 1, SCREEN_WIDTH // 2 - 70, 22))

            # 阶段只在变化时显示，颜色更亮
            if phase != last_phase:
                phase_surf = app.renderer.font_tiny.render(phase_cn, True, (120, 220, 120))
                screen.blit(phase_surf, (col_phase, y + 1))
                last_phase = phase

            # 玩家名用白色高亮，确保可见
            name_surf = app.renderer.font_tiny.render(player_name, True, (240, 240, 240))
            screen.blit(name_surf, (col_name, y + 1))

            action_surf = app.renderer.font_tiny.render(action_cn, True, color)
            screen.blit(action_surf, (col_action, y + 1))

            if amount > 0:
                amt_surf = app.renderer.font_tiny.render(f"{amount}", True, COLOR_GOLD)
                screen.blit(amt_surf, (col_amount, y + 1))

            # 高亮当前动作
            if j == step - 1 and not paused:
                pygame.draw.rect(screen, (150, 150, 70), (left_x - 4, y - 1, SCREEN_WIDTH // 2 - 70, 22), 1, border_radius=2)

            y += 22

    def _draw_showdown(self, screen, showdown, top_y, right_x, app):
        """绘制摊牌结果"""
        label = app.renderer.font_normal.render("摊牌结果", True, COLOR_GOLD)
        screen.blit(label, (right_x, top_y))

        col_name = right_x
        col_hand = right_x + 90
        col_payout = right_x + 210
        col_net = right_x + 320

        y = top_y + 30
        for sd in showdown:
            name = sd.get("name", "")
            hand_type = sd.get("hand_type", "")
            payout = sd.get("payout", 0)
            net = sd.get("net_profit", 0)
            is_winner = payout > 0

            if is_winner:
                pygame.draw.rect(screen, (45, 80, 45), (right_x - 6, y - 2, SCREEN_WIDTH // 2 - 80, 24))

            name_color = (100, 255, 150) if is_winner else (200, 200, 200)
            name_surf = app.renderer.font_tiny.render(name, True, name_color)
            screen.blit(name_surf, (col_name, y))

            ht_surf = app.renderer.font_tiny.render(hand_type, True, (180, 180, 220))
            screen.blit(ht_surf, (col_hand, y))

            payout_str = f"派彩: {payout}"
            payout_color = COLOR_GOLD if is_winner else (120, 120, 120)
            payout_surf = app.renderer.font_tiny.render(payout_str, True, payout_color)
            screen.blit(payout_surf, (col_payout, y))

            net_str = f"净赢: {net:+d}"
            net_color = (100, 255, 100) if net > 0 else (255, 100, 100) if net < 0 else (120, 120, 120)
            net_surf = app.renderer.font_tiny.render(net_str, True, net_color)
            screen.blit(net_surf, (col_net, y))

            y += 24

    def _get_phase_at_step(self, actions, step):
        """获取当前步骤对应的阶段"""
        if step <= 0:
            return "preflop"
        if step > len(actions):
            return "showdown"
        return actions[step - 1].get("phase", "preflop")

    def _get_revealed_community(self, step, actions, comm_cards):
        """根据当前步骤计算应显示的公共牌数量"""
        if step == 0:
            return []
        if step > len(actions):
            return comm_cards

        current_phase = "preflop"
        for j in range(min(step, len(actions))):
            ph = actions[j].get("phase", "preflop")
            if ph != "unknown":
                current_phase = ph

        if current_phase == "preflop":
            return []
        elif current_phase == "flop":
            return comm_cards[:3]
        elif current_phase == "turn":
            return comm_cards[:4]
        elif current_phase == "river":
            return comm_cards[:5]
        return comm_cards

    def _parse_card_str(self, card_str: str) -> Card:
        """将日志字符串（如 K♦ / A♣ / 10♥）解析为 Card 对象"""
        if not card_str:
            return None
        card_str = card_str.strip()
        suit_symbol = card_str[-1]
        rank_str = card_str[:-1]
        suit_map = {'♠': 's', '♥': 'h', '♦': 'd', '♣': 'c'}
        suit = suit_map.get(suit_symbol)
        if not suit:
            return None
        rank_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        rank = rank_map.get(rank_str)
        if rank is None:
            return None
        return Card(rank=rank, suit=suit)

