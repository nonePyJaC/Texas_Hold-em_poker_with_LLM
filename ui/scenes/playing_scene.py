"""对局场景：AI思考/说话流程、下注轮处理、人类玩家操作"""
import pygame
from .base_scene import BaseScene


class PlayingScene(BaseScene):
    """对局进行中场景"""

    CARD_W = 160
    CARD_H = 70

    @property
    def name(self) -> str:
        return "playing"

    def handle_event(self, event):
        app = self.app
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                app._toggle_fullscreen()
                return
            if event.key == pygame.K_ESCAPE:
                # 优先关闭弹窗
                if app.selected_player_index is not None:
                    app.selected_player_index = None
                    app.player_popup_close_btn = None
                    return
                app._leave_game()
                return

        self._handle_playing_event(event)

    def _handle_playing_event(self, event):
        """处理游戏中的事件"""
        app = self.app

        # 聊天输入处理 (最高优先级，激活时拦截事件)
        if app.chat_controller.handle_event(event):
            return

        # Enter 键激活聊天 (仅在加注输入框未激活时)
        if (event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN
                and app.chat_controller.input and not app.renderer.raise_input.active):
            app.chat_controller.input.active = True
            app.chat_controller.active = True
            pygame.key.start_text_input()
            if hasattr(pygame.key, 'set_text_input_rect'):
                pygame.key.set_text_input_rect(app.chat_controller.input.rect)
            return

        # 弹窗关闭优先处理
        if app.selected_player_index is not None:
            if app.player_popup_close_btn and app.player_popup_close_btn.handle_event(event):
                app.selected_player_index = None
                app.player_popup_close_btn = None
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                app.selected_player_index = None
                app.player_popup_close_btn = None
                return

        # 离开按钮
        if app.renderer.leave_button.handle_event(event):
            self._on_leave()
            return

        # 点击 AI 玩家卡片打开详情弹窗
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and app.game:
            idx = self._find_clicked_player_index(event.pos)
            if idx >= 0:
                app.selected_player_index = idx
                return

        # 右键点击 AI 玩家卡片：艾特该 AI
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and app.game:
            idx = self._find_clicked_player_index(event.pos)
            if idx >= 0:
                app.chat_controller.activate_with_target(app.players[idx].name)
                return

        if app.ai_thinking:
            return

        current = app.game.get_current_player() if app.game else None
        if not current or not current.is_human or not current.can_act():
            return

        # 操作面板按钮
        for key, btn in app.renderer.action_buttons.items():
            if btn.handle_event(event):
                app._on_human_action(key)
                return

        # 加注滑块
        if app.renderer.raise_slider.handle_event(event):
            return

        # 加注数值输入框
        if app.renderer.raise_input.handle_event(event):
            return

    def _on_leave(self):
        """离开游戏 — 子类可覆盖为离开锦标赛"""
        self.app._leave_game()

    def _find_clicked_player_index(self, mouse_pos):
        """返回鼠标位置下的 AI 玩家索引，未命中返回 -1"""
        app = self.app
        if not app.game or not app.players:
            return -1
        positions = app.renderer.get_seat_positions(app.players)
        for i, player in enumerate(app.players):
            if player.is_human or not hasattr(player, '_char_stats'):
                continue
            pos = positions[i]
            rect = pygame.Rect(
                pos[0] - self.CARD_W // 2,
                pos[1] - self.CARD_H // 2,
                self.CARD_W,
                self.CARD_H,
            )
            if rect.collidepoint(mouse_pos):
                return i
        return -1

    def update(self, dt: float):
        app = self.app
        app.animations.update(dt)
        self._update_common(dt)
        self._update_ai_flow(dt)

    def _update_common(self, dt: float):
        """公共更新：LLM轮询、情绪衰减、行动对话计时器"""
        app = self.app

        # 轮询 LLM 异步结果
        if hasattr(app, 'dialogue_manager') and app.dialogue_manager:
            llm_result = app.dialogue_manager.poll_llm_result()
            if llm_result:
                app.ai_action_dialogue = llm_result
                app.ai_action_dialogue_timer = llm_result.duration
                app.ai_action_dialogue_name = llm_result.metadata.get("char_name", "")
                app.ai_action_dialogue_revealed = ""
                app.ai_action_dialogue_reveal_timer = 0.0
                app.chat_controller.add_message(
                    llm_result.metadata.get("char_name", ""),
                    llm_result.text,
                    "llm",
                    replace_last_template=True,
                )

        # 轮询 AI 回复玩家聊天的结果
        if hasattr(app, 'dialogue_manager') and app.dialogue_manager:
            replies = app.dialogue_manager.poll_replies()
            for reply in replies:
                app.chat_controller.add_message(
                    reply.metadata.get("char_name", ""),
                    reply.text,
                    "llm"
                )

        # 情绪衰减
        if hasattr(app, 'players'):
            for p in app.players:
                if not p.is_human and hasattr(p, 'emotion_engine'):
                    p.emotion_engine.decay(dt)

        # 行动对话计时器
        if app.ai_action_dialogue_timer > 0:
            app.ai_action_dialogue_timer -= dt
            if app.ai_action_dialogue:
                dialogue_text = app.ai_action_dialogue.text if hasattr(app.ai_action_dialogue, 'text') else str(app.ai_action_dialogue)
                app.ai_action_dialogue_reveal_timer += dt
                target_len = min(len(dialogue_text), int(app.ai_action_dialogue_reveal_timer / 0.08) + 1)
                if target_len > len(app.ai_action_dialogue_revealed):
                    app.ai_action_dialogue_revealed = dialogue_text[:target_len]
            if app.ai_action_dialogue_timer <= 0:
                app.ai_action_dialogue = None
                app.ai_action_dialogue_timer = 0
                app.ai_action_dialogue_revealed = ""

    def _update_ai_flow(self, dt: float):
        """AI 思考/说话流程 + 下注轮处理"""
        app = self.app
        if app.ai_thinking:
            app.ai_think_timer += dt
            if app.ai_think_timer >= app.ai_action_delay:
                app.ai_controller.start_decision()
            import time as _t
            _ai_t0 = _t.perf_counter()
            action = app.ai_controller.poll_decision()
            _ai_t1 = _t.perf_counter()
            try:
                from utils.perf_monitor import get_monitor
                get_monitor().record_phase("ai_decision", _ai_t1 - _ai_t0)
            except Exception:
                pass
            if action is not None:
                app.ai_thinking = False
                app.ai_speaking = True
                app.ai_speak_timer = 0.0
                app._pending_ai_action = action
        elif app.ai_speaking:
            app.ai_speak_timer += dt
            dialogue_text = ""
            if app.ai_action_dialogue:
                dialogue_text = app.ai_action_dialogue.text if hasattr(app.ai_action_dialogue, 'text') else str(app.ai_action_dialogue)
            reveal_done = len(app.ai_action_dialogue_revealed) >= len(dialogue_text)
            min_done = app.ai_speak_timer >= app.ai_speak_min_time
            max_done = app.ai_speak_timer >= app.ai_speak_max_time
            if min_done and (reveal_done or max_done):
                app.ai_speaking = False
                app.ai_controller.execute_action(app._pending_ai_action)
                app._pending_ai_action = None
                app._advance_after_action()
        else:
            app._process_betting_round()

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_playing()
        app._present()
